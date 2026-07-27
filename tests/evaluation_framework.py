import csv
import os
import sys
from collections import defaultdict

from tests.date_normalizer import normalize_date
from tests.matchers import match_field

EVAL_FIELDS = [
    "tingkat",
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "jenis_penyelenggara",
    "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi",
]


def load_csv(csv_path: str) -> list[dict]:
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def resolve_pdf_path(row: dict, base_dir: str) -> str | None:
    folder = row.get("Folder", "").strip()
    filename = row.get("Nama File", "").strip()
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

    for row_results in all_results:
        for field, result in row_results.items():
            total[field] += 1
            if result["exact"]:
                exact_ok[field] += 1
            if result["fuzzy"]:
                fuzzy_ok[field] += 1
            confidences[field].append(result["confidence"])

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
        }

    overall_exact = sum(exact_ok.values())
    overall_fuzzy = sum(fuzzy_ok.values())
    overall_total = sum(total.values())
    summary["macro_avg"] = {
        "total": overall_total,
        "exact": overall_exact,
        "fuzzy": overall_fuzzy,
        "exact_acc": round(overall_exact / overall_total, 4) if overall_total else 0,
        "fuzzy_acc": round(overall_fuzzy / overall_total, 4) if overall_total else 0,
    }

    return summary


def print_report(summary: dict):
    print()
    print(f"{'Field':38s} {'Total':>6s} {'Exact':>8s} {'Fuzzy':>8s} {'E%':>6s} {'F%':>6s} {'Avg Conf':>8s}")
    print("-" * 80)
    for field, s in summary.items():
        if field == "macro_avg":
            continue
        print(
            f"{field:38s} {s['total']:>6d} {s['exact']:>8d} {s['fuzzy']:>8d} "
            f"{s['exact_acc']*100:>5.1f}% {s['fuzzy_acc']*100:>5.1f}% {s['avg_confidence']:>7.2f}"
        )
    ma = summary["macro_avg"]
    print("-" * 80)
    print(
        f"{'MACRO AVERAGE':38s} {ma['total']:>6d} {ma['exact']:>8d} {ma['fuzzy']:>8d} "
        f"{ma['exact_acc']*100:>5.1f}% {ma['fuzzy_acc']*100:>5.1f}%"
    )
    print()
