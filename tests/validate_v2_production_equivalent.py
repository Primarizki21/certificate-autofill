"""Four-layer empirical proof for the V2 Scope-Aware production-equivalent run.

Layer 1 reports descriptive fixed-prediction holdout/bootstrap artifacts; it is
not an independent model-fitting cross-validation claim. Layer 2 sends mutated
and OCR-noisy versions through the V2 prompt. Layer 3 audits prompt and source
hardcoding. Layer 4 reports both legacy calibrated and current production
confidence.

The validator is test-only and never changes production configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from tests.benchmark_v2_production_equivalent import (
    _call_single_pass,
    _ensure_fresh_output,
)
from tests.benchmark_prompt_opt_v2_v3 import (
    V2_BASELINE_SYSTEM_INSTRUCTION,
    V2_BASELINE_USER_PROMPT_TEMPLATE,
)
from tests.benchmark_production_input_matrix import evaluate_document_prediction
from tests.evaluation_framework import load_csv
from tests.gemini_client import GeminiClient, load_google_api_key
from tests.gemini_field_extractor import ALL_EVAL_FIELDS
from tests.ood_probe import inject_noise, mutate
from tests.validate_gemini_4layer import run_anti_hardcoding_audit

MUTATION_DIAGNOSTIC_FIELDS = (
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
)
MUTATION_GATE_FIELDS = (
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
)
NOISE_LEVELS = (0.10, 0.25, 0.50)
PROOF_FILES = ("four_layer_proof.json", "four_layer_proof.md")


def _accuracy(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> float:
    total = len(rows) * len(fields)
    exact = sum(1 for row in rows for field_name in fields if row["evaluation"][field_name]["exact"])
    return round(exact / total * 100.0, 2) if total else 0.0

TOKEN_FIELDS = (
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


def _token_rollup(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist aggregate and per-call accounting without document text."""
    totals = {field_name: 0.0 for field_name in TOKEN_FIELDS}
    calls_details: list[dict[str, Any]] = []
    web_search_queries: list[str] = []
    for document_index, row in enumerate(rows, start=1):
        meta = row["call_meta"]
        for field_name in TOKEN_FIELDS:
            totals[field_name] += float(meta.get(field_name, 0) or 0)
        queries = list(meta.get("web_search_queries", []))
        web_search_queries.extend(queries)
        calls_details.append(
            {
                "document_index": document_index,
                "status": meta.get("status"),
                "prompt_tokens": int(meta.get("prompt_tokens", 0) or 0),
                "candidates_tokens": int(meta.get("candidates_tokens", 0) or 0),
                "cached_tokens": int(meta.get("cached_tokens", 0) or 0),
                "thoughts_tokens": int(meta.get("thoughts_tokens", 0) or 0),
                "total_tokens": int(meta.get("total_tokens", 0) or 0),
                "cost_usd": float(meta.get("cost_usd", 0) or 0),
                "cost_idr": float(meta.get("cost_idr", 0) or 0),
                "latency_s": float(meta.get("latency_s", 0) or 0),
                "web_search_queries": queries,
            }
        )
    return {
        "total_calls": int(totals["calls_count"]),
        "prompt_tokens": int(totals["prompt_tokens"]),
        "candidates_tokens": int(totals["candidates_tokens"]),
        "cached_tokens": int(totals["cached_tokens"]),
        "thoughts_tokens": int(totals["thoughts_tokens"]),
        "total_tokens": int(totals["total_tokens"]),
        "total_cost_usd": round(totals["cost_usd"], 6),
        "total_cost_idr": round(totals["cost_idr"], 2),
        "avg_latency_s": round(
            totals["latency_s"] / totals["calls_count"], 4
        ) if totals["calls_count"] else 0.0,
        "web_search_queries": web_search_queries,
        "calls_details": calls_details,
    }


def _evaluate_v2_text(
    raw_text: str,
    gt_row: dict[str, str],
    client: GeminiClient,
    model: str,
) -> dict[str, Any]:
    mapped, call_meta = _call_single_pass(
        variant="v2_scope_aware",
        raw_text=raw_text,
        client=client,
        model=model,
        skip_gemini=False,
    )
    return {
        "evaluation": evaluate_document_prediction(mapped, gt_row),
        "call_meta": call_meta,
    }


def _run_ood(
    base_rows: list[dict[str, Any]],
    gt_by_stem: dict[str, dict[str, str]],
    texts_dir: Path,
    client: GeminiClient,
    model: str,
) -> dict[str, Any]:
    raw_texts: dict[str, str] = {}
    for row in base_rows:
        text_path = texts_dir / f"{row['stem']}.txt"
        if not text_path.exists():
            raise FileNotFoundError(f"Raw text tidak ditemukan untuk stem {row['stem']}")
        raw_text = text_path.read_text(encoding="utf-8", errors="replace")
        if not raw_text.strip():
            raise ValueError(f"Raw text kosong untuk stem {row['stem']}")
        raw_texts[row["stem"]] = raw_text

    mutated_rows: list[dict[str, Any]] = []
    for row in base_rows:
        stem = row["stem"]
        mutated_rows.append(
            _evaluate_v2_text(mutate(raw_texts[stem]), gt_by_stem[stem], client, model)
        )

    baseline_gate_accuracy = _accuracy(base_rows, MUTATION_GATE_FIELDS)
    mutation_gate_accuracy = _accuracy(mutated_rows, MUTATION_GATE_FIELDS)
    baseline_diag_accuracy = _accuracy(base_rows, MUTATION_DIAGNOSTIC_FIELDS)
    mutation_diag_accuracy = _accuracy(mutated_rows, MUTATION_DIAGNOSTIC_FIELDS)
    gate_drop = round(baseline_gate_accuracy - mutation_gate_accuracy, 2)
    diagnostic_drop = round(baseline_diag_accuracy - mutation_diag_accuracy, 2)

    noise_runs: dict[str, Any] = {}
    rng = random.Random(42)
    for noise_level in NOISE_LEVELS:
        noisy_rows: list[dict[str, Any]] = []
        for row in base_rows:
            stem = row["stem"]
            noisy_rows.append(
                _evaluate_v2_text(
                    inject_noise(raw_texts[stem], noise_level, rng),
                    gt_by_stem[stem],
                    client,
                    model,
                )
            )
        accuracy = _accuracy(noisy_rows, ALL_EVAL_FIELDS)
        noise_runs[f"{int(noise_level * 100)}%"] = {
            "n_documents": len(noisy_rows),
            "all_cells_exact_pct": accuracy,
            "drop_from_clean_all_cells_pct": round(
                _accuracy(base_rows, ALL_EVAL_FIELDS) - accuracy, 2
            ),
            "total_calls": sum(
                int(row["call_meta"].get("calls_count", 0)) for row in noisy_rows
            ),
            "web_search_queries": sum(
                len(row["call_meta"].get("web_search_queries", [])) for row in noisy_rows
            ),
            "token_rollup": _token_rollup(noisy_rows),
        }

    return {
        "n_documents": len(base_rows),
        "mutation": {
            "diagnostic_fields": list(MUTATION_DIAGNOSTIC_FIELDS),
            "gate_fields": list(MUTATION_GATE_FIELDS),
            "baseline_accuracy_pct": baseline_gate_accuracy,
            "mutated_accuracy_pct": mutation_gate_accuracy,
            "drop_pct": gate_drop,
            "gate_threshold_drop_pct": 2.0,
            "gate_pass": gate_drop <= 2.0,
            "token_rollup": _token_rollup(mutated_rows),
            "diagnostic_all_free_fields_baseline_pct": baseline_diag_accuracy,
            "diagnostic_all_free_fields_mutated_pct": mutation_diag_accuracy,
            "diagnostic_drop_pct": diagnostic_drop,
            "note": (
                "Nama kegiatan dilaporkan sebagai diagnostik karena mutator juga "
                "mengganti nama event; GT asli tidak ikut dimutasi."
            ),
        },
        "noise": {
            "clean_all_cells_exact_pct": _accuracy(base_rows, ALL_EVAL_FIELDS),
            "levels": noise_runs,
        },
    }


def _load_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    summary_path = run_dir / "summary.json"
    results_path = run_dir / "results.json"
    if not summary_path.exists() or not results_path.exists():
        raise FileNotFoundError("summary.json dan results.json wajib tersedia sebelum proof.")
    return (
        json.loads(summary_path.read_text(encoding="utf-8")),
        json.loads(results_path.read_text(encoding="utf-8")),
    )


def run_proof(
    run_dir: str,
    gt_csv: str,
    model: str | None = None,
    delay: float = 1.2,
    timeout_s: float = 30.0,
    output_dir: str | None = None,
    source_run_dir: str | None = None,
    raw_text_dir: str | None = None,
) -> dict[str, Any]:
    """Run OOD and assemble four-layer proof for an existing paired run."""
    run_path = Path(run_dir)
    summary_payload, results_payload = _load_run(run_path)
    target_dir = Path(output_dir) if output_dir else run_path
    if target_dir == run_path:
        for name in PROOF_FILES:
            if (target_dir / name).exists():
                raise FileExistsError(
                    f"B14 Immutability Guard: {name} sudah ada di {target_dir}; "
                    "gunakan run/output directory baru."
                )
    else:
        _ensure_fresh_output(target_dir)

    candidate_rows = results_payload["variants"].get("v2_scope_aware", [])
    if not candidate_rows:
        raise ValueError("Run tidak memiliki hasil v2_scope_aware.")
    gt_rows = load_csv(gt_csv)
    if not gt_rows:
        raise ValueError(f"Ground truth kosong: {gt_csv}")
    gt_by_stem: dict[str, dict[str, str]] = {}
    for row in gt_rows:
        stem = Path(row["nama_file"]).stem
        if stem in gt_by_stem:
            raise ValueError(f"Ground truth memiliki stem duplikat: {stem}")
        gt_by_stem[stem] = row
    if "v9" in Path(gt_csv).name.lower() and len(candidate_rows) != 74:
        raise ValueError(
            "Proof GT v9 penuh membutuhkan 74 hasil kandidat; "
            f"ditemukan {len(candidate_rows)}."
        )
    missing_gt = [row["stem"] for row in candidate_rows if row["stem"] not in gt_by_stem]
    if missing_gt:
        raise ValueError(f"GT tidak lengkap untuk {len(missing_gt)} dokumen.")

    effective_model = model or summary_payload["metadata"].get(
        "gemini_model", "gemini-3.1-flash-lite"
    )
    api_key = load_google_api_key()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY tidak ditemukan untuk OOD live proof.")
    client = GeminiClient(
        api_key=api_key,
        default_model=effective_model,
        request_delay=delay,
        max_retries=0,
        timeout_s=timeout_s,
    )
    anti_hardcoding = run_anti_hardcoding_audit(
        V2_BASELINE_SYSTEM_INSTRUCTION,
        V2_BASELINE_USER_PROMPT_TEMPLATE,
        source_files=(
            Path(REPO_ROOT) / "tests" / "v2_title_boundary.py",
            Path(REPO_ROOT) / "tests" / "v2_organizer_boundary.py",
            Path(REPO_ROOT) / "tests" / "v2_safety_review.py",
        ),
    )
    source_path = (
        Path(source_run_dir)
        if source_run_dir
        else run_path
    )
    if not source_path.is_absolute():
        source_path = Path(REPO_ROOT) / source_path
    texts_path = (
        Path(raw_text_dir)
        if raw_text_dir
        else source_path / "raw_texts" / "production_conditional"
    )
    if not texts_path.is_absolute():
        texts_path = Path(REPO_ROOT) / texts_path
    ood = _run_ood(
        base_rows=candidate_rows,
        gt_by_stem=gt_by_stem,
        texts_dir=texts_path,
        client=client,
        model=effective_model,
    )
    candidate_summary = summary_payload["variants"]["v2_scope_aware"]
    safety_legacy = candidate_summary["safety_net_legacy_calibrated"]
    safety_production = candidate_summary["safety_net_production_confidence"]
    layer1 = {
        "status": "DESCRIPTIVE_FIXED_PIPELINE_HOLDOUT",
        "independent_model_fit_per_fold": False,
        "method": (
            "Paired-run 5-fold holdout dan bootstrap atas prediksi tetap; "
            "tidak ada fitting model independen per fold."
        ),
        "stratified_5fold_cv": candidate_summary["stratified_5fold_cv"],
        "bootstrap_ci": candidate_summary["bootstrap_ci"],
        "proof_artifact_present": True,
    }
    gates = {
        "layer_1_statistical_artifacts": False,
        "layer_2_mutation": bool(ood["mutation"]["gate_pass"]),
        "layer_3_anti_hardcoding": bool(anti_hardcoding["anti_hardcoding_pass"]),
        "layer_4_legacy_safety": bool(
            safety_legacy["cell_review_recall_pct"] >= 95.0
        ),
        "layer_4_production_safety": bool(
            safety_production["cell_review_recall_pct"] >= 95.0
        ),
    }
    gates["all_pass"] = all(gates.values())
    proof = {
        "metadata": {
            "campaign_id": "EXP-PROD-V2-CAMPAIGN-001",
            "run_dir": os.path.relpath(run_path, REPO_ROOT),
            "source_run_dir": os.path.relpath(source_path, REPO_ROOT),
            "raw_text_dir": os.path.relpath(texts_path, REPO_ROOT),
            "gt_csv": os.path.relpath(gt_csv, REPO_ROOT),
            "model": effective_model,
            "grounding_enabled": False,
            "n_documents": len(candidate_rows),
            "mutation_fields_gated": list(MUTATION_GATE_FIELDS),
            "noise_levels": [f"{int(level * 100)}%" for level in NOISE_LEVELS],
            "status": "STAGING_ONLY",
            "completeness": "INCOMPLETE" if not gates["all_pass"] else "COMPLETE",
            "production_promotion": False,
        },
        "layer_1_statistical": layer1,
        "layer_2_ood": ood,
        "layer_3_anti_hardcoding": anti_hardcoding,
        "layer_4_safety": {
            "legacy_calibrated": safety_legacy,
            "production_confidence": safety_production,
        },
        "gates": gates,
    }
    (target_dir / "four_layer_proof.json").write_text(
        json.dumps(proof, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_markdown(target_dir / "four_layer_proof.md", proof)
    print(f"Empirical proof tersimpan: {target_dir}")
    print(f"Overall four-layer gate: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return proof


def _write_markdown(path: Path, proof: dict[str, Any]) -> None:
    layer1 = proof["layer_1_statistical"]
    ood = proof["layer_2_ood"]
    layer3 = proof["layer_3_anti_hardcoding"]
    safety = proof["layer_4_safety"]
    gates = proof["gates"]
    lines = [
        "# Four-Layer Proof — V2 Scope-Aware",
        "",
        f"- Dataset: `{proof['metadata']['gt_csv']}` ({proof['metadata']['n_documents']} dokumen)",
        f"- Model: `{proof['metadata']['model']}`",
        "- Input: production PyMuPDF + conditional OCR",
        "- Grounding: disabled",
        "",
        "## Layer 1 — Statistical",
        "",
        "| Fold | N certs | MACRO exact |",
        "|---:|---:|---:|",
    ]
    for fold in layer1["stratified_5fold_cv"].get("folds", []):
        lines.append(f"| {fold['fold']} | {fold['n_certs']} | {fold['macro_exact_pct']}% |")
    lines.extend(
        [
            "",
            f"- Mean: {layer1['stratified_5fold_cv'].get('mean_exact_pct')}%",
            f"- Min fold: {layer1['stratified_5fold_cv'].get('min_fold_exact_pct')}%",
            f"- Bootstrap: {layer1['bootstrap_ci'].get('n_bootstraps')} resamples",
            f"- Bootstrap All-Cells CI: {layer1['bootstrap_ci'].get('all_cells_exact_95_ci')}",
            f"- Status: `{layer1['status']}`",
            f"- Independent model fit per fold: `{layer1['independent_model_fit_per_fold']}`",
            "",
            "## Layer 2 — OOD",
            "",
            "| Uji | Baseline | Pasca uji | Drop | Status |",
            "|---|---:|---:|---:|---:|",
            f"| Mutation gate fields | {ood['mutation']['baseline_accuracy_pct']}% | "
            f"{ood['mutation']['mutated_accuracy_pct']}% | {ood['mutation']['drop_pct']}pt | "
            f"{'PASS' if ood['mutation']['gate_pass'] else 'FAIL'} |",
        ]
    )
    for level, result in ood["noise"]["levels"].items():
        lines.append(
            f"| OCR noise {level} | {ood['noise']['clean_all_cells_exact_pct']}% | "
            f"{result['all_cells_exact_pct']}% | {result['drop_from_clean_all_cells_pct']}pt | recorded |"
        )
    mutation_rollup = ood["mutation"]["token_rollup"]
    lines.extend(
        [
            "",
            f"- Mutation token rollup: {mutation_rollup['total_calls']} calls; "
            f"prompt={mutation_rollup['prompt_tokens']}, candidates={mutation_rollup['candidates_tokens']}, "
            f"cached={mutation_rollup['cached_tokens']}, thoughts={mutation_rollup['thoughts_tokens']}, "
            f"total={mutation_rollup['total_tokens']}, cost=Rp{mutation_rollup['total_cost_idr']}",
            *[
                f"- OCR noise {level} token rollup: {result['token_rollup']['total_calls']} calls; "
                f"prompt={result['token_rollup']['prompt_tokens']}, "
                f"candidates={result['token_rollup']['candidates_tokens']}, "
                f"cached={result['token_rollup']['cached_tokens']}, "
                f"thoughts={result['token_rollup']['thoughts_tokens']}, "
                f"total={result['token_rollup']['total_tokens']}, "
                f"cost=Rp{result['token_rollup']['total_cost_idr']}"
                for level, result in ood["noise"]["levels"].items()
            ],
        ]
    )
    lines.extend(
        [
            "",
            "## Layer 3 — Structural Semantic Anchors",
            "",
            f"- Keywords audited: {layer3['audited_keywords_count']}",
            f"- Violations: {len(layer3['violations_found'])}",
            "| Mode | Cell review recall | Cell review precision | Status |",
            "|---|---:|---:|---:|",
            f"| Legacy calibrated | {safety['legacy_calibrated']['cell_review_recall_pct']}% | "
            f"{safety['legacy_calibrated']['cell_review_precision_pct']}% | "
            f"{'PASS' if gates['layer_4_legacy_safety'] else 'FAIL'} |",
            f"| Production confidence | {safety['production_confidence']['cell_review_recall_pct']}% | "
            f"{safety['production_confidence']['cell_review_precision_pct']}% | "
            f"{'PASS' if gates['layer_4_production_safety'] else 'FAIL'} |",
            "",
            "## Gate Summary",
            "",
            "| Layer | Status |",
            "|---|---:|",
        ]
    )
    for key, passed in gates.items():
        if key != "all_pass":
            lines.append(f"| {key} | **{'PASS' if passed else 'FAIL'}** |")
    lines.append(f"| **Overall** | **{'PASS' if gates['all_pass'] else 'FAIL'}** |")
    lines.extend(
        [
            "",
            "Catatan: mutation gate mengecualikan nomor dan organizer karena mutasi institusi "
            "mengubah jawaban literal yang benar. Nama kegiatan tetap dilaporkan sebagai "
            "diagnostik karena mutator mengganti nama event tanpa mengubah GT.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main() -> int:
    parser = argparse.ArgumentParser(description="Four-layer V2 Scope-Aware empirical proof")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--gt-csv", default=os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v9.csv"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--source-run-dir", default=None)
    parser.add_argument("--raw-text-dir", default=None)
    args = parser.parse_args()
    run_proof(
        run_dir=args.run_dir,
        gt_csv=args.gt_csv,
        model=args.model,
        delay=args.delay,
        timeout_s=args.timeout_s,
        output_dir=args.output_dir,
        source_run_dir=args.source_run_dir,
        raw_text_dir=args.raw_text_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
