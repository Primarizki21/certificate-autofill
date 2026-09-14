"""Shared loaders and evaluators for isolated V2 staging experiments."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from tests.matchers import match_field

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN_DIR = REPO_ROOT / "docs/experiments/EXP-PROD-V2-SCOPE-001/run_full_74"
RAW_TEXT_DIR = SOURCE_RUN_DIR / "raw_texts/production_conditional"
GT_PATH = REPO_ROOT / "Ground_Truth_Sertifikat_v9.csv"
ALL_FIELDS = (
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "tingkat",
)
LITERAL_FIELDS = tuple(field for field in ALL_FIELDS if field != "tingkat")
GT_COLUMNS = {
    "Tingkat": "tingkat",
    "Nama Kegiatan Sertifikasi": "nama_kegiatan_sertifikasi",
    "Waktu Mulai Pelaksanaan": "waktu_mulai_pelaksanaan",
    "Waktu Selesai Pelaksanaan": "waktu_selesai_pelaksanaan",
    "Penyelenggara Kegiatan": "penyelenggara_kegiatan",
    "Nomor Bukti Fisik Nomor Sertifikasi": "nomor_bukti_fisik_nomor_sertifikasi",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def ensure_fresh_directory(path: Path) -> None:
    if path.exists():
        existing = list(path.iterdir())
        if existing:
            raise FileExistsError(
                f"B14 AGENTS.md Immutability Guard: {path} is not empty"
            )
    path.mkdir(parents=True, exist_ok=True)


def load_ground_truth(path: Path = GT_PATH) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        return {
            Path(row["Nama File"]).stem: {
                field_name: (row.get(source_name) or "").strip()
                for source_name, field_name in GT_COLUMNS.items()
            }
            for row in rows
        }


def load_cached_corpus(
    run_dir: Path = SOURCE_RUN_DIR,
    raw_dir: Path = RAW_TEXT_DIR,
    gt_path: Path = GT_PATH,
) -> dict[str, dict[str, Any]]:
    """Muat cache V1/V2 dengan manifest input yang lengkap dan konsisten."""
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(
            f"Cached results.json tidak ditemukan di {results_path}. "
            "Sediakan --source-run-dir dari run V2 yang valid."
        )
    if not gt_path.exists():
        raise FileNotFoundError(
            f"Ground truth tidak ditemukan di {gt_path}. "
            "Sediakan --gt-path yang menunjuk ke Ground_Truth_Sertifikat_v9.csv."
        )
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"Raw OCR directory tidak ditemukan di {raw_dir}. "
            "Sediakan --raw-text-dir dari artefak OCR yang sesuai."
        )
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    ground_truth = load_ground_truth(gt_path)
    raw_texts = {
        path.stem: path.read_text(encoding="utf-8", errors="replace")
        for path in raw_dir.glob("*.txt")
    }
    empty_raw = sorted(stem for stem, text in raw_texts.items() if not text.strip())
    if empty_raw:
        raise ValueError(
            f"Raw OCR kosong untuk {len(empty_raw)} dokumen; "
            "benchmark dihentikan agar model tidak dievaluasi pada input kosong."
        )
    variants = payload["variants"]
    v1_by_stem = {row["stem"]: row for row in variants["v1_production"]}
    v2_by_stem = {row["stem"]: row for row in variants["v2_scope_aware"]}
    expected_stems = set(ground_truth)
    if (
        set(v1_by_stem) != set(v2_by_stem)
        or set(v2_by_stem) != expected_stems
        or set(v2_by_stem) != set(raw_texts)
    ):
        raise ValueError(
            "Cached V1/V2, GT, dan raw OCR manifests tidak sama; "
            "benchmark dihentikan agar metrik tidak incomplete."
        )

    corpus: dict[str, dict[str, Any]] = {}
    for stem, v2_row in v2_by_stem.items():
        v1_row = v1_by_stem[stem]
        corpus[stem] = {
            "stem": stem,
            "filename": v2_row["filename"],
            "doc_type": v2_row["doc_type"],
            "raw_text": raw_texts[stem],
            "raw_text_sha256": sha256_text(raw_texts[stem]),
            "ground_truth": ground_truth[stem],
            "v1_fields": {
                field: v1_row["evaluation"][field]["pred"] or ""
                for field in ALL_FIELDS
            },
            "v2_fields": {
                field: v2_row["evaluation"][field]["pred"] or ""
                for field in ALL_FIELDS
            },
            "v1_call_meta": v1_row.get("call_meta", {}),
            "v2_call_meta": v2_row.get("call_meta", {}),
        }
    return corpus


def evaluate_fields(
    corpus: dict[str, dict[str, Any]],
    field_selector: Callable[[dict[str, Any]], dict[str, str]],
    *,
    source: str = "staging",
    confidence_selector: Callable[[str, dict[str, Any]], float] | None = None,
    review_selector: Callable[[str, dict[str, Any]], bool] | None = None,
    reasons_selector: Callable[[str, dict[str, Any]], list[str]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stem in sorted(corpus):
        item = corpus[stem]
        fields = field_selector(item)
        evaluation: dict[str, dict[str, Any]] = {}
        for field in ALL_FIELDS:
            expected = item["ground_truth"][field]
            predicted = fields.get(field, "") or ""
            match = match_field(expected, predicted, field)
            confidence = (
                confidence_selector(field, item)
                if confidence_selector
                else (0.90 if predicted.strip() else 0.0)
            )
            reasons = reasons_selector(field, item) if reasons_selector else []
            evaluation[field] = {
                "gt": expected,
                "pred": predicted,
                "exact": bool(match["exact"]),
                "fuzzy": bool(match["fuzzy"]),
                "wer": float(match.get("wer", 0.0)),
                "cer": float(match.get("cer", 0.0)),
                "confidence": round(float(confidence), 4),
                "source": source,
                "needs_review": bool(
                    review_selector(field, item) if review_selector else False
                ),
                "review_reasons": reasons,
            }
        rows.append(
            {
                "stem": stem,
                "filename": item["filename"],
                "doc_type": item["doc_type"],
                "raw_text_sha256": item["raw_text_sha256"],
                "fields": fields,
                "evaluation": evaluation,
            }
        )
    return rows


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n_documents = len(rows)
    per_field: dict[str, dict[str, Any]] = {}
    exact_all = 0
    fuzzy_all = 0
    framework_total = 0
    framework_exact = 0
    framework_fuzzy = 0
    for field in ALL_FIELDS:
        evaluations = [row["evaluation"][field] for row in rows]
        exact = sum(int(item["exact"]) for item in evaluations)
        fuzzy = sum(int(item["fuzzy"]) for item in evaluations)
        exact_all += exact
        fuzzy_all += fuzzy
        per_field[field] = {
            "total": n_documents,
            "exact": exact,
            "fuzzy": fuzzy,
            "exact_pct": round(exact / n_documents * 100, 2) if n_documents else 0.0,
            "fuzzy_pct": round(fuzzy / n_documents * 100, 2) if n_documents else 0.0,
        }
    for row in rows:
        for field in LITERAL_FIELDS:
            item = row["evaluation"][field]
            if item["gt"] and item["gt"] != "-":
                framework_total += 1
                framework_exact += int(item["exact"])
                framework_fuzzy += int(item["fuzzy"])
    review_cells = sum(
        int(item["needs_review"])
        for row in rows
        for item in row["evaluation"].values()
    )
    review_documents = sum(
        any(item["needs_review"] for item in row["evaluation"].values())
        for row in rows
    )
    return {
        "n_documents": n_documents,
        "all_cells_6f": {
            "total": n_documents * len(ALL_FIELDS),
            "exact": exact_all,
            "fuzzy": fuzzy_all,
            "exact_pct": round(exact_all / (n_documents * len(ALL_FIELDS)) * 100, 2)
            if n_documents
            else 0.0,
            "fuzzy_pct": round(fuzzy_all / (n_documents * len(ALL_FIELDS)) * 100, 2)
            if n_documents
            else 0.0,
        },
        "framework_5f": {
            "total": framework_total,
            "exact": framework_exact,
            "fuzzy": framework_fuzzy,
            "exact_pct": round(framework_exact / framework_total * 100, 2)
            if framework_total
            else 0.0,
            "fuzzy_pct": round(framework_fuzzy / framework_total * 100, 2)
            if framework_total
            else 0.0,
        },
        "per_field": per_field,
        "review": {
            "documents": review_documents,
            "cells": review_cells,
        },
    }


def paired_outcomes(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_by_stem = {row["stem"]: row for row in baseline_rows}
    candidate_by_stem = {row["stem"]: row for row in candidate_rows}
    fields = list(ALL_FIELDS)
    result: dict[str, Any] = {
        "total_documents": len(candidate_rows),
        "document_total_exact": {"candidate_wins": 0, "ties": 0, "candidate_losses": 0},
        "per_field": {
            field: {"candidate_wins": 0, "ties": 0, "candidate_losses": 0}
            for field in fields
        },
    }
    for stem, candidate in candidate_by_stem.items():
        baseline = baseline_by_stem[stem]
        candidate_exact = sum(int(candidate["evaluation"][field]["exact"]) for field in fields)
        baseline_exact = sum(int(baseline["evaluation"][field]["exact"]) for field in fields)
        if candidate_exact > baseline_exact:
            result["document_total_exact"]["candidate_wins"] += 1
        elif candidate_exact < baseline_exact:
            result["document_total_exact"]["candidate_losses"] += 1
        else:
            result["document_total_exact"]["ties"] += 1
        for field in fields:
            candidate_ok = bool(candidate["evaluation"][field]["exact"])
            baseline_ok = bool(baseline["evaluation"][field]["exact"])
            if candidate_ok and not baseline_ok:
                result["per_field"][field]["candidate_wins"] += 1
            elif baseline_ok and not candidate_ok:
                result["per_field"][field]["candidate_losses"] += 1
            else:
                result["per_field"][field]["ties"] += 1
    return result


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_evaluation_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = ["stem", "filename", "doc_type"]
    for field in ALL_FIELDS:
        columns.extend(
            [
                f"{field}_pred",
                f"{field}_gt",
                f"{field}_exact",
                f"{field}_fuzzy",
                f"{field}_confidence",
                f"{field}_needs_review",
                f"{field}_review_reasons",
            ]
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            output = {
                "stem": row["stem"],
                "filename": row["filename"],
                "doc_type": row["doc_type"],
            }
            for field in ALL_FIELDS:
                item = row["evaluation"][field]
                output.update(
                    {
                        f"{field}_pred": item["pred"],
                        f"{field}_gt": item["gt"],
                        f"{field}_exact": item["exact"],
                        f"{field}_fuzzy": item["fuzzy"],
                        f"{field}_confidence": item["confidence"],
                        f"{field}_needs_review": item["needs_review"],
                        f"{field}_review_reasons": "|".join(item["review_reasons"]),
                    }
                )
            writer.writerow(output)


def summarize_metrics(aggregate: dict[str, Any]) -> dict[str, Any]:
    return {
        "all_cells_exact_pct": aggregate["all_cells_6f"]["exact_pct"],
        "all_cells_fuzzy_pct": aggregate["all_cells_6f"]["fuzzy_pct"],
        "framework_exact_pct": aggregate["framework_5f"]["exact_pct"],
        "framework_fuzzy_pct": aggregate["framework_5f"]["fuzzy_pct"],
        "per_field_exact_pct": {
            field: aggregate["per_field"][field]["exact_pct"] for field in ALL_FIELDS
        },
    }
