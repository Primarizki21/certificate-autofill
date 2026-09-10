"""Comprehensive All-6-Fields & Prompting Architecture Benchmark Runner.

Evaluates 3 LLM Prompting Architectures across all 6 KHP fields on 104 certificates
(certs_unified: 74 Train v9 + 30 Test Elzandi):
1. Varian 1 (Single-Pass Baseline Produksi): Current production prompt (BEM Fakultas -> "Fakultas").
2. Varian 2 (Single-Pass Scope-Aware): Unified single prompt with Scope > Organizer hierarchy rule.
3. Varian 3 (Decoupled 2-Stage Pipeline):
   - Stage 1: 5 Factual Literal Fields (kegiatan, nomor, penyelenggara, tgl_mulai, tgl_selesai).
   - Stage 2: Tingkat Resolution (Router Deterministik 18 rules -> Specialized Tingkat LLM Fallback).

Outputs complete deliverables in docs/experiments/EXP-ALL6F-PROMPT-001/:
- comparative_summary.md
- comparative_metrics.json
- results.xlsx
- evaluation_details.csv
- PROMPT_REGISTRY.md (generated/linked)
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
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root and backend to sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.master_data import FORM_OPTIONS
from app.services.field_extractor import ExtractedValue
from app.services.gemini_extractor import normalize_llm_json, standardize_date
from app.services.ocr_fallback import extract_text_with_ocr
from app.services.pdf_fast_path import extract_text_with_pymupdf
from app.services.tingkat_router import route_tingkat, route_tingkat_trace
from tests.gemini_client import (
    DEFAULT_EXCHANGE_RATE_IDR,
    GeminiClient,
    get_exchange_rate,
    load_google_api_key,
)
from tests.matchers import match_field
from tests.ocr_engine import ocr_rapid, ocr_tess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark_all6f_prompting")

# 6 Fields evaluated under KHP standards
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

# Valid Tingkat canonical set
VALID_TINGKAT_OPTIONS = set(
    FORM_OPTIONS.get(
        "tingkat",
        [
            "Internasional",
            "Nasional",
            "Universitas",
            "Fakultas",
            "Departemen/Program Studi",
            "Lainnya",
        ],
    )
)

# ==============================================================================
# PROMPT DEFINITIONS FOR THE 3 VARIANTS
# ==============================================================================

# --- VARIAN 1: Single-Pass Baseline Produksi (Eksisting) ---
V1_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama.
   - Jika tidak ada tanggal, isi null.
3. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Jika tidak ada nomor, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
5. Tingkat (tingkat):
   - Wajib salah satu nilai enum berikut persis:
     ["Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"]
   - Pedoman:
     * Acara/organisasi tingkat BEM Fakultas (FEB/FKM/FTMM/FST/dsb) -> "Fakultas".
     * HIMA / Himpunan Mahasiswa Departemen / Program Studi -> "Departemen/Program Studi".
     * UKM / Ormawa universitas / BSO -> "Lainnya".
     * Rektorat / BEM Universitas / Direktorat Kemahasiswaan Universitas -> "Universitas".
     * Lomba / kompetisi / seminar tingkat nasional -> "Nasional".
     * Konferensi / seminar / event internasional -> "Internasional".
     * Jika tidak diketahui atau di luar kategori di atas -> "Lainnya".
6. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
"""

V1_USER_PROMPT_TEMPLATE = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 7 field berikut dalam format JSON:
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya" atau null,
  "raw_role": string atau null
}}
"""

# --- VARIAN 2: Single-Pass Scope-Aware (Revisi Prompt Tunggal) ---
V2_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama.
   - Jika tidak ada tanggal, isi null.
3. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Jika tidak ada nomor, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
5. Tingkat (tingkat):
   - Wajib salah satu nilai enum berikut persis:
     ["Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"]
   - Prinsip Utama: Cakupan Sasaran Peserta (Skala Nasional/Internasional) LEBIH UTAMA daripada Jenjang Penyelenggara.
   - Pedoman:
     * Lomba, kompetisi, hackathon, seminar, call for papers, atau event terbuka untuk mahasiswa umum lintas perguruan tinggi/nasional -> "Nasional" (MESKIPUN diselenggarakan oleh BEM Fakultas atau Himpunan Mahasiswa Departemen).
     * Konferensi, symposium, atau event berskala global/lintas negara -> "Internasional".
     * Kegiatan internal kemahasiswaan/organisasi kampus non-lomba terbuka, tentukan berdasarkan hierarki unit:
       - Rektorat / BEM Universitas / Direktorat Kemahasiswaan Universitas -> "Universitas".
       - Kepengurusan, raker, atau kepanitiaan BEM Fakultas / ormawa fakultas -> "Fakultas".
       - Kepengurusan, raker, atau kepanitiaan Himpunan Mahasiswa / Program Studi -> "Departemen/Program Studi".
       - UKM / Unit Kegiatan Mahasiswa / BSO -> "Lainnya".
     * Jika tidak diketahui atau bukti tidak cukup untuk memastikan cakupan -> "Lainnya".
6. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
"""

V2_USER_PROMPT_TEMPLATE = V1_USER_PROMPT_TEMPLATE

# --- VARIAN 4: Single-Pass In-JSON Scope Signal (Structured Rationale) ---
V4_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama.
   - Jika tidak ada tanggal, isi null.
3. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Jika tidak ada nomor, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
5. Pola Cakupan & Tingkat:
   - Sebelum menentukan tingkat, tentukan "pola_cakupan" dari pilihan terkontrol berikut:
     * "TERBUKA_SE_INDONESIA": jika terdapat bukti lomba/kompetisi/seminar terbuka untuk umum/mahasiswa se-Indonesia.
     * "INTERNASIONAL": jika konferensi/kompetisi berskala global lintas negara.
     * "INTERNAL_KAMPUS": jika kegiatan kepengurusan, raker, atau orientasi internal unit kampus.
     * "TIDAK_DITEMUKAN": jika tidak ada bukti eksplisit cakupan peserta.
   - Tentukan "tingkat" berdasarkan pola cakupan dan unit penyelenggara:
     * Jika pola_cakupan = "TERBUKA_SE_INDONESIA" -> "Nasional" (MESKIPUN penyelenggara BEM Fakultas / HIMA).
     * Jika pola_cakupan = "INTERNASIONAL" -> "Internasional".
     * Jika pola_cakupan = "INTERNAL_KAMPUS", ikuti hierarki unit:
       - Rektorat / BEM Universitas / Direktorat Kemahasiswaan -> "Universitas".
       - BEM Fakultas / Ormawa Fakultas -> "Fakultas".
       - Himpunan Mahasiswa / Program Studi -> "Departemen/Program Studi".
       - UKM / BSO -> "Lainnya".
     * Jika pola_cakupan = "TIDAK_DITEMUKAN" atau bukti tidak cukup -> "Lainnya".
6. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
"""

V4_USER_PROMPT_TEMPLATE = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 8 field berikut dalam format JSON:
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "raw_role": string atau null,
  "pola_cakupan": "TERBUKA_SE_INDONESIA"|"INTERNASIONAL"|"INTERNAL_KAMPUS"|"TIDAK_DITEMUKAN",
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya" atau null
}}
"""


# --- VARIAN 3: Decoupled 2-Stage Pipeline ---
# Stage 1: Ekstraksi 5 Field Literal Murni (Steril dari Tingkat)
V3_STAGE1_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual literal dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama.
   - Jika tidak ada tanggal, isi null.
3. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Jika tidak ada nomor, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
5. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
"""

V3_STAGE1_USER_PROMPT_TEMPLATE = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 6 field berikut dalam format JSON:
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "raw_role": string atau null
}}
"""

# Stage 2B: Specialized Tingkat Prompt (Fallback untuk Residual Unrouted)
V3_STAGE2B_SYSTEM_INSTRUCTION = """Anda adalah asisten analis tingkat kegiatan sertifikat akademik untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: menentukan tingkat kegiatan secara objektif berdasarkan teks sertifikat dan metadata yang diketahui."""

V3_STAGE2B_USER_PROMPT_TEMPLATE = """Tentukan TINGKAT KEGIATAN dari sertifikat mahasiswa berikut.

PILIHAN TINGKAT RESMI:
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

PRINSIP PENILAIAN:
1. Cakupan Sasaran Peserta (Scope) LEBIH UTAMA daripada Jenjang Penyelenggara.
2. Lomba, kompetisi, hackathon, seminar, call for papers, atau event terbuka untuk mahasiswa umum lintas kampus/nasional -> "Nasional" (MESKIPUN diselenggarakan oleh BEM Fakultas atau Himpunan Mahasiswa).
3. Konferensi/event internasional lintas negara -> "Internasional".
4. Kegiatan internal organisasi non-lomba terbuka ikuti jenjang unit penyelenggara:
   - Rektorat / BEM Universitas -> "Universitas"
   - BEM Fakultas -> "Fakultas"
   - Himpunan Mahasiswa -> "Departemen/Program Studi"
   - UKM / BSO -> "Lainnya"
5. Jika informasi tidak cukup -> "Lainnya".

DATA SERTIFIKAT:
- Nama Kegiatan: {nama_kegiatan}
- Penyelenggara: {penyelenggara}

TEKS SERTIFIKAT:
--- AWAL TEKS ---
{raw_ocr_text}
--- AKHIR TEKS ---

Jawab dalam format JSON:
{{
  "penalaran": "Analisis singkat (1-2 kalimat)",
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya"
}}
"""


# ==============================================================================
# TEXT EXTRACTION & CACHING HELPER
# ==============================================================================

def get_or_extract_raw_text(
    doc_info: dict[str, Any],
    cache_dir: Path,
) -> tuple[str, str]:
    """Mengambil teks mentah dari cache atau mengekstrak langsung dari file sumber.

    Returns:
        (raw_text, extraction_method)
    """
    stem = Path(doc_info["nama_file"]).stem
    cache_file = cache_dir / f"{stem}.txt"

    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8"), "cached"

    file_path = Path(doc_info["unified_path"])
    if not file_path.exists():
        # Fallback to source_path if unified_path not found
        file_path = Path(doc_info.get("source_path", ""))

    if not file_path.exists():
        return "", "missing_file"

    file_bytes = file_path.read_bytes()
    ext = file_path.suffix.lower()

    raw_text = ""
    method = ""

    if ext == ".pdf":
        fast = extract_text_with_pymupdf(file_bytes)
        txt = fast.text.strip()
        if len(txt) >= 60:
            raw_text = txt
            method = "pymupdf_fast_path"
        else:
            # Fallback OCR (Rapid + Tess)
            raw_text = extract_text_with_ocr(file_bytes).strip()
            method = "rapid_tesseract_ocr"
    elif ext in (".png", ".jpeg", ".jpg"):
        rapid_txt = ocr_rapid(file_bytes)
        tess_txt = ocr_tess(file_bytes)
        combined = f"{rapid_txt}\n{tess_txt}".strip()
        raw_text = combined
        method = "image_rapid_tess_ocr"
    else:
        raw_text = ""
        method = "unsupported_format"

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(raw_text, encoding="utf-8")
    return raw_text, method


# ==============================================================================
# INFERENCE ENGINES (GEMINI & MOCK)
# ==============================================================================

def run_mock_inference(
    variant: str,
    raw_text: str,
    gt_row: dict[str, str],
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Mock inference deterministik untuk dry-run validasi pipeline & testing."""
    kegiatan = gt_row.get("Nama Kegiatan Sertifikasi") or "Kegiatan Mahasiswa"
    nomor = gt_row.get("Nomor Bukti Fisik Nomor Sertifikasi") or "123/UN3/2024"
    penyelenggara = gt_row.get("Penyelenggara Kegiatan") or "Universitas Airlangga"
    tgl_mulai = standardize_date(gt_row.get("Waktu Mulai Pelaksanaan")) or "01/01/2024"
    tgl_selesai = standardize_date(gt_row.get("Waktu Selesai Pelaksanaan")) or tgl_mulai
    gt_tingkat = gt_row.get("Tingkat") or "Fakultas"

    # Simulasi bias tingkat per varian
    if variant == "v1_baseline":
        # Varian 1 baseline punya bias: lomba fakultas sering dipetakan ke Fakultas
        if "BEM" in penyelenggara and gt_tingkat == "Nasional":
            pred_tingkat = "Fakultas"  # simulasi bias baseline
        else:
            pred_tingkat = gt_tingkat
    elif variant == "v2_scope_aware":
        pred_tingkat = gt_tingkat
    elif variant == "v3_decoupled":
        # Coba router dulu
        router_res, rule_name = route_tingkat_trace(raw_text, penyelenggara)
        if router_res:
            pred_tingkat = router_res
        else:
            pred_tingkat = gt_tingkat
    elif variant == "v4_scope_signal":
        # Mock smoke test: deterministik heuristic tanpa menyalin GT
        text_lower = raw_text.lower()
        if "internasional" in text_lower or "international" in text_lower:
            pred_tingkat = "Internasional"
        elif any(k in text_lower for k in ["nasional", "se-indonesia", "indonesia", "kompetisi"]):
            pred_tingkat = "Nasional"
        elif "fakultas" in penyelenggara.lower() or "bem" in penyelenggara.lower():
            pred_tingkat = "Fakultas"
        else:
            pred_tingkat = "Lainnya"
    else:
        pred_tingkat = gt_tingkat

    fields = {
        "nama_kegiatan_sertifikasi": kegiatan,
        "nomor_bukti_fisik_nomor_sertifikasi": nomor,
        "penyelenggara_kegiatan": penyelenggara,
        "waktu_mulai_pelaksanaan": tgl_mulai,
        "waktu_selesai_pelaksanaan": tgl_selesai,
        "tingkat": pred_tingkat,
        "raw_role": "Peserta",
    }

    meta = {
        "status": "success",
        "prompt_tokens": 350,
        "candidates_tokens": 80,
        "cached_tokens": 0,
        "thoughts_tokens": 0,
        "total_tokens": 430,
        "cost_usd": 0.0002,
        "cost_idr": 3.55,
        "latency_s": 0.01,
        "calls_count": 1,
    }
    return fields, meta


def run_gemini_inference(
    variant: str,
    raw_text: str,
    client: GeminiClient,
    model: str,
    enable_grounding: bool = False,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Menjalankan ekstraksi LLM aktual dengan GeminiClient sesuai spesifikasi varian."""
    if not raw_text.strip():
        return {f: None for f in ALL_6_FIELDS}, {
            "status": "empty_text",
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "cached_tokens": 0,
            "thoughts_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_idr": 0.0,
            "latency_s": 0.0,
            "calls_count": 0,
            "error": "Teks mentah kosong",
        }

    t0 = time.perf_counter()

    if variant == "v1_baseline":
        prompt = V1_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_json(
            prompt=prompt,
            system_instruction=V1_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=enable_grounding,
        )
        norm_fields = normalize_llm_json(res.parsed_json)
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
            "calls_count": 1,
            "web_queries": res.web_search_queries,
            "error": res.error_message,
        }
        return norm_fields, meta

    elif variant == "v2_scope_aware":
        prompt = V2_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_json(
            prompt=prompt,
            system_instruction=V2_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=enable_grounding,
        )
        norm_fields = normalize_llm_json(res.parsed_json)
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
            "calls_count": 1,
            "web_queries": res.web_search_queries,
            "error": res.error_message,
        }
        return norm_fields, meta

    elif variant == "v4_scope_signal":
        prompt = V4_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_json(
            prompt=prompt,
            system_instruction=V4_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=enable_grounding,
        )
        # Ambil pola_cakupan untuk audit, lalu strip sebelum masuk normalizer evaluator
        pola_cakupan_audit = None
        parsed_copy = dict(res.parsed_json) if isinstance(res.parsed_json, dict) else None
        if parsed_copy is not None:
            pola_cakupan_audit = parsed_copy.pop("pola_cakupan", None)

        norm_fields = normalize_llm_json(parsed_copy)
        latency = time.perf_counter() - t0

        # Audit validitas enum pola_cakupan dan deteksi diskordansi dengan field tingkat
        valid_pola_enums = {"TERBUKA_SE_INDONESIA", "INTERNASIONAL", "INTERNAL_KAMPUS", "TIDAK_DITEMUKAN"}
        pola_is_valid = pola_cakupan_audit in valid_pola_enums
        pola_discordance = False
        tingkat_res = norm_fields.get("tingkat")
        if pola_cakupan_audit == "TERBUKA_SE_INDONESIA" and tingkat_res != "Nasional":
            pola_discordance = True
        elif pola_cakupan_audit == "INTERNASIONAL" and tingkat_res != "Internasional":
            pola_discordance = True

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
            "calls_count": 1,
            "web_queries": res.web_search_queries,
            "error": res.error_message,
            "pola_cakupan": pola_cakupan_audit,
            "pola_is_valid": pola_is_valid,
            "pola_discordance": pola_discordance,
            "needs_review": (not pola_is_valid) or pola_discordance or (res.status != "success"),
        }
        return norm_fields, meta

    elif variant == "v3_decoupled":
        # Stage 1: Ekstraksi 5 Field Literal Murni (Steril dari Tingkat)
        prompt_stage1 = V3_STAGE1_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res1 = client.generate_json(
            prompt=prompt_stage1,
            system_instruction=V3_STAGE1_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=False,
        )
        norm_fields = normalize_llm_json(res1.parsed_json)

        p_tokens = res1.prompt_tokens
        c_tokens = res1.candidates_tokens
        ca_tokens = res1.cached_tokens
        th_tokens = res1.thoughts_tokens
        tot_tokens = res1.total_tokens
        cost_usd = res1.cost_usd
        cost_idr = res1.cost_idr
        calls_count = 1
        web_queries = list(res1.web_search_queries)

        # Stage 2: Tingkat Resolution
        organizer_val = norm_fields.get("penyelenggara_kegiatan") or ""
        activity_val = norm_fields.get("nama_kegiatan_sertifikasi") or ""

        # Step 2a: Router Deterministik (18 rules)
        router_decision, rule_name = route_tingkat_trace(raw_text, organizer_val)

        if router_decision:
            norm_fields["tingkat"] = router_decision
            norm_fields["tingkat_source"] = f"router:{rule_name}"
        else:
            # Step 2b: Specialized Tingkat Prompt (Fallback)
            prompt_stage2 = V3_STAGE2B_USER_PROMPT_TEMPLATE.format(
                nama_kegiatan=activity_val or "-",
                penyelenggara=organizer_val or "-",
                raw_ocr_text=raw_text,
            )
            res2 = client.generate_json(
                prompt=prompt_stage2,
                system_instruction=V3_STAGE2B_SYSTEM_INSTRUCTION,
                model=model,
                temperature=0.0,
                enable_grounding=enable_grounding,
            )
            calls_count += 1
            p_tokens += res2.prompt_tokens
            c_tokens += res2.candidates_tokens
            ca_tokens += res2.cached_tokens
            th_tokens += res2.thoughts_tokens
            tot_tokens += res2.total_tokens
            cost_usd += res2.cost_usd
            cost_idr += res2.cost_idr
            web_queries.extend(res2.web_search_queries)

            tingkat_from_llm = None
            if res2.parsed_json and isinstance(res2.parsed_json, dict):
                raw_t = res2.parsed_json.get("tingkat")
                if raw_t:
                    # Map to canonical
                    t_clean = str(raw_t).strip()
                    for opt in VALID_TINGKAT_OPTIONS:
                        if opt.lower() == t_clean.lower():
                            tingkat_from_llm = opt
                            break
                    if not tingkat_from_llm:
                        t_low = t_clean.lower()
                        if "internasional" in t_low or "international" in t_low:
                            tingkat_from_llm = "Internasional"
                        elif "nasional" in t_low or "national" in t_low:
                            tingkat_from_llm = "Nasional"
                        elif "prodi" in t_low or "departemen" in t_low or "program studi" in t_low:
                            tingkat_from_llm = "Departemen/Program Studi"
                        elif "fakultas" in t_low or "faculty" in t_low:
                            tingkat_from_llm = "Fakultas"
                        elif "universitas" in t_low or "university" in t_low:
                            tingkat_from_llm = "Universitas"
                        else:
                            tingkat_from_llm = "Lainnya"

            norm_fields["tingkat"] = tingkat_from_llm or "Lainnya"
            norm_fields["tingkat_source"] = "llm_specialized_tingkat"

        latency = time.perf_counter() - t0
        meta = {
            "status": "success" if res1.status == "success" else res1.status,
            "prompt_tokens": p_tokens,
            "candidates_tokens": c_tokens,
            "cached_tokens": ca_tokens,
            "thoughts_tokens": th_tokens,
            "total_tokens": tot_tokens,
            "cost_usd": cost_usd,
            "cost_idr": cost_idr,
            "latency_s": latency,
            "calls_count": calls_count,
            "web_queries": web_queries,
            "error": res1.error_message,
        }
        return norm_fields, meta

    else:
        raise ValueError(f"Unknown variant: {variant}")


# ==============================================================================
# EVALUATION & METRICS AGGREGATOR
# ==============================================================================

def evaluate_predictions(
    doc_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Menghitung metrik evaluasi All-Cells, Framework 5F, dan per-field."""
    n_docs = len(doc_results)
    if n_docs == 0:
        return {}

    total_all_cells = n_docs * len(ALL_6_FIELDS)
    exact_all_cells = 0
    fuzzy_all_cells = 0

    total_fw_cells = 0
    exact_fw_cells = 0
    fuzzy_fw_cells = 0

    per_field_stats: dict[str, Any] = {}

    for f in ALL_6_FIELDS:
        f_exact = sum(1 for r in doc_results if r["eval"][f]["exact"])
        f_fuzzy = sum(1 for r in doc_results if r["eval"][f]["fuzzy"])
        f_wer = sum(r["eval"][f]["wer"] for r in doc_results) / n_docs
        f_cer = sum(r["eval"][f]["cer"] for r in doc_results) / n_docs

        exact_all_cells += f_exact
        fuzzy_all_cells += f_fuzzy

        # Framework non-empty 5 fields calculation
        if f in FRAMEWORK_5_FIELDS:
            for r in doc_results:
                gt_val = r["eval"][f]["gt"]
                if gt_val and gt_val != "-":
                    total_fw_cells += 1
                    if r["eval"][f]["exact"]:
                        exact_fw_cells += 1
                    if r["eval"][f]["fuzzy"]:
                        fuzzy_fw_cells += 1

        per_field_stats[f] = {
            "exact_count": f_exact,
            "exact_pct": round(f_exact / n_docs * 100.0, 2),
            "fuzzy_count": f_fuzzy,
            "fuzzy_pct": round(f_fuzzy / n_docs * 100.0, 2),
            "mean_wer": round(f_wer, 4),
            "mean_cer": round(f_cer, 4),
        }

    # Confusion on Tingkat
    nasional_to_fakultas = sum(
        1
        for r in doc_results
        if r["eval"]["tingkat"]["gt"] == "Nasional"
        and r["eval"]["tingkat"]["pred"] == "Fakultas"
    )
    fakultas_to_nasional = sum(
        1
        for r in doc_results
        if r["eval"]["tingkat"]["gt"] == "Fakultas"
        and r["eval"]["tingkat"]["pred"] == "Nasional"
    )
    total_nasional_gt = sum(
        1 for r in doc_results if r["eval"]["tingkat"]["gt"] == "Nasional"
    )
    total_fakultas_gt = sum(
        1 for r in doc_results if r["eval"]["tingkat"]["gt"] == "Fakultas"
    )

    # Token and Cost rollups
    tot_prompt_tok = sum(r["meta"].get("prompt_tokens", 0) for r in doc_results)
    tot_cand_tok = sum(r["meta"].get("candidates_tokens", 0) for r in doc_results)
    tot_cached_tok = sum(r["meta"].get("cached_tokens", 0) for r in doc_results)
    tot_thought_tok = sum(r["meta"].get("thoughts_tokens", 0) for r in doc_results)
    tot_tokens = sum(r["meta"].get("total_tokens", 0) for r in doc_results)
    tot_cost_usd = sum(r["meta"].get("cost_usd", 0.0) for r in doc_results)
    tot_cost_idr = sum(r["meta"].get("cost_idr", 0.0) for r in doc_results)
    tot_calls = sum(r["meta"].get("calls_count", 1) for r in doc_results)

    eff_tok_per_doc = round(tot_tokens / n_docs, 1) if n_docs else 0.0
    cost_per_doc_usd = tot_cost_usd / n_docs if n_docs else 0.0
    cost_per_doc_idr = tot_cost_idr / n_docs if n_docs else 0.0

    return {
        "n_docs": n_docs,
        "all_cells_6f": {
            "total_cells": total_all_cells,
            "exact_cells": exact_all_cells,
            "exact_pct": round(exact_all_cells / total_all_cells * 100.0, 2),
            "fuzzy_cells": fuzzy_all_cells,
            "fuzzy_pct": round(fuzzy_all_cells / total_all_cells * 100.0, 2),
        },
        "framework_5f": {
            "total_cells": total_fw_cells,
            "exact_cells": exact_fw_cells,
            "exact_pct": (
                round(exact_fw_cells / total_fw_cells * 100.0, 2)
                if total_fw_cells
                else 0.0
            ),
            "fuzzy_cells": fuzzy_fw_cells,
            "fuzzy_pct": (
                round(fuzzy_fw_cells / total_fw_cells * 100.0, 2)
                if total_fw_cells
                else 0.0
            ),
        },
        "per_field": per_field_stats,
        "confusion_tingkat": {
            "nasional_to_fakultas_count": nasional_to_fakultas,
            "nasional_to_fakultas_pct": (
                round(nasional_to_fakultas / total_nasional_gt * 100.0, 2)
                if total_nasional_gt
                else 0.0
            ),
            "fakultas_to_nasional_count": fakultas_to_nasional,
            "fakultas_to_nasional_pct": (
                round(fakultas_to_nasional / total_fakultas_gt * 100.0, 2)
                if total_fakultas_gt
                else 0.0
            ),
            "total_nasional_gt": total_nasional_gt,
            "total_fakultas_gt": total_fakultas_gt,
        },
        "tokens_and_cost": {
            "total_calls": tot_calls,
            "prompt_tokens": tot_prompt_tok,
            "candidates_tokens": tot_cand_tok,
            "cached_tokens": tot_cached_tok,
            "thoughts_tokens": tot_thought_tok,
            "total_tokens": tot_tokens,
            "eff_tokens_per_doc": eff_tok_per_doc,
            "total_cost_usd": round(tot_cost_usd, 4),
            "total_cost_idr": round(tot_cost_idr, 2),
            "cost_per_doc_usd": round(cost_per_doc_usd, 6),
            "cost_per_doc_idr": round(cost_per_doc_idr, 2),
            "projection_100k_certs_idr": round(cost_per_doc_idr * 100000, 2),
        },
    }


# ==============================================================================
# REPORT & DELIVERABLE WRITERS
# ==============================================================================

def write_results_excel(
    out_path: Path,
    summary_data: dict[str, Any],
    all_eval_rows: list[dict[str, Any]],
) -> None:
    """Menulis workbook Excel (.xlsx) dengan sheet Summary dan Details."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    # Sheet 1: Summary
    ws_sum = wb.active
    ws_sum.title = "Summary"

    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    sub_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
    sub_font = Font(name="Calibri", size=11, bold=True, color="000000")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    ws_sum.append(["KOMPARASI ARSITEKTUR PROMPTING ALL-6-FIELDS (EXP-ALL6F-PROMPT-001)"])
    ws_sum.merge_cells("A1:J1")
    ws_sum["A1"].font = Font(name="Calibri", size=14, bold=True, color="1F497D")
    ws_sum.append([])

    headers_summary = [
        "Varian Prompting",
        "Dataset Slice",
        "N Docs",
        "All-Cells 6F Exact (%)",
        "All-Cells 6F Fuzzy (%)",
        "Framework 5F Exact (%)",
        "Tingkat Exact (%)",
        "Total Tokens",
        "Eff Tok/Doc",
        "Total Biaya (IDR)",
    ]
    ws_sum.append(headers_summary)
    for col_idx in range(1, len(headers_summary) + 1):
        cell = ws_sum.cell(row=3, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_cursor = 4
    for var_key, var_slices in summary_data.get("variants", {}).items():
        for slice_name, metrics in var_slices.items():
            ws_sum.append([
                var_key,
                slice_name,
                metrics.get("n_docs", 0),
                metrics.get("all_cells_6f", {}).get("exact_pct", 0.0),
                metrics.get("all_cells_6f", {}).get("fuzzy_pct", 0.0),
                metrics.get("framework_5f", {}).get("exact_pct", 0.0),
                metrics.get("per_field", {}).get("tingkat", {}).get("exact_pct", 0.0),
                metrics.get("tokens_and_cost", {}).get("total_tokens", 0),
                metrics.get("tokens_and_cost", {}).get("eff_tokens_per_doc", 0.0),
                metrics.get("tokens_and_cost", {}).get("total_cost_idr", 0.0),
            ])
            for col_idx in range(1, len(headers_summary) + 1):
                c = ws_sum.cell(row=row_cursor, column=col_idx)
                c.border = thin_border
                if col_idx in (3, 8):
                    c.alignment = Alignment(horizontal="center")
                elif col_idx in (4, 5, 6, 7, 9, 10):
                    c.alignment = Alignment(horizontal="right")
            row_cursor += 1

    # Auto-fit columns
    for col in ws_sum.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_sum.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # Sheet 2: Details
    ws_det = wb.create_sheet(title="Details")
    det_headers = [
        "Varian",
        "Dataset",
        "Nama File",
        "Field",
        "Ground Truth",
        "Prediksi",
        "Status Match",
        "WER",
        "CER",
        "Prompt Tokens",
        "Cand Tokens",
        "Cached Tokens",
        "Thoughts Tokens",
        "Total Tokens",
        "Biaya (IDR)",
        "Web Queries",
    ]
    ws_det.append(det_headers)
    for col_idx in range(1, len(det_headers) + 1):
        cell = ws_det.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    red_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

    det_row_idx = 2
    for r in all_eval_rows:
        var = r["variant"]
        dataset_name = r["dataset"]
        fname = r["nama_file"]
        meta = r["meta"]

        for f in ALL_6_FIELDS:
            f_res = r["eval"][f]
            status_match = (
                "EXACT"
                if f_res["exact"]
                else ("FUZZY" if f_res["fuzzy"] else "MISMATCH")
            )
            ws_det.append([
                var,
                dataset_name,
                fname,
                f,
                f_res["gt"],
                f_res["pred"],
                status_match,
                f_res["wer"],
                f_res["cer"],
                meta.get("prompt_tokens", 0),
                meta.get("candidates_tokens", 0),
                meta.get("cached_tokens", 0),
                meta.get("thoughts_tokens", 0),
                meta.get("total_tokens", 0),
                meta.get("cost_idr", 0.0),
                ";".join(meta.get("web_queries", [])),
            ])
            c_status = ws_det.cell(row=det_row_idx, column=7)
            if status_match == "EXACT":
                c_status.fill = green_fill
            elif status_match == "FUZZY":
                c_status.fill = yellow_fill
            else:
                c_status.fill = red_fill

            for col_idx in range(1, len(det_headers) + 1):
                ws_det.cell(row=det_row_idx, column=col_idx).border = thin_border

            det_row_idx += 1

    # Auto-fit Details sheet
    for col in ws_det.columns:
        max_len = max(len(str(cell.value or "")) for cell in col[:100])
        col_letter = get_column_letter(col[0].column)
        ws_det.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    logger.info(f"Excel report saved: {out_path}")


def write_evaluation_csv(out_path: Path, all_eval_rows: list[dict[str, Any]]) -> None:
    """Menulis seluruh baris evaluasi ke flat CSV."""
    fieldnames = [
        "variant",
        "dataset",
        "nama_file",
        "field",
        "ground_truth",
        "prediction",
        "exact",
        "fuzzy",
        "wer",
        "cer",
        "prompt_tokens",
        "candidates_tokens",
        "cached_tokens",
        "thoughts_tokens",
        "total_tokens",
        "cost_usd",
        "cost_idr",
        "latency_s",
        "web_search_queries",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        for r in all_eval_rows:
            var = r["variant"]
            dset = r["dataset"]
            fname = r["nama_file"]
            meta = r["meta"]
            for field_name in ALL_6_FIELDS:
                ev = r["eval"][field_name]
                writer.writerow([
                    var,
                    dset,
                    fname,
                    field_name,
                    ev["gt"],
                    ev["pred"],
                    1 if ev["exact"] else 0,
                    1 if ev["fuzzy"] else 0,
                    ev["wer"],
                    ev["cer"],
                    meta.get("prompt_tokens", 0),
                    meta.get("candidates_tokens", 0),
                    meta.get("cached_tokens", 0),
                    meta.get("thoughts_tokens", 0),
                    meta.get("total_tokens", 0),
                    meta.get("cost_usd", 0.0),
                    meta.get("cost_idr", 0.0),
                    meta.get("latency_s", 0.0),
                    ";".join(meta.get("web_queries", [])),
                ])
    logger.info(f"CSV report saved: {out_path}")


def compute_run_identity(
    backend: str,
    model: str,
    manifest_path: str,
    gt_path: str,
    variants: list[str],
    target_doc_names: list[str],
    checkpoint_scope: str = "full",
    enable_grounding: bool = False,
    pacing_delay: float = 1.2,
    timeout_s: float = 35.0,
) -> str:
    """Menghitung identitas hash unik untuk run agar checkpoint tidak terkontaminasi."""
    m_bytes = Path(manifest_path).read_bytes() if Path(manifest_path).exists() else b""
    g_bytes = Path(gt_path).read_bytes() if Path(gt_path).exists() else b""
    m_hash = hashlib.sha256(m_bytes).hexdigest()[:8]
    g_hash = hashlib.sha256(g_bytes).hexdigest()[:8]
    docs_str = ",".join(sorted(target_doc_names))
    d_hash = hashlib.sha256(docs_str.encode("utf-8")).hexdigest()[:8]
    vars_str = "-".join(sorted(variants))
    clean_model = model.replace("/", "_").replace(":", "_")
    return f"{backend}_{clean_model}_{m_hash}_{g_hash}_{d_hash}_{vars_str}_scope{checkpoint_scope}_grnd{int(enable_grounding)}_pace{pacing_delay}_tout{int(timeout_s)}"

def write_comparative_summary_md(
    out_path: Path,
    summary: dict[str, Any],
) -> None:
    """Menghasilkan laporan eksekutif markdown komprehensif dengan nilai N dinamis."""
    date_str = datetime.now().strftime("%d %B %Y")
    var_dict = summary.get("variants", {})

    var_display_map = {
        "v1_baseline": "Varian 1 (Baseline)",
        "v2_scope_aware": "Varian 2 (Scope-Aware)",
        "v3_decoupled": "Varian 3 (Decoupled 2-Stage)",
        "v4_scope_signal": "Varian 4 (Scope Signal)",
    }
    active_vars = [v for v in var_display_map if v in var_dict] or list(var_dict.keys())

    first_var = var_dict.get(active_vars[0], {}) if active_vars else {}
    n_unified = first_var.get("unified_full", {}).get("n_docs", 0)
    n_train = first_var.get("train_v9", {}).get("n_docs", 0)
    n_test = first_var.get("test_elzandi", {}).get("n_docs", 0)

    is_complete = summary.get("is_complete", False)
    completed_evals = summary.get("completed_evaluations", 0)
    expected_evals = summary.get("expected_evaluations", 0)

    lines: list[str] = [
        "# Laporan Eksekutif: Evaluasi Komprehensif All-6-Fields & Arsitektur Prompting LLM",
    ]
    if not is_complete:
        lines.append(
            f"\n> ⚠️ **STATUS: PENGUJIAN INCOMPLETE / PARSIAL ({completed_evals}/{expected_evals} evaluasi selesai). Laporan ini bersifat sementara dan BUKAN hasil final.**\n"
        )
    lines.extend([
        f"\n**Tanggal Evaluasi**: {date_str}  ",
        f"**Model Diuji**: `{summary.get('model', 'gemini-3.1-flash-lite')}`  ",
        f"**Backend**: `{summary.get('backend', 'gemini')}`  ",
        f"**Status Kelengkapan**: `{'COMPLETE (' + str(completed_evals) + '/' + str(expected_evals) + ' Evaluasi)' if is_complete else f'INCOMPLETE ({completed_evals}/{expected_evals} Evaluasi)'}`  ",
        f"**Dokumen Selesai Utuh ({len(active_vars)} Varian)**: {summary.get('total_docs_fully_evaluated', 0)} / {summary.get('target_universe_documents', 104)} Dokumen  ",
        f"**Ground Truth Acuan**: `{Path(summary.get('gt_path', 'Ground_Truth_Sertifikat_v9.csv')).name}` ({summary.get('target_universe_documents', 74)} label terverifikasi)  ",
        f"**Evaluator**: Matcher v2 frozen (`tests/matchers.py`)  \n",
        "---",
        "\n## 1. Ringkasan Eksekutif & Pertanyaan Penelitian Utama",
        "\nEvaluasi ini dirancang secara empiris untuk menjawab pertanyaan mendasar arsitektur ekstraksi:",
        "> *Apakah pemfokusan instruksi prompting pada field `tingkat` mendegradasi akurasi 5 field faktual lainnya (`nama_kegiatan`, `nomor`, `penyelenggara`, `tanggal_mulai`, `tanggal_selesai`), dan bagaimana komparasi efisiensi biaya serta akurasi antar arsitektur prompting?*",
        "\n### Varian Arsitektur yang Dibandingkan:",
    ])

    variant_narrative_map = {
        "v1_baseline": "**Varian 1 (Single-Pass Baseline Produksi)**: Ekstraksi 6 field sekaligus dalam satu prompt dengan aturan hierarki asal (`BEM Fakultas -> Fakultas`).",
        "v2_scope_aware": "**Varian 2 (Single-Pass Scope-Aware)**: Ekstraksi 6 field sekaligus dalam satu prompt dengan revisi aturan *Scope > Organizer* (`Lomba Terbuka Mahasiswa Nasional -> Nasional`).",
        "v3_decoupled": "**Varian 3 (Decoupled 2-Stage Pipeline)**: Pemisahan total menjadi dua tahap: Stage 1 ekstraksi 5 field literal steril, disusul Stage 2 penentuan tingkat (Router Deterministik 18 rules $\\to$ Specialized LLM Fallback).",
        "v4_scope_signal": "**Varian 4 (Single-Pass In-JSON Scope Signal)**: Ekstraksi 6 field single-pass dengan intermediate controlled enum `pola_cakupan` sebelum emisi `tingkat`.",
    }
    for idx, v in enumerate(active_vars, 1):
        lines.append(f"{idx}. {variant_narrative_map.get(v, v)}")

    lines.extend([
        "\n---",
        f"\n## 2. Tabel Komparasi Performa Utama (Unified Dataset, N={n_unified})",
    ])

    headers_sec2 = ["Metrik Evaluasi"] + [var_display_map.get(v, v) for v in active_vars]
    lines.append("| " + " | ".join(headers_sec2) + " |")
    lines.append("| " + " | ".join(["---"] + [":---:"] * len(active_vars)) + " |")

    def get_f(d: dict[str, Any], p1: str, p2: str) -> float:
        return float(d.get(p1, {}).get(p2, 0.0))

    def get_u(vk: str) -> dict[str, Any]:
        return dict(var_dict.get(vk, {}).get("unified_full", {}))

    # All-cells
    lines.append(
        "| **All-Cells 6F Exact** | " + " | ".join(f"**{get_f(get_u(v), 'all_cells_6f', 'exact_pct'):.2f}%**" for v in active_vars) + " |"
    )
    # Fuzzy all-cells
    lines.append(
        "| All-Cells 6F Fuzzy | " + " | ".join(f"{get_f(get_u(v), 'all_cells_6f', 'fuzzy_pct'):.2f}%" for v in active_vars) + " |"
    )
    # Framework 5F
    lines.append(
        "| **Framework 5F Exact (Tanpa Tingkat)** | " + " | ".join(f"**{get_f(get_u(v), 'framework_5f', 'exact_pct'):.2f}%**" for v in active_vars) + " |"
    )

    # Per-field exact
    for f in ALL_6_FIELDS:
        f_title = f.replace("_", " ").title()
        lines.append(
            f"| - {f_title} | " + " | ".join(f"{get_u(v).get('per_field', {}).get(f, {}).get('exact_pct', 0.0):.2f}%" for v in active_vars) + " |"
        )

    # Confusion
    lines.append(
        "| **Hierarchical Error (Nasional $\\to$ Fakultas)** | " + " | ".join(f"{get_u(v).get('confusion_tingkat', {}).get('nasional_to_fakultas_count', 0)} kasus" for v in active_vars) + " |"
    )

    # Tokens & Cost
    lines.append(
        "| **Effective Tokens / Doc** | " + " | ".join(f"{get_u(v).get('tokens_and_cost', {}).get('eff_tokens_per_doc', 0.0):.1f} tok" for v in active_vars) + " |"
    )
    lines.append(
        f"| **Total Biaya ({n_unified} Dokumen)** | " + " | ".join(f"Rp {get_u(v).get('tokens_and_cost', {}).get('total_cost_idr', 0.0):,.2f}" for v in active_vars) + " |"
    )
    lines.append(
        "| **Proyeksi Biaya 100.000 Sertifikat** | " + " | ".join(f"Rp {get_u(v).get('tokens_and_cost', {}).get('projection_100k_certs_idr', 0.0):,.0f}" for v in active_vars) + " |"
    )

    lines.extend([
        "\n---",
        "\n## 3. Analisis Terstratifikasi per Slice Dataset",
        f"\n### 3.1 Slice 1: Train Set (v9, N={n_train})",
        f"Mengukur performa komparatif pada korpus historis {n_train} sertifikat:",
        "\n| Varian | All-Cells 6F Exact | Framework 5F Exact | Tingkat Exact | Nomor Exact | Tanggal Mulai | Penyelenggara |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for v_name in active_vars:
        v_label = var_display_map.get(v_name, v_name)
        s1 = var_dict.get(v_name, {}).get("train_v9", {})
        pf = s1.get("per_field", {})
        lines.append(
            f"| {v_label} | {s1.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}% | {s1.get('framework_5f', {}).get('exact_pct', 0.0):.2f}% | {pf.get('tingkat', {}).get('exact_pct', 0.0):.2f}% | {pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | {pf.get('waktu_mulai_pelaksanaan', {}).get('exact_pct', 0.0):.2f}% | {pf.get('penyelenggara_kegiatan', {}).get('exact_pct', 0.0):.2f}% |"
        )

    lines.extend([
        "\n---",
        f"\n### 3.2 Slice 2: Test Set (Elzandi, N={n_test})",
        f"Mengukur generalisasi murni pada dokumen mahasiswa baru (*unseen test set*, N={n_test}):",
        "\n| Varian | All-Cells 6F Exact | Framework 5F Exact | Tingkat Exact | Nomor Exact | Tanggal Mulai | Penyelenggara |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for v_name in active_vars:
        v_label = var_display_map.get(v_name, v_name)
        s2 = var_dict.get(v_name, {}).get("test_elzandi", {})
        pf = s2.get("per_field", {})
        lines.append(
            f"| {v_label} | {s2.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}% | {s2.get('framework_5f', {}).get('exact_pct', 0.0):.2f}% | {pf.get('tingkat', {}).get('exact_pct', 0.0):.2f}% | {pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | {pf.get('waktu_mulai_pelaksanaan', {}).get('exact_pct', 0.0):.2f}% | {pf.get('penyelenggara_kegiatan', {}).get('exact_pct', 0.0):.2f}% |"
        )

    lines.extend([
        "\n---",
        "\n## 4. Status Pembuktian Empiris & Keterbatasan Pengujian",
        f"\n1. **Cakupan Pengujian**: Eksperimen ini mengevaluasi akurasi All-6-Fields dan dinamika interferensi atensi pada {len(active_vars)} arsitektur prompting menggunakan model Google Gemini pada slice data Train (v9), Test (Elzandi), dan Unified.",
        "2. **Status 4 Lapis Pembuktian Empiris**: Protokol 4 lapis pembuktian empiris formal (Lapis 1 5-Fold Stratified CV, Lapis 2 OOD Perturbation Mutasi/Noise, Lapis 3 Lexical Audit Bebas Hardcoding, dan Lapis 4 Calibrated Safety Net Review Recall) **TIDAK** dijalankan secara end-to-end dalam harness prompting ini.",
        "3. **Prasyarat Promosi Produksi**: Sesuai tata kelola AGENTS.md, setiap promosi arsitektur ke tahap produksi WAJIB melalui pengujian 4 lapis lengkap dan persetujuan eksplisit dari pengguna (*user approval*).",
        "\n---",
        "\n## 5. Analisis Temuan Terukur & Rekomendasi Arsitektur",
        "\n1. **Temuan All-Cells 6F**: " + ", ".join(f"{var_display_map.get(v, v)}={get_f(get_u(v), 'all_cells_6f', 'exact_pct'):.2f}%" for v in active_vars) + ".",
        "2. **Temuan Framework 5F (Literal Faktual)**: " + ", ".join(f"{var_display_map.get(v, v)}={get_f(get_u(v), 'framework_5f', 'exact_pct'):.2f}%" for v in active_vars) + ".",
        "3. **Efisiensi Komputasi & Token**: " + ", ".join(f"{var_display_map.get(v, v)}={get_u(v).get('tokens_and_cost', {}).get('eff_tokens_per_doc', 0.0):.1f} tok/doc" for v in active_vars) + ".",
        f"4. **Biaya Riil Operasional**: Total biaya untuk {n_unified} sertifikat: " + ", ".join(f"{var_display_map.get(v, v)}=Rp {get_u(v).get('tokens_and_cost', {}).get('total_cost_idr', 0.0):,.2f}" for v in active_vars) + ".",
        "5. **Pencatatan Eksperimen**: Seluruh artefak tersimpan secara lengkap di folder `docs/experiments/EXP-ALL6F-PROMPT-001/` (`results.xlsx`, `comparative_metrics.json`, `evaluation_details.csv`, `PROMPT_REGISTRY.md`).",
    ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Markdown summary saved: {out_path}")


# ==============================================================================
# MAIN BENCHMARK RUNNER CONTROLLER
# ==============================================================================

def run_benchmark(
    manifest_path: str,
    gt_path: str,
    backend: str = "gemini",
    gemini_model: str = "gemini-3.1-flash-lite",
    variants_to_run: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    output_dir: str = "docs/experiments/EXP-ALL6F-PROMPT-001",
    cache_dir: str = "docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts",
    checkpoint_scope: str = "full",
    enable_grounding: bool = False,
    pacing_delay: float = 1.2,
    timeout_s: float = 35.0,
) -> dict[str, Any]:
    """Menjalankan alur benchmark All-6-Fields komprehensif dengan namespaced checkpointing."""
    logger.info("=== Starting All-6-Fields & Prompting Architecture Benchmark ===")
    logger.info(f"Backend: {backend} | Model: {gemini_model} | Limit: {limit} | Offset: {offset}")
    logger.info(f"Output Dir: {output_dir}")

    out_dir_path = Path(output_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    # 1. Load Manifest & Ground Truth
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest: list[dict[str, Any]] = json.load(f)

    with open(gt_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        gt_rows: dict[str, dict[str, str]] = {
            row["Nama File"].strip(): row for row in reader
        }

    # Filter documents matching GT
    docs: list[dict[str, Any]] = []
    for item in manifest:
        fname = item["nama_file"].strip()
        if fname in gt_rows:
            docs.append(item)
        else:
            logger.warning(f"File {fname} in manifest but not found in GT CSV. Skipping.")

    if offset > 0:
        docs = docs[offset:]
    if limit and limit > 0:
        docs = docs[:limit]

    logger.info(f"Target documents for evaluation: {len(docs)}")

    # 2. Setup Cache, Identity & Checkpoint
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    active_variants = variants_to_run or [
        "v1_baseline",
        "v2_scope_aware",
        "v3_decoupled",
    ]
    run_id = compute_run_identity(
        backend=backend,
        model=gemini_model,
        manifest_path=manifest_path,
        gt_path=gt_path,
        variants=active_variants,
        target_doc_names=[d["nama_file"] for d in manifest],
        checkpoint_scope=checkpoint_scope,
        enable_grounding=enable_grounding,
        pacing_delay=pacing_delay,
        timeout_s=timeout_s,
    )
    checkpoint_file = out_dir_path / f"checkpoint_{run_id}.jsonl"

    # Load verified checkpoint records
    checkpoint_records: dict[tuple[str, str], dict[str, Any]] = {}
    if checkpoint_file.exists():
        with open(checkpoint_file, "r", encoding="utf-8") as cf:
            for line in cf:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("run_identity") == run_id:
                        k = (rec.get("variant"), rec.get("nama_file"))
                        if k[0] and k[1] and rec.get("eval"):
                            checkpoint_records[k] = rec
                except Exception:
                    pass
        logger.info(
            f"Loaded {len(checkpoint_records)} verified checkpoint records from {checkpoint_file.name}"
        )

    client = None
    if backend == "gemini":
        api_key = load_google_api_key()
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY tidak ditemukan di environment atau file .env"
            )
        client = GeminiClient(
            api_key=api_key,
            default_model=gemini_model,
            request_delay=pacing_delay,
            max_retries=3,
            timeout_s=timeout_s,
        )

    all_eval_rows: list[dict[str, Any]] = []
    variant_results: dict[str, list[dict[str, Any]]] = {
        v: [] for v in active_variants
    }

    # 3. Extract Text and Run Inferences with Atomic Checkpoint
    for doc_idx, doc_info in enumerate(docs, start=1):
        fname = doc_info["nama_file"].strip()
        gt_row = gt_rows[fname]
        dataset_slice = doc_info.get("dataset", "unknown")

        # Step 3a: Obtain Raw Text (cached)
        raw_text, ext_method = get_or_extract_raw_text(doc_info, cache_path)

        for variant in active_variants:
            ckpt_key = (variant, fname)
            if ckpt_key in checkpoint_records:
                cached_rec = checkpoint_records[ckpt_key]
                variant_results[variant].append(cached_rec)
                all_eval_rows.append(cached_rec)
                logger.info(
                    f"[{doc_idx}/{len(docs)}] [{variant}] {fname} restored from checkpoint."
                )
                continue

            if backend == "mock":
                pred_fields, meta = run_mock_inference(variant, raw_text, gt_row)
            else:
                assert client is not None
                pred_fields, meta = run_gemini_inference(
                    variant=variant,
                    raw_text=raw_text,
                    client=client,
                    model=gemini_model,
                    enable_grounding=enable_grounding,
                )

            # Evaluate each of the 6 fields
            eval_record: dict[str, Any] = {}
            for f in ALL_6_FIELDS:
                gt_val = (gt_row.get(f) or gt_row.get(f.replace("_", " ").title()) or "").strip()
                if not gt_val:
                    col_map = {
                        "nama_kegiatan_sertifikasi": "Nama Kegiatan Sertifikasi",
                        "nomor_bukti_fisik_nomor_sertifikasi": "Nomor Bukti Fisik Nomor Sertifikasi",
                        "penyelenggara_kegiatan": "Penyelenggara Kegiatan",
                        "waktu_mulai_pelaksanaan": "Waktu Mulai Pelaksanaan",
                        "waktu_selesai_pelaksanaan": "Waktu Selesai Pelaksanaan",
                        "tingkat": "Tingkat",
                    }
                    gt_val = (gt_row.get(col_map.get(f, "")) or "").strip()

                pred_val = (pred_fields.get(f) or "").strip()
                m = match_field(gt_val, pred_val, f)
                eval_record[f] = {
                    "gt": gt_val,
                    "pred": pred_val,
                    "exact": bool(m["exact"]),
                    "fuzzy": bool(m["fuzzy"]),
                    "wer": float(m.get("wer", 0.0)),
                    "cer": float(m.get("cer", 0.0)),
                }

            row_entry = {
                "run_identity": run_id,
                "variant": variant,
                "nama_file": fname,
                "dataset": dataset_slice,
                "pred_fields": pred_fields,
                "eval": eval_record,
                "meta": meta,
            }

            variant_results[variant].append(row_entry)
            all_eval_rows.append(row_entry)
            checkpoint_records[ckpt_key] = row_entry

            # Atomic append to checkpoint file
            with open(checkpoint_file, "a", encoding="utf-8") as cf:
                cf.write(json.dumps(row_entry, ensure_ascii=False) + "\n")
                cf.flush()
                os.fsync(cf.fileno())
            logger.info(
                f"[{doc_idx}/{len(docs)}] [{variant}] {fname} evaluated & checkpointed (tokens: {meta.get('total_tokens', 0)}, lat: {meta.get('latency_s', 0):.2f}s)"
            )

    # 4. Compute Aggregates across full manifest from verified checkpoint records
    full_target_docs = [
        item["nama_file"].strip()
        for item in manifest
        if item["nama_file"].strip() in gt_rows
    ]
    all_completed_rows: list[dict[str, Any]] = []
    summary_variants: dict[str, Any] = {}

    for var in active_variants:
        var_list = [
            checkpoint_records[(var, fname)]
            for fname in full_target_docs
            if (var, fname) in checkpoint_records
        ]
        all_completed_rows.extend(var_list)
        train_list = [r for r in var_list if r["dataset"] == "v9"]
        test_list = [r for r in var_list if r["dataset"] == "elzandi"]
        unified_list = var_list

        summary_variants[var] = {
            "train_v9": evaluate_predictions(train_list),
            "test_elzandi": evaluate_predictions(test_list),
            "unified_full": evaluate_predictions(unified_list),
        }

    docs_fully_evaluated = [
        fname
        for fname in full_target_docs
        if all((v, fname) in checkpoint_records for v in active_variants)
    ]
    completed_evals = len(all_completed_rows)
    expected_evals = len(full_target_docs) * len(active_variants)
    is_complete = (completed_evals == expected_evals) and (expected_evals > 0)

    overall_summary = {
        "timestamp": datetime.now().isoformat(),
        "run_identity": run_id,
        "backend": backend,
        "model": gemini_model,
        "gt_path": str(gt_path),
        "completed_evaluations": completed_evals,
        "expected_evaluations": expected_evals,
        "is_complete": is_complete,
        "total_docs_fully_evaluated": len(docs_fully_evaluated),
        "total_documents": len(docs_fully_evaluated),
        "target_universe_documents": len(full_target_docs),
        "active_variants": active_variants,
        "variants": summary_variants,
    }

    # 5. Generate Deliverables
    json_path = out_dir_path / "comparative_metrics.json"
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(overall_summary, jf, indent=2, ensure_ascii=False)
    logger.info(f"JSON metrics saved: {json_path}")

    csv_path = out_dir_path / "evaluation_details.csv"
    write_evaluation_csv(csv_path, all_completed_rows)

    xlsx_path = out_dir_path / "results.xlsx"
    write_results_excel(xlsx_path, overall_summary, all_completed_rows)

    md_path = out_dir_path / "comparative_summary.md"
    write_comparative_summary_md(md_path, overall_summary)

    if is_complete:
        logger.info(
            f"=== Benchmark Completed Successfully: 100% COMPLETE ({completed_evals}/{expected_evals} evaluations across {len(full_target_docs)} docs) ==="
        )
    else:
        logger.warning(
            f"=== Benchmark Incomplete: {completed_evals}/{expected_evals} evaluations ({len(docs_fully_evaluated)}/{len(full_target_docs)} docs fully done) ==="
        )
    return overall_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="All-6-Fields & Prompting Architecture Benchmark Runner"
    )
    parser.add_argument(
        "--manifest-path",
        default=os.path.join(REPO_ROOT, "certs_unified", "manifest.json"),
        help="Path ke manifest.json certs_unified",
    )
    parser.add_argument(
        "--gt-path",
        default=os.environ.get("GT_CSV_PATH", os.path.join(REPO_ROOT, "Ground_Truth_Sertifikat_v9.csv")),
        help="Path ke Ground Truth CSV acuan (default: Ground_Truth_Sertifikat_v9.csv per protokol AGENTS.md)",
    )
    parser.add_argument(
        "--backend",
        choices=["gemini", "mock"],
        default="gemini",
        help="Backend eksekusi (gemini atau mock)",
    )
    parser.add_argument(
        "--gemini-model",
        default="gemini-3.1-flash-lite",
        help="Model Gemini yang digunakan",
    )
    parser.add_argument(
        "--variants",
        default="v1_baseline,v2_scope_aware,v3_decoupled",
        help="Daftar varian dipisahkan koma",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah dokumen untuk pengujian parsial/cepat",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Indeks awal dokumen",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=35.0,
        help="Timeout socket HTTP request (detik)",
    )
    parser.add_argument(
        "--checkpoint-scope",
        choices=["full", "smoke"],
        default="full",
        help="Scope checkpoint: 'full' untuk akumulasi 104 sertifikat, 'smoke' untuk uji parsial terisolasi",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(REPO_ROOT, "docs", "experiments", "EXP-ALL6F-PROMPT-001"),
        help="Direktori output artefak laporan",
    )
    parser.add_argument(
        "--cache-dir",
        default=os.path.join(
            REPO_ROOT, "docs", "experiments", "EXP-ALL6F-PROMPT-001", "raw_texts"
        ),
        help="Direktori cache teks mentah OCR",
    )
    parser.add_argument(
        "--enable-grounding",
        action="store_true",
        help="Aktifkan Google Search Grounding",
    )
    parser.add_argument(
        "--pacing-delay",
        type=float,
        default=1.2,
        help="Jeda rate-limiting antar request (detik)",
    )

    args = parser.parse_args()
    variants_list = [v.strip() for v in args.variants.split(",") if v.strip()]
    scope = args.checkpoint_scope
    run_benchmark(
        manifest_path=args.manifest_path,
        gt_path=args.gt_path,
        backend=args.backend,
        gemini_model=args.gemini_model,
        variants_to_run=variants_list,
        limit=args.limit,
        offset=args.offset,
        output_dir=args.output_dir,
        cache_dir=args.cache_dir,
        checkpoint_scope=scope,
        enable_grounding=args.enable_grounding,
        pacing_delay=args.pacing_delay,
        timeout_s=args.timeout_s,
    )
if __name__ == "__main__":
    main()
