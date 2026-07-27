import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("PROCESSING_MODE", "sync")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill",
)

from app.services.extraction_pipeline import run_extraction_pipeline
from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
    read_pdf_bytes,
    resolve_pdf_path,
)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "Ground_Truth_Sertifikat.csv")
GT_DIR = os.path.join(os.path.dirname(__file__), "..", "Sertifikat_Ground_Truth")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "benchmark_results.json")


def run_benchmark():
    rows = load_csv(CSV_PATH)
    print(f"Loaded {len(rows)} ground truth rows")

    all_results = []
    skipped = 0

    for i, row in enumerate(rows):
        filename = row.get("Nama File", "")
        folder = row.get("Folder", "")
        filepath = resolve_pdf_path(row, GT_DIR)

        if not filepath:
            skipped += 1
            print(f"  [{i+1}] SKIP: {filename} (not found)")
            continue

        pdf_bytes = read_pdf_bytes(filepath)
        mapped = run_extraction_pipeline(pdf_bytes, filename, "2024/2025", "Sertifikat")

        field_results = evaluate_row(mapped.mapped_fields, row)
        all_results.append(field_results)

        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(rows)}] processed...")

    print(f"\nProcessed {len(all_results)} files, skipped {skipped}")

    summary = aggregate_results(all_results)

    payload = {
        "n_processed": len(all_results),
        "n_skipped": skipped,
        "summary": summary,
        "per_cert_results": all_results,
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nSaved individual results to {RESULTS_PATH}")

    print_report(summary)
    return summary


if __name__ == "__main__":
    run_benchmark()
