import csv
import os
import sys
from collections import defaultdict

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
