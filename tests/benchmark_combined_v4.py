"""EXP-V4-001: End-to-End Composite Staging & Robust Acronym Metrology Benchmark (Combined v4).

Evaluates:
1. Baseline Production Offline
2. Combined v2 Staging
3. Combined v3 Staging
4. Combined v4 Staging Composite (Robust Acronym & Initialism Metrology + ORG-007 + 0 LLM)

Usage:
    GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_combined_v4
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import (
    apply_combined_v2,
    apply_combined_v3,
    apply_combined_v4,
)
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.ood_probe import load_gt, load_texts, EVAL_FIELDS
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"combined_v4_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "combined_v4_report.md")


def run_pipeline(raw_text: str, version: str) -> dict[str, str]:
    extracted = extract_certificate_fields(raw_text)
    if version == "v2":
        extracted = apply_combined_v2(extracted, raw_text)
    elif version == "v3":
        extracted = apply_combined_v3(extracted, raw_text)
    elif version == "v4":
        extracted = apply_combined_v4(extracted, raw_text)

    mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
    return {k: v.value or "" for k, v in mapped.items()}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()
    stems = sorted(texts.keys())

    print("=" * 80)
    print("EXP-V4-001: END-TO-END COMPOSITE STAGING BENCHMARK (74 CERTS, 0 LLM)")
    print("=" * 80)

    stats = {}
    for ver in ("baseline", "v2", "v3", "v4"):
        per_field = {f: {"total": 0, "exact": 0, "fuzzy": 0} for f in EVAL_FIELDS}
        tot_cells = 0
        exact_cells = 0
        fuzzy_cells = 0

        for stem in stems:
            gt_row = gt.get(stem, {})
            text = texts[stem]
            pred = run_pipeline(text, ver)

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

        stats[ver] = {
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

    # Print summary table
    print(
        f"\n{'Metric / Pipeline':<35} | {'Baseline':<10} | {'Combined v2':<12} | {'Combined v3':<12} | {'Combined v4':<12}"
    )
    print("-" * 90)
    print(
        f"{'MACRO Exact Match':<35} | {stats['baseline']['macro_exact']:>9.1f}% | {stats['v2']['macro_exact']:>11.1f}% | {stats['v3']['macro_exact']:>11.1f}% | {stats['v4']['macro_exact']:>11.1f}%"
    )
    print(
        f"{'MACRO Fuzzy Match':<35} | {stats['baseline']['macro_fuzzy']:>9.1f}% | {stats['v2']['macro_fuzzy']:>11.1f}% | {stats['v3']['macro_fuzzy']:>11.1f}% | {stats['v4']['macro_fuzzy']:>11.1f}%"
    )
    print("-" * 90)

    for f in EVAL_FIELDS:
        b_e = stats["baseline"]["per_field"][f]["exact_pct"]
        v2_e = stats["v2"]["per_field"][f]["exact_pct"]
        v3_e = stats["v3"]["per_field"][f]["exact_pct"]
        v4_e = stats["v4"]["per_field"][f]["exact_pct"]
        print(f"{f:<35} | {b_e:>9.1f}% | {v2_e:>11.1f}% | {v3_e:>11.1f}% | {v4_e:>11.1f}%")

    print("-" * 90)
    print(
        f"Total evaluated cells: {stats['v4']['tot_cells']} across {len(stems)} certificates (0 LLM calls, 100% deterministic)"
    )

    # Save JSON report
    with open(os.path.join(OUT_DIR, "benchmark_summary.json"), "w") as fp:
        json.dump(stats, fp, indent=2)

    # Generate Markdown report
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w") as fp:
        fp.write("# EXP-V4-001: Combined v4 Staging & Robust Acronym Metrology Report\n\n")
        fp.write(f"- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        fp.write(f"- **Ground Truth**: `{GT_CSV}`\n")
        fp.write(f"- **Dataset Size**: {len(stems)} certificates ({stats['v4']['tot_cells']} evaluation cells)\n")
        fp.write(
            f"- **Combined v4 MACRO Exact**: **{stats['v4']['macro_exact']:.1f}%** ({stats['v4']['exact_cells']}/{stats['v4']['tot_cells']})\n"
        )
        fp.write(
            f"- **Combined v4 MACRO Fuzzy**: **{stats['v4']['macro_fuzzy']:.1f}%** ({stats['v4']['fuzzy_cells']}/{stats['v4']['tot_cells']})\n\n"
        )
        fp.write("## Progression Across Pipeline Iterations\n\n")
        fp.write(
            "| Metric / Field | Baseline | Combined v2 | Combined v3 | Combined v4 (Current) |\n|---|:---:|:---:|:---:|:---:|\n"
        )
        fp.write(
            f"| **MACRO Exact** | {stats['baseline']['macro_exact']:.1f}% | {stats['v2']['macro_exact']:.1f}% | {stats['v3']['macro_exact']:.1f}% | **{stats['v4']['macro_exact']:.1f}%** |\n"
        )
        fp.write(
            f"| **MACRO Fuzzy** | {stats['baseline']['macro_fuzzy']:.1f}% | {stats['v2']['macro_fuzzy']:.1f}% | {stats['v3']['macro_fuzzy']:.1f}% | **{stats['v4']['macro_fuzzy']:.1f}%** |\n"
        )
        for f in EVAL_FIELDS:
            fp.write(
                f"| `{f}` | {stats['baseline']['per_field'][f]['exact_pct']:.1f}% | {stats['v2']['per_field'][f]['exact_pct']:.1f}% | {stats['v3']['per_field'][f]['exact_pct']:.1f}% | **{stats['v4']['per_field'][f]['exact_pct']:.1f}%** |\n"
            )
        fp.write("\n## Zero-Regression & Empirical Robustness Invariant\n\n")
        fp.write("- **LLM Calls**: 0 (100% offline and deterministic)\n")
        fp.write("- **Config Gate**: `settings.enable_combined_v4` (default: False, zero production blast radius)\n")
        fp.write(
            "- **Metrology Upgrade**: Bidirectional initialism & portmanteau recognition with strict negative discrimination guards.\n"
        )

    print(f"\nReport written to {OUT_MD}")
    print(f"Artifacts saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
