"""Harness dan Benchmark EXP-SEARCH-GROUNDING-002: Forced Web Search Grounding on Non-Regex Residual Documents.

Eksperimen: EXP-SEARCH-GROUNDING-002
Denominator: 94 dokumen residual non-regex dari Unified Universe (N=104) yang tidak memicu Safe Bypass regex.
Lengan Pembanding:
1. Baseline Historis: V2 Single-Pass Scope-Aware (acuan resmi proyek pada 94 dokumen yang sama).
2. Lengan Uji: V3 Forced Search Decoupled (Stage 1 literal + Stage 2 Scope-Aware CoT dengan bounded search retry).

Kebijakan Grounding & Transparansi:
- Retry Bounded: Jika Attempt 1 mengembalikan 0 kueri web, dieksekusi 1 kali Attempt 2 dengan prompt imperatif penelusuran.
- Strict Metadata Proof: Dokumen hanya diakui sebagai 'grounded' bila web_search_queries > 0.
- Dual-Cohort Reporting: Melaporkan cohort keseluruhan (N=94) dan pure grounded cohort (Q > 0) secara terpisah.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
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
from app.services.gemini_extractor import normalize_llm_json
from tests.benchmark_search_grounding import (
    ALL_6_FIELDS,
    FRAMEWORK_5_FIELDS,
    STAGE1_SYSTEM_INSTRUCTION,
    STAGE1_USER_PROMPT_TEMPLATE,
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
logger = logging.getLogger("benchmark_forced_search")

# Tarif resmi Google Search Grounding: $14 / 1.000 kueri = $0.014 / kueri
SEARCH_QUERY_FEE_USD = 0.014
DEFAULT_EXCHANGE_RATE = 17758.0
SEARCH_QUERY_FEE_IDR = round(SEARCH_QUERY_FEE_USD * DEFAULT_EXCHANGE_RATE, 2)  # Rp 248.61

STAGE2_FORCED_PROMPT_ATTEMPT1 = """Nama Kegiatan: '{nama_kegiatan}'
Penyelenggara: '{penyelenggara}'

Cari di internet menggunakan Google Search untuk mengetahui skala atau tingkat kegiatan di atas.
Berdasarkan hasil pencarian dan pedoman:
- Lomba/kompetisi terbuka mahasiswa -> 'Nasional'
- Konferensi/event global -> 'Internasional'
- Kegiatan internal kampus -> sesuai jenjang unit (Universitas, Fakultas, Departemen/Program Studi)

Tentukan tingkat resmi (pilih salah satu: Internasional, Nasional, Universitas, Fakultas, Departemen/Program Studi, Lainnya).
Format JSON:
```json
{{
  "tingkat": "...",
  "alasan": "..."
}}
```
"""

STAGE2_FORCED_PROMPT_ATTEMPT2 = """WAJIB GUNAKAN GOOGLE SEARCH:
Nama Kegiatan: '{nama_kegiatan}'
Penyelenggara: '{penyelenggara}'

Lakukan pencarian web di Google untuk menemukan cakupan peserta kegiatan di atas.
Cari tahu apakah kegiatan ini terbuka untuk peserta nasional (se-Indonesia) atau terbatas pada internal kampus.

Tentukan tingkat resmi (pilih salah satu: Internasional, Nasional, Universitas, Fakultas, Departemen/Program Studi, Lainnya).
Format JSON:
```json
{{
  "tingkat": "...",
  "alasan": "..."
}}
```
"""


@dataclass
class AttemptRecord:
    attempt_index: int
    prompt_tokens: int
    candidates_tokens: int
    cached_tokens: int
    thoughts_tokens: int
    total_tokens: int
    cost_usd: float
    cost_idr: float
    latency_s: float
    web_queries: list[str]
    raw_response: str
    parsed_json: dict[str, Any] | None


def determine_outcome_category(
    v3_pred: str | None,
    v2_pred: str | None,
    gt_val: str | None,
    web_queries_count: int,
) -> str:
    """Klasifikasi outcome komparasi semantik V3 vs V2 terhadap GT."""
    c_exact = (str(v2_pred).strip().lower() == str(gt_val).strip().lower()) if v2_pred and gt_val else False
    s_exact = (str(v3_pred).strip().lower() == str(gt_val).strip().lower()) if v3_pred and gt_val else False

    if web_queries_count > 0:
        if s_exact and c_exact:
            return "Keduanya Benar ✅"
        elif not s_exact and not c_exact:
            return "Keduanya Salah ❌"
        elif s_exact and not c_exact:
            return "Search Memperbaiki ✅ (Grounded)"
        elif not s_exact and c_exact:
            return "Search Memperburuk ❌ (Grounded)"
    else:
        if s_exact and c_exact:
            return "Keduanya Benar ✅ (Ungrounded)"
        elif not s_exact and not c_exact:
            return "Keduanya Salah ❌ (Ungrounded)"
        elif s_exact and not c_exact:
            return "V3 Benar Tanpa Search (Q=0)"
        elif not s_exact and c_exact:
            return "V3 Salah Tanpa Search (Q=0)"
    return "Lainnya"


def run_mock_forced_inference(
    nama_file: str,
    raw_text: str,
    gt_tingkat: str,
    v2_pred: str,
) -> dict[str, Any]:
    """Mock runner untuk pengujian dry-run plumbing dan verifikasi invariant."""
    h = hashlib.md5(f"{nama_file}:{raw_text[:40]}".encode()).hexdigest()
    val_int = int(h, 16)

    # Simulasikan Stage 1
    s1_tokens = 1150
    s1_cost_idr = 9.5

    # Simulasikan apakah Attempt 1 memicu web search (~35% mock chance)
    attempt1_queries = [f"kegiatan {nama_file[:15]}"] if (val_int % 3 == 0) else []

    attempts: list[AttemptRecord] = []
    if attempt1_queries:
        # Grounded pada Attempt 1
        tingkat_res = gt_tingkat if (val_int % 4 != 0) else "Internasional"
        att1 = AttemptRecord(
            attempt_index=1,
            prompt_tokens=420,
            candidates_tokens=65,
            cached_tokens=0,
            thoughts_tokens=0,
            total_tokens=485,
            cost_usd=0.0001,
            cost_idr=1.8,
            latency_s=1.5,
            web_queries=attempt1_queries,
            raw_response=json.dumps({"tingkat": tingkat_res, "alasan": "mock grounded 1"}),
            parsed_json={"tingkat": tingkat_res, "alasan": "mock grounded 1"},
        )
        attempts.append(att1)
        grounding_status = "grounded_first_attempt"
        final_tingkat = tingkat_res
    else:
        # Attempt 1 ungrounded -> jalankan Attempt 2
        att1 = AttemptRecord(
            attempt_index=1,
            prompt_tokens=420,
            candidates_tokens=60,
            cached_tokens=0,
            thoughts_tokens=0,
            total_tokens=480,
            cost_usd=0.0001,
            cost_idr=1.7,
            latency_s=1.2,
            web_queries=[],
            raw_response=json.dumps({"tingkat": v2_pred, "alasan": "mock ungrounded 1"}),
            parsed_json={"tingkat": v2_pred, "alasan": "mock ungrounded 1"},
        )
        attempts.append(att1)

        # Attempt 2 retry: ~50% peluang terpicu
        attempt2_queries = [f"info lomba {nama_file[:15]}"] if (val_int % 2 == 0) else []
        if attempt2_queries:
            tingkat_res = gt_tingkat if (val_int % 5 != 0) else "Lainnya"
            grounding_status = "grounded_on_retry"
            final_tingkat = tingkat_res
        else:
            tingkat_res = v2_pred
            grounding_status = "ungrounded_fallback"
            final_tingkat = tingkat_res

        att2 = AttemptRecord(
            attempt_index=2,
            prompt_tokens=450,
            candidates_tokens=70,
            cached_tokens=0,
            thoughts_tokens=0,
            total_tokens=520,
            cost_usd=0.00012,
            cost_idr=2.1,
            latency_s=1.8 if attempt2_queries else 1.1,
            web_queries=attempt2_queries,
            raw_response=json.dumps({"tingkat": final_tingkat, "alasan": "mock retry"}),
            parsed_json={"tingkat": final_tingkat, "alasan": "mock retry"},
        )
        attempts.append(att2)

    all_queries: list[str] = []
    for att in attempts:
        all_queries.extend(att.web_queries)

    total_query_count = len(all_queries)
    search_fee_idr = round(total_query_count * SEARCH_QUERY_FEE_IDR, 2)
    s2_tok_cost = sum(a.cost_idr for a in attempts)
    total_effective_cost = round(s1_cost_idr + s2_tok_cost + search_fee_idr, 2)

    outcome_cat = determine_outcome_category(final_tingkat, v2_pred, gt_tingkat, total_query_count)

    fields = {
        "nama_kegiatan_sertifikasi": f"Kegiatan Mock {nama_file[:10]}",
        "nomor_bukti_fisik_nomor_sertifikasi": f"123/MOCK/{val_int % 1000:03d}",
        "penyelenggara_kegiatan": "BEM Fakultas Mock",
        "waktu_mulai_pelaksanaan": "15/08/2024",
        "waktu_selesai_pelaksanaan": "15/08/2024",
        "tingkat": final_tingkat,
    }

    return {
        "fields": fields,
        "grounding_status": grounding_status,
        "outcome_category": outcome_cat,
        "attempts_count": len(attempts),
        "total_web_queries": total_query_count,
        "web_queries": all_queries,
        "search_fee_idr": search_fee_idr,
        "stage1_tokens": s1_tokens,
        "stage1_cost_idr": s1_cost_idr,
        "stage2_tokens": sum(a.total_tokens for a in attempts),
        "stage2_cost_idr": round(s2_tok_cost, 2),
        "total_tokens": s1_tokens + sum(a.total_tokens for a in attempts),
        "total_effective_cost_idr": total_effective_cost,
        "calls_details": [
            {
                "stage": "stage1_literal",
                "attempt": 1,
                "prompt_tokens": 1150,
                "candidates_tokens": 70,
                "cached_tokens": 0,
                "thoughts_tokens": 0,
                "total_tokens": 1220,
                "cost_usd": 0.0003,
                "cost_idr": s1_cost_idr,
                "latency_s": 0.8,
                "queries": [],
            }
        ] + [
            {
                "stage": "stage2_forced_search",
                "attempt": a.attempt_index,
                "prompt_tokens": a.prompt_tokens,
                "candidates_tokens": a.candidates_tokens,
                "cached_tokens": a.cached_tokens,
                "thoughts_tokens": a.thoughts_tokens,
                "total_tokens": a.total_tokens,
                "cost_usd": a.cost_usd,
                "cost_idr": a.cost_idr,
                "latency_s": a.latency_s,
                "queries": a.web_queries,
            }
            for a in attempts
        ],
    }


def run_gemini_forced_inference(
    nama_file: str,
    raw_text: str,
    client: GeminiClient,
    model: str,
    gt_tingkat: str,
    v2_pred: str,
) -> dict[str, Any]:
    """Eksekusi inferensi live ke Gemini API dengan Stage 1 + Stage 2 Forced Search Bounded Retry."""
    t0 = time.perf_counter()

    # Stage 1: Ekstraksi Literal Tanpa Search
    prompt1 = STAGE1_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
    res1 = client.generate_text(
        prompt=prompt1,
        system_instruction=STAGE1_SYSTEM_INSTRUCTION,
        model=model,
        temperature=0.0,
        enable_grounding=False,
    )
    parsed1 = clean_json_from_text(res1.response_text) or {}
    norm_fields = normalize_llm_json(parsed1)

    act_val = norm_fields.get("nama_kegiatan_sertifikasi") or "-"
    org_val = norm_fields.get("penyelenggara_kegiatan") or "-"

    attempts: list[AttemptRecord] = []

    # Stage 2: Attempt 1
    prompt2_att1 = STAGE2_FORCED_PROMPT_ATTEMPT1.format(nama_kegiatan=act_val, penyelenggara=org_val)
    t_att1 = time.perf_counter()
    res2_att1 = client.generate_text(
        prompt=prompt2_att1,
        system_instruction=None,
        model=model,
        temperature=0.0,
        enable_grounding=True,
    )
    lat_att1 = time.perf_counter() - t_att1
    parsed_att1 = clean_json_from_text(res2_att1.response_text)

    att1_record = AttemptRecord(
        attempt_index=1,
        prompt_tokens=res2_att1.prompt_tokens,
        candidates_tokens=res2_att1.candidates_tokens,
        cached_tokens=res2_att1.cached_tokens,
        thoughts_tokens=res2_att1.thoughts_tokens,
        total_tokens=res2_att1.total_tokens,
        cost_usd=res2_att1.cost_usd,
        cost_idr=res2_att1.cost_idr,
        latency_s=lat_att1,
        web_queries=res2_att1.web_search_queries or [],
        raw_response=res2_att1.response_text,
        parsed_json=parsed_att1,
    )
    attempts.append(att1_record)

    final_parsed = parsed_att1
    if att1_record.web_queries:
        grounding_status = "grounded_first_attempt"
    else:
        # Attempt 1 ungrounded -> jalankan Bounded Retry (Attempt 2)
        prompt2_att2 = STAGE2_FORCED_PROMPT_ATTEMPT2.format(nama_kegiatan=act_val, penyelenggara=org_val)
        t_att2 = time.perf_counter()
        res2_att2 = client.generate_text(
            prompt=prompt2_att2,
            system_instruction=None,
            model=model,
            temperature=0.0,
            enable_grounding=True,
        )
        lat_att2 = time.perf_counter() - t_att2
        parsed_att2 = clean_json_from_text(res2_att2.response_text)

        att2_record = AttemptRecord(
            attempt_index=2,
            prompt_tokens=res2_att2.prompt_tokens,
            candidates_tokens=res2_att2.candidates_tokens,
            cached_tokens=res2_att2.cached_tokens,
            thoughts_tokens=res2_att2.thoughts_tokens,
            total_tokens=res2_att2.total_tokens,
            cost_usd=res2_att2.cost_usd,
            cost_idr=res2_att2.cost_idr,
            latency_s=lat_att2,
            web_queries=res2_att2.web_search_queries or [],
            raw_response=res2_att2.response_text,
            parsed_json=parsed_att2,
        )
        attempts.append(att2_record)

        if att2_record.web_queries:
            grounding_status = "grounded_on_retry"
            final_parsed = parsed_att2
        else:
            grounding_status = "ungrounded_fallback"
            final_parsed = parsed_att2 if parsed_att2 else parsed_att1

    tingkat_val, _ = parse_cot_tingkat(final_parsed)
    norm_fields["tingkat"] = tingkat_val

    all_queries: list[str] = []
    for att in attempts:
        all_queries.extend(att.web_queries)

    total_query_count = len(all_queries)
    search_fee_idr = round(total_query_count * SEARCH_QUERY_FEE_IDR, 2)
    s1_tok_cost = res1.cost_idr
    s2_tok_cost = sum(a.cost_idr for a in attempts)
    total_effective_cost = round(s1_tok_cost + s2_tok_cost + search_fee_idr, 2)

    outcome_cat = determine_outcome_category(tingkat_val, v2_pred, gt_tingkat, total_query_count)

    return {
        "fields": norm_fields,
        "grounding_status": grounding_status,
        "outcome_category": outcome_cat,
        "attempts_count": len(attempts),
        "total_web_queries": total_query_count,
        "web_queries": all_queries,
        "search_fee_idr": search_fee_idr,
        "stage1_tokens": res1.total_tokens,
        "stage1_cost_idr": round(s1_tok_cost, 2),
        "stage2_tokens": sum(a.total_tokens for a in attempts),
        "stage2_cost_idr": round(s2_tok_cost, 2),
        "total_tokens": res1.total_tokens + sum(a.total_tokens for a in attempts),
        "total_effective_cost_idr": total_effective_cost,
        "latency_s": time.perf_counter() - t0,
        "calls_details": [
            {
                "stage": "stage1_literal",
                "attempt": 1,
                "prompt_tokens": res1.prompt_tokens,
                "candidates_tokens": res1.candidates_tokens,
                "cached_tokens": res1.cached_tokens,
                "thoughts_tokens": res1.thoughts_tokens,
                "total_tokens": res1.total_tokens,
                "cost_usd": res1.cost_usd,
                "cost_idr": round(s1_tok_cost, 2),
                "latency_s": round(time.perf_counter() - t0, 3),
                "queries": res1.web_search_queries or [],
            }
        ] + [
            {
                "stage": "stage2_forced_search",
                "attempt": a.attempt_index,
                "prompt_tokens": a.prompt_tokens,
                "candidates_tokens": a.candidates_tokens,
                "cached_tokens": a.cached_tokens,
                "thoughts_tokens": a.thoughts_tokens,
                "total_tokens": a.total_tokens,
                "cost_usd": a.cost_usd,
                "cost_idr": a.cost_idr,
                "latency_s": a.latency_s,
                "queries": a.web_queries,
            }
            for a in attempts
        ],
    }

def write_prompt_registry(out_path: Path, model: str) -> None:
    """Tulis arsip template prompt resmi EXP-SEARCH-GROUNDING-002 dengan pembungkus 4-backtick."""
    content = f"""# PROMPT REGISTRY: EXP-SEARCH-GROUNDING-002
Model Target: `{model}` | Tanggal: {datetime.now().strftime("%Y-%m-%d")}

---

## 1. Stage 1: Literal Extraction (5 Field Faktual)

### System Instruction
````text
{STAGE1_SYSTEM_INSTRUCTION}
````

### User Prompt Template
````text
{STAGE1_USER_PROMPT_TEMPLATE}
````

---

## 2. Stage 2: Forced Search Grounding (Isolated Entity CoT)

### Attempt 1 Prompt (Initial Grounded Attempt)
````text
{STAGE2_FORCED_PROMPT_ATTEMPT1}
````

### Attempt 2 Prompt (Bounded Retry - Explicit Search Directive)
````text
{STAGE2_FORCED_PROMPT_ATTEMPT2}
````
"""
    out_path.write_text(content, encoding="utf-8")


def run_benchmark(
    manifest_path: str = "docs/experiments/EXP-SEARCH-GROUNDING-002/manifest_94_fallback.csv",
    output_dir: str = "docs/experiments/EXP-SEARCH-GROUNDING-002",
    raw_texts_dir: str = "docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts",
    gt_csv_path: str = "Ground_Truth_Unified.csv",
    model: str = "gemini-3.1-flash-lite",
    backend: str = "gemini",
    max_cumulative_queries: int = 188,
    max_cumulative_cost_idr: float = 65000.0,
    pacing_delay: float = 1.2,
    timeout_s: float = 30.0,
    limit: int | None = None,
    offset: int = 0,
    mock: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Eksekusi evaluasi forced search grounding berpasangan pada manifest 94 residual."""
    # Jika mode mock dan output_dir masih default EXP-002, alihkan ke dry_run folder
    if mock and output_dir == "docs/experiments/EXP-SEARCH-GROUNDING-002":
        output_dir = "docs/experiments/EXP-SEARCH-GROUNDING-002/dry_run"

    out_dir_path = Path(REPO_ROOT) / output_dir

    # B14 Immutability Guard: Tolak menimpa deliverable final jika sudah ada
    deliverables = [out_dir_path / "comparative_metrics.json", out_dir_path / "evaluation_details.csv"]
    existing_delivs = [f.name for f in deliverables if f.exists()]
    if existing_delivs and not force:
        raise FileExistsError(
            f"B14 Immutability Guard: Deliverable final {existing_delivs} sudah ada di {out_dir_path}. "
            "Gunakan folder output baru atau tentukan --force untuk menimpa secara eksplisit."
        )

    out_dir_path.mkdir(parents=True, exist_ok=True)

    # 1. Muat Ground Truth Resmi (Unified 104)
    gt_map = load_and_normalize_gt(Path(REPO_ROOT) / gt_csv_path)

    # 2. Muat Manifest 94 Fallback
    man_path = Path(REPO_ROOT) / manifest_path
    if not man_path.exists():
        raise FileNotFoundError(f"Manifest tidak ditemukan: {man_path}")

    with open(man_path, encoding="utf-8") as f:
        manifest_rows = list(csv.DictReader(f))

    assert len(manifest_rows) == 94, f"Manifest harus memuat tepat 94 dokumen, ditemukan {len(manifest_rows)}"

    target_slice = manifest_rows[offset : (offset + limit) if limit else None]
    logger.info(f"Target manifest slice: {len(target_slice)} dokumen (offset={offset}, limit={limit})")

    # 3. Inisialisasi Klien API (jika non-mock)
    client: GeminiClient | None = None
    if not mock:
        client = GeminiClient(default_model=model, request_delay=pacing_delay, timeout_s=timeout_s)

    checkpoint_file = out_dir_path / "checkpoint_forced_search.jsonl"
    existing_records: dict[str, dict[str, Any]] = {}
    if checkpoint_file.exists():
        with open(checkpoint_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    existing_records[rec["nama_file"]] = rec
        logger.info(f"Ditemukan {len(existing_records)} record dari checkpoint sebelumnya.")
    # 4. Evaluasi Dokumen
    raw_dir = Path(REPO_ROOT) / raw_texts_dir
    cp_writer = open(checkpoint_file, "a", encoding="utf-8")

    all_records: list[dict[str, Any]] = []
    cumulative_queries = sum(r.get("total_web_queries", 0) for r in existing_records.values())
    cumulative_cost = sum(r.get("total_effective_cost_idr", 0.0) for r in existing_records.values())

    try:
        for idx, row in enumerate(target_slice, 1):
            fn = row["nama_file"]
            gt_tkt = row["gt_tingkat"]
            v2_pred = row["v2_historical_pred"]

            if fn in existing_records:
                all_records.append(existing_records[fn])
                continue

            # Cek Safety Stop-Gate
            if cumulative_queries >= max_cumulative_queries:
                logger.warning(f"Stop-gate tercapai! Kueri kumulatif ({cumulative_queries}) >= {max_cumulative_queries}.")
                break
            if cumulative_cost >= max_cumulative_cost_idr:
                logger.warning(f"Stop-gate tercapai! Biaya kumulatif (Rp {cumulative_cost:,.2f}) >= Rp {max_cumulative_cost_idr:,.2f}.")
                break

            stem = Path(fn).stem
            txt_path = raw_dir / f"{stem}.txt"
            if not txt_path.exists():
                logger.warning(f"Raw text tidak ditemukan untuk {fn}, lewati.")
                continue
            raw_text = txt_path.read_text(encoding="utf-8")

            if mock:
                res_meta = run_mock_forced_inference(fn, raw_text, gt_tkt, v2_pred)
            else:
                assert client is not None
                res_meta = run_gemini_forced_inference(fn, raw_text, client, model, gt_tkt, v2_pred)

            doc_gt = gt_map.get(fn, gt_map.get(stem, {}))
            # Evaluasi per-field
            eval_dict = evaluate_predictions(res_meta["fields"], doc_gt)
            record = {
                "no": row["no"],
                "dataset": row["dataset"],
                "nama_file": fn,
                "gt_tingkat": gt_tkt,
                "v2_historical_pred": v2_pred,
                "v2_historical_exact": int(row["v2_historical_exact"]),
                "v3_pred": res_meta["fields"].get("tingkat"),
                "v3_exact": int(eval_dict.get("tingkat", {}).get("exact", False)),
                "grounding_status": res_meta["grounding_status"],
                "outcome_category": res_meta["outcome_category"],
                "attempts_count": res_meta["attempts_count"],
                "total_web_queries": res_meta["total_web_queries"],
                "web_queries": res_meta["web_queries"],
                "search_fee_idr": res_meta["search_fee_idr"],
                "stage1_tokens": res_meta.get("stage1_tokens", 0),
                "stage1_cost_idr": res_meta.get("stage1_cost_idr", 0.0),
                "stage2_tokens": res_meta.get("stage2_tokens", 0),
                "stage2_cost_idr": res_meta.get("stage2_cost_idr", 0.0),
                "total_tokens": res_meta["total_tokens"],
                "total_effective_cost_idr": res_meta["total_effective_cost_idr"],
                "fields": res_meta["fields"],
                "eval": eval_dict,
                "calls_details": res_meta["calls_details"],
            }

            cp_writer.write(json.dumps(record, ensure_ascii=False) + "\n")
            cp_writer.flush()
            all_records.append(record)

            cumulative_queries += record["total_web_queries"]
            cumulative_cost += record["total_effective_cost_idr"]
            logger.info(
                f"[{idx}/{len(target_slice)}] {fn[:30]}: V2={v2_pred} -> V3={record['v3_pred']} (GT={gt_tkt}) "
                f"| Q={record['total_web_queries']} | Cat={record['outcome_category']} | TotalCost=Rp {cumulative_cost:,.2f}"
            )

    finally:
        cp_writer.close()

    # 5. Tulis PROMPT_REGISTRY.md
    write_prompt_registry(out_dir_path / "PROMPT_REGISTRY.md", model)

    # 6. Agregasi Metrik
    n_docs = len(all_records)
    v2_correct = sum(r["v2_historical_exact"] for r in all_records)
    v3_correct = sum(r["v3_exact"] for r in all_records)

    grounded_cohort = [r for r in all_records if r["total_web_queries"] > 0]
    ungrounded_cohort = [r for r in all_records if r["total_web_queries"] == 0]

    v2_tkt_acc = (v2_correct / n_docs * 100.0) if n_docs else 0.0
    v3_tkt_acc = (v3_correct / n_docs * 100.0) if n_docs else 0.0

    cat_counts: dict[str, int] = {}
    for r in all_records:
        cat_counts[r["outcome_category"]] = cat_counts.get(r["outcome_category"], 0) + 1

    summary_metrics = {
        "metadata": {
            "experiment_id": "EXP-SEARCH-GROUNDING-002",
            "model": model,
            "backend": backend,
            "mock": mock,
            "timestamp": datetime.now().isoformat(),
            "total_documents_evaluated": n_docs,
            "target_denominator": 94,
        },
        "accuracy": {
            "v2_historical_tingkat_exact": v2_tkt_acc,
            "v2_historical_correct": v2_correct,
            "v3_forced_search_tingkat_exact": v3_tkt_acc,
            "v3_forced_search_correct": v3_correct,
            "net_gain_percentage": round(v3_tkt_acc - v2_tkt_acc, 2),
        },
        "outcome_breakdown": cat_counts,
        "grounding_cohorts": {
            "grounded_count": len(grounded_cohort),
            "grounded_rate": round(len(grounded_cohort) / n_docs * 100.0, 2) if n_docs else 0.0,
            "grounded_v3_accuracy": round(sum(r["v3_exact"] for r in grounded_cohort) / len(grounded_cohort) * 100.0, 2) if grounded_cohort else 0.0,
            "grounded_v2_accuracy": round(sum(r["v2_historical_exact"] for r in grounded_cohort) / len(grounded_cohort) * 100.0, 2) if grounded_cohort else 0.0,
            "ungrounded_count": len(ungrounded_cohort),
            "ungrounded_rate": round(len(ungrounded_cohort) / n_docs * 100.0, 2) if n_docs else 0.0,
            "ungrounded_v3_accuracy": round(sum(r["v3_exact"] for r in ungrounded_cohort) / len(ungrounded_cohort) * 100.0, 2) if ungrounded_cohort else 0.0,
        },
        "costs": {
            "total_queries": sum(r["total_web_queries"] for r in all_records),
            "total_search_fee_idr": round(sum(r["search_fee_idr"] for r in all_records), 2),
            "total_tokens": sum(r["total_tokens"] for r in all_records),
            "total_effective_cost_idr": round(sum(r["total_effective_cost_idr"] for r in all_records), 2),
            "avg_cost_per_doc_idr": round(sum(r["total_effective_cost_idr"] for r in all_records) / n_docs, 2) if n_docs else 0.0,
        },
    }

    # Simpan comparative_metrics.json
    metrics_path = out_dir_path / "comparative_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(summary_metrics, f, indent=2, ensure_ascii=False)

    # 7. Simpan evaluation_details.csv
    csv_path = out_dir_path / "evaluation_details.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "no",
            "dataset",
            "nama_file",
            "gt_tingkat",
            "v2_pred",
            "v2_exact",
            "v3_pred",
            "v3_exact",
            "grounding_status",
            "outcome_category",
            "attempts_count",
            "total_web_queries",
            "search_fee_idr",
            "stage1_tokens",
            "stage1_cost_idr",
            "stage2_tokens",
            "stage2_cost_idr",
            "total_tokens",
            "total_effective_cost_idr",
            "calls_details_json",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_records:
            writer.writerow({
                "no": r["no"],
                "dataset": r["dataset"],
                "nama_file": r["nama_file"],
                "gt_tingkat": r["gt_tingkat"],
                "v2_pred": r["v2_historical_pred"],
                "v2_exact": r["v2_historical_exact"],
                "v3_pred": r["v3_pred"],
                "v3_exact": r["v3_exact"],
                "grounding_status": r["grounding_status"],
                "outcome_category": r["outcome_category"],
                "attempts_count": r["attempts_count"],
                "total_web_queries": r["total_web_queries"],
                "search_fee_idr": r["search_fee_idr"],
                "stage1_tokens": r.get("stage1_tokens", 0),
                "stage1_cost_idr": r.get("stage1_cost_idr", 0.0),
                "stage2_tokens": r.get("stage2_tokens", 0),
                "stage2_cost_idr": r.get("stage2_cost_idr", 0.0),
                "total_tokens": r["total_tokens"],
                "total_effective_cost_idr": r["total_effective_cost_idr"],
                "calls_details_json": json.dumps(r.get("calls_details", []), ensure_ascii=False),
            })

    logger.info(f"Benchmark selesai. Ringkasan metrik tersimpan di {metrics_path}")
    return summary_metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runner Benchmark EXP-SEARCH-GROUNDING-002")
    parser.add_argument("--manifest-path", default="docs/experiments/EXP-SEARCH-GROUNDING-002/manifest_94_fallback.csv")
    parser.add_argument("--output-dir", default="docs/experiments/EXP-SEARCH-GROUNDING-002")
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--live", action="store_true", help="Wajib disertakan untuk eksekusi API live nyata. Jika tidak disertakan, default mode adalah mock dry-run.")
    parser.add_argument("--force", action="store_true", help="Paksa menimpa output directory yang sudah ada.")
    parser.add_argument("--pacing-delay", type=float, default=1.2, help="Jeda pacing antar request (detik).")
    parser.add_argument("--timeout-s", type=float, default=30.0, help="Timeout HTTP per request (detik).")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    # Fail-safe default: mock aktif jika flag --live TIDAK diberikan
    is_mock = not args.live

    run_benchmark(
        manifest_path=args.manifest_path,
        output_dir=args.output_dir,
        model=args.model,
        mock=is_mock,
        force=args.force,
        pacing_delay=args.pacing_delay,
        timeout_s=args.timeout_s,
        limit=args.limit,
        offset=args.offset,
    )
