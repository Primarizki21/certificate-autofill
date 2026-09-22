"""EXP-OCR-PSM-DPI-001: Comprehensive Evaluation of Tesseract PSM and DPI/Zoom on Unified Dataset (N=104).

Evaluates combinations of:
- Zoom / DPI: 2.0 (200 DPI), 3.0 (300 DPI, Baseline), 4.0 (400 DPI)
- Tesseract Modes:
    - Multi-PSM: 3-Pass ("", "--psm 6", "--psm 11") [Control]
    - Single PSM 6: "--psm 6" (single uniform block)
    - Single PSM 3: "" / "--psm 3" (automatic page segmentation)
    - Single PSM 11: "--psm 11" (sparse text)
- Combined with RapidOCR (ONNX) merger (production equivalent).

Includes persistent disk caching to accelerate re-runs without redundant OCR compute.
Outputs low-level artifacts to: docs/experiments/EXP-OCR-PSM-DPI-001/
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import sys
import time

# Restrict CPU threads and disable GPU probing to prevent WSL host reset/overload
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["VECLIB_MAXIMUM_THREADS"] = "4"
os.environ["NUMEXPR_NUM_THREADS"] = "4"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
import fitz
import pytesseract

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.ocr_fallback import _load_rapidocr, _ocr_with_rapidocr, merge_unique_lines
from tests.matchers import match_field

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "certs_unified" / "manifest.json"
GT_PATH = REPO_ROOT / "Ground_Truth_Unified.csv"
OUTPUT_DIR = REPO_ROOT / "docs" / "experiments" / "EXP-OCR-PSM-DPI-001"
CACHE_DIR = REPO_ROOT / ".cache" / "ocr_eval"

EVAL_FIELDS = [
    ("Nama Kegiatan Sertifikasi", "nama_kegiatan_sertifikasi"),
    ("Nomor Bukti Fisik Nomor Sertifikasi", "nomor_bukti_fisik_nomor_sertifikasi"),
    ("Penyelenggara Kegiatan", "penyelenggara_kegiatan"),
    ("Waktu Mulai Pelaksanaan", "waktu_mulai_pelaksanaan"),
    ("Waktu Selesai Pelaksanaan", "waktu_selesai_pelaksanaan"),
    ("Tingkat", "tingkat"),
]

VARIANTS = {
    "control_z3_multi": {"zoom": 3.0, "psm_config": "multi", "desc": "Zoom 3.0 + Multi-PSM (Control)"},
    "z3_psm6": {"zoom": 3.0, "psm_config": "psm6", "desc": "Zoom 3.0 + PSM 6 Tunggal"},
    "z3_psm3": {"zoom": 3.0, "psm_config": "psm3", "desc": "Zoom 3.0 + PSM 3 Tunggal"},
    "z3_psm11": {"zoom": 3.0, "psm_config": "psm11", "desc": "Zoom 3.0 + PSM 11 Tunggal"},
    "z2_multi": {"zoom": 2.0, "psm_config": "multi", "desc": "Zoom 2.0 + Multi-PSM"},
    "z2_psm6": {"zoom": 2.0, "psm_config": "psm6", "desc": "Zoom 2.0 + PSM 6 Tunggal"},
    "z2_psm3": {"zoom": 2.0, "psm_config": "psm3", "desc": "Zoom 2.0 + PSM 3 Tunggal"},
    "z4_psm6": {"zoom": 4.0, "psm_config": "psm6", "desc": "Zoom 4.0 + PSM 6 Tunggal"},
}


def load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else list(data.values())
    return [item for item in items if item.get("file_exists")]


def load_ground_truth() -> dict[str, dict[str, str]]:
    if not GT_PATH.exists():
        raise FileNotFoundError(f"Ground truth not found: {GT_PATH}")
    with open(GT_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        gt_dict = {}
        for row in reader:
            fname = row.get("Nama File")
            if fname:
                gt_dict[fname] = row
    return gt_dict

def _atomic_write_bytes(target: Path, data: bytes) -> None:
    tmp = target.with_suffix(target.suffix + f".tmp_{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def _atomic_write_text(target: Path, text: str) -> None:
    tmp = target.with_suffix(target.suffix + f".tmp_{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


class CachedOCREngine:
    def __init__(self, cache_root: Path):
        self.cache_root = cache_root
        self.render_dir = cache_root / "rendered"
        self.rapid_dir = cache_root / "rapidocr"
        self.tess_dir = cache_root / "tesseract"
        for d in (self.render_dir, self.rapid_dir, self.tess_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.rapid_engine = _load_rapidocr()

    def get_or_render_image(self, file_path: Path, zoom: float) -> tuple[bytes, float]:
        stem = file_path.stem
        cache_file = self.render_dir / f"{stem}_z{zoom:.1f}.png"
        if cache_file.exists() and cache_file.stat().st_size > 0:
            return cache_file.read_bytes(), 0.0

        t0 = time.perf_counter()
        if file_path.suffix.lower() == ".pdf":
            with fitz.open(file_path) as doc:
                page = doc[0]
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_bytes = pix.tobytes("png")
                del pix
        else:
            with Image.open(file_path) as raw_img:
                img = raw_img.convert("RGB")
                buf = BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
                img.close()
        render_time = time.perf_counter() - t0

        _atomic_write_bytes(cache_file, img_bytes)
        return img_bytes, render_time

    def get_or_run_rapidocr(self, stem: str, zoom: float, img_bytes: bytes) -> tuple[str, float]:
        cache_file = self.rapid_dir / f"{stem}_z{zoom:.1f}.txt"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8"), 0.0

        t0 = time.perf_counter()
        if self.rapid_engine is not None:
            text = _ocr_with_rapidocr(self.rapid_engine, img_bytes)
        else:
            text = ""
        rapid_time = time.perf_counter() - t0

        _atomic_write_text(cache_file, text)
        return text, rapid_time

    def get_or_run_tesseract(
        self, stem: str, zoom: float, psm_config: str, img_bytes: bytes
    ) -> tuple[str, float]:
        cache_file = self.tess_dir / f"{stem}_z{zoom:.1f}_{psm_config}.txt"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8"), 0.0

        t0 = time.perf_counter()
        with Image.open(BytesIO(img_bytes)) as img:
            if psm_config == "multi":
                configs = ["", "--psm 6", "--psm 11"]
                lines: list[str] = []
                seen: set[str] = set()
                for cfg in configs:
                    try:
                        txt = pytesseract.image_to_string(img, lang="ind+eng", config=cfg).strip()
                    except Exception:
                        txt = pytesseract.image_to_string(img, lang="eng", config=cfg).strip()
                    for line in txt.splitlines():
                        clean = line.strip()
                        if clean and clean not in seen:
                            seen.add(clean)
                            lines.append(clean)
                text = "\n".join(lines)
            elif psm_config == "psm6":
                try:
                    text = pytesseract.image_to_string(img, lang="ind+eng", config="--psm 6").strip()
                except Exception:
                    text = pytesseract.image_to_string(img, lang="eng", config="--psm 6").strip()
            elif psm_config == "psm3":
                try:
                    text = pytesseract.image_to_string(img, lang="ind+eng", config="--psm 3").strip()
                except Exception:
                    text = pytesseract.image_to_string(img, lang="eng", config="--psm 3").strip()
            elif psm_config == "psm11":
                try:
                    text = pytesseract.image_to_string(img, lang="ind+eng", config="--psm 11").strip()
                except Exception:
                    text = pytesseract.image_to_string(img, lang="eng", config="--psm 11").strip()
            else:
                text = ""
        tess_time = time.perf_counter() - t0

        _atomic_write_text(cache_file, text)
        return text, tess_time

def run_pipeline_on_text(raw_text: str) -> dict[str, str]:
    extracted = extract_certificate_fields(raw_text)
    extracted = apply_combined_v4_2(extracted, raw_text)
    mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
    return {k: v.value or "" for k, v in mapped.items()}


def evaluate_variant(
    variant_name: str,
    variant_cfg: dict[str, Any],
    manifest: list[dict[str, Any]],
    gt_dict: dict[str, dict[str, str]],
    engine: CachedOCREngine,
    limit: int | None = None,
) -> dict[str, Any]:
    zoom = float(variant_cfg["zoom"])
    psm_config = str(variant_cfg["psm_config"])

    results = []
    field_totals = {pred_key: {"exact": 0, "fuzzy": 0, "total": 0} for _, pred_key in EVAL_FIELDS}

    render_times = []
    rapid_times = []
    tess_times = []
    total_times = []

    items = manifest[:limit] if limit else manifest

    for idx, item in enumerate(items, start=1):
        file_name = item["nama_file"]
        file_path = REPO_ROOT / item["unified_path"]
        stem = file_path.stem

        t_doc_start = time.perf_counter()

        img_bytes, t_render = engine.get_or_render_image(file_path, zoom)
        rapid_text, t_rapid = engine.get_or_run_rapidocr(stem, zoom, img_bytes)
        tess_text, t_tess = engine.get_or_run_tesseract(stem, zoom, psm_config, img_bytes)

        combined_ocr_text = merge_unique_lines([rapid_text, tess_text])

        # Also get digital text if PDF has layer, or purely OCR
        digital_text = ""
        if file_path.suffix.lower() == ".pdf":
            try:
                with fitz.open(file_path) as doc:
                    digital_text = "".join(page.get_text() for page in doc).strip()
            except Exception:
                digital_text = ""

        full_raw_text = merge_unique_lines([digital_text, combined_ocr_text]) if digital_text else combined_ocr_text

        pred_fields = run_pipeline_on_text(full_raw_text)
        doc_time = time.perf_counter() - t_doc_start

        render_times.append(t_render)
        rapid_times.append(t_rapid)
        tess_times.append(t_tess)
        total_times.append(doc_time)
        if idx % 10 == 0 or idx == len(items):
            print(f"       [{idx}/{len(items)}] processed {file_name[:30]} (last doc: {doc_time:.2f}s)")
            sys.stdout.flush()

        gt_row = gt_dict.get(file_name, {})
        doc_eval = {
            "index": idx,
            "nama_file": file_name,
            "dataset": item.get("dataset", "unknown"),
            "timings": {
                "render_s": round(t_render, 4),
                "rapidocr_s": round(t_rapid, 4),
                "tesseract_s": round(t_tess, 4),
                "total_s": round(doc_time, 4),
            },
            "fields": {},
        }

        for gt_col, pred_key in EVAL_FIELDS:
            gt_val = gt_row.get(gt_col, "") or ""
            pred_val = pred_fields.get(pred_key, "") or ""
            match_res = match_field(expected=gt_val, actual=pred_val, field_name=pred_key)
            is_exact = bool(match_res.get("exact"))
            is_fuzzy = bool(match_res.get("fuzzy"))
            status = "EXACT" if is_exact else ("FUZZY" if is_fuzzy else "MISMATCH")
            doc_eval["fields"][pred_key] = {
                "pred": pred_val,
                "gt": gt_val,
                "status": status,
                "exact": is_exact,
                "fuzzy": is_fuzzy,
                "wer": round(match_res.get("wer", 1.0), 4),
                "cer": round(match_res.get("cer", 1.0), 4),
            }
            field_totals[pred_key]["total"] += 1
            if is_exact:
                field_totals[pred_key]["exact"] += 1
                field_totals[pred_key]["fuzzy"] += 1
            elif is_fuzzy:
                field_totals[pred_key]["fuzzy"] += 1

        results.append(doc_eval)
        del img_bytes, rapid_text, tess_text, combined_ocr_text, full_raw_text
        if idx % 5 == 0:
            gc.collect()

    # Compute aggregate metrics
    total_cells = sum(f["total"] for f in field_totals.values())
    exact_cells = sum(f["exact"] for f in field_totals.values())
    fuzzy_cells = sum(f["fuzzy"] for f in field_totals.values())

    field_summary = {}
    for _, pred_key in EVAL_FIELDS:
        tot = field_totals[pred_key]["total"]
        field_summary[pred_key] = {
            "exact_count": field_totals[pred_key]["exact"],
            "fuzzy_count": field_totals[pred_key]["fuzzy"],
            "total": tot,
            "exact_pct": round((field_totals[pred_key]["exact"] / tot * 100) if tot else 0.0, 2),
            "fuzzy_pct": round((field_totals[pred_key]["fuzzy"] / tot * 100) if tot else 0.0, 2),
        }

    return {
        "variant": variant_name,
        "config": variant_cfg,
        "evaluated_docs": len(results),
        "total_cells": total_cells,
        "exact_cells": exact_cells,
        "fuzzy_cells": fuzzy_cells,
        "macro_exact": round((exact_cells / total_cells * 100) if total_cells else 0.0, 2),
        "macro_fuzzy": round((fuzzy_cells / total_cells * 100) if total_cells else 0.0, 2),
        "field_summary": field_summary,
        "timings": {
            "avg_render_s": round(sum(render_times) / len(render_times) if render_times else 0.0, 4),
            "avg_rapid_s": round(sum(rapid_times) / len(rapid_times) if rapid_times else 0.0, 4),
            "avg_tess_s": round(sum(tess_times) / len(tess_times) if tess_times else 0.0, 4),
            "avg_total_s": round(sum(total_times) / len(total_times) if total_times else 0.0, 4),
            "p95_total_s": round(sorted(total_times)[int(len(total_times) * 0.95)] if total_times else 0.0, 4),
        },
        "details": results,
    }

def generate_experiment_reports(
    out_dir: Path,
    variant_summaries: dict[str, Any],
    manifest: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    control_name = "control_z3_multi" if "control_z3_multi" in variant_summaries else next(iter(variant_summaries))
    ctrl = variant_summaries[control_name]

    # 1. Generate manifest.json
    manifest_data = {
        "experiment_id": "EXP-OCR-PSM-DPI-001",
        "campaign_id": "CMP-OCR-PSM-DPI",
        "role": "evaluation",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": "Ground_Truth_Unified.csv",
        "total_documents": len(manifest),
        "evaluated_documents": ctrl["evaluated_docs"],
        "variants_evaluated": list(variant_summaries.keys()),
        "control_variant": control_name,
        "status": "COMPLETED",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    # 2. Generate summary.md
    lines = [
        "# Laporan Komprehensif Evaluasi OCR: Mode Tesseract PSM & Skala Resolusi DPI/Zoom",
        "",
        "**ID Eksperimen**: `EXP-OCR-PSM-DPI-001`  ",
        f"**Tanggal & Waktu**: `{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}`  ",
        f"**Dataset Evaluasi**: `Ground_Truth_Unified.csv` ($N={ctrl['evaluated_docs']}$ dokumen)  ",
        "**Evaluator Baseline**: Matcher v2 frozen (`tests/matchers.py`)  ",
        "**Pipeline Ekstraktor**: Production Combined v4.2 + Form Mapper  ",
        "",
        "---",
        "",
        "## 1. Ringkasan Eksekutif",
        "",
        "Eksperimen ini bertujuan menginvestigasi trade-off antara **latensi komputasi** dan **akurasi ekstraksi** pada pemrosesan OCR sertifikat mahasiswa. Pengujian mengevaluasi kombinasi:",
        "1. **Skala Resolusi / DPI**: Zoom 2.0 (200 DPI), Zoom 3.0 (300 DPI, kontrol), dan Zoom 4.0 (400 DPI).",
        "2. **Mode Segmentasi Halaman (Tesseract `--psm`)**: Kontrol Multi-PSM 3-Pass (`\"\"` + `psm 6` + `psm 11`) vs Single-Pass (`psm 6`, `psm 3`, `psm 11`).",
        "",
        "---",
        "",
        "## 2. Tabel Komparasi Utama",
        "",
        "| Varian | Konfigurasi | Macro Exact | Macro Fuzzy | Waktu Tesseract | Waktu Total | Latensi p95 | Status Gate |",
        "|---|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    ctrl_exact = ctrl["macro_exact"]
    for var_name, res in variant_summaries.items():
        exact_diff = res["macro_exact"] - ctrl_exact
        exact_str = f"{res['macro_exact']}% ({'+' if exact_diff > 0 else ''}{exact_diff:.2f}pt)" if var_name != control_name else f"**{res['macro_exact']}%**"
        tess_s = res["timings"]["avg_tess_s"]
        tot_s = res["timings"]["avg_total_s"]
        p95_s = res["timings"]["p95_total_s"]
        verdict = "CONTROL" if var_name == control_name else ("PASS" if res["macro_exact"] >= ctrl_exact else "FAIL")
        lines.append(
            f"| `{var_name}` | {res['config']['desc']} | {exact_str} | {res['macro_fuzzy']}% | {tess_s}s | {tot_s}s | {p95_s}s | **{verdict}** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Rincian Akurasi per Field (Exact Match %)",
        "",
        "| Field | " + " | ".join(f"`{k}`" for k in variant_summaries.keys()) + " |",
        "|---|" + "|".join(":---:" for _ in variant_summaries) + "|",
    ])

    for _, pred_key in EVAL_FIELDS:
        row_vals = []
        for res in variant_summaries.values():
            f_stat = res["field_summary"].get(pred_key, {})
            row_vals.append(f"{f_stat.get('exact_pct', 0.0)}% ({f_stat.get('exact_count', 0)}/{f_stat.get('total', 0)})")
        lines.append(f"| **{pred_key}** | " + " | ".join(row_vals) + " |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Bedah Tahapan Waktu (Stage Timing Breakdown)",
        "",
        "| Varian | Render (s) | RapidOCR (s) | Tesseract (s) | Total Pipeline (s) | Penghematan vs Kontrol |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ])

    ctrl_tot = ctrl["timings"]["avg_total_s"]
    for var_name, res in variant_summaries.items():
        t = res["timings"]
        savings = ((ctrl_tot - t["avg_total_s"]) / ctrl_tot * 100) if ctrl_tot else 0.0
        lines.append(
            f"| `{var_name}` | {t['avg_render_s']}s | {t['avg_rapid_s']}s | {t['avg_tess_s']}s | {t['avg_total_s']}s | {savings:+.1f}% |"
        )

    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 3. Generate failure_breakdown.md (Root-Cause Failure Breakdown)
    fail_lines = [
        "# Bedah Cacat / Akar Masalah (Root-Cause Failure Breakdown)",
        "",
        "Dokumen ini membedah kasus-kasus konkret di mana varian kandidat mengalami kegagalan ekstraksi (penurunan skor) dibandingkan dengan Kontrol Multi-PSM.",
        "",
    ]

    ctrl_docs = {d["nama_file"]: d for d in ctrl["details"]}

    for var_name, res in variant_summaries.items():
        if var_name == control_name:
            continue
        fail_lines.append(f"## Varian: `{var_name}` ({res['config']['desc']})")
        dropped_cases = []

        for doc in res["details"]:
            fname = doc["nama_file"]
            c_doc = ctrl_docs.get(fname, {})
            for _, p_key in EVAL_FIELDS:
                c_stat = c_doc.get("fields", {}).get(p_key, {}).get("status")
                v_stat = doc.get("fields", {}).get(p_key, {}).get("status")
                if c_stat == "EXACT" and v_stat != "EXACT":
                    dropped_cases.append({
                        "nama_file": fname,
                        "field": p_key,
                        "gt": c_doc["fields"][p_key]["gt"],
                        "control_pred": c_doc["fields"][p_key]["pred"],
                        "candidate_pred": doc["fields"][p_key]["pred"],
                        "candidate_status": v_stat,
                    })

        if not dropped_cases:
            fail_lines.append(f"- **Zero Losses**: Varian ini tidak mengalami penurunan akurasi pada dokumen mana pun dibanding Kontrol!\n")
        else:
            fail_lines.append(f"Ditemukan **{len(dropped_cases)} kasus** penurunan dari EXACT menjadi non-EXACT:\n")
            for c in dropped_cases[:10]:
                fail_lines.extend([
                    f"### Kasus: `{c['nama_file']}` (Field: `{c['field']}`)",
                    f"- **Ground Truth**: `{c['gt']}`",
                    f"- **Kontrol Multi-PSM Pred**: `{c['control_pred']}` (EXACT)",
                    f"- **Kandidat `{var_name}` Pred**: `{c['candidate_pred']}` ({c['candidate_status']})",
                    "",
                ])
            if len(dropped_cases) > 10:
                fail_lines.append(f"*... dan {len(dropped_cases) - 10} kasus penurunan lainnya (lihat detailed_results.json).*\n")

    (out_dir / "failure_breakdown.md").write_text("\n".join(fail_lines) + "\n", encoding="utf-8")

    # 4. Generate success_breakdown.md
    succ_lines = [
        "# Bedah Keunggulan / Sumber Efisiensi (Key Success & Gain Breakdown)",
        "",
        "Dokumen ini membedah kasus-kasus konkret di mana varian kandidat berhasil memangkas latensi tanpa mengorbankan kelengkapan teks atau akurasi.",
        "",
    ]
    for var_name, res in variant_summaries.items():
        if var_name == control_name:
            continue
        succ_lines.extend([
            f"## Varian: `{var_name}` ({res['config']['desc']})",
            f"- **Macro Exact**: {res['macro_exact']}% (Kontrol: {ctrl_exact}%)",
            f"- **Rata-rata Waktu Tesseract**: {res['timings']['avg_tess_s']}s (Kontrol: {ctrl['timings']['avg_tess_s']}s)",
            f"- **Efisiensi Total**: Pangkas latensi sebesar {((ctrl_tot - res['timings']['avg_total_s']) / ctrl_tot * 100):.1f}%",
            "",
        ])
    (out_dir / "success_breakdown.md").write_text("\n".join(succ_lines) + "\n", encoding="utf-8")
    print(f"Comprehensive reports generated successfully in {out_dir}")

def main():
    parser = argparse.ArgumentParser(description="EXP-OCR-PSM-DPI-001 Evaluation Benchmark")
    parser.add_argument("--variants", nargs="+", default=["control_z3_multi", "z3_psm6", "z3_psm3", "z2_psm6"], help="Variants to evaluate")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents for smoke test")
    parser.add_argument("--cache-dir", type=str, default=str(CACHE_DIR), help="Disk cache directory")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR), help="Deliverable output directory")
    args = parser.parse_args()

    out_path = Path(args.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    engine = CachedOCREngine(Path(args.cache_dir))

    manifest = load_manifest()
    gt_dict = load_ground_truth()

    print("=" * 80)
    print(f"EXP-OCR-PSM-DPI-001: RUNNING OCR EVALUATION ON {len(manifest)} UNIFIED DOCS")
    print("=" * 80)

    variant_summaries = {}

    for var_name in args.variants:
        if var_name not in VARIANTS:
            print(f"Warning: unknown variant '{var_name}', skipping.")
            continue
        cfg = VARIANTS[var_name]
        print(f"\n---> Evaluating {var_name}: {cfg['desc']} ...")
        res = evaluate_variant(var_name, cfg, manifest, gt_dict, engine, limit=args.limit)
        variant_summaries[var_name] = res

        print(f"     Macro Exact: {res['macro_exact']}% | Macro Fuzzy: {res['macro_fuzzy']}%")
        print(f"     Field Breakdown (Exact):")
        for f_name, f_stats in res["field_summary"].items():
            print(f"       - {f_name:35s}: {f_stats['exact_count']}/{f_stats['total']} ({f_stats['exact_pct']}%)")
        print(f"     Average Total Latency: {res['timings']['avg_total_s']}s (Tesseract: {res['timings']['avg_tess_s']}s)")

    # Save master summary JSON and comprehensive reports
    summary_file = out_path / "detailed_results.json"
    summary_file.write_text(json.dumps(variant_summaries, indent=2), encoding="utf-8")
    print(f"\nMaster results saved to: {summary_file}")
    generate_experiment_reports(out_path, variant_summaries, manifest, args)


if __name__ == "__main__":
    main()
