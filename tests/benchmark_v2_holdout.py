"""Evaluate V2 boundary candidates on the untouched 30-document holdout."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.matchers import match_field
from tests.v2_organizer_boundary import apply_organizer_boundary
from tests.v2_title_boundary import apply_title_boundary

CHECKPOINT_PATH = next(
    (REPO_ROOT / "docs/experiments/EXP-ALL6F-PROMPT-001").glob(
        "checkpoint_gemini_*v2_scope_aware*_grnd0_pace1.2_tout35.jsonl"
    ),
    None,
)
RAW_TEXT_DIR = REPO_ROOT / "docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts"
GT_PATH = REPO_ROOT / "Ground_Truth_Unified.csv"
FIELDS = (
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "tingkat",
)
GT_COLUMNS = {
    "nama_kegiatan_sertifikasi": "Nama Kegiatan Sertifikasi",
    "waktu_mulai_pelaksanaan": "Waktu Mulai Pelaksanaan",
    "waktu_selesai_pelaksanaan": "Waktu Selesai Pelaksanaan",
    "penyelenggara_kegiatan": "Penyelenggara Kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi": "Nomor Bukti Fisik Nomor Sertifikasi",
    "tingkat": "Tingkat",
}


def _load_gt() -> dict[str, dict[str, str]]:
    with GT_PATH.open(encoding="utf-8", newline="") as handle:
        return {
            Path(row["Nama File"]).stem: row
            for row in csv.DictReader(handle)
        }


def _load_v2_rows() -> dict[str, dict[str, Any]]:
    if CHECKPOINT_PATH is None:
        raise FileNotFoundError("Checkpoint holdout V2 tidak ditemukan")
    rows: dict[str, dict[str, Any]] = {}
    with CHECKPOINT_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            if item.get("dataset") != "elzandi" or item.get("variant") != "v2_scope_aware":
                continue
            stem = Path(item["nama_file"]).stem
            raw_path = RAW_TEXT_DIR / f"{stem}.txt"
            if not raw_path.exists():
                raise FileNotFoundError(f"Raw holdout tidak ditemukan: {raw_path}")
            rows[stem] = {
                "stem": stem,
                "filename": item["nama_file"],
                "raw_text": raw_path.read_text(encoding="utf-8"),
                "gt": item["eval"],
                "fields": {
                    field: (item.get("pred_fields", {}).get(field) or "").strip()
                    for field in FIELDS
                },
            }
    if len(rows) != 30:
        raise ValueError(f"Holdout V2 harus 30 dokumen, ditemukan {len(rows)}")
    return rows


def _evaluate(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    per_field: dict[str, dict[str, int]] = {
        field: {"total": 0, "exact": 0, "fuzzy": 0} for field in FIELDS
    }
    evaluations: dict[str, dict[str, dict[str, Any]]] = {}
    for stem, row in rows.items():
        evaluations[stem] = {}
        for field in FIELDS:
            gt = row["gt"][field]["gt"]
            pred = row["fields"][field]
            match = match_field(gt, pred, field)
            evaluations[stem][field] = {
                "gt": gt,
                "pred": pred,
                "exact": bool(match["exact"]),
                "fuzzy": bool(match["fuzzy"]),
            }
            per_field[field]["total"] += 1
            per_field[field]["exact"] += int(match["exact"])
            per_field[field]["fuzzy"] += int(match["fuzzy"])
    all_total = len(rows) * len(FIELDS)
    all_exact = sum(value["exact"] for value in per_field.values())
    all_fuzzy = sum(value["fuzzy"] for value in per_field.values())
    framework = {
        field: value
        for field, value in per_field.items()
        if field != "tingkat"
    }
    framework_total = sum(value["total"] for value in framework.values())
    framework_exact = sum(value["exact"] for value in framework.values())
    framework_fuzzy = sum(value["fuzzy"] for value in framework.values())
    return {
        "n_documents": len(rows),
        "all_cells_6f": {
            "total": all_total,
            "exact": all_exact,
            "fuzzy": all_fuzzy,
            "exact_pct": round(all_exact / all_total * 100, 2),
            "fuzzy_pct": round(all_fuzzy / all_total * 100, 2),
        },
        "framework_5f": {
            "total": framework_total,
            "exact": framework_exact,
            "fuzzy": framework_fuzzy,
            "exact_pct": round(framework_exact / framework_total * 100, 2),
            "fuzzy_pct": round(framework_fuzzy / framework_total * 100, 2),
        },
        "per_field": {
            field: {
                **value,
                "exact_pct": round(value["exact"] / value["total"] * 100, 2),
                "fuzzy_pct": round(value["fuzzy"] / value["total"] * 100, 2),
            }
            for field, value in per_field.items()
        },
        "evaluations": evaluations,
    }


def _paired(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    wins = ties = losses = 0
    per_field: dict[str, dict[str, int]] = {
        field: {"wins": 0, "ties": 0, "losses": 0} for field in FIELDS
    }
    for stem in base["evaluations"]:
        base_row = base["evaluations"][stem]
        candidate_row = candidate["evaluations"][stem]
        base_total = sum(int(base_row[field]["exact"]) for field in FIELDS)
        candidate_total = sum(int(candidate_row[field]["exact"]) for field in FIELDS)
        if candidate_total > base_total:
            wins += 1
        elif candidate_total == base_total:
            ties += 1
        else:
            losses += 1
        for field in FIELDS:
            before = base_row[field]["exact"]
            after = candidate_row[field]["exact"]
            if after > before:
                per_field[field]["wins"] += 1
            elif after == before:
                per_field[field]["ties"] += 1
            else:
                per_field[field]["losses"] += 1
    return {
        "document_total": {"wins": wins, "ties": ties, "losses": losses},
        "per_field": per_field,
    }


def _variant_rows(
    base_rows: dict[str, dict[str, Any]], variant: str
) -> dict[str, dict[str, Any]]:
    rows = {
        stem: {**row, "fields": dict(row["fields"])}
        for stem, row in base_rows.items()
    }
    if variant not in {"title_boundary", "organizer_boundary", "integrated_boundary"}:
        return rows
    for row in rows.values():
        if variant in {"title_boundary", "integrated_boundary"}:
            row["fields"]["nama_kegiatan_sertifikasi"] = apply_title_boundary(
                row["raw_text"], row["fields"]["nama_kegiatan_sertifikasi"]
            ).value
        if variant in {"organizer_boundary", "integrated_boundary"}:
            row["fields"]["penyelenggara_kegiatan"] = apply_organizer_boundary(
                row["raw_text"], row["fields"]["penyelenggara_kegiatan"]
            ).value
    return rows


def _summary(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['experiment_id']}",
        "",
        "- Holdout: `30` dokumen Elzandi; GT `Ground_Truth_Unified.csv`.",
        "- Prediksi sumber: checkpoint V2 Scope-Aware yang sudah ada; panggilan baru: `0`.",
        "- Matcher: `tests/matchers.py`.",
        "",
        "|Varian|All-cells exact|All-cells fuzzy|Framework exact|Framework fuzzy|Wins/Ties/Losses vs V2|",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, value in payload["variants"].items():
        metrics = value["metrics"]
        paired = value.get("paired_vs_v2")
        outcome = "control"
        if paired:
            totals = paired["document_total"]
            outcome = f"{totals['wins']}/{totals['ties']}/{totals['losses']}"
        lines.append(
            f"|{name}|{metrics['all_cells_6f']['exact_pct']}%|"
            f"{metrics['all_cells_6f']['fuzzy_pct']}%|"
            f"{metrics['framework_5f']['exact_pct']}%|"
            f"{metrics['framework_5f']['fuzzy_pct']}%|{outcome}|"
        )
    lines.extend(
        [
            "",
            "## Keputusan",
            "",
            "Boundary title dan organizer diuji pada holdout tanpa call baru. Varian dipakai sebagai bukti tambahan, bukan promosi production.",
            "",
            "- Semua field yang tidak disentuh harus identik per stem.",
            "- Review safety tidak mengubah nilai prediksi; evaluasi recall/precision tetap memakai eksperimen primary 74 dokumen.",
            "- Jika holdout berbeda dari primary, primary gate tetap menjadi pengendali keputusan karena GT v9 adalah baseline frozen.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Folder eksperimen sudah berisi artefak: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    gt_all = _load_gt()
    base_rows = _load_v2_rows()
    gt = {stem: gt_all[stem] for stem in base_rows if stem in gt_all}
    if set(base_rows) != set(gt):
        missing_gt = sorted(set(base_rows) - set(gt))
        raise ValueError(f"Stem holdout tidak ada di GT: {missing_gt}")
    for stem, row in base_rows.items():
        for field, column in GT_COLUMNS.items():
            checkpoint_gt = row["gt"][field]["gt"]
            csv_gt = gt[stem][column]
            if checkpoint_gt != csv_gt:
                raise ValueError(
                    f"GT checkpoint berbeda dari CSV pada {stem}/{field}: "
                    f"{checkpoint_gt!r} != {csv_gt!r}"
                )
    variants: dict[str, dict[str, Any]] = {}
    for name in (
        "v2_scope_aware",
        "title_boundary",
        "organizer_boundary",
        "integrated_boundary",
    ):
        metrics = _evaluate(_variant_rows(base_rows, name))
        variants[name] = {"metrics": metrics}
        if name != "v2_scope_aware":
            variants[name]["paired_vs_v2"] = _paired(
                variants["v2_scope_aware"]["metrics"], metrics
            )
    payload = {
        "experiment_id": output_dir.name,
        "source_checkpoint": str(CHECKPOINT_PATH.relative_to(REPO_ROOT)),
        "gt_csv": GT_PATH.name,
        "matcher": "tests/matchers.py",
        "new_model_calls": 0,
        "variants": variants,
    }
    (output_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "summary.md").write_text(_summary(payload), encoding="utf-8")
    manifest = {
        "experiment_id": output_dir.name,
        "step": "holdout_boundary",
        "immutable": True,
        "n_documents": 30,
        "dataset": "elzandi",
        "production_promotion": False,
        "new_model_calls": 0,
        "source_checkpoint": str(CHECKPOINT_PATH.relative_to(REPO_ROOT)),
        "gt_csv": GT_PATH.name,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs/experiments/EXP-PROD-V2-HOLDOUT-001",
    )
    args = parser.parse_args()
    run(args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
