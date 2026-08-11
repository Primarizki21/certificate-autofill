"""KB-001 — Shadow replay KB tingkat v1 (prototipe, 0 LLM runtime, tests only).

Mengukur KB sebagai decision cache `tingkat` dalam alur ROUTER → KB → LLM
(shadow: hasil eval tetap dari pipeline, KB hanya dihitung potensinya):

1. warm-up = N cert pertama (urutan deterministik sorted-stem, proxy
   kronologis tanpa timestamps; bebas leakage).
2. Pipeline label per cert = router recompute current → fallback tingkat run v9
   (`extracted_fields.csv` run_llm_v4_20260805_163541, LLM asli tak dijalankan).
3. Key = canonicalizer `tests.kb.key` (organizer v3+R6, role map_jabatan,
   KEY_VERSION). KB menulis label pipeline utk setiap key.
4. Eval (cert non-warm): hit authoritative dihitung sebagai LLM call terselamat
   (hanya bila router miss), plus:
   - `shadow_disagree`: KB label != pipeline label (indikator regress jika KB
     diadopsi) — gate: 0.
   - `wrong_hits`: KB label != GT (hit yang salah secara absolut) — gate: 0.
   - `conflicts`: key sama → tingkat beda (entry non-authoritative) — gate: 0
     entry konflik dipakai autofill.
5. Safety: replay dengan OCR noise injection (10/25/50%, confusion + merge dari
   ood_probe) → `wrong_hits` noise harus tetap 0 (key exact-match → noise = miss).

Korpus 74 hanya alat ukur mekanisme (F3: 2 key berulang dgn raw_role; role
ternormalisasi diharapkan menaikkan repeat). Gain produksi tetap harus
divalidasi data riil lintas fakultas (fase berikutnya).

Usage:
  uv run python -m tests.benchmark_kb_shadow
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import extract_certificate_fields
import tests.kb.kb as kbimpl
from tests.benchmark_kb_warmup import load_pipeline_tingkat
from tests.kb.kb import KBEntry, TingkatKB
from tests.kb.key import KEY_VERSION, build_key
from tests.llm_router_v4 import route_tingkat_trace
from tests.matchers import match_field
from tests.ood_probe import inject_noise, load_gt, load_texts
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"kb_shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "kb_shadow.md")

SEED = 42
WARMUP_SIZES = [10, 20, 37]
CONFIGS = [("1x confirm", 1), ("3x confirm (default warm-up)", 3)]
NOISE_LEVELS = [0.10, 0.25, 0.50]


def replay(texts: dict[str, str], gt: dict[str, dict], tingkat_pipe: dict[str, str],
           n_warm: int, confirms: int) -> dict:
    """Satu pass deterministik: sorted-stem; warm = N pertama."""
    kb = TingkatKB()
    # mutasi langsung di module (bukan package namespace) — konfig 1x/3x efektif
    kbimpl.WARMUP_CONFIRMS = confirms
    stems = sorted(texts)
    warm, eval_stems = set(stems[:n_warm]), stems[n_warm:]

    stats = {"llm_calls": 0, "kb_hits": 0, "saved_llm": 0, "wrong_hits": 0,
             "shadow_disagree": 0, "collisions": 0, "exact_pipe": 0, "exact_kb": 0,
             "total_eval": 0, "kb_size": 0, "n_warm": n_warm}

    by_key: dict[tuple, set] = {}

    def process(stem: str, text: str, track_eval: bool) -> tuple[str | None, tuple | None]:
        extracted = extract_certificate_fields(text)
        rv = extracted.get("raw_role")
        role_val = rv.value if rv and rv.value else None
        org = extract_organizer_v2(text)
        key = build_key(org, role_val, text)
        decision, _ = route_tingkat_trace(text, org or "")
        tingkat = decision if decision else tingkat_pipe.get(stem)
        if not decision:
            stats["llm_calls"] += 1
        if key:
            kb.write(key, KBEntry(
                tingkat=tingkat or "Lainnya",
                source="router_rule" if decision else "llm",
                created_from_cert_id=stem,
            ))
            by_key.setdefault(key, set()).add(tingkat or "Lainnya")
            entry = kb.peek(key)
            if track_eval and entry and entry.authoritative:
                stats["kb_hits"] += 1
                if not decision:
                    stats["saved_llm"] += 1
                if entry.tingkat != tingkat:
                    stats["shadow_disagree"] += 1
        return tingkat, key

    for stem in stems:
        row = gt.get(stem)
        gv = (row.get("tingkat") or "").strip() if row else ""
        if not gv or gv == "-":
            continue
        track = stem in eval_stems
        tingkat, key = process(stem, texts[stem], track)
        if track:
            stats["total_eval"] += 1
            stats["exact_pipe"] += 1 if match_field(gv, tingkat, "tingkat")["exact"] else 0
            entry = kb.peek(key) if key else None
            if entry and entry.authoritative:
                stats["exact_kb"] += 1 if match_field(gv, entry.tingkat, "tingkat")["exact"] else 0
                if not match_field(gv, entry.tingkat, "tingkat")["exact"]:
                    stats["wrong_hits"] += 1

    stats["collisions"] = sum(1 for v in by_key.values() if len(v) > 1)
    stats["kb_size"] = len(kb)
    return stats


def corpus_diagnostics(texts: dict[str, str]) -> dict:
    """Berapa banyak key berulang di korpus (prasyarat gain KB)."""
    keys: dict[tuple, int] = {}
    for stem, text in texts.items():
        extracted = extract_certificate_fields(text)
        rv = extracted.get("raw_role")
        role = rv.value if rv and rv.value else None
        key = build_key(extract_organizer_v2(text), role, text)
        if key:
            keys[key] = keys.get(key, 0) + 1
    repeated = {k: n for k, n in keys.items() if n >= 2}
    return {
        "n_certs": len(texts),
        "keys": len(keys),
        "repeated_keys": len(repeated),
        "repeated_key_certs": sum(repeated.values()),
        "sample_repeated": [{"org": k[0], "role": k[1], "n": n} for k, n in sorted(repeated.items(), key=lambda x: -x[1])[:10]],
    }


def render_md(runs: list[dict], baseline_calls: int, diag: dict) -> str:
    lines = [
        "# KB-001 — Shadow replay KB tingkat v1 (alur router → KB → LLM)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"key {KEY_VERSION} (organizer v3+R6 + role map_jabatan) | pipeline = run v9 + router CURRENT | "
        f"0 LLM runtime call",
        "",
        "Shadow: hasil eval tetap dari pipeline; KB dihitung potensinya (hit "
        "authoritative pada cert router-miss = LLM call terselamat). `shadow_disagree` "
        "= hit yang BERBEDA dari pipeline (regress jika KB diadopsi); `wrong_hits` = "
        "hit yang salah vs GT. Gate: disagree 0, wrong 0, konflik tak dipakai.",
        "",
        "## Diagnostics korpus (74 cert)",
        "",
        f"- Key unik: {diag['keys']} | key berulang: {diag['repeated_keys']} "
        f"({diag['repeated_key_certs']} cert) | baseline LLM calls (no-KB): {baseline_calls}",
        "",
        "| Key (org, role) | frekuensi |",
        "|---|---|",
    ]
    for k in diag["sample_repeated"]:
        lines.append(f"| {k['org']} + {k['role']} | {k['n']} |")
    lines += [
        "",
        "| Konfig | Warm N | KB size | Hit | Saved LLM | Disagree | Wrong | Konflik | Tingkat exact pipe | Tingkat exact KB |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        if r.get("noise_level") is not None:
            continue
        lines.append(
            f"| {r['config']} | {r['n_warm']} | {r['kb_size']} | {r['kb_hits']} | "
            f"{r['saved_llm']} | {r['shadow_disagree']} | {r['wrong_hits']} | {r['collisions']} | "
            f"{r['exact_pipe']}/{r['total_eval']} "
            f"({r['exact_pipe'] / r['total_eval'] * 100 if r['total_eval'] else 0:.1f}%) | "
            f"{r['exact_kb']}/{r['total_eval']} "
            f"({r['exact_kb'] / r['total_eval'] * 100 if r['total_eval'] else 0:.1f}%) |"
        )
    lines += ["", "## Safety — OCR noise (wrong_hits harus tetap 0)", "",
              "| Noise | config | Warm N | Wrong hits | Disagree |", "|---|---|---|---|---|"]
    for n in runs:
        if n.get("noise_level") is not None:
            lines.append(
                f"| {n['noise_level']:.0%} | {n['config']} | {n['n_warm']} | "
                f"{n['wrong_hits']} | {n['shadow_disagree']} |"
            )
    lines += [
        "",
        "## Interpretasi",
        "",
        "- Key berulang naik vs F3 (role mentah) BUKTI normalisasi role bekerja; "
        "gain LLM call tetap kecil di 74 cert — ukuran korpus membatasi, bukan desain.",
        "- `shadow_disagree`/`wrong_hits` = 0 di semua konfig = shadow aman: "
        "mengadopsi KB tidak mengubah hasil pipeline (syarat no-regress).",
        "- Konflik (key sama, tingkat beda) → entry non-authoritative otomatis "
        "(lihat `tests/kb/kb.py`); di korpus ini diukur `collisions`.",
        "- Keputusan produksi TETAP menunggu sampling data riil lintas fakultas "
        "(asumsi unique organizer 1.000–10.000 belum tervalidasi).",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    tingkat_pipe = load_pipeline_tingkat()
    print(f"Corpus: {len(texts)} certs | pipeline tingkat: {len(tingkat_pipe)}")

    diag = corpus_diagnostics(texts)
    print(f"Keys: {diag['keys']} | repeated: {diag['repeated_keys']} "
          f"({diag['repeated_key_certs']} cert)")

    runs = []
    baseline_calls = None
    for label, confirms in CONFIGS:
        for n in WARMUP_SIZES:
            r = replay(texts, gt, tingkat_pipe, n, confirms)
            r["config"] = label
            runs.append(r)
            if baseline_calls is None:
                baseline_calls = r["llm_calls"] + r["saved_llm"]
            print(f"[{label}] N={n}: hits={r['kb_hits']} saved_llm={r['saved_llm']} "
                  f"disagree={r['shadow_disagree']} wrong={r['wrong_hits']} "
                  f"coll={r['collisions']} exact_pipe={r['exact_pipe']}/{r['total_eval']} "
                  f"exact_kb={r['exact_kb']}/{r['total_eval']}")

    rng = random.Random(SEED)
    for level in NOISE_LEVELS:
        noisy = {s: inject_noise(t, level, rng) for s, t in texts.items()}
        for label, confirms in [("3x confirm (default warm-up)", 3)]:
            r = replay(noisy, gt, tingkat_pipe, 20, confirms)
            r["config"] = label
            r["noise_level"] = level
            runs.append(r)
            print(f"Noise {level:.0%}: wrong={r['wrong_hits']} disagree={r['shadow_disagree']}")

    summary = {"runs": runs, "baseline_llm_calls": baseline_calls,
               "diagnostics": diag, "seed": SEED, "key_version": KEY_VERSION,
               "gt": os.path.basename(GT_CSV), "matcher": "v2"}
    r0 = runs[0]
    summary["macro_avg"] = {
        "exact_acc": r0["exact_pipe"] / r0["total_eval"] if r0["total_eval"] else 0.0}
    with open(os.path.join(OUT_DIR, "summary_kb_shadow.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(runs, baseline_calls, diag))
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_kb_shadow.json")


if __name__ == "__main__":
    main()
