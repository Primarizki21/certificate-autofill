import json
import os
import sys
import time
from collections import Counter
from datetime import datetime

from tqdm import tqdm

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
    save_mismatch_report,
    save_summary_json,
)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "Ground_Truth_Sertifikat.csv")
GT_DIR = os.path.join(os.path.dirname(__file__), "..", "Sertifikat_Ground_Truth")
RUNS_DIR = os.path.join(os.path.dirname(__file__), "benchmark_runs")


def create_run_dir() -> str:
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(os.path.join(run_dir, "extracted_texts"), exist_ok=True)
    return run_dir


def run_benchmark():
    rows = load_csv(CSV_PATH)
    print(f"Loaded {len(rows)} ground truth rows")

    run_dir = create_run_dir()
    print(f"Output: {run_dir}")

    all_results = []
    skipped = 0
    errors = 0
    timings = []

    for row in tqdm(rows, desc="Benchmarking"):
        filename = row.get("nama_file", "")
        filepath = resolve_pdf_path(row, GT_DIR)

        if not filepath:
            skipped += 1
            continue

        try:
            pdf_bytes = read_pdf_bytes(filepath)
            t0 = time.perf_counter()
            mapped = run_extraction_pipeline(pdf_bytes, "2024/2025", "Sertifikat")
            elapsed = round(time.perf_counter() - t0, 2)
            timings.append(elapsed)

            field_results = evaluate_row(mapped.mapped_fields, row)
            field_results["_meta"] = {
                "filename": filename,
                "parser_engine": mapped.parser_engine,
                "seconds": elapsed,
                "raw_text": mapped.raw_text,
                "extracted_fields": {
                    k: {"value": v.value, "confidence": v.confidence, "source": v.source}
                    for k, v in mapped.mapped_fields.items()
                    if not k.startswith("_")
                },
            }
            all_results.append(field_results)
        except Exception as e:
            errors += 1
            all_results.append({
                "_error": str(e),
                "_meta": {"filename": filename},
            })

    print(f"\nProcessed {len(all_results)} files, skipped {skipped}, errors {errors}")

    summary = aggregate_results(all_results)

    if timings:
        timings_sorted = sorted(timings)
        summary["_timing"] = {
            "total_seconds": round(sum(timings), 1),
            "avg_per_file": round(sum(timings) / len(timings), 2),
            "median_per_file": round(timings_sorted[len(timings_sorted) // 2], 2),
            "p95_per_file": round(timings_sorted[int(len(timings_sorted) * 0.95)], 2),
            "max_per_file": round(max(timings), 2),
            "n_timed": len(timings),
        }

    # Diff against previous run
    prev_summary = _load_previous_summary()
    if prev_summary:
        print_diff(prev_summary, summary)

    # Save extracted texts
    texts_dir = os.path.join(run_dir, "extracted_texts")
    for result in all_results:
        meta = result.get("_meta", {})
        fname = meta.get("filename", "unknown")
        raw_text = meta.get("raw_text", "")
        if raw_text:
            stem = os.path.splitext(fname)[0]
            with open(os.path.join(texts_dir, f"{stem}.txt"), "w") as f:
                f.write(f"# Method: {meta.get('parser_engine', '?')}\n")
                f.write(f"# Time: {meta.get('seconds', '?')}s\n\n")
                f.write(raw_text)

    # Save results.json (strip raw_text to keep size reasonable)
    json_results = []
    for r in all_results:
        meta = r.get("_meta", {})
        clean = {k: v for k, v in r.items() if k != "_meta"}
        clean["_meta"] = {k: v for k, v in meta.items() if k != "raw_text"}
        json_results.append(clean)

    payload = {
        "n_processed": len(all_results),
        "n_skipped": skipped,
        "n_errors": errors,
        "summary": summary,
        "per_cert_results": json_results,
    }
    with open(os.path.join(run_dir, "results.json"), "w") as f:
        json.dump(payload, f, indent=2, default=str)

    # Save mismatches.csv + extracted_fields.csv (+ xlsx copies)
    save_mismatch_report(all_results, run_dir, source="regex")

    # Save summary.json
    save_summary_json(summary, run_dir)

    # Save summary.md (pipeline-specific: includes parser engine distribution)
    _write_summary_md(run_dir, summary, all_results)

    print(f"\nSaved to {run_dir}")
    print_report(summary)
    return summary


def _load_previous_summary() -> dict | None:
    if not os.path.exists(RUNS_DIR):
        return None
    dirs = sorted(d for d in os.listdir(RUNS_DIR) if d.startswith("run_"))
    if not dirs:
        return None
    prev_path = os.path.join(RUNS_DIR, dirs[-1], "results.json")
    if not os.path.exists(prev_path):
        return None
    try:
        with open(prev_path) as f:
            return json.load(f).get("summary", {})
    except Exception:
        return None


def _write_summary_md(run_dir: str, summary: dict, all_results: list):
    lines = ["# Benchmark Summary\n"]
    lines.append(f"**Date:** {datetime.now().isoformat()}\n")

    t = summary.get("_timing", {})
    lines.append(f"**Total time:** {t.get('total_seconds', '?')}s "
                 f"({t.get('avg_per_file', '?')}s avg/file)\n")

    # Parser engine distribution
    engines = Counter(r.get("_meta", {}).get("parser_engine", "?") for r in all_results)
    lines.append("## Parser Engine Distribution\n")
    for engine, count in engines.most_common():
        lines.append(f"- `{engine}`: {count}")

    # Field accuracy table
    lines.append("\n## Field Accuracy\n")
    lines.append("| Field | Total | Exact% | Fuzzy% | AvgWER | AvgCER | Avg Conf |")
    lines.append("|-------|-------|--------|--------|--------|--------|----------|")
    for field, s in summary.items():
        if field.startswith("_") or field == "macro_avg":
            continue
        lines.append(f"| {field} | {s['total']} | {s['exact_acc']*100:.1f}% | "
                     f"{s['fuzzy_acc']*100:.1f}% | {s['avg_wer']:.3f} | {s['avg_cer']:.3f} | {s['avg_confidence']:.2f} |")
    ma = summary.get("macro_avg", {})
    lines.append(f"| **MACRO** | {ma.get('total',0)} | {ma.get('exact_acc',0)*100:.1f}% | "
                 f"{ma.get('fuzzy_acc',0)*100:.1f}% | {ma['avg_wer']:.3f} | {ma['avg_cer']:.3f} | — |")

    # Worst 10 files
    lines.append("\n## Worst 10 Files (fewest exact matches)\n")
    scored = []
    for r in all_results:
        meta = r.get("_meta", {})
        exact_count = sum(1 for k, v in r.items() if not k.startswith("_") and v.get("exact"))
        total_fields = sum(1 for k in r if not k.startswith("_"))
        scored.append((meta.get("filename", "?"), exact_count, total_fields,
                       meta.get("parser_engine", "?"), meta.get("seconds", 0)))
    scored.sort(key=lambda x: (x[1], x[0]))
    lines.append("| Filename | Exact | Total | Method | Time |")
    lines.append("|----------|-------|-------|--------|------|")
    for fname, exact, total, method, secs in scored[:10]:
        lines.append(f"| {fname} | {exact}/{total} | {total} | `{method}` | {secs}s |")

    with open(os.path.join(run_dir, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def print_diff(prev_summary: dict, curr_summary: dict):
    print()
    print("=" * 90)
    print("DIFF vs previous run")
    print("=" * 90)
    print(f"{'Field':38s} {'Prev E%':>8s} {'New E%':>8s} {'Delta':>7s}  {'Prev F%':>8s} {'New F%':>8s} {'Delta':>7s}")
    print("-" * 90)

    for field in EVAL_FIELDS:
        p = prev_summary.get(field, {})
        c = curr_summary.get(field, {})
        pe = p.get("exact_acc", 0) * 100
        ce = c.get("exact_acc", 0) * 100
        pf = p.get("fuzzy_acc", 0) * 100
        cf = c.get("fuzzy_acc", 0) * 100
        de = ce - pe
        df = cf - pf
        de_s = f"+{de:.1f}" if de >= 0 else f"{de:.1f}"
        df_s = f"+{df:.1f}" if df >= 0 else f"{df:.1f}"
        print(
            f"{field:38s} {pe:>7.1f}% {ce:>7.1f}% {de_s:>6s}%  "
            f"{pf:>7.1f}% {cf:>7.1f}% {df_s:>6s}%"
        )

    pm = prev_summary.get("macro_avg", {})
    cm = curr_summary.get("macro_avg", {})
    pe = pm.get("exact_acc", 0) * 100
    ce = cm.get("exact_acc", 0) * 100
    pf = pm.get("fuzzy_acc", 0) * 100
    cf = cm.get("fuzzy_acc", 0) * 100
    de = ce - pe
    df = cf - pf
    de_s = f"+{de:.1f}" if de >= 0 else f"{de:.1f}"
    df_s = f"+{df:.1f}" if df >= 0 else f"{df:.1f}"
    print("-" * 90)
    print(
        f"{'MACRO AVERAGE':38s} {pe:>7.1f}% {ce:>7.1f}% {de_s:>6s}%  "
        f"{pf:>7.1f}% {cf:>7.1f}% {df_s:>6s}%"
    )
    print()


if __name__ == "__main__":
    run_benchmark()
