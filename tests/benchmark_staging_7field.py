"""Benchmark Runner for Staging 7-Field Prompt (EXP-ALL6F-PROMPT-006).

Evaluates the clean 7-field staging prompt from commit 7c7da1d against the V2 Scope-Aware control:
- Target: v2_staging_7field (KHP_STAGING_SYSTEM_INSTRUCTION with 13 master tingkat + raw_role)
- Control: v2_scope_aware_control (V2 baseline single-pass scope-aware)
- Fields: 6 official KHP ground truth fields evaluated via Matcher v2 (tests/matchers.py).
- raw_role: NOT_RUN / intermediate-only (tracked for extraction presence, no GT column).

Enforces B14/B15 immutability guards and outputs to isolated campaign folder:
docs/experiments/EXP-ALL6F-PROMPT-006/
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
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

from app.master_data import FORM_OPTIONS, KHP_TINGKAT_LABELS
from app.services.field_extractor import ExtractedValue
from app.services.gemini_extractor import (
    KHP_STAGING_SYSTEM_INSTRUCTION,
    KHP_STAGING_USER_PROMPT_TEMPLATE,
    SYSTEM_INSTRUCTION as CONTROL_V2_SYSTEM_INSTRUCTION,
    USER_PROMPT_TEMPLATE as CONTROL_V2_USER_PROMPT_TEMPLATE,
    normalize_llm_json,
    standardize_date,
)
from app.services.ocr_fallback import extract_text_with_ocr
from app.services.pdf_fast_path import extract_text_with_pymupdf
from tests.gemini_client import (
    GeminiCallResult,
    GeminiClient,
    get_exchange_rate,
    load_google_api_key,
)
from tests.matchers import match_field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark_staging_7field")

ALL_6_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
]

FRAMEWORK_5_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
]


class MockGeminiClient:
    """Mock client for dry-runs and regression checks without live API calls."""

    def __init__(self, default_model: str = "gemini-3.1-flash-lite") -> None:
        self.default_model = default_model

    def generate_json(
        self,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        enable_grounding: bool = False,
    ) -> GeminiCallResult:
        mock_data = {
            "nama_kegiatan_sertifikasi": "Kegiatan Uji Coba Mahasiswa",
            "nomor_bukti_fisik_nomor_sertifikasi": "01/TEST/2026",
            "penyelenggara_kegiatan": "BEM Universitas Airlangga",
            "waktu_mulai_pelaksanaan": "18/08/2024",
            "waktu_selesai_pelaksanaan": "18/08/2024",
            "tingkat": "Universitas",
            "raw_role": "Peserta",
        }
        return GeminiCallResult(
            response_text=json.dumps(mock_data),
            parsed_json=mock_data,
            prompt_tokens=150,
            candidates_tokens=40,
            cached_tokens=0,
            thoughts_tokens=0,
            total_tokens=190,
            cost_usd=0.00008,
            cost_idr=1.42,
            latency_s=0.05,
            model=model or self.default_model,
            status="success",
        )


def load_manifest(manifest_path: str | Path) -> list[dict[str, Any]]:
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ground_truth(gt_path: str | Path) -> dict[str, dict[str, str]]:
    with open(gt_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            row["Nama File"].strip(): row
            for row in reader
            if row.get("Nama File")
        }


def get_raw_text(
    doc_info: dict[str, Any],
    cache_dir: Path | None = None,
) -> str:
    fname = doc_info["nama_file"].strip()
    if cache_dir:
        stem = Path(fname).stem
        for cand in (cache_dir / f"{stem}.txt", cache_dir / f"{fname}.txt"):
            if cand.exists():
                return cand.read_text(encoding="utf-8").strip()

    pdf_path = doc_info.get("resolved_path") or os.path.join(
        REPO_ROOT, doc_info.get("folder", "certs_unified"), fname
    )
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        fast = extract_text_with_pymupdf(pdf_bytes)
        text = fast.text.strip()
        if len(text) >= 80:
            return text
        ocr_text = extract_text_with_ocr(pdf_bytes)
        return f"{text}\n{ocr_text}".strip()
    return ""


def call_variant(
    variant: str,
    raw_text: str,
    client: GeminiClient | MockGeminiClient,
    model: str = "gemini-3.1-flash-lite",
) -> tuple[dict[str, str | None], dict[str, Any]]:
    t0 = time.perf_counter()
    if variant == "v2_staging_7field":
        prompt = KHP_STAGING_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        sys_inst = KHP_STAGING_SYSTEM_INSTRUCTION
        valid_tingkat = KHP_TINGKAT_LABELS
    elif variant == "v2_scope_aware_control":
        prompt = CONTROL_V2_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        sys_inst = CONTROL_V2_SYSTEM_INSTRUCTION
        valid_tingkat = None
    else:
        raise ValueError(f"Varian tidak dikenal: {variant}")

    res = client.generate_json(
        prompt=prompt,
        system_instruction=sys_inst,
        model=model,
        temperature=0.0,
        enable_grounding=False,
    )
    norm = normalize_llm_json(res.parsed_json, valid_tingkat_options=valid_tingkat)
    latency = time.perf_counter() - t0
    meta = {
        "status": res.status,
        "prompt_tokens": res.prompt_tokens,
        "candidates_tokens": res.candidates_tokens,
        "cached_tokens": res.cached_tokens,
        "thoughts_tokens": res.thoughts_tokens,
        "total_tokens": res.total_tokens,
        "cost_usd": res.cost_usd,
        "cost_idr": res.cost_idr,
        "latency_s": latency,
        "error": res.error_message,
        "raw_role": norm.get("raw_role"),
    }
    return norm, meta


def evaluate_prediction(
    pred: dict[str, str | None],
    gt: dict[str, str],
) -> dict[str, dict[str, Any]]:
    gt_map = {
        "nama_kegiatan_sertifikasi": gt.get("Nama Kegiatan Sertifikasi", ""),
        "nomor_bukti_fisik_nomor_sertifikasi": gt.get("Nomor Bukti Fisik Nomor Sertifikasi", ""),
        "penyelenggara_kegiatan": gt.get("Penyelenggara Kegiatan", ""),
        "waktu_mulai_pelaksanaan": gt.get("Waktu Mulai Pelaksanaan", ""),
        "waktu_selesai_pelaksanaan": gt.get("Waktu Selesai Pelaksanaan", ""),
        "tingkat": gt.get("Tingkat", ""),
    }
    results = {}
    for fld in ALL_6_FIELDS:
        res = match_field(gt_map.get(fld, ""), pred.get(fld), fld)
        results[fld] = {
            "exact": bool(res["exact"]),
            "fuzzy": bool(res["fuzzy"]),
            "token_overlap": round(float(res.get("token_overlap", 0.0)), 4),
            "pred": pred.get(fld),
            "gt": gt_map.get(fld),
        }
    return results


def run_benchmark(
    manifest_path: str | Path,
    gt_path: str | Path,
    output_dir: str | Path,
    backend: str = "gemini",
    model: str = "gemini-3.1-flash-lite",
    raw_texts_dir: str | Path | None = None,
    limit: int | None = None,
    offset: int = 0,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    if out_dir.exists() and not allow_overwrite:
        if (out_dir / "summary.md").exists():
            raise FileExistsError(
                f"Output directory {out_dir} already contains deliverables. "
                "Per B14, use a new directory or pass --allow-overwrite."
            )
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(manifest_path)
    gt_rows = load_ground_truth(gt_path)
    docs = [d for d in manifest if d["nama_file"].strip() in gt_rows]
    if offset > 0:
        docs = docs[offset:]
    if limit and limit > 0:
        docs = docs[:limit]

    logger.info(f"Target documents: {len(docs)} from GT: {gt_path}")
    cache_path = Path(raw_texts_dir) if raw_texts_dir else None

    client: GeminiClient | MockGeminiClient
    if backend == "mock":
        client = MockGeminiClient(default_model=model)
    else:
        api_key = load_google_api_key()
        if not api_key:
            raise ValueError("GOOGLE_API_KEY tidak ditemukan!")
        client = GeminiClient(api_key=api_key, default_model=model)

    variants = ["v2_scope_aware_control", "v2_staging_7field"]

    eval_rows: list[dict[str, Any]] = []
    variant_stats: dict[str, dict[str, Any]] = {
        v: {
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "cached_tokens": 0,
            "thoughts_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_idr": 0.0,
            "latency_total": 0.0,
            "calls_count": 0,
            "exact_6f": 0,
            "fuzzy_6f": 0,
            "exact_5f": 0,
            "fuzzy_5f": 0,
            "exact_tingkat": 0,
            "raw_role_extracted": 0,
            "total_cells_6f": len(docs) * 6,
            "total_cells_5f": len(docs) * 5,
        }
        for v in variants
    }

    t_start = datetime.now()
    for idx, doc in enumerate(docs, start=1):
        fname = doc["nama_file"].strip()
        gt = gt_rows[fname]
        raw_text = get_raw_text(doc, cache_path)
        logger.info(f"[{idx}/{len(docs)}] Processing: {fname}")

        for var in variants:
            pred, meta = call_variant(var, raw_text, client, model=model)
            evals = evaluate_prediction(pred, gt)

            stats = variant_stats[var]
            stats["prompt_tokens"] += meta.get("prompt_tokens", 0)
            stats["candidates_tokens"] += meta.get("candidates_tokens", 0)
            stats["cached_tokens"] += meta.get("cached_tokens", 0)
            stats["thoughts_tokens"] += meta.get("thoughts_tokens", 0)
            stats["total_tokens"] += meta.get("total_tokens", 0)
            stats["cost_usd"] += meta.get("cost_usd", 0.0)
            stats["cost_idr"] += meta.get("cost_idr", 0.0)
            stats["latency_total"] += meta.get("latency_s", 0.0)
            stats["calls_count"] += 1
            if meta.get("raw_role"):
                stats["raw_role_extracted"] += 1

            for fld in ALL_6_FIELDS:
                if evals[fld]["exact"]:
                    stats["exact_6f"] += 1
                if evals[fld]["fuzzy"]:
                    stats["fuzzy_6f"] += 1

            for fld in FRAMEWORK_5_FIELDS:
                if evals[fld]["exact"]:
                    stats["exact_5f"] += 1
                if evals[fld]["fuzzy"]:
                    stats["fuzzy_5f"] += 1

            if evals["tingkat"]["exact"]:
                stats["exact_tingkat"] += 1

            eval_rows.append({
                "doc_name": fname,
                "variant": var,
                "folder": doc.get("folder", ""),
                "evaluations": evals,
                "raw_role": meta.get("raw_role"),
                "meta": meta,
            })

    t_end = datetime.now()
    summary: dict[str, Any] = {
        "campaign_id": "EXP-ALL6F-PROMPT-CAMPAIGN-006",
        "timestamp_start": t_start.isoformat(),
        "timestamp_end": t_end.isoformat(),
        "gt_path": str(gt_path),
        "total_documents": len(docs),
        "model": model,
        "backend": backend,
        "variants": {},
    }

    for var in variants:
        st = variant_stats[var]
        n_docs = len(docs) or 1
        summary["variants"][var] = {
            "all_cells_6f_exact_pct": round(st["exact_6f"] / (n_docs * 6) * 100.0, 2),
            "all_cells_6f_fuzzy_pct": round(st["fuzzy_6f"] / (n_docs * 6) * 100.0, 2),
            "framework_5f_exact_pct": round(st["exact_5f"] / (n_docs * 5) * 100.0, 2),
            "framework_5f_fuzzy_pct": round(st["fuzzy_5f"] / (n_docs * 5) * 100.0, 2),
            "tingkat_exact_pct": round(st["exact_tingkat"] / n_docs * 100.0, 2),
            "raw_role_presence_pct": round(st["raw_role_extracted"] / n_docs * 100.0, 2),
            "raw_role_evaluation_status": "NOT_RUN (internal intermediate field, no GT column)",
            "avg_tokens_per_doc": round(st["total_tokens"] / n_docs, 1),
            "avg_cost_idr_per_doc": round(st["cost_idr"] / n_docs, 2),
            "avg_latency_s": round(st["latency_total"] / n_docs, 3),
            "raw_stats": st,
        }

    ctrl = summary["variants"]["v2_scope_aware_control"]
    tgt = summary["variants"]["v2_staging_7field"]

    # Strict No-Regress Gate Evaluation against Control
    gate_tingkat = tgt["tingkat_exact_pct"] >= ctrl["tingkat_exact_pct"]
    gate_framework = tgt["framework_5f_exact_pct"] >= ctrl["framework_5f_exact_pct"]
    gate_all_cells = tgt["all_cells_6f_exact_pct"] >= ctrl["all_cells_6f_exact_pct"]
    all_gates_pass = bool(gate_tingkat and gate_framework and gate_all_cells)

    summary["gates"] = {
        "gate_tingkat_no_regress": {
            "pass": bool(gate_tingkat),
            "target": tgt["tingkat_exact_pct"],
            "control": ctrl["tingkat_exact_pct"],
            "delta_pt": round(tgt["tingkat_exact_pct"] - ctrl["tingkat_exact_pct"], 2),
        },
        "gate_framework_5f_no_regress": {
            "pass": bool(gate_framework),
            "target": tgt["framework_5f_exact_pct"],
            "control": ctrl["framework_5f_exact_pct"],
            "delta_pt": round(tgt["framework_5f_exact_pct"] - ctrl["framework_5f_exact_pct"], 2),
        },
        "gate_all_cells_no_regress": {
            "pass": bool(gate_all_cells),
            "target": tgt["all_cells_6f_exact_pct"],
            "control": ctrl["all_cells_6f_exact_pct"],
            "delta_pt": round(tgt["all_cells_6f_exact_pct"] - ctrl["all_cells_6f_exact_pct"], 2),
        },
        "all_gates_pass": all_gates_pass,
    }

    # Deliverables: JSON
    with open(out_dir / "comparative_metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Deliverables: CSV
    with open(out_dir / "evaluation_details.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "doc_name", "variant", "field", "exact", "fuzzy", "token_overlap", "pred", "gt"
        ])
        for row in eval_rows:
            for fld, ev in row["evaluations"].items():
                writer.writerow([
                    row["doc_name"], row["variant"], fld, ev["exact"], ev["fuzzy"],
                    ev["token_overlap"], ev["pred"], ev["gt"]
                ])

    # Deliverables: XLSX (jika openpyxl terinstall)
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws.append(["Metric", "Control (V2 Scope-Aware)", "Target (V2 Staging 7-Field)", "Delta"])
        ws.append(["Tingkat Exact (%)", ctrl["tingkat_exact_pct"], tgt["tingkat_exact_pct"], round(tgt["tingkat_exact_pct"] - ctrl["tingkat_exact_pct"], 2)])
        ws.append(["All-Cells 6F Exact (%)", ctrl["all_cells_6f_exact_pct"], tgt["all_cells_6f_exact_pct"], round(tgt["all_cells_6f_exact_pct"] - ctrl["all_cells_6f_exact_pct"], 2)])
        ws.append(["Framework 5F Exact (%)", ctrl["framework_5f_exact_pct"], tgt["framework_5f_exact_pct"], round(tgt["framework_5f_exact_pct"] - ctrl["framework_5f_exact_pct"], 2)])
        ws.append(["Raw Role Presence (%)", ctrl["raw_role_presence_pct"], tgt["raw_role_presence_pct"], round(tgt["raw_role_presence_pct"] - ctrl["raw_role_presence_pct"], 2)])
        ws.append(["Avg Tokens / Doc", ctrl["avg_tokens_per_doc"], tgt["avg_tokens_per_doc"], round(tgt["avg_tokens_per_doc"] - ctrl["avg_tokens_per_doc"], 1)])
        ws.append(["Avg Cost / Doc (IDR)", ctrl["avg_cost_idr_per_doc"], tgt["avg_cost_idr_per_doc"], round(tgt["avg_cost_idr_per_doc"] - ctrl["avg_cost_idr_per_doc"], 2)])
        ws.append(["Avg Latency (s)", ctrl["avg_latency_s"], tgt["avg_latency_s"], round(tgt["avg_latency_s"] - ctrl["avg_latency_s"], 3)])
        wb.save(out_dir / "results.xlsx")
        logger.info(f"Excel report saved: {out_dir / 'results.xlsx'}")
    except ImportError:
        logger.warning("openpyxl tidak terinstall, melewati pembuatan results.xlsx")

    # Deliverables: Markdown Summary
    md_text = f"""# Comparative Summary: EXP-ALL6F-PROMPT-006

- **Campaign ID**: EXP-ALL6F-PROMPT-CAMPAIGN-006
- **Dataset**: `{gt_path}` (N={len(docs)})
- **Model**: `{model}` (backend: `{backend}`)
- **Evaluation Period**: `{t_start.isoformat()}` to `{t_end.isoformat()}`
- **Overall Gate Status**: **{'PASS' if all_gates_pass else 'FAIL'}**

## Comparative Metrics

| Metric | Control (V2 Scope-Aware) | Target (V2 Staging 7-Field) | Delta |
|---|:---:|:---:|:---:|
| Tingkat Exact | {ctrl['tingkat_exact_pct']}% | {tgt['tingkat_exact_pct']}% | {round(tgt['tingkat_exact_pct'] - ctrl['tingkat_exact_pct'], 2):+}% |
| All-Cells 6F Exact | {ctrl['all_cells_6f_exact_pct']}% | {tgt['all_cells_6f_exact_pct']}% | {round(tgt['all_cells_6f_exact_pct'] - ctrl['all_cells_6f_exact_pct'], 2):+}% |
| Framework 5F Exact | {ctrl['framework_5f_exact_pct']}% | {tgt['framework_5f_exact_pct']}% | {round(tgt['framework_5f_exact_pct'] - ctrl['framework_5f_exact_pct'], 2):+}% |
| Raw Role Presence | {ctrl['raw_role_presence_pct']}% | {tgt['raw_role_presence_pct']}% | {round(tgt['raw_role_presence_pct'] - ctrl['raw_role_presence_pct'], 2):+}% |
| Raw Role GT Eval | NOT_RUN (no GT column) | NOT_RUN (no GT column) | - |
| Avg Tokens / Doc | {ctrl['avg_tokens_per_doc']} | {tgt['avg_tokens_per_doc']} | {round(tgt['avg_tokens_per_doc'] - ctrl['avg_tokens_per_doc'], 1):+} |
| Avg Cost / Doc | Rp {ctrl['avg_cost_idr_per_doc']} | Rp {tgt['avg_cost_idr_per_doc']} | Rp {round(tgt['avg_cost_idr_per_doc'] - ctrl['avg_cost_idr_per_doc'], 2):+} |
| Avg Latency | {ctrl['avg_latency_s']}s | {tgt['avg_latency_s']}s | {round(tgt['avg_latency_s'] - ctrl['avg_latency_s'], 3):+}s |

## Gate Breakdown

- Gate Tingkat No-Regress: **{'PASS' if gate_tingkat else 'FAIL'}** ({tgt['tingkat_exact_pct']}% vs {ctrl['tingkat_exact_pct']}%)
- Gate Framework 5F No-Regress: **{'PASS' if gate_framework else 'FAIL'}** ({tgt['framework_5f_exact_pct']}% vs {ctrl['framework_5f_exact_pct']}%)
- Gate All-Cells No-Regress: **{'PASS' if gate_all_cells else 'FAIL'}** ({tgt['all_cells_6f_exact_pct']}% vs {ctrl['all_cells_6f_exact_pct']}%)
"""
    with open(out_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write(md_text)

    # Deliverables: manifest.json
    manifest_data = {
        "campaign_id": "EXP-ALL6F-PROMPT-CAMPAIGN-006",
        "experiment_id": "EXP-ALL6F-PROMPT-006",
        "role": "evaluation_runner",
        "dataset": str(gt_path),
        "total_documents": len(docs),
        "variants": variants,
        "status": "PASS" if all_gates_pass else "FAIL",
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Deliverables successfully saved to: {out_dir}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Staging 7-Field Prompt Benchmark Runner")
    parser.add_argument(
        "--manifest-path",
        default=os.path.join(REPO_ROOT, "certs_unified", "manifest.json"),
        help="Path ke manifest.json",
    )
    parser.add_argument(
        "--gt-path",
        default=os.path.join(REPO_ROOT, "Ground_Truth_Unified.csv"),
        help="Path ke Ground Truth CSV (Unified atau Primary v9)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Direktori output artefak baru (wajib unik, misal docs/experiments/EXP-ALL6F-PROMPT-006/run_unified_104)",
    )
    parser.add_argument(
        "--backend",
        choices=["gemini", "mock"],
        default="gemini",
        help="Backend eksekusi",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.1-flash-lite",
        help="Model Gemini yang digunakan",
    )
    parser.add_argument(
        "--raw-texts-dir",
        default=os.path.join(REPO_ROOT, "docs", "experiments", "EXP-ALL6F-PROMPT-001", "raw_texts"),
        help="Direktori cache raw OCR teks",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah dokumen untuk pengujian",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Offset indeks awal",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Izinkan overwrite jika folder sudah ada",
    )
    args = parser.parse_args()

    run_benchmark(
        manifest_path=args.manifest_path,
        gt_path=args.gt_path,
        output_dir=args.output_dir,
        backend=args.backend,
        model=args.model,
        raw_texts_dir=args.raw_texts_dir,
        limit=args.limit,
        offset=args.offset,
        allow_overwrite=args.allow_overwrite,
    )


if __name__ == "__main__":
    main()
