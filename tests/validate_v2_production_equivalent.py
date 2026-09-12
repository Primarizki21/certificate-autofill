"""Four-layer empirical proof for the V2 Scope-Aware production-equivalent run.

Layer 1 reuses paired-run CV/bootstrap artifacts. Layer 2 sends mutated and
OCR-noisy versions through the V2 prompt. Layer 3 audits prompt hardcoding.
Layer 4 reports both legacy calibrated and current production confidence.

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
        raw_texts[row["stem"]] = text_path.read_text(encoding="utf-8", errors="replace")

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
    gt_by_stem = {Path(row["nama_file"]).stem: row for row in gt_rows}
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
    )
    ood = _run_ood(
        base_rows=candidate_rows,
        gt_by_stem=gt_by_stem,
        texts_dir=run_path / "raw_texts" / "production_conditional",
        client=client,
        model=effective_model,
    )
    candidate_summary = summary_payload["variants"]["v2_scope_aware"]
    safety_legacy = candidate_summary["safety_net_legacy_calibrated"]
    safety_production = candidate_summary["safety_net_production_confidence"]
    layer1 = {
        "stratified_5fold_cv": candidate_summary["stratified_5fold_cv"],
        "bootstrap_ci": candidate_summary["bootstrap_ci"],
        "proof_artifact_present": True,
    }
    gates = {
        "layer_1_statistical_artifacts": bool(
            layer1["stratified_5fold_cv"].get("k_folds") == 5
            and layer1["bootstrap_ci"].get("n_bootstraps") == 1000
        ),
        "layer_2_mutation": bool(ood["mutation"]["gate_pass"]),
        "layer_3_anti_hardcoding": bool(anti_hardcoding["anti_hardcoding_pass"]),
        "layer_4_legacy_safety": bool(safety_legacy["review_recall_pct"] >= 95.0),
        "layer_4_production_safety": bool(safety_production["review_recall_pct"] >= 95.0),
    }
    gates["all_pass"] = all(gates.values())
    proof = {
        "metadata": {
            "run_dir": os.path.relpath(run_path, REPO_ROOT),
            "gt_csv": os.path.relpath(gt_csv, REPO_ROOT),
            "model": effective_model,
            "grounding_enabled": False,
            "n_documents": len(candidate_rows),
            "mutation_fields_gated": list(MUTATION_GATE_FIELDS),
            "noise_levels": [f"{int(level * 100)}%" for level in NOISE_LEVELS],
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
    lines.extend(
        [
            "",
            "## Layer 3 — Structural Semantic Anchors",
            "",
            f"- Keywords audited: {layer3['audited_keywords_count']}",
            f"- Violations: {len(layer3['violations_found'])}",
            f"- Status: **{'PASS' if layer3['anti_hardcoding_pass'] else 'FAIL'}**",
            "",
            "## Layer 4 — Safety Net",
            "",
            "| Mode | Review recall | Review precision | Status |",
            "|---|---:|---:|---:|",
            f"| Legacy calibrated | {safety['legacy_calibrated']['review_recall_pct']}% | "
            f"{safety['legacy_calibrated']['review_precision_pct']}% | "
            f"{'PASS' if gates['layer_4_legacy_safety'] else 'FAIL'} |",
            f"| Production confidence | {safety['production_confidence']['review_recall_pct']}% | "
            f"{safety['production_confidence']['review_precision_pct']}% | "
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
    args = parser.parse_args()
    run_proof(
        run_dir=args.run_dir,
        gt_csv=args.gt_csv,
        model=args.model,
        delay=args.delay,
        timeout_s=args.timeout_s,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
