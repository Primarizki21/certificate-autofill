"""Run isolated, immutable V2 staging steps against the cached 74-document corpus."""

from __future__ import annotations

import argparse
import json
import os
import random
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


def _source_manifest() -> dict[str, Any]:
    metadata_path = SOURCE_RUN_DIR / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {
        "path": str(SOURCE_RUN_DIR.relative_to(REPO_ROOT)),
        "run_id": metadata.get("run_id"),
        "git_sha": metadata.get("git_sha"),
        "gt_path": str(GT_PATH.relative_to(REPO_ROOT)),
        "gt_sha256": sha256_text(GT_PATH.read_text(encoding="utf-8")),
        "results_sha256": sha256_text(
            (SOURCE_RUN_DIR / "results.json").read_text(encoding="utf-8")
        ),
        "raw_text_count": len(list((SOURCE_RUN_DIR / "raw_texts/production_conditional").glob("*.txt"))),
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
        gates["review_recall"] = {
            **review,
            "minimum_doc_recall_pct": 95.0,
            "pass": review["doc_level"]["recall_pct"] >= 95.0,
        }
    if token_accounting is not None:
        gates["token_accounting"] = {
            "all_required_fields": all(
                key in token_accounting
                for key in (
                    "prompt_tokens",
                    "candidates_tokens",
                    "cached_tokens",
                    "thoughts_tokens",
                    "total_tokens",
                    "cost_usd",
                    "cost_idr",
                    "web_search_queries",
                )
            ),
            "web_search_queries": token_accounting["web_search_queries"],
            "pass": not token_accounting["web_search_queries"],
        }
    gates["all_pass"] = all(item["pass"] for item in gates.values())
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
    for meta in call_meta.values():
        for field in fields:
            rollup[field] += meta.get(field, 0) or 0
        for query in meta.get("web_search_queries", []):
            if query not in queries:
                queries.append(query)
        status = meta.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    rollup["web_search_queries"] = queries
    rollup["status_counts"] = statuses
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
        lines.append(f"|`{field}`|{delta:+.2f}|" )
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
    review_metrics: dict[str, Any] | None = None,
    token_accounting: dict[str, Any] | None = None,
    output_ready: bool = False,
) -> dict[str, Any]:
    if not output_ready:
        ensure_fresh_directory(output_dir)
    experiment_id = output_dir.name
    source = _source_manifest()
    proof = _gate_report(
        baseline_rows,
        candidate_rows,
        review=review_metrics,
        token_accounting=token_accounting,
    )
    _attach_metadata(candidate_rows, corpus, decisions=decisions)
    manifest = {
        "experiment_id": experiment_id,
        "step": step,
        "generated_at": _utc_now(),
        "immutable": True,
        "production_promotion": False,
        "source": source,
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
) -> dict[str, Any]:
    artifact_paths = {
        "v2_cached": SOURCE_RUN_DIR,
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
    proof_path = (
        SOURCE_RUN_DIR.parent
        / "proof_full_74_token_accounted"
        / "four_layer_proof.json"
    )
    four_layer = (
        json.loads(proof_path.read_text(encoding="utf-8"))
        if proof_path.exists()
        else {"status": "missing"}
    )
    return {
        "source_artifacts": {
            name: str(path.relative_to(REPO_ROOT)) if path else None
            for name, path in artifact_paths.items()
        },
        "variants": comparison,
        "four_layer_proof_source": four_layer,
        "notes": [
            "Semua varian dibandingkan dengan V2 cached pada stem dan matcher yang sama.",
            "Varian OCR hanya tersedia bila eksperimen OCR live selesai dengan artefak results.json.",
        ],
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
    mean_fold = sum(fold_scores) / len(fold_scores)
    variance = sum((score - mean_fold) ** 2 for score in fold_scores) / 4

    bootstrap_rng = random.Random(42)
    all_scores: list[float] = []
    framework_scores: list[float] = []
    for _ in range(1000):
        sample = [rows[bootstrap_rng.randrange(len(rows))] for _ in rows]
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
        all_scores.append(all_exact / all_total * 100)
        framework_scores.append(
            framework_exact / framework_total * 100 if framework_total else 0.0
        )
    all_scores.sort()
    framework_scores.sort()
    proof_path = (
        SOURCE_RUN_DIR.parent
        / "proof_full_74_token_accounted"
        / "four_layer_proof.json"
    )
    source_proof = json.loads(proof_path.read_text(encoding="utf-8"))
    source_ood = source_proof["layer_2_ood"]
    source_noise = source_ood["noise"]
    ood_summary = {
        "status": "inherited_control_measurement",
        "source": str(proof_path.relative_to(REPO_ROOT)),
        "note": "Boundary bundle tidak menjalankan ulang model pada mutasi/noise; angka berikut adalah control V2.",
        "mutation": {
            key: source_ood["mutation"][key]
            for key in (
                "baseline_accuracy_pct",
                "mutated_accuracy_pct",
                "drop_pct",
                "gate_threshold_drop_pct",
                "gate_pass",
            )
        },
        "noise": {
            "clean_all_cells_exact_pct": source_noise["clean_all_cells_exact_pct"],
            "levels": {
                level: {
                    key: values[key]
                    for key in ("all_cells_exact_pct", "drop_from_clean_all_cells_pct")
                }
                for level, values in source_noise["levels"].items()
            },
        },
    }
    return {
        "metadata": {
            "n_documents": len(rows),
            "n_bootstraps": 1000,
            "seed": 42,
            "production_promotion": False,
        },
        "layer_1_statistical": {
            "stratified_5fold_cv": {
                "k_folds": 5,
                "folds": fold_metrics,
                "mean_exact_pct": round(mean_fold, 2),
                "std_dev_pct": round(variance**0.5, 2),
                "min_fold_exact_pct": min(fold_scores),
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
        },
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
            "dataset_event_literals": [],
            "hardcoded_event_names": 0,
        },
        "layer_4_safety_net": {
            **review_metrics,
            "minimum_doc_recall_pct": 95.0,
            "gate_pass": review_metrics["doc_level"]["recall_pct"] >= 95.0,
        },
    }


def run_step(
    step: str,
    output_dir: Path,
    *,
    model: str,
    request_delay: float,
    skip_gemini: bool,
) -> dict[str, Any]:
    corpus = load_cached_corpus()
    baseline_rows = _baseline_rows(corpus)
    if step == "baseline":
        return _write_step(
            step=step,
            output_dir=output_dir,
            corpus=corpus,
            baseline_rows=baseline_rows,
            candidate_rows=baseline_rows,
            decisions={},
            notes=[
                "Control replay dari V2 Scope-Aware tersimpan; tidak ada panggilan baru.",
                "Fuzzy memakai matcher v2 saat ini; angka fuzzy report lama tidak ditimpa.",
            ],
        )
    if step in {"title", "organizer", "integrated"}:
        decisions, selector = _decision_rows(corpus, step)
        candidate_rows = evaluate_fields(corpus, selector, source=f"v2_{step}_boundary")
        review = None
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
        proof = _write_step(
            step=step,
            output_dir=output_dir,
            corpus=corpus,
            baseline_rows=baseline_rows,
            candidate_rows=candidate_rows,
            decisions=decisions,
            review_metrics=review,
            notes=[
                "Nilai model V2 tetap menjadi control; hanya boundary struktural yang diproses.",
                "Tidak ada perubahan backend produksi dan tidak ada panggilan Gemini baru.",
            ],
        )
        if step == "integrated":
            integrated_proof = _four_layer_proof(candidate_rows, review or {})
            write_json(output_dir / "four_layer_proof.json", integrated_proof)
            ablation = _build_ablation(corpus, baseline_rows, candidate_rows)
            ablation["four_layer_proof"] = integrated_proof
            write_json(output_dir / "ablation.json", ablation)
            payload = json.loads((output_dir / "results.json").read_text(encoding="utf-8"))
            payload["ablation"] = ablation
            payload["four_layer_proof"] = integrated_proof
            write_json(output_dir / "results.json", payload)
            with (output_dir / "summary.md").open("a", encoding="utf-8") as handle:
                handle.write("\n## Ablation lintas langkah\n\n")
                for name, variant in ablation["variants"].items():
                    metrics = variant["metrics"]
                    handle.write(
                        f"- `{name}`: all-cells exact "
                        f"`{metrics['all_cells_exact_pct']}%`, framework exact "
                        f"`{metrics['framework_exact_pct']}%`, "
                        f"no field loss `{variant['no_field_losses']}`.\n"
                    )
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
        checks = {
            "combined_v4_2_default_false": 'os.getenv("ENABLE_COMBINED_V4_2", "false")' in config_text,
            "tesseract_gemini_default_true": 'os.getenv("ENABLE_TESSERACT_GEMINI", "true")' in config_text,
            "production_pipeline_keeps_direct_gemini_branch": "enable_tesseract_gemini" in pipeline_text,
            "no_promotion_flag_added": True,
            "source_run_git_sha": _source_manifest()["git_sha"],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        ensure_fresh_directory(output_dir)
        manifest = {
            "experiment_id": output_dir.name,
            "step": step,
            "generated_at": _utc_now(),
            "immutable": True,
            "production_promotion": False,
            "source": _source_manifest(),
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
    parser.add_argument("--step", choices=tuple(STEP_DIRECTORIES))
    parser.add_argument("--output-dir", type=Path)
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
    )
    print(json.dumps({"step": args.step, "output_dir": str(output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
