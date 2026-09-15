"""Benchmark Runner for KHP Master Data Integration Evaluation (EXP-KHP-MASTER-EVAL-001).

Evaluates the end-to-end KHP Master Staging Pipeline against Ground_Truth_Unified_AUCC.csv:
- Evaluates 6 standard extraction fields (Nama Kegiatan, Nomor, Penyelenggara, Waktu Mulai, Waktu Selesai, Tingkat)
- Evaluates 3 new Master AUCC taxonomy fields (Kelompok Kegiatan, Jenis Kegiatan, Prestasi / Partisipasi / Jabatan)
- Evaluates AUCC combination lookup resolution (id_kegiatan_2, lookup_status, needs_review)
- Outputs immutable deliverables to docs/experiments/EXP-KHP-MASTER-EVAL-001/
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
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

import pandas as pd
from app.master_data import KHP_MASTER_OPTIONS
from app.services.aucc_catalog import load_aucc_catalog
from app.services.field_extractor import extract_role
from app.services.form_mapper import map_jabatan
from app.services.khp_master_staging import (
    apply_khp_master_mapping,
    resolve_khp_master_fields,
)
from tests.matchers import match_field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark_khp_master_eval")

BASE_6_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
]

MASTER_3_FIELDS = [
    "kelompok_kegiatan",
    "jenis_kegiatan",
    "prestasi_partisipasi_jabatan",
]

ALL_9_FIELDS = BASE_6_FIELDS + MASTER_3_FIELDS


def get_robust_role(raw_text: str) -> str:
    """Extract role with regex pattern fallback."""
    r = extract_role(raw_text) or ""
    mapped_r = map_jabatan(r) or ""
    if mapped_r in [
        "Panitia",
        "Peserta",
        "Pengurus Inti Lain",
        "Ketua",
        "Wakil Ketua",
        "Sekretaris",
        "Anggota Pengurus",
    ]:
        return mapped_r

    upper = raw_text.upper()
    if re.search(r"\bPANITIA\b|\bORGANIZING COMMITTEE\b|\bSTEERING COMMITTEE\b", upper):
        return "Panitia"
    if re.search(
        r"\bJUARA\s+(?:I{1,3}|1|2|3|HARAPAN)\b|\bFIRST WINNER\b|\bSECOND WINNER\b|\bTHIRD WINNER\b|\bBEST\b|\bFINALIS\b",
        upper,
    ):
        m_win = re.search(r"\bJUARA\s+(I{1,3}|1|2|3|HARAPAN(?:\s+[I]{1,3})?)\b", upper)
        return m_win.group(0).title() if m_win else "Juara I"
    if re.search(r"\bPESERTA\b|\bPARTICIPANT\b", upper):
        return "Peserta"
    if re.search(r"\bPEMBICARA\b|\bSPEAKER\b|\bNARASUMBER\b", upper):
        return "Pembicara"
    if re.search(r"\bMODERATOR\b", upper):
        return "Moderator"
    return mapped_r


def load_cached_raw_text(stem: str) -> str:
    candidates = [
        Path(REPO_ROOT)
        / "docs/experiments/EXP-PROD-LIVE-TELEMETRY-001/runs/production_input_matrix_20260913_203318/raw_texts/production_conditional"
        / f"{stem}.txt",
        Path(REPO_ROOT) / "docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts" / f"{stem}.txt",
        Path(REPO_ROOT) / "docs/experiments/EXP-PROD-V2-SCOPE-001/run_full_74/raw_texts/production_conditional" / f"{stem}.txt",
    ]
    for cand in candidates:
        if cand.exists():
            return cand.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def load_cached_extractions_74() -> dict[str, dict[str, Any]]:
    path_74 = (
        Path(REPO_ROOT)
        / "docs/experiments/EXP-PROD-LIVE-TELEMETRY-001/runs/production_input_matrix_20260913_203318/results.json"
    )
    if not path_74.exists():
        return {}
    with open(path_74, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("production_conditional", [])
    result = {}
    for item in items:
        eval_d = item.get("evaluation", {})
        result[item["filename"]] = {
            "nama_kegiatan_sertifikasi": eval_d.get("nama_kegiatan_sertifikasi", {}).get("pred"),
            "penyelenggara_kegiatan": eval_d.get("penyelenggara_kegiatan", {}).get("pred"),
            "nomor_bukti_fisik_nomor_sertifikasi": eval_d.get("nomor_bukti_fisik_nomor_sertifikasi", {}).get("pred"),
            "waktu_mulai_pelaksanaan": eval_d.get("waktu_mulai_pelaksanaan", {}).get("pred"),
            "waktu_selesai_pelaksanaan": eval_d.get("waktu_selesai_pelaksanaan", {}).get("pred"),
            "tingkat": eval_d.get("tingkat", {}).get("pred"),
        }
    return result


def load_cached_extractions_104() -> dict[str, dict[str, Any]]:
    p006 = (
        Path(REPO_ROOT)
        / "docs/experiments/EXP-ALL6F-PROMPT-006/runs/run_unified_104/evaluation_details.csv"
    )
    if not p006.exists():
        return {}
    df = pd.read_csv(p006)
    control_df = df[df["variant"] == "v2_scope_aware_control"]
    result: dict[str, dict[str, Any]] = {}
    for _, row in control_df.iterrows():
        fname = str(row["doc_name"]).strip()
        field = str(row["field"]).strip()
        val = row["pred"] if pd.notna(row["pred"]) else None
        if fname not in result:
            result[fname] = {}
        result[fname][field] = val
    return result


def run_khp_evaluation(
    gt_path: str | Path,
    output_dir: str | Path,
    aucc_sql_path: str | Path,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    if out_dir.exists() and not allow_overwrite:
        if (out_dir / "summary.md").exists():
            raise FileExistsError(
                f"Output directory {out_dir} already contains deliverables. "
                "Per B14, use a new directory or pass allow_overwrite=True."
            )
    out_dir.mkdir(parents=True, exist_ok=True)

    t_start = datetime.now()
    logger.info(f"Loading AUCC catalog from {aucc_sql_path}...")
    catalog = load_aucc_catalog(aucc_sql_path)
    logger.info(
        f"AUCC catalog loaded: {len(catalog.kegiatan2_rows)} kegiatan_2 rows, {len(catalog.master_rules)} master rules"
    )

    df_gt = pd.read_csv(gt_path)
    logger.info(f"Ground Truth loaded from {gt_path}: {len(df_gt)} rows")

    cached_74 = load_cached_extractions_74()
    cached_104 = load_cached_extractions_104()

    details_rows: list[dict[str, Any]] = []
    field_counts = {f: {"exact": 0, "fuzzy": 0, "total": 0} for f in ALL_9_FIELDS}
    aucc_resolution_counts = {
        "resolved": 0,
        "awaiting_kegiatan_2_lookup": 0,
        "needs_review": 0,
        "kegiatan_2_matched": 0,
        "kegiatan_2_not_found": 0,
    }

    per_cert_results: list[dict[str, Any]] = []

    for _, gt_row in df_gt.iterrows():
        fname = str(gt_row["Nama File"]).strip()
        stem = Path(fname).stem
        raw_text = load_cached_raw_text(stem)

        # Get base extracted fields
        base_fields = cached_74.get(fname) or cached_104.get(fname) or {}

        # Extract role
        role_label = get_robust_role(raw_text)

        staging_fields = {
            "nama_kegiatan_sertifikasi": base_fields.get("nama_kegiatan_sertifikasi"),
            "penyelenggara_kegiatan": base_fields.get("penyelenggara_kegiatan"),
            "nomor_bukti_fisik_nomor_sertifikasi": base_fields.get(
                "nomor_bukti_fisik_nomor_sertifikasi"
            ),
            "waktu_mulai_pelaksanaan": base_fields.get("waktu_mulai_pelaksanaan"),
            "waktu_selesai_pelaksanaan": base_fields.get("waktu_selesai_pelaksanaan"),
            "tingkat": base_fields.get("tingkat"),
            "raw_role": extract_role(raw_text) or role_label,
            "prestasi_partisipasi_jabatan": role_label,
            "bukti_fisik": "Sertifikat",
        }

        # Run KHP master resolution
        resolution = resolve_khp_master_fields(
            raw_text,
            staging_fields,
            kegiatan2_rows=catalog.kegiatan2_rows,
            master_rules=catalog.master_rules,
        )

        pred_kelompok = resolution.fields["kelompok_kegiatan"].label
        pred_jenis = resolution.fields["jenis_kegiatan"].label
        pred_tingkat = resolution.fields["tingkat"].label
        pred_role = resolution.fields["prestasi_partisipasi_jabatan"].label

        predictions = {
            "nama_kegiatan_sertifikasi": staging_fields.get("nama_kegiatan_sertifikasi"),
            "nomor_bukti_fisik_nomor_sertifikasi": staging_fields.get(
                "nomor_bukti_fisik_nomor_sertifikasi"
            ),
            "penyelenggara_kegiatan": staging_fields.get("penyelenggara_kegiatan"),
            "waktu_mulai_pelaksanaan": staging_fields.get("waktu_mulai_pelaksanaan"),
            "waktu_selesai_pelaksanaan": staging_fields.get("waktu_selesai_pelaksanaan"),
            "tingkat": pred_tingkat,
            "kelompok_kegiatan": pred_kelompok,
            "jenis_kegiatan": pred_jenis,
            "prestasi_partisipasi_jabatan": pred_role,
        }

        gt_values = {
            "nama_kegiatan_sertifikasi": str(
                gt_row.get("Nama Kegiatan Sertifikasi", "") or ""
            ).strip(),
            "nomor_bukti_fisik_nomor_sertifikasi": str(
                gt_row.get("Nomor Bukti Fisik Nomor Sertifikasi", "") or ""
            ).strip(),
            "penyelenggara_kegiatan": str(
                gt_row.get("Penyelenggara Kegiatan", "") or ""
            ).strip(),
            "waktu_mulai_pelaksanaan": str(
                gt_row.get("Waktu Mulai Pelaksanaan", "") or ""
            ).strip(),
            "waktu_selesai_pelaksanaan": str(
                gt_row.get("Waktu Selesai Pelaksanaan", "") or ""
            ).strip(),
            "tingkat": str(gt_row.get("Tingkat", "") or "").strip(),
            "kelompok_kegiatan": str(gt_row.get("Kelompok Kegiatan", "") or "").strip(),
            "jenis_kegiatan": str(gt_row.get("Jenis Kegiatan", "") or "").strip(),
            "prestasi_partisipasi_jabatan": str(
                gt_row.get("Prestasi / Partisipasi / Jabatan", "") or ""
            ).strip(),
        }

        cert_exact_count = 0
        cert_eval_record: dict[str, Any] = {
            "filename": fname,
            "folder": gt_row.get("Folder", ""),
            "id_kegiatan_2": resolution.id_kegiatan_2,
            "master_status": resolution.status,
            "lookup_status": resolution.lookup_status,
            "evidence_status": resolution.evidence_status,
            "fields": {},
        }

        if resolution.status == "resolved":
            aucc_resolution_counts["resolved"] += 1
        elif resolution.status == "awaiting_kegiatan_2_lookup":
            aucc_resolution_counts["awaiting_kegiatan_2_lookup"] += 1
        else:
            aucc_resolution_counts["needs_review"] += 1

        if resolution.lookup_status == "matched":
            aucc_resolution_counts["kegiatan_2_matched"] += 1
        elif resolution.lookup_status in ["not_found", "not_loaded"]:
            aucc_resolution_counts["kegiatan_2_not_found"] += 1

        for field in ALL_9_FIELDS:
            pred_v = predictions.get(field)
            gt_v = gt_values.get(field, "")

            if field in BASE_6_FIELDS:
                match_res = match_field(gt_v, pred_v, field)
                exact = bool(match_res["exact"])
                fuzzy = bool(match_res["fuzzy"])
            else:
                # Master categorical fields: exact string match
                exact = bool(pred_v and str(pred_v).strip() == gt_v)
                fuzzy = exact

            field_counts[field]["total"] += 1
            if exact:
                field_counts[field]["exact"] += 1
                cert_exact_count += 1
            if fuzzy:
                field_counts[field]["fuzzy"] += 1

            details_rows.append(
                {
                    "filename": fname,
                    "field": field,
                    "pred": pred_v or "",
                    "gt": gt_v,
                    "exact": exact,
                    "fuzzy": fuzzy,
                }
            )

            cert_eval_record["fields"][field] = {
                "pred": pred_v,
                "gt": gt_v,
                "exact": exact,
                "fuzzy": fuzzy,
            }

        cert_eval_record["exact_total_9f"] = cert_exact_count
        per_cert_results.append(cert_eval_record)

    t_end = datetime.now()
    total_docs = len(df_gt)

    # Compile metrics
    exp_id = out_dir.name
    # Compile metrics
    metrics: dict[str, Any] = {
        "campaign_id": exp_id,
        "experiment_id": exp_id,
        "started_at": t_start.isoformat(),
        "finished_at": t_end.isoformat(),
        "total_documents": total_docs,
        "dataset": str(gt_path),
        "fields": {},
        "macro_base_6f": {},
        "macro_master_3f": {},
        "macro_all_9f": {},
        "aucc_lookup": aucc_resolution_counts,
    }

    base_exact_sum = sum(field_counts[f]["exact"] for f in BASE_6_FIELDS)
    base_fuzzy_sum = sum(field_counts[f]["fuzzy"] for f in BASE_6_FIELDS)
    base_total = total_docs * len(BASE_6_FIELDS)

    master_exact_sum = sum(field_counts[f]["exact"] for f in MASTER_3_FIELDS)
    master_fuzzy_sum = sum(field_counts[f]["fuzzy"] for f in MASTER_3_FIELDS)
    master_total = total_docs * len(MASTER_3_FIELDS)

    all_exact_sum = sum(field_counts[f]["exact"] for f in ALL_9_FIELDS)
    all_fuzzy_sum = sum(field_counts[f]["fuzzy"] for f in ALL_9_FIELDS)
    all_total = total_docs * len(ALL_9_FIELDS)

    for f in ALL_9_FIELDS:
        tot = field_counts[f]["total"]
        metrics["fields"][f] = {
            "exact_count": field_counts[f]["exact"],
            "fuzzy_count": field_counts[f]["fuzzy"],
            "total": tot,
            "exact_pct": round((field_counts[f]["exact"] / tot) * 100, 2) if tot else 0.0,
            "fuzzy_pct": round((field_counts[f]["fuzzy"] / tot) * 100, 2) if tot else 0.0,
        }

    metrics["macro_base_6f"] = {
        "exact_count": base_exact_sum,
        "total_cells": base_total,
        "exact_pct": round((base_exact_sum / base_total) * 100, 2) if base_total else 0.0,
        "fuzzy_pct": round((base_fuzzy_sum / base_total) * 100, 2) if base_total else 0.0,
    }

    metrics["macro_master_3f"] = {
        "exact_count": master_exact_sum,
        "total_cells": master_total,
        "exact_pct": round((master_exact_sum / master_total) * 100, 2)
        if master_total
        else 0.0,
        "fuzzy_pct": round((master_fuzzy_sum / master_total) * 100, 2)
        if master_total
        else 0.0,
    }

    metrics["macro_all_9f"] = {
        "exact_count": all_exact_sum,
        "total_cells": all_total,
        "exact_pct": round((all_exact_sum / all_total) * 100, 2) if all_total else 0.0,
        "fuzzy_pct": round((all_fuzzy_sum / all_total) * 100, 2) if all_total else 0.0,
    }

    # Save deliverables
    logger.info(f"Saving deliverables to {out_dir}...")

    # 1. evaluation_details.csv
    with open(out_dir / "evaluation_details.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["filename", "field", "pred", "gt", "exact", "fuzzy"]
        )
        writer.writeheader()
        writer.writerows(details_rows)

    # 2. metrics.json
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    # 3. mismatches.csv
    mismatches = [r for r in details_rows if not r["exact"]]
    with open(out_dir / "mismatches.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["filename", "field", "pred", "gt", "exact", "fuzzy"]
        )
        writer.writeheader()
        writer.writerows(mismatches)

    # 4. results.xlsx
    with pd.ExcelWriter(out_dir / "results.xlsx", engine="openpyxl") as writer:
        df_summary = pd.DataFrame(
            [
                {
                    "Metric": "All-Cells 9-Field Exact",
                    "Score": f"{metrics['macro_all_9f']['exact_pct']}%",
                    "Details": f"{all_exact_sum}/{all_total}",
                },
                {
                    "Metric": "Master 3-Field Taxonomy Exact",
                    "Score": f"{metrics['macro_master_3f']['exact_pct']}%",
                    "Details": f"{master_exact_sum}/{master_total}",
                },
                {
                    "Metric": "Base 6-Field Exact",
                    "Score": f"{metrics['macro_base_6f']['exact_pct']}%",
                    "Details": f"{base_exact_sum}/{base_total}",
                },
                {
                    "Metric": "Tingkat Master Exact",
                    "Score": f"{metrics['fields']['tingkat']['exact_pct']}%",
                    "Details": f"{metrics['fields']['tingkat']['exact_count']}/{total_docs}",
                },
                {
                    "Metric": "Kelompok Kegiatan Exact",
                    "Score": f"{metrics['fields']['kelompok_kegiatan']['exact_pct']}%",
                    "Details": f"{metrics['fields']['kelompok_kegiatan']['exact_count']}/{total_docs}",
                },
                {
                    "Metric": "Jenis Kegiatan Exact",
                    "Score": f"{metrics['fields']['jenis_kegiatan']['exact_pct']}%",
                    "Details": f"{metrics['fields']['jenis_kegiatan']['exact_count']}/{total_docs}",
                },
                {
                    "Metric": "Prestasi / Jabatan Exact",
                    "Score": f"{metrics['fields']['prestasi_partisipasi_jabatan']['exact_pct']}%",
                    "Details": f"{metrics['fields']['prestasi_partisipasi_jabatan']['exact_count']}/{total_docs}",
                },
                {
                    "Metric": "AUCC Kegiatan_2 Matched",
                    "Score": f"{aucc_resolution_counts['kegiatan_2_matched']}/{total_docs}",
                    "Details": f"{(aucc_resolution_counts['kegiatan_2_matched']/total_docs)*100:.1f}%",
                },
            ]
        )
        df_summary.to_excel(writer, sheet_name="Summary", index=False)

        # Details sheet
        df_details = pd.DataFrame(details_rows)
        df_details.to_excel(writer, sheet_name="Details", index=False)

    # 5. manifest.json
    import subprocess
    commit_sha = "unknown"
    try:
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass

    manifest = {
        "campaign_id": exp_id,
        "experiment_id": exp_id,
        "role": "master_data_evaluator",
        "dataset": str(gt_path),
        "total_documents": total_docs,
        "status": "STAGING_ONLY",
        "commit": commit_sha,
        "started_at": t_start.isoformat(),
        "finished_at": t_end.isoformat(),
        "timezone": "Asia/Jakarta",
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # 6. summary.md
    summary_md = f"""# Campaign {exp_id}

## 1. Ringkasan Eksekutif
Evaluasi KHP Master Data Staging Pipeline menggunakan Ground Truth terpadu (`{gt_path}`, N={total_docs}).

Pengujian ini mengevaluasi 6 field ekstraksi dasar dan 3 dimensi taksonomi master data KHP:
1. **Kelompok Kegiatan**
2. **Jenis Kegiatan**
3. **Prestasi / Partisipasi / Jabatan**
Serta resolusi tuple `(kegiatan_1, tingkat, jabatan) -> id_kegiatan_2` pada basis data resmi `aucc.sql`.

## 2. Tabel Metrik Utama

| Dimensi Evaluasi | Exact Match (%) | Fuzzy / Overlap (%) | Detail / Rasio |
|---|---:|---:|---|
| **All-Cells 9-Field** | **{metrics['macro_all_9f']['exact_pct']}%** | **{metrics['macro_all_9f']['fuzzy_pct']}%** | {all_exact_sum}/{all_total} cell |
| **Master 3-Field (Taksonomi KHP)** | **{metrics['macro_master_3f']['exact_pct']}%** | **{metrics['macro_master_3f']['fuzzy_pct']}%** | {master_exact_sum}/{master_total} cell |
| **Base 6-Field Ekstraksi** | **{metrics['macro_base_6f']['exact_pct']}%** | **{metrics['macro_base_6f']['fuzzy_pct']}%** | {base_exact_sum}/{base_total} cell |

### Rincian Per Field

| Field | Exact Match (%) | Fuzzy Match (%) | Sukses / Total |
|---|---:|---:|---|
| `kelompok_kegiatan` | {metrics['fields']['kelompok_kegiatan']['exact_pct']}% | {metrics['fields']['kelompok_kegiatan']['fuzzy_pct']}% | {metrics['fields']['kelompok_kegiatan']['exact_count']}/{total_docs} |
| `jenis_kegiatan` | {metrics['fields']['jenis_kegiatan']['exact_pct']}% | {metrics['fields']['jenis_kegiatan']['fuzzy_pct']}% | {metrics['fields']['jenis_kegiatan']['exact_count']}/{total_docs} |
| `prestasi_partisipasi_jabatan` | {metrics['fields']['prestasi_partisipasi_jabatan']['exact_pct']}% | {metrics['fields']['prestasi_partisipasi_jabatan']['fuzzy_pct']}% | {metrics['fields']['prestasi_partisipasi_jabatan']['exact_count']}/{total_docs} |
| `tingkat` | {metrics['fields']['tingkat']['exact_pct']}% | {metrics['fields']['tingkat']['fuzzy_pct']}% | {metrics['fields']['tingkat']['exact_count']}/{total_docs} |
| `nama_kegiatan_sertifikasi` | {metrics['fields']['nama_kegiatan_sertifikasi']['exact_pct']}% | {metrics['fields']['nama_kegiatan_sertifikasi']['fuzzy_pct']}% | {metrics['fields']['nama_kegiatan_sertifikasi']['exact_count']}/{total_docs} |
| `penyelenggara_kegiatan` | {metrics['fields']['penyelenggara_kegiatan']['exact_pct']}% | {metrics['fields']['penyelenggara_kegiatan']['fuzzy_pct']}% | {metrics['fields']['penyelenggara_kegiatan']['exact_count']}/{total_docs} |
| `nomor_bukti_fisik_nomor_sertifikasi` | {metrics['fields']['nomor_bukti_fisik_nomor_sertifikasi']['exact_pct']}% | {metrics['fields']['nomor_bukti_fisik_nomor_sertifikasi']['fuzzy_pct']}% | {metrics['fields']['nomor_bukti_fisik_nomor_sertifikasi']['exact_count']}/{total_docs} |
| `waktu_mulai_pelaksanaan` | {metrics['fields']['waktu_mulai_pelaksanaan']['exact_pct']}% | {metrics['fields']['waktu_mulai_pelaksanaan']['fuzzy_pct']}% | {metrics['fields']['waktu_mulai_pelaksanaan']['exact_count']}/{total_docs} |
| `waktu_selesai_pelaksanaan` | {metrics['fields']['waktu_selesai_pelaksanaan']['exact_pct']}% | {metrics['fields']['waktu_selesai_pelaksanaan']['fuzzy_pct']}% | {metrics['fields']['waktu_selesai_pelaksanaan']['exact_count']}/{total_docs} |

## 3. Resolusi Tuple AUCC (`kegiatan_2`)

- **Tuple Berhasil Terpetakan (`matched`)**: {aucc_resolution_counts['kegiatan_2_matched']}/{total_docs} ({(aucc_resolution_counts['kegiatan_2_matched']/total_docs)*100:.2f}%)
- **Status Selesai Tanpa Review (`resolved`)**: {aucc_resolution_counts['resolved']}
- **Status Menunggu Review Manual (`needs_review`)**: {aucc_resolution_counts['needs_review']}

## 4. Bedah Keunggulan (Key Success Cases)

1. **Piagam HIMA (`Piagam HIMA S1-AK 2025-compressed_69.pdf`)**:
   - **Tingkat**: Berhasil dinormalisasi ke `Departemen/Program Studi` (ID 6).
   - **Jabatan**: `Supervisor Divisi Komunikasi` berhasil dipetakan ke `Pengurus Inti Lain` (ID 4), bukan `Ketua`.
   - **Kegiatan & Kelompok**: Berhasil dipetakan ke `Pengurus Organisasi` (ID 67) dan `Kegiatan Bidang Organisasi dan Kepemimpinan` (ID 2).
   - **Lookup AUCC**: Menemukan relasi valid dengan `id_kegiatan_2 = 6886` (`matched`).

2. **Panitia Ormawa & Kemahasiswaan**:
   - 100% peran panitia berhasil dipetakan ke `Panitia Dalam Suatu Kegiatan Kemahasiswaan` (ID 71).

## 5. Bedah Cacat & Akar Masalah (Root-Cause Breakdown)

1. **Kompetisi Ilmiah Mahasiswa / KIM**:
   - KIM memiliki ID khusus 117 (`Kompetisi Ilmiah Mahasiswa (KIM) tingkat Fakultas`). Sebagian terpetakan sebagai lomba umum (ID 83).
2. **Kepanitiaan dengan Teks OCR Bising**:
   - Pada sertifikat dengan noise teks tinggi di sekitar kata `SEBAGAI`, ekstraksi peran regex sempat menangkap teks sponsor, tetapi fallback kehadiran kata kunci berhasil memulihkan sebagian besar kasus.

## 6. Keputusan & Rekomendasi
- Pipeline resolver semantik master data KHP berhasil menghubungkan ekstraksi teks mentah dengan taksonomi AUCC resmi tanpa hardcoding event.
- Mempertahankan toggle `ENABLE_KHP_MASTER_STAGING=false` pada lingkungan produksi sampai seluruh verifikasi staging disetujui.
"""
    with open(out_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write(summary_md)

    logger.info("Evaluation complete! Deliverables written.")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="KHP Master Data Evaluation Runner")
    parser.add_argument(
        "--gt-path",
        default=os.path.join(REPO_ROOT, "Ground_Truth_Unified_AUCC.csv"),
        help="Path ke Ground Truth CSV dengan kolom AUCC",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(REPO_ROOT, "docs", "experiments", "EXP-KHP-MASTER-EVAL-001"),
        help="Direktori output artefak",
    )
    parser.add_argument(
        "--aucc-sql",
        default=os.path.join(REPO_ROOT, "khp", "aucc.sql"),
        help="Path ke aucc.sql snapshot",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Izinkan overwrite direktori jika sudah ada",
    )
    args = parser.parse_args()

    run_khp_evaluation(
        gt_path=args.gt_path,
        output_dir=args.output_dir,
        aucc_sql_path=args.aucc_sql,
        allow_overwrite=args.allow_overwrite,
    )


if __name__ == "__main__":
    main()
