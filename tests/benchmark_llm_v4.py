"""Handoff v7 — stable benchmark for v4 experiments.

Fork of benchmark_llm_v3 with three additions:
  1. `_meta.filename` attached to eval results so mismatch reports carry names.
  2. Categorized mismatch taxonomy (see tests/mismatch_taxonomy.py).
  3. Pluggable organizer extraction via --organizer-variant (Phase 1 seam;
     'regex' = production extract_certificate_fields, 'phrase_v2' = experiment).

Runs hybrid+PP once per cert, then LLM tingkat via Variant A / Variant B.

Usage:
  uv run python -m tests.benchmark_llm_v4
  uv run python -m tests.benchmark_llm_v4 --limit 10
  uv run python -m tests.benchmark_llm_v4 --organizer-variant phrase_v2
"""

import argparse
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

from app.services.field_extractor import extract_certificate_fields, ExtractedValue
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
from tests.mismatch_taxonomy import classify, build_taxonomy_report
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
    save_xlsx,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.environ.get(
    "GT_CSV_PATH", os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat.csv")
)
TEXTS_DIR = os.environ.get(
    "GT_TEXTS_DIR",
    os.path.join(REPO_ROOT, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts"),
)
GT_VERSION = os.environ.get("GT_VERSION") or os.path.basename(CSV_PATH).replace(".csv", "")
BENCHMARK_PROMPT_VERSION = "v4_variants"

# Variant yang menjadi sumber taxonomy mismatch (ditetapkan eksplisit,
# bukan "variant terakhir yang diloop").
TAXONOMY_VARIANT = "e_hybrid"

# Total sertifikat dalam dataset — dipakai untuk menghitung token efektif
# per dokumen (amortized), bukan per-call.
N_CERTS = 74
from tests.llm_extractor_v3 import (
    PROMPT_VERSION,
    MINIMIZE_CONFIG,
    build_prompt_tingkat_context,
    build_prompt_tingkat_minimized,
)
from tests.llm_extractor_v4 import (
    build_prompt_tingkat_adaptive,
    build_prompt_tingkat_bias,
    build_prompt_tingkat_evidence,
    build_prompt_tingkat_hybrid,
    build_prompt_tingkat_mid,
    parse_evidence_response,
)
from tests.ocr_cleanup_v4 import dedup_lines

if "tingkat" not in ev_fw.EVAL_FIELDS:
    ev_fw.EVAL_FIELDS[:] = EVAL_FIELDS + ["tingkat"]

VARIANTS = {
    "a_context": {
        "builder": build_prompt_tingkat_context,
        "uses_text": False,
        "prompt_version": "v3_tingkat_only",
    },
    "b_minimized": {
        "builder": build_prompt_tingkat_minimized,
        "uses_text": True,
        "prompt_version": "v3_tingkat_only",
    },
    "c_adaptive": {
        "builder": build_prompt_tingkat_adaptive,
        "uses_text": True,
        "prompt_version": "v4_adaptive",
    },
    "d_mid": {
        "builder": build_prompt_tingkat_mid,
        "uses_text": True,
        "prompt_version": "v4_adaptive",
    },
    "e_hybrid": {
        "builder": build_prompt_tingkat_hybrid,
        "uses_text": True,
        "prompt_version": "v4_adaptive",
    },
    "f_bias": {
        "builder": build_prompt_tingkat_bias,
        "uses_text": True,
        "prompt_version": "v4_bias",
    },
    "g_evidence": {
        "builder": build_prompt_tingkat_evidence,
        "uses_text": True,
        "prompt_version": "v4_evidence",
        "parse_evidence": True,
    },
}

ORGANIZER_VARIANTS = ["regex", "phrase_v2"]


def normalize_gt_tingkat(value: str) -> str:
    return TINGKAT_GT_MAP.get(value.strip(), value.strip())


def _organizer_from_variant(raw_text: str, variant: str) -> dict:
    if variant == "phrase_v2":
        from tests.organizer_extractor_v2 import extract_organizer_v2
        value = extract_organizer_v2(raw_text)
        if value:
            return {"penyelenggara_kegiatan": ExtractedValue(value, 0.84, "organizer_v2")}
    return {}


def _known_fields(hybrid_pp: dict, regex_fields: dict) -> dict[str, str]:
    known = {
        "nama_kegiatan_sertifikasi": "",
        "penyelenggara_kegiatan": "",
        "raw_role": "",
    }
    ev = regex_fields.get("raw_role")
    if ev and ev.value:
        known["raw_role"] = ev.value
    for field in ("nama_kegiatan_sertifikasi", "penyelenggara_kegiatan"):
        ev = hybrid_pp.get(field)
        if ev and ev.value:
            known[field] = ev.value
    return known


def _call_tingkat(prompt: str, stem: str, method: str, row: dict, log_path: str, prompt_version: str = BENCHMARK_PROMPT_VERSION, parse_evidence: bool = False):
    response, ollama_data = call_ollama(prompt)
    if parse_evidence:
        _, clean_value = parse_evidence_response(response)
    else:
        clean_value = validate_tingkat(response)
    eval_count = ollama_data.get("eval_count", 0)
    prompt_eval_count = ollama_data.get("prompt_eval_count", 0)
    eval_dur = ollama_data.get("eval_duration", 0)
    prompt_eval_dur = ollama_data.get("prompt_eval_duration", 0)
    total_dur = ollama_data.get("total_duration", 0)
    tps = (eval_count / eval_dur * 1e9) if eval_dur > 0 else 0

    expected = normalize_gt_tingkat(row.get("tingkat", ""))
    call_log = TokenUsage(
        call_id=f"{stem}_tingkat_{method}",
        certificate=f"{stem}.txt",
        field="tingkat",
        method=method,
        model=DEFAULT_MODEL,
        prompt_tokens=prompt_eval_count,
        completion_tokens=eval_count,
        total_tokens=prompt_eval_count + eval_count,
        prompt_eval_duration_ns=prompt_eval_dur,
        eval_duration_ns=eval_dur,
        total_duration_ns=total_dur,
        tokens_per_second=round(tps, 1),
        prompt_version=prompt_version,
        response=response,
        valid=clean_value is not None,
        expected=expected or None,
        correct=(
            clean_value is not None and clean_value == expected
        ) if expected else None,
    )
    log_call(call_log, log_path)
    return clean_value


def run_benchmark(limit: int | None = None, organizer_variant: str = "regex", dedup: bool = False, router: str = "none"):
    assert organizer_variant in ORGANIZER_VARIANTS, organizer_variant
    assert router in ("none", "shadow", "on"), router
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
    print(f"Loaded {len(rows)} ground truth rows, {len(text_files)} text files")
    print(f"Model: {DEFAULT_MODEL} | Organizer: {organizer_variant} | Dedup: {dedup} | Router: {router} | Variants: {list(VARIANTS)}")

    run_dir = create_run_dir("llm_v4")
    calls_paths = {
        name: os.path.join(run_dir, f"calls_{name}.json") for name in VARIANTS
    }
    router_rows = []
    print(f"Output: {run_dir}")

    per_cert_rows = []
    all_hybrid_pp = []
    results_by_variant = {name: [] for name in VARIANTS}
    taxonomy_rows = []
    minimize_stats = []
    total_calls = 0

    for txt_file in tqdm(text_files, desc="Benchmarking"):
        stem, raw_text = read_text_file(os.path.join(TEXTS_DIR, txt_file))
        if dedup:
            raw_text = dedup_lines(raw_text)
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
            filtered = filter_signer_roles(entities, raw_text)
            ner_pp_fields = map_entities_to_fields(filtered, full_text=normalized_text)
        except Exception:
            ner_pp_fields = {}

        hybrid_pp = combine_hybrid(ner_pp_fields, regex_fields)
        hybrid_pp.update(_organizer_from_variant(raw_text, organizer_variant))
        known = _known_fields(hybrid_pp, regex_fields)

        hybrid_pp_result = evaluate_row(hybrid_pp, row)
        all_hybrid_pp.append(hybrid_pp_result)

        base_meta = hybrid_pp_result.get("_meta", {})
        row_data = {k: v for k, v in base_meta.items() if k != "raw_text"}
        row_data["filename"] = f"{stem}.txt"

        routed_value = None
        routed_rule = ""
        if router != "none":
            from tests.llm_router_v4 import route_tingkat_trace
            org = _organizer_from_variant(raw_text, "phrase_v2").get("penyelenggara_kegiatan")
            routed_value, routed_rule = route_tingkat_trace(raw_text, org.value if org else "")
            expected = normalize_gt_tingkat(row.get("tingkat", ""))
            router_rows.append({
                "certificate": f"{stem}.txt",
                "decision": routed_value or "",
                "rule": routed_rule,
                "expected": expected,
                "exact": routed_value is not None and routed_value == expected,
                "skipped_call": routed_value is not None and router == "on",
            })

        for name, spec in VARIANTS.items():
            if spec["uses_text"]:
                prompt, minimized = spec["builder"](raw_text, known)
                minimize_stats.append({
                    "certificate": f"{stem}.txt",
                    "chars_in": len(raw_text),
                    "chars_out": len(minimized),
                    "compression": (
                        1 - len(minimized) / len(raw_text)
                    ) if raw_text else 0,
                })
            else:
                prompt = spec["builder"](known)

            tingkat = None
            if routed_value is not None and router == "on":
                total_calls += 0
            else:
                tingkat = _call_tingkat(
                    prompt, stem, name, row, calls_paths[name],
                    prompt_version=spec["prompt_version"],
                    parse_evidence=spec.get("parse_evidence", False),
                )
                total_calls += 1

            merged = dict(hybrid_pp)
            if routed_value is not None and router == "on":
                merged["tingkat"] = ExtractedValue(routed_value, 0.99, "router_rule")
            elif tingkat:
                merged["tingkat"] = ExtractedValue(tingkat, 0.85, "llm_ollama")
            eval_result = evaluate_row(merged, row)
            eval_result["_meta"] = {"filename": f"{stem}.txt"}
            results_by_variant[name].append(eval_result)

            t_ev = eval_result.get("tingkat", {})
            row_data[f"{name}_tingkat_expected"] = t_ev.get("expected", "")
            row_data[f"{name}_tingkat_actual"] = t_ev.get("actual", "")
            row_data[f"{name}_tingkat_exact"] = 1 if t_ev.get("exact") else 0
            row_data[f"{name}_tingkat_fuzzy"] = 1 if t_ev.get("fuzzy") else 0

        per_cert_rows.append(row_data)

        # Taxonomy hanya dari variant pemenang yang ditetapkan eksplisit.
        taxonomy_result = results_by_variant[TAXONOMY_VARIANT][-1]
        for field in ("penyelenggara_kegiatan", "tingkat"):
            r = taxonomy_result.get(field, {})
            if not r or r.get("exact"):
                continue
            expected = r.get("expected", "")
            actual = r.get("actual")
            if not expected or expected == "-":
                continue
            taxonomy_rows.append({
                "filename": f"{stem}.txt",
                "field": field,
                "expected": expected,
                "actual": actual or "",
                "categories": classify(field, expected, actual, raw_text),
            })

    # Config + stats
    with open(os.path.join(run_dir, "config.json"), "w") as f:
        json.dump({
            "model": DEFAULT_MODEL,
            "benchmark_prompt_version": BENCHMARK_PROMPT_VERSION,
            "prompt_version": PROMPT_VERSION,
            "variants": {
                name: {"uses_text": spec["uses_text"], "prompt_version": spec["prompt_version"]}
                for name, spec in VARIANTS.items()
            },
            "taxonomy_variant": TAXONOMY_VARIANT,
            "organizer_variant": organizer_variant,
            "dedup": dedup,
            "router": router,
            "minimize_config": MINIMIZE_CONFIG,
            "csv_path": CSV_PATH,
            "texts_dir": TEXTS_DIR,
            "gt_version": GT_VERSION,
            "n_certs": N_CERTS,
        }, f, indent=2, ensure_ascii=False)
    with open(os.path.join(run_dir, "minimize_stats.json"), "w") as f:
        json.dump(minimize_stats, f, indent=2)

    if router_rows:
        router_path = os.path.join(run_dir, "router_decisions.json")
        with open(router_path, "w") as f:
            json.dump(router_rows, f, indent=2)
        decisions = [r for r in router_rows if r["decision"]]
        if decisions:
            prec = sum(1 for r in decisions if r["exact"]) / len(decisions)
            skipped = sum(1 for r in decisions if r["skipped_call"])
            print(f"Router decisions: {len(decisions)}/74 | precision {prec:.1%} | "
                  f"skipped LLM calls: {skipped} ({100*skipped/max(len(router_rows),1):.1f}%)")

    # Summaries
    summary_pp = aggregate_results(all_hybrid_pp)
    _save_summary(run_dir, summary_pp, "hybrid_pp")
    summaries = {"hybrid_pp": summary_pp}
    for name, results in results_by_variant.items():
        s = aggregate_results(results)
        summaries[name] = s
        _save_summary(run_dir, s, f"variant_{name}")

    best = summaries.get(TAXONOMY_VARIANT, summaries.get("b_minimized", summary_pp))
    save_summary_json(best, run_dir)
    save_mismatch_report(results_by_variant.get(TAXONOMY_VARIANT, []), run_dir, source=f"llm_v4_{TAXONOMY_VARIANT}")

    # Taxonomy artifacts
    taxonomy_path = os.path.join(run_dir, "mismatch_taxonomy.csv")
    with open(taxonomy_path, "w") as f:
        f.write("filename,field,expected,actual,categories\n")
        for r in taxonomy_rows:
            f.write(f"{r['filename']},{r['field']},{r['expected']},{r['actual']},{';'.join(r['categories'])}\n")
    with open(os.path.join(run_dir, "taxonomy_summary.json"), "w") as f:
        json.dump(build_taxonomy_report(taxonomy_rows), f, indent=2, ensure_ascii=False)

    # Token summaries
    token_summaries = {}
    for name in VARIANTS:
        ts = build_token_usage_summary(calls_paths[name])
        if ts:
            with open(os.path.join(run_dir, f"token_usage_{name}.json"), "w") as f:
                json.dump(ts, f, indent=2)
            token_summaries[name] = ts

    xlsx_path = os.path.join(run_dir, "results.xlsx")
    save_xlsx(per_cert_rows, xlsx_path)

    _write_report(run_dir, summaries, token_summaries, total_calls, taxonomy_rows)

    print("\n=== Hybrid + Post-Processing (baseline) ===")
    print_report(summary_pp)
    for name in VARIANTS:
        print(f"\n=== Variant {name.upper()} ===")
        print_report(summaries[name])
    print(f"\nTotal LLM calls: {total_calls}")
    for name, ts in token_summaries.items():
        print(f"  [{name}] calls={ts['total_calls']} tokens={ts['total_tokens']} "
              f"(prompt {ts['total_prompt_tokens']} / completion {ts['total_completion_tokens']})")
    print(f"\n=== Taxonomy ({TAXONOMY_VARIANT}) ===")
    report = build_taxonomy_report(taxonomy_rows)
    print(json.dumps(report["by_field"], indent=2, ensure_ascii=False))

    return summaries, token_summaries, report


def _save_summary(run_dir: str, summary: dict, mode: str):
    with open(os.path.join(run_dir, f"summary_{mode}.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)


def _write_report(run_dir: str, summaries: dict, token_summaries: dict, total_calls: int, taxonomy_rows: list):
    lines = ["# Handoff v7 — LLM v4 Benchmark\n"]
    lines.append(f"**Date:** {datetime.now().isoformat()}\n")
    lines.append(f"**Model:** {DEFAULT_MODEL}\n")
    lines.append(f"**Prompt version:** {BENCHMARK_PROMPT_VERSION}\n")
    lines.append(f"**GT version:** {GT_VERSION}\n")
    lines.append(f"**Run dir:** {os.path.basename(run_dir)}\n\n")

    fields = list(dict.fromkeys(ev_fw.EVAL_FIELDS + ["tingkat"]))
    lines.append("## Tingkat Exact Accuracy\n\n")
    lines.append("| Variant | Tingkat exact | MACRO exact | Eff. tokens/cert |\n")
    lines.append("|---------|--------------|-------------|------------------|\n")
    pp_macro = summaries["hybrid_pp"].get("macro_avg", {}).get("exact_acc", 0) * 100
    lines.append(f"| Hybrid+PP | 0.0% | {pp_macro:.1f}% | 0 |\n")
    for name in VARIANTS:
        s = summaries.get(name, {})
        t = s.get("tingkat", {}).get("exact_acc", 0) * 100
        m = s.get("macro_avg", {}).get("exact_acc", 0) * 100
        ts = token_summaries.get(name, {})
        # Token efektif per dokumen: total token di-amortisasi ke N_CERTS
        # (sertifikat yang di-route ke rule = 0 token).
        per_cert = ts.get("total_tokens", 0) / N_CERTS if ts else 0
        lines.append(f"| {name} | {t:.1f}% | {m:.1f}% | {per_cert:.0f} |\n")

    lines.append("\n## Per-field Exact Accuracy\n\n")
    lines.append("| Field | Hybrid+PP | " + " | ".join(v.upper() for v in VARIANTS) + " |\n")
    lines.append("|-------|--------" + "|---" * len(VARIANTS) + "|\n")
    for field in fields:
        pp = summaries["hybrid_pp"].get(field, {}).get("exact_acc", 0) * 100
        row = [f"| `{field}` | {pp:.1f}%"]
        for name in VARIANTS:
            v = summaries.get(name, {}).get(field, {}).get("exact_acc", 0) * 100
            row.append(f" {v:.1f}%")
        row.append(" |")
        lines.append(" ".join(row) + "\n")

    if taxonomy_rows:
        report = build_taxonomy_report(taxonomy_rows)
        lines.append("\n## Mismatch Taxonomy\n\n")
        lines.append("| Field | Category | Count |\n")
        lines.append("|-------|----------|------:|\n")
        for field, cats in report["by_field"].items():
            for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
                lines.append(f"| {field} | {cat} | {count} |\n")

    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write("".join(lines))
    print(f"\nReport saved to {run_dir}/report.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--organizer-variant", default="regex", choices=ORGANIZER_VARIANTS)
    parser.add_argument("--dedup", action="store_true")
    parser.add_argument("--router", default="none", choices=["none", "shadow", "on"])
    args = parser.parse_args()
    run_benchmark(limit=args.limit, organizer_variant=args.organizer_variant, dedup=args.dedup, router=args.router)
