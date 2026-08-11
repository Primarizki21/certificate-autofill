"""KB-004 — Audit korpus teks utk KB tingkat (TANPA GT; alat gate data riil).

Menjawab pertanyaan gate produksi sebelum data real: "di korpus ini ada
berapa key berulang, collision, dan berapa LLM call yang bisa dihemat KB?"

Input: direktori berisi *.txt (format `extracted_texts`). Zero LLM, zero OCR:
- tingkat pipeline per cert = router (route_tingkat_trace) → fallback
  offline (map_fields_to_form, ENABLE_LLM_TINGKAT false = map_tingkat legacy).
- key = canonicalizer v1 plain (variant bisa dipilih via --variant).

Output per audit:
- unique organizer v3 / key unik / distribusi frekuensi / repeated keys
- fragmentasi org logis (stem grouping, dari KB-002)
- collision: key → tingkat pipeline berbeda (gate produksi: harus di-review)
- proyeksi saved LLM: replay 3x confirm, urutan sorted-stem, warm N pertama;
  saved = authoritative hit saat router miss; LLM fallback (tanpa KB) =
  jumlah cert router-miss
- JSON + report md ke run dir + docs/report/kb_audit.md

Dry-run selfcheck: korpus 74 harus konsisten dgn KB-001 (55 key unik, 3
repeated, key version v1-plain).

Usage:
  uv run python -m tests.kb.audit --dir tests/benchmark_runs/run_20260728_131835/extracted_texts
  uv run python -m tests.kb.audit --dir <dir_data_riil> --out <run_dir_baru>
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
import tests.kb.kb as kbimpl
from tests.kb.kb import KBEntry, TingkatKB
from tests.kb.key import KEY_VARIANTS, build_key
from tests.llm_router_v4 import route_tingkat_trace
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DEFAULT_TEXTS = os.path.join(REPO, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts")
OUT_MD = os.path.join(REPO, "docs", "report", "kb_audit.md")

# Konsistensi dry-run dgn KB-001 (diagnostics: 55 key unik, 3 repeated)
SELFCHECK_KEYS = 55
SELFCHECK_REPEATED = 3

# Proyeksi replay
WARM_N = 20
CONFIRMS = 3


def pipeline_label(stem: str, text: str, variant: str) -> tuple[tuple | None, str | None, bool]:
    """(key, tingkat pipeline, routed) — zero LLM, zero OCR."""
    extracted = extract_certificate_fields(text)
    org = extract_organizer_v2(text)
    if org:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(org, 0.84, "organizer_v2")
    rv = extracted.get("raw_role")
    role = rv.value if rv and rv.value else None
    key = build_key(org, role, text, variant=variant)
    decision, _ = route_tingkat_trace(text, org or "")
    if decision:
        return key, decision, True
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    t = mapped.get("tingkat")
    return key, (t.value if t else None), False


def logical_org(v: str) -> str:
    words = [re.sub(r"s$", "", w) if len(w) > 3 else w
             for w in re.sub(r"[^a-z0-9]+", " ", v.lower()).split()]
    return "".join(words)


def audit(texts: dict[str, str], variant: str) -> dict:
    keys: dict[tuple, int] = {}
    orgs: dict[str, int] = {}
    by_key: dict[tuple, set] = {}
    labels: dict[str, tuple | None] = {}
    for stem in sorted(texts):
        key, level, routed = pipeline_label(stem, texts[stem], variant)
        labels[stem] = (key, level, routed)
        if key:
            keys[key] = keys.get(key, 0) + 1
            orgs[key[0]] = orgs.get(key[0], 0) + 1
            if level:
                by_key.setdefault(key, set()).add(level)
    repeated = {k: n for k, n in keys.items() if n >= 2}

    # fragmentasi: org logis dengan >1 key
    groups: dict[str, list[tuple]] = {}
    for k, n in keys.items():
        if n >= 2:
            groups.setdefault(logical_org(k[0]), []).append(k)
    frags = [{"logical_org": o, "keys": len(ks), "certs": sum(keys[k] for k in ks)}
             for o, ks in groups.items() if len(ks) > 1]

    # proyeksi saved LLM (3x confirm, warm N pertama, urutan sorted)
    kbimpl.WARMUP_CONFIRMS = CONFIRMS
    kb = TingkatKB()
    stems = sorted(texts)
    warm, eval_stems = set(stems[:WARM_N]), stems[WARM_N:]
    hits = saved = 0
    llm_fallback = sum(1 for s in stems if labels[s][2] is False)
    routed_n = len(stems) - llm_fallback
    for stem in stems:
        key, level, routed = labels[stem]
        if key:
            kb.write(key, KBEntry(level or "Lainnya",
                                  "router_rule" if routed else "llm", stem))
        if stem in eval_stems:
            entry = kb.peek(key) if key else None
            if entry and entry.authoritative:
                hits += 1
                if not routed:
                    saved += 1
    kbimpl.WARMUP_CONFIRMS = 3

    return {
        "variant": variant,
        "n_certs": len(texts),
        "unique_orgs": len(orgs),
        "unique_keys": len(keys),
        "repeated_keys": len(repeated),
        "repeated_certs": sum(repeated.values()),
        "top_keys": [{"key": [k[0], k[1]], "n": n}
                     for k, n in sorted(repeated.items(), key=lambda x: -x[1])[:10]],
        "collisions": sum(1 for v in by_key.values() if len(v) > 1),
        "collision_examples": [
            {"key": [k[0], k[1]], "levels": sorted(v)} for k, v in by_key.items() if len(v) > 1
        ][:5],
        "fragmentation": frags,
        "projection": {"warm_n": WARM_N, "confirms": CONFIRMS, "routed": routed_n,
                       "llm_fallback_no_kb": llm_fallback, "kb_hits": hits,
                       "saved_llm": saved},
    }


def render_md(r: dict) -> str:
    lines = [
        "# KB-004 — Audit korpus utk KB tingkat (tanpa GT)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"variant {r['variant']} | pipeline = router + fallback offline (0 LLM) | "
        f"proyeksi 3x confirm, warm {r['projection']['warm_n']}",
        "",
        f"- Cert: {r['n_certs']} | organizer unik (v3): {r['unique_orgs']} | "
        f"key unik: {r['unique_keys']} | key berulang: {r['repeated_keys']} "
        f"({r['repeated_certs']} cert)",
        "",
        "## Key berulang (kandidat KB)",
        "",
        "| Organizer | Role | Frekuensi |",
        "|---|---|---|",
    ]
    for t in r["top_keys"]:
        lines.append(f"| {t['key'][0]} | {t['key'][1]} | {t['n']} |")
    lines += [
        "",
        "## Collision (key sama → tingkat pipeline beda)",
        "",
        f"Jumlah: {r['collisions']}",
    ]
    for c in r["collision_examples"]:
        lines.append(f"- {c['key'][0]} + {c['key'][1]} → {c['levels']}")
    lines += [
        "",
        "## Fragmentasi org logis (>1 key utk 1 org)",
        "",
        "| Org logis | Keys | Certs |",
        "|---|---|---|",
    ]
    for f in r["fragmentation"]:
        lines.append(f"| {f['logical_org']} | {f['keys']} | {f['certs']} |")
    p = r["projection"]
    lines += [
        "",
        "## Proyeksi KB (3x confirm, warm N pertama)",
        "",
        f"| Routed (router) | LLM fallback tanpa KB | KB hits (eval) | Saved LLM |",
        "|---|---|---|---|",
        f"| {p['routed']} | {p['llm_fallback_no_kb']} | {p['kb_hits']} | {p['saved_llm']} |",
        "",
        "## Interpretasi",
        "",
        "- `repeated_keys`/`repeated_certs` = potensi gain KB (LLM call saved). "
        "Kecil = korpus belum membuktikan KB hemat (korpus 74: 3/9).",
        "- `collisions` > 0 = key yang TIDAK boleh authoritative tanpa review "
        "manusia (tambah rule/alias atau flag).",
        "- `fragmentation` = kerugian exact-match; normalisasi key (KB-003) "
        "atau alias table.",
        "- Angka ini = gate data riil: sebelum produksi, ulangi audit di korpus "
        "lintas fakultas.",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit korpus teks utk KB tingkat")
    ap.add_argument("--dir", default=DEFAULT_TEXTS)
    ap.add_argument("--variant", default="plain", choices=KEY_VARIANTS)
    ap.add_argument("--out", default=None, help="run dir (default benchmark_runs/kb_audit_<ts>)")
    args = ap.parse_args()

    texts = {}
    for fn in sorted(os.listdir(args.dir)):
        if fn.endswith(".txt"):
            with open(os.path.join(args.dir, fn), encoding="utf-8", errors="replace") as f:
                texts[os.path.splitext(fn)[0]] = f.read()
    print(f"Corpus: {len(texts)} certs dari {args.dir} | variant {args.variant}")

    r = audit(texts, args.variant)

    out_dir = args.out or os.path.join(REPO, "tests", "benchmark_runs",
                                       f"kb_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "summary_kb_audit.json"), "w") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(r))
    print(f"keys={r['unique_keys']} repeated={r['repeated_keys']} "
          f"collisions={r['collisions']} saved_llm={r['projection']['saved_llm']}")
    print(f"wrote {OUT_MD}")
    print(f"wrote {out_dir}/summary_kb_audit.json")

    if os.path.abspath(args.dir) == os.path.abspath(DEFAULT_TEXTS):
        ok = (r["unique_keys"] == SELFCHECK_KEYS and r["repeated_keys"] == SELFCHECK_REPEATED)
        print(f"SELFCHECK: keys {r['unique_keys']}=={SELFCHECK_KEYS}, "
              f"repeated {r['repeated_keys']}=={SELFCHECK_REPEATED} → {'PASS' if ok else 'FAIL'}")
        if not ok:
            raise SystemExit("selfcheck FAIL — audit tidak konsisten dgn KB-001")


if __name__ == "__main__":
    main()
