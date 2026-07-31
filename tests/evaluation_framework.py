import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

import openpyxl

from tests.date_normalizer import normalize_date
from tests.matchers import match_field

EVAL_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi",
]


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")


def load_csv(csv_path: str) -> list[dict]:
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({_normalize_key(k): v for k, v in row.items()})
    return rows


def resolve_pdf_path(row: dict, base_dir: str) -> str | None:
    folder = row.get("folder", "").strip()
    filename = row.get("nama_file", "").strip()
    if not folder or not filename:
        return None
    path = os.path.join(base_dir, folder, filename)
    if os.path.exists(path):
        return path
    return None


def read_pdf_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def evaluate_row(
    mapped: dict, expected_row: dict
) -> dict[str, dict]:
    results = {}
    for field in EVAL_FIELDS:
        expected = expected_row.get(field, "").strip()
        if not expected or expected == "-":
            continue
        extracted_val = mapped.get(field)
        actual = extracted_val.value if extracted_val else None
        results[field] = {
            "expected": expected,
            "actual": actual,
            "confidence": extracted_val.confidence if extracted_val else 0.0,
            **match_field(expected, actual, field),
        }
    return results


def aggregate_results(all_results: list[dict]) -> dict:
    total = defaultdict(int)
    exact_ok = defaultdict(int)
    fuzzy_ok = defaultdict(int)
    confidences = defaultdict(list)
    wers = defaultdict(list)
    cers = defaultdict(list)

    for row_results in all_results:
        for field, result in row_results.items():
            if field.startswith("_"):
                continue
            total[field] += 1
            if result["exact"]:
                exact_ok[field] += 1
            if result["fuzzy"]:
                fuzzy_ok[field] += 1
            confidences[field].append(result["confidence"])
            wers[field].append(result["wer"])
            cers[field].append(result["cer"])

    summary = {}
    all_fields = sorted(set(list(total.keys()) + EVAL_FIELDS))
    for field in all_fields:
        n = total[field]
        summary[field] = {
            "total": n,
            "exact": exact_ok[field],
            "fuzzy": fuzzy_ok[field],
            "exact_acc": round(exact_ok[field] / n, 4) if n else 0,
            "fuzzy_acc": round(fuzzy_ok[field] / n, 4) if n else 0,
            "avg_confidence": round(sum(confidences[field]) / len(confidences[field]), 4) if confidences[field] else 0,
            "avg_wer": round(sum(wers[field]) / len(wers[field]), 4) if wers[field] else 0,
            "avg_cer": round(sum(cers[field]) / len(cers[field]), 4) if cers[field] else 0,
        }

    overall_exact = sum(exact_ok.values())
    overall_fuzzy = sum(fuzzy_ok.values())
    overall_total = sum(total.values())
    overall_wer = sum(sum(w) for w in wers.values()) / sum(len(w) for w in wers.values()) if wers else 0
    overall_cer = sum(sum(c) for c in cers.values()) / sum(len(c) for c in cers.values()) if cers else 0
    summary["macro_avg"] = {
        "total": overall_total,
        "exact": overall_exact,
        "fuzzy": overall_fuzzy,
        "exact_acc": round(overall_exact / overall_total, 4) if overall_total else 0,
        "fuzzy_acc": round(overall_fuzzy / overall_total, 4) if overall_total else 0,
        "avg_wer": round(overall_wer, 4),
        "avg_cer": round(overall_cer, 4),
    }

    return summary


def print_report(summary: dict):
    print()
    header = f"{'Field':38s} {'Total':>6s} {'Exact':>8s} {'Fuzzy':>8s} {'E%':>6s} {'F%':>6s} {'AvgWER':>7s} {'AvgCER':>7s} {'AvgConf':>7s}"
    print(header)
    print("-" * len(header))
    for field, s in summary.items():
        if field == "macro_avg" or field.startswith("_"):
            continue
        print(
            f"{field:38s} {s['total']:>6d} {s['exact']:>8d} {s['fuzzy']:>8d} "
            f"{s['exact_acc']*100:>5.1f}% {s['fuzzy_acc']*100:>5.1f}% "
            f"{s['avg_wer']:>6.3f} {s['avg_cer']:>6.3f} {s['avg_confidence']:>6.2f}"
        )
    ma = summary["macro_avg"]
    print("-" * len(header))
    print(
        f"{'MACRO AVERAGE':38s} {ma['total']:>6d} {ma['exact']:>8d} {ma['fuzzy']:>8d} "
        f"{ma['exact_acc']*100:>5.1f}% {ma['fuzzy_acc']*100:>5.1f}% "
        f"{ma['avg_wer']:>6.3f} {ma['avg_cer']:>6.3f}"
    )
    print()


# ---------------------------------------------------------------------------
# Standardized benchmark output helpers
# ---------------------------------------------------------------------------

def save_mismatch_report(
    all_results: list[dict],
    output_dir: str,
    source: str = "",
):
    """Generate mismatches.csv/.xlsx and extracted_fields.csv/.xlsx from eval results.

    Each result dict should have per-field eval dicts (keyed by EVAL_FIELDS)
    and optionally a _meta dict with 'filename'.
    """
    os.makedirs(output_dir, exist_ok=True)

    mismatches_path = os.path.join(output_dir, "mismatches.csv")
    extracted_path = os.path.join(output_dir, "extracted_fields.csv")

    with open(mismatches_path, "w", newline="") as mf, \
         open(extracted_path, "w", newline="") as ef:
        m_writer = csv.writer(mf)
        e_writer = csv.writer(ef)
        m_writer.writerow(["filename", "field", "expected", "actual", "confidence", "error_type"])
        e_writer.writerow(["filename", "field", "value", "confidence", "source", "exact_match", "wer", "cer"])

        for result in all_results:
            meta = result.get("_meta", {})
            fname = meta.get("filename", "")
            for field in EVAL_FIELDS:
                r = result.get(field, {})
                if not r:
                    continue
                exp = r.get("expected", "")
                act = r.get("actual")
                conf = r.get("confidence", 0)

                e_writer.writerow([
                    fname, field, act or "", f"{conf:.2f}",
                    source, r.get("exact", False),
                    f"{r.get('wer', 1.0):.3f}", f"{r.get('cer', 1.0):.3f}",
                ])

                if r.get("exact"):
                    continue
                if not exp or exp == "-":
                    continue
                error_type = "null" if act is None else "mismatch"
                m_writer.writerow([fname, field, exp, act or "", f"{conf:.2f}", error_type])

    _csv_to_xlsx(mismatches_path)
    _csv_to_xlsx(extracted_path)


def _csv_to_xlsx(csv_path: str):
    xlsx_path = csv_path.replace(".csv", ".xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = os.path.basename(csv_path).replace(".csv", "")
    with open(csv_path) as f:
        for row in csv.reader(f):
            ws.append(row)
    wb.save(xlsx_path)


def save_summary_json(summary: dict, output_dir: str):
    """Save summary as canonical summary.json."""
    path = os.path.join(output_dir, "summary.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)


def save_report_md(
    summary: dict,
    output_dir: str,
    title: str = "Benchmark Summary",
    all_results: list[dict] | None = None,
    extra_lines: list[str] | None = None,
):
    """Generate standardized report.md with field accuracy table + worst files."""
    lines = [f"# {title}\n"]
    lines.append(f"**Date:** {datetime.now().isoformat()}\n")

    t = summary.get("_timing", {})
    if t:
        lines.append(f"**Total time:** {t.get('total_seconds', '?')}s "
                     f"({t.get('avg_per_file', '?')}s avg/file)\n")

    if extra_lines:
        lines.extend(extra_lines)

    lines.append("## Field Accuracy\n")
    lines.append("| Field | Total | Exact% | Fuzzy% | AvgWER | AvgCER | Avg Conf |")
    lines.append("|-------|-------|--------|--------|--------|--------|----------|")
    for field, s in summary.items():
        if field.startswith("_") or field == "macro_avg":
            continue
        lines.append(
            f"| {field} | {s['total']} | {s['exact_acc']*100:.1f}% | "
            f"{s['fuzzy_acc']*100:.1f}% | {s['avg_wer']:.3f} | {s['avg_cer']:.3f} | "
            f"{s.get('avg_confidence', 0):.2f} |"
        )
    ma = summary.get("macro_avg", {})
    lines.append(
        f"| **MACRO** | {ma.get('total',0)} | {ma.get('exact_acc',0)*100:.1f}% | "
        f"{ma.get('fuzzy_acc',0)*100:.1f}% | {ma.get('avg_wer',0):.3f} | "
        f"{ma.get('avg_cer',0):.3f} | — |"
    )

    if all_results:
        lines.append("\n## Worst 10 Files (fewest exact matches)\n")
        scored = []
        for r in all_results:
            meta = r.get("_meta", {})
            exact_count = sum(1 for k, v in r.items() if not k.startswith("_") and v.get("exact"))
            total_fields = sum(1 for k in r if not k.startswith("_"))
            scored.append((meta.get("filename", "?"), exact_count, total_fields,
                           meta.get("parser_engine", ""), meta.get("seconds", 0)))
        scored.sort(key=lambda x: (x[1], x[0]))
        lines.append("| Filename | Exact | Total | Method | Time |")
        lines.append("|----------|-------|-------|--------|------|")
        for fname, exact, total, method, secs in scored[:10]:
            lines.append(f"| {fname} | {exact}/{total} | {total} | `{method}` | {secs}s |")

    with open(os.path.join(output_dir, "report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
