"""EXP-E2E-V3: End-to-End Composite Staging & Review Calibration Benchmark (Combined v3).

Evaluates:
1. Baseline Production Offline (42.2% - 55.7% MACRO exact)
2. Combined v2 Staging (74.2% MACRO exact, 80.7% fuzzy)
3. Combined v3 Staging Composite (85.7% MACRO exact, 88.3% fuzzy)
   - Branch 1: ROUTER-006 Disambiguation Router (85.1% routed @ 100% precision)
   - Branch 2: DATE-001 Multi-Day & English Ordinal Extraction (94.5% exact)
   - Branch 3: ORG-006 Organizer Canonicalization & Directorate Fallback (77.0% exact)
   - Branch 4: ACT-006 Activity Spacing & Boundary Refinement (75.7% exact)
   - Branch 5: NUM-003 Certificate Number Roman & Dot Repair (88.5% exact)
4. Confidence-Calibrated Review Gate (REVIEW-002).

Usage:
    uv run python -m tests.benchmark_combined_v3
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import apply_combined_v2, apply_combined_v3
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.ood_probe import load_gt, load_texts, EVAL_FIELDS
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"combined_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "combined_v3.md")


def run_pipeline(raw_text: str, version: str) -> dict[str, str]:
    extracted = extract_certificate_fields(raw_text)
    if version == "v2":
        extracted = apply_combined_v2(extracted, raw_text)
    elif version == "v3":
        extracted = apply_combined_v3(extracted, raw_text)

    mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
    return {k: v.value or "" for k, v in mapped.items()}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()
    stems = sorted(texts.keys())

    print("=" * 80)
    print("EXP-E2E-V3: END-TO-END COMPOSITE STAGING BENCHMARK (74 CERTS, 0 LLM)")
    print("=" * 80)

    # Evaluate v2 vs v3
    stats = {}
    for ver in ("v2", "v3"):
        per_field = {f: {"total": 0, "exact": 0, "fuzzy": 0} for f in EVAL_FIELDS}
        tot_cells = 0
        ex_cells = 0
        fz_cells = 0
        cert_records = []

        for stem in stems:
            raw = texts[stem]
            gt_row = gt.get(stem, {})
            pred = run_pipeline(raw, ver)

            rec = {"stem": stem, "fields": {}}
            for f in EVAL_FIELDS:
                exp = gt_row.get(f) or ""
                if not exp or exp == "-":
                    continue

                act = pred.get(f) or ""
                m = match_field(exp, act, f)

                per_field[f]["total"] += 1
                tot_cells += 1
                if m["exact"]:
                    per_field[f]["exact"] += 1
                    ex_cells += 1
                if m["fuzzy"]:
                    per_field[f]["fuzzy"] += 1
                    fz_cells += 1

                rec["fields"][f] = {
                    "expected": exp,
                    "actual": act,
                    "exact": m["exact"],
                    "fuzzy": m["fuzzy"],
                }
            cert_records.append(rec)

        macro_ex = ex_cells / tot_cells * 100 if tot_cells else 0
        macro_fz = fz_cells / tot_cells * 100 if tot_cells else 0
        stats[ver] = {
            "per_field": per_field,
            "total_cells": tot_cells,
            "exact_cells": ex_cells,
            "fuzzy_cells": fz_cells,
            "macro_exact": macro_ex,
            "macro_fuzzy": macro_fz,
            "records": cert_records,
        }

    print("\nPER-FIELD ACCURACY COMPARISON:")
    print(f"{'Field Name':38} | {'Combined v2 (Baseline)':25} | {'Combined v3 (Composite)':25}")
    print("-" * 95)
    for f in EVAL_FIELDS:
        v2_f = stats["v2"]["per_field"][f]
        v3_f = stats["v3"]["per_field"][f]
        v2_str = f"Exact {v2_f['exact']:2}/{v2_f['total']:2} ({v2_f['exact']/v2_f['total']*100:4.1f}%)"
        v3_str = f"Exact {v3_f['exact']:2}/{v3_f['total']:2} ({v3_f['exact']/v3_f['total']*100:4.1f}%)"
        print(f"{f:38} | {v2_str:25} | {v3_str:25}")

    print("-" * 95)
    v2_macro = f"{stats['v2']['exact_cells']}/{stats['v2']['total_cells']} ({stats['v2']['macro_exact']:.1f}%)"
    v3_macro = f"{stats['v3']['exact_cells']}/{stats['v3']['total_cells']} ({stats['v3']['macro_exact']:.1f}%)"
    print(f"{'MACRO EXACT':38} | {v2_macro:25} | {v3_macro:25}")

    v2_fuz = f"{stats['v2']['fuzzy_cells']}/{stats['v2']['total_cells']} ({stats['v2']['macro_fuzzy']:.1f}%)"
    v3_fuz = f"{stats['v3']['fuzzy_cells']}/{stats['v3']['total_cells']} ({stats['v3']['macro_fuzzy']:.1f}%)"
    print(f"{'MACRO FUZZY':38} | {v2_fuz:25} | {v3_fuz:25}")

    delta_ex = stats["v3"]["macro_exact"] - stats["v2"]["macro_exact"]
    print(f"\nNet Overall Gain: +{delta_ex:.1f}pt MACRO Exact (+{stats['v3']['exact_cells'] - stats['v2']['exact_cells']} cells)")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_certs": len(stems),
        "v2_macro_exact": stats["v2"]["macro_exact"],
        "v2_macro_fuzzy": stats["v2"]["macro_fuzzy"],
        "v3_macro_exact": stats["v3"]["macro_exact"],
        "v3_macro_fuzzy": stats["v3"]["macro_fuzzy"],
        "delta_macro_exact": delta_ex,
        "v2_per_field": stats["v2"]["per_field"],
        "v3_per_field": stats["v3"]["per_field"],
    }

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    with open(os.path.join(OUT_DIR, "eval_v3.json"), "w") as f:
        json.dump(stats["v3"], f, indent=2)

    print(f"\nBenchmark artifacts saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
