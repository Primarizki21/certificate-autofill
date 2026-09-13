"""Benchmark Runner: Prompt Optimization V2 & V3 (EXP-PROMPT-OPT-002).

Evaluates 4 Prompting Architectures across all 6 KHP fields:
1. Varian A (v2_baseline): Single-Pass Scope-Aware control from EXP-ALL6F-PROMPT-001.
2. Varian B (v2_opt): Single-Pass Verbatim-Guarded & Literal-First JSON.
3. Varian C (v3_pure_llm): Decoupled 2-Stage Pure-LLM (Stage 1 6-field literal -> Stage 2 Scope-Aware CoT JSON for 100% docs).
4. Varian D (v3_enhanced_router): Decoupled 2-Stage (Stage 1 6-field literal -> Stage 2A Router 18 rules -> Stage 2B Scope-Aware CoT JSON fallback).

Adheres strictly to docs/EVALUATION_DESIGN.md:
- Primary Frozen Benchmark: 74 certificates (Ground_Truth_Sertifikat_v9.csv) with Emb-25 vs Scan-49 split & All-Cells 444.
- Auxiliary Generalization Benchmark: 104 certificates (Ground_Truth_Unified.csv) with Train v9 (74) vs Test Elzandi (30) split.
- Safety-Net Metrology: Calibrated confidence (<0.85) & needs_review recall/precision tracking.
- Granular Token & IDR Cost Accounting without 6x row duplication bug.
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

# Ensure repo root and backend are in sys.path
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
from app.services.tingkat_router import route_tingkat_trace
from tests.gemini_client import (
    DEFAULT_EXCHANGE_RATE_IDR,
    GeminiClient,
    get_exchange_rate,
    load_google_api_key,
)
from tests.matchers import match_field
from tests.ocr_engine import classify_manifest, ocr_rapid, ocr_tess
from tests.v2_staging_common import ensure_fresh_directory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark_prompt_opt_v2_v3")

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

ACTIVE_VARIANTS = [
    "v2_baseline",
    "v2_opt",
    "v3_pure_llm",
    "v3_enhanced_router",
]

# ==============================================================================
# PROMPT DEFINITIONS
# ==============================================================================

# --- VARIAN A: V2 Baseline (Scope-Aware Control) ---
V2_BASELINE_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
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

V2_BASELINE_USER_PROMPT_TEMPLATE = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
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

# --- VARIAN B: V2-Opt (Single-Pass Verbatim-Guarded & Literal-First JSON) ---
V2_OPT_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

ATURAN KRITIS - SALIN KARAKTER PERSIS (STRICT VERBATIM GUARD):
1. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Salin nomor resmi sertifikat KARAKTER DEMI KARAKTER persis seperti tertulis di teks OCR.
   - Wajib pertahankan seluruh tanda baca resmi: garis miring (/), titik (.), tanda hubung (-), atau garis bawah (_).
   - DILARANG memotong angka, membuang kode surat, atau mengubah huruf Romawi/Arab. Jika tidak ada nomor resmi, isi null.
2. Nama Kegiatan (nama_kegiatan_sertifikasi):
   - Salin judul/tema kegiatan secara utuh dan persis. Dilarang menyingkat, mengedit, atau meringkas nama acara.

ATURAN FIELD LAINNYA:
3. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama. Jika tidak ada tanggal, isi null.
4. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga"). DILARANG menyebut nama orang perorangan.
5. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", "Anggota". Jika tidak tertulis, isi null.
6. Tingkat (tingkat):
   - Wajib salah satu nilai enum: ["Internasional", "Nasional", "Universitas", "Fakultas", "Departemen/Program Studi", "Lainnya"].
   - Prinsip Scope > Organizer: Lomba/seminar/kompetisi terbuka berskala nasional -> "Nasional" (meskipun diadakan BEM/Himpunan). Event global -> "Internasional".
   - Kegiatan internal non-lomba terbuka ikuti unit: BEM Univ/Rektorat -> "Universitas"; BEM Fak -> "Fakultas"; HIMA -> "Departemen/Program Studi"; UKM/BSO/Lainnya -> "Lainnya".
"""

V2_OPT_USER_PROMPT_TEMPLATE = """PERHATIAN: Salin nomor sertifikat dan nama kegiatan persis apa adanya dari teks berikut tanpa mengubah tanda baca atau memotong karakter.

Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak seluruh field dalam format JSON dengan urutan field literal di awal:
{{
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "nama_kegiatan_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "raw_role": string atau null,
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya" atau null
}}
"""

# --- VARIAN C & D: STAGE 1 (Ekstraksi 6 Field Literal Faktual) ---
STAGE1_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual literal dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Salin persis tanpa mengubah karakter. Jika tidak ada nomor, isi null.
3. Nama Kegiatan (nama_kegiatan_sertifikasi):
   - Salin judul kegiatan secara utuh dan persis seperti tertulis di sertifikat.
4. Format Tanggal (waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan):
   - Wajib format angka "DD/MM/YYYY" (contoh: "24/08/2024").
   - Jika rentang tanggal, pisahkan tanggal mulai dan tanggal selesai.
   - Jika hanya tertulis satu tanggal pelaksanaan, isi waktu_mulai_pelaksanaan dan waktu_selesai_pelaksanaan dengan tanggal yang sama. Jika tidak ada tanggal, isi null.
5. Penyelenggara Kegiatan (penyelenggara_kegiatan):
   - Nama organisasi, institusi, lembaga, atau panitia pelaksana (contoh: "BEM FTMM Universitas Airlangga", "Himpunan Mahasiswa Teknologi Sains Data").
   - JANGAN sebut nama orang perorangan atau nama penerima sertifikat.
6. Peran (raw_role):
   - Peran partisipasi penerima sertifikat jika tertulis: "Peserta", "Panitia", "Juara", "Pembicara", "Pengurus", atau "Anggota". Jika tidak tertulis, isi null.
"""

STAGE1_USER_PROMPT_TEMPLATE = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 6 field faktual berikut dalam format JSON:
{{
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "nama_kegiatan_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "raw_role": string atau null
}}
"""

# --- VARIAN C & D: STAGE 2 (Penalaran Tingkat Scope-Aware CoT JSON) ---
STAGE2_COT_SYSTEM_INSTRUCTION = """Anda adalah asisten analis tingkat kegiatan sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: menentukan tingkat kegiatan secara objektif dan sistematis melalui analisis bertahap (Chain-of-Thought) sebelum menarik kesimpulan.

Format Jawaban Wajib: Format JSON terstruktur yang memuat langkah analisis terpisah dan label tingkat resmi.
"""

STAGE2_COT_USER_PROMPT_TEMPLATE = """Tentukan TINGKAT KEGIATAN dari sertifikat mahasiswa berikut melalui analisis bertahap.

PILIHAN TINGKAT RESMI:
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

PRINSIP PENILAIAN (Scope > Organizer):
1. Cakupan Sasaran Peserta LEBIH UTAMA daripada Jenjang Penyelenggara.
2. Lomba, kompetisi, hackathon, seminar, call for papers, atau event terbuka untuk mahasiswa umum lintas perguruan tinggi/nasional -> "Nasional" (MESKIPUN diselenggarakan oleh BEM Fakultas atau Himpunan Mahasiswa Departemen).
3. Konferensi, symposium, atau event berskala global/lintas negara -> "Internasional".
4. Kegiatan internal organisasi non-lomba terbuka ikuti jenjang unit penyelenggara:
   - Rektorat / BEM Universitas / Direktorat Kemahasiswaan Universitas -> "Universitas"
   - BEM Fakultas / ormawa fakultas -> "Fakultas"
   - Himpunan Mahasiswa / Program Studi -> "Departemen/Program Studi"
   - UKM / BSO -> "Lainnya"
5. Jika bukti tidak cukup untuk memastikan cakupan terbuka -> "Lainnya".

METADATA SERTIFIKAT TERVERIFIKASI:
- Nama Kegiatan: {nama_kegiatan}
- Penyelenggara: {penyelenggara}

TEKS MENTAH SERTIFIKAT:
--- AWAL TEKS ---
{raw_ocr_text}
--- AKHIR TEKS ---

Jawab dalam format JSON dengan langkah penalaran eksplisit:
{{
  "langkah_1_penyelenggara": "Siapa unit penyelenggara acara (Universitas, BEM Fakultas, HIMA, Lembaga Eksternal)?",
  "langkah_2_sifat_kegiatan": "Apakah lomba/seminar terbuka umum/nasional, atau kegiatan internal kampus?",
  "langkah_3_cakupan_peserta": "Terapkan prinsip Scope > Organizer: apakah cakupan peserta menaikkan tingkat ke Nasional/Internasional?",
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya"
}}
"""

# ==============================================================================
# COT PARSER HELPER
# ==============================================================================

def parse_cot_tingkat_json(parsed_json: dict[str, Any] | None) -> tuple[str, bool]:
    """Mem-parsing hasil JSON CoT dan memvalidasi label tingkat ke kanonikal enum.

    Returns:
        (canonical_tingkat, has_reasoning_steps)
    """
    if not parsed_json or not isinstance(parsed_json, dict):
        return "Lainnya", False

    has_steps = any(
        k in parsed_json
        for k in (
            "langkah_1_penyelenggara",
            "langkah_2_sifat_kegiatan",
            "langkah_3_cakupan_peserta",
            "analisis_langkah",
            "penalaran",
        )
    )

    raw_t = parsed_json.get("tingkat")
    if not raw_t:
        return "Lainnya", has_steps

    clean_t = str(raw_t).strip()
    for opt in VALID_TINGKAT_OPTIONS:
        if opt.lower() == clean_t.lower():
            return opt, has_steps

    t_low = clean_t.lower()
    if "internasional" in t_low or "international" in t_low:
        return "Internasional", has_steps
    elif "nasional" in t_low or "national" in t_low:
        return "Nasional", has_steps
    elif "prodi" in t_low or "departemen" in t_low or "program studi" in t_low:
        return "Departemen/Program Studi", has_steps
    elif "fakultas" in t_low or "faculty" in t_low:
        return "Fakultas", has_steps
    elif "universitas" in t_low or "university" in t_low:
        return "Universitas", has_steps

    return "Lainnya", has_steps


# ==============================================================================
# TEXT CACHE & INFERENCE RUNNER
# ==============================================================================

def get_or_extract_raw_text(doc_info: dict[str, Any], cache_dir: Path) -> tuple[str, str]:
    """Mengambil teks mentah dari cache atau mengekstrak langsung."""
    stem = Path(doc_info["nama_file"]).stem
    cache_file = cache_dir / f"{stem}.txt"

    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8"), "cached"

    file_path = Path(doc_info["unified_path"])
    if not file_path.exists():
        file_path = Path(doc_info.get("source_path", ""))

    if not file_path.exists():
        return "", "missing_file"

    file_bytes = file_path.read_bytes()
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        fast = extract_text_with_pymupdf(file_bytes)
        txt = fast.text.strip()
        if len(txt) >= 60:
            raw_text = txt
            method = "pymupdf_fast_path"
        else:
            raw_text = extract_text_with_ocr(file_bytes).strip()
            method = "rapid_tesseract_ocr"
    elif ext in (".png", ".jpeg", ".jpg"):
        rapid_txt = ocr_rapid(file_bytes)
        tess_txt = ocr_tess(file_bytes)
        raw_text = f"{rapid_txt}\n{tess_txt}".strip()
        method = "image_rapid_tess_ocr"
    else:
        raw_text = ""
        method = "unsupported_format"

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(raw_text, encoding="utf-8")
    return raw_text, method


def run_mock_inference(
    variant: str,
    raw_text: str,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Mock inference yang hanya memakai raw text, bukan ground truth."""
    text = raw_text or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    kegiatan = next(
        (
            line
            for line in lines
            if not re.fullmatch(r"sertifikat", line, re.IGNORECASE)
        ),
        "Mock activity from raw OCR",
    )
    number_match = next(
        (
            match.group(0)
            for match in re.finditer(
                r"\b[0-9A-Z]+(?:[/._-][0-9A-Z]+)+\b", text, re.IGNORECASE
            )
            if not re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", match.group(0))
        ),
        "MOCK/NUMBER",
    )
    organizer_match = re.search(
        r"(?:diselenggarakan|diadakan|dilaksanakan)\s+(?:oleh\s+)?(.+?)(?:[.;\n]|$)",
        text,
        re.IGNORECASE,
    )
    penyelenggara = (
        organizer_match.group(1).strip(" -:;,")
        if organizer_match
        else "Mock organizer from raw OCR"
    )
    dates = re.findall(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b",
        text,
    )
    tgl_mulai = standardize_date(dates[0]) if dates else "01/01/2000"
    tgl_selesai = standardize_date(dates[1]) if len(dates) > 1 else tgl_mulai
    level_aliases = (
        ("internasional", "Internasional"),
        ("international", "Internasional"),
        ("nasional", "Nasional"),
        ("national", "Nasional"),
        ("universitas", "Universitas"),
        ("university", "Universitas"),
        ("fakultas", "Fakultas"),
        ("faculty", "Fakultas"),
        ("departemen", "Departemen/Program Studi"),
        ("program studi", "Departemen/Program Studi"),
        ("prodi", "Departemen/Program Studi"),
    )
    lowered = text.lower()
    pred_tingkat = next(
        (value for token, value in level_aliases if token in lowered),
        "Lainnya",
    )
    calls_count = 1
    total_tokens = 420
    cost_idr = 3.45
    if variant == "v3_pure_llm":
        calls_count = 2
        total_tokens = 840
        cost_idr = 6.90
    elif variant == "v3_enhanced_router":
        router_res, _ = route_tingkat_trace(text, penyelenggara)
        if router_res:
            pred_tingkat = router_res
        else:
            calls_count = 2
            total_tokens = 840
            cost_idr = 6.90
    per_call_tokens = total_tokens // calls_count
    per_call_prompt_tokens = int(per_call_tokens * 0.8)
    per_call_candidates_tokens = per_call_tokens - per_call_prompt_tokens
    per_call_cost_idr = round(cost_idr / calls_count, 6)
    calls_details = [
        {
            "stage": f"mock_pass_{index}",
            "status": "success",
            "prompt_tokens": per_call_prompt_tokens,
            "candidates_tokens": per_call_candidates_tokens,
            "cached_tokens": 0,
            "thoughts_tokens": 0,
            "total_tokens": per_call_tokens,
            "cost_usd": round(per_call_cost_idr / DEFAULT_EXCHANGE_RATE_IDR, 6),
            "cost_idr": per_call_cost_idr,
            "latency_s": 0.01,
            "web_search_queries": [],
            "error": None,
        }
        for index in range(1, calls_count + 1)
    ]


    fields = {
        "nama_kegiatan_sertifikasi": kegiatan,
        "nomor_bukti_fisik_nomor_sertifikasi": number_match,
        "penyelenggara_kegiatan": penyelenggara,
        "waktu_mulai_pelaksanaan": tgl_mulai,
        "waktu_selesai_pelaksanaan": tgl_selesai,
        "tingkat": pred_tingkat,
        "raw_role": "Peserta",
    }
    meta = {
        "status": "success",
        "prompt_tokens": int(total_tokens * 0.8),
        "candidates_tokens": int(total_tokens * 0.2),
        "cached_tokens": 0,
        "thoughts_tokens": 0,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_idr / DEFAULT_EXCHANGE_RATE_IDR, 6),
        "cost_idr": cost_idr,
        "latency_s": 0.01,
        "calls_count": calls_count,
        "web_search_queries": [],
        "calls_details": calls_details,
        "error": None,
    }
    return fields, meta


def _call_detail(result: Any, stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": result.status,
        "prompt_tokens": result.prompt_tokens,
        "candidates_tokens": result.candidates_tokens,
        "cached_tokens": result.cached_tokens,
        "thoughts_tokens": result.thoughts_tokens,
        "total_tokens": result.total_tokens,
        "cost_usd": result.cost_usd,
        "cost_idr": result.cost_idr,
        "latency_s": result.latency_s,
        "web_search_queries": list(result.web_search_queries),
        "error": result.error_message,
    }


def run_gemini_inference(
    variant: str,
    raw_text: str,
    client: GeminiClient,
    model: str,
    enable_grounding: bool = False,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Menjalankan ekstraksi Gemini aktual sesuai spesifikasi 4 varian."""
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
            "web_search_queries": [],
            "calls_details": [],
        }

    t0 = time.perf_counter()

    if variant == "v2_baseline":
        prompt = V2_BASELINE_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_json(
            prompt=prompt,
            system_instruction=V2_BASELINE_SYSTEM_INSTRUCTION,
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
            "web_search_queries": res.web_search_queries,
            "calls_details": [_call_detail(res, "single_pass")],
            "error": res.error_message,
        }
        return norm_fields, meta

    elif variant == "v2_opt":
        prompt = V2_OPT_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_json(
            prompt=prompt,
            system_instruction=V2_OPT_SYSTEM_INSTRUCTION,
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
            "web_search_queries": res.web_search_queries,
            "calls_details": [_call_detail(res, "single_pass")],
            "error": res.error_message,
        }
        return norm_fields, meta

    elif variant == "v3_pure_llm":
        # Stage 1: Ekstraksi 6 Field Literal Faktual (Steril dari Tingkat)
        prompt1 = STAGE1_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res1 = client.generate_json(
            prompt=prompt1,
            system_instruction=STAGE1_SYSTEM_INSTRUCTION,
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

        # Stage 2: Scope-Aware CoT JSON untuk 100% dokumen
        act_val = norm_fields.get("nama_kegiatan_sertifikasi") or "-"
        org_val = norm_fields.get("penyelenggara_kegiatan") or "-"
        prompt2 = STAGE2_COT_USER_PROMPT_TEMPLATE.format(
            nama_kegiatan=act_val,
            penyelenggara=org_val,
            raw_ocr_text=raw_text,
        )
        res2 = client.generate_json(
            prompt=prompt2,
            system_instruction=STAGE2_COT_SYSTEM_INSTRUCTION,
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

        tingkat_val, _ = parse_cot_tingkat_json(res2.parsed_json)
        norm_fields["tingkat"] = tingkat_val
        norm_fields["tingkat_source"] = "pure_llm_cot"

        latency = time.perf_counter() - t0
        combined_status = (
            "success"
            if (res1.status == "success" and res2.status == "success")
            else (res1.status if res1.status != "success" else res2.status)
        )
        combined_error = res1.error_message or res2.error_message
        meta = {
            "status": combined_status,
            "prompt_tokens": p_tokens,
            "candidates_tokens": c_tokens,
            "cached_tokens": ca_tokens,
            "thoughts_tokens": th_tokens,
            "total_tokens": tot_tokens,
            "cost_usd": cost_usd,
            "cost_idr": cost_idr,
            "latency_s": latency,
            "calls_count": calls_count,
            "web_search_queries": web_queries,
            "calls_details": [
                _call_detail(res1, "stage1_literal"),
                _call_detail(res2, "stage2_tingkat"),
            ],
            "error": combined_error,
        }
        return norm_fields, meta

    elif variant == "v3_enhanced_router":
        # Stage 1: Ekstraksi 6 Field Literal Faktual
        prompt1 = STAGE1_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res1 = client.generate_json(
            prompt=prompt1,
            system_instruction=STAGE1_SYSTEM_INSTRUCTION,
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

        org_val = norm_fields.get("penyelenggara_kegiatan") or ""
        act_val = norm_fields.get("nama_kegiatan_sertifikasi") or ""

        # Stage 2A: Router Deterministik (18 rules)
        router_decision, rule_name = route_tingkat_trace(raw_text, org_val)
        res2 = None

        if router_decision:
            norm_fields["tingkat"] = router_decision
            norm_fields["tingkat_source"] = f"router:{rule_name}"
        else:
            # Stage 2B: Fallback Scope-Aware CoT JSON untuk unrouted saja
            prompt2 = STAGE2_COT_USER_PROMPT_TEMPLATE.format(
                nama_kegiatan=act_val or "-",
                penyelenggara=org_val or "-",
                raw_ocr_text=raw_text,
            )
            res2 = client.generate_json(
                prompt=prompt2,
                system_instruction=STAGE2_COT_SYSTEM_INSTRUCTION,
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

            tingkat_val, _ = parse_cot_tingkat_json(res2.parsed_json)
            norm_fields["tingkat"] = tingkat_val
            norm_fields["tingkat_source"] = "enhanced_router_cot"

        latency = time.perf_counter() - t0
        res2_status = getattr(res2, "status", "success") if res2 is not None else "success"
        res2_error = getattr(res2, "error_message", None) if res2 is not None else None
        combined_status = (
            "success"
            if (res1.status == "success" and res2_status == "success")
            else (res1.status if res1.status != "success" else res2_status)
        )
        combined_error = res1.error_message or res2_error
        meta = {
            "status": combined_status,
            "prompt_tokens": p_tokens,
            "candidates_tokens": c_tokens,
            "cached_tokens": ca_tokens,
            "thoughts_tokens": th_tokens,
            "total_tokens": tot_tokens,
            "cost_usd": cost_usd,
            "cost_idr": cost_idr,
            "latency_s": latency,
            "calls_count": calls_count,
            "web_search_queries": web_queries,
            "calls_details": [
                _call_detail(res1, "stage1_literal"),
                *(
                    [_call_detail(res2, "stage2_tingkat")]
                    if res2 is not None
                    else []
                ),
            ],
            "error": combined_error,
        }
        return norm_fields, meta

    else:
        raise ValueError(f"Unknown variant: {variant}")


# ==============================================================================
# CALIBRATED SAFETY-NET & EVALUATION METRICS
# ==============================================================================

def compute_field_confidence_and_review(
    field_name: str,
    val: str | None,
    source: str = "llm",
) -> tuple[float, bool]:
    """Menghitung calibrated confidence dan flag needs_review (<0.85)."""
    if not val or not str(val).strip():
        return 0.0, True

    v = str(val).strip()
    if field_name in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        if re.match(r"^\d{2}/\d{2}/\d{4}$", v):
            conf = 0.92
        else:
            conf = 0.50
    elif field_name == "tingkat":
        if "router:" in source:
            conf = 0.98
        elif v in VALID_TINGKAT_OPTIONS and v != "Lainnya":
            conf = 0.88
        else:
            conf = 0.70
    elif field_name == "nomor_bukti_fisik_nomor_sertifikasi":
        if any(char in v for char in "/.-_") and len(v) >= 5:
            conf = 0.88
        else:
            conf = 0.65
    elif field_name == "nama_kegiatan_sertifikasi":
        conf = 0.86 if len(v) >= 8 else 0.70
    elif field_name == "penyelenggara_kegiatan":
        conf = 0.86 if len(v) >= 5 else 0.70
    else:
        conf = 0.85

    needs_rev = conf < 0.85
    return conf, needs_rev


def evaluate_predictions(doc_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Menghitung metrik All-Cells 6F, Framework 5F, per-field, dan safety-net review."""
    n_docs = len(doc_results)
    if n_docs == 0:
        return {}

    total_all_cells = n_docs * len(ALL_6_FIELDS)
    exact_all_cells = 0
    fuzzy_all_cells = 0

    total_fw_cells = 0
    exact_fw_cells = 0
    fuzzy_fw_cells = 0
    total_fw_cells_fixed = n_docs * len(FRAMEWORK_5_FIELDS)
    exact_fw_cells_fixed = 0
    per_field_stats: dict[str, dict[str, Any]] = {
        f: {
            "exact_count": 0,
            "fuzzy_count": 0,
            "total": n_docs,
            "exact_pct": 0.0,
            "fuzzy_pct": 0.0,
            "avg_wer": 0.0,
            "avg_cer": 0.0,
        }
        for f in ALL_6_FIELDS
    }

    # Safety-net review counters at field-cell level (TP, FP, FN, TN)
    cell_error_total = 0
    cell_flagged_error = 0
    cell_flagged_total = 0
    doc_error_total = 0
    doc_flagged_error = 0
    doc_flagged_total = 0

    for r in doc_results:
        ev = r["eval"]
        doc_has_error = False
        doc_has_flag = False

        for f in ALL_6_FIELDS:
            f_res = ev[f]
            is_exact = bool(f_res["exact"])
            is_fuzzy = bool(f_res["fuzzy"])

            if is_exact:
                exact_all_cells += 1
                per_field_stats[f]["exact_count"] += 1
            else:
                cell_error_total += 1
                doc_has_error = True

            if is_fuzzy:
                fuzzy_all_cells += 1
                per_field_stats[f]["fuzzy_count"] += 1

            if f in FRAMEWORK_5_FIELDS:
                if is_exact:
                    exact_fw_cells_fixed += 1
                gt_val_s = str(f_res.get("gt") or "").strip()
                if gt_val_s and gt_val_s != "-":
                    total_fw_cells += 1
                    if is_exact:
                        exact_fw_cells += 1
                    if is_fuzzy:
                        fuzzy_fw_cells += 1

            per_field_stats[f]["avg_wer"] += f_res.get("wer", 0.0)
            per_field_stats[f]["avg_cer"] += f_res.get("cer", 0.0)

            # Check confidence and review flag per cell
            val = f_res.get("pred")
            src = r.get("tingkat_source", "llm") if f == "tingkat" else "llm"
            _, needs_rev = compute_field_confidence_and_review(f, val, src)
            if needs_rev:
                cell_flagged_total += 1
                doc_has_flag = True
                if not is_exact:
                    cell_flagged_error += 1

        if doc_has_error:
            doc_error_total += 1
            if doc_has_flag:
                doc_flagged_error += 1
        if doc_has_flag:
            doc_flagged_total += 1

    for f in ALL_6_FIELDS:
        per_field_stats[f]["exact_pct"] = round(
            per_field_stats[f]["exact_count"] / n_docs * 100.0, 2
        )
        per_field_stats[f]["fuzzy_pct"] = round(
            per_field_stats[f]["fuzzy_count"] / n_docs * 100.0, 2
        )
        per_field_stats[f]["avg_wer"] = round(per_field_stats[f]["avg_wer"] / n_docs, 4)
        per_field_stats[f]["avg_cer"] = round(per_field_stats[f]["avg_cer"] / n_docs, 4)

    # Confusion tingkat
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
    tot_nas_gt = sum(1 for r in doc_results if r["eval"]["tingkat"]["gt"] == "Nasional")
    tot_fak_gt = sum(1 for r in doc_results if r["eval"]["tingkat"]["gt"] == "Fakultas")
    # Token, biaya, latensi, status, dan kueri web dari setiap call.
    tot_prompt_tok = sum(r["meta"].get("prompt_tokens", 0) for r in doc_results)
    tot_cand_tok = sum(r["meta"].get("candidates_tokens", 0) for r in doc_results)
    tot_cached_tok = sum(r["meta"].get("cached_tokens", 0) for r in doc_results)
    tot_thought_tok = sum(r["meta"].get("thoughts_tokens", 0) for r in doc_results)
    tot_tokens = sum(r["meta"].get("total_tokens", 0) for r in doc_results)
    tot_cost_usd = sum(r["meta"].get("cost_usd", 0.0) for r in doc_results)
    tot_cost_idr = sum(r["meta"].get("cost_idr", 0.0) for r in doc_results)
    tot_calls = sum(r["meta"].get("calls_count", 1) for r in doc_results)
    tot_latency_s = sum(r["meta"].get("latency_s", 0.0) for r in doc_results)
    web_search_queries = [
        query
        for row in doc_results
        for query in row["meta"].get("web_search_queries", [])
    ]
    calls_details = [
        {"nama_file": row.get("nama_file"), **detail}
        for row in doc_results
        for detail in row["meta"].get("calls_details", [])
    ]
    status_counts: dict[str, int] = {}
    for detail in calls_details:
        status = detail.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    eff_tok_per_doc = round(tot_tokens / n_docs, 1) if n_docs else 0.0
    cost_per_doc_usd = tot_cost_usd / n_docs if n_docs else 0.0
    cost_per_doc_idr = tot_cost_idr / n_docs if n_docs else 0.0

    cell_review_recall = (
        round(cell_flagged_error / cell_error_total * 100.0, 2)
        if cell_error_total > 0
        else 100.0
    )
    cell_review_precision = (
        round(cell_flagged_error / cell_flagged_total * 100.0, 2)
        if cell_flagged_total > 0
        else 0.0
    )
    doc_review_recall = (
        round(doc_flagged_error / doc_error_total * 100.0, 2)
        if doc_error_total > 0
        else 100.0
    )
    doc_review_precision = (
        round(doc_flagged_error / doc_flagged_total * 100.0, 2)
        if doc_flagged_total > 0
        else 0.0
    )

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
            "exact_pct": round(exact_fw_cells / total_fw_cells * 100.0, 2) if total_fw_cells else 0.0,
            "fuzzy_cells": fuzzy_fw_cells,
            "fuzzy_pct": round(fuzzy_fw_cells / total_fw_cells * 100.0, 2) if total_fw_cells else 0.0,
            "fixed_total_cells": total_fw_cells_fixed,
            "fixed_exact_pct": round(exact_fw_cells_fixed / total_fw_cells_fixed * 100.0, 2) if total_fw_cells_fixed else 0.0,
        },
        "per_field": per_field_stats,
        "safety_net_review": {
            "cell_level": {
                "total_errors": cell_error_total,
                "flagged_errors": cell_flagged_error,
                "total_flagged": cell_flagged_total,
                "recall_pct": cell_review_recall,
                "precision_pct": cell_review_precision,
            },
            "doc_level": {
                "total_errors": doc_error_total,
                "flagged_errors": doc_flagged_error,
                "total_flagged": doc_flagged_total,
                "recall_pct": doc_review_recall,
                "precision_pct": doc_review_precision,
            },
            "review_recall_pct": doc_review_recall,
            "review_precision_pct": doc_review_precision,
        },
        "confusion_tingkat": {
            "nasional_to_fakultas_count": nasional_to_fakultas,
            "nasional_to_fakultas_pct": round(nasional_to_fakultas / tot_nas_gt * 100.0, 2) if tot_nas_gt else 0.0,
            "fakultas_to_nasional_count": fakultas_to_nasional,
            "fakultas_to_nasional_pct": round(fakultas_to_nasional / tot_fak_gt * 100.0, 2) if tot_fak_gt else 0.0,
            "total_nasional_gt": tot_nas_gt,
            "total_fakultas_gt": tot_fak_gt,
        },
        "tokens_and_cost": {
            "total_calls": tot_calls,
            "prompt_tokens": tot_prompt_tok,
            "candidates_tokens": tot_cand_tok,
            "cached_tokens": tot_cached_tok,
            "thoughts_tokens": tot_thought_tok,
            "total_tokens": tot_tokens,
            "eff_tokens_per_doc": eff_tok_per_doc,
            "total_latency_s": round(tot_latency_s, 4),
            "avg_latency_s": round(tot_latency_s / tot_calls, 4) if tot_calls else 0.0,
            "web_search_queries": web_search_queries,
            "status_counts": status_counts,
            "calls_details": calls_details,
            "total_cost_usd": round(tot_cost_usd, 4),
            "total_cost_idr": round(tot_cost_idr, 2),
            "cost_per_doc_usd": round(cost_per_doc_usd, 6),
            "cost_per_doc_idr": round(cost_per_doc_idr, 2),
            "projection_100k_certs_idr": round(cost_per_doc_idr * 100000, 2),
        },
    }

# ==============================================================================
# REPORT WRITERS
# ==============================================================================

def write_results_excel(
    out_path: Path,
    summary_variants: dict[str, Any],
    all_eval_rows: list[dict[str, Any]],
) -> None:
    """Menulis Excel multi-sheet: Summary, Primary 74, Unified 104, dan Details ber-warna."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    # Sheet 1: Summary Komparasi
    ws_sum = wb.active
    ws_sum.title = "Summary"

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    sub_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    ws_sum.append(["KOMPARASI PROMPT OPTIMIZATION (EXP-PROMPT-OPT-002)"])
    ws_sum.append(["Tanggal Evaluasi:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    ws_sum.append([])

    headers = [
        "Varian",
        "Primary 74 Exact (All-444)",
        "Primary FW-5F Exact",
        "Scan-49 Exact",
        "Emb-25 Exact",
        "Unified 104 Exact",
        "Test Elzandi (N=30)",
        "Nomor (Test 30)",
        "Kegiatan (Test 30)",
        "Tingkat (Test 30)",
        "Review Recall",
        "Eff Tok/Doc",
        "Biaya / Doc (IDR)",
    ]
    ws_sum.append(headers)
    for col_idx in range(1, len(headers) + 1):
        c = ws_sum.cell(row=4, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")

    variant_labels = {
        "v2_baseline": "Varian A: V2 Baseline (Control)",
        "v2_opt": "Varian B: V2-Opt (Verbatim Guard)",
        "v3_pure_llm": "Varian C: V3-PureLLM (Zero Rules)",
        "v3_enhanced_router": "Varian D: V3-Enhanced-Router",
    }

    row_idx = 5
    for var_key, var_label in variant_labels.items():
        v_data = summary_variants.get(var_key, {})
        p74 = v_data.get("primary_v9_74", {})
        u104 = v_data.get("unified_full", {})
        t30 = v_data.get("test_elzandi", {})
        scan = v_data.get("primary_scan49", {})
        emb = v_data.get("primary_emb25", {})

        row_vals = [
            var_label,
            f"{p74.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}%",
            f"{p74.get('framework_5f', {}).get('exact_pct', 0.0):.2f}%",
            f"{scan.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}%",
            f"{emb.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}%",
            f"{u104.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}%",
            f"{t30.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}%",
            f"{t30.get('per_field', {}).get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}%",
            f"{t30.get('per_field', {}).get('nama_kegiatan_sertifikasi', {}).get('exact_pct', 0.0):.2f}%",
            f"{t30.get('per_field', {}).get('tingkat', {}).get('exact_pct', 0.0):.2f}%",
            f"{p74.get('safety_net_review', {}).get('review_recall_pct', 0.0):.1f}%",
            p74.get("tokens_and_cost", {}).get("eff_tokens_per_doc", 0.0),
            round(p74.get("tokens_and_cost", {}).get("cost_per_doc_idr", 0.0), 2),
        ]
        ws_sum.append(row_vals)
        for col_idx in range(1, len(headers) + 1):
            cell = ws_sum.cell(row=row_idx, column=col_idx)
            cell.border = thin_border
            if col_idx > 1:
                cell.alignment = Alignment(horizontal="center")
        row_idx += 1

    # Auto-fit Summary
    for col in ws_sum.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_sum.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # Sheet 2: Details ber-warna
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
        cell.fill = sub_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    red_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

    det_row_idx = 2
    for r in all_eval_rows:
        var = r["variant"]
        dset = r["dataset"]
        fname = r["nama_file"]
        meta = r["meta"]

        for f_name in ALL_6_FIELDS:
            f_res = r["eval"][f_name]
            status_match = "EXACT" if f_res["exact"] else ("FUZZY" if f_res["fuzzy"] else "MISMATCH")
            ws_det.append([
                var,
                dset,
                fname,
                f_name,
                f_res["gt"],
                f_res["pred"],
                status_match,
                f_res.get("wer", 0.0),
                f_res.get("cer", 0.0),
                meta.get("prompt_tokens", 0),
                meta.get("candidates_tokens", 0),
                meta.get("cached_tokens", 0),
                meta.get("thoughts_tokens", 0),
                meta.get("total_tokens", 0),
                meta.get("cost_idr", 0.0),
                ";".join(meta.get("web_search_queries", [])),
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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    logger.info(f"Excel report saved: {out_path}")


def write_evaluation_csv(out_path: Path, all_eval_rows: list[dict[str, Any]]) -> None:
    """Menulis flat CSV 19 kolom terstandardisasi."""
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
                    ev.get("wer", 0.0),
                    ev.get("cer", 0.0),
                    meta.get("prompt_tokens", 0),
                    meta.get("candidates_tokens", 0),
                    meta.get("cached_tokens", 0),
                    meta.get("thoughts_tokens", 0),
                    meta.get("total_tokens", 0),
                    meta.get("cost_usd", 0.0),
                    meta.get("cost_idr", 0.0),
                    round(meta.get("latency_s", 0.0), 3),
                    ";".join(meta.get("web_search_queries", [])),
                ])
    logger.info(f"CSV report saved: {out_path}")


def write_comparative_summary_md(
    out_path: Path,
    summary_variants: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Menghasilkan comparative_summary.md yang kohesif dan transparan."""
    lines = [
        "# Laporan Eksekutif: Evaluasi Lanjutan Optimasi Prompting V2 & V3 (EXP-PROMPT-OPT-002)",
        "",
        f"**Tanggal Evaluasi**: {datetime.now().strftime('%d %B %Y')}  ",
        f"**Model Diuji**: `{metadata.get('model', 'gemini-3.1-flash-lite')}`  ",
        f"**Backend**: `{metadata.get('backend', 'gemini')}`  ",
        f"**Total Dokumen Dievaluasi**: {metadata.get('total_docs', 104)} (Primary v9 N=74 + Test Elzandi N=30)  ",
        f"**Evaluator**: Matcher v2 frozen (`tests/matchers.py`)  ",
        "",
        "---",
        "",
        "## 1. Ringkasan Eksekutif & Hipotesis Eksperimen",
        "",
        "Eksperimen ini mengevaluasi 4 varian arsitektur untuk menjawab tuntas:",
        "1. **Hipotesis V2-Opt**: Apakah penambahan *Strict Verbatim Guard* dan pemadatan System Instruction mampu memulihkan akurasi nomor sertifikat tanpa mengorbankan akurasi tingkat?",
        "2. **Hipotesis V3-PureLLM vs V3-Enhanced-Router**: Apakah eliminasi total aturan regex (100% 2-stage LLM) lebih unggul dalam generalisasi dibandingkan router deterministik 18 rules yang dipadukan dengan Scope-Aware CoT Fallback?",
        "",
        "---",
        "",
        "## 2. Tabel Komparasi Utama: Primary Frozen Benchmark (N=74, All-Cells 444)",
        "",
        "Sesuai `docs/EVALUATION_DESIGN.md`, berikut evaluasi otoritatif pada 74 dokumen Ground Truth v9:",
        "",
        "| Varian | All-Cells Exact (444 sel) | FW-5F Exact (370 sel) | Scan-49 Exact | Emb-25 Exact | Tingkat | Nomor | Kegiatan | Review Recall | Eff Tok/Doc | Biaya (IDR) |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for v_key, v_label in [
        ("v2_baseline", "Varian A (V2 Baseline)"),
        ("v2_opt", "Varian B (V2-Opt Guarded)"),
        ("v3_pure_llm", "Varian C (V3-PureLLM)"),
        ("v3_enhanced_router", "Varian D (V3-Enhanced-Router)"),
    ]:
        v_d = summary_variants.get(v_key, {})
        p = v_d.get("primary_v9_74", {})
        s = v_d.get("primary_scan49", {})
        e = v_d.get("primary_emb25", {})
        pf = p.get("per_field", {})
        lines.append(
            f"| {v_label} | {p.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}% | "
            f"{p.get('framework_5f', {}).get('exact_pct', 0.0):.2f}% | "
            f"{s.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}% | "
            f"{e.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('tingkat', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nama_kegiatan_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{p.get('safety_net_review', {}).get('review_recall_pct', 0.0):.1f}% | "
            f"{p.get('tokens_and_cost', {}).get('eff_tokens_per_doc', 0.0)} | "
            f"Rp {p.get('tokens_and_cost', {}).get('cost_per_doc_idr', 0.0):.2f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Evaluasi Auxiliary Generalization: Holdout Test Set Elzandi (N=30)",
        "",
        "Mengukur ketahanan out-of-domain pada dokumen mahasiswa baru (*unseen holdout*):",
        "",
        "| Varian | All-Cells Exact | Framework 5F | Tingkat | Nomor Sertifikat | Nama Kegiatan | Penyelenggara |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for v_key, v_label in [
        ("v2_baseline", "Varian A (V2 Baseline)"),
        ("v2_opt", "Varian B (V2-Opt Guarded)"),
        ("v3_pure_llm", "Varian C (V3-PureLLM)"),
        ("v3_enhanced_router", "Varian D (V3-Enhanced-Router)"),
    ]:
        v_d = summary_variants.get(v_key, {})
        t = v_d.get("test_elzandi", {})
        pf = t.get("per_field", {})
        lines.append(
            f"| {v_label} | {t.get('all_cells_6f', {}).get('exact_pct', 0.0):.2f}% | "
            f"{t.get('framework_5f', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('tingkat', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nama_kegiatan_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('penyelenggara_kegiatan', {}).get('exact_pct', 0.0):.2f}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Analisis Temuan Kunci & Rekomendasi",
        "",
        "1. **Dampak Strict Verbatim Guard (V2-Opt)**: Menunjukkan apakah instruksi karakter persis mampu mencegah salah ketik nomor sertifikat.",
        "2. **Trade-off Pure-LLM vs Enhanced-Router**: Membandingkan efisiensi token router deterministik vs akurasi penalaran CoT bertahap.",
        "3. **Evaluasi Safety Net**: Review recall mengukur proporsi kesalahan ekstraksi yang berhasil terdeteksi oleh sistem untuk diverifikasi pengguna.",
        "",
    ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Summary markdown saved: {out_path}")


# ==============================================================================
# MAIN BENCHMARK ORCHESTRATOR
# ==============================================================================

def _run_identity(
    *,
    manifest_path: str,
    gt_path: str,
    matched_docs: list[dict[str, Any]],
    active_variants: list[str],
    backend: str,
    gemini_model: str,
    checkpoint_scope: str,
    enable_grounding: bool,
    pacing_delay: float,
    timeout_s: float,
    offset: int = 0,
    limit: int | None = None,
) -> tuple[str, dict[str, Any]]:
    prompt_source = "\n".join(
        (
            V2_BASELINE_SYSTEM_INSTRUCTION,
            V2_BASELINE_USER_PROMPT_TEMPLATE,
            V2_OPT_SYSTEM_INSTRUCTION,
            V2_OPT_USER_PROMPT_TEMPLATE,
            STAGE1_SYSTEM_INSTRUCTION,
            STAGE1_USER_PROMPT_TEMPLATE,
            STAGE2_COT_SYSTEM_INSTRUCTION,
            STAGE2_COT_USER_PROMPT_TEMPLATE,
        )
    )
    payload = {
        "manifest_sha256": hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
        "gt_sha256": hashlib.sha256(Path(gt_path).read_bytes()).hexdigest(),
        "documents": [doc["nama_file"].strip() for doc in matched_docs],
        "variants": list(active_variants),
        "backend": backend,
        "model": gemini_model,
        "checkpoint_scope": checkpoint_scope,
        "enable_grounding": enable_grounding,
        "pacing_delay": pacing_delay,
        "timeout_s": timeout_s,
        "offset": offset,
        "limit": limit,
        "prompt_sha256": hashlib.sha256(prompt_source.encode("utf-8")).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest(), payload


def run_benchmark(
    manifest_path: str,
    gt_path: str,
    output_dir: str,
    backend: str = "gemini",
    gemini_model: str = "gemini-3.1-flash-lite",
    variants: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    cache_dir: str | None = None,
    checkpoint_scope: str = "full",
    enable_grounding: bool = False,
    pacing_delay: float = 1.2,
    timeout_s: float = 35.0,
    *,
    force: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Menjalankan alur benchmark All-6-Fields optimasi prompt."""
    logger.info("=== Starting Prompt Optimization V2 & V3 Benchmark (EXP-PROMPT-OPT-002) ===")
    logger.info(f"Backend: {backend} | Model: {gemini_model} | Limit: {limit} | Offset: {offset}")
    logger.info(f"Output Dir: {output_dir}")

    out_dir_path = Path(output_dir)
    if force or resume:
        out_dir_path.mkdir(parents=True, exist_ok=True)
    else:
        ensure_fresh_directory(out_dir_path)
    # Cache default mengikuti output agar eksperimen baru tidak mencampur artefak lama.
    cache_path = Path(cache_dir) if cache_dir else out_dir_path / "raw_texts"
    cache_path.mkdir(parents=True, exist_ok=True)

    # 1. Load Ground Truth
    with open(gt_path, mode="r", encoding="utf-8") as f:
        gt_reader = csv.DictReader(f)
        gt_rows = {row["Nama File"].strip(): row for row in gt_reader if row.get("Nama File")}
    if not gt_rows:
        raise ValueError(f"Ground truth kosong: {gt_path}")
    logger.info(f"Loaded {len(gt_rows)} ground truth rows from {gt_path}")

    # 2. Load Manifest
    with open(manifest_path, mode="r", encoding="utf-8") as f:
        manifest = json.load(f)
    matched_docs = [d for d in manifest if d["nama_file"].strip() in gt_rows]
    logger.info(f"Manifest matched with GT: {len(matched_docs)} / {len(manifest)} documents")
    if len(matched_docs) != len(gt_rows):
        missing_in_manifest = sorted(set(gt_rows) - {d["nama_file"].strip() for d in matched_docs})
        raise ValueError(
            "Manifest/GT tidak lengkap; dokumen GT tanpa manifest: "
            f"{missing_in_manifest}"
        )

    # Enforce slice integrity if v9 GT is specified
    if "v9" in Path(gt_path).name.lower():
        if len(gt_rows) != 74 or len(matched_docs) != 74:
            raise ValueError(
                f"Slice integrity check FAILED for primary v9: expected 74 docs, got {len(matched_docs)} matched and {len(gt_rows)} GT rows."
            )
    # Load layout manifest to classify Scan-49 vs Emb-25
    layout_manifest_path = Path(REPO_ROOT) / "tests" / "layout_manifest.json"
    scan_classification = {}
    if layout_manifest_path.exists():
        try:
            with open(layout_manifest_path, "r", encoding="utf-8") as lf:
                lm = json.load(lf)
            scan_classification = classify_manifest(lm)
        except Exception as e:
            logger.warning(f"Could not classify layout manifest: {e}")

    active_variants = variants or ACTIVE_VARIANTS
    unknown_variants = sorted(set(active_variants) - set(ACTIVE_VARIANTS))
    if unknown_variants:
        raise ValueError(f"Unknown benchmark variants: {unknown_variants}")

    # Compute run identity from every input and prompt/configuration dependency.
    target_fnames = [d["nama_file"].strip() for d in matched_docs]
    vars_str = "-".join(active_variants)
    m_hash = hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()[:8]
    g_hash = hashlib.sha256(Path(gt_path).read_bytes()).hexdigest()[:8]
    d_hash = hashlib.sha256(";".join(sorted(target_fnames)).encode()).hexdigest()[:8]
    clean_model = gemini_model.replace("/", "_").replace(":", "_")
    slice_key = f"off{offset}_lim{limit if limit is not None else 'all'}"
    run_id = (
        f"{backend}_{clean_model}_{m_hash}_{g_hash}_{d_hash}_{vars_str}"
        f"_scope{checkpoint_scope}_{slice_key}_grnd{int(enable_grounding)}"
        f"_pace{pacing_delay}_tout{int(timeout_s)}"
    )
    identity_hash, identity_payload = _run_identity(
        manifest_path=manifest_path,
        gt_path=gt_path,
        matched_docs=matched_docs,
        active_variants=active_variants,
        backend=backend,
        gemini_model=gemini_model,
        checkpoint_scope=checkpoint_scope,
        enable_grounding=enable_grounding,
        pacing_delay=pacing_delay,
        timeout_s=timeout_s,
        offset=offset,
        limit=limit,
    )
    identity_path = out_dir_path / "run_identity.json"
    if identity_path.exists():
        existing_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if existing_identity.get("identity_hash") != identity_hash:
            raise ValueError(
                "Output directory berisi run identity berbeda; gunakan folder baru."
            )
    elif resume:
        raise ValueError("Resume ditolak: run_identity.json tidak ditemukan.")
    identity_path.write_text(
        json.dumps(
            {"identity_hash": identity_hash, "payload": identity_payload},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    checkpoint_file = out_dir_path / f"checkpoint_{run_id}.jsonl"
    checkpoint_records: dict[tuple[str, str], dict[str, Any]] = {}

    if resume and checkpoint_file.exists():
        with open(checkpoint_file, "r", encoding="utf-8") as cf:
            for line in cf:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        k = (rec.get("variant", ""), rec.get("nama_file", ""))
                        if (
                            k[0]
                            and k[1]
                            and rec.get("eval")
                            and rec.get("run_identity") == identity_hash
                        ):
                            checkpoint_records[k] = rec
                    except Exception:
                        continue
        logger.info(
            f"Loaded {len(checkpoint_records)} verified checkpoint records "
            f"from {checkpoint_file.name}"
        )
    elif checkpoint_file.exists():
        checkpoint_file.write_text("", encoding="utf-8")

    client = None
    if backend == "gemini":
        api_key = load_google_api_key()
        client = GeminiClient(
            api_key=api_key,
            timeout_s=timeout_s,
            request_delay=pacing_delay,
            max_retries=3,
        )
    # Slice documents if limit/offset specified
    docs_to_eval = matched_docs[offset:]
    if limit is not None:
        docs_to_eval = docs_to_eval[:limit]

    all_eval_rows: list[dict[str, Any]] = []

    for doc_idx, doc_info in enumerate(docs_to_eval, start=1):
        fname = doc_info["nama_file"].strip()
        gt_row = gt_rows[fname]
        raw_text, extract_method = get_or_extract_raw_text(doc_info, cache_path)
        if not raw_text.strip():
            raise ValueError(f"Raw OCR kosong untuk {fname}; benchmark dihentikan.")
        dset_type = doc_info.get("dataset", "v9")
        stem = Path(fname).stem
        is_scan = scan_classification.get(stem, {}).get("scan", True)


        for variant in active_variants:
            ckpt_key = (variant, fname)
            if ckpt_key in checkpoint_records:
                cached_rec = checkpoint_records[ckpt_key]
                all_eval_rows.append(cached_rec)
                logger.info(f"[{doc_idx}/{len(docs_to_eval)}] [{variant}] {fname} restored from checkpoint.")
                continue

            if backend == "gemini":
                pred_fields, meta = run_gemini_inference(
                    variant=variant,
                    raw_text=raw_text,
                    client=client,
                    model=gemini_model,
                    enable_grounding=enable_grounding,
                )
                time.sleep(pacing_delay)
            else:
                pred_fields, meta = run_mock_inference(
                    variant=variant,
                    raw_text=raw_text,
                )

            # Match fields with Matcher v2 frozen
            eval_dict: dict[str, Any] = {}
            for f in ALL_6_FIELDS:
                pred_val = pred_fields.get(f)
                gt_val = gt_row.get(
                    f.replace("_", " ").title().replace("Nomor Bukti Fisik Nomor Sertifikasi", "Nomor Bukti Fisik Nomor Sertifikasi")
                )
                if not gt_val:
                    # Alternative column headers
                    col_map = {
                        "nama_kegiatan_sertifikasi": "Nama Kegiatan Sertifikasi",
                        "nomor_bukti_fisik_nomor_sertifikasi": "Nomor Bukti Fisik Nomor Sertifikasi",
                        "penyelenggara_kegiatan": "Penyelenggara Kegiatan",
                        "waktu_mulai_pelaksanaan": "Waktu Mulai Pelaksanaan",
                        "waktu_selesai_pelaksanaan": "Waktu Selesai Pelaksanaan",
                        "tingkat": "Tingkat",
                    }
                    gt_val = gt_row.get(col_map.get(f, ""), "")

                m_res = match_field(field_name=f, expected=gt_val, actual=pred_val)
                eval_dict[f] = {
                    "gt": gt_val,
                    "pred": pred_val,
                    "exact": m_res["exact"],
                    "fuzzy": m_res["fuzzy"],
                    "wer": m_res["wer"],
                    "cer": m_res["cer"],
                }
            row_entry = {
                "variant": variant,
                "dataset": dset_type,
                "nama_file": fname,
                "is_scan": is_scan,
                "raw_text_method": extract_method,
                "tingkat_source": pred_fields.get("tingkat_source", "llm"),
                "eval": eval_dict,
                "meta": meta,
                "run_identity": identity_hash,
            }

            all_eval_rows.append(row_entry)
            checkpoint_records[ckpt_key] = row_entry

            # Atomic append to checkpoint file
            with open(checkpoint_file, "a", encoding="utf-8") as cf:
                cf.write(json.dumps(row_entry, ensure_ascii=False) + "\n")
                cf.flush()
                os.fsync(cf.fileno())

            logger.info(
                f"[{doc_idx}/{len(docs_to_eval)}] [{variant}] {fname} evaluated & checkpointed (tokens: {meta.get('total_tokens', 0)}, calls: {meta.get('calls_count', 1)})"
            )

    # 4. Compute Aggregate Metrics
    summary_variants: dict[str, Any] = {}
    for var in active_variants:
        var_rows = [r for r in all_eval_rows if r["variant"] == var]
        v9_rows = [r for r in var_rows if r["dataset"] == "v9"]
        elzandi_rows = [r for r in var_rows if r["dataset"] == "elzandi"]
        scan_rows = [r for r in v9_rows if r.get("is_scan", True)]
        emb_rows = [r for r in v9_rows if not r.get("is_scan", True)]

        summary_variants[var] = {
            "primary_v9_74": evaluate_predictions(v9_rows),
            "primary_scan49": evaluate_predictions(scan_rows),
            "primary_emb25": evaluate_predictions(emb_rows),
            "test_elzandi": evaluate_predictions(elzandi_rows),
            "unified_full": evaluate_predictions(var_rows),
        }

    # 5. Write Deliverables
    write_results_excel(out_dir_path / "results.xlsx", summary_variants, all_eval_rows)
    write_evaluation_csv(out_dir_path / "evaluation_details.csv", all_eval_rows)

    metrics_payload = {
        "metadata": {
            "campaign_id": "EXP-PROMPT-OPT-CAMPAIGN-001",
            "run_id": run_id,
            "run_identity": identity_hash,
            "status": "STAGING_ONLY",
            "timestamp": datetime.now().isoformat(),
            "model": gemini_model,
            "backend": backend,
            "total_evaluations": len(all_eval_rows),
            "evaluated_docs": len({row["nama_file"] for row in all_eval_rows}),
            "total_docs": len(matched_docs),
            "variants": active_variants,
        },
        "summary": summary_variants,
    }
    with open(out_dir_path / "comparative_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2, ensure_ascii=False)

    write_comparative_summary_md(
        out_dir_path / "comparative_summary.md",
        summary_variants,
        metrics_payload["metadata"],
    )

    logger.info("=== Benchmark Completed Successfully ===")
    return metrics_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Prompt Optimization V2 & V3 Benchmark Runner")
    parser.add_argument(
        "--manifest-path",
        default=os.path.join(REPO_ROOT, "certs_unified", "manifest.json"),
        help="Path ke manifest.json",
    )
    parser.add_argument(
        "--gt-path",
        default=os.path.join(REPO_ROOT, "Ground_Truth_Unified.csv"),
        help="Path ke Ground_Truth CSV",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(REPO_ROOT, "docs", "experiments", "EXP-PROMPT-OPT-002"),
        help="Direktori output artefak",
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
        default="v2_baseline,v2_opt,v3_pure_llm,v3_enhanced_router",
        help="Daftar varian dipisahkan koma",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Batasi jumlah dokumen untuk pengujian parsial/smoke",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Indeks awal dokumen",
    )
    parser.add_argument(
        "--checkpoint-scope",
        choices=["full", "smoke"],
        default="full",
        help="Scope checkpoint",
    )
    parser.add_argument(
        "--pacing-delay",
        type=float,
        default=1.2,
        help="Jeda detik antar request",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=35.0,
        help="Timeout socket per request",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Izinkan menulis ulang output yang sama setelah identity cocok",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Lanjutkan checkpoint dengan identity yang sama",
    )

    args = parser.parse_args()
    var_list = [v.strip() for v in args.variants.split(",") if v.strip()]

    run_benchmark(
        manifest_path=args.manifest_path,
        gt_path=args.gt_path,
        output_dir=args.output_dir,
        backend=args.backend,
        gemini_model=args.gemini_model,
        variants=var_list,
        limit=args.limit,
        offset=args.offset,
        checkpoint_scope=args.checkpoint_scope,
        force=args.force,
        resume=args.resume,
        pacing_delay=args.pacing_delay,
        timeout_s=args.timeout_s,
    )


if __name__ == "__main__":
    main()
