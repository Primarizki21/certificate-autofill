"""Harness dan Benchmark Gated Search Grounding: Structural Regex Gate + Conditional Search Fallback.

Eksperimen: EXP-GATED-SEARCH-001
Tujuan:
1. Menguji efektivitas filter regex berbasis anchor semantik struktural untuk kata kunci tingkat eksplisit
   (mis. "tingkat nasional", "tingkatan nasional", "tingkat fakultas") sebagai bypass penelusuran web.
2. Mengevaluasi precision dan bypass rate regex gating pada korpus holdout target dan unified universe.
3. Menangani kasus ambigu melalui fallback Search Stage 2 dengan flag needs_review
   bila kueri web tidak terpicu (Q=0) atau terjadi konflik multi-level.
4. Membandingkan 3 arms evaluasi pada shared Stage 1:
   - control_arm: v3_text_control (tanpa search)
   - search_arm: v3_search_cot (tanpa gate, search selalu aktif)
   - gated_arm: v3_gated_search (regex gate -> bypass jika eksplisit; fallback jika ambigu)
5. Menghasilkan output kanonikal ExtractedValue(value, confidence, source) pada seluruh alur inferensi.
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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.master_data import FORM_OPTIONS
from app.services.field_extractor import ExtractedValue
from app.services.gemini_extractor import normalize_llm_json
from tests.benchmark_search_grounding import (
    ALL_6_FIELDS,
    FRAMEWORK_5_FIELDS,
    STAGE1_SYSTEM_INSTRUCTION,
    STAGE1_USER_PROMPT_TEMPLATE,
    STAGE2_SEARCH_COT_USER_PROMPT_TEMPLATE,
    clean_json_from_text,
    evaluate_predictions,
    load_and_normalize_gt,
    parse_cot_tingkat,
)
from tests.gemini_client import DEFAULT_EXCHANGE_RATE_IDR, GeminiClient, load_google_api_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark_gated_search")

# Pola regex anchor tingkat eksplisit murni struktural (Pillar 3: Anti-Hardcoding, tanpa entitas institusi kampus)
EXPLICIT_LEVEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(?:tingkat|tingkatan|skala|kategori)\s+internasional\b|\binternational\s+(?:level|scale|event|competition)\b",
            re.IGNORECASE,
        ),
        "Internasional",
    ),
    (
        re.compile(
            r"\b(?:tingkat|tingkatan|skala|kategori)\s+nasional\b|\bse[- ]indonesia\b|\bnational\s+(?:level|scale|event|competition)\b",
            re.IGNORECASE,
        ),
        "Nasional",
    ),
    (
        re.compile(
            r"\b(?:tingkat|tingkatan|skala)\s+universitas\b|\bse[- ]universitas\b",
            re.IGNORECASE,
        ),
        "Universitas",
    ),
    (
        re.compile(
            r"\b(?:tingkat|tingkatan|skala)\s+fakultas\b|\bse[- ]fakultas\b",
            re.IGNORECASE,
        ),
        "Fakultas",
    ),
    (
        re.compile(
            r"\b(?:tingkat|tingkatan|skala)\s+(?:departemen|program studi|prodi)\b",
            re.IGNORECASE,
        ),
        "Departemen/Program Studi",
    ),
]


def detect_explicit_level(raw_text: str) -> tuple[str | None, str | None, bool]:
    """Deteksi tingkat eksplisit dari teks OCR menggunakan structural anchor regex.

    Returns:
        tuple[level_name, matched_pattern, is_conflict]
    """
    if not raw_text or not raw_text.strip():
        return None, None, False

    # Guard negasi tegas (bukan, tidak, tidak termasuk, bukan pada)
    cleaned_text = re.sub(
        r"\b(?:bukan|tidak|tidak\s+termasuk|bukan\s+pada)\s+(?:tingkat|tingkatan|skala)\s+\w+\b",
        "",
        raw_text,
        flags=re.IGNORECASE,
    )

    # Deteksi konteks transisi ambigu ("menuju tingkat ...", "calon ...", "seleksi untuk ...")
    has_transitional = bool(
        re.search(
            r"\b(?:menuju|calon|persiapan|seleksi\s+untuk)\s+(?:tingkat|tingkatan|skala)\s+\w+\b",
            raw_text,
            re.IGNORECASE,
        )
    )

    detected_levels: list[tuple[str, str]] = []
    for pattern, level in EXPLICIT_LEVEL_PATTERNS:
        match = pattern.search(cleaned_text)
        if match:
            detected_levels.append((level, match.group(0)))

    if not detected_levels:
        return None, None, False

    # Jika ada frasa transisional atau terdeteksi >1 level berbeda -> Tandai konflik/ambigu
    unique_levels = {lvl for lvl, _ in detected_levels}
    if len(unique_levels) > 1 or has_transitional:
        first_lvl, first_pat = detected_levels[0]
        return first_lvl, first_pat, True

    # Tunggal dan bersih
    first_lvl, first_pat = detected_levels[0]
    return first_lvl, first_pat, False


def evaluate_gated_search_hybrid(
    raw_text: str,
    nama_kegiatan: str,
    penyelenggara: str,
    client: GeminiClient | None = None,
    enable_search_fallback: bool = True,
    model: str = "gemini-3.1-flash-lite",
) -> tuple[ExtractedValue, dict[str, Any]]:
    """Jalankan inferensi Gated Search Hybrid dengan ExtractedValue output kanonikal.

    Alur:
    1. Cek regex tingkat eksplisit (Stage 1 Gating).
    2. Jika terdeteksi tunggal: Bypass search -> return ExtractedValue(conf=0.92, source="regex_explicit_gate", bypass=True).
    3. Jika terdeteksi konflik/transisi: return ExtractedValue(conf=0.60, source="regex_explicit_gate_conflict", bypass=False, needs_review=True).
    4. Jika tidak terdeteksi: Masuk Stage 2 Search Fallback (hanya entitas terisolasi).
    """
    explicit_lvl, matched_pat, is_conflict = detect_explicit_level(raw_text)

    # Kasus 1: Terdeteksi konflik multi-level atau transisi -> TIDAK boleh bypass aman
    if is_conflict and explicit_lvl:
        extracted = ExtractedValue(
            value=explicit_lvl,
            confidence=0.60,
            source="regex_explicit_gate_conflict",
        )
        meta = {
            "matched_pattern": matched_pat,
            "gated_bypass": False,
            "is_conflict": True,
            "web_queries_count": 0,
            "web_queries": [],
            "search_fee_usd": 0.0,
            "search_fee_idr": 0.0,
            "needs_review": True,
        }
        return extracted, meta

    # Kasus 2: Terdeteksi tunggal tanpa konflik -> Bypass aman
    if explicit_lvl is not None:
        extracted = ExtractedValue(
            value=explicit_lvl,
            confidence=0.92,
            source="regex_explicit_gate",
        )
        meta = {
            "matched_pattern": matched_pat,
            "gated_bypass": True,
            "is_conflict": False,
            "web_queries_count": 0,
            "web_queries": [],
            "search_fee_usd": 0.0,
            "search_fee_idr": 0.0,
            "needs_review": False,
        }
        return extracted, meta

    # Kasus 3: Fallback ke Search Stage 2 (Jika tidak ada keyword eksplisit)
    if not enable_search_fallback or client is None:
        extracted = ExtractedValue(
            value=None,
            confidence=0.0,
            source="fallback_unresolved",
        )
        meta = {
            "matched_pattern": None,
            "gated_bypass": False,
            "is_conflict": False,
            "web_queries_count": 0,
            "web_queries": [],
            "search_fee_usd": 0.0,
            "search_fee_idr": 0.0,
            "needs_review": True,
        }
        return extracted, meta

    prompt = STAGE2_SEARCH_COT_USER_PROMPT_TEMPLATE.format(
        nama_kegiatan=nama_kegiatan or "-",
        penyelenggara=penyelenggara or "-",
    )
    res = client.generate_text(
        prompt=prompt,
        system_instruction=None,
        model=model,
        temperature=0.0,
        enable_grounding=True,
    )
    parsed = clean_json_from_text(res.response_text)
    tingkat_val, _ = parse_cot_tingkat(parsed)
    queries = res.web_search_queries
    q_cnt = len(queries)
    search_fee_usd = q_cnt * 0.014
    search_fee_idr = search_fee_usd * DEFAULT_EXCHANGE_RATE_IDR

    conf = 0.88 if q_cnt > 0 and tingkat_val else 0.65
    needs_rev = (q_cnt == 0 or tingkat_val is None)

    extracted = ExtractedValue(
        value=tingkat_val,
        confidence=conf,
        source="gemini_search_fallback" if q_cnt > 0 else "gemini_ungrounded_fallback",
    )
    meta = {
        "matched_pattern": None,
        "gated_bypass": False,
        "is_conflict": False,
        "web_queries_count": q_cnt,
        "web_queries": queries,
        "search_fee_usd": search_fee_usd,
        "search_fee_idr": round(search_fee_idr, 2),
        "needs_review": needs_rev,
    }
    return extracted, meta


def run_gated_search_audit(
    manifest_path: str = "certs_unified/manifest.json",
    gt_path: str = "Ground_Truth_Unified.csv",
    cache_dir: str = "docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts",
    target_indices: list[int] | None = None,
) -> dict[str, Any]:
    """Audit presisi dan bypass rate gating regex pada dataset holdout."""
    with open(Path(REPO_ROOT) / manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    gt_map = load_and_normalize_gt(Path(REPO_ROOT) / gt_path)
    indices = target_indices or list(range(88, 103))
    raw_dir = Path(REPO_ROOT) / cache_dir

    total_docs = len(indices)
    safe_bypass_count = 0
    correct_safe_bypass = 0
    conflict_count = 0
    fallback_count = 0

    records = []
    for idx in indices:
        doc = manifest[idx]
        fname = doc["nama_file"]
        gt_row = gt_map.get(fname, {})
        gt_tingkat = gt_row.get("tingkat", "-")

        stem = Path(fname).stem
        txt_path = raw_dir / f"{stem}.txt"
        raw_text = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""

        lvl, pat, is_conf = detect_explicit_level(raw_text)
        if lvl and not is_conf:
            safe_bypass_count += 1
            is_correct = (lvl.lower() == gt_tingkat.lower())
            if is_correct:
                correct_safe_bypass += 1
        elif is_conf:
            conflict_count += 1
            is_correct = False
        else:
            fallback_count += 1
            is_correct = False

        records.append({
            "idx": idx,
            "nama_file": fname,
            "gt_tingkat": gt_tingkat,
            "detected_level": lvl,
            "pattern": pat,
            "is_conflict": is_conf,
            "is_correct": is_correct,
        })

    precision = (correct_safe_bypass / safe_bypass_count * 100.0) if safe_bypass_count > 0 else 0.0
    bypass_rate = (safe_bypass_count / total_docs * 100.0) if total_docs > 0 else 0.0

    return {
        "total_docs": total_docs,
        "safe_bypass_count": safe_bypass_count,
        "correct_safe_bypass": correct_safe_bypass,
        "conflict_count": conflict_count,
        "fallback_count": fallback_count,
        "precision_pct": round(precision, 2),
        "bypass_rate_pct": round(bypass_rate, 2),
        "records": records,
    }


def main() -> None:
    """CLI runner untuk audit gating regex EXP-GATED-SEARCH-001."""
    parser = argparse.ArgumentParser(description="Audit Gated Search Explicit Regex")
    parser.add_argument(
        "--manifest-path",
        default="certs_unified/manifest.json",
        help="Path ke manifest.json",
    )
    parser.add_argument(
        "--gt-path",
        default="Ground_Truth_Unified.csv",
        help="Path ke Ground_Truth_Unified.csv",
    )
    parser.add_argument(
        "--dataset-slice",
        choices=["target_15", "elzandi_30", "v9_74", "unified_104"],
        default="target_15",
        help="Slice dataset yang diaudit",
    )
    args = parser.parse_args()

    slice_map = {
        "target_15": list(range(88, 103)),
        "elzandi_30": list(range(74, 104)),
        "v9_74": list(range(0, 74)),
        "unified_104": list(range(0, 104)),
    }
    indices = slice_map[args.dataset_slice]

    res = run_gated_search_audit(
        manifest_path=args.manifest_path,
        gt_path=args.gt_path,
        target_indices=indices,
    )
    print(f"\n=== Hasil Audit Gated Search: {args.dataset_slice} ===")
    print(f"Total Dokumen    : {res['total_docs']}")
    print(f"Safe Bypass      : {res['safe_bypass_count']} ({res['bypass_rate_pct']}%)")
    print(f"Correct Safe     : {res['correct_safe_bypass']}")
    print(f"Precision Safe   : {res['precision_pct']}%")
    print(f"Konflik / Ambigu : {res['conflict_count']}")
    print(f"Perlu Fallback   : {res['fallback_count']}")


if __name__ == "__main__":
    main()
