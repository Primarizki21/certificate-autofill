"""Production-equivalent paired benchmark for V1 versus V2 Scope-Aware.

The runner reuses the production PDF -> PyMuPDF -> conditional OCR input path,
then evaluates the current V1 prompt and test-only V2 prompt against the same
raw text. Production code remains unchanged until an explicit promotion.

Outputs are immutable per B14: pass a new output directory for every run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.config import settings
from app.services.extraction_pipeline import run_extraction_pipeline
from app.services.field_extractor import ExtractedValue
from app.services.form_mapper import field_needs_review, map_fields_to_form
from app.services.gemini_extractor import (
    SYSTEM_INSTRUCTION as PRODUCTION_V1_SYSTEM_INSTRUCTION,
    USER_PROMPT_TEMPLATE as PRODUCTION_USER_PROMPT_TEMPLATE,
    normalize_llm_json,
)
from tests.benchmark_prompt_opt_v2_v3 import (
    V2_BASELINE_SYSTEM_INSTRUCTION,
    V2_BASELINE_USER_PROMPT_TEMPLATE,
    compute_field_confidence_and_review,
)
from tests.benchmark_production_input_matrix import (
    compute_paired_deltas,
    compute_variant_aggregate,
    evaluate_document_prediction,
    fallback_offline_extraction,
    load_manifest,
)
from tests.evaluation_framework import load_csv, resolve_pdf_path
from tests.gemini_client import GeminiClient, load_google_api_key
from tests.gemini_field_extractor import ALL_EVAL_FIELDS
from tests.v2_safety_review import is_optional_absence

VARIANTS = ("v1_production", "v2_scope_aware")
LITERAL_FIELDS = tuple(f for f in ALL_EVAL_FIELDS if f != "tingkat")
DEFAULT_GT_PATH = os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v9.csv")
DEFAULT_GT_DIR = os.path.join(REPO_ROOT, "Sertifikat_Ground_Truth")
DEFAULT_MANIFEST_PATH = os.path.join(REPO_ROOT, "tests", "layout_manifest.json")
DEFAULT_OUTPUT_DIR = os.path.join(
    REPO_ROOT, "docs", "experiments", "EXP-PROD-V2-SCOPE-001", "run_full_74"
)
DELIVERABLES = (
    "run_metadata.json",
    "results.json",
    "summary.json",
    "gate.json",
    "per_certificate.csv",
    "mismatches.csv",
    "summary.md",
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _assert_prompt_parity() -> None:
    """Ensure V1 benchmark request matches the current production prompt."""
    if PRODUCTION_USER_PROMPT_TEMPLATE != V2_BASELINE_USER_PROMPT_TEMPLATE:
        raise AssertionError(
            "Production V1 user template differs from benchmark baseline template."
        )
    if "Cakupan Sasaran Peserta" not in V2_BASELINE_SYSTEM_INSTRUCTION:
        raise AssertionError("V2 Scope-Aware prompt kehilangan aturan scope utama.")
    if "Jenjang Penyelenggara" not in V2_BASELINE_SYSTEM_INSTRUCTION:
        raise AssertionError("V2 Scope-Aware prompt kehilangan pembanding organizer.")


def _ensure_fresh_output(output_dir: Path) -> None:
    """Reject existing deliverables or non-empty output directories."""
    if output_dir.exists():
        existing = [name for name in DELIVERABLES if (output_dir / name).exists()]
        if existing or any(output_dir.iterdir()):
            found = existing or [p.name for p in output_dir.iterdir()]
            raise FileExistsError(
                "B14 Immutability Guard: output directory is not empty "
                f"({found}). Use a new isolated directory."
            )
    output_dir.mkdir(parents=True, exist_ok=True)


def _extract_production_input(pdf_bytes: bytes) -> tuple[str, str]:
    """Run the exact production input branch without making a Gemini call."""
    original = settings.enable_tesseract_gemini
    try:
        object.__setattr__(settings, "enable_tesseract_gemini", False)
        result = run_extraction_pipeline(
            pdf_bytes,
            tahun_akademik="2024/2025",
            bukti_fisik="Sertifikat",
        )
        return result.raw_text, result.parser_engine
    finally:
        object.__setattr__(settings, "enable_tesseract_gemini", original)


def _map_prediction(
    fields: dict[str, str | None],
    raw_text: str,
    source: str,
) -> dict[str, ExtractedValue]:
    """Adapt normalized LLM fields to the production form mapper contract."""
    extracted: dict[str, ExtractedValue] = {
        "full_text": ExtractedValue(raw_text, 1.0, "tesseract_raw"),
    }
    for field_name in (*ALL_EVAL_FIELDS, "raw_role"):
        value = fields.get(field_name)
        confidence = 0.90 if value else 0.0
        extracted[field_name] = ExtractedValue(value, confidence, source)
    return map_fields_to_form(
        extracted,
        tahun_akademik="2024/2025",
        bukti_fisik="Sertifikat",
    )


def _offline_prediction(raw_text: str) -> dict[str, ExtractedValue]:
    return map_fields_to_form(
        fallback_offline_extraction(raw_text),
        tahun_akademik="2024/2025",
        bukti_fisik="Sertifikat",
    )


def _call_single_pass(
    variant: str,
    raw_text: str,
    client: GeminiClient | None,
    model: str,
    skip_gemini: bool,
) -> tuple[dict[str, ExtractedValue], dict[str, Any]]:
    """Execute one V1/V2 call, preserving production fallback semantics."""
    if skip_gemini or client is None:
        return _offline_prediction(raw_text), {
            "status": "skipped_dry_run",
            "model": model,
            "latency_s": 0.0,
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "cached_tokens": 0,
            "thoughts_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_idr": 0.0,
            "calls_count": 0,
            "web_search_queries": [],
            "calls_details": [],
            "error": None,
            "error_fallback": False,
        }

    if variant == "v1_production":
        system_instruction = PRODUCTION_V1_SYSTEM_INSTRUCTION
        prompt_template = PRODUCTION_USER_PROMPT_TEMPLATE
        prompt_source = "production_v1"
    elif variant == "v2_scope_aware":
        system_instruction = V2_BASELINE_SYSTEM_INSTRUCTION
        prompt_template = V2_BASELINE_USER_PROMPT_TEMPLATE
        prompt_source = "v2_scope_aware"
    else:
        raise ValueError(f"Unknown variant: {variant}")

    prompt = prompt_template.format(raw_ocr_text=raw_text)
    response = client.generate_json(
        prompt=prompt,
        system_instruction=system_instruction,
        model=model,
        temperature=0.0,
        enable_grounding=False,
    )
    call_detail = {
        "stage": "single_pass",
        "variant": variant,
        "status": response.status,
        "prompt_tokens": response.prompt_tokens,
        "candidates_tokens": response.candidates_tokens,
        "cached_tokens": response.cached_tokens,
        "thoughts_tokens": response.thoughts_tokens,
        "total_tokens": response.total_tokens,
        "cost_usd": response.cost_usd,
        "cost_idr": response.cost_idr,
        "latency_s": response.latency_s,
        "web_search_queries": list(response.web_search_queries),
        "error": response.error_message,
    }
    meta = {
        "status": response.status,
        "model": response.model or model,
        "prompt_source": prompt_source,
        "prompt_tokens": response.prompt_tokens,
        "candidates_tokens": response.candidates_tokens,
        "cached_tokens": response.cached_tokens,
        "thoughts_tokens": response.thoughts_tokens,
        "total_tokens": response.total_tokens,
        "cost_usd": response.cost_usd,
        "cost_idr": response.cost_idr,
        "latency_s": response.latency_s,
        "calls_count": 1,
        "web_search_queries": list(response.web_search_queries),
        "calls_details": [call_detail],
        "error": response.error_message,
        "error_fallback": False,
    }

    if response.status != "success" or response.parsed_json is None:
        meta["error_fallback"] = True
        return _offline_prediction(raw_text), meta

    normalized = normalize_llm_json(response.parsed_json)
    return _map_prediction(normalized, raw_text, "gemini_llm"), meta


def _safety_metrics(
    rows: list[dict[str, Any]],
    production_confidence: bool,
) -> dict[str, Any]:
    """Measure review recall while ignoring valid optional absences."""
    cell_error_total = 0
    cell_flagged_error = 0
    cell_flagged_total = 0
    doc_error_total = 0
    doc_flagged_error = 0
    doc_flagged_total = 0
    ignored_optional_absences = 0

    for row in rows:
        doc_has_error = False
        doc_has_flag = False
        for field_name in ALL_EVAL_FIELDS:
            evaluation = row["evaluation"][field_name]
            if is_optional_absence(
                field_name,
                evaluation.get("gt"),
                evaluation.get("pred"),
            ):
                ignored_optional_absences += 1
                continue
            is_exact = bool(evaluation["exact"])
            value = evaluation.get("pred")
            if production_confidence:
                confidence = 0.90 if value and str(value).strip() else 0.0
                needs_review = field_needs_review(field_name, value, confidence)
            else:
                source = row.get("tingkat_source", "llm") if field_name == "tingkat" else "llm"
                _, needs_review = compute_field_confidence_and_review(
                    field_name, value, source
                )

            if not is_exact:
                cell_error_total += 1
                doc_has_error = True
            if needs_review:
                cell_flagged_total += 1
                doc_has_flag = True
                if not is_exact:
                    cell_flagged_error += 1

        if doc_has_error:
            doc_error_total += 1
            if doc_has_flag:
                doc_flagged_error += 1
        if doc_has_flag:
            doc_flagged_total += 1

    cell_recall = (
        cell_flagged_error / cell_error_total * 100.0 if cell_error_total else 100.0
    )
    cell_precision = (
        cell_flagged_error / cell_flagged_total * 100.0 if cell_flagged_total else 0.0
    )
    doc_recall = (
        doc_flagged_error / doc_error_total * 100.0 if doc_error_total else 100.0
    )
    doc_precision = (
        doc_flagged_error / doc_flagged_total * 100.0 if doc_flagged_total else 0.0
    )
    return {
        "mode": "production_fixed_0.90" if production_confidence else "legacy_calibrated",
        "ignored_optional_absences": ignored_optional_absences,
        "cell_level": {
            "total_errors": cell_error_total,
            "flagged_errors": cell_flagged_error,
            "total_flagged": cell_flagged_total,
            "recall_pct": round(cell_recall, 2),
            "precision_pct": round(cell_precision, 2),
        },
        "doc_level": {
            "total_errors": doc_error_total,
            "flagged_errors": doc_flagged_error,
            "total_flagged": doc_flagged_total,
            "recall_pct": round(doc_recall, 2),
            "precision_pct": round(doc_precision, 2),
        },
        "cell_review_recall_pct": round(cell_recall, 2),
        "cell_review_precision_pct": round(cell_precision, 2),
        "doc_review_recall_pct": round(doc_recall, 2),
        "doc_review_precision_pct": round(doc_precision, 2),
    }


def _gate_report(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    min_tingkat_gain: float,
) -> dict[str, Any]:
    """Apply accuracy, literal-field preservation, and safety gates."""
    baseline = compute_variant_aggregate(baseline_rows)
    candidate = compute_variant_aggregate(candidate_rows)
    paired = compute_paired_deltas(candidate_rows, baseline_rows)
    candidate_safety_legacy = _safety_metrics(candidate_rows, production_confidence=False)
    candidate_safety_production = _safety_metrics(candidate_rows, production_confidence=True)

    tingkat_delta = (
        candidate["per_field"]["tingkat"]["exact_pct"]
        - baseline["per_field"]["tingkat"]["exact_pct"]
    )
    field_deltas = {
        field_name: round(
            candidate["per_field"][field_name]["exact_pct"]
            - baseline["per_field"][field_name]["exact_pct"],
            2,
        )
        for field_name in ALL_EVAL_FIELDS
    }
    literal_field_gates = {
        field_name: candidate["per_field"][field_name]["exact_pct"]
        >= baseline["per_field"][field_name]["exact_pct"]
        for field_name in LITERAL_FIELDS
    }
    safety_gate_legacy = candidate_safety_legacy["cell_review_recall_pct"] >= 95.0
    safety_gate_production = candidate_safety_production["cell_review_recall_pct"] >= 95.0
    gates = {
        "tingkat_gain": {
            "baseline_exact_pct": baseline["per_field"]["tingkat"]["exact_pct"],
            "candidate_exact_pct": candidate["per_field"]["tingkat"]["exact_pct"],
            "delta_pct": round(tingkat_delta, 2),
            "minimum_delta_pct": min_tingkat_gain,
            "pass": tingkat_delta >= min_tingkat_gain,
        },
        "literal_field_preservation": {
            "deltas_pct": field_deltas,
            "per_field_pass": literal_field_gates,
            "pass": all(literal_field_gates.values()),
        },
        "safety_net_legacy_calibrated": {
            **candidate_safety_legacy,
            "minimum_cell_review_recall_pct": 95.0,
            "pass": safety_gate_legacy,
        },
        "safety_net_production_confidence": {
            **candidate_safety_production,
            "minimum_cell_review_recall_pct": 95.0,
            "pass": safety_gate_production,
        },
        "all_pass": bool(
            tingkat_delta >= min_tingkat_gain
            and all(literal_field_gates.values())
            and safety_gate_legacy
            and safety_gate_production
        ),
        "n_documents": len(candidate_rows),
        "paired_deltas": paired,
    }
    return {
        "baseline": baseline,
        "candidate": candidate,
        "gates": gates,
    }


def _write_per_certificate_csv(
    output_path: Path,
    rows_by_variant: dict[str, list[dict[str, Any]]],
) -> None:
    columns = [
        "variant",
        "stem",
        "filename",
        "doc_type",
        "parser_engine",
        "gemini_status",
        "error_fallback",
        "latency_s",
        "total_tokens",
        "prompt_tokens",
        "candidates_tokens",
        "cached_tokens",
        "thoughts_tokens",
        "cost_idr",
    ]
    for field_name in ALL_EVAL_FIELDS:
        columns.extend((f"{field_name}_pred", f"{field_name}_gt", f"{field_name}_match"))
    columns.extend(("exact_fields_count", "fuzzy_fields_count"))

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for variant, rows in rows_by_variant.items():
            for row in rows:
                record: dict[str, Any] = {
                    "variant": variant,
                    "stem": row["stem"],
                    "filename": row["filename"],
                    "doc_type": row["doc_type"],
                    "parser_engine": row["parser_engine"],
                    "gemini_status": row["call_meta"].get("status", ""),
                    "error_fallback": row["call_meta"].get("error_fallback", False),
                    "latency_s": row["call_meta"].get("latency_s", 0.0),
                    "total_tokens": row["call_meta"].get("total_tokens", 0),
                    "prompt_tokens": row["call_meta"].get("prompt_tokens", 0),
                    "candidates_tokens": row["call_meta"].get("candidates_tokens", 0),
                    "cached_tokens": row["call_meta"].get("cached_tokens", 0),
                    "thoughts_tokens": row["call_meta"].get("thoughts_tokens", 0),
                    "cost_idr": row["call_meta"].get("cost_idr", 0.0),
                    "exact_fields_count": row["summary"]["exact_fields"],
                    "fuzzy_fields_count": row["summary"]["fuzzy_fields"],
                }
                for field_name in ALL_EVAL_FIELDS:
                    evaluation = row["evaluation"][field_name]
                    record[f"{field_name}_pred"] = evaluation["pred"]
                    record[f"{field_name}_gt"] = evaluation["gt"]
                    record[f"{field_name}_match"] = (
                        "EXACT"
                        if evaluation["exact"]
                        else "FUZZY"
                        if evaluation["fuzzy"]
                        else "MISMATCH"
                    )
                writer.writerow(record)


def _write_mismatches_csv(
    output_path: Path,
    rows_by_variant: dict[str, list[dict[str, Any]]],
) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["variant", "stem", "doc_type", "field", "prediction", "ground_truth", "wer", "cer"]
        )
        for variant, rows in rows_by_variant.items():
            for row in rows:
                for field_name in ALL_EVAL_FIELDS:
                    evaluation = row["evaluation"][field_name]
                    if not evaluation["exact"]:
                        writer.writerow(
                            [
                                variant,
                                row["stem"],
                                row["doc_type"],
                                field_name,
                                evaluation["pred"],
                                evaluation["gt"],
                                evaluation["wer"],
                                evaluation["cer"],
                            ]
                        )


def _write_summary_md(
    output_path: Path,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    gate_report: dict[str, Any],
) -> None:
    lines = [
        "# V2 Scope-Aware Production-Equivalent Benchmark",
        "",
        f"- **Run**: `{metadata['run_id']}`",
        f"- **Git SHA**: `{metadata['git_sha']}`",
        f"- **Dataset**: `{metadata['gt_csv']}` ({metadata['n_documents']} PDF)",
        f"- **Model**: `{metadata['gemini_model']}`",
        "- **Input path**: production PyMuPDF + conditional OCR",
        "- **Grounding**: disabled; expected web queries `[]`",
        "",
        "## Macro Results",
        "",
        "| Variant | Framework exact | All-cells exact | Tingkat exact | Tokens/doc | Cost/doc IDR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        metrics = summary[variant]
        tokens = metrics["token_rollup"]["eff_tokens_per_doc"]
        cost = metrics["token_rollup"]["cost_per_doc_idr"]
        lines.append(
            f"| {variant} | {metrics['framework_5f']['exact_pct']}% | "
            f"{metrics['all_cells_6f']['exact_pct']}% | "
            f"{metrics['per_field']['tingkat']['exact_pct']}% | {tokens} | {cost} |"
        )

    lines.extend(
        [
            "",
            "## Per-field Exact Delta: V2 minus V1",
            "",
            "| Field | V1 | V2 | Delta |",
            "|---|---:|---:|---:|",
        ]
    )
    baseline = gate_report["baseline"]
    candidate = gate_report["candidate"]
    for field_name in ALL_EVAL_FIELDS:
        b = baseline["per_field"][field_name]["exact_pct"]
        c = candidate["per_field"][field_name]["exact_pct"]
        lines.append(f"| {field_name} | {b}% | {c}% | {round(c - b, 2)}pt |")

    gates = gate_report["gates"]
    lines.extend(
        [
            "",
            "## Gate Results",
            "",
            f"- Tingkat gain gate: **{'PASS' if gates['tingkat_gain']['pass'] else 'FAIL'}** "
            f"- Safety legacy calibrated: **{'PASS' if gates['safety_net_legacy_calibrated']['pass'] else 'FAIL'}** "
            f"(cell recall {gates['safety_net_legacy_calibrated']['cell_review_recall_pct']}%)",
            f"- Safety production confidence: **{'PASS' if gates['safety_net_production_confidence']['pass'] else 'FAIL'}** "
            f"(cell recall {gates['safety_net_production_confidence']['cell_review_recall_pct']}%)",
            f"- **Overall: {'PASS' if gates['all_pass'] else 'FAIL'}**",
            "",
            "## Limitations",
            "",
            "- Fresh source PDFs available in this checkout: v9 primary 74 documents.",
            "- Elzandi holdout has no corresponding source PDFs in this checkout; prior cached-text holdout results are not substituted here.",
            "- This runner does not promote or modify production configuration.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _token_rollup(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n_docs = len(rows)
    fields = (
        "prompt_tokens",
        "candidates_tokens",
        "cached_tokens",
        "thoughts_tokens",
        "total_tokens",
        "cost_usd",
        "cost_idr",
        "calls_count",
        "latency_s",
    )
    totals = {
        field: sum(float(row["call_meta"].get(field, 0) or 0) for row in rows)
        for field in fields
    }
    web_search_queries = [
        query
        for row in rows
        for query in row["call_meta"].get("web_search_queries", [])
    ]
    calls_details = [
        {
            "stem": row["stem"],
            **detail,
        }
        for row in rows
        for detail in row["call_meta"].get("calls_details", [])
    ]
    return {
        "total_calls": int(totals["calls_count"]),
        "prompt_tokens": int(totals["prompt_tokens"]),
        "candidates_tokens": int(totals["candidates_tokens"]),
        "cached_tokens": int(totals["cached_tokens"]),
        "thoughts_tokens": int(totals["thoughts_tokens"]),
        "total_tokens": int(totals["total_tokens"]),
        "eff_tokens_per_doc": round(totals["total_tokens"] / n_docs, 1) if n_docs else 0.0,
        "total_cost_usd": round(totals["cost_usd"], 6),
        "total_cost_idr": round(totals["cost_idr"], 2),
        "cost_per_doc_idr": round(totals["cost_idr"] / n_docs, 2) if n_docs else 0.0,
        "total_latency_s": round(totals["latency_s"], 4),
        "avg_latency_s": round(totals["latency_s"] / totals["calls_count"], 4)
        if totals["calls_count"]
        else 0.0,
        "web_search_queries": web_search_queries,
        "calls_details": calls_details,
    }


def run_benchmark(
    gt_csv: str = DEFAULT_GT_PATH,
    gt_dir: str = DEFAULT_GT_DIR,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    model: str | None = None,
    delay: float = 1.2,
    timeout_s: float = 30.0,
    limit: int | None = None,
    min_tingkat_gain: float = 10.0,
    skip_gemini: bool = False,
) -> dict[str, Any]:
    """Run paired V1/V2 evaluation on the production input path."""
    _assert_prompt_parity()
    out_path = Path(output_dir)
    _ensure_fresh_output(out_path)

    gt_rows = load_csv(gt_csv)
    if limit is None and len(gt_rows) != 74:
        raise ValueError(f"Frozen GT v9 harus berisi 74 baris, ditemukan {len(gt_rows)}.")
    if limit is not None:
        gt_rows = gt_rows[:limit]

    manifest = load_manifest(manifest_path)
    sources: list[dict[str, Any]] = []
    for row in gt_rows:
        resolved = resolve_pdf_path(row, gt_dir)
        if not resolved or not os.path.exists(resolved):
            raise FileNotFoundError(f"File sumber tidak ditemukan untuk satu baris GT: {row.get('nama_file', '')}")
        pdf_bytes = Path(resolved).read_bytes()
        stem = Path(resolved).stem
        sources.append(
            {
                "gt_row": row,
                "path": resolved,
                "bytes": pdf_bytes,
                "stem": stem,
                "filename": Path(resolved).name,
                "doc_type": manifest.get(stem, "unknown"),
                "pdf_sha256": sha256_bytes(pdf_bytes),
            }
        )

    effective_model = model or settings.google_gemini_model or "gemini-3.1-flash-lite"
    api_key = None if skip_gemini else load_google_api_key()
    if not skip_gemini and not api_key:
        raise RuntimeError("GOOGLE_API_KEY tidak ditemukan; gunakan --skip-gemini untuk dry run.")
    client = None
    if not skip_gemini:
        client = GeminiClient(
            api_key=api_key,
            default_model=effective_model,
            request_delay=delay,
            max_retries=0,
            timeout_s=timeout_s,
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"production_v2_scope_{timestamp}"
    metadata = {
        "campaign_id": "EXP-PROD-V2-CAMPAIGN-001",
        "run_id": run_id,
        "timestamp": timestamp,
        "git_sha": _git_sha(),
        "gt_csv": os.path.relpath(gt_csv, REPO_ROOT),
        "gt_dir": os.path.relpath(gt_dir, REPO_ROOT),
        "manifest_path": os.path.relpath(manifest_path, REPO_ROOT),
        "n_documents": len(sources),
        "gemini_model": effective_model,
        "skip_gemini": skip_gemini,
        "max_retries": 0,
        "pacing_delay_s": delay,
        "timeout_s": timeout_s,
        "grounding_enabled": False,
        "input_path": "production: pymupdf -> conditional_ocr -> prompt",
        "status": "STAGING_ONLY",
        "production_promotion": False,
        "prompt_hashes": {
            "v1_system": sha256_text(PRODUCTION_V1_SYSTEM_INSTRUCTION),
            "v1_user": sha256_text(PRODUCTION_USER_PROMPT_TEMPLATE),
            "v2_system": sha256_text(V2_BASELINE_SYSTEM_INSTRUCTION),
            "v2_user": sha256_text(V2_BASELINE_USER_PROMPT_TEMPLATE),
        },
        "source_pdf_sha256": {source["stem"]: source["pdf_sha256"] for source in sources},
    }
    (out_path / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    raw_dir = out_path / "raw_texts" / "production_conditional"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows_by_variant: dict[str, list[dict[str, Any]]] = {variant: [] for variant in VARIANTS}

    for index, source in enumerate(sources, start=1):
        raw_text, parser_engine = _extract_production_input(source["bytes"])
        raw_path = raw_dir / f"{source['stem']}.txt"
        raw_path.write_text(raw_text, encoding="utf-8")
        raw_hash = sha256_text(raw_text)

        for variant in VARIANTS:
            mapped, call_meta = _call_single_pass(
                variant=variant,
                raw_text=raw_text,
                client=client,
                model=effective_model,
                skip_gemini=skip_gemini,
            )
            evaluation = evaluate_document_prediction(mapped, source["gt_row"])
            exact_count = sum(1 for field_name in ALL_EVAL_FIELDS if evaluation[field_name]["exact"])
            fuzzy_count = sum(1 for field_name in ALL_EVAL_FIELDS if evaluation[field_name]["fuzzy"])
            rows_by_variant[variant].append(
                {
                    "stem": source["stem"],
                    "filename": source["filename"],
                    "doc_type": source["doc_type"],
                    "variant": variant,
                    "parser_engine": parser_engine,
                    "raw_text_sha256": raw_hash,
                    "tingkat_source": "llm",
                    "call_meta": call_meta,
                    "evaluation": evaluation,
                    "summary": {
                        "exact_fields": exact_count,
                        "fuzzy_fields": fuzzy_count,
                        "total_fields": len(ALL_EVAL_FIELDS),
                    },
                }
            )
            print(
                f"[{index:02d}/{len(sources):02d}] {variant} "
                f"doc_type={source['doc_type']} exact={exact_count}/6 "
                f"status={call_meta.get('status')}"
            )

    summaries: dict[str, Any] = {}
    for variant, rows in rows_by_variant.items():
        aggregate = compute_variant_aggregate(rows)
        aggregate["token_rollup"] = _token_rollup(rows)
        aggregate["safety_net_legacy_calibrated"] = _safety_metrics(rows, production_confidence=False)
        aggregate["safety_net_production_confidence"] = _safety_metrics(rows, production_confidence=True)
        summaries[variant] = aggregate

    gate_report = _gate_report(
        rows_by_variant["v1_production"],
        rows_by_variant["v2_scope_aware"],
        min_tingkat_gain=min_tingkat_gain,
    )
    results_payload = {
        "metadata": metadata,
        "variants": rows_by_variant,
    }
    summary_payload = {
        "metadata": metadata,
        "variants": summaries,
        "gates": gate_report["gates"],
    }
    (out_path / "results.json").write_text(
        json.dumps(results_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_path / "summary.json").write_text(
        json.dumps(summary_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_path / "gate.json").write_text(
        json.dumps(gate_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_per_certificate_csv(out_path / "per_certificate.csv", rows_by_variant)
    _write_mismatches_csv(out_path / "mismatches.csv", rows_by_variant)
    _write_summary_md(out_path / "summary.md", metadata, summaries, gate_report)
    print(f"Artefak tersimpan: {out_path}")
    print(f"Overall gate: {'PASS' if gate_report['gates']['all_pass'] else 'FAIL'}")
    return summary_payload


def _git_sha() -> str:
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Paired V1 versus V2 Scope-Aware production-equivalent benchmark."
    )
    parser.add_argument("--gt-csv", default=DEFAULT_GT_PATH)
    parser.add_argument("--gt-dir", default=DEFAULT_GT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default=None)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-tingkat-gain", type=float, default=10.0)
    parser.add_argument(
        "--skip-gemini",
        action="store_true",
        help="Dry run tanpa API; tetap menguji loading, input path, output, dan gate.",
    )
    args = parser.parse_args()
    run_benchmark(
        gt_csv=args.gt_csv,
        gt_dir=args.gt_dir,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        model=args.model,
        delay=args.delay,
        timeout_s=args.timeout_s,
        limit=args.limit,
        min_tingkat_gain=args.min_tingkat_gain,
        skip_gemini=args.skip_gemini,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
