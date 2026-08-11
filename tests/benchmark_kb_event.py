"""KB-005 — Event_type utk key: role vs jenis_kegiatan vs kelompok_kegiatan.

Pertanyaan desain #1 (kb_design.md): pipeline perlu ekstrak `jenis_kegiatan`
beneran utk key, atau cukup role proxy? Jawaban diukur dari yang TERSEDIA
offline (0 LLM): `map_kelompok_dan_jenis` menghasilkan kelompok & jenis.

Desain: 4 varian normalisasi key (plain/stem/alias/both) × 3 event
(role/jenis/kelompok) = 12 kombinasi. Per cert label diekstrak SEKALI
(cache), lalu key dirakit via `make_key` — efisien, tanpa re-extract.

Metrik per kombinasi:
- keys / repeated keys / empty rate (key mati krn event kosong/`"--"`)
- collision: key → tingkat pipeline beda (gate 0)
- ceiling seeded (label = GT cert pertama utk key berulang): hits, wrong
- shadow 3x N=20: hits, disagree, wrong (gate 0)
- noise OCR 25%: wrong (gate 0)

Gate KB-005:
- G1 collision = 0 semua kombinasi
- G2 seeded wrong = 0 + noise wrong = 0
- G3 hit >= 5 (best KB-003)
- G4 empty rate dilaporkan jujur (risiko nyata jenis_kegiatan)

Usage:
  uv run python -m tests.benchmark_kb_event
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
from tests.kb.key import EVENTS, KEY_VARIANTS, compute_event, make_key, normalize_organizer, normalize_role
from tests.llm_router_v4 import route_tingkat_trace
from tests.matchers import match_field
from tests.ood_probe import inject_noise, load_gt, load_texts
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"kb_event_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "kb_event.md")

SEED = 42
WARM_N = 20
CONFIRMS = 3


def load_cache(texts: dict[str, str], gt: dict[str, dict],
               tingkat_pipe: dict[str, str]) -> dict[str, dict]:
    """Satu kali ekstraksi per cert → semua kombinasi pakai cache."""
    rows = {}
    for stem in sorted(texts):
        text = texts[stem]
        extracted = extract_certificate_fields(text)
        org_raw = extract_organizer_v2(text)
        rv = extracted.get("raw_role")
        role_raw = rv.value if rv and rv.value else None
        decision, _ = route_tingkat_trace(text, org_raw or "")
        label = decision if decision else tingkat_pipe.get(stem)
        jenis, kelompok = compute_event(text, role_raw, org_raw)
        gv = (gt.get(stem) or {}).get("tingkat") or ""
        rows[stem] = {
            "org": normalize_organizer(org_raw, text),
            "role": normalize_role(role_raw),
            "jenis": jenis,
            "kelompok": kelompok,
            "label": label,
            "routed": decision is not None,
            "gt": gv.strip() if gv.strip() and gv.strip() != "-" else None,
        }
    return rows


def run_combo(cache: dict[str, dict], variant: str, event: str) -> dict:
    """Ceiling seeded + collision + shadow 3x utk satu kombinasi."""
    freq: dict[tuple, int] = {}
    by_key: dict[tuple, set] = {}
    first_gt: dict[tuple, str] = {}
    keys: dict[str, tuple | None] = {}
    for stem, r in cache.items():
        k = make_key(r["org"], r["role"] if event == "role" else r[event],
                     variant, event)
        keys[stem] = k
        if k:
            freq[k] = freq.get(k, 0) + 1
            if r["label"]:
                by_key.setdefault(k, set()).add(r["label"])
            if r["gt"] and k not in first_gt:
                first_gt[k] = r["gt"]

    kb = TingkatKB()
    kbimpl.WARMUP_CONFIRMS = 1  # seed human_review = otoritas segera
    for k, n in freq.items():
        if n >= 2 and k in first_gt:
            kb.write(k, KBEntry(first_gt[k], "human_review", "seed"))
    # NOTE: WARMUP_CONFIRMS tetap 1 selama ceiling eval (seed authoritative);
    # shadow 3x di bawah mengembalikan ke 3.

    stats = {"variant": variant, "event": event, "certs": len(cache),
             "keys": len(freq),
             "repeated": sum(1 for n in freq.values() if n >= 2),
             "repeated_certs": sum(n for n in freq.values() if n >= 2),
             "empty": sum(1 for k in keys.values() if k is None),
             "collisions": sum(1 for v in by_key.values() if len(v) > 1),
             "seeds": len(kb), "hits": 0, "saved_llm": 0, "wrong": 0,
             "exact_kb": 0, "exact_pipe": 0}

    for stem, r in cache.items():
        k = keys[stem]
        entry = kb.peek(k) if k else None
        if r["gt"]:
            stats["exact_pipe"] += 1 if match_field(r["gt"], r["label"], "tingkat")["exact"] else 0
            if entry and entry.authoritative:
                stats["hits"] += 1
                if not r["routed"]:
                    stats["saved_llm"] += 1
                if match_field(r["gt"], entry.tingkat, "tingkat")["exact"]:
                    stats["exact_kb"] += 1
                else:
                    stats["wrong"] += 1

    # shadow 3x: warm pertama, eval sisa
    kbimpl.WARMUP_CONFIRMS = CONFIRMS
    kb2 = TingkatKB()
    stems = sorted(cache)
    warm = set(stems[:WARM_N])
    s = {"hits": 0, "saved_llm": 0, "disagree": 0, "wrong": 0}
    for stem in stems:
        r = cache[stem]
        k = keys[stem]
        if k:
            kb2.write(k, KBEntry(r["label"] or "Lainnya",
                                 "router_rule" if r["routed"] else "llm", stem))
        if stem not in warm and r["gt"]:
            entry = kb2.peek(k) if k else None
            if entry and entry.authoritative:
                s["hits"] += 1
                if not r["routed"]:
                    s["saved_llm"] += 1
                if entry.tingkat != r["label"]:
                    s["disagree"] += 1
                if not match_field(r["gt"], entry.tingkat, "tingkat")["exact"]:
                    s["wrong"] += 1
    stats.update({"shadow_hits": s["hits"], "shadow_saved": s["saved_llm"],
                  "shadow_disagree": s["disagree"], "shadow_wrong": s["wrong"]})
    return stats


def render_md(rows: list[dict]) -> str:
    lines = [
        "# KB-005 — Event_type utk key: role vs jenis_kegiatan vs kelompok_kegiatan",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"pipeline = run v9 + router CURRENT | 0 LLM runtime | seed {SEED}",
        "",
        "Pertanyaan desain #1 (kb_design.md): cukup role proxy, atau perlu "
        "ekstrak `jenis_kegiatan` beneran? Diukur dari `map_kelompok_dan_jenis` "
        "(offline, 0 LLM) — 4 varian normalisasi key × 3 event = 12 kombinasi.",
        "",
        "| Varian | Event | Keys | Repeat (cert) | Empty | Collision | Seeds | Hit | Saved | Wrong | Exact KB / Pipe | Shadow hit (3x) | Shadow disagree | Shadow wrong |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        t = r["certs"]
        lines.append(
            f"| {r['variant']} | {r['event']} | {r['keys']} | {r['repeated']} ({r['repeated_certs']}) | "
            f"{r['empty']} | {r['collisions']} | {r['seeds']} | {r['hits']} | {r['saved_llm']} | "
            f"{r['wrong']} | {r['exact_kb']}/{t} ({r['exact_kb'] / t * 100 if t else 0:.1f}%) / "
            f"{r['exact_pipe']}/{t} ({r['exact_pipe'] / t * 100 if t else 0:.1f}%) | "
            f"{r['shadow_hits']} | {r['shadow_disagree']} | {r['shadow_wrong']} |"
        )
    lines += [
        "",
        "## Interpretasi",
        "",
        "- `Empty` = cert yang key-nya mati (event kosong/`--`). `jenis_kegiatan` "
        "sering `--` → key mati; `kelompok` selalu non-empty (5 kategori).",
        "- `Collision` = key sama → tingkat pipeline beda (gate 0).",
        "- `Wrong`/`Shadow wrong`/`Shadow disagree` = 0 = aman.",
        "- Keputusan desain: event mana yg menang (repeat keys tinggi, empty "
        "rendah, hit tinggi, collision 0). Ini jawaban utk schema produksi KB "
        "(kapan pun dipromosikan).",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    tingkat_pipe = load_pipeline_tingkat()
    print(f"Corpus: {len(texts)} certs")

    cache = load_cache(texts, gt, tingkat_pipe)
    rows = []
    for variant in KEY_VARIANTS:
        for event in EVENTS:
            r = run_combo(cache, variant, event)
            rows.append(r)
            print(f"[{variant}/{event}] keys={r['keys']} repeat={r['repeated']}({r['repeated_certs']}) "
                  f"empty={r['empty']} coll={r['collisions']} hit={r['hits']} "
                  f"shadow_hit={r['shadow_hits']} wrong={r['wrong']}/{r['shadow_wrong']}")

    rng = random.Random(SEED)
    noisy = {s: inject_noise(t, 0.25, rng) for s, t in texts.items()}
    ncache = load_cache(noisy, gt, tingkat_pipe)
    noise_rows = []
    for variant in KEY_VARIANTS:
        for event in EVENTS:
            r = run_combo(ncache, variant, event)
            noise_rows.append(r)
    print("Noise 25% shadow wrong:", [(r["variant"], r["event"], r["shadow_wrong"]) for r in noise_rows])

    summary = {"rows": rows, "noise": noise_rows, "seed": SEED,
               "gt": os.path.basename(GT_CSV), "matcher": "v2",
               "macro_avg": {"exact_acc": rows[0]["exact_pipe"] / rows[0]["certs"] if rows[0]["certs"] else 0.0}}
    with open(os.path.join(OUT_DIR, "summary_kb_event.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(rows))
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_kb_event.json")


if __name__ == "__main__":
    main()
