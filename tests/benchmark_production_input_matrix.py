"""Production Input Matrix Benchmark Runner.

Exhaustive benchmark across 6 fresh PDF-to-text input variants on 74 certificates:
1. production_conditional : PyMuPDF -> OCR fallback if short/missing dates -> Gemini
2. pymupdf_only          : PyMuPDF digital text only (short-circuits empty scans)
3. rapidocr_only         : RapidOCR on all 74 documents
4. tesseract_only        : Tesseract OCR on all 74 documents (zoom 3.0, multi-PSM)
5. rapid_tesseract_only  : Merged fresh RapidOCR + Tesseract
6. always_hybrid         : Merged fresh PyMuPDF + RapidOCR + Tesseract

Evaluates 6 core fields against Ground_Truth_Sertifikat_v9.csv with Matcher v2:
- nama_kegiatan_sertifikasi
- nomor_bukti_fisik_nomor_sertifikasi
- penyelenggara_kegiatan
- waktu_mulai_pelaksanaan
- waktu_selesai_pelaksanaan
- tingkat
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root and backend are in sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.config import settings
from app.services.extraction_pipeline import run_extraction_pipeline
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.gemini_extractor import extract_fields_with_gemini
from app.services.organizer_v2 import extract_organizer_v2
from app.services.pdf_fast_path import extract_text_with_pymupdf
from tests.evaluation_framework import EVAL_FIELDS as LEGACY_5_FIELDS, load_csv, resolve_pdf_path
from tests.gemini_client import (
    DEFAULT_EXCHANGE_RATE_IDR,
    PRICING_TABLE,
    get_exchange_rate,
    load_google_api_key,
)
from tests.gemini_field_extractor import ALL_EVAL_FIELDS
from tests.matchers import match_field
from tests.ocr_engine import (
    ZOOM,
    classify_manifest,
    merge_unique_lines,
    ocr_engine,
    ocr_pdf,
)

logger = logging.getLogger("benchmark_input_matrix")

VARIANTS = [
    "production_conditional",
    "pymupdf_only",
    "rapidocr_only",
    "tesseract_only",
    "rapid_tesseract_only",
    "always_hybrid",
]

DEFAULT_GT_PATH = os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v9.csv")
DEFAULT_MANIFEST_PATH = os.path.join(REPO_ROOT, "tests", "layout_manifest.json")
DEFAULT_GT_DIR = os.path.join(REPO_ROOT, "Sertifikat_Ground_Truth")
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "tests", "benchmark_runs")


def get_git_sha() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def load_manifest(manifest_path: str = DEFAULT_MANIFEST_PATH) -> dict[str, str]:
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            raw_m = json.load(f)
        classification = classify_manifest(raw_m)
        return {
            stem: ("scan" if info.get("scan", True) else "embedded")
            for stem, info in classification.items()
        }
    return {}


def extract_fresh_text_for_engine(
    engine_key: str, file_path: str, file_bytes: bytes
) -> str:
    """Ekstraksi teks fresh langsung dari source bytes/path."""
    ext = os.path.splitext(file_path)[1].lower()
    if engine_key == "pymupdf":
        fast = extract_text_with_pymupdf(file_bytes)
        return fast.text.strip()
    elif engine_key == "rapid":
        if ext == ".png":
            return ocr_engine("rapid", file_bytes).strip()
        return ocr_pdf("rapid", file_bytes, zoom=ZOOM).strip()
    elif engine_key == "tess":
        if ext == ".png":
            return ocr_engine("tess", file_bytes).strip()
        return ocr_pdf("tess", file_bytes, zoom=ZOOM).strip()
    else:
        raise ValueError(f"Unknown engine_key: {engine_key}")


def call_gemini_with_retry(
    raw_ocr_text: str,
    api_key: str | None = None,
    model: str | None = None,
    max_retries: int = 3,
    initial_backoff: float = 2.0,
    pacing_delay: float = 1.2,
) -> tuple[dict[str, ExtractedValue] | None, dict[str, Any]]:
    """Panggil Gemini REST API dengan pacing delay dan exponential backoff retry."""
    if not raw_ocr_text.strip():
        return None, {
            "status": "skipped_empty",
            "latency_s": 0.0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "cost_usd": 0.0,
            "cost_idr": 0.0,
        }

    if pacing_delay > 0:
        time.sleep(pacing_delay)

    backoff = initial_backoff
    last_meta: dict[str, Any] = {}

    for attempt in range(1, max_retries + 1):
        extracted, meta = extract_fields_with_gemini(
            raw_ocr_text, api_key=api_key, model=model
        )
        if extracted is not None and meta.get("status") == "success":
            return extracted, meta

        last_meta = meta
        err_msg = meta.get("error", "unknown error")
        logger.warning(
            f"Gemini call attempt {attempt}/{max_retries} failed: {err_msg}. Retrying in {backoff:.1f}s..."
        )
        if attempt < max_retries:
            time.sleep(backoff)
            backoff *= 2.0

    return None, last_meta


def fallback_offline_extraction(raw_text: str) -> dict[str, ExtractedValue]:
    """Fallback deterministik offline identik dengan pipeline produksi."""
    extracted = extract_certificate_fields(raw_text)
    v2_org = extract_organizer_v2(raw_text)
    if v2_org:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(
            v2_org, 0.84, "organizer_v2"
        )
    extracted["full_text"] = ExtractedValue(raw_text, 1.0, "raw_text")
    return extracted


def evaluate_document_prediction(
    mapped_fields: dict[str, ExtractedValue],
    gt_row: dict[str, str],
) -> dict[str, Any]:
    """Evaluasi 6 field KHP terhadap Ground Truth v9."""
    eval_res: dict[str, Any] = {}
    for f in ALL_EVAL_FIELDS:
        gt_val = (gt_row.get(f) or "").strip()
        ev_obj = mapped_fields.get(f)
        pred_val = (ev_obj.value or "") if ev_obj else ""
        conf = float(ev_obj.confidence) if ev_obj else 0.0
        src = str(ev_obj.source) if ev_obj else "missing"

        m = match_field(gt_val, pred_val, f)
        eval_res[f] = {
            "gt": gt_val,
            "pred": pred_val,
            "exact": bool(m["exact"]),
            "fuzzy": bool(m["fuzzy"]),
            "wer": float(m.get("wer", 0.0)),
            "cer": float(m.get("cer", 0.0)),
            "confidence": conf,
            "source": src,
        }
    return eval_res


def compute_variant_aggregate(
    eval_list: list[dict[str, Any]],
) -> dict[str, Any]:
    """Hitung metrik all-cells (6 field) dan framework (5 field non-empty)."""
    n_docs = len(eval_list)
    if n_docs == 0:
        return {}

    # 1. All-cells 6 fields
    total_all_cells = n_docs * len(ALL_EVAL_FIELDS)
    exact_all_cells = 0
    fuzzy_all_cells = 0
    per_field_stats: dict[str, Any] = {}

    for f in ALL_EVAL_FIELDS:
        f_exact = sum(1 for e in eval_list if e["evaluation"][f]["exact"])
        f_fuzzy = sum(1 for e in eval_list if e["evaluation"][f]["fuzzy"])
        f_wer = sum(e["evaluation"][f]["wer"] for e in eval_list) / n_docs
        f_cer = sum(e["evaluation"][f]["cer"] for e in eval_list) / n_docs
        exact_all_cells += f_exact
        fuzzy_all_cells += f_fuzzy
        per_field_stats[f] = {
            "total": n_docs,
            "exact": f_exact,
            "fuzzy": f_fuzzy,
            "exact_pct": round(f_exact / n_docs * 100, 2),
            "fuzzy_pct": round(f_fuzzy / n_docs * 100, 2),
            "avg_wer": round(f_wer, 4),
            "avg_cer": round(f_cer, 4),
        }

    # 2. Framework legacy 5 fields (non-empty only)
    fw_cells_total = 0
    fw_exact_cells = 0
    fw_fuzzy_cells = 0
    missing_values_count = 0

    for e in eval_list:
        for f in LEGACY_5_FIELDS:
            gt_val = e["evaluation"][f]["gt"]
            if gt_val and gt_val != "-":
                fw_cells_total += 1
                if e["evaluation"][f]["exact"]:
                    fw_exact_cells += 1
                if e["evaluation"][f]["fuzzy"]:
                    fw_fuzzy_cells += 1
        for f in ALL_EVAL_FIELDS:
            pred_val = e["evaluation"][f]["pred"]
            if not pred_val or pred_val.strip() in ("", "-", "null"):
                missing_values_count += 1

    fw_exact_pct = (
        round(fw_exact_cells / fw_cells_total * 100, 2) if fw_cells_total else 0.0
    )
    fw_fuzzy_pct = (
        round(fw_fuzzy_cells / fw_cells_total * 100, 2) if fw_cells_total else 0.0
    )
    all_exact_pct = (
        round(exact_all_cells / total_all_cells * 100, 2) if total_all_cells else 0.0
    )
    all_fuzzy_pct = (
        round(fuzzy_all_cells / total_all_cells * 100, 2) if total_all_cells else 0.0
    )

    return {
        "n_documents": n_docs,
        "all_cells_6f": {
            "total_cells": total_all_cells,
            "exact_cells": exact_all_cells,
            "fuzzy_cells": fuzzy_all_cells,
            "exact_pct": all_exact_pct,
            "fuzzy_pct": all_fuzzy_pct,
        },
        "framework_5f": {
            "total_cells": fw_cells_total,
            "exact_cells": fw_exact_cells,
            "fuzzy_cells": fw_fuzzy_cells,
            "exact_pct": fw_exact_pct,
            "fuzzy_pct": fw_fuzzy_pct,
        },
        "missing_values": missing_values_count,
        "per_field": per_field_stats,
    }


def run_stratified_5fold(
    results: list[dict[str, Any]], seed: int = 42
) -> dict[str, Any]:
    """5-Fold CV terstratifikasi berdasarkan tipe dokumen (scan vs embedded)."""
    rng = random.Random(seed)
    scans = [r for r in results if r.get("doc_type") == "scan"]
    embedded = [r for r in results if r.get("doc_type") == "embedded"]
    others = [r for r in results if r.get("doc_type") not in ("scan", "embedded")]

    rng.shuffle(scans)
    rng.shuffle(embedded)
    rng.shuffle(others)

    k = 5
    folds: list[list[dict[str, Any]]] = [[] for _ in range(k)]
    for i, item in enumerate(scans):
        folds[i % k].append(item)
    for i, item in enumerate(embedded):
        folds[i % k].append(item)
    for i, item in enumerate(others):
        folds[i % k].append(item)

    fold_metrics = []
    for fold_idx in range(k):
        holdout = folds[fold_idx]
        total_cells = len(holdout) * len(ALL_EVAL_FIELDS)
        exact_cells = sum(
            1
            for r in holdout
            for f in ALL_EVAL_FIELDS
            if r["evaluation"][f]["exact"]
        )
        fold_acc = (exact_cells / total_cells * 100.0) if total_cells else 0.0
        fold_metrics.append({
            "fold": fold_idx + 1,
            "n_certs": len(holdout),
            "macro_exact_pct": round(fold_acc, 2),
        })

    accuracies = [fm["macro_exact_pct"] for fm in fold_metrics]
    mean_acc = sum(accuracies) / k
    variance = (
        sum((a - mean_acc) ** 2 for a in accuracies) / (k - 1) if k > 1 else 0.0
    )
    std_dev = variance ** 0.5
    return {
        "k_folds": k,
        "folds": fold_metrics,
        "mean_exact_pct": round(mean_acc, 2),
        "std_dev_pct": round(std_dev, 2),
        "min_fold_exact_pct": round(min(accuracies), 2) if accuracies else 0.0,
    }


def run_bootstrap_ci(
    results: list[dict[str, Any]], n_bootstraps: int = 1000, seed: int = 42
) -> dict[str, Any]:
    """Bootstrap 1000x resampling untuk 95% Confidence Interval."""
    rng = random.Random(seed)
    n = len(results)
    if n == 0:
        return {}

    boot_all_exact: list[float] = []
    boot_fw_exact: list[float] = []

    for _ in range(n_bootstraps):
        sample = [results[rng.randint(0, n - 1)] for _ in range(n)]
        tot_all = len(sample) * len(ALL_EVAL_FIELDS)
        ex_all = sum(
            1
            for r in sample
            for f in ALL_EVAL_FIELDS
            if r["evaluation"][f]["exact"]
        )
        boot_all_exact.append(ex_all / tot_all * 100.0 if tot_all else 0.0)

        tot_fw = 0
        ex_fw = 0
        for r in sample:
            for f in LEGACY_5_FIELDS:
                if r["evaluation"][f]["gt"] and r["evaluation"][f]["gt"] != "-":
                    tot_fw += 1
                    if r["evaluation"][f]["exact"]:
                        ex_fw += 1
        boot_fw_exact.append(ex_fw / tot_fw * 100.0 if tot_fw else 0.0)

    boot_all_exact.sort()
    boot_fw_exact.sort()
    idx_l = int(0.025 * n_bootstraps)
    idx_u = int(0.975 * n_bootstraps)

    return {
        "n_bootstraps": n_bootstraps,
        "all_cells_exact_mean_pct": round(
            sum(boot_all_exact) / n_bootstraps, 2
        ),
        "all_cells_exact_95_ci": (
            round(boot_all_exact[idx_l], 2),
            round(boot_all_exact[idx_u], 2),
        ),
        "framework_exact_mean_pct": round(
            sum(boot_fw_exact) / n_bootstraps, 2
        ),
        "framework_exact_95_ci": (
            round(boot_fw_exact[idx_l], 2),
            round(boot_fw_exact[idx_u], 2),
        ),
    }


def compute_paired_deltas(
    candidate_results: list[dict[str, Any]],
    baseline_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Hitung perbandingan paired per stem terhadap production_conditional."""
    base_map = {r["stem"]: r for r in baseline_results}
    field_deltas: dict[str, dict[str, int]] = {
        f: {"win": 0, "tie": 0, "loss": 0} for f in ALL_EVAL_FIELDS
    }
    overall_wins = 0
    overall_ties = 0
    overall_losses = 0
    scan_impact: list[dict[str, Any]] = []
    emb_impact: list[dict[str, Any]] = []

    for cand in candidate_results:
        stem = cand["stem"]
        base = base_map.get(stem)
        if not base:
            continue
        doc_type = cand.get("doc_type", "unknown")
        cand_exact_sum = sum(
            1 for f in ALL_EVAL_FIELDS if cand["evaluation"][f]["exact"]
        )
        base_exact_sum = sum(
            1 for f in ALL_EVAL_FIELDS if base["evaluation"][f]["exact"]
        )

        if cand_exact_sum > base_exact_sum:
            overall_wins += 1
        elif cand_exact_sum < base_exact_sum:
            overall_losses += 1
        else:
            overall_ties += 1

        for f in ALL_EVAL_FIELDS:
            c_ex = cand["evaluation"][f]["exact"]
            b_ex = base["evaluation"][f]["exact"]
            if c_ex and not b_ex:
                field_deltas[f]["win"] += 1
            elif not c_ex and b_ex:
                field_deltas[f]["loss"] += 1
            else:
                field_deltas[f]["tie"] += 1

        delta_info = {
            "stem": stem,
            "cand_exact": cand_exact_sum,
            "base_exact": base_exact_sum,
            "diff": cand_exact_sum - base_exact_sum,
        }
        if doc_type == "embedded" and delta_info["diff"] != 0:
            emb_impact.append(delta_info)
        elif doc_type == "scan" and delta_info["diff"] != 0:
            scan_impact.append(delta_info)

    return {
        "overall": {
            "wins": overall_wins,
            "ties": overall_ties,
            "losses": overall_losses,
        },
        "per_field": field_deltas,
        "embedded_impact": emb_impact,
        "scan_impact": scan_impact,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run fresh Production Input Matrix Benchmark across 74 certificates."
    )
    parser.add_argument(
        "--gt-csv",
        default=DEFAULT_GT_PATH,
        help="Path ke Ground_Truth_Sertifikat_v9.csv",
    )
    parser.add_argument(
        "--gt-dir",
        default=DEFAULT_GT_DIR,
        help="Direktori sumber Sertifikat_Ground_Truth",
    )
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST_PATH,
        help="Path ke layout_manifest.json",
    )
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Direktori output benchmark_runs",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi N sertifikat pertama (untuk smoke test)",
    )
    parser.add_argument(
        "--variants",
        default=",".join(VARIANTS),
        help=f"Daftar varian (default: {','.join(VARIANTS)})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.2,
        help="Jeda detik antar panggilan Gemini (pacing)",
    )
    parser.add_argument(
        "--skip-gemini",
        action="store_true",
        help="Lewatkan panggilan Gemini; gunakan offline extractor (dry run / smoke)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model Gemini yang digunakan (default: dari config.settings)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Path direktori run yang ingin di-resume",
    )

    args = parser.parse_args()

    # Pastikan API key terdeteksi jika tidak skip-gemini
    effective_key = load_google_api_key()
    if not args.skip_gemini and not effective_key:
        print(
            "ERROR: GOOGLE_API_KEY tidak ditemukan di .env.google atau environment!"
        )
        return 1

    active_variants = [
        v.strip() for v in args.variants.split(",") if v.strip() in VARIANTS
    ]
    if not active_variants:
        print(f"ERROR: Tidak ada varian valid dalam: {args.variants}")
        return 1

    # Load Ground Truth
    gt_rows = load_csv(args.gt_csv)
    if args.limit is None and len(gt_rows) != 74:
        print(
            f"ERROR: GT v9 harus berisi tepat 74 baris, ditemukan {len(gt_rows)} baris."
        )
        return 1

    if args.limit and args.limit > 0:
        gt_rows = gt_rows[: args.limit]

    manifest = load_manifest(args.manifest)

    # Verifikasi keberadaan seluruh file sumber
    sources: list[dict[str, Any]] = []
    for r in gt_rows:
        resolved = resolve_pdf_path(r, args.gt_dir)
        if not resolved or not os.path.exists(resolved):
            print(f"ERROR: File sumber tidak ditemukan untuk baris: {r}")
            return 1
        with open(resolved, "rb") as f:
            b = f.read()
        stem = os.path.splitext(os.path.basename(resolved))[0]
        sources.append({
            "gt_row": r,
            "path": resolved,
            "bytes": b,
            "sha256": sha256_bytes(b),
            "stem": stem,
            "doc_type": manifest.get(stem, "unknown"),
        })

    if args.limit is None and len(sources) != 74:
        print(
            f"ERROR: Total file sumber valid harus tepat 74, ditemukan {len(sources)}."
        )
        return 1

    # Setup run directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.resume and os.path.exists(args.resume):
        run_dir = args.resume
    else:
        run_dir = os.path.join(
            args.out_dir, f"production_input_matrix_{timestamp}"
        )
        os.makedirs(run_dir, exist_ok=True)

    raw_texts_base = os.path.join(run_dir, "raw_texts")
    for v in active_variants:
        os.makedirs(os.path.join(raw_texts_base, v), exist_ok=True)

    # Catat metadata run
    effective_model = (
        args.model or settings.google_gemini_model or "gemini-3.1-flash-lite"
    )
    if args.skip_gemini:
        object.__setattr__(settings, "enable_tesseract_gemini", False)
    run_meta = {
        "timestamp": timestamp,
        "git_sha": get_git_sha(),
        "gt_csv": args.gt_csv,
        "n_documents": len(sources),
        "active_variants": active_variants,
        "gemini_model": effective_model,
        "skip_gemini": args.skip_gemini,
        "pacing_delay": args.delay,
        "ocr_zoom": ZOOM,
        "sources_sha256": {s["stem"]: s["sha256"] for s in sources},
    }
    with open(
        os.path.join(run_dir, "run_metadata.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(run_meta, f, indent=2)

    print("=" * 70)
    print("PRODUCTION INPUT MATRIX BENCHMARK RUNNER")
    print("=" * 70)
    print(f"Run directory     : {run_dir}")
    print(f"Ground Truth      : {args.gt_csv} ({len(sources)} dokumen)")
    print(f"Active variants   : {', '.join(active_variants)}")
    print(f"Gemini Model      : {effective_model}")
    print(f"Skip Gemini (Dry) : {args.skip_gemini}")
    print(f"Pacing Delay      : {args.delay}s")
    print("=" * 70 + "\n")

    # Matriks teks fresh per file dan engine dasar
    # Kita ekstrak pymupdf, rapid, dan tess sekali per dokumen agar efisien
    fresh_texts: dict[str, dict[str, str]] = {}
    print("-> Tahap 1: Ekstraksi Teks Fresh dari Dokumen Sumber...")
    t0_ocr = time.perf_counter()
    for idx, src in enumerate(sources, 1):
        stem = src["stem"]
        fb = src["bytes"]
        fpath = src["path"]
        print(
            f"   [{idx:02d}/{len(sources):02d}] Ekstraksi fresh: {stem} ({src['doc_type']})...",
            end="",
            flush=True,
        )
        cache_dir = os.path.join(run_dir, "cache_texts")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, f"{stem}.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as cf:
                fresh_texts[stem] = json.load(cf)
        else:
            t_pymupdf = extract_fresh_text_for_engine("pymupdf", fpath, fb)
            t_rapid = extract_fresh_text_for_engine("rapid", fpath, fb)
            t_tess = extract_fresh_text_for_engine("tess", fpath, fb)
            t_rapid_tess = merge_unique_lines([t_rapid, t_tess])
            t_always_hybrid = merge_unique_lines([t_pymupdf, t_rapid_tess])
            fresh_texts[stem] = {
                "pymupdf": t_pymupdf,
                "rapid": t_rapid,
                "tess": t_tess,
                "rapid_tess": t_rapid_tess,
                "always_hybrid": t_always_hybrid,
            }
            with open(cache_file, "w", encoding="utf-8") as cf:
                json.dump(fresh_texts[stem], cf)
        print(" OK!")
    ocr_duration = time.perf_counter() - t0_ocr
    print(f"   Ekstraksi teks fresh selesai dalam {ocr_duration:.2f}s.\n")

    # Struktur penyimpan seluruh hasil
    all_results: dict[str, list[dict[str, Any]]] = {
        v: [] for v in active_variants
    }
    raw_texts_hashes: dict[str, dict[str, str]] = {
        v: {} for v in active_variants
    }

    # Tahap 2: Eksekusi Per Varian
    print("-> Tahap 2: Menjalankan Ekstraksi & Evaluasi Varian...")
    exchange_rate = get_exchange_rate()
    pricing = PRICING_TABLE.get(
        effective_model, PRICING_TABLE.get("gemini-3.1-flash-lite")
    )

    for v_idx, variant in enumerate(active_variants, 1):
        print(
            f"\n--- [{v_idx}/{len(active_variants)}] Varian: {variant} ---"
        )
        for d_idx, src in enumerate(sources, 1):
            stem = src["stem"]
            fb = src["bytes"]
            fpath = src["path"]
            gt_row = src["gt_row"]
            doc_type = src["doc_type"]

            raw_text = ""
            parser_engine_tag = variant
            call_meta: dict[str, Any] = {
                "status": "success",
                "model": effective_model,
                "latency_s": 0.0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "candidates_tokens": 0,
                "cost_usd": 0.0,
                "cost_idr": 0.0,
            }
            mapped: dict[str, ExtractedValue] = {}
            route_reason = "direct"
            if variant == "production_conditional":
                # Jalur produksi aktual: PyMuPDF -> OCR jika teks pendek/missing dates -> Gemini
                pipe_res = run_extraction_pipeline(
                    fb, tahun_akademik="2024/2025", bukti_fisik="Sertifikat"
                )
                raw_text = pipe_res.raw_text
                parser_engine_tag = pipe_res.parser_engine
                mapped = pipe_res.mapped_fields
                if pipe_res.raw_json:
                    call_meta.update(pipe_res.raw_json)
                route_reason = (
                    "ocr_triggered"
                    if "ocr" in parser_engine_tag
                    else "pymupdf_sufficient"
                )

            else:
                # 5 varian sintetis
                if variant == "pymupdf_only":
                    raw_text = fresh_texts[stem]["pymupdf"]
                elif variant == "rapidocr_only":
                    raw_text = fresh_texts[stem]["rapid"]
                elif variant == "tesseract_only":
                    raw_text = fresh_texts[stem]["tess"]
                elif variant == "rapid_tesseract_only":
                    raw_text = fresh_texts[stem]["rapid_tess"]
                elif variant == "always_hybrid":
                    raw_text = fresh_texts[stem]["always_hybrid"]
            # Simpan teks fresh ke direktori varian
            txt_save_path = os.path.join(
                raw_texts_base, variant, f"{stem}.txt"
            )
            with open(txt_save_path, "w", encoding="utf-8") as tf:
                tf.write(raw_text)

            if variant != "production_conditional":

                if args.skip_gemini:
                    # Dry run offline
                    extracted_fallback = fallback_offline_extraction(raw_text)
                    mapped = map_fields_to_form(
                        extracted_fallback,
                        tahun_akademik="2024/2025",
                        bukti_fisik="Sertifikat",
                    )
                    call_meta["status"] = "skipped_dry_run"
                else:
                    if not raw_text.strip():
                        # Short-circuit dokumen tanpa teks (49 scan di pymupdf_only)
                        extracted_empty = {
                            f: ExtractedValue(None, 0.0, "empty_input")
                            for f in ALL_EVAL_FIELDS
                        }
                        mapped = map_fields_to_form(
                            extracted_empty,
                            tahun_akademik="2024/2025",
                            bukti_fisik="Sertifikat",
                        )
                        call_meta["status"] = "skipped_empty_text"
                    else:
                        gemini_extracted, g_meta = call_gemini_with_retry(
                            raw_ocr_text=raw_text,
                            api_key=effective_key,
                            model=effective_model,
                            pacing_delay=args.delay,
                        )
                        call_meta.update(g_meta)

                        # Hitung biaya jika tersedia token usage
                        p_tok = g_meta.get("prompt_tokens", 0)
                        c_tok = g_meta.get("candidates_tokens", 0)
                        if pricing and (p_tok or c_tok):
                            usd = (
                                (p_tok * pricing.input_rate)
                                + (c_tok * pricing.output_rate)
                            ) / 1_000_000.0
                            idr = usd * exchange_rate
                            call_meta["cost_usd"] = round(usd, 6)
                            call_meta["cost_idr"] = round(idr, 2)

                        if gemini_extracted is not None:
                            mapped = map_fields_to_form(
                                gemini_extracted,
                                tahun_akademik="2024/2025",
                                bukti_fisik="Sertifikat",
                            )
                        else:
                            # Fallback offline jika Gemini error setelah retry
                            call_meta["status"] = "error"
                            call_meta["error_fallback"] = True
                            fallback_ex = fallback_offline_extraction(raw_text)
                            mapped = map_fields_to_form(
                                fallback_ex,
                                tahun_akademik="2024/2025",
                                bukti_fisik="Sertifikat",
                            )

            # Simpan hash teks mentah
            raw_texts_hashes[variant][stem] = sha256_text(raw_text)

            # Evaluasi terhadap GT
            evaluation = evaluate_document_prediction(mapped, gt_row)
            exact_count = sum(
                1 for f in ALL_EVAL_FIELDS if evaluation[f]["exact"]
            )
            fuzzy_count = sum(
                1 for f in ALL_EVAL_FIELDS if evaluation[f]["fuzzy"]
            )

            res_entry = {
                "stem": stem,
                "filename": os.path.basename(fpath),
                "doc_type": doc_type,
                "variant": variant,
                "route_reason": route_reason,
                "parser_engine": parser_engine_tag,
                "call_meta": call_meta,
                "evaluation": evaluation,
                "summary": {
                    "exact_fields": exact_count,
                    "fuzzy_fields": fuzzy_count,
                    "total_fields": len(ALL_EVAL_FIELDS),
                },
            }
            all_results[variant].append(res_entry)

            print(
                f"   [{d_idx:02d}/{len(sources):02d}] {stem} ({doc_type}): "
                f"Exact {exact_count}/6, Tok {call_meta.get('total_tokens', 0)}, "
                f"Lat {call_meta.get('latency_s', 0):.2f}s [{call_meta.get('status', 'ok')}]"
            )

    # Tahap 3: Agregasi Metrik, Paired Deltas, Bootstrap CI & 5-Fold
    print(
        "\n-> Tahap 3: Menghitung Metrik Agregat, Statistik, & Pemenang..."
    )
    summary_variants: dict[str, Any] = {}
    paired_deltas_all: dict[str, Any] = {}
    bootstrap_ci_all: dict[str, Any] = {}
    cv_5fold_all: dict[str, Any] = {}

    baseline_variant = "production_conditional"
    base_res = all_results.get(baseline_variant, [])

    for v in active_variants:
        v_res = all_results[v]
        scan_res = [r for r in v_res if r["doc_type"] == "scan"]
        emb_res = [r for r in v_res if r["doc_type"] == "embedded"]

        agg_overall = compute_variant_aggregate(v_res)
        agg_scan = compute_variant_aggregate(scan_res)
        agg_emb = compute_variant_aggregate(emb_res)

        # Statistical validation
        boot = run_bootstrap_ci(v_res, n_bootstraps=1000, seed=42)
        cv5 = run_stratified_5fold(v_res, seed=42)

        bootstrap_ci_all[v] = boot
        cv_5fold_all[v] = cv5

        # Paired deltas vs production_conditional
        if base_res and v != baseline_variant:
            p_deltas = compute_paired_deltas(v_res, base_res)
            paired_deltas_all[v] = p_deltas
        elif v == baseline_variant:
            paired_deltas_all[v] = {
                "overall": {"wins": 0, "ties": len(v_res), "losses": 0}
            }

        summary_variants[v] = {
            "overall": agg_overall,
            "scan": agg_scan,
            "embedded": agg_emb,
            "bootstrap_ci": boot,
            "stratified_5fold_cv": cv5,
            "paired_vs_production": paired_deltas_all.get(v, {}),
        }

    # Penentuan Accuracy Winner secara Deterministik:
    # 1. Framework exact tertinggi
    # 2. All-cells exact tertinggi
    # 3. Missing values terendah
    # 4. Tie-breaker: production_conditional
    def sort_key_winner(v_name: str) -> tuple[float, float, float, int]:
        s = summary_variants[v_name]["overall"]
        fw_ex = s["framework_5f"]["exact_pct"]
        all_ex = s["all_cells_6f"]["exact_pct"]
        missing = s["missing_values"]
        is_prod = 1 if v_name == baseline_variant else 0
        return (fw_ex, all_ex, -missing, is_prod)

    sorted_by_accuracy = sorted(
        active_variants, key=sort_key_winner, reverse=True
    )
    accuracy_winner = sorted_by_accuracy[0]
    print(f"\n🏆 DETERMINISTIC ACCURACY WINNER: {accuracy_winner}")
    win_fw = summary_variants[accuracy_winner]["overall"]["framework_5f"][
        "exact_pct"
    ]
    win_all = summary_variants[accuracy_winner]["overall"]["all_cells_6f"][
        "exact_pct"
    ]
    print(
        f"   Framework Exact: {win_fw:.2f}% | All-Cells Exact: {win_all:.2f}%"
    )

    # Simpan hasil-hasil artefak
    # 1. results.json
    results_path = os.path.join(run_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    # 2. summary.json
    summary_payload = {
        "run_metadata": run_meta,
        "accuracy_winner": accuracy_winner,
        "accuracy_ranking": sorted_by_accuracy,
        "variants": summary_variants,
    }
    summary_path = os.path.join(run_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    # 3. per_certificate.csv (444 baris)
    per_cert_csv_path = os.path.join(run_dir, "per_certificate.csv")
    with open(per_cert_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "stem",
            "filename",
            "doc_type",
            "variant",
            "route_reason",
            "parser_engine",
            "gemini_status",
            "latency_s",
            "total_tokens",
            "cost_idr",
            "kegiatan_pred",
            "kegiatan_gt",
            "kegiatan_match",
            "nomor_pred",
            "nomor_gt",
            "nomor_match",
            "organizer_pred",
            "organizer_gt",
            "organizer_match",
            "tgl_mulai_pred",
            "tgl_mulai_gt",
            "tgl_mulai_match",
            "tgl_selesai_pred",
            "tgl_selesai_gt",
            "tgl_selesai_match",
            "tingkat_pred",
            "tingkat_gt",
            "tingkat_match",
            "exact_fields_count",
            "fuzzy_fields_count",
        ])
        for v in active_variants:
            for r in all_results[v]:
                ev = r["evaluation"]
                writer.writerow([
                    r["stem"],
                    r["filename"],
                    r["doc_type"],
                    r["variant"],
                    r["route_reason"],
                    r["parser_engine"],
                    r["call_meta"].get("status", "ok"),
                    r["call_meta"].get("latency_s", 0.0),
                    r["call_meta"].get("total_tokens", 0),
                    r["call_meta"].get("cost_idr", 0.0),
                    ev["nama_kegiatan_sertifikasi"]["pred"],
                    ev["nama_kegiatan_sertifikasi"]["gt"],
                    "EXACT"
                    if ev["nama_kegiatan_sertifikasi"]["exact"]
                    else (
                        "FUZZY"
                        if ev["nama_kegiatan_sertifikasi"]["fuzzy"]
                        else "MISMATCH"
                    ),
                    ev["nomor_bukti_fisik_nomor_sertifikasi"]["pred"],
                    ev["nomor_bukti_fisik_nomor_sertifikasi"]["gt"],
                    "EXACT"
                    if ev["nomor_bukti_fisik_nomor_sertifikasi"]["exact"]
                    else (
                        "FUZZY"
                        if ev["nomor_bukti_fisik_nomor_sertifikasi"]["fuzzy"]
                        else "MISMATCH"
                    ),
                    ev["penyelenggara_kegiatan"]["pred"],
                    ev["penyelenggara_kegiatan"]["gt"],
                    "EXACT"
                    if ev["penyelenggara_kegiatan"]["exact"]
                    else (
                        "FUZZY"
                        if ev["penyelenggara_kegiatan"]["fuzzy"]
                        else "MISMATCH"
                    ),
                    ev["waktu_mulai_pelaksanaan"]["pred"],
                    ev["waktu_mulai_pelaksanaan"]["gt"],
                    "EXACT"
                    if ev["waktu_mulai_pelaksanaan"]["exact"]
                    else (
                        "FUZZY"
                        if ev["waktu_mulai_pelaksanaan"]["fuzzy"]
                        else "MISMATCH"
                    ),
                    ev["waktu_selesai_pelaksanaan"]["pred"],
                    ev["waktu_selesai_pelaksanaan"]["gt"],
                    "EXACT"
                    if ev["waktu_selesai_pelaksanaan"]["exact"]
                    else (
                        "FUZZY"
                        if ev["waktu_selesai_pelaksanaan"]["fuzzy"]
                        else "MISMATCH"
                    ),
                    ev["tingkat"]["pred"],
                    ev["tingkat"]["gt"],
                    "EXACT"
                    if ev["tingkat"]["exact"]
                    else (
                        "FUZZY" if ev["tingkat"]["fuzzy"] else "MISMATCH"
                    ),
                    r["summary"]["exact_fields"],
                    r["summary"]["fuzzy_fields"],
                ])

    # 4. mismatches.csv
    mismatches_path = os.path.join(run_dir, "mismatches.csv")
    with open(mismatches_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "variant",
            "stem",
            "doc_type",
            "field",
            "predicted",
            "ground_truth",
            "wer",
            "cer",
        ])
        for v in active_variants:
            for r in all_results[v]:
                for fld in ALL_EVAL_FIELDS:
                    ev_f = r["evaluation"][fld]
                    if not ev_f["exact"]:
                        writer.writerow([
                            v,
                            r["stem"],
                            r["doc_type"],
                            fld,
                            ev_f["pred"],
                            ev_f["gt"],
                            ev_f["wer"],
                            ev_f["cer"],
                        ])

    # 5. summary.md
    summary_md_path = os.path.join(run_dir, "summary.md")
    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write("# Production Input Matrix Benchmark Summary\n\n")
        f.write(
            f"- **Timestamp**: {timestamp} | **Git SHA**: `{get_git_sha()[:8]}`\n"
        )
        f.write(
            f"- **Gemini Model**: `{effective_model}` | **Documents**: {len(sources)}\n"
        )
        f.write(f"- **Accuracy Winner**: **`{accuracy_winner}`**\n\n")
        f.write("## 1. Komparasi Makro Antar Varian\n\n")
        f.write(
            "| Varian | Framework Exact | All-Cells Exact | Fuzzy 6F | Scan-49 Exact | Emb-25 Exact | Missing | 95% CI All-Cells |\n"
        )
        f.write(
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        )
        for v in sorted_by_accuracy:
            s_all = summary_variants[v]["overall"]
            s_scan = summary_variants[v]["scan"]
            s_emb = summary_variants[v]["embedded"]
            ci = summary_variants[v]["bootstrap_ci"].get(
                "all_cells_exact_95_ci", (0, 0)
            )
            scan_str = f"{s_scan['all_cells_6f']['exact_pct']}%" if s_scan.get("all_cells_6f") else "—"
            emb_str = f"{s_emb['all_cells_6f']['exact_pct']}%" if s_emb.get("all_cells_6f") else "—"
            f.write(
                f"| **{v}** | {s_all['framework_5f']['exact_pct']}% | "
                f"**{s_all['all_cells_6f']['exact_pct']}%** | {s_all['all_cells_6f']['fuzzy_pct']}% | "
                f"{scan_str} | {emb_str} | "
                f"{s_all['missing_values']} | [{ci[0]}%, {ci[1]}%] |\n"
            )

        f.write("\n## 2. Akurasi Per Field (All-Cells 6-Field)\n\n")
        f.write(
            "| Varian | Kegiatan | Nomor | Penyelenggara | Tgl Mulai | Tgl Selesai | Tingkat |\n"
        )
        f.write(
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|\n"
        )
        for v in sorted_by_accuracy:
            pf = summary_variants[v]["overall"]["per_field"]
            f.write(
                f"| **{v}** | {pf['nama_kegiatan_sertifikasi']['exact_pct']}% | "
                f"{pf['nomor_bukti_fisik_nomor_sertifikasi']['exact_pct']}% | "
                f"{pf['penyelenggara_kegiatan']['exact_pct']}% | "
                f"{pf['waktu_mulai_pelaksanaan']['exact_pct']}% | "
                f"{pf['waktu_selesai_pelaksanaan']['exact_pct']}% | "
                f"{pf['tingkat']['exact_pct']}% |\n"
            )

        f.write("\n## 3. Paired Delta vs Production Conditional\n\n")
        f.write("| Varian | Wins | Ties | Losses | Embedded Impact |\n")
        f.write("|---|:---:|:---:|:---:|:---:|\n")
        for v in sorted_by_accuracy:
            if v == baseline_variant:
                f.write(f"| **{v}** (Baseline) | — | {len(sources)} | — | Control |\n")
            else:
                pd = paired_deltas_all.get(v, {}).get("overall", {})
                emb_imp = len(paired_deltas_all.get(v, {}).get("embedded_impact", []))
                f.write(
                    f"| **{v}** | +{pd.get('wins', 0)} | {pd.get('ties', 0)} | "
                    f"-{pd.get('losses', 0)} | {emb_imp} certs affected |\n"
                )

    print("\n" + "=" * 70)
    print(f"BENCHMARK SELESAI! Artefak tersimpan di: {run_dir}")
    print(f"1. Results JSON  : {results_path}")
    print(f"2. Summary JSON  : {summary_path}")
    print(f"3. Per Cert CSV  : {per_cert_csv_path}")
    print(f"4. Mismatches CSV: {mismatches_path}")
    print(f"5. Summary MD    : {summary_md_path}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
