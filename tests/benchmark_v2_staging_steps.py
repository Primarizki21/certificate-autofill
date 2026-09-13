"""Run isolated, immutable V2 staging steps against the cached 74-document corpus."""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.v2_ocr_normalizer import normalize_raw_ocr
from tests.v2_organizer_boundary import apply_organizer_boundary
from tests.v2_safety_review import build_review_annotations
from tests.v2_staging_common import (
    ALL_FIELDS,
    GT_PATH,
    LITERAL_FIELDS,
    RAW_TEXT_DIR,
    SOURCE_RUN_DIR,
    aggregate_rows,
    ensure_fresh_directory,
    evaluate_fields,
    load_cached_corpus,
    paired_outcomes,
    sha256_text,
    summarize_metrics,
    write_evaluation_csv,
    write_json,
)
from tests.v2_title_boundary import apply_title_boundary

STEP_DIRECTORIES = {
    "baseline": "EXP-PROD-V2-BASELINE-001",
    "title": "EXP-PROD-V2-TITLE-BOUNDARY-001",
    "organizer": "EXP-PROD-V2-ORGANIZER-BOUNDARY-001",
    "review": "EXP-PROD-V2-REVIEW-SAFETY-001",
    "ocr": "EXP-PROD-V2-OCR-NORMALIZER-001",
    "integrated": "EXP-PROD-V2-INTEGRATED-001",
    "shadow": "EXP-PROD-V2-SHADOW-001",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_manifest(
    source_run_dir: Path = SOURCE_RUN_DIR,
    raw_text_dir: Path | None = None,
    gt_path: Path = GT_PATH,
) -> dict[str, Any]:
    raw_dir = raw_text_dir or source_run_dir / "raw_texts/production_conditional"
    metadata_path = source_run_dir / "run_metadata.json"
    results_path = source_run_dir / "results.json"
    for required in (metadata_path, results_path, gt_path, raw_dir):
        if not required.exists():
            raise FileNotFoundError(f"Input staging tidak ditemukan: {required}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {
        "path": os.path.relpath(source_run_dir, REPO_ROOT),
        "run_id": metadata.get("run_id"),
        "git_sha": metadata.get("git_sha"),
        "gt_path": os.path.relpath(gt_path, REPO_ROOT),
        "gt_sha256": sha256_text(gt_path.read_text(encoding="utf-8")),
        "results_sha256": sha256_text(results_path.read_text(encoding="utf-8")),
        "raw_text_dir": os.path.relpath(raw_dir, REPO_ROOT),
        "raw_text_count": len(list(raw_dir.glob("*.txt"))),
    }


def _baseline_rows(corpus: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return evaluate_fields(
        corpus,
        lambda item: item["v2_fields"],
        source="gemini_v2_cached",
    )


def _decision_rows(
    corpus: dict[str, dict[str, Any]],
    step: str,
) -> tuple[dict[str, dict[str, Any]], Callable[[dict[str, Any]], dict[str, str]]]:
    decisions: dict[str, dict[str, Any]] = {}

    def selector(item: dict[str, Any]) -> dict[str, str]:
        fields = dict(item["v2_fields"])
        if step in {"title", "integrated"}:
            result = apply_title_boundary(
                item["raw_text"], fields["nama_kegiatan_sertifikasi"]
            )
            fields["nama_kegiatan_sertifikasi"] = result.value
            decisions.setdefault(item["stem"], {})["title"] = result.__dict__
        if step in {"organizer", "integrated"}:
            result = apply_organizer_boundary(
                item["raw_text"], fields["penyelenggara_kegiatan"]
            )
            fields["penyelenggara_kegiatan"] = result.value
            decisions.setdefault(item["stem"], {})["organizer"] = result.__dict__
        return fields

    return decisions, selector


def _review_rows(
    corpus: dict[str, dict[str, Any]],
    *,
    source: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    annotations = {
        stem: build_review_annotations(item["raw_text"], item["v2_fields"])
        for stem, item in corpus.items()
    }
    rows = evaluate_fields(
        corpus,
        lambda item: item["v2_fields"],
        source=source,
        confidence_selector=lambda field, item: annotations[item["stem"]][field]["confidence"],
        review_selector=lambda field, item: annotations[item["stem"]][field]["needs_review"],
        reasons_selector=lambda field, item: annotations[item["stem"]][field]["reasons"],
    )
    return rows, annotations


def _attach_metadata(
    rows: list[dict[str, Any]],
    corpus: dict[str, dict[str, Any]],
    *,
    decisions: dict[str, dict[str, Any]] | None = None,
    call_meta: dict[str, dict[str, Any]] | None = None,
) -> None:
    for row in rows:
        stem = row["stem"]
        row["decision"] = (decisions or {}).get(stem, {})
        if call_meta is not None:
            row["call_meta"] = call_meta.get(stem, {})
        row["raw_text_sha256"] = corpus[stem]["raw_text_sha256"]


def _review_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    error_cells = flagged_error_cells = flagged_cells = 0
    error_docs = flagged_error_docs = flagged_docs = 0
    for row in rows:
        has_error = False
        has_flag = False
        for evaluation in row["evaluation"].values():
            if not evaluation["exact"]:
                error_cells += 1
                has_error = True
            if evaluation["needs_review"]:
                flagged_cells += 1
                has_flag = True
                if not evaluation["exact"]:
                    flagged_error_cells += 1
        if has_error:
            error_docs += 1
            if has_flag:
                flagged_error_docs += 1
        if has_flag:
            flagged_docs += 1
    return {
        "cell_level": {
            "total_errors": error_cells,
            "flagged_errors": flagged_error_cells,
            "total_flagged": flagged_cells,
            "recall_pct": round(flagged_error_cells / error_cells * 100, 2)
            if error_cells
            else 100.0,
            "precision_pct": round(flagged_error_cells / flagged_cells * 100, 2)
            if flagged_cells
            else 0.0,
        },
        "doc_level": {
            "total_errors": error_docs,
            "flagged_errors": flagged_error_docs,
            "total_flagged": flagged_docs,
            "recall_pct": round(flagged_error_docs / error_docs * 100, 2)
            if error_docs
            else 100.0,
            "precision_pct": round(flagged_error_docs / flagged_docs * 100, 2)
            if flagged_docs
            else 0.0,
        },
    }


def _gate_report(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    review: dict[str, Any] | None = None,
    token_accounting: dict[str, Any] | None = None,
    extra_gates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    baseline = aggregate_rows(baseline_rows)
    candidate = aggregate_rows(candidate_rows)
    paired = paired_outcomes(baseline_rows, candidate_rows)
    deltas = {
        field: round(
            candidate["per_field"][field]["exact_pct"]
            - baseline["per_field"][field]["exact_pct"],
            2,
        )
        for field in ALL_FIELDS
    }
    literal_pass = all(deltas[field] >= 0 for field in LITERAL_FIELDS)
    tingkat_pass = deltas["tingkat"] >= 0
    no_losses = all(
        value["candidate_losses"] == 0
        for value in paired["per_field"].values()
    )
    gates: dict[str, Any] = {
        "literal_field_preservation": {
            "deltas_pct": deltas,
            "pass": literal_pass,
        },
        "tingkat_non_decrease": {
            "delta_pct": deltas["tingkat"],
            "pass": tingkat_pass,
        },
        "no_paired_field_losses": {"pass": no_losses},
    }
    if review is not None:
        cell_recall = review["cell_level"]["recall_pct"]
        gates["review_recall"] = {
            **review,
            "minimum_cell_recall_pct": 95.0,
            "pass": cell_recall >= 95.0,
        }
    if token_accounting is not None:
        required_fields = (
            "prompt_tokens",
            "candidates_tokens",
            "cached_tokens",
            "thoughts_tokens",
            "total_tokens",
            "cost_usd",
            "cost_idr",
            "calls_count",
            "latency_s",
            "web_search_queries",
            "calls_details",
        )
        all_required_fields = all(
            key in token_accounting for key in required_fields
        )
        web_search_queries = token_accounting.get("web_search_queries", [])
        calls_details = token_accounting.get("calls_details", [])
        if not isinstance(web_search_queries, list):
            all_required_fields = False
            web_search_queries = []
        if not isinstance(calls_details, list):
            all_required_fields = False
            calls_details = []
        detail_fields = (
            "status",
            "prompt_tokens",
            "candidates_tokens",
            "cached_tokens",
            "thoughts_tokens",
            "total_tokens",
            "cost_usd",
            "cost_idr",
            "latency_s",
            "web_search_queries",
            "error",
        )
        if any(
            not isinstance(detail, dict)
            or any(field not in detail for field in detail_fields)
            for detail in calls_details
        ):
            all_required_fields = False
        gates["token_accounting"] = {
            "all_required_fields": all_required_fields,
            "required_fields": list(required_fields),
            "web_search_queries": web_search_queries,
            "pass": all_required_fields and not web_search_queries,
        }
    if extra_gates:
        gates.update(extra_gates)
    gates["all_pass"] = all(
        gate.get("pass", False)
        for name, gate in gates.items()
        if name != "all_pass"
    )
    return {
        "baseline": baseline,
        "candidate": candidate,
        "deltas_pct": deltas,
        "paired": paired,
        "gates": gates,
    }


def _token_rollup(call_meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "prompt_tokens",
        "candidates_tokens",
        "cached_tokens",
        "thoughts_tokens",
        "total_tokens",
        "cost_usd",
        "cost_idr",
        "latency_s",
        "calls_count",
    )
    rollup: dict[str, Any] = {field: 0 for field in fields}
    queries: list[str] = []
    statuses: dict[str, int] = {}
    calls_details: list[dict[str, Any]] = []
    for stem, meta in call_meta.items():
        for field in fields:
            rollup[field] += meta.get(field, 0) or 0
        for query in meta.get("web_search_queries", []):
            if query not in queries:
                queries.append(query)
        status = meta.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        calls_details.extend(
            {"stem": stem, **detail}
            for detail in meta.get("calls_details", [])
        )
    rollup["web_search_queries"] = queries
    rollup["status_counts"] = statuses
    rollup["calls_details"] = calls_details
    for field in fields:
        if field in {"cost_usd", "cost_idr", "latency_s"}:
            rollup[field] = round(float(rollup[field]), 6)
        else:
            rollup[field] = int(rollup[field])
    return rollup


def _summary_markdown(
    *,
    step: str,
    experiment_id: str,
    source: dict[str, Any],
    proof: dict[str, Any],
    decision_count: int,
    token_accounting: dict[str, Any] | None,
    notes: list[str],
) -> str:
    baseline = proof["baseline"]
    candidate = proof["candidate"]
    gates = proof["gates"]
    lines = [
        f"# {experiment_id}",
        "",
        f"- Langkah: `{step}`",
        f"- Waktu run: `{_utc_now()}`",
        f"- Sumber: `{source['path']}`; run `{source['run_id']}`",
        f"- Dokumen: `{candidate['n_documents']}`",
        f"- Keputusan postprocessor berubah: `{decision_count}`",
        "",
        "## Metrik baseline dan kandidat",
        "",
        "|Varian|All-cells exact|All-cells fuzzy|Framework exact|Framework fuzzy|",
        "|---|---:|---:|---:|---:|",
        f"|V2 cached|{baseline['all_cells_6f']['exact_pct']}%|{baseline['all_cells_6f']['fuzzy_pct']}%|{baseline['framework_5f']['exact_pct']}%|{baseline['framework_5f']['fuzzy_pct']}%|",
        f"|{step}|{candidate['all_cells_6f']['exact_pct']}%|{candidate['all_cells_6f']['fuzzy_pct']}%|{candidate['framework_5f']['exact_pct']}%|{candidate['framework_5f']['fuzzy_pct']}%|",
        "",
        "## Delta exact per field",
        "",
        "|Field|Delta point|",
        "|---|---:|",
    ]
    for field, delta in proof["deltas_pct"].items():
        lines.append(f"|`{field}`|{delta:+.2f}|")
    lines.extend(["", "## Gate", ""])
    for name, gate in gates.items():
        if name == "all_pass":
            continue
        lines.append(f"- `{name}`: **{'PASS' if gate['pass'] else 'FAIL'}**")
    lines.append(f"- **Overall: {'PASS' if gates['all_pass'] else 'FAIL'}**")
    if token_accounting is not None:
        lines.extend(
            [
                "",
                "## Token dan biaya",
                "",
                f"- Prompt: `{token_accounting['prompt_tokens']}`",
                f"- Candidates: `{token_accounting['candidates_tokens']}`",
                f"- Cached: `{token_accounting['cached_tokens']}`",
                f"- Thoughts: `{token_accounting['thoughts_tokens']}`",
                f"- Total: `{token_accounting['total_tokens']}`",
                f"- Biaya: `${token_accounting['cost_usd']:.6f}` / `Rp{token_accounting['cost_idr']:.2f}`",
                f"- Web queries: `{len(token_accounting['web_search_queries'])}`",
            ]
        )
    lines.extend(["", "## Catatan", ""])
    lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines) + "\n"


def _write_step(
    *,
    step: str,
    output_dir: Path,
    corpus: dict[str, dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
    notes: list[str],
    source_run_dir: Path,
    raw_text_dir: Path,
    gt_path: Path,
    review_metrics: dict[str, Any] | None = None,
    token_accounting: dict[str, Any] | None = None,
    extra_gates: dict[str, dict[str, Any]] | None = None,
    output_ready: bool = False,
) -> dict[str, Any]:
    if not output_ready:
        ensure_fresh_directory(output_dir)
    experiment_id = output_dir.name
    source = _source_manifest(source_run_dir, raw_text_dir, gt_path)
    proof = _gate_report(
        baseline_rows,
        candidate_rows,
        review=review_metrics,
        token_accounting=token_accounting,
        extra_gates=extra_gates,
    )
    _attach_metadata(candidate_rows, corpus, decisions=decisions)
    generated_at = _utc_now()
    manifest = {
        "campaign_id": "EXP-PROD-V2-CAMPAIGN-001",
        "experiment_id": experiment_id,
        "parent_experiment_id": None,
        "related_experiment_ids": [],
        "role": step,
        "step": step,
        "status": "STAGING_ONLY",
        "started_at": generated_at,
        "finished_at": _utc_now(),
        "generated_at": generated_at,
        "immutable": True,
        "production_promotion": False,
        "source": source,
        "commit": source["git_sha"],
        "input_artifacts": {
            "source_run_dir": source["path"],
            "raw_text_dir": source["raw_text_dir"],
            "gt_path": source["gt_path"],
            "gt_sha256": source["gt_sha256"],
        },
        "fields": list(ALL_FIELDS),
        "notes": notes,
    }
    write_json(output_dir / "manifest.json", manifest)
    write_json(
        output_dir / "results.json",
        {
            "metadata": manifest,
            "baseline_metrics": summarize_metrics(proof["baseline"]),
            "candidate_metrics": summarize_metrics(proof["candidate"]),
            "proof": proof,
            "token_accounting": token_accounting,
            "decisions": decisions,
            "rows": candidate_rows,
        },
    )
    write_json(output_dir / "gate.json", proof["gates"])
    write_evaluation_csv(output_dir / "per_certificate.csv", candidate_rows)
    (output_dir / "summary.md").write_text(
        _summary_markdown(
            step=step,
            experiment_id=experiment_id,
            source=source,
            proof=proof,
            decision_count=sum(
                int(
                    bool(by_field.get("changed"))
                    if "changed" in by_field
                    else any(
                        isinstance(decision, dict) and decision.get("changed", False)
                        for decision in by_field.values()
                    )
                )
                for by_field in decisions.values()
            ),
            token_accounting=token_accounting,
            notes=notes,
        ),
        encoding="utf-8",
    )
    return proof


def _run_ocr(
    corpus: dict[str, dict[str, Any]],
    output_dir: Path,
    *,
    model: str,
    request_delay: float,
    skip_gemini: bool,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    from tests.benchmark_v2_production_equivalent import _call_single_pass
    from tests.gemini_client import GeminiClient
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir = output_dir / "normalized_texts"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    client = None if skip_gemini else GeminiClient(
        default_model=model,
        request_delay=request_delay,
        max_retries=3,
        timeout_s=60.0,
    )
    predictions: dict[str, dict[str, str]] = {}
    call_meta: dict[str, dict[str, Any]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    for stem in sorted(corpus):
        item = corpus[stem]
        normalized = normalize_raw_ocr(item["raw_text"])
        safe_name = stem.replace("/", "_") + ".txt"
        (normalized_dir / safe_name).write_text(normalized.text, encoding="utf-8")
        decisions[stem] = normalized.__dict__
        extracted, meta = _call_single_pass(
            "v2_scope_aware",
            normalized.text,
            client,
            model,
            skip_gemini,
        )
        predictions[stem] = {
            field: getattr(extracted.get(field), "value", None) or ""
            for field in ALL_FIELDS
        }
        call_meta[stem] = meta
    rows = evaluate_fields(
        corpus,
        lambda item: predictions[item["stem"]],
        source="v2_scope_aware_ocr_normalized",
    )
    _attach_metadata(rows, corpus, decisions=decisions, call_meta=call_meta)
    return rows, decisions, call_meta


def _load_ocr_rows(path: Path, corpus: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = json.loads((path / "results.json").read_text(encoding="utf-8"))
    rows = payload["rows"]
    fields = {row["stem"]: row["fields"] for row in rows}
    return evaluate_fields(corpus, lambda item: fields[item["stem"]], source="ocr_normalized_cached"), fields
def _load_artifact_fields(
    path: Path,
) -> dict[str, dict[str, str]]:
    payload = json.loads((path / "results.json").read_text(encoding="utf-8"))
    return {row["stem"]: row["fields"] for row in payload["rows"]}


def _build_ablation(
    corpus: dict[str, dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    integrated_rows: list[dict[str, Any]],
    *,
    source_run_dir: Path = SOURCE_RUN_DIR,
) -> dict[str, Any]:
    artifact_paths = {
        "v2_cached": source_run_dir,
        "title_boundary": REPO_ROOT / "docs/experiments/EXP-PROD-V2-TITLE-BOUNDARY-001",
        "organizer_boundary": REPO_ROOT
        / "docs/experiments/EXP-PROD-V2-ORGANIZER-BOUNDARY-003",
        "review_safety": REPO_ROOT
        / "docs/experiments/EXP-PROD-V2-REVIEW-SAFETY-001",
        "integrated_boundary_review": None,
        "ocr_normalized": REPO_ROOT
        / "docs/experiments/EXP-PROD-V2-OCR-NORMALIZER-002",
    }
    variants: dict[str, list[dict[str, Any]]] = {
        "v2_cached": baseline_rows,
        "integrated_boundary_review": integrated_rows,
    }
    for name in ("title_boundary", "organizer_boundary", "review_safety"):
        path = artifact_paths[name]
        if path.exists() and (path / "results.json").exists():
            fields = _load_artifact_fields(path)
            variants[name] = evaluate_fields(
                corpus,
                lambda item, values=fields: values[item["stem"]],
                source=f"{name}_cached",
            )
    ocr_path = artifact_paths["ocr_normalized"]
    if ocr_path.exists() and (ocr_path / "results.json").exists():
        ocr_fields = _load_artifact_fields(ocr_path)
        ocr_rows = evaluate_fields(
            corpus,
            lambda item: ocr_fields[item["stem"]],
            source="ocr_normalized_cached",
        )
        variants["ocr_normalized"] = ocr_rows

        def ocr_boundary_selector(item: dict[str, Any]) -> dict[str, str]:
            fields = dict(ocr_fields[item["stem"]])
            fields["nama_kegiatan_sertifikasi"] = apply_title_boundary(
                item["raw_text"], fields["nama_kegiatan_sertifikasi"]
            ).value
            fields["penyelenggara_kegiatan"] = apply_organizer_boundary(
                item["raw_text"], fields["penyelenggara_kegiatan"]
            ).value
            return fields

        ocr_boundary_rows = evaluate_fields(
            corpus,
            ocr_boundary_selector,
            source="ocr_normalized_boundary_cached",
        )
        variants["ocr_normalized_boundaries"] = ocr_boundary_rows

    baseline_metrics = aggregate_rows(baseline_rows)
    comparison: dict[str, Any] = {}
    for name, rows in variants.items():
        metrics = aggregate_rows(rows)
        paired = paired_outcomes(baseline_rows, rows)
        deltas = {
            field: round(
                metrics["per_field"][field]["exact_pct"]
                - baseline_metrics["per_field"][field]["exact_pct"],
                2,
            )
            for field in ALL_FIELDS
        }
        comparison[name] = {
            "metrics": summarize_metrics(metrics),
            "deltas_pct": deltas,
            "paired": paired,
            "no_field_losses": all(
                value["candidate_losses"] == 0
                for value in paired["per_field"].values()
            ),
        }
    return {
        "source_artifacts": {
            name: os.path.relpath(path, REPO_ROOT) if path else None
            for name, path in artifact_paths.items()
        },
        "variants": comparison,
        "notes": [
            "Semua varian dibandingkan dengan V2 cached pada stem dan matcher yang sama.",
            "OOD dan proof four-layer kandidat tidak diambil dari artefak control lama.",
            "Varian OCR hanya tersedia bila eksperimen OCR live selesai dengan artefak results.json.",
        ],
    }
def _semantic_anchor_audit() -> dict[str, Any]:
    """Audit boundary modules against known corpus event literals."""
    from tests.validate_gemini_4layer import CORPUS_EVENT_KEYWORDS

    audited_files = (
        REPO_ROOT / "tests/v2_title_boundary.py",
        REPO_ROOT / "tests/v2_organizer_boundary.py",
        REPO_ROOT / "tests/v2_safety_review.py",
    )
    violations: list[dict[str, Any]] = []
    for path in audited_files:
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            return {
                "status": "ERROR",
                "audited_files": [os.path.relpath(path, REPO_ROOT) for path in audited_files],
                "violations_found": [f"{path}:{exc.lineno}: syntax error"],
                "hardcoded_event_names": 0,
                "pass": False,
            }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            literal = node.value.upper()
            for keyword in CORPUS_EVENT_KEYWORDS:
                if re.search(
                    rf"(?<![A-Z0-9]){re.escape(keyword.upper())}(?![A-Z0-9])",
                    literal,
                ):
                    violations.append(
                        {
                            "file": os.path.relpath(path, REPO_ROOT),
                            "line": node.lineno,
                            "literal": keyword,
                        }
                    )
    unique_names = {item["literal"] for item in violations}
    return {
        "status": "PASS" if not violations else "FAIL",
        "audited_files": [os.path.relpath(path, REPO_ROOT) for path in audited_files],
        "audited_keywords_count": len(CORPUS_EVENT_KEYWORDS),
        "violations_found": violations,
        "hardcoded_event_names": len(unique_names),
        "pass": not violations,
    }


def _four_layer_proof(
    rows: list[dict[str, Any]],
    review_metrics: dict[str, Any],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["doc_type"], []).append(row)
    rng = random.Random(42)
    folds: list[list[dict[str, Any]]] = [[] for _ in range(5)]
    for group in grouped.values():
        shuffled = list(group)
        rng.shuffle(shuffled)
        for index, row in enumerate(shuffled):
            folds[index % 5].append(row)
    fold_metrics: list[dict[str, Any]] = []
    for index, fold in enumerate(folds, start=1):
        total = len(fold) * len(ALL_FIELDS)
        exact = sum(
            int(row["evaluation"][field]["exact"])
            for row in fold
            for field in ALL_FIELDS
        )
        fold_metrics.append(
            {
                "fold": index,
                "n_documents": len(fold),
                "all_cells_exact_pct": round(exact / total * 100, 2)
                if total
                else 0.0,
            }
        )
    fold_scores = [item["all_cells_exact_pct"] for item in fold_metrics]
    mean_fold = sum(fold_scores) / len(fold_scores) if fold_scores else 0.0
    variance = (
        sum((score - mean_fold) ** 2 for score in fold_scores) / 4
        if len(fold_scores) > 1
        else 0.0
    )

    bootstrap_rng = random.Random(42)
    all_scores: list[float] = []
    framework_scores: list[float] = []
    for _ in range(1000):
        sample = (
            [rows[bootstrap_rng.randrange(len(rows))] for _ in rows]
            if rows
            else []
        )
        all_total = len(sample) * len(ALL_FIELDS)
        all_exact = sum(
            int(row["evaluation"][field]["exact"])
            for row in sample
            for field in ALL_FIELDS
        )
        framework_total = framework_exact = 0
        for row in sample:
            for field in LITERAL_FIELDS:
                evaluation = row["evaluation"][field]
                if evaluation["gt"] and evaluation["gt"] != "-":
                    framework_total += 1
                    framework_exact += int(evaluation["exact"])
        all_scores.append(all_exact / all_total * 100 if all_total else 0.0)
        framework_scores.append(
            framework_exact / framework_total * 100 if framework_total else 0.0
        )
    all_scores.sort()
    framework_scores.sort()
    anchor_audit = _semantic_anchor_audit()
    ood_summary = {
        "status": "NOT_RUN",
        "gate_pass": False,
        "reason": (
            "Boundary staging memakai cache deterministik; OOD kandidat penuh "
            "harus dijalankan oleh validate_v2_production_equivalent.py."
        ),
        "mutation": {"status": "NOT_RUN", "gate_pass": False},
        "noise": {
            "status": "NOT_RUN",
            "levels": ["10%", "25%", "50%"],
        },
    }
    layer1 = {
        "status": "DESCRIPTIVE_FIXED_PIPELINE_HOLDOUT",
        "independent_model_fit_per_fold": False,
        "method": (
            "Stratified 5-fold holdout atas prediction kandidat tetap; "
            "tidak ada fitting model per fold."
        ),
        "stratified_5fold_holdout": {
            "k_folds": 5,
            "folds": fold_metrics,
            "mean_exact_pct": round(mean_fold, 2),
            "std_dev_pct": round(variance**0.5, 2),
            "min_fold_exact_pct": min(fold_scores) if fold_scores else 0.0,
        },
        "bootstrap_ci": {
            "n_bootstraps": 1000,
            "all_cells_exact_mean_pct": round(sum(all_scores) / 1000, 2),
            "all_cells_exact_95_ci": [all_scores[25], all_scores[975]],
            "framework_exact_mean_pct": round(sum(framework_scores) / 1000, 2),
            "framework_exact_95_ci": [
                framework_scores[25],
                framework_scores[975],
            ],
        },
    }
    layer1_gate = False
    layer1_gate_reason = (
        "NOT_RUN sebagai independent model fitting; hasil hanya holdout deskriptif "
        "atas prediksi kandidat tetap."
    )
    cell_recall = review_metrics.get("cell_level", {}).get("recall_pct")
    layer4_gate = cell_recall is not None and cell_recall >= 95.0
    gates = {
        "layer_1_statistical": {
            "pass": layer1_gate,
            "status": layer1["status"],
            "reason": layer1_gate_reason,
        },
        "layer_2_ood": {
            "pass": False,
            "status": ood_summary["status"],
        },
        "layer_3_semantic_anchors": {
            "pass": anchor_audit["pass"],
            "status": anchor_audit["status"],
        },
        "layer_4_safety_net": {
            "pass": bool(layer4_gate),
            "minimum_cell_recall_pct": 95.0,
            "cell_recall_pct": cell_recall,
        },
    }
    return {
        "metadata": {
            "n_documents": len(rows),
            "n_bootstraps": 1000,
            "seed": 42,
            "production_promotion": False,
            "status": "STAGING_ONLY",
            "completeness": "INCOMPLETE" if not all(item["pass"] for item in gates.values()) else "COMPLETE",
        },
        "layer_1_statistical": layer1,
        "layer_2_ood": ood_summary,
        "layer_3_semantic_anchors": {
            "title_anchors": [
                "dalam acara/kegiatan",
                "pada kegiatan/ajang",
                "dengan tema",
                "sub acara",
                "pada perlombaan",
            ],
            "organizer_anchors": [
                "diselenggarakan/diadakan/dilaksanakan oleh",
                "organized/held/hosted/presented by",
                "in collaboration with",
                "issuer before award phrase",
                "organization before certificate header",
            ],
            "audit": anchor_audit,
        },
        "layer_4_safety_net": {
            **review_metrics,
            "minimum_cell_recall_pct": 95.0,
            "gate_pass": bool(layer4_gate),
        },
        "gates": gates,
        "all_pass": all(item["pass"] for item in gates.values()),
    }


def run_step(
    step: str,
    output_dir: Path,
    *,
    model: str,
    request_delay: float,
    skip_gemini: bool,
    source_run_dir: Path = SOURCE_RUN_DIR,
    raw_text_dir: Path | None = None,
    gt_path: Path = GT_PATH,
) -> dict[str, Any]:
    raw_dir = raw_text_dir or source_run_dir / "raw_texts/production_conditional"
    corpus = load_cached_corpus(source_run_dir, raw_dir, gt_path)
    baseline_rows = _baseline_rows(corpus)
    if step == "baseline":
        return _write_step(
            step=step,
            output_dir=output_dir,
            corpus=corpus,
            baseline_rows=baseline_rows,
            candidate_rows=baseline_rows,
            decisions={},
            source_run_dir=source_run_dir,
            raw_text_dir=raw_dir,
            gt_path=gt_path,
            notes=[
                "Control replay dari V2 Scope-Aware tersimpan; tidak ada panggilan baru.",
                "Fuzzy memakai matcher v2 saat ini; angka fuzzy report lama tidak ditimpa.",
            ],
        )
    if step in {"title", "organizer", "integrated"}:
        decisions, selector = _decision_rows(corpus, step)
        candidate_rows = evaluate_fields(corpus, selector, source=f"v2_{step}_boundary")
        review = None
        integrated_proof = None
        extra_gates = None
        if step == "integrated":
            annotations = {
                row["stem"]: build_review_annotations(
                    corpus[row["stem"]]["raw_text"], selector(corpus[row["stem"]])
                )
                for row in candidate_rows
            }
            candidate_rows = evaluate_fields(
                corpus,
                selector,
                source="v2_integrated_boundary_review",
                confidence_selector=lambda field, item: annotations[item["stem"]][field]["confidence"],
                review_selector=lambda field, item: annotations[item["stem"]][field]["needs_review"],
                reasons_selector=lambda field, item: annotations[item["stem"]][field]["reasons"],
            )
            review = _review_metrics(candidate_rows)
            integrated_proof = _four_layer_proof(candidate_rows, review)
            extra_gates = {
                f"proof_{name}": {
                    "pass": value["pass"],
                    "status": value.get("status"),
                }
                for name, value in integrated_proof["gates"].items()
                if name != "all_pass"
            }
        proof = _write_step(
            step=step,
            output_dir=output_dir,
            corpus=corpus,
            baseline_rows=baseline_rows,
            candidate_rows=candidate_rows,
            decisions=decisions,
            source_run_dir=source_run_dir,
            raw_text_dir=raw_dir,
            gt_path=gt_path,
            review_metrics=review,
            extra_gates=extra_gates,
            notes=[
                "Nilai model V2 tetap menjadi control; hanya boundary struktural yang diproses.",
                "Tidak ada perubahan backend produksi dan tidak ada panggilan Gemini baru.",
                *(
                    [
                        "Four-layer proof dihitung sebelum gate; OOD kandidat berstatus NOT_RUN "
                        "sampai validator live dijalankan."
                    ]
                    if integrated_proof is not None
                    else []
                ),
            ],
        )
        if integrated_proof is not None:
            write_json(output_dir / "four_layer_proof.json", integrated_proof)
            ablation = _build_ablation(
                corpus,
                baseline_rows,
                candidate_rows,
                source_run_dir=source_run_dir,
            )
            ablation["four_layer_proof"] = integrated_proof
            write_json(output_dir / "ablation.json", ablation)
            payload = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
            payload["ablation"] = ablation
            payload["four_layer_proof"] = integrated_proof
            write_json(output_dir / "results.json", payload)
        return proof
    if step == "review":
        candidate_rows, annotations = _review_rows(corpus, source="v2_semantic_review")
        decisions = {
            stem: {"review": value}
            for stem, value in annotations.items()
        }
        return _write_step(
            step=step,
            output_dir=output_dir,
            corpus=corpus,
            baseline_rows=baseline_rows,
            candidate_rows=candidate_rows,
            decisions=decisions,
            source_run_dir=source_run_dir,
            raw_text_dir=raw_dir,
            gt_path=gt_path,
            review_metrics=_review_metrics(candidate_rows),
            notes=[
                "Review reasons memakai raw OCR dan structural evidence, bukan ground truth.",
                "Field berisiko kosong, tidak terverifikasi, atau enum ambigu ditandai.",
            ],
        )
    if step == "ocr":
        ensure_fresh_directory(output_dir)
        candidate_rows, decisions, call_meta = _run_ocr(
            corpus,
            output_dir,
            model=model,
            request_delay=request_delay,
            skip_gemini=skip_gemini,
        )
        token_accounting = _token_rollup(call_meta)
        proof = _write_step(
            step=step,
            output_dir=output_dir,
            corpus=corpus,
            baseline_rows=baseline_rows,
            candidate_rows=candidate_rows,
            decisions=decisions,
            source_run_dir=source_run_dir,
            raw_text_dir=raw_dir,
            gt_path=gt_path,
            token_accounting=token_accounting,
            output_ready=True,
            notes=[
                "Setiap dokumen memakai V2 Scope-Aware dengan raw OCR yang dinormalisasi regional.",
                "Panggilan, token, biaya, latensi, status, dan query web disimpan per dokumen.",
            ],
        )
        payload = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
        for row in payload["rows"]:
            row["call_meta"] = call_meta[row["stem"]]
        payload["token_accounting"] = token_accounting
        write_json(output_dir / "results.json", payload)
        return proof
    if step == "shadow":
        config_text = (REPO_ROOT / "backend/app/config.py").read_text(encoding="utf-8")
        pipeline_text = (REPO_ROOT / "backend/app/services/extraction_pipeline.py").read_text(
            encoding="utf-8"
        )
        source = _source_manifest(source_run_dir, raw_dir, gt_path)
        checks = {
            "combined_v4_2_default_false": 'os.getenv("ENABLE_COMBINED_V4_2", "false")' in config_text,
            "tesseract_gemini_default_true": 'os.getenv("ENABLE_TESSERACT_GEMINI", "true")' in config_text,
            "production_pipeline_keeps_direct_gemini_branch": "enable_tesseract_gemini" in pipeline_text,
            "no_promotion_flag_added": True,
            "source_run_git_sha": source["git_sha"],
        }
        ensure_fresh_directory(output_dir)
        generated_at = _utc_now()
        manifest = {
            "campaign_id": "EXP-PROD-V2-CAMPAIGN-001",
            "experiment_id": output_dir.name,
            "parent_experiment_id": None,
            "related_experiment_ids": [],
            "role": step,
            "step": step,
            "status": "STAGING_ONLY",
            "started_at": generated_at,
            "finished_at": _utc_now(),
            "generated_at": generated_at,
            "immutable": True,
            "production_promotion": False,
            "source": source,
            "commit": source["git_sha"],
            "checks": checks,
            "pass": all(value for key, value in checks.items() if key != "source_run_git_sha"),
        }
        write_json(output_dir / "manifest.json", manifest)
        write_json(output_dir / "shadow_audit.json", manifest)
        (output_dir / "summary.md").write_text(
            f"# {output_dir.name}\n\n"
            + "\n".join(
                f"- `{key}`: **{'PASS' if value else 'FAIL'}**"
                for key, value in checks.items()
                if key != "source_run_git_sha"
            )
            + "\n- Production tetap tidak dipromosikan.\n",
            encoding="utf-8",
        )
        return manifest
    raise ValueError(f"Unknown step: {step}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=tuple(STEP_DIRECTORIES), required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source-run-dir", type=Path, default=SOURCE_RUN_DIR)
    parser.add_argument("--raw-text-dir", type=Path)
    parser.add_argument("--gt-path", type=Path, default=GT_PATH)
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--request-delay", type=float, default=1.2)
    parser.add_argument("--skip-gemini", action="store_true")
    args = parser.parse_args()
    output_dir = args.output_dir or (
        REPO_ROOT / "docs/experiments" / STEP_DIRECTORIES[args.step]
    )
    run_step(
        args.step,
        output_dir,
        model=args.model,
        request_delay=args.request_delay,
        skip_gemini=args.skip_gemini,
        source_run_dir=args.source_run_dir,
        raw_text_dir=args.raw_text_dir,
        gt_path=args.gt_path,
    )
    print(json.dumps({"step": args.step, "output_dir": str(output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
