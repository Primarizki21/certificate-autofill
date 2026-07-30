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

from app.services.field_extractor import extract_certificate_fields
from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
)
from tests.ner_extractor import load_ner_model, extract_entities, normalize_for_ner
from tests.ner_to_fields import map_entities_to_fields
from tests.post_processors import filter_signer_roles

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "Ground_Truth_Sertifikat.csv")
TEXTS_DIR = os.path.join(
    os.path.dirname(__file__),
    "benchmark_runs",
    "run_20260728_131835",
    "extracted_texts",
)
RUNS_DIR = os.path.join(os.path.dirname(__file__), "benchmark_runs")


TEXT_FIELDS = {"nama_kegiatan_sertifikasi", "penyelenggara_kegiatan"}
STRUCTURED_FIELDS = {"waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "nomor_bukti_fisik_nomor_sertifikasi"}


def create_run_dir(name_prefix: str) -> str:
    run_id = f"run_{name_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def read_text_file(filepath: str) -> tuple[str, str]:
    with open(filepath) as f:
        content = f.read()
    stem = os.path.splitext(os.path.basename(filepath))[0]
    lines = content.split("\n")
    body_lines = [line for line in lines if not line.startswith("#")]
    raw_text = "\n".join(body_lines).strip()
    return stem, raw_text


def combine_hybrid(ner_fields: dict, regex_fields: dict) -> dict:
    combined = {}
    for field in TEXT_FIELDS:
        if field in ner_fields and ner_fields[field].value:
            combined[field] = ner_fields[field]
        elif field in regex_fields and regex_fields[field].value:
            combined[field] = regex_fields[field]
    for field in STRUCTURED_FIELDS:
        if field in regex_fields and regex_fields[field].value:
            combined[field] = regex_fields[field]
        elif field in ner_fields and ner_fields[field].value:
            combined[field] = ner_fields[field]
    return combined


def run_hybrid_benchmark():
    ner_pipe = load_ner_model()

    rows = load_csv(CSV_PATH)
    filename_to_row = {}
    for row in rows:
        fname = row.get("nama_file", "")
        stem = os.path.splitext(fname)[0]
        filename_to_row[stem] = row

    text_files = sorted(f for f in os.listdir(TEXTS_DIR) if f.endswith(".txt"))
    print(f"Loaded {len(rows)} ground truth rows, {len(text_files)} text files")

    run_dir = create_run_dir("hybrid_pp")
    print(f"Output: {run_dir}")

    all_ner_raw = []
    all_regex_raw = []
    all_hybrid_raw = []
    all_hybrid_pp = []

    for txt_file in tqdm(text_files, desc="Benchmarking"):
        stem, raw_text = read_text_file(os.path.join(TEXTS_DIR, txt_file))
        row = filename_to_row.get(stem)
        if row is None:
            continue

        normalized_text = normalize_for_ner(raw_text)

        try:
            regex_fields = extract_certificate_fields(raw_text)
        except Exception:
            regex_fields = {}

        try:
            entities = extract_entities(raw_text, ner_pipe)
            ner_fields = map_entities_to_fields(entities, full_text=normalized_text)
        except Exception:
            entities = []
            ner_fields = {}

        try:
            filtered_entities = filter_signer_roles(entities, raw_text)
            ner_pp_fields = map_entities_to_fields(filtered_entities, full_text=normalized_text)
        except Exception:
            ner_pp_fields = {}

        ner_result = evaluate_row(ner_fields, row)
        ner_result["_meta"] = {"filename": row.get("nama_file", stem), "raw_text": raw_text}
        all_ner_raw.append(ner_result)

        hybrid_fields = combine_hybrid(ner_fields, regex_fields)
        hybrid_result = evaluate_row(hybrid_fields, row)
        hybrid_result["_meta"] = {"filename": row.get("nama_file", stem), "raw_text": raw_text}
        all_hybrid_raw.append(hybrid_result)

        hybrid_pp_fields = combine_hybrid(ner_pp_fields, regex_fields)
        hybrid_pp_result = evaluate_row(hybrid_pp_fields, row)
        hybrid_pp_result["_meta"] = {"filename": row.get("nama_file", stem), "raw_text": raw_text}
        all_hybrid_pp.append(hybrid_pp_result)

    summary_ner = aggregate_results(all_ner_raw)
    summary_hybrid = aggregate_results(all_hybrid_raw)
    summary_hybrid_pp = aggregate_results(all_hybrid_pp)

    _save_results(run_dir, summary_ner, "ner_only")
    _save_results(run_dir, summary_hybrid, "hybrid")
    _save_results(run_dir, summary_hybrid_pp, "hybrid_pp")

    _write_diff_report(run_dir, summary_ner, summary_hybrid, summary_hybrid_pp)

    print("\n=== NER Only ===")
    print_report(summary_ner)
    print("\n=== Hybrid (NER+regex) ===")
    print_report(summary_hybrid)
    print("\n=== Hybrid + Post-Processing ===")
    print_report(summary_hybrid_pp)

    return summary_ner, summary_hybrid, summary_hybrid_pp


def _save_results(run_dir: str, summary: dict, mode: str):
    path = os.path.join(run_dir, f"summary_{mode}.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)


def _write_diff_report(run_dir: str, ner_summary: dict, hybrid_summary: dict, pp_summary: dict):
    lines = ["# Hybrid Benchmark Report\n"]
    lines.append(f"**Date:** {datetime.now().isoformat()}\n")
    lines.append("| Field | NER Only | Hybrid | Hybrid+PP | Delta (PP vs Hybrid) |\n")
    lines.append("|-------|----------|--------|-----------|----------------------|\n")

    for field in EVAL_FIELDS:
        n = ner_summary.get(field, {}).get("exact_acc", 0) * 100
        h = hybrid_summary.get(field, {}).get("exact_acc", 0) * 100
        p = pp_summary.get(field, {}).get("exact_acc", 0) * 100
        delta = p - h
        d_str = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"
        lines.append(f"| `{field}` | {n:.1f}% | {h:.1f}% | {p:.1f}% | {d_str} |\n")

    nm = ner_summary.get("macro_avg", {}).get("exact_acc", 0) * 100
    hm = hybrid_summary.get("macro_avg", {}).get("exact_acc", 0) * 100
    pm = pp_summary.get("macro_avg", {}).get("exact_acc", 0) * 100
    md = pm - hm
    md_str = f"+{md:.1f}%" if md >= 0 else f"{md:.1f}%"
    lines.append(f"| **MACRO** | {nm:.1f}% | {hm:.1f}% | {pm:.1f}% | {md_str} |\n")

    lines.append("\n## Fuzzy Accuracy\n")
    lines.append("| Field | NER Only | Hybrid | Hybrid+PP |\n")
    lines.append("|-------|----------|--------|-----------|\n")
    for field in EVAL_FIELDS:
        n = ner_summary.get(field, {}).get("fuzzy_acc", 0) * 100
        h = hybrid_summary.get(field, {}).get("fuzzy_acc", 0) * 100
        p = pp_summary.get(field, {}).get("fuzzy_acc", 0) * 100
        lines.append(f"| `{field}` | {n:.1f}% | {h:.1f}% | {p:.1f}% |\n")

    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write("".join(lines))

    print(f"\nReport saved to {run_dir}/report.md")


if __name__ == "__main__":
    run_hybrid_benchmark()
