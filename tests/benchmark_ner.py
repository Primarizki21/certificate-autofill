import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime

import openpyxl
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("PROCESSING_MODE", "sync")

from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
)
from tests.ner_extractor import load_ner_model, extract_entities
from tests.ner_to_fields import map_entities_to_fields

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "Ground_Truth_Sertifikat.csv")
TEXTS_DIR = os.path.join(
    os.path.dirname(__file__),
    "benchmark_runs",
    "run_20260728_131835",
    "extracted_texts",
)
RUNS_DIR = os.path.join(os.path.dirname(__file__), "benchmark_runs")


def create_run_dir() -> str:
    run_id = f"run_ner_v1_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def read_text_file(filepath: str) -> tuple[str, str, str]:
    with open(filepath) as f:
        content = f.read()

    stem = os.path.splitext(os.path.basename(filepath))[0]

    lines = content.split("\n")
    method = ""
    timing = ""
    body_lines = []
    for line in lines:
        if line.startswith("# Method:"):
            method = line.replace("# Method:", "").strip()
        elif line.startswith("# Time:"):
            timing = line.replace("# Time:", "").strip()
        elif not line.startswith("#"):
            body_lines.append(line)

    raw_text = "\n".join(body_lines).strip()
    return stem, raw_text, method, timing


def run_benchmark():
    ner_pipe = load_ner_model()

    rows = load_csv(CSV_PATH)
    filename_to_row = {}
    for row in rows:
        fname = row.get("nama_file", "")
        stem = os.path.splitext(fname)[0]
        filename_to_row[stem] = row

    text_files = sorted(
        f for f in os.listdir(TEXTS_DIR) if f.endswith(".txt")
    )
    print(f"Loaded {len(rows)} ground truth rows, {len(text_files)} text files")

    run_dir = create_run_dir()
    print(f"Output: {run_dir}")

    all_results = []
    errors = 0
    skipped = 0
    timings = []
    engine_counts: Counter = Counter()

    for txt_file in tqdm(text_files, desc="Benchmarking NER"):
        stem, raw_text, method, _ = read_text_file(
            os.path.join(TEXTS_DIR, txt_file)
        )

        row = filename_to_row.get(stem)
        if row is None:
            skipped += 1
            continue

        try:
            t0 = time.perf_counter()
            entities = extract_entities(raw_text, ner_pipe)
            ner_fields = map_entities_to_fields(entities)
            elapsed = round(time.perf_counter() - t0, 2)
            timings.append(elapsed)

            engine_counts["ner_indobert"] += 1

            field_results = evaluate_row(ner_fields, row)
            field_results["_meta"] = {
                "filename": row.get("nama_file", stem),
                "parser_engine": "ner_indobert",
                "seconds": elapsed,
                "raw_text": raw_text,
                "extracted_fields": {
                    k: {"value": v.value, "confidence": v.confidence, "source": v.source}
                    for k, v in ner_fields.items()
                },
            }
            all_results.append(field_results)
        except Exception as e:
            errors += 1
            all_results.append({
                "_error": str(e),
                "_meta": {"filename": row.get("nama_file", stem)},
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

    json_results = []
    for r in all_results:
        meta = r.get("_meta", {})
        clean = {k: v for k, v in r.items() if k != "_meta"}
        clean["_meta"] = {k: v for k, v in meta.items() if k != "raw_text"}
        json_results.append(clean)

    payload = {
        "experiment": "ner_v1",
        "model": "treamyracle/indobert-ner-gold",
        "n_processed": len(all_results),
        "n_errors": errors,
        "n_skipped": skipped,
        "summary": summary,
        "per_cert_results": json_results,
    }
    with open(os.path.join(run_dir, "results.json"), "w") as f:
        json.dump(payload, f, indent=2, default=str)

    _write_mismatches_csv(run_dir, all_results)
    _write_extracted_fields_csv(run_dir, all_results)
    _write_summary_md(run_dir, summary, all_results, engine_counts)
    _write_excel_files(run_dir)

    prev_summary = _load_previous_summary()
    if prev_summary:
        print_diff(prev_summary, summary)

    print(f"\nSaved to {run_dir}")
    print_report(summary)
    return summary


def _load_previous_summary() -> dict | None:
    if not os.path.exists(RUNS_DIR):
        return None
    dirs = sorted(d for d in os.listdir(RUNS_DIR) if d.startswith("run_ner_"))
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


def print_diff(prev_summary: dict, curr_summary: dict):
    print()
    print("=" * 90)
    print("DIFF vs previous NER run")
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


def _write_mismatches_csv(run_dir: str, all_results: list):
    path = os.path.join(run_dir, "mismatches.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "field", "expected", "actual", "confidence", "error_type"])
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
                if r.get("exact"):
                    continue
                if not exp or exp == "-":
                    continue
                error_type = "null" if act is None else "mismatch"
                writer.writerow([fname, field, exp, act or "", f"{conf:.2f}", error_type])


def _write_extracted_fields_csv(run_dir: str, all_results: list):
    path = os.path.join(run_dir, "extracted_fields.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "field", "value", "confidence", "source", "exact_match", "wer", "cer"])
        for result in all_results:
            meta = result.get("_meta", {})
            fname = meta.get("filename", "")
            for field in EVAL_FIELDS:
                r = result.get(field, {})
                if not r:
                    continue
                writer.writerow([
                    fname,
                    field,
                    r.get("actual") or "",
                    f"{r.get('confidence', 0):.2f}",
                    "ner_indobert",
                    r.get("exact", False),
                    f"{r.get('wer', 1.0):.3f}",
                    f"{r.get('cer', 1.0):.3f}",
                ])


def _write_summary_md(run_dir: str, summary: dict, all_results: list, engine_counts: Counter):
    lines = ["# NER v1 Benchmark Summary\n"]
    lines.append(f"**Experiment:** Pre-trained NER (`treamyracle/indobert-ner-gold`)\n")
    lines.append(f"**Date:** {datetime.now().isoformat()}\n")

    t = summary.get("_timing", {})
    lines.append(f"**Total time:** {t.get('total_seconds', '?')}s "
                 f"({t.get('avg_per_file', '?')}s avg/file)\n")

    lines.append("## Model Distribution\n")
    for engine, count in engine_counts.most_common():
        lines.append(f"- `{engine}`: {count}")

    lines.append("\n## Per-Field Accuracy\n")
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

    lines.append("\n## Worst 10 Files\n")
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

    lines.append("\n## Goals vs Baseline\n")
    lines.append("| Metric | Regex Baseline (42.2%) | NER v1 | Target |")
    lines.append("|--------|----------------------|--------|--------|")
    for field in EVAL_FIELDS:
        s = summary.get(field, {})
        ner_exact = s.get("exact_acc", 0) * 100
        lines.append(f"| `{field}` exact | — | {ner_exact:.1f}% | — |")
    ma = summary.get("macro_avg", {})
    ner_macro = ma.get("exact_acc", 0) * 100
    lines.append(f"| **MACRO exact** | 42.2% | {ner_macro:.1f}% | >50% |")

    with open(os.path.join(run_dir, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def _write_excel_files(run_dir: str):
    for csv_name in ("mismatches.csv", "extracted_fields.csv"):
        csv_path = os.path.join(run_dir, csv_name)
        if not os.path.exists(csv_path):
            continue
        xlsx_path = os.path.join(run_dir, csv_name.replace(".csv", ".xlsx"))
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = csv_name.replace(".csv", "")
        with open(csv_path) as f:
            reader = csv.reader(f)
            for row in reader:
                ws.append(row)
        wb.save(xlsx_path)


if __name__ == "__main__":
    run_benchmark()
