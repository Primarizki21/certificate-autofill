"""EXP-V4-003: Direct Comparison Benchmark (v4.0 Baseline vs v4.1 vs v4.2 Candidate).

Evaluates:
- v4.0: Initial Combined v4 Staging Baseline
- v4.1: Minor Staging Refinement (Ordinals, Underscore Nomor, Activity Repairs, Dirkem Rule)
- v4.2: 3 Pillars & High-DPI Robustness Candidate (Structural Grammars, Roman Repairs, Calibrated Confidence)

Usage:
    GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_combined_v4_2
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import (
    apply_combined_v4,
    apply_combined_v4_1,
    apply_combined_v4_2,
)
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.ood_probe import load_gt, load_texts, EVAL_FIELDS
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"combined_v4_2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "combined_v4_2_report.md")


def run_pipeline(raw_text: str, version: str) -> dict[str, str]:
    extracted = extract_certificate_fields(raw_text)
    if version == "v4.0":
        extracted = apply_combined_v4(extracted, raw_text)
    elif version == "v4.1":
        extracted = apply_combined_v4_1(extracted, raw_text)
    elif version == "v4.2":
        extracted = apply_combined_v4_2(extracted, raw_text)

    mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
    return {k: v.value or "" for k, v in mapped.items()}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()
    stems = sorted(texts.keys())

    print("=" * 95)
    print("EXP-V4-003: v4.x BENCHMARK — v4.0 (BASELINE) VS v4.1 VS v4.2 (CANDIDATE)")
    print("=" * 95)

    stats = {}
    for ver_name, ver_key in [
        ("v4.0 (Baseline)", "v4.0"),
        ("v4.1 (Minor)", "v4.1"),
        ("v4.2 (Candidate)", "v4.2"),
    ]:
        per_field = {f: {"total": 0, "exact": 0, "fuzzy": 0} for f in EVAL_FIELDS}
        tot_cells = 0
        exact_cells = 0
        fuzzy_cells = 0

        for stem in stems:
            gt_row = gt.get(stem, {})
            text = texts[stem]
            pred = run_pipeline(text, ver_key)

            for field in EVAL_FIELDS:
                gt_val = gt_row.get(field, "")
                pred_val = pred.get(field, "")
                if not gt_val:
                    continue

                res = match_field(gt_val, pred_val, field)
                per_field[field]["total"] += 1
                tot_cells += 1
                if res["exact"]:
                    per_field[field]["exact"] += 1
                    exact_cells += 1
                if res["fuzzy"]:
                    per_field[field]["fuzzy"] += 1
                    fuzzy_cells += 1

        macro_exact = (exact_cells / tot_cells * 100) if tot_cells else 0.0
        macro_fuzzy = (fuzzy_cells / tot_cells * 100) if tot_cells else 0.0

        stats[ver_name] = {
            "macro_exact": macro_exact,
            "macro_fuzzy": macro_fuzzy,
            "exact_cells": exact_cells,
            "fuzzy_cells": fuzzy_cells,
            "tot_cells": tot_cells,
            "per_field": {
                f: {
                    "exact_pct": (per_field[f]["exact"] / per_field[f]["total"] * 100)
                    if per_field[f]["total"]
                    else 0.0,
                    "fuzzy_pct": (per_field[f]["fuzzy"] / per_field[f]["total"] * 100)
                    if per_field[f]["total"]
                    else 0.0,
                    "exact_count": per_field[f]["exact"],
                    "total_count": per_field[f]["total"],
                }
                for f in EVAL_FIELDS
            },
        }

    b_exact = stats["v4.0 (Baseline)"]["macro_exact"]
    v41_exact = stats["v4.1 (Minor)"]["macro_exact"]
    v42_exact = stats["v4.2 (Candidate)"]["macro_exact"]

    # Print summary table
    print(
        f"\n{'Field / Metric':<35} | {'v4.0 (Baseline)':<18} | {'v4.1 (Minor)':<18} | {'v4.2 (Candidate)':<18}"
    )
    print("-" * 98)
    print(
        f"{'MACRO Exact Match':<35} | {b_exact:>16.2f}% | {v41_exact:>16.2f}% | {v42_exact:>16.2f}%"
    )
    print(
        f"{'MACRO Fuzzy Match':<35} | {stats['v4.0 (Baseline)']['macro_fuzzy']:>16.2f}% | {stats['v4.1 (Minor)']['macro_fuzzy']:>16.2f}% | {stats['v4.2 (Candidate)']['macro_fuzzy']:>16.2f}%"
    )
    print("-" * 98)

    for f in EVAL_FIELDS:
        v40 = stats["v4.0 (Baseline)"]["per_field"][f]["exact_pct"]
        v41 = stats["v4.1 (Minor)"]["per_field"][f]["exact_pct"]
        v42 = stats["v4.2 (Candidate)"]["per_field"][f]["exact_pct"]
        print(f"{f:<35} | {v40:>16.1f}% | {v41:>16.1f}% | {v42:>16.1f}%")

    print("-" * 98)
    print(
        f"Total evaluated cells: {stats['v4.2 (Candidate)']['tot_cells']} across {len(stems)} certificates (0 LLM calls, 100% deterministic)"
    )

    # Save JSON summary
    with open(os.path.join(OUT_DIR, "benchmark_summary.json"), "w") as fp:
        json.dump(stats, fp, indent=2)

    # Generate Markdown report
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as fp:
        fp.write("# EXP-V4-003: v4.x Benchmark — v4.0 (Baseline) vs v4.1 vs v4.2 (Candidate)\n\n")
        fp.write(f"- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        fp.write(f"- **Ground Truth**: `{GT_CSV}`\n")
        fp.write(
            f"- **Dataset Size**: {len(stems)} certificates ({stats['v4.2 (Candidate)']['tot_cells']} evaluation cells)\n"
        )
        fp.write(f"- **v4.0 MACRO Exact**: **{b_exact:.2f}%**\n")
        fp.write(f"- **v4.1 MACRO Exact**: **{v41_exact:.2f}%**\n")
        fp.write(f"- **v4.2 MACRO Exact**: **{v42_exact:.2f}%** (**{v42_exact - b_exact:+.2f}pt vs v4.0**)\n\n")
        fp.write("## Progression Across v4.x Iterations\n\n")
        fp.write(
            "| Field / Metric | v4.0 (Baseline) | v4.1 (Minor) | v4.2 (Candidate) | Delta vs v4.0 |\n|---|:---:|:---:|:---:|:---:|\n"
        )
        fp.write(
            f"| **MACRO Exact** | {b_exact:.2f}% | {v41_exact:.2f}% | **{v42_exact:.2f}%** | **{v42_exact - b_exact:+.2f}pt** |\n"
        )
        fp.write(
            f"| **MACRO Fuzzy** | {stats['v4.0 (Baseline)']['macro_fuzzy']:.2f}% | {stats['v4.1 (Minor)']['macro_fuzzy']:.2f}% | **{stats['v4.2 (Candidate)']['macro_fuzzy']:.2f}%** | **{stats['v4.2 (Candidate)']['macro_fuzzy'] - stats['v4.0 (Baseline)']['macro_fuzzy']:+.2f}pt** |\n"
        )
        for f in EVAL_FIELDS:
            v40 = stats["v4.0 (Baseline)"]["per_field"][f]["exact_pct"]
            v41 = stats["v4.1 (Minor)"]["per_field"][f]["exact_pct"]
            v42 = stats["v4.2 (Candidate)"]["per_field"][f]["exact_pct"]
            fp.write(f"| `{f}` | {v40:.1f}% | {v41:.1f}% | **{v42:.1f}%** | **{v42 - v40:+.1f}pt** |\n")
        fp.write("\n## 3 Pillars Implemented in v4.2\n\n")
        fp.write(
            "1. **Pillar 1: Structural Semantic Anchors**: Indonesian & English formal certificate grammar patterns (`extract_activity_v8`).\n"
        )
        fp.write(
            "2. **Pillar 2: General OCR Noise Cleaning & Roman Repairs**: Universal Roman numeral month normalization (`normalize_nomor_v5`).\n"
        )
        fp.write(
            "3. **Pillar 3: Calibrated Confidence & Zero-Silent-Error Review Gate**: Review trigger when any field confidence is below 0.85.\n"
        )
        fp.write(
            "4. **High-DPI Region Crop Module**: `app/services/high_dpi_crop.py` provides 6.0x zoom region re-rendering for low-resolution scanned certificates.\n"
        )

    print(f"\nReport written to {OUT_MD}")
    print(f"Artifacts saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
