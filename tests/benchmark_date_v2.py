"""EXP-DATE-001: Date Extraction Benchmark v2 (Multi-Day Intervals, English Ordinals, OCR Year Normalization).

Evaluates:
1. Baseline extract_dates (45/55 exact = 81.8%)
2. extract_dates_v2 with:
   - OCR year normalization (2o24/2O24 -> 2024)
   - English ordinal stripping (23th, 7th-9th, 11th, 1lth)
   - Month-first multi-day intervals (November 11-23, 2024)
   - Day-first multi-day intervals (21-23 Agustus 2024, 7-8 Februari Tahun 2026)
   - Explicit single event date prioritization (on Saturday, September 23 2023, on 30 April 2026, on 17 November 2023)
3. Zero-regression verification on all 45 baseline correct dates.

Usage:
    uv run python -m tests.benchmark_date_v2
"""

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import (
    extract_dates,
    normalize_text,
    to_ddmmyyyy,
    token_to_ddmmyyyy,
    normalize_month,
    scan_date_tokens,
    choose_best_date_pair,
)
from tests.ood_probe import load_gt, load_texts
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"date_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "date_v2.md")


def normalize_for_date_v2(text: str) -> str:
    # 1. OCR year typos directly on raw string
    t = re.sub(r"2[oO0]2([0-9])", r"202\1", text)
    t = re.sub(r"2[oO0]1([0-9])", r"201\1", t)
    # 2. Dashes
    u = t.upper().replace("—", "-").replace("–", "-")
    # 3. Ordinals
    u = re.sub(r"\b1[lL](?:ST|ND|RD|TH)", "11", u)
    u = re.sub(r"(\d{1,2})(?:ST|ND|RD|TH)", r"\1", u)
    u = re.sub(r"\b(FROM|ON|IN|HELD|UNTIL|AT|DILAKSANAKAN|PADA|TANGGAL)(?=[A-Z])", r"\1 ", u)
    # 4. Spacing
    u = re.sub(r"(?<=[A-Z])(?=\d)", " ", u)
    u = re.sub(r"(?<=\d)(?=[A-Z])", " ", u)
    u = re.sub(r"(?<=,)(?=\d{4})", " ", u)
    u = re.sub(r"\s+", " ", u)
    return u


def extract_dates_v2(text: str) -> tuple[str | None, str | None, float]:
    upper = normalize_for_date_v2(text)

    # 1) Numeric interval: 24/08/2024 - 22/09/2024
    numeric_interval = re.search(
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*(?:-|S/D|SD|SAMPAI|S\.D\.|TO)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        upper,
        flags=re.IGNORECASE,
    )
    if numeric_interval:
        d1, m1, y1, d2, m2, y2 = numeric_interval.groups()
        return f"{int(d1):02d}/{int(m1):02d}/{y1}", f"{int(d2):02d}/{int(m2):02d}/{y2}", 0.95

    # 2) Full date interval: 2 September 2023 - 17 September 2023
    full_interval = re.search(
        r"(\d{1,2})\s+([A-Z0-9]{3,20})\s+(\d{4})\s*(?:-|S/D|SD|SAMPAI|S\.D\.|TO)\s*(\d{1,2})\s+([A-Z0-9]{3,20})\s+(\d{4})",
        upper,
        flags=re.IGNORECASE,
    )
    if full_interval:
        d1, m1, y1, d2, m2, y2 = full_interval.groups()
        s = to_ddmmyyyy(d1, m1, y1)
        e = to_ddmmyyyy(d2, m2, y2)
        if s and e:
            return s, e, 0.95

    # 3) English month-first interval: September 21 to December 7, 2024
    english_interval = re.search(
        r"([A-Z]{3,20})\s+(\d{1,2})(?:,\s*(\d{4}))?\s*(?:-|TO|UNTIL|S/D|SD|SAMPAI)\s*([A-Z]{3,20})\s+(\d{1,2})(?:,?\s*(\d{4}))",
        upper,
        flags=re.IGNORECASE,
    )
    if english_interval:
        m1, d1, y1, m2, d2, y2 = english_interval.groups()
        year = y1 or y2
        start_value = to_ddmmyyyy(d1, m1, year)
        end_value = to_ddmmyyyy(d2, m2, y2 or year)
        if start_value and end_value:
            return start_value, end_value, 0.95

    # 4) Month-first same-month interval: November 11-23, 2024
    month_first_span = re.search(
        r"([A-Z]{3,20})\s+(\d{1,2})\s*(?:-|TO|S/D|SD|SAMPAI)\s*(\d{1,2})(?:,\s*|\s+)(\d{4})",
        upper,
        flags=re.IGNORECASE,
    )
    if month_first_span:
        month, d1, d2, year = month_first_span.groups()
        s = to_ddmmyyyy(d1, month, year)
        e = to_ddmmyyyy(d2, month, year)
        if s and e:
            return s, e, 0.95

    # 5) Day-first same-month interval: 21-23 Agustus 2024 / 7-8 Februari Tahun 2026 / 7-9 July 2026
    same_month = re.search(
        r"(\d{1,2})\s*(?:-|S/D|SD|SAMPAI|S\.D\.|TO)\s*(\d{1,2})\s+([A-Z0-9]{3,20})\s+(?:TAHUN\s+)?(\d{4})",
        upper,
        flags=re.IGNORECASE,
    )
    if same_month:
        d1, d2, month, year = same_month.groups()
        year = re.sub(r"\D", "", year)
        start_value = to_ddmmyyyy(d1, month, year)
        end_value = to_ddmmyyyy(d2, month, year)
        if start_value and end_value:
            return start_value, end_value, 0.95

    # 6) Explicit single event date: "on Saturday, September 23 2023" / "on 30 April 2026" / "on 17 November 2023"
    on_event = re.search(
        r"\b(?:ON|HELD ON|HELD AT|PADA TANGGAL|PADA|DILAKSANAKAN PADA)\s+(?:[A-Z]+\s*,\s*)?([A-Z]{3,20})\s+(\d{1,2})(?:,\s*|\s+)(\d{4})\b",
        upper,
    )
    if on_event:
        mo, d, y = on_event.groups()
        v = to_ddmmyyyy(d, mo, y)
        if v:
            return v, v, 0.92

    on_event2 = re.search(
        r"\b(?:ON|HELD ON|HELD AT|PADA TANGGAL|PADA|DILAKSANAKAN PADA)\s+(?:[A-Z]+\s*,\s*)?(\d{1,2})\s+([A-Z]{3,20})\s+(\d{4})\b",
        upper,
    )
    if on_event2:
        d, mo, y = on_event2.groups()
        v = to_ddmmyyyy(d, mo, y)
        if v:
            return v, v, 0.92

    # 7) Single numeric
    numeric_single = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", upper)
    if numeric_single:
        d, m, y = numeric_single.groups()
        value = f"{int(d):02d}/{int(m):02d}/{y}"
        return value, value, 0.80

    # 8) Date token scan
    date_tokens = scan_date_tokens(upper)
    if len(date_tokens) >= 2:
        best_pair = choose_best_date_pair(upper, date_tokens)
        if best_pair:
            first, second = best_pair
            year = first["year"] or second["year"]
            if year:
                start_value = token_to_ddmmyyyy(first, year)
                end_value = token_to_ddmmyyyy(second, second["year"] or year)
                if start_value and end_value:
                    return start_value, end_value, 0.94

    for token in date_tokens:
        if token["year"]:
            value = token_to_ddmmyyyy(token, token["year"])
            if value:
                return value, value, 0.80

    return None, None, 0.0


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()
    stems = sorted(texts.keys())

    print("=" * 70)
    print("EXP-DATE-001: Date Extraction Benchmark v2")
    print("=" * 70)

    total_evaluated = 0
    base_exact = 0
    v2_exact = 0
    fixes = []
    regressions = []
    records = []

    for stem in stems:
        raw = texts[stem]
        gt_row = gt.get(stem, {})
        gt_start = gt_row.get("waktu_mulai_pelaksanaan") or ""
        gt_end = gt_row.get("waktu_selesai_pelaksanaan") or ""

        if not gt_start or gt_start == "-" or not gt_end or gt_end == "-":
            continue

        total_evaluated += 1

        b_s, b_e, _ = extract_dates(raw)
        b_s = b_s or ""
        b_e = b_e or ""

        v2_s, v2_e, _ = extract_dates_v2(raw)
        v2_s = v2_s or ""
        v2_e = v2_e or ""

        b_s_ok = match_field(gt_start, b_s, "waktu_mulai_pelaksanaan")["exact"]
        b_e_ok = match_field(gt_end, b_e, "waktu_selesai_pelaksanaan")["exact"]
        b_ok = b_s_ok and b_e_ok

        v2_s_ok = match_field(gt_start, v2_s, "waktu_mulai_pelaksanaan")["exact"]
        v2_e_ok = match_field(gt_end, v2_e, "waktu_selesai_pelaksanaan")["exact"]
        v2_ok = v2_s_ok and v2_e_ok

        if b_ok:
            base_exact += 1
        if v2_ok:
            v2_exact += 1

        if v2_ok and not b_ok:
            fixes.append({"stem": stem, "pred_start": v2_s, "pred_end": v2_e, "gt_start": gt_start, "gt_end": gt_end})
        elif b_ok and not v2_ok:
            regressions.append({"stem": stem, "b_start": b_s, "b_end": b_e, "v2_start": v2_s, "v2_end": v2_e, "gt_start": gt_start, "gt_end": gt_end})

        records.append({
            "stem": stem,
            "gt_start": gt_start,
            "gt_end": gt_end,
            "base_start": b_s,
            "base_end": b_e,
            "base_ok": b_ok,
            "v2_start": v2_s,
            "v2_end": v2_e,
            "v2_ok": v2_ok,
        })

    print(f"Total Non-Empty GT Dates: {total_evaluated}")
    print(f"Baseline Exact: {base_exact}/{total_evaluated} ({base_exact/total_evaluated*100:.1f}%)")
    print(f"Date v2 Exact:  {v2_exact}/{total_evaluated} ({v2_exact/total_evaluated*100:.1f}%)")
    print(f"Accuracy Delta: +{(v2_exact - base_exact)/total_evaluated*100:.1f}pt")
    print(f"Total Fixes:    {len(fixes)}")
    print(f"Total Regress:  {len(regressions)}")

    print("\nFixes Details:")
    for f in fixes:
        print(f"  + {f['stem'][:35]:35} | Pred: {f['pred_start']} - {f['pred_end']} | GT: {f['gt_start']} - {f['gt_end']}")

    if regressions:
        print("\nRegressions Details:")
        for r in regressions:
            print(f"  - {r['stem']}")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_evaluated": total_evaluated,
        "base_exact": base_exact,
        "base_accuracy": base_exact / total_evaluated,
        "v2_exact": v2_exact,
        "v2_accuracy": v2_exact / total_evaluated,
        "delta_pt": (v2_exact - base_exact) / total_evaluated * 100,
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
