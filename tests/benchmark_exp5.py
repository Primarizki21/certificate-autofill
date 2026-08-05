"""Exp 5 — multi-field LLM benchmark (tingkat + penyelenggara, 1 call).

Variant C (ceiling experiment): LLM organizer HANYA dipakai untuk cert yang
pipeline organizer-nya MISS (tidak exact & tidak fuzzy pasca matcher v2).
Cert yang sudah exact/fuzzy tidak diganggu (no-regress). Oracle selection
pakai GT — ini mengukur CEILING, bukan runtime selector.

Alur per cert (router on):
- rule-routed            -> tingkat=rule, organizer=pipeline, TANPA call
- ke-LLM & organizer miss -> multi-field prompt (tingkat + organizer), 1 call
- ke-LLM & organizer OK   -> f_bias biasa (tingkat saja), 1 call

Evaluasi: GT v9 + matcher v2 (tests/matchers). Organizer pasca-pipeline vs
pasca-LLM (variant C) dibandingkan.

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_exp5
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_exp5 --limit 10
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("PROCESSING_MODE", "sync")

from app.services.field_extractor import extract_certificate_fields, ExtractedValue
from tests import evaluation_framework as ev_fw
from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
    save_summary_json,
)
from tests.ner_extractor import load_ner_model, extract_entities, normalize_for_ner
from tests.ner_to_fields import map_entities_to_fields
from tests.post_processors import filter_signer_roles
from tests.llm_extractor import (
    DEFAULT_MODEL,
    TINGKAT_GT_MAP,
    build_token_usage_summary,
    call_ollama,
    log_call,
    validate_tingkat,
    TokenUsage,
)
from tests.benchmark_llm import (
    read_text_file,
    combine_hybrid,
    RUNS_DIR,
    create_run_dir,
)
from tests.llm_extractor_v4 import build_prompt_tingkat_bias
from tests.llm_extractor_v5 import (
    PROMPT_VERSION,
    build_prompt_multi,
    parse_multi_response,
)
from tests.llm_router_v4 import route_tingkat_trace
from tests.matchers import match_field
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.environ.get(
    "GT_CSV_PATH", os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v9.csv")
)
TEXTS_DIR = os.environ.get(
    "GT_TEXTS_DIR",
    os.path.join(REPO_ROOT, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts"),
)
GT_VERSION = os.path.basename(CSV_PATH).replace(".csv", "")
N_CERTS = 74

if "tingkat" not in ev_fw.EVAL_FIELDS:
    ev_fw.EVAL_FIELDS[:] = EVAL_FIELDS + ["tingkat"]


def normalize_gt_tingkat(value: str) -> str:
    return TINGKAT_GT_MAP.get(value.strip(), value.strip())


def _organizer_is_miss(gt: str, actual: str) -> bool:
    """True bila organizer pipeline MISS pasca matcher v2 (target variant C)."""
    if not gt or gt == "-":
        return False
    res = match_field(gt, actual, "penyelenggara_kegiatan")
    return not res["exact"] and not res["fuzzy"]


def _call(prompt: str, stem: str, method: str, row: dict, log_path: str, max_tokens: int = 60) -> tuple[str, dict]:
    response, ollama_data = call_ollama(prompt, max_tokens=max_tokens)
    eval_count = ollama_data.get("eval_count", 0)
    prompt_eval_count = ollama_data.get("prompt_eval_count", 0)
    eval_dur = ollama_data.get("eval_duration", 0)
    prompt_eval_dur = ollama_data.get("prompt_eval_duration", 0)
    total_dur = ollama_data.get("total_duration", 0)
    tps = (eval_count / eval_dur * 1e9) if eval_dur > 0 else 0

    call_log = TokenUsage(
        call_id=f"{stem}_{method}",
        certificate=f"{stem}.txt",
        field="tingkat+organizer" if method == "multi" else "tingkat",
        method=method,
        model=DEFAULT_MODEL,
        prompt_tokens=prompt_eval_count,
        completion_tokens=eval_count,
        total_tokens=prompt_eval_count + eval_count,
        prompt_eval_duration_ns=prompt_eval_dur,
        eval_duration_ns=eval_dur,
        total_duration_ns=total_dur,
        tokens_per_second=round(tps, 1),
        prompt_version=PROMPT_VERSION if method == "multi" else "v4_bias",
        response=response,
        valid=True,
        expected=None,
        correct=None,
    )
    log_call(call_log, log_path)
    return response, ollama_data


def run_benchmark(limit: int | None = None):
    ner_pipe = load_ner_model()
    rows = load_csv(CSV_PATH)
    filename_to_row = {}
    for row in rows:
        fname = row.get("nama_file", "")
        stem = os.path.splitext(fname)[0]
        filename_to_row[stem] = row

    text_files = sorted(f for f in os.listdir(TEXTS_DIR) if f.endswith(".txt"))
    if limit:
        text_files = text_files[:limit]
    print(f"Loaded {len(rows)} GT rows, {len(text_files)} text files")
    print(f"Model: {DEFAULT_MODEL} | Exp5 variant C (multi-field for organizer-miss) | GT: {GT_VERSION}")

    run_dir = create_run_dir("llm_v5_exp5")
    calls_path = os.path.join(run_dir, "calls_multi.json")
    print(f"Output: {run_dir}")

    per_cert_rows = []
    all_hybrid_pp = []
    all_exp5 = []
    total_calls = 0
    miss_before = miss_after = miss_fixed = miss_total = 0
    multi_certs = 0

    for txt_file in tqdm(text_files, desc="Exp5"):
        stem, raw_text = read_text_file(os.path.join(TEXTS_DIR, txt_file))
        row = filename_to_row.get(stem)
        if row is None:
            continue
        expected_tingkat = normalize_gt_tingkat(row.get("tingkat", ""))
        gt_org = row.get("penyelenggara_kegiatan", "").strip()

        normalized_text = normalize_for_ner(raw_text)
        regex_fields = extract_certificate_fields(raw_text)
        try:
            entities = extract_entities(raw_text, ner_pipe)
            filtered = filter_signer_roles(entities, raw_text)
            ner_pp_fields = map_entities_to_fields(filtered, full_text=normalized_text)
        except Exception:
            ner_pp_fields = {}

        hybrid_pp = combine_hybrid(ner_pp_fields, regex_fields)
        org_v2 = extract_organizer_v2(raw_text)
        if org_v2:
            hybrid_pp["penyelenggara_kegiatan"] = ExtractedValue(org_v2, 0.84, "organizer_v2")

        known = {
            "nama_kegiatan_sertifikasi": "",
            "penyelenggara_kegiatan": org_v2 or "",
            "raw_role": "",
        }
        for field in ("nama_kegiatan_sertifikasi", "penyelenggara_kegiatan"):
            ev = hybrid_pp.get(field)
            if ev and ev.value:
                known[field] = ev.value
        ev = regex_fields.get("raw_role")
        if ev and ev.value:
            known["raw_role"] = ev.value

        hybrid_pp_result = evaluate_row(hybrid_pp, row)
        all_hybrid_pp.append(hybrid_pp_result)
        base_meta = hybrid_pp_result.get("_meta", {})
        row_data = {k: v for k, v in base_meta.items() if k != "raw_text"}
        row_data["filename"] = f"{stem}.txt"

        # Router (rule on): rule-routed -> tanpa call LLM.
        routed_value, routed_rule = route_tingkat_trace(raw_text, org_v2 or "")
        merged = dict(hybrid_pp)
        organizer_source = "pipeline"
        if routed_value is not None:
            merged["tingkat"] = ExtractedValue(routed_value, 0.99, "router_rule")
        else:
            miss = _organizer_is_miss(gt_org, org_v2)
            if miss:
                miss_total += 1
                prompt, _min = build_prompt_multi(raw_text, known)
                response, _ = _call(prompt, stem, "multi", row, calls_path, max_tokens=50)
                tingkat, llm_org = parse_multi_response(response)
                if tingkat:
                    merged["tingkat"] = ExtractedValue(tingkat, 0.85, "llm_multi")
                if llm_org:
                    merged["penyelenggara_kegiatan"] = ExtractedValue(llm_org, 0.85, "llm_multi")
                    organizer_source = "llm_multi"
                    multi_certs += 1
                total_calls += 1
            else:
                prompt, _min = build_prompt_tingkat_bias(raw_text, known)
                response, _ = _call(prompt, stem, "f_bias", row, calls_path, max_tokens=30)
                tingkat = validate_tingkat(response)
                if tingkat:
                    merged["tingkat"] = ExtractedValue(tingkat, 0.85, "llm_ollama")
                total_calls += 1

        eval_result = evaluate_row(merged, row)
        eval_result["_meta"] = {"filename": f"{stem}.txt"}
        all_exp5.append(eval_result)

        t = eval_result.get("tingkat", {})
        o = eval_result.get("penyelenggara_kegiatan", {})
        row_data["tingkat_expected"] = t.get("expected", "")
        row_data["tingkat_actual"] = t.get("actual", "")
        row_data["tingkat_exact"] = 1 if t.get("exact") else 0
        row_data["organizer_expected"] = o.get("expected", "")
        row_data["organizer_actual"] = o.get("actual", "")
        row_data["organizer_exact"] = 1 if o.get("exact") else 0
        row_data["organizer_source"] = organizer_source

        if _organizer_is_miss(gt_org, org_v2):
            miss_before += 1
            if o.get("exact") or o.get("fuzzy"):
                miss_after += 1
                if o.get("exact"):
                    miss_fixed += 1
            per_cert_rows.append(row_data)

    # Config + stats
    with open(os.path.join(run_dir, "config.json"), "w") as f:
        json.dump({
            "model": DEFAULT_MODEL,
            "prompt_version": PROMPT_VERSION,
            "gt_version": GT_VERSION,
            "csv_path": CSV_PATH,
            "texts_dir": TEXTS_DIR,
            "n_certs": N_CERTS,
            "variant": "C (multi-field hanya utk organizer-miss; oracle GT)",
        }, f, indent=2, ensure_ascii=False)

    summary_pp = aggregate_results(all_hybrid_pp)
    with open(os.path.join(run_dir, "summary_hybrid_pp.json"), "w") as f:
        json.dump(summary_pp, f, indent=2, default=str)
    summary_exp5 = aggregate_results(all_exp5)
    with open(os.path.join(run_dir, "summary_exp5.json"), "w") as f:
        json.dump(summary_exp5, f, indent=2, default=str)
    save_summary_json(summary_exp5, run_dir)

    ts = build_token_usage_summary(calls_path)
    if ts:
        with open(os.path.join(run_dir, "token_usage.json"), "w") as f:
            json.dump(ts, f, indent=2)

    with open(os.path.join(run_dir, "results.csv"), "w", newline="") as f:
        if per_cert_rows:
            writer = csv.DictWriter(f, fieldnames=list(per_cert_rows[0].keys()))
            writer.writeheader()
            writer.writerows(per_cert_rows)

    per_cert = ts.get("total_tokens", 0) / N_CERTS if ts else 0
    print("\n=== Hybrid + PP (baseline pipeline) ===")
    print_report(summary_pp)
    print("\n=== Exp5 variant C (multi-field, oracle miss-selection) ===")
    print_report(summary_exp5)
    print(f"\nTotal LLM calls: {total_calls} | tokens/cert (amortized): {per_cert:.0f}")
    if ts:
        print(f"  [tokens] calls={ts['total_calls']} total={ts['total_tokens']} "
              f"(prompt {ts['total_prompt_tokens']} / completion {ts['total_completion_tokens']})")
    print(f"\nOrganizer MISS set: {miss_before} cert (pipeline). "
          f"Setelah variant C: {miss_after} naik jadi exact/fuzzy, "
          f"{miss_fixed} jadi EXACT. Multi-field calls: {multi_certs}.")
    print(f"Organizer source: {sum(1 for r in per_cert_rows if r['organizer_source']=='llm_multi')} llm_multi "
          f"/ {sum(1 for r in per_cert_rows if r['organizer_source']=='pipeline')} pipeline")

    return summary_pp, summary_exp5, ts, total_calls


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run_benchmark(limit=args.limit)
