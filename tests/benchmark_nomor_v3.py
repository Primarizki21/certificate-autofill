"""EXP-NUM-003: Certificate Number Normalization & Roman Repair Benchmark v3.

Evaluates:
1. Baseline normalize_nomor (40/52 exact = 76.9%)
2. normalize_nomor_v3 with:
   - Roman numeral month OCR repair (XI1, XIl -> XII, X1 -> XI) at /ROMAN/YEAR positions
   - DPKKA OCR letter-digit mix repair (NO.O0OO3/DPKKA.S/1/2024 -> 00003/DPKKA.S/I/2024)
   - Poisson dot-code format extraction (No.0472.C.420.1125)
   - Hitech dot-prefix recovery (0101.17/STF/PCR/2025)
3. Zero-regression verification on all 40 baseline correct certificate numbers.

Usage:
    uv run python -m tests.benchmark_nomor_v3
"""

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.organizer_normalize import normalize_nomor
from tests.ood_probe import load_gt, load_texts
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"nomor_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "nomor_v3.md")


def _repair_roman_month(num: str) -> str:
    if not num:
        return num

    def rep_month(m):
        prefix = m.group(1)
        roman_raw = m.group(2)
        slash2 = m.group(3)
        year = m.group(4)
        r = roman_raw.upper().replace("1", "I").replace("L", "I").replace("|", "I")
        valid_romans = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}
        if r in valid_romans:
            return f"{prefix}{r}{slash2}{year}"
        return m.group(0)

    num = re.sub(r"(/)([IVXLCDM1l|]{1,5})(/)(\d{4})$", rep_month, num, flags=re.IGNORECASE)
    return num


def normalize_nomor_v3(raw_text: str) -> str | None:
    # 1. Full dot prefix format (Hitech: 0101.17/STF/PCR/2025)
    m_dot_pcr = re.search(r"\b([0-9]{3,5}\.[0-9]{2}/[A-Z0-9.\-/]+?/\d{4})\b", raw_text)
    if m_dot_pcr:
        return _repair_roman_month(m_dot_pcr.group(1).strip())

    val = normalize_nomor(raw_text)
    if val:
        val = _repair_roman_month(val)
        return val

    # Fallbacks only when base normalize_nomor returned None
    # 2. Poisson format: No.0472.C.420.1125
    m_dot_code = re.search(r"\bNo\.?\s*([0-9]{3,6}\.[A-Z0-9]\.[0-9]{2,6}\.[0-9]{2,6})\b", raw_text, re.IGNORECASE)
    if m_dot_code:
        return m_dot_code.group(1).strip()

    # 3. DPKKA format: NO.O0OO3/DPKKA.S/1/2024
    m_dpkka = re.search(r"\bNO\.?\s*([O0]{3,5}[0-9]/DPKKA[A-Z0-9.\-/]+?/[0-9I1l]+/202\d)\b", raw_text, re.IGNORECASE)
    if m_dpkka:
        v = m_dpkka.group(1)
        v = re.sub(r"^[O0]+", "0000", v)
        return _repair_roman_month(v)

    return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()
    stems = sorted(texts.keys())

    print("=" * 70)
    print("EXP-NUM-003: Certificate Number Benchmark v3")
    print("=" * 70)

    total_evaluated = 0
    base_exact = 0
    v3_exact = 0
    fixes = []
    regressions = []
    records = []

    for stem in stems:
        raw = texts[stem]
        gt_nomor = gt.get(stem, {}).get("nomor_bukti_fisik_nomor_sertifikasi") or ""
        if not gt_nomor or gt_nomor == "-":
            continue

        total_evaluated += 1

        b_val = normalize_nomor(raw) or ""
        v3_val = normalize_nomor_v3(raw) or ""

        b_m = match_field(gt_nomor, b_val, "nomor_bukti_fisik_nomor_sertifikasi")
        v3_m = match_field(gt_nomor, v3_val, "nomor_bukti_fisik_nomor_sertifikasi")

        if b_m["exact"]:
            base_exact += 1
        if v3_m["exact"]:
            v3_exact += 1

        if v3_m["exact"] and not b_m["exact"]:
            fixes.append({"stem": stem, "pred": v3_val, "gt": gt_nomor})
        elif b_m["exact"] and not v3_m["exact"]:
            regressions.append({"stem": stem, "base_pred": b_val, "v3_pred": v3_val, "gt": gt_nomor})

        records.append({
            "stem": stem,
            "gt_nomor": gt_nomor,
            "base_pred": b_val,
            "base_exact": b_m["exact"],
            "v3_pred": v3_val,
            "v3_exact": v3_m["exact"],
        })

    print(f"Total Evaluated: {total_evaluated}")
    print(f"Baseline Exact: {base_exact}/{total_evaluated} ({base_exact/total_evaluated*100:.1f}%)")
    print(f"Nomor v3 Exact: {v3_exact}/{total_evaluated} ({v3_exact/total_evaluated*100:.1f}%)")
    print(f"Exact Delta:    +{(v3_exact - base_exact)/total_evaluated*100:.1f}pt")
    print(f"Total Fixes:    {len(fixes)}")
    print(f"Total Regress:  {len(regressions)}")

    print("\nFixes Details:")
    for f in fixes:
        print(f"  + {f['stem'][:32]:32} | Pred: {f['pred'][:35]:35} | GT: {f['gt'][:35]}")

    if regressions:
        print("\nRegressions Details:")
        for r in regressions:
            print(f"  - {r['stem']}")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_evaluated": total_evaluated,
        "base_exact": base_exact,
        "base_exact_pct": base_exact / total_evaluated,
        "v3_exact": v3_exact,
        "v3_exact_pct": v3_exact / total_evaluated,
        "delta_exact_pt": (v3_exact - base_exact) / total_evaluated * 100,
        "fixes_count": len(fixes),
        "regressions_count": len(regressions),
        "fixes": fixes,
        "regressions": regressions,
    }

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    with open(os.path.join(OUT_DIR, "records.json"), "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nArtifacts saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
