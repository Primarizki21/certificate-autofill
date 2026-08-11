"""KB-003 — Normalisasi key v2: ukur 4 varian (plain/stem/alias/both).

Masalah (KB-002): exact-match memecah 1 org logis (FST INFORMATION SYSTEMS
DEPT vs Information System Dept., 7 cert) → hit rate KB turun. KB-003 mengukur
apakah normalisasi key (stem / alias / both) menaikkan hit tanpa menimbulkan
collision baru.

Per varian (key version `v1-{variant}`, snapshot tak tercampur):
1. plain — baseline KB-001/002 (organizer v3+R6 apa adanya).
2. stem — case/punct collapse + singular-stem per kata (>3 huruf).
3. alias — tabel alias eksplisit data-driven (FST pair).
4. both — alias dulu, lalu stem.

Metrik per varian (semua 0 LLM runtime, GT v9 + matcher v2):
- unique keys / repeated keys / certs tercakup
- ceiling seeded (label = GT cert pertama utk key berulang freq>=2): hit,
  saved_llm, wrong vs GT, disagree vs pipeline
- collision: key → tingkat pipeline beda (over-merge risk) — gate 0
- fragmentasi teratasi: org logis FST jadi 1 key?
- safety noise 25%: wrong hits — gate 0
- shadow 3x confirm N=20: disagree/wrong — gate 0

Gate KB-003:
- G1 collision = 0 (stem/both tidak over-merge di korpus)
- G2 seeded wrong = 0 + noise 25% wrong = 0 (semua varian)
- G3 hit >= 9 (baseline plain) — varian lebih baik/imbang
- G4 shadow 3x disagree/wrong = 0

Usage:
  uv run python -m tests.benchmark_kb_norm
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
from tests.kb.key import KEY_VARIANTS, build_key
from tests.llm_router_v4 import route_tingkat_trace
from tests.matchers import match_field
from tests.ood_probe import inject_noise, load_gt, load_texts
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"kb_norm_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "kb_norm.md")

SEED = 42


def _label(stem: str, text: str, tingkat_pipe: dict[str, str],
           variant: str) -> tuple[tuple | None, str | None, bool]:
    extracted = extract_certificate_fields(text)
    rv = extracted.get("raw_role")
    role = rv.value if rv and rv.value else None
    org = extract_organizer_v2(text)
    key = build_key(org, role, text, variant=variant)
    decision, _ = route_tingkat_trace(text, org or "")
    tingkat = decision if decision else tingkat_pipe.get(stem)
    return key, tingkat, decision is not None


def run_variant(texts: dict[str, str], gt: dict[str, dict],
                tingkat_pipe: dict[str, str], variant: str) -> dict:
    """Ceiling seeded + collision + fragmentasi per varian (tanpa learning)."""
    kbimpl.WARMUP_CONFIRMS = 1  # seed human_review = otoritas segera
    freq: dict[tuple, int] = {}
    first_label: dict[tuple, str] = {}
    by_key: dict[tuple, set] = {}
    for stem in sorted(texts):
        key, label, _ = _label(stem, texts[stem], tingkat_pipe, variant)
        if key:
            freq[key] = freq.get(key, 0) + 1
            if label:
                by_key.setdefault(key, set()).add(label)
            gv = (gt.get(stem) or {}).get("tingkat") or ""
            if gv.strip() and gv.strip() != "-" and key not in first_label:
                first_label[key] = gv.strip()

    kb = TingkatKB()
    for k, n in freq.items():
        if n >= 2 and k in first_label:
            kb.write(k, KBEntry(first_label[k], "human_review", "seed"))

    stats = {"variant": variant, "keys": len(freq), "repeated_keys": 0,
             "repeated_certs": 0, "seeds": len(kb), "hits": 0, "saved_llm": 0,
             "wrong_hits": 0, "disagree": 0, "collisions": 0,
             "exact_kb": 0, "exact_pipe": 0, "total_eval": 0, "fst_merged": 0}
    for k, n in freq.items():
        if n >= 2:
            stats["repeated_keys"] += 1
            stats["repeated_certs"] += n
    stats["collisions"] = sum(1 for v in by_key.values() if len(v) > 1)
    # FST merged: ada key yang mencakup >=7 cert (pasangan FST 5+2 disatukan)
    top_freq = max(freq.values(), default=0)
    stats["fst_merged"] = int(top_freq >= 7)

    for stem in sorted(texts):
        row = gt.get(stem)
        gv = (row.get("tingkat") or "").strip() if row else ""
        if not gv or gv == "-":
            continue
        key, label, routed = _label(stem, texts[stem], tingkat_pipe, variant)
        entry = kb.peek(key) if key else None
        stats["total_eval"] += 1
        stats["exact_pipe"] += 1 if match_field(gv, label, "tingkat")["exact"] else 0
        if entry and entry.authoritative:
            stats["hits"] += 1
            if not routed:
                stats["saved_llm"] += 1
            if entry.tingkat != label:
                stats["disagree"] += 1
            if match_field(gv, entry.tingkat, "tingkat")["exact"]:
                stats["exact_kb"] += 1
            else:
                stats["wrong_hits"] += 1
    kbimpl.WARMUP_CONFIRMS = 3
    return stats


def shadow_3x(texts: dict[str, str], gt: dict[str, dict],
              tingkat_pipe: dict[str, str], variant: str) -> dict:
    """Shadow replay 3x confirm N=20 (alur router→KB→LLM) — no-regress check."""
    kbimpl.WARMUP_CONFIRMS = 3
    stems = sorted(texts)
    warm, eval_stems = set(stems[:20]), stems[20:]
    kb = TingkatKB()
    s = {"variant": variant, "hits": 0, "saved_llm": 0, "disagree": 0, "wrong": 0}
    for stem in stems:
        row = gt.get(stem)
        gv = (row.get("tingkat") or "").strip() if row else ""
        if not gv or gv == "-":
            continue
        key, label, routed = _label(stem, texts[stem], tingkat_pipe, variant)
        if key:
            kb.write(key, KBEntry(label or "Lainnya",
                                  "router_rule" if routed else "llm", stem))
        if stem in eval_stems:
            entry = kb.peek(key) if key else None
            if entry and entry.authoritative:
                s["hits"] += 1
                if not routed:
                    s["saved_llm"] += 1
                if entry.tingkat != label:
                    s["disagree"] += 1
                if not match_field(gv, entry.tingkat, "tingkat")["exact"]:
                    s["wrong"] += 1
    kbimpl.WARMUP_CONFIRMS = 3
    return s


def render_md(rows: list[dict], shadows: list[dict], noise: list[dict]) -> str:
    lines = [
        "# KB-003 — Normalisasi key v2 (plain/stem/alias/both)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"pipeline = run v9 + router CURRENT | 0 LLM runtime",
        "",
        "Masalah (KB-002): exact-match memecah 1 org logis (FST DEPT, 7 cert) "
        "menjadi 2 key → hit turun. Varian normalisasi key diukur terpisah; "
        "versi key `v1-{variant}` (snapshot tak tercampur).",
        "",
        "## Ceiling seeded (label = GT cert pertama utk key berulang freq≥2)",
        "",
        "| Varian | Keys | Repeat (cert) | Seeds | Hit | Saved LLM | Wrong | Disagree | Collision | FST merged | Exact KB / Pipe |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {r['keys']} | {r['repeated_keys']} ({r['repeated_certs']}) | "
            f"{r['seeds']} | {r['hits']} | {r['saved_llm']} | {r['wrong_hits']} | "
            f"{r['disagree']} | {r['collisions']} | {r['fst_merged']} | "
            f"{r['exact_kb']}/{r['total_eval']} ({r['exact_kb'] / r['total_eval'] * 100 if r['total_eval'] else 0:.1f}%) / "
            f"{r['exact_pipe']}/{r['total_eval']} ({r['exact_pipe'] / r['total_eval'] * 100 if r['total_eval'] else 0:.1f}%) |"
        )
    lines += [
        "",
        "## Shadow 3x confirm N=20 (no-regress check)",
        "",
        "| Varian | Hits | Saved LLM | Disagree | Wrong |",
        "|---|---|---|---|---|",
    ]
    for s in shadows:
        lines.append(f"| {s['variant']} | {s['hits']} | {s['saved_llm']} | {s['disagree']} | {s['wrong']} |")
    lines += ["", "## Safety — noise OCR 25% (wrong harus 0)", "",
              "| Varian | Hits | Wrong | Disagree |", "|---|---|---|---|"]
    for n in noise:
        lines.append(f"| {n['variant']} | {n['hits']} | {n['wrong']} | {n['disagree']} |")
    lines += [
        "",
        "## Interpretasi",
        "",
        "- `Collision` = key sama → tingkat pipeline beda (risiko over-merge "
        "stem/both). Gate: 0.",
        "- `FST merged` = 1 jika varian menyatukan pasangan FST jadi 1 key "
        "(stem/alias/both).",
        "- `Wrong`/`Disagree` = 0 semua varian = normalisasi key tidak menurunkan "
        "kualitas. Keputusan varian final menunggu data riil (alias = konservatif, "
        "stem = general tapi over-merge risk).",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    tingkat_pipe = load_pipeline_tingkat()
    print(f"Corpus: {len(texts)} certs | variants: {KEY_VARIANTS}")

    rows, shadows, noise = [], [], []
    for variant in KEY_VARIANTS:
        r = run_variant(texts, gt, tingkat_pipe, variant)
        rows.append(r)
        print(f"[{variant}] keys={r['keys']} repeat={r['repeated_keys']}({r['repeated_certs']}) "
              f"seeds={r['seeds']} hits={r['hits']} saved={r['saved_llm']} "
              f"wrong={r['wrong_hits']} coll={r['collisions']} fst={r['fst_merged']}")
    for variant in KEY_VARIANTS:
        s = shadow_3x(texts, gt, tingkat_pipe, variant)
        shadows.append(s)
        print(f"shadow[{variant}] hits={s['hits']} disagree={s['disagree']} wrong={s['wrong']}")
    rng = random.Random(SEED)
    noisy = {st: inject_noise(t, 0.25, rng) for st, t in texts.items()}
    for variant in KEY_VARIANTS:
        n = shadow_3x(noisy, gt, tingkat_pipe, variant)
        noise.append(n)
        print(f"noise[{variant}] wrong={n['wrong']}")

    summary = {"rows": rows, "shadows": shadows, "noise": noise,
               "seed": SEED, "gt": os.path.basename(GT_CSV), "matcher": "v2",
               "macro_avg": {"exact_acc": rows[0]["exact_pipe"] / rows[0]["total_eval"] if rows[0]["total_eval"] else 0.0}}
    with open(os.path.join(OUT_DIR, "summary_kb_norm.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(rows, shadows, noise))
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_kb_norm.json")


if __name__ == "__main__":
    main()
