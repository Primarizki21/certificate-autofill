"""Benchmark Runner for Tesseract-to-Gemini Direct Extraction.

Evaluates 3 Google Gemini models (gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3.1-flash-lite)
on raw Tesseract OCR texts across 74 certificates against Ground_Truth_Sertifikat_v9.csv
using Matcher v2 frozen evaluation.

Generates run_results.json, per_cert_results.csv, summary.csv, and report.md per run,
plus multi-model comparison reports in docs/report/.
"""

from __future__ import annotations

import argparse
import csv
import json
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

from tests.evaluation_framework import EVAL_FIELDS, load_csv
from tests.gemini_client import (
    DEFAULT_EXCHANGE_RATE_IDR,
    PRICING_TABLE,
    GeminiCallResult,
    GeminiClient,
    get_exchange_rate,
)
from tests.gemini_field_extractor import (
    ALL_EVAL_FIELDS,
    SYSTEM_INSTRUCTION_STANDARD,
    USER_PROMPT_TEMPLATE,
    extract_fields_from_ocr,
)
from tests.matchers import match_field

DEFAULT_GT_PATH = os.environ.get(
    "GT_CSV_PATH", os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v9.csv")
)
DEFAULT_TEXTS_DIR = os.path.join(
    REPO_ROOT,
    "tests",
    "benchmark_runs",
    "ocr_experiment",
    "tesseract_primary_v4",
    "extracted_texts",
)
MANIFEST_PATH = os.path.join(REPO_ROOT, "tests", "layout_manifest.json")
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "tests", "benchmark_runs", "ocr_experiment")

EVAL_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
]

def load_manifest() -> dict[str, str]:
    """Muat klasifikasi tipe dokumen (scan vs embedded) dari manifest."""
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                raw_m = json.load(f)
            from tests.ocr_engine import classify_manifest
            classification = classify_manifest(raw_m)
            return {
                stem: ("scan" if info.get("scan", True) else "embedded")
                for stem, info in classification.items()
            }
        except Exception:
            pass
    return {}


def evaluate_certificate_row(
    mapped_form: dict[str, Any],
    gt_row: dict[str, str],
) -> dict[str, Any]:
    """Evaluasi 6 field ekstraksi form terhadap Ground Truth baris sertifikat."""
    row_eval: dict[str, Any] = {}
    for field in ALL_EVAL_FIELDS:
        pred_obj = mapped_form.get(field)
        pred_val = (pred_obj.value or "") if pred_obj else ""
        gt_val = (gt_row.get(field) or "").strip()

        m = match_field(gt_val, pred_val, field)
        row_eval[field] = {
            "pred": pred_val,
            "gt": gt_val,
            "exact": bool(m["exact"]),
            "fuzzy": bool(m["fuzzy"]),
            "wer": float(m.get("wer", 0.0)),
            "cer": float(m.get("cer", 0.0)),
            "confidence": float(pred_obj.confidence if pred_obj else 0.0),
            "source": str(pred_obj.source if pred_obj else "none"),
        }
    return row_eval


def aggregate_metrics(results: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    """Hitung agregat exact, fuzzy, average WER/CER, dan MACRO accuracy."""
    agg: dict[str, Any] = {}
    total_cells = 0
    exact_cells = 0
    fuzzy_cells = 0

    for f in fields:
        f_total = len(results)
        f_exact = sum(1 for r in results if r["evaluation"][f]["exact"])
        f_fuzzy = sum(1 for r in results if r["evaluation"][f]["fuzzy"])
        f_wer = sum(r["evaluation"][f]["wer"] for r in results) / max(f_total, 1)
        f_cer = sum(r["evaluation"][f]["cer"] for r in results) / max(f_total, 1)

        total_cells += f_total
        exact_cells += f_exact
        fuzzy_cells += f_fuzzy

        agg[f] = {
            "total": f_total,
            "exact": f_exact,
            "fuzzy": f_fuzzy,
            "exact_pct": round(f_exact / f_total * 100, 2) if f_total else 0.0,
            "fuzzy_pct": round(f_fuzzy / f_total * 100, 2) if f_total else 0.0,
            "avg_wer": round(f_wer, 4),
            "avg_cer": round(f_cer, 4),
        }

    agg["macro_avg"] = {
        "total_cells": total_cells,
        "exact_cells": exact_cells,
        "fuzzy_cells": fuzzy_cells,
        "exact_pct": round(exact_cells / total_cells * 100, 2) if total_cells else 0.0,
        "fuzzy_pct": round(fuzzy_cells / total_cells * 100, 2) if total_cells else 0.0,
    }
    return agg


def run_benchmark_for_model(
    model: str,
    texts_dir: str = DEFAULT_TEXTS_DIR,
    gt_csv_path: str = DEFAULT_GT_PATH,
    out_root: str = DEFAULT_OUT_DIR,
    limit: int | None = None,
    request_delay: float = 1.2,
    verbose: bool = True,
) -> dict[str, Any]:
    """Jalankan benchmark ekstraksi direct Gemini untuk satu model spesifik."""
    exchange_rate = get_exchange_rate()
    client = GeminiClient(
        default_model=model,
        request_delay=request_delay,
        exchange_rate=exchange_rate,
    )

    manifest = load_manifest()
    gt_rows = load_csv(gt_csv_path)
    stem_to_gt: dict[str, dict[str, str]] = {}
    for r in gt_rows:
        fname = (r.get("nama_file") or "").strip()
        stem = os.path.splitext(fname)[0]
        stem_to_gt[stem] = r

    txt_files = sorted(Path(texts_dir).glob("*.txt"))
    if limit and limit > 0:
        txt_files = txt_files[:limit]

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_model_name = model.replace("-", "_").replace(".", "_")
    run_name = f"{sanitized_model_name}_{timestamp_str}"
    run_dir = os.path.join(out_root, run_name)
    os.makedirs(run_dir, exist_ok=True)

    print(f"\n=======================================================")
    print(f"BENCHMARK TESSERACT -> GOOGLE GEMINI: {model}")
    print(f"=======================================================")
    print(f"Input texts   : {texts_dir} ({len(txt_files)} files)")
    print(f"Ground Truth  : {gt_csv_path} ({len(gt_rows)} records)")
    print(f"Run Output Dir: {run_dir}")
    print(f"Kurs IDR/USD  : Rp{exchange_rate:,.2f}")
    print(f"Pricing Model : {PRICING_TABLE.get(model)}")
    print(f"Request Delay : {request_delay}s\n")

    cert_results: list[dict[str, Any]] = []

    total_prompt_tokens = 0
    total_cand_tokens = 0
    total_cached_tokens = 0
    total_thoughts_tokens = 0
    total_all_tokens = 0
    total_cost_usd = 0.0
    total_cost_idr = 0.0
    total_latency_s = 0.0

    for idx, txt_path in enumerate(txt_files, 1):
        stem = txt_path.stem
        raw_ocr_text = txt_path.read_text(encoding="utf-8", errors="replace")
        gt_row = stem_to_gt.get(stem, {})
        doc_type = manifest.get(stem, "unknown")

        if verbose:
            print(f"[{idx:02d}/{len(txt_files):02d}] {stem} ({doc_type})...", end="", flush=True)

        mapped_form, call_res = extract_fields_from_ocr(
            raw_ocr_text=raw_ocr_text,
            client=client,
            model=model,
            temperature=0.0,
        )

        row_eval = evaluate_certificate_row(mapped_form, gt_row)

        exact_count = sum(1 for f in ALL_EVAL_FIELDS if row_eval[f]["exact"])
        fuzzy_count = sum(1 for f in ALL_EVAL_FIELDS if row_eval[f]["fuzzy"])

        total_prompt_tokens += call_res.prompt_tokens
        total_cand_tokens += call_res.candidates_tokens
        total_cached_tokens += call_res.cached_tokens
        total_thoughts_tokens += call_res.thoughts_tokens
        total_all_tokens += call_res.total_tokens
        total_cost_usd += call_res.cost_usd
        total_cost_idr += call_res.cost_idr
        total_latency_s += call_res.latency_s

        cert_results.append({
            "stem": stem,
            "filename": f"{stem}.pdf",
            "doc_type": doc_type,
            "call_result": call_res.to_dict(),
            "evaluation": row_eval,
            "summary": {
                "exact_fields": exact_count,
                "fuzzy_fields": fuzzy_count,
                "total_fields": len(ALL_EVAL_FIELDS),
            },
        })

        if verbose:
            print(
                f" OK! Exact: {exact_count}/{len(ALL_EVAL_FIELDS)}, "
                f"Tok: {call_res.total_tokens}, Cost: Rp{call_res.cost_idr:.2f}, "
                f"Lat: {call_res.latency_s:.2f}s"
            )

    n_certs = max(len(cert_results), 1)
    avg_tokens = round(total_all_tokens / n_certs, 1)
    avg_usd = round(total_cost_usd / n_certs, 6)
    avg_idr = round(total_cost_idr / n_certs, 2)
    avg_lat = round(total_latency_s / n_certs, 3)

    agg_all = aggregate_metrics(cert_results, ALL_EVAL_FIELDS)

    scan_certs = [r for r in cert_results if r["doc_type"] == "scan"]
    agg_scan = aggregate_metrics(scan_certs, ALL_EVAL_FIELDS) if scan_certs else {}

    emb_certs = [r for r in cert_results if r["doc_type"] == "embedded"]
    agg_emb = aggregate_metrics(emb_certs, ALL_EVAL_FIELDS) if emb_certs else {}

    agg_framework_all = aggregate_metrics(cert_results, EVAL_FIELDS)
    agg_framework_scan = aggregate_metrics(scan_certs, EVAL_FIELDS) if scan_certs else {}
    agg_framework_emb = aggregate_metrics(emb_certs, EVAL_FIELDS) if emb_certs else {}

    run_meta = {
        "run_name": run_name,
        "model": model,
        "timestamp": timestamp_str,
        "dataset_size": len(cert_results),
        "exchange_rate_idr_per_usd": exchange_rate,
        "pricing": PRICING_TABLE.get(model).__dict__ if PRICING_TABLE.get(model) else {},
        "totals": {
            "prompt_tokens": total_prompt_tokens,
            "candidates_tokens": total_cand_tokens,
            "cached_tokens": total_cached_tokens,
            "thoughts_tokens": total_thoughts_tokens,
            "total_tokens": total_all_tokens,
            "cost_usd": round(total_cost_usd, 6),
            "cost_idr": round(total_cost_idr, 2),
            "latency_s": round(total_latency_s, 2),
        },
        "averages_per_cert": {
            "tokens": avg_tokens,
            "cost_usd": avg_usd,
            "cost_idr": avg_idr,
            "latency_s": avg_lat,
        },
        "aggregates": {
            "all_cells_6field": {
                "all": agg_all,
                "scan": agg_scan,
                "embedded": agg_emb,
            },
            "framework_5field": {
                "all": agg_framework_all,
                "scan": agg_framework_scan,
                "embedded": agg_framework_emb,
            },
        },
        "system_instruction": SYSTEM_INSTRUCTION_STANDARD,
        "prompt_template": USER_PROMPT_TEMPLATE,
    }

    # 1. Simpan run_results.json
    run_results_payload = {
        "metadata": run_meta,
        "certificates": cert_results,
    }
    json_path = os.path.join(run_dir, "run_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(run_results_payload, f, indent=2, ensure_ascii=False)

    # 2. Simpan per_cert_results.csv
    csv_path = os.path.join(run_dir, "per_cert_results.csv")
    csv_headers = [
        "filename",
        "stem",
        "doc_type",
        "status",
        "prompt_tokens",
        "candidates_tokens",
        "thoughts_tokens",
        "total_tokens",
        "cost_usd",
        "cost_idr",
        "latency_s",
    ]
    for f in ALL_EVAL_FIELDS:
        csv_headers.extend([f"{f}_gt", f"{f}_pred", f"{f}_exact", f"{f}_fuzzy", f"{f}_wer", f"{f}_cer"])

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_headers)
        for r in cert_results:
            row_data = [
                r["filename"],
                r["stem"],
                r["doc_type"],
                r["call_result"]["status"],
                r["call_result"]["prompt_tokens"],
                r["call_result"]["candidates_tokens"],
                r["call_result"]["thoughts_tokens"],
                r["call_result"]["total_tokens"],
                f"{r['call_result']['cost_usd']:.6f}",
                f"{r['call_result']['cost_idr']:.2f}",
                f"{r['call_result']['latency_s']:.3f}",
            ]
            for f in ALL_EVAL_FIELDS:
                fe = r["evaluation"][f]
                row_data.extend([
                    fe["gt"],
                    fe["pred"],
                    1 if fe["exact"] else 0,
                    1 if fe["fuzzy"] else 0,
                    f"{fe['wer']:.4f}",
                    f"{fe['cer']:.4f}",
                ])
            writer.writerow(row_data)

    # 3. Simpan summary.csv
    summary_path = os.path.join(run_dir, "summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_name", "model", "n_certs",
            "macro_exact_6f", "macro_fuzzy_6f",
            "framework_exact_5f", "framework_fuzzy_5f",
            "scan_exact_6f", "emb_exact_6f",
            "total_tokens", "total_usd", "total_idr",
            "avg_tok_cert", "avg_usd_cert", "avg_idr_cert", "avg_lat_s"
        ])
        writer.writerow([
            run_name,
            model,
            len(cert_results),
            f"{agg_all['macro_avg']['exact_pct']:.2f}%",
            f"{agg_all['macro_avg']['fuzzy_pct']:.2f}%",
            f"{agg_framework_all['macro_avg']['exact_pct']:.2f}%",
            f"{agg_framework_all['macro_avg']['fuzzy_pct']:.2f}%",
            f"{agg_scan.get('macro_avg', {}).get('exact_pct', 0.0):.2f}%" if agg_scan else "-",
            f"{agg_emb.get('macro_avg', {}).get('exact_pct', 0.0):.2f}%" if agg_emb else "-",
            total_all_tokens,
            f"${total_cost_usd:.4f}",
            f"Rp{total_cost_idr:,.2f}",
            avg_tokens,
            f"${avg_usd:.6f}",
            f"Rp{avg_idr:.2f}",
            f"{avg_lat:.2f}s",
        ])

    # 4. Simpan report.md
    report_md_path = os.path.join(run_dir, "report.md")
    report_lines = [
        f"# Benchmark Report: Direct Tesseract-to-LLM Extraction ({model})",
        "",
        f"- **Model**: `{model}`",
        f"- **Run ID**: `{run_name}`",
        f"- **Tanggal & Waktu**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- **Jumlah Sertifikat**: {len(cert_results)} (Scan: {len(scan_certs)}, Embedded: {len(emb_certs)})",
        f"- **Kurs IDR/USD**: Rp{exchange_rate:,.2f} per 2 Agustus 2026",
        "",
        "## 1. Ringkasan Metrik Utama",
        "",
        "| Metrik Evaluasi | All-74 Sertifikat | 49 Scan Sertifikat | 25 Embedded Sertifikat |",
        "|---|:---:|:---:|:---:|",
        f"| **MACRO Exact (All-Cells 6-Field)** | **{agg_all['macro_avg']['exact_pct']:.2f}%** | {agg_scan.get('macro_avg', {}).get('exact_pct', 0.0):.2f}% | {agg_emb.get('macro_avg', {}).get('exact_pct', 0.0):.2f}% |",
        f"| **MACRO Fuzzy (All-Cells 6-Field)** | **{agg_all['macro_avg']['fuzzy_pct']:.2f}%** | {agg_scan.get('macro_avg', {}).get('fuzzy_pct', 0.0):.2f}% | {agg_emb.get('macro_avg', {}).get('fuzzy_pct', 0.0):.2f}% |",
        f"| **Framework Exact (5-Field)** | **{agg_framework_all['macro_avg']['exact_pct']:.2f}%** | {agg_framework_scan.get('macro_avg', {}).get('exact_pct', 0.0):.2f}% | {agg_framework_emb.get('macro_avg', {}).get('exact_pct', 0.0):.2f}% |",
        f"| **Framework Fuzzy (5-Field)** | **{agg_framework_all['macro_avg']['fuzzy_pct']:.2f}%** | {agg_framework_scan.get('macro_avg', {}).get('fuzzy_pct', 0.0):.2f}% | {agg_framework_emb.get('macro_avg', {}).get('fuzzy_pct', 0.0):.2f}% |",
        "",
        "## 2. Rincian Akurasi per Field (All-74)",
        "",
        "| Nama Field | Total Sel | Exact (%) | Fuzzy (%) | Avg WER | Avg CER |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ]

    for f in ALL_EVAL_FIELDS:
        fa = agg_all[f]
        report_lines.append(
            f"| `{f}` | {fa['total']} | **{fa['exact_pct']:.2f}%** ({fa['exact']}/{fa['total']}) | "
            f"{fa['fuzzy_pct']:.2f}% ({fa['fuzzy']}/{fa['total']}) | {fa['avg_wer']:.4f} | {fa['avg_cer']:.4f} |"
        )

    report_lines.extend([
        "",
        "## 3. Konsumsi Token & Rincian Biaya (USD & IDR)",
        "",
        "| Komponen | Total Kumulatif | Rata-rata per Sertifikat |",
        "|---|:---:|:---:|",
        f"| Prompt Tokens | {total_prompt_tokens:,} | {round(total_prompt_tokens / n_certs, 1):,} |",
        f"| Candidates Tokens | {total_cand_tokens:,} | {round(total_cand_tokens / n_certs, 1):,} |",
        f"| Thoughts Tokens | {total_thoughts_tokens:,} | {round(total_thoughts_tokens / n_certs, 1):,} |",
        f"| Total Tokens | {total_all_tokens:,} | {avg_tokens:,} |",
        f"| **Estimasi Biaya USD** | **${total_cost_usd:.4f}** | **${avg_usd:.6f}** |",
        f"| **Estimasi Biaya IDR** | **Rp{total_cost_idr:,.2f}** | **Rp{avg_idr:.2f}** |",
        f"| **Rata-rata Latensi** | {total_latency_s:.2f}s | **{avg_lat:.2f}s/cert** |",
        "",
        "## 4. Contoh Konkret 5 Sertifikat: Prediksi vs Ground Truth",
        "",
    ])

    sample_certs = cert_results[:5]
    for s_idx, sc in enumerate(sample_certs, 1):
        report_lines.append(f"### Contoh {s_idx}: `{sc['stem']}` ({sc['doc_type']})")
        report_lines.append(f"- Status: `{sc['call_result']['status']}` | Tokens: {sc['call_result']['total_tokens']} | Biaya: Rp{sc['call_result']['cost_idr']:.2f} | Latensi: {sc['call_result']['latency_s']:.2f}s")
        report_lines.append("")
        report_lines.append("| Field | Prediksi LLM | Ground Truth v9 | Status Exact | Status Fuzzy |")
        report_lines.append("|---|---|---|:---:|:---:|")
        for f in ALL_EVAL_FIELDS:
            fe = sc["evaluation"][f]
            p_val = fe["pred"] or "*(null)*"
            g_val = fe["gt"] or "*(null)*"
            e_sym = "✅ EXACT" if fe["exact"] else "❌ MISMATCH"
            f_sym = "✅ MATCH" if fe["fuzzy"] else "❌ MISMATCH"
            report_lines.append(f"| `{f}` | {p_val} | {g_val} | {e_sym} | {f_sym} |")
        report_lines.append("")

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n[DONE] Model {model}: MACRO Exact = {agg_all['macro_avg']['exact_pct']:.2f}%, "
          f"Total IDR = Rp{total_cost_idr:,.2f}, Avg Latency = {avg_lat:.2f}s")
    print(f"Artifacts saved in: {run_dir}\n")

    return run_results_payload


def generate_consolidated_reports(
    all_runs: list[dict[str, Any]],
    report_dir: str = os.path.join(REPO_ROOT, "docs", "report"),
) -> None:
    """Buat laporan perbandingan gabungan 3 model di docs/report/."""
    os.makedirs(report_dir, exist_ok=True)
    comp_csv_path = os.path.join(report_dir, "gemini_models_comparison.csv")
    comp_md_path = os.path.join(report_dir, "gemini_tesseract_benchmark_report.md")
    reg_md_path = os.path.join(report_dir, "gemini_prompt_and_config_registry.md")

    exchange_rate = get_exchange_rate()

    # 1. Comparison CSV
    with open(comp_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "model",
            "n_certs",
            "macro_exact_6field",
            "macro_fuzzy_6field",
            "framework_exact_5field",
            "framework_fuzzy_5field",
            "scan_macro_exact",
            "emb_macro_exact",
            "nama_kegiatan_exact",
            "nomor_exact",
            "organizer_exact",
            "tanggal_mulai_exact",
            "tanggal_selesai_exact",
            "tingkat_exact",
            "total_tokens",
            "total_cost_usd",
            "total_cost_idr",
            "avg_tokens_per_cert",
            "avg_cost_idr_per_cert",
            "avg_latency_s",
        ])

        for run in all_runs:
            meta = run["metadata"]
            agg = meta["aggregates"]["all_cells_6field"]["all"]
            agg_fw = meta["aggregates"]["framework_5field"]["all"]
            agg_scan = meta["aggregates"]["all_cells_6field"]["scan"]
            agg_emb = meta["aggregates"]["all_cells_6field"]["embedded"]
            tots = meta["totals"]
            avgs = meta["averages_per_cert"]

            writer.writerow([
                meta["model"],
                meta["dataset_size"],
                f"{agg['macro_avg']['exact_pct']:.2f}%",
                f"{agg['macro_avg']['fuzzy_pct']:.2f}%",
                f"{agg_fw['macro_avg']['exact_pct']:.2f}%",
                f"{agg_fw['macro_avg']['fuzzy_pct']:.2f}%",
                f"{agg_scan.get('macro_avg', {}).get('exact_pct', 0.0):.2f}%" if agg_scan else "-",
                f"{agg_emb.get('macro_avg', {}).get('exact_pct', 0.0):.2f}%" if agg_emb else "-",
                f"{agg['nama_kegiatan_sertifikasi']['exact_pct']:.2f}%",
                f"{agg['nomor_bukti_fisik_nomor_sertifikasi']['exact_pct']:.2f}%",
                f"{agg['penyelenggara_kegiatan']['exact_pct']:.2f}%",
                f"{agg['waktu_mulai_pelaksanaan']['exact_pct']:.2f}%",
                f"{agg['waktu_selesai_pelaksanaan']['exact_pct']:.2f}%",
                f"{agg['tingkat']['exact_pct']:.2f}%",
                tots["total_tokens"],
                f"${tots['cost_usd']:.4f}",
                f"Rp{tots['cost_idr']:,.2f}",
                avgs["tokens"],
                f"Rp{avgs['cost_idr']:.2f}",
                f"{avgs['latency_s']:.2f}s",
            ])

    # 2. Consolidated Markdown Report
    lines = [
        "# Laporan Komparatif: Direct Tesseract-to-Gemini Extraction Benchmark",
        "",
        "> Evaluasi komparatif end-to-end ekstraksi 6 field sertifikat KHP langsung dari teks mentah OCR Tesseract",
        f"> menggunakan 3 model Google Gemini (`gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`).",
        f"> Tanggal evaluasi: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` | Kurs acuan: Rp{exchange_rate:,.2f} per USD.",
        "",
        "## 1. Tabel Komparasi Utama",
        "",
        "| Model | MACRO Exact (6-Field) | MACRO Fuzzy (6-Field) | Framework Exact (5-Field) | Scan-49 Exact | Emb-25 Exact | Avg Tokens/Cert | Avg Cost/Cert (IDR) | Avg Latency |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for run in all_runs:
        meta = run["metadata"]
        agg = meta["aggregates"]["all_cells_6field"]["all"]
        agg_fw = meta["aggregates"]["framework_5field"]["all"]
        agg_scan = meta["aggregates"]["all_cells_6field"]["scan"]
        agg_emb = meta["aggregates"]["all_cells_6field"]["embedded"]
        avgs = meta["averages_per_cert"]
        lines.append(
            f"| **`{meta['model']}`** | **{agg['macro_avg']['exact_pct']:.2f}%** | {agg['macro_avg']['fuzzy_pct']:.2f}% | "
            f"{agg_fw['macro_avg']['exact_pct']:.2f}% | {agg_scan.get('macro_avg', {}).get('exact_pct', 0.0):.2f}% | "
            f"{agg_emb.get('macro_avg', {}).get('exact_pct', 0.0):.2f}% | {avgs['tokens']:,} | Rp{avgs['cost_idr']:.2f} | {avgs['latency_s']:.2f}s |"
        )

    lines.extend([
        "",
        "## 2. Perbandingan Akurasi per Field (Exact %)",
        "",
        "| Model | Nama Kegiatan | Nomor Sertifikat | Penyelenggara | Tanggal Mulai | Tanggal Selesai | Tingkat |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for run in all_runs:
        meta = run["metadata"]
        agg = meta["aggregates"]["all_cells_6field"]["all"]
        lines.append(
            f"| `{meta['model']}` | {agg['nama_kegiatan_sertifikasi']['exact_pct']:.1f}% | "
            f"{agg['nomor_bukti_fisik_nomor_sertifikasi']['exact_pct']:.1f}% | "
            f"{agg['penyelenggara_kegiatan']['exact_pct']:.1f}% | "
            f"{agg['waktu_mulai_pelaksanaan']['exact_pct']:.1f}% | "
            f"{agg['waktu_selesai_pelaksanaan']['exact_pct']:.1f}% | "
            f"{agg['tingkat']['exact_pct']:.1f}% |"
        )

    lines.extend([
        "",
        "## 3. Analisis Biaya dan Efisiensi Token",
        "",
        "| Model | Total Tokens | Total Biaya (USD) | Total Biaya (IDR) | Tarif Input / 1M | Tarif Output / 1M |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ])

    for run in all_runs:
        meta = run["metadata"]
        tots = meta["totals"]
        p = meta["pricing"]
        lines.append(
            f"| `{meta['model']}` | {tots['total_tokens']:,} | ${tots['cost_usd']:.4f} | Rp{tots['cost_idr']:,.2f} | "
            f"${p.get('input_rate', 0):.2f} | ${p.get('output_rate', 0):.2f} |"
        )

    lines.extend([
        "",
        "## 4. Kesimpulan dan Model Pemenang",
        "",
    ])

    winner = max(all_runs, key=lambda r: r["metadata"]["aggregates"]["all_cells_6field"]["all"]["macro_avg"]["exact_pct"])
    w_meta = winner["metadata"]
    w_agg = w_meta["aggregates"]["all_cells_6field"]["all"]

    lines.append(
        f"- **Model Pemenang**: `{w_meta['model']}` dengan MACRO exact **{w_agg['macro_avg']['exact_pct']:.2f}%** "
        f"(Framework: {w_meta['aggregates']['framework_5field']['all']['macro_avg']['exact_pct']:.2f}%)."
    )
    lines.append(
        f"- **Efisiensi Finansial**: Biaya rata-rata hanya **Rp{w_meta['averages_per_cert']['cost_idr']:.2f} per sertifikat** "
        f"dengan latensi {w_meta['averages_per_cert']['latency_s']:.2f}s."
    )

    with open(comp_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 3. Prompt & Config Registry
    reg_lines = [
        "# Gemini Prompt and Configuration Registry",
        "",
        f"> Terdaftar per `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## System Instruction",
        "```text",
        SYSTEM_INSTRUCTION_STANDARD.strip(),
        "```",
        "",
        "## User Prompt Template",
        "```text",
        USER_PROMPT_TEMPLATE.strip(),
        "```",
        "",
        "## Generation Config",
        "- `temperature`: 0.0 (deterministik & reproduktif)",
        "- `responseMimeType`: application/json",
        "- `request_delay`: 1.2 detik (pacing anti rate-limit)",
        "- `max_retries`: 3 (exponential backoff)",
    ]
    with open(reg_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(reg_lines))

    print(f"\n[CONSOLIDATED] Reports generated at:")
    print(f" - {comp_csv_path}")
    print(f" - {comp_md_path}")
    print(f" - {reg_md_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct Tesseract-to-Gemini Extraction Benchmark")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash", help="Model Gemini yang diuji")
    parser.add_argument("--all-models", action="store_true", help="Uji ketiga model (gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3.1-flash-lite)")
    parser.add_argument("--limit", type=int, default=None, help="Batasi jumlah sertifikat (misal: 3 untuk smoke test)")
    parser.add_argument("--texts-dir", type=str, default=DEFAULT_TEXTS_DIR, help="Direktori teks Tesseract OCR")
    parser.add_argument("--gt-csv", type=str, default=DEFAULT_GT_PATH, help="Path ke Ground Truth v9 CSV")
    parser.add_argument("--out-dir", type=str, default=DEFAULT_OUT_DIR, help="Direktori output run benchmark")
    parser.add_argument("--request-delay", type=float, default=1.2, help="Delay pacing antar-request dalam detik")

    args = parser.parse_args()

    models_to_run = EVAL_MODELS if args.all_models else [args.model]
    all_runs: list[dict[str, Any]] = []

    for m in models_to_run:
        res = run_benchmark_for_model(
            model=m,
            texts_dir=args.texts_dir,
            gt_csv_path=args.gt_csv,
            out_root=args.out_dir,
            limit=args.limit,
            request_delay=args.request_delay,
            verbose=True,
        )
        all_runs.append(res)

    if len(all_runs) > 1:
        generate_consolidated_reports(all_runs)


if __name__ == "__main__":
    main()
