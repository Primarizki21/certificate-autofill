"""Empirical 4-Layer Generalization & Robustness Proof for Gemini Extraction.

Implements the mandatory 4-layer empirical proof required by AGENTS.md:
  1. Layer 1: Statistical Holdout (stratified fixed-prediction split) + Bootstrap 1000x CI
  2. Layer 2: Out-of-Distribution (OOD) Robustness (Template/Entity Mutation + OCR Noise 10/25/50%)
  3. Layer 3: Structural Semantic Anchors Audit (Anti-Hardcoding & De-Corpusing Audit)
  4. Layer 4: Production Safety Net & Calibrated Confidence Review Calibration (Recall >= 95%)

Outputs full tabular proof to docs/report/gemini_4layer_empirical_proof.md.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import sys
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
from tests.gemini_client import GeminiClient
from tests.gemini_field_extractor import (
    ALL_EVAL_FIELDS,
    SYSTEM_INSTRUCTION_STANDARD,
    USER_PROMPT_TEMPLATE,
    extract_fields_from_ocr,
)
from tests.matchers import match_field
from tests.ood_probe import CONFUSIONS, MUTATIONS, inject_noise, mutate

# Hardcoded corpus keywords yang diaudit untuk Lapis 3 (harus 0 kemunculan di prompt)
CORPUS_EVENT_KEYWORDS = [
    "SPECTA",
    "KARSA",
    "FALCON",
    "HEALTH BUDDIES",
    "DIGITAL CAMPAIGN",
    "GIVE YOURSELF A BREAK",
    "FROM DISCRETE MATHEMATICS",
    "AGENTIC AI",
    "AIRNOLOGY",
    "KAKIWIMA",
    "BRIEF",
    "VENEDICT",
    "MAWACANA",
    "ANANDA",
]


def find_latest_benchmark_json(runs_root: str) -> str | None:
    """Cari run_results.json terbaru di direktori benchmark runs."""
    p = Path(runs_root)
    if not p.exists():
        return None
    candidates = list(p.glob("gemini_*/run_results.json"))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(candidates[0])


# ==============================================================================
# LAPIS 1: VALIDASI STATISTIK (5-FOLD CV & BOOTSTRAP 1000X CI)
# ==============================================================================

def run_stratified_5fold_cv(certificates: list[dict[str, Any]], seed: int = 42) -> dict[str, Any]:
    """Ukur holdout terstratifikasi dari prediction tetap, bukan fitting CV."""
    rng = random.Random(seed)

    scans = [c for c in certificates if c.get("doc_type") == "scan"]
    embedded = [c for c in certificates if c.get("doc_type") == "embedded"]
    others = [c for c in certificates if c.get("doc_type") not in ("scan", "embedded")]

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

    fold_metrics: list[dict[str, Any]] = []

    for fold_idx in range(k):
        holdout = folds[fold_idx]
        total_cells = 0
        exact_cells = 0
        field_exact: dict[str, int] = {f: 0 for f in ALL_EVAL_FIELDS}
        field_total: dict[str, int] = {f: 0 for f in ALL_EVAL_FIELDS}

        for cert in holdout:
            ev = cert["evaluation"]
            for f in ALL_EVAL_FIELDS:
                total_cells += 1
                field_total[f] += 1
                if ev[f]["exact"]:
                    exact_cells += 1
                    field_exact[f] += 1

        fold_acc = (exact_cells / total_cells * 100) if total_cells else 0.0
        fold_metrics.append({
            "fold": fold_idx + 1,
            "n_certs": len(holdout),
            "macro_exact_pct": round(fold_acc, 2),
            "per_field_exact_pct": {
                f: round(field_exact[f] / field_total[f] * 100, 2) if field_total[f] else 0.0
                for f in ALL_EVAL_FIELDS
            },
        })

    accuracies = [fm["macro_exact_pct"] for fm in fold_metrics]
    mean_acc = sum(accuracies) / k
    variance = sum((a - mean_acc) ** 2 for a in accuracies) / (k - 1)
    std_dev = variance ** 0.5
    min_fold = min(accuracies)

    return {
        "status": "DESCRIPTIVE_FIXED_PIPELINE_HOLDOUT",
        "method": "stratified_5fold_holdout_on_fixed_predictions",
        "independent_model_fit_per_fold": False,
        "k_folds": k,
        "fold_results": fold_metrics,
        "mean_macro_exact_pct": round(mean_acc, 2),
        "std_dev_pct": round(std_dev, 2),
        "min_fold_accuracy_pct": round(min_fold, 2),
    }


def run_bootstrap_resampling(certificates: list[dict[str, Any]], n_bootstraps: int = 1000, seed: int = 42) -> dict[str, Any]:
    """Hitung 95% Confidence Interval untuk MACRO exact dan per-field via Bootstrap 1000x."""
    rng = random.Random(seed)
    n = len(certificates)
    if n == 0:
        return {}

    boot_macro: list[float] = []
    boot_fields: dict[str, list[float]] = {f: [] for f in ALL_EVAL_FIELDS}

    for _ in range(n_bootstraps):
        sample = [certificates[rng.randint(0, n - 1)] for _ in range(n)]
        tot_cells = 0
        ex_cells = 0
        f_tot = {f: 0 for f in ALL_EVAL_FIELDS}
        f_ex = {f: 0 for f in ALL_EVAL_FIELDS}

        for cert in sample:
            ev = cert["evaluation"]
            for f in ALL_EVAL_FIELDS:
                tot_cells += 1
                f_tot[f] += 1
                if ev[f]["exact"]:
                    ex_cells += 1
                    f_ex[f] += 1

        boot_macro.append(ex_cells / tot_cells * 100.0)
        for f in ALL_EVAL_FIELDS:
            boot_fields[f].append(f_ex[f] / f_tot[f] * 100.0 if f_tot[f] else 0.0)

    boot_macro.sort()
    idx_lower = int(0.025 * n_bootstraps)
    idx_upper = int(0.975 * n_bootstraps)

    ci_macro = (round(boot_macro[idx_lower], 2), round(boot_macro[idx_upper], 2))

    ci_fields: dict[str, tuple[float, float]] = {}
    for f in ALL_EVAL_FIELDS:
        boot_fields[f].sort()
        ci_fields[f] = (
            round(boot_fields[f][idx_lower], 2),
            round(boot_fields[f][idx_upper], 2),
        )

    return {
        "n_bootstraps": n_bootstraps,
        "macro_exact_mean_pct": round(sum(boot_macro) / n_bootstraps, 2),
        "macro_exact_95_ci": ci_macro,
        "per_field_95_ci": ci_fields,
    }

def summarize_gemini_calls(calls: list[tuple[str, Any]]) -> dict[str, Any]:
    """Ringkas token, biaya, latensi, status, dan kueri per panggilan."""
    totals = {
        "prompt_tokens": 0,
        "candidates_tokens": 0,
        "cached_tokens": 0,
        "thoughts_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "cost_idr": 0.0,
        "latency_s": 0.0,
    }
    details: list[dict[str, Any]] = []
    web_search_queries: list[str] = []
    for call_index, (stem, result) in enumerate(calls, start=1):
        prompt_tokens = int(result.prompt_tokens or 0)
        candidates_tokens = int(result.candidates_tokens or 0)
        cached_tokens = int(result.cached_tokens or 0)
        thoughts_tokens = int(result.thoughts_tokens or 0)
        total_tokens = prompt_tokens + candidates_tokens + thoughts_tokens
        queries = list(result.web_search_queries or [])
        totals["prompt_tokens"] += prompt_tokens
        totals["candidates_tokens"] += candidates_tokens
        totals["cached_tokens"] += cached_tokens
        totals["thoughts_tokens"] += thoughts_tokens
        totals["total_tokens"] += total_tokens
        totals["cost_usd"] += float(result.cost_usd or 0.0)
        totals["cost_idr"] += float(result.cost_idr or 0.0)
        totals["latency_s"] += float(result.latency_s or 0.0)
        web_search_queries.extend(queries)
        details.append(
            {
                "call_index": call_index,
                "stem": stem,
                "status": result.status,
                "prompt_tokens": prompt_tokens,
                "candidates_tokens": candidates_tokens,
                "cached_tokens": cached_tokens,
                "thoughts_tokens": thoughts_tokens,
                "total_tokens": total_tokens,
                "cost_usd": float(result.cost_usd or 0.0),
                "cost_idr": float(result.cost_idr or 0.0),
                "latency_s": float(result.latency_s or 0.0),
                "web_search_queries": queries,
                "error": result.error_message,
            }
        )
    call_count = len(calls)
    return {
        "total_calls": call_count,
        "prompt_tokens": totals["prompt_tokens"],
        "candidates_tokens": totals["candidates_tokens"],
        "cached_tokens": totals["cached_tokens"],
        "thoughts_tokens": totals["thoughts_tokens"],
        "total_tokens": totals["total_tokens"],
        "total_cost_usd": round(totals["cost_usd"], 6),
        "total_cost_idr": round(totals["cost_idr"], 2),
        "avg_latency_s": round(totals["latency_s"] / call_count, 4) if call_count else 0.0,
        "web_search_queries": web_search_queries,
        "calls_details": details,
    }


# ==============================================================================
# LAPIS 2: UJI KETAHANAN OOD (MUTASI ENTITAS & NOISE OCR)
# ==============================================================================

def run_ood_stress_testing(
    certificates: list[dict[str, Any]],
    texts_dir: str,
    client: GeminiClient,
    model: str,
    subset_size: int = 15,
) -> dict[str, Any]:
    """Uji ketahanan model terhadap mutasi entitas dan injeksi noise karakter OCR nyata."""
    rng = random.Random(42)

    # Pilih subset terstratifikasi jika subset_size < len(certificates)
    scans = [c for c in certificates if c.get("doc_type") == "scan"]
    embedded = [c for c in certificates if c.get("doc_type") == "embedded"]

    sample: list[dict[str, Any]] = []
    if subset_size and subset_size < len(certificates):
        n_scan = min(len(scans), int(subset_size * (len(scans) / len(certificates))))
        n_emb = subset_size - n_scan
        sample = rng.sample(scans, n_scan) + rng.sample(embedded, min(len(embedded), n_emb))
    else:
        sample = list(certificates)
    texts_path = Path(texts_dir)
    if not texts_path.is_dir():
        raise FileNotFoundError(f"Direktori teks OCR tidak ditemukan: {texts_path}")
    missing_texts = [
        c["stem"] for c in sample if not (texts_path / f"{c['stem']}.txt").is_file()
    ]
    if missing_texts:
        raise FileNotFoundError(
            f"Teks OCR tidak lengkap untuk {len(missing_texts)} dokumen: "
            f"{missing_texts[:5]}"
        )
    empty_texts = [
        c["stem"]
        for c in sample
        if not (texts_path / f"{c['stem']}.txt").read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    ]
    if empty_texts:
        raise ValueError(f"Teks OCR kosong untuk dokumen: {empty_texts[:5]}")

    print(f"\n--- MENJALANKAN LAPIS 2: OOD STRESS TEST ({len(sample)} sertifikat terstratifikasi) ---")

    # Baseline unperturbed pada sample
    base_free_exact = 0
    base_free_total = 0
    FREE_FIELDS = [
        "nama_kegiatan_sertifikasi",
        "waktu_mulai_pelaksanaan",
        "waktu_selesai_pelaksanaan",
        "nomor_bukti_fisik_nomor_sertifikasi",
    ]

    for c in sample:
        ev = c["evaluation"]
        for f in FREE_FIELDS:
            base_free_total += 1
            if ev[f]["exact"]:
                base_free_exact += 1

    base_free_pct = round(base_free_exact / base_free_total * 100, 2) if base_free_total else 0.0
    base_all_exact = sum(
        int(c["evaluation"][field]["exact"])
        for c in sample
        for field in ALL_EVAL_FIELDS
    )
    base_all_total = len(sample) * len(ALL_EVAL_FIELDS)
    base_all_pct = (
        round(base_all_exact / base_all_total * 100, 2) if base_all_total else 0.0
    )

    # 1. Mutasi Entitas
    mut_free_exact = 0
    mutation_calls: list[tuple[str, Any]] = []
    mut_free_total = 0
    print(" 1. Menguji Mutasi Entitas (UNAIR->UNS, FTMM->FST, event generik)...")

    for idx, c in enumerate(sample, 1):
        stem = c["stem"]
        txt_p = texts_path / f"{stem}.txt"
        if not txt_p.exists():
            continue
        raw_text = txt_p.read_text(encoding="utf-8", errors="replace")
        mutated_text = mutate(raw_text)

        mapped, call_result = extract_fields_from_ocr(
            raw_ocr_text=mutated_text,
            client=client,
            model=model,
            temperature=0.0,
        )
        mutation_calls.append((stem, call_result))

        for f in FREE_FIELDS:
            mut_free_total += 1
            # Evaluasi field bebas instansi terhadap GT awal
            gt_val = c["evaluation"][f]["gt"]
            pred_val = (mapped.get(f).value or "") if mapped.get(f) else ""
            m = match_field(gt_val, pred_val, f)
            if m["exact"]:
                mut_free_exact += 1

    mut_free_pct = round(mut_free_exact / mut_free_total * 100, 2) if mut_free_total else 0.0
    mut_drop = round(base_free_pct - mut_free_pct, 2)
    mut_pass = mut_drop <= 2.0

    # 2. Injeksi Noise OCR (10%, 25%, 50%)
    noise_results: dict[str, Any] = {}
    noise_calls: dict[str, list[tuple[str, Any]]] = {}
    for noise_level in (0.10, 0.25, 0.50):
        print(f" 2. Menguji Injeksi Noise OCR {int(noise_level*100)}%...")
        noise_exact = 0
        noise_total = 0

        for c in sample:
            stem = c["stem"]
            txt_p = texts_path / f"{stem}.txt"
            if not txt_p.exists():
                continue
            raw_text = txt_p.read_text(encoding="utf-8", errors="replace")
            noisy_text = inject_noise(raw_text, noise_level, rng)

            mapped, call_result = extract_fields_from_ocr(
                raw_ocr_text=noisy_text,
                client=client,
                model=model,
                temperature=0.0,
            )
            noise_calls.setdefault(f"{int(noise_level*100)}%", []).append(
                (stem, call_result)
            )

            for f in ALL_EVAL_FIELDS:
                noise_total += 1
                gt_val = c["evaluation"][f]["gt"]
                pred_val = (mapped.get(f).value or "") if mapped.get(f) else ""
                m = match_field(gt_val, pred_val, f)
                if m["exact"]:
                    noise_exact += 1

        n_pct = round(noise_exact / noise_total * 100, 2) if noise_total else 0.0
        noise_key = f"{int(noise_level*100)}%"
        noise_results[noise_key] = {
            "exact_pct": n_pct,
            "drop_pct": round(base_all_pct - n_pct, 2),
            "token_rollup": summarize_gemini_calls(noise_calls.get(noise_key, [])),
        }

    return {
        "sample_size": len(sample),
        "baseline_free_institution_pct": base_free_pct,
        "mutation_free_institution_pct": mut_free_pct,
        "mutation_drop_pct": mut_drop,
        "mutation_gate_pass": mut_pass,
        "mutation_token_rollup": summarize_gemini_calls(mutation_calls),
        "baseline_all_cells_pct": base_all_pct,
        "noise_degradation_curve": noise_results,
    }


# ==============================================================================
# LAPIS 3: AUDIT ANCHOR STRUKTURAL (ANTI-HARDCODING)
# ==============================================================================
def run_anti_hardcoding_audit(
    system_instruction: str,
    prompt_template: str,
    source_files: tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Audit prompt dan source code terhadap literal event dari corpus."""
    violations: list[str] = []
    violation_locations: list[str] = []

    def scan_text(text: str, label: str) -> None:
        upper_text = text.upper()
        for keyword in CORPUS_EVENT_KEYWORDS:
            if re.search(
                rf"(?<![A-Z0-9]){re.escape(keyword.upper())}(?![A-Z0-9])",
                upper_text,
            ):
                violations.append(keyword)
                violation_locations.append(f"{label}:{keyword}")

    scan_text(system_instruction, "system_instruction")
    scan_text(prompt_template, "prompt_template")
    for path in source_files:
        if not path.exists():
            violations.append(f"{path}:missing")
            violation_locations.append(f"{path}:missing")
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path}:{exc.lineno}:syntax_error")
            violation_locations.append(f"{path}:{exc.lineno}:syntax_error")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                scan_text(node.value, f"{path}:{node.lineno}")

    return {
        "audited_keywords_count": len(CORPUS_EVENT_KEYWORDS),
        "audited_source_files": [str(path) for path in source_files],
        "violations_found": violations,
        "violation_locations": violation_locations,
        "anti_hardcoding_pass": len(violations) == 0,
    }

# ==============================================================================
# LAPIS 4: SAFETY NET PRODUKSI & CALIBRATED CONFIDENCE (REVIEW RECALL >= 95%)
# ==============================================================================

def run_safety_net_calibration(certificates: list[dict[str, Any]]) -> dict[str, Any]:
    """Ukur recall review pada cell dan dokumen secara terpisah."""
    cell_tp = cell_fp = cell_fn = cell_tn = 0
    doc_tp = doc_fp = doc_fn = doc_tn = 0

    for certificate in certificates:
        evaluation = certificate["evaluation"]
        doc_has_error = False
        doc_has_flag = False
        for field_name in ALL_EVAL_FIELDS:
            field_evaluation = evaluation[field_name]
            has_error = not field_evaluation["exact"]
            prediction = field_evaluation["pred"]
            confidence = field_evaluation["confidence"]
            flag_review = not prediction or confidence < 0.85
            if "tanggal" in field_name and prediction:
                flag_review = flag_review or not re.match(
                    r"^\d{2}/\d{2}/\d{4}$", prediction.strip()
                )
            doc_has_error = doc_has_error or has_error
            doc_has_flag = doc_has_flag or flag_review
            if has_error:
                if flag_review:
                    cell_tp += 1
                else:
                    cell_fn += 1
            elif flag_review:
                cell_fp += 1
            else:
                cell_tn += 1

        if doc_has_error:
            if doc_has_flag:
                doc_tp += 1
            else:
                doc_fn += 1
        elif doc_has_flag:
            doc_fp += 1
        else:
            doc_tn += 1

    def rates(tp: int, fp: int, fn: int, clean: int) -> dict[str, float]:
        errors = tp + fn
        flagged = tp + fp
        recall = round(tp / errors * 100, 2) if errors else 100.0
        precision = round(tp / flagged * 100, 2) if flagged else 0.0
        false_alarm = round(fp / clean * 100, 2) if clean else 0.0
        return {
            "recall_pct": recall,
            "precision_pct": precision,
            "false_alarm_pct": false_alarm,
        }

    cell_rates = rates(cell_tp, cell_fp, cell_fn, cell_fp + cell_tn)
    doc_rates = rates(doc_tp, doc_fp, doc_fn, doc_fp + doc_tn)
    return {
        "confusion_matrix": {
            "true_positive": doc_tp,
            "false_positive": doc_fp,
            "false_negative": doc_fn,
            "true_negative": doc_tn,
        },
        "cell_confusion_matrix": {
            "true_positive": cell_tp,
            "false_positive": cell_fp,
            "false_negative": cell_fn,
            "true_negative": cell_tn,
        },
        "doc_confusion_matrix": {
            "true_positive": doc_tp,
            "false_positive": doc_fp,
            "false_negative": doc_fn,
            "true_negative": doc_tn,
        },
        "cell_review_recall_pct": cell_rates["recall_pct"],
        "cell_review_precision_pct": cell_rates["precision_pct"],
        "cell_false_alarm_pct": cell_rates["false_alarm_pct"],
        "doc_review_recall_pct": doc_rates["recall_pct"],
        "doc_review_precision_pct": doc_rates["precision_pct"],
        "doc_false_alarm_pct": doc_rates["false_alarm_pct"],
        "review_recall_pct": cell_rates["recall_pct"],
        "review_precision_pct": cell_rates["precision_pct"],
        "false_alarm_pct": cell_rates["false_alarm_pct"],
        "gate_recall_pass": cell_rates["recall_pct"] >= 95.0,
        "minimum_cell_review_recall_pct": 95.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 4-Layer Empirical Proof for Gemini Extraction")
    parser.add_argument("--run-json", type=str, default=None, help="Path ke run_results.json hasil benchmark")
    parser.add_argument("--runs-root", type=str, default=os.path.join(REPO_ROOT, "tests", "benchmark_runs", "ocr_experiment"), help="Direktori root benchmark runs")
    parser.add_argument("--texts-dir", type=str, default=os.path.join(REPO_ROOT, "tests", "benchmark_runs", "ocr_experiment", "tesseract_primary_v4", "extracted_texts"), help="Direktori teks Tesseract OCR")
    parser.add_argument("--model", type=str, default=None, help="Model yang diuji pada Lapis 2 OOD")
    parser.add_argument("--full", action="store_true", help="Jalankan OOD pada 74 sertifikat penuh (bukan sampel 15)")
    parser.add_argument("--out-dir", type=str, default=os.path.join(REPO_ROOT, "docs", "report"), help="Direktori penyimpanan laporan bukti empiris")

    args = parser.parse_args()

    run_json_path = args.run_json or find_latest_benchmark_json(args.runs_root)
    if not run_json_path or not os.path.exists(run_json_path):
        print(f"[ERROR] run_results.json tidak ditemukan di {run_json_path}! Jalankan benchmark_gemini_tesseract terlebih dahulu.")
        sys.exit(1)

    print(f"\n=======================================================")
    print(f"MENJALANKAN 4 LAPIS PEMBUKTIAN EMPIRIS AGENTS.md")
    print(f"=======================================================")
    print(f"Artifact JSON : {run_json_path}")

    with open(run_json_path, "r", encoding="utf-8") as f:
        run_data = json.load(f)

    meta = run_data["metadata"]
    certs = run_data["certificates"]
    model_name = args.model or meta.get("model", "gemini-2.5-flash")
    ah_res = run_anti_hardcoding_audit(
        SYSTEM_INSTRUCTION_STANDARD,
        USER_PROMPT_TEMPLATE,
        source_files=(
            Path(REPO_ROOT) / "tests/gemini_field_extractor.py",
            Path(REPO_ROOT) / "tests/benchmark_gemini_tesseract.py",
        ),
    )
    # Lapis 1: Validasi statistik deskriptif
    print("-> Lapis 1: 5-Fold Stratified Holdout (fixed predictions; bukan fitting CV)...")
    cv_res = run_stratified_5fold_cv(certs, seed=42)
    print(
        f"   Mean Fold Accuracy : {cv_res['mean_macro_exact_pct']}% "
        f"(Std Dev: {cv_res['std_dev_pct']}%, Min-Fold: {cv_res['min_fold_accuracy_pct']}%)"
    )

    print("-> Lapis 1: Bootstrap 1000x Resampling (95% CI)...")
    boot_res = run_bootstrap_resampling(certs, n_bootstraps=1000, seed=42)
    print(f"   MACRO Exact 95% CI : {boot_res['macro_exact_95_ci'][0]}% - {boot_res['macro_exact_95_ci'][1]}%")

    # Lapis 2: OOD Stress Testing
    client = GeminiClient(default_model=model_name, request_delay=1.2)
    subset_size = len(certs) if args.full else 15
    ood_res = run_ood_stress_testing(certs, args.texts_dir, client, model_name, subset_size=subset_size)
    print(f"   Mutation Free-Inst Drop : {ood_res['mutation_drop_pct']}pt (Gate <= 2.0pt: {'PASS' if ood_res['mutation_gate_pass'] else 'FAIL'})")
    print(f"   Noise Degradation       : 10%={ood_res['noise_degradation_curve'].get('10%', {}).get('exact_pct')}%, 25%={ood_res['noise_degradation_curve'].get('25%', {}).get('exact_pct')}%, 50%={ood_res['noise_degradation_curve'].get('50%', {}).get('exact_pct')}%")

    # Lapis 3: Audit Anchor Struktural
    print("-> Lapis 3: Audit Anchor Semantik Struktural (Anti-Hardcoding)...")
    print("-> Lapis 4: Evaluasi Safety Net & Calibrated Confidence...")
    sn_res = run_safety_net_calibration(certs)
    print(
        f"   Cell Review Recall    : {sn_res['cell_review_recall_pct']}% "
        f"(Gate >= 95%: {'PASS' if sn_res['gate_recall_pass'] else 'FAIL'})"
    )
    print(
        f"   Cell Review Precision : {sn_res['cell_review_precision_pct']}% | "
        f"Doc Recall: {sn_res['doc_review_recall_pct']}%"
    )

    # Susun Laporan Markdown Bukti Empiris
    os.makedirs(args.out_dir, exist_ok=True)
    out_md_path = os.path.join(args.out_dir, "gemini_4layer_empirical_proof.md")

    md_lines = [
        f"# Empat Lapis Pembuktian Empiris: Evaluasi Generalisasi & Ketahanan ({model_name})",
        "",
        "## 1. Lapis 1: Holdout Statistik Deskriptif & Bootstrap 1000x CI",
        "",
        "> Fold memakai prediction tetap; tidak ada fitting model terpisah per fold. Angka ini bukan bukti cross-validation independen.",
        "",
        "### Tabel 5-Fold Stratified Holdout (Scan vs Embedded)",
        "| Fold | Jumlah Sertifikat | MACRO Exact (%) |",
        "|:---:|:---:|:---:|",
    ]

    for f_info in cv_res["fold_results"]:
        md_lines.append(f"| Fold {f_info['fold']} | {f_info['n_certs']} | {f_info['macro_exact_pct']:.2f}% |")

    md_lines.extend([
        "",
        f"- **Rata-rata 5-Fold Holdout**: **{cv_res['mean_macro_exact_pct']:.2f}%**",
        f"- **Standar Deviasi**: **±{cv_res['std_dev_pct']:.2f}%**",
        f"- **Min-Fold Accuracy**: **{cv_res['min_fold_accuracy_pct']:.2f}%**",
        f"- **Status**: **{cv_res['status']}**",
        "",
        "### Bootstrap Resampling 1000x (95% Confidence Interval)",
        "",
        "| Field | Mean Estimasi (%) | 95% Confidence Interval |",
        "|---|:---:|:---:|",
        f"| **MACRO Exact (All-Cells)** | **{boot_res['macro_exact_mean_pct']:.2f}%** | **[{boot_res['macro_exact_95_ci'][0]:.2f}%, {boot_res['macro_exact_95_ci'][1]:.2f}%]** |",
    ])

    for f in ALL_EVAL_FIELDS:
        ci_f = boot_res["per_field_95_ci"][f]
        md_lines.append(f"| `{f}` | — | [{ci_f[0]:.2f}%, {ci_f[1]:.2f}%] |")

    md_lines.extend([
        "",
        "## 2. Lapis 2: Uji Ketahanan Out-of-Distribution (OOD)",
        "",
        f"- **Ukuran Sampel Terstratifikasi**: {ood_res['sample_size']} sertifikat",
        f"- **Akurasi Baseline Field Bebas-Institusi**: {ood_res['baseline_free_institution_pct']:.2f}%",
        f"- **Akurasi Pasca-Mutasi Entitas (UNAIR->UNS, FTMM->FST)**: {ood_res['mutation_free_institution_pct']:.2f}%",
        f"- **Penurunan Akurasi (Delta)**: **{ood_res['mutation_drop_pct']:.2f}pt** (Ambang batas toleransi <= 2.0pt: **{'PASS' if ood_res['mutation_gate_pass'] else 'FAIL'}**)",
        "",
        "### Kurva Ketahanan terhadap Noise Karakter OCR Nyata",
        "",
        "| Tingkat Noise | Akurasi Pasca-Noise (%) | Penurunan Akurasi (pt) |",
        "|:---:|:---:|:---:|",
    ])

    for n_key, n_val in ood_res["noise_degradation_curve"].items():
        md_lines.append(f"| Noise {n_key} | {n_val['exact_pct']:.2f}% | -{n_val['drop_pct']:.2f}pt |")

    mutation_rollup = ood_res["mutation_token_rollup"]
    md_lines.extend(
        [
            "",
            f"- **Mutasi token**: {mutation_rollup['total_calls']} calls; "
            f"prompt={mutation_rollup['prompt_tokens']}, candidates={mutation_rollup['candidates_tokens']}, "
            f"cached={mutation_rollup['cached_tokens']}, thoughts={mutation_rollup['thoughts_tokens']}, "
            f"total={mutation_rollup['total_tokens']}, cost=Rp{mutation_rollup['total_cost_idr']:.2f}",
        ]
    )
    for n_key, n_val in ood_res["noise_degradation_curve"].items():
        rollup = n_val["token_rollup"]
        md_lines.append(
            f"- **Noise {n_key} token**: {rollup['total_calls']} calls; "
            f"prompt={rollup['prompt_tokens']}, candidates={rollup['candidates_tokens']}, "
            f"cached={rollup['cached_tokens']}, thoughts={rollup['thoughts_tokens']}, "
            f"total={rollup['total_tokens']}, cost=Rp{rollup['total_cost_idr']:.2f}"
        )

    md_lines.extend([
        "",
        "## 3. Lapis 3: Audit Anchor Semantik Struktural (Anti-Hardcoding)",
        "",
        "- **Metode**: Audit leksikal independen terhadap seluruh keyword event spesifik dari korpus 74 sertifikat.",
        f"- **Jumlah Keyword Diaudit**: {ah_res['audited_keywords_count']} entitas (SPECTA, KARSA, FALCON, BRIEF, AIRNOLOGY, dsb.)",
        f"- **Pelanggaran Ditemukan**: {len(ah_res['violations_found'])} kata kunci",
        f"- **Status Audit**: **{'PASS (100% Bebas Hardcoding Leksikal)' if ah_res['anti_hardcoding_pass'] else 'FAIL'}**",
        "",
        "### Confusion Matrix Safety Net Review (Cell)",
        "",
        "| Kategori | Prediksi Memiliki Error | Prediksi Sempurna (0 Error) | Total |",
        "|---|:---:|:---:|:---:|",
        f"| **Flagged (`needs_review=True`)** | **{sn_res['cell_confusion_matrix']['true_positive']}** (TP) | {sn_res['cell_confusion_matrix']['false_positive']} (FP) | {sn_res['cell_confusion_matrix']['true_positive'] + sn_res['cell_confusion_matrix']['false_positive']} |",
        f"| **Unflagged (`needs_review=False`)** | {sn_res['cell_confusion_matrix']['false_negative']} (FN) | {sn_res['cell_confusion_matrix']['true_negative']} (TN) | {sn_res['cell_confusion_matrix']['false_negative'] + sn_res['cell_confusion_matrix']['true_negative']} |",
        "",
        "### Confusion Matrix Safety Net Review (Dokumen)",
        "",
        "| Kategori | Prediksi Memiliki Error | Prediksi Sempurna (0 Error) | Total |",
        "|---|:---:|:---:|:---:|",
        f"| **Flagged (`needs_review=True`)** | **{sn_res['confusion_matrix']['true_positive']}** (TP) | {sn_res['confusion_matrix']['false_positive']} (FP) | {sn_res['confusion_matrix']['true_positive'] + sn_res['confusion_matrix']['false_positive']} |",
        f"| **Unflagged (`needs_review=False`)** | {sn_res['confusion_matrix']['false_negative']} (FN) | {sn_res['confusion_matrix']['true_negative']} (TN) | {sn_res['confusion_matrix']['false_negative'] + sn_res['confusion_matrix']['true_negative']} |",
        "",
        f"- **Cell Review Recall**: **{sn_res['cell_review_recall_pct']:.2f}%** (Target mandatori >= 95.0%: **{'PASS' if sn_res['gate_recall_pass'] else 'FAIL'}**)",
        f"- **Cell Review Precision**: **{sn_res['cell_review_precision_pct']:.2f}%**",
        f"- **Cell False Alarm Rate**: **{sn_res['cell_false_alarm_pct']:.2f}%**",
        f"- **Document Review Recall**: **{sn_res['doc_review_recall_pct']:.2f}%**",
        "",
        "## 5. Ringkasan Verdict 4 Lapis",
        "",
        "| Lapis Bukti | Metrik Kunci | Hasil Terukur | Status |",
        "|---|---|:---:|:---:|",
        f"| Lapis 1 (Holdout deskriptif) | Min-Fold Accuracy | {cv_res['min_fold_accuracy_pct']:.2f}% | **NOT INDEPENDENT CV** |",
        f"| Lapis 1 (Bootstrap) | MACRO 95% Confidence Interval | [{boot_res['macro_exact_95_ci'][0]:.2f}%, {boot_res['macro_exact_95_ci'][1]:.2f}%] | **RECORDED** |",
        f"| Lapis 2 (OOD Mutasi) | Delta Penurunan Mutasi | {ood_res['mutation_drop_pct']:.2f}pt | **{'PASS' if ood_res['mutation_gate_pass'] else 'FAIL'}** |",
        f"| Lapis 3 (Anti-Hardcode) | Pelanggaran Keyword Korpus | {len(ah_res['violations_found'])} keyword | **{'PASS' if ah_res['anti_hardcoding_pass'] else 'FAIL'}** |",
        f"| Lapis 4 (Safety Net) | Cell Review Recall | {sn_res['cell_review_recall_pct']:.2f}% | **{'PASS' if sn_res['gate_recall_pass'] else 'FAIL'}** |",
    ])

    with open(out_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n[DONE] 4-Layer Empirical Proof written to: {out_md_path}\n")


if __name__ == "__main__":
    main()
