import json
import os
import sys
from datetime import datetime

import openpyxl
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("PROCESSING_MODE", "sync")

from tests import evaluation_framework as ev_fw
from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
)
from tests.llm_extractor import (
    DEFAULT_MODEL,
    TINGKAT_GT_MAP,
    TokenUsage,
    call_ollama,
    log_call,
    build_token_usage_summary,
)
from tests.llm_extractor_v2 import (
    FIELD_MAP,
    PROMPT_VERSION,
    build_prompt_v2,
    parse_and_validate,
)
from tests.benchmark_llm import (
    CSV_PATH,
    TEXTS_DIR,
    RUNS_DIR,
    read_text_file,
    create_run_dir,
    save_xlsx,
    LLM_EVAL_FIELDS,
)

# Patch EVAL_FIELDS to include tingkat
ev_fw.EVAL_FIELDS[:] = LLM_EVAL_FIELDS


def run_benchmark_v2():
    rows = load_csv(CSV_PATH)
    filename_to_row = {}
    for row in rows:
        fname = row.get("nama_file", "")
        stem = os.path.splitext(fname)[0]
        row["tingkat"] = TINGKAT_GT_MAP.get(row.get("tingkat", "").strip(), row.get("tingkat", "").strip())
        filename_to_row[stem] = row

    text_files = sorted(f for f in os.listdir(TEXTS_DIR) if f.endswith(".txt"))
    print(f"Loaded {len(rows)} ground truth rows, {len(text_files)} text files")
    print(f"Model: {DEFAULT_MODEL}")

    run_dir = create_run_dir("fulltext_llm")
    token_log_path = os.path.join(run_dir, "calls.json")
    print(f"Output: {run_dir}")

    all_results = []
    errors = 0

    for txt_file in tqdm(text_files, desc="Benchmarking"):
        stem, raw_text = read_text_file(os.path.join(TEXTS_DIR, txt_file))
        row = filename_to_row.get(stem)
        if row is None:
            continue

        # Build prompt and call LLM
        prompt = build_prompt_v2(raw_text)
        response, ollama_data = call_ollama(prompt, max_tokens=200)

        # Parse and validate
        extracted = parse_and_validate(response)

        # Build ExtractedValue dict
        from app.services.field_extractor import ExtractedValue

        mapped = {}
        for gt_key in EVAL_FIELDS:
            val = extracted.get(gt_key)
            if val:
                mapped[gt_key] = ExtractedValue(val, 0.85, "llm_ollama_v2")

        # Token tracking
        eval_count = ollama_data.get("eval_count", 0)
        prompt_eval_count = ollama_data.get("prompt_eval_count", 0)
        eval_dur = ollama_data.get("eval_duration", 0)
        prompt_eval_dur = ollama_data.get("prompt_eval_duration", 0)
        total_dur = ollama_data.get("total_duration", 0)
        tps = (eval_count / eval_dur * 1e9) if eval_dur > 0 else 0

        # Check per-field correctness for logging
        from tests.matchers import match_field

        fields_in_call = []
        for alias, gt_key in FIELD_MAP.items():
            expected_val = row.get(gt_key, "")
            actual_val = extracted.get(gt_key)
            correct = None
            if expected_val and actual_val:
                m = match_field(expected_val, actual_val, gt_key)
                correct = m.get("exact", False)
            fields_in_call.append({
                "field": gt_key,
                "response": extracted.get(gt_key, ""),
                "expected": expected_val or None,
                "correct": correct,
            })

        call_log = TokenUsage(
            call_id=f"{stem}_fulltext",
            certificate=f"{stem}.txt",
            field="all",
            method="fulltext_llm",
            model=DEFAULT_MODEL,
            prompt_tokens=prompt_eval_count,
            completion_tokens=eval_count,
            total_tokens=prompt_eval_count + eval_count,
            prompt_eval_duration_ns=prompt_eval_dur,
            eval_duration_ns=eval_dur,
            total_duration_ns=total_dur,
            tokens_per_second=round(tps, 1),
            prompt_version=PROMPT_VERSION,
            response=json.dumps(fields_in_call),
            valid=bool(extracted),
        )
        log_call(call_log, token_log_path)

        # Evaluate
        result = evaluate_row(mapped, row)
        all_results.append(result)

    # Aggregate
    summary = aggregate_results(all_results)
    _save_summary(run_dir, summary, "fulltext_llm", LLM_EVAL_FIELDS)

    # Token usage
    token_summary = build_token_usage_summary(token_log_path)
    if token_summary:
        token_summary["method"] = "fulltext_llm"
        with open(os.path.join(run_dir, "token_usage.json"), "w") as f:
            json.dump(token_summary, f, indent=2)
        print(f"\nToken usage: {token_summary['total_tokens']} tokens across {token_summary['total_calls']} calls")
        print(f"  Avg latency: {token_summary['avg_latency_ms']}ms")

    # XLSX
    xlsx_rows = []
    for i, result in enumerate(all_results):
        meta = result.get("_meta", {})
        row_data = {k: v for k, v in meta.items() if k != "raw_text"}
        row_data["index"] = i
        for field in EVAL_FIELDS:
            ev = result.get(field, {})
            row_data[f"{field}_llm_expected"] = ev.get("expected", "")
            row_data[f"{field}_llm_actual"] = ev.get("actual", "")
            row_data[f"{field}_llm_exact"] = 1 if ev.get("exact") else 0
            row_data[f"{field}_llm_fuzzy"] = 1 if ev.get("fuzzy") else 0
        xlsx_rows.append(row_data)
    save_xlsx(xlsx_rows, os.path.join(run_dir, "results.xlsx"))

    # Report
    _write_report(run_dir, summary)

    print("\n=== Full-Text LLM Extraction ===")
    print_report(summary)

    return summary


def _save_summary(run_dir: str, summary: dict, mode: str, fields: list[str] | None = None):
    if fields:
        filtered = {k: v for k, v in summary.items() if k in fields or k == "macro_avg"}
    else:
        filtered = summary
    path = os.path.join(run_dir, f"summary_{mode}.json")
    with open(path, "w") as f:
        json.dump(filtered, f, indent=2, default=str)


def _write_report(run_dir: str, summary: dict):
    lines = ["# Full-Text LLM Extraction (Approach 2)\n"]
    lines.append(f"**Date:** {datetime.now().isoformat()}\n")
    lines.append(f"**Model:** {DEFAULT_MODEL}\n")
    lines.append(f"**Prompt version:** {PROMPT_VERSION}\n\n")

    lines.append("## Exact Accuracy\n\n")
    lines.append("| Field | Full-text LLM |\n")
    lines.append("|-------|---------------|\n")
    for field in EVAL_FIELDS:
        p = summary.get(field, {}).get("exact_acc", 0) * 100
        lines.append(f"| `{field}` | {p:.1f}% |\n")
    ma = summary.get("macro_avg", {}).get("exact_acc", 0) * 100
    lines.append(f"| **MACRO** | {ma:.1f}% |\n")

    lines.append("\n## Fuzzy Accuracy\n\n")
    lines.append("| Field | Full-text LLM |\n")
    lines.append("|-------|---------------|\n")
    for field in EVAL_FIELDS:
        p = summary.get(field, {}).get("fuzzy_acc", 0) * 100
        lines.append(f"| `{field}` | {p:.1f}% |\n")

    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write("".join(lines))
    print(f"\nReport saved to {run_dir}/report.md")


if __name__ == "__main__":
    run_benchmark_v2()
