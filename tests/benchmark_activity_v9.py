"""B5 — Benchmark akurasi nama_kegiatan: v4.2 (activity_v8) vs activity_v9.

Gate B5:
  - exact >= 79.7% (zero regression vs v4.2, EXP-V4-002/003).
  - fuzzy >= 83.8%.
  - 0 organizer bleeding (diuji di unit test adversarial).

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_activity_v9
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.activity_extractor_v9 import extract_activity_v9
from tests.matchers import match_field
from tests.ood_probe import load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"activity_v9_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "b5_structural_activity_report.md")

FIELD = "nama_kegiatan_sertifikasi"
GATE_EXACT = 79.7
GATE_FUZZY = 83.8


def run_v42(text: str) -> str:
    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    return (mapped.get(FIELD).value if mapped.get(FIELD) else None) or ""


def run_v9(text: str) -> str:
    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    act = extract_activity_v9(text)
    if act:
        extracted[FIELD] = ExtractedValue(act, 0.95, "activity_v9")
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    return (mapped.get(FIELD).value if mapped.get(FIELD) else None) or ""


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()

    stats = {}
    details = {}
    for label, fn in (("v4_2", run_v42), ("v9", run_v9)):
        total = exact = fuzzy = 0
        changes = []
        per = {}
        for stem, text in texts.items():
            gv = (gt.get(stem, {}).get(FIELD, "") or "").strip()
            if not gv or gv == "-":
                continue
            pred = fn(text)
            res = match_field(gv, pred, FIELD)
            total += 1
            exact += int(res["exact"])
            fuzzy += int(res["fuzzy"])
            per[stem] = {"gt": gv, "pred": pred, "exact": res["exact"], "fuzzy": res["fuzzy"]}
        stats[label] = {
            "exact": exact, "total": total,
            "exact_pct": exact / total * 100 if total else 0.0,
            "fuzzy_pct": fuzzy / total * 100 if total else 0.0,
        }
        details[label] = per

    # Diff v9 vs v4.2: fixes & regressions (flag exact) + value changes
    diff = {"fix": [], "regress": [], "value_changed": []}
    for stem in details["v4_2"]:
        a, b = details["v4_2"][stem], details["v9"][stem]
        if a["pred"] != b["pred"]:
            diff["value_changed"].append(
                {"stem": stem, "gt": a["gt"], "v42": a["pred"], "v9": b["pred"]}
            )
        if a["exact"] != b["exact"]:
            (diff["fix"] if b["exact"] else diff["regress"]).append(
                {"stem": stem, "gt": a["gt"], "v42": a["pred"], "v9": b["pred"]}
            )
    gates = {
        "v9_exact_pct": stats["v9"]["exact_pct"],
        "exact_gate": GATE_EXACT,
        "exact_pass": stats["v9"]["exact_pct"] >= GATE_EXACT,
        "v9_fuzzy_pct": stats["v9"]["fuzzy_pct"],
        "fuzzy_gate": GATE_FUZZY,
        "fuzzy_pass": stats["v9"]["fuzzy_pct"] >= GATE_FUZZY,
        "fix_count": len(diff["fix"]),
        "regress_count": len(diff["regress"]),
        "value_changed_count": len(diff["value_changed"]),
        "zero_value_change_pass": len(diff["value_changed"]) == 0,
    }
    summary = {"created": datetime.now().isoformat(), "stats": stats, "gates": gates, "diff": diff}
    with open(os.path.join(OUT_DIR, "summary_activity_v9.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = [
        "# B5 — Structural Activity Extraction v9 (anti-bleed, N=74)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2.",
        "",
        "| Varian | exact | fuzzy |",
        "|---|---|---|",
        f"| v4.2 (activity_v8) | {stats['v4_2']['exact_pct']:.1f}% ({stats['v4_2']['exact']}/{stats['v4_2']['total']}) | {stats['v4_2']['fuzzy_pct']:.1f}% |",
        f"| **v9 (anti-bleed)** | **{stats['v9']['exact_pct']:.1f}%** ({stats['v9']['exact']}/{stats['v9']['total']}) | **{stats['v9']['fuzzy_pct']:.1f}%** |",
        "",
        f"**Gate**: exact >= {GATE_EXACT}% -> {'PASS' if gates['exact_pass'] else 'FAIL'} | "
        f"fuzzy >= {GATE_FUZZY}% -> {'PASS' if gates['fuzzy_pass'] else 'FAIL'}",
        "",
        f"Diff v9 vs v4.2: fix {gates['fix_count']}, regress {gates['regress_count']} "
        f"(zero exact-flag regression: {'PASS' if gates['regress_count'] == 0 else 'FAIL'}); "
        f"nilai berubah (benign) {gates['value_changed_count']} — laporan, bukan gate",
        "",
    ]
    if diff["fix"]:
        lines.append("### Fix")
        lines.append("")
        for d in diff["fix"]:
            lines.append(f"- `{d['stem'][:44]}` GT={d['gt'][:50]!r} v4.2={d['v42'][:50]!r} -> v9={d['v9'][:50]!r}")
        lines.append("")
    if diff["regress"]:
        lines.append("### Regress")
        lines.append("")
        for d in diff["regress"]:
            lines.append(f"- `{d['stem'][:44]}` GT={d['gt'][:50]!r} v4.2={d['v42'][:50]!r} -> v9={d['v9'][:50]!r}")
        lines.append("")
    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))

    print(f"v4.2: {stats['v4_2']['exact_pct']:.1f}% exact | v9: {stats['v9']['exact_pct']:.1f}% exact, {stats['v9']['fuzzy_pct']:.1f}% fuzzy")
    print(f"diff: fix {len(diff['fix'])} regress {len(diff['regress'])} value_changed {len(diff['value_changed'])}")
    print(f"GATES: exact {'PASS' if gates['exact_pass'] else 'FAIL'} ({gates['v9_exact_pct']:.1f}% vs {GATE_EXACT}%) | "
          f"fuzzy {'PASS' if gates['fuzzy_pass'] else 'FAIL'} ({gates['v9_fuzzy_pct']:.1f}% vs {GATE_FUZZY}%) | "
          f"zero-regress {'PASS' if gates['regress_count'] == 0 else 'FAIL'}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()