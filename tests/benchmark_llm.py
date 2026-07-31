import csv
import json
import os
import sys
import time
from datetime import datetime

import openpyxl
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("PROCESSING_MODE", "sync")

from app.services.field_extractor import extract_certificate_fields
from tests import evaluation_framework as ev_fw
from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
    save_mismatch_report,
    save_summary_json,
)
from tests.ner_extractor import load_ner_model, extract_entities, normalize_for_ner
from tests.ner_to_fields import map_entities_to_fields
from tests.post_processors import filter_signer_roles
from tests.llm_extractor import (
    DEFAULT_MODEL,
    TINGKAT_GT_MAP,
    build_prompt_free_text,
    build_prompt_tingkat,
    build_token_usage_summary,
    call_ollama,
    log_call,
    validate_free_text,
    validate_tingkat,
    TokenUsage,
)

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

# LLM-inferred fields (adds tingkat which is never extracted by regex/NER)
LLM_EVAL_FIELDS = EVAL_FIELDS + ["tingkat"]

# Patch EVAL_FIELDS so evaluate_row also evaluates tingkat
_orig_eval_fields = list(ev_fw.EVAL_FIELDS)
ev_fw.EVAL_FIELDS[:] = LLM_EVAL_FIELDS

# Fields the LLM can infer
LLM_INFERRED = ["tingkat", "nama_kegiatan_sertifikasi", "penyelenggara_kegiatan", "nomor_bukti_fisik_nomor_sertifikasi"]

# 필드 이름 → label untuk prompt
FIELD_LABELS = {
    "nama_kegiatan_sertifikasi": "Nama Kegiatan",
    "penyelenggara_kegiatan": "Penyelenggara",
    "nomor_bukti_fisik_nomor_sertifikasi": "Nomor Bukti",
    "raw_role": "Peran",
    "tingkat": "Tingkat",
}

CONFIDENCE_THRESHOLD = 0.7


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


def needs_llm(field: str, fields: dict, always_extract: bool = False) -> bool:
    if always_extract:
        return True
    ev = fields.get(field)
    if ev is None or ev.value is None:
        return True
    if ev.confidence < CONFIDENCE_THRESHOLD:
        return True
    return False


def normalize_gt_tingkat(gt_value: str) -> str:
    return TINGKAT_GT_MAP.get(gt_value.strip(), gt_value.strip())


def create_run_dir(name_prefix: str) -> str:
    run_id = f"run_{name_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def save_xlsx(data: list[dict], path: str):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"
    if not data:
        wb.save(path)
        return
    headers = list(data[0].keys())
    ws.append(headers)
    for row in data:
        ws.append([row.get(h, "") for h in headers])
    wb.save(path)


def format_eval_result(eval_dict: dict, meta: dict) -> dict:
    row = dict(meta)
    for field, result in eval_dict.items():
        if field.startswith("_"):
            continue
        row[f"{field}_expected"] = result.get("expected", "")
        row[f"{field}_actual"] = result.get("actual", "")
        row[f"{field}_exact"] = 1 if result.get("exact") else 0
        row[f"{field}_fuzzy"] = 1 if result.get("fuzzy") else 0
        row[f"{field}_confidence"] = result.get("confidence", 0)
    return row


def run_llm_benchmark():
    ner_pipe = load_ner_model()
    rows = load_csv(CSV_PATH)
    filename_to_row = {}
    for row in rows:
        fname = row.get("nama_file", "")
        stem = os.path.splitext(fname)[0]
        row["tingkat"] = normalize_gt_tingkat(row.get("tingkat", ""))
        filename_to_row[stem] = row

    text_files = sorted(f for f in os.listdir(TEXTS_DIR) if f.endswith(".txt"))
    print(f"Loaded {len(rows)} ground truth rows, {len(text_files)} text files")
    print(f"Model: {DEFAULT_MODEL}")

    run_dir = create_run_dir("hybrid_llm")
    token_log_path = os.path.join(run_dir, "calls.json")
    print(f"Output: {run_dir}")

    all_hybrid_pp = []
    all_hybrid_llm = []
    total_llm_calls = 0
    errors = 0

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
            filtered_entities = filter_signer_roles(entities, raw_text)
            ner_pp_fields = map_entities_to_fields(filtered_entities, full_text=normalized_text)
        except Exception:
            ner_pp_fields = {}

        hybrid_pp = combine_hybrid(ner_pp_fields, regex_fields)

        # Evaluate hybrid+pp baseline
        hybrid_pp_result = evaluate_row(hybrid_pp, row)
        all_hybrid_pp.append(hybrid_pp_result)

        # Build known_fields dict for LLM context
        known_fields = {
            "nama_kegiatan_sertifikasi": "",
            "penyelenggara_kegiatan": "",
            "raw_role": "",
        }
        ev = regex_fields.get("raw_role")
        if ev and ev.value:
            known_fields["raw_role"] = ev.value
        for f in TEXT_FIELDS:
            ev = hybrid_pp.get(f)
            if ev and ev.value:
                known_fields[f] = ev.value

        # Call LLM for each field that needs it
        llm_fields = {}
        for field in LLM_INFERRED:
            always = field == "tingkat"
            if not needs_llm(field, hybrid_pp, always_extract=always):
                continue

            if field == "tingkat":
                prompt = build_prompt_tingkat(raw_text, known_fields)
                label = "Tingkat"
            else:
                label = FIELD_LABELS.get(field, field)
                prompt = build_prompt_free_text(label, raw_text, known_fields)

            response, ollama_data = call_ollama(prompt)

            valid = False
            clean_value = None
            if field == "tingkat":
                clean_value = validate_tingkat(response)
            else:
                clean_value = validate_free_text(response)

            if clean_value:
                valid = True
                llm_fields[field] = clean_value

            # Token tracking
            eval_count = ollama_data.get("eval_count", 0)
            prompt_eval_count = ollama_data.get("prompt_eval_count", 0)
            eval_dur = ollama_data.get("eval_duration", 0)
            prompt_eval_dur = ollama_data.get("prompt_eval_duration", 0)
            total_dur = ollama_data.get("total_duration", 0)
            tps = (eval_count / eval_dur * 1e9) if eval_dur > 0 else 0

            expected_val = row.get(field, "")
            correct = None
            if expected_val and clean_value:
                from tests.matchers import match_field
                m = match_field(expected_val, clean_value, field)
                correct = m.get("exact", False)

            call_log = TokenUsage(
                call_id=f"{stem}_{field}",
                certificate=f"{stem}.txt",
                field=field,
                method="hybrid_pp_llm",
                model=DEFAULT_MODEL,
                prompt_tokens=prompt_eval_count,
                completion_tokens=eval_count,
                total_tokens=prompt_eval_count + eval_count,
                prompt_eval_duration_ns=prompt_eval_dur,
                eval_duration_ns=eval_dur,
                total_duration_ns=total_dur,
                tokens_per_second=round(tps, 1),
                prompt_version="v1_aggressive",
                response=response,
                valid=valid,
                expected=expected_val or None,
                correct=correct,
            )
            log_call(call_log, token_log_path)
            total_llm_calls += 1

        # Merge LLM results into hybrid+pp
        from app.services.field_extractor import ExtractedValue

        hybrid_llm = dict(hybrid_pp)
        for field, value in llm_fields.items():
            hybrid_llm[field] = ExtractedValue(value, 0.85, "llm_ollama")

        # Evaluate hybrid+pp+llm
        hybrid_llm_result = evaluate_row(hybrid_llm, row)
        all_hybrid_llm.append(hybrid_llm_result)

    # Aggregate results
    summary_pp = aggregate_results(all_hybrid_pp)
    summary_llm = aggregate_results(all_hybrid_llm)

    # Save summaries (only fields both methods share for fair comparison)
    _save_summary(run_dir, summary_pp, "hybrid_pp", EVAL_FIELDS)
    _save_summary(run_dir, summary_llm, "hybrid_llm", EVAL_FIELDS)

    # Also save llm-only evaluation for tingkat (not in EVAL_FIELDS)
    _save_summary(run_dir, summary_pp, "hybrid_pp_full", list(summary_pp.keys()))
    _save_summary(run_dir, summary_llm, "hybrid_llm_full", list(summary_llm.keys()))

    # Canonical summary.json (hybrid+pp+llm)
    save_summary_json(summary_llm, run_dir)
    save_mismatch_report(all_hybrid_llm, run_dir, source="hybrid_pp_llm")

    # Token usage summary
    token_summary = build_token_usage_summary(token_log_path)
    if token_summary:
        summary_path = os.path.join(run_dir, "token_usage.json")
        with open(summary_path, "w") as f:
            json.dump(token_summary, f, indent=2)
        print(f"\nToken usage saved: {summary_path}")
        print(f"  Total calls: {token_summary['total_calls']}")
        print(f"  Total tokens: {token_summary['total_tokens']}")
        print(f"  Avg latency: {token_summary['avg_latency_ms']}ms")
        print(f"  Avg tok/s: {token_summary['avg_tokens_per_second']}")

    # XLSX
    xlsx_rows = []
    for i, (pp_r, llm_r) in enumerate(zip(all_hybrid_pp, all_hybrid_llm)):
        meta = pp_r.get("_meta", {})
        row_data = {k: v for k, v in meta.items() if k != "raw_text"}
        row_data["index"] = i
        for field in EVAL_FIELDS:
            pp_ev = pp_r.get(field, {})
            llm_ev = llm_r.get(field, {})
            row_data[f"{field}_pp_expected"] = pp_ev.get("expected", "")
            row_data[f"{field}_pp_actual"] = pp_ev.get("actual", "")
            row_data[f"{field}_pp_exact"] = 1 if pp_ev.get("exact") else 0
            row_data[f"{field}_llm_actual"] = llm_ev.get("actual", "")
            row_data[f"{field}_llm_exact"] = 1 if llm_ev.get("exact") else 0
            row_data[f"{field}_llm_delta"] = row_data[f"{field}_llm_exact"] - row_data[f"{field}_pp_exact"]
        xlsx_rows.append(row_data)
    xlsx_path = os.path.join(run_dir, "results.xlsx")
    save_xlsx(xlsx_rows, xlsx_path)

    # Report
    _write_report(run_dir, summary_pp, summary_llm)

    # Print
    print("\n=== Hybrid + Post-Processing (baseline) ===")
    print_report(summary_pp)
    print("\n=== Hybrid + Post-Processing + LLM ===")
    print_report(summary_llm)
    print(f"\nTotal LLM calls: {total_llm_calls}")

    return summary_pp, summary_llm


def _save_summary(run_dir: str, summary: dict, mode: str, fields: list[str] | None = None):
    if fields:
        filtered = {k: v for k, v in summary.items() if k in fields or k == "macro_avg"}
    else:
        filtered = summary
    path = os.path.join(run_dir, f"summary_{mode}.json")
    with open(path, "w") as f:
        json.dump(filtered, f, indent=2, default=str)


def _write_report(run_dir: str, pp_summary: dict, llm_summary: dict):
    lines = ["# Hybrid + PP vs Hybrid + PP + LLM Benchmark\n"]
    lines.append(f"**Date:** {datetime.now().isoformat()}\n")
    lines.append(f"**Model:** {DEFAULT_MODEL}\n")
    lines.append(f"**Prompt version:** v1_aggressive\n\n")

    # Exact comparison
    lines.append("## Exact Accuracy\n\n")
    lines.append("| Field | Hybrid+PP | Hybrid+PP+LLM | Delta |\n")
    lines.append("|-------|-----------|---------------|-------|\n")
    for field in LLM_EVAL_FIELDS:
        p = pp_summary.get(field, {}).get("exact_acc", 0) * 100
        l = llm_summary.get(field, {}).get("exact_acc", 0) * 100
        delta = l - p
        d_str = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"
        lines.append(f"| `{field}` | {p:.1f}% | {l:.1f}% | {d_str} |\n")

    pm = pp_summary.get("macro_avg", {}).get("exact_acc", 0) * 100
    lm = llm_summary.get("macro_avg", {}).get("exact_acc", 0) * 100
    md = lm - pm
    md_str = f"+{md:.1f}%" if md >= 0 else f"{md:.1f}%"
    lines.append(f"| **MACRO** | {pm:.1f}% | {lm:.1f}% | {md_str} |\n")

    # Fuzzy comparison
    lines.append("\n## Fuzzy Accuracy\n\n")
    lines.append("| Field | Hybrid+PP | Hybrid+PP+LLM | Delta |\n")
    lines.append("|-------|-----------|---------------|-------|\n")
    for field in LLM_EVAL_FIELDS:
        p = pp_summary.get(field, {}).get("fuzzy_acc", 0) * 100
        l = llm_summary.get(field, {}).get("fuzzy_acc", 0) * 100
        delta = l - p
        d_str = f"+{delta:.1f}%" if delta >= 0 else f"{delta:.1f}%"
        lines.append(f"| `{field}` | {p:.1f}% | {l:.1f}% | {d_str} |\n")

    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write("".join(lines))
    print(f"\nReport saved to {run_dir}/report.md")


if __name__ == "__main__":
    run_llm_benchmark()
