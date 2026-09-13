"""Benchmark Google Search Grounding untuk Klasifikasi Tingkat & All-6-Fields.

Eksperimen: EXP-SEARCH-GROUNDING-001
Tujuan:
1. Menguji secara ilmiah apakah Google Search Grounding pada Gemini 3.1 Flash Lite
   dapat meningkatkan akurasi klasifikasi `tingkat` tanpa merusak field literal lainnya.
2. Mengisolasi efek Google Search secara bersih dengan menyediakan `v2_text_control`
   (mode teks tanpa search) dan `v2_search` (mode teks dengan search) pada prompt,
   model, dan parameter yang identik 100%.
3. Membandingkan performa pada:
   - Primary Frozen Benchmark (N=74, Ground_Truth_Sertifikat_v9.csv)
   - Auxiliary Holdout Test Set (N=30, Dokumen Mahasiswa Baru Elzandi)
   - Unified Total Universe (N=104)
4. Melakukan akuntansi token rinci (prompt, candidates, cached, thoughts, total),
   estimasi biaya token (USD & IDR), biaya kueri search terpisah,
   latensi, dan kueri web per-call.

Penggunaan:
  uv run python -m tests.benchmark_search_grounding --backend mock --limit 5
  uv run python -m tests.benchmark_search_grounding --backend gemini --variants v2_text_control,v2_search
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
from collections import Counter
from dataclasses import asdict, dataclass, field
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
from app.services.gemini_extractor import normalize_llm_json, standardize_date
from tests.gemini_client import (
    DEFAULT_EXCHANGE_RATE_IDR,
    GeminiClient,
    get_exchange_rate,
    load_google_api_key,
)
from tests.matchers import match_field
from tests.v2_staging_common import ensure_fresh_directory

def load_and_normalize_gt(csv_path: str | Path) -> dict[str, dict[str, str]]:
    """Muat ground truth dan gagal tertutup bila input hilang atau kosong."""
    result: dict[str, dict[str, str]] = {}
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"Ground truth tidak ditemukan: {p}")
    with open(p, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fname = (row.get("Nama File") or row.get("nama_file") or "").strip()
            if not fname:
                continue
            normalized = {
                "nama_file": fname,
                "nama_kegiatan_sertifikasi": (row.get("Nama Kegiatan Sertifikasi") or row.get("nama_kegiatan_sertifikasi") or "-").strip(),
                "nomor_bukti_fisik_nomor_sertifikasi": (row.get("Nomor Bukti Fisik Nomor Sertifikasi") or row.get("nomor_bukti_fisik_nomor_sertifikasi") or "-").strip(),
                "penyelenggara_kegiatan": (row.get("Penyelenggara Kegiatan") or row.get("penyelenggara_kegiatan") or "-").strip(),
                "waktu_mulai_pelaksanaan": (row.get("Waktu Mulai Pelaksanaan") or row.get("waktu_mulai_pelaksanaan") or "-").strip(),
                "waktu_selesai_pelaksanaan": (row.get("Waktu Selesai Pelaksanaan") or row.get("waktu_selesai_pelaksanaan") or "-").strip(),
                "tingkat": (row.get("Tingkat") or row.get("tingkat") or "-").strip(),
                "raw_role": (row.get("Folder") or row.get("raw_role") or "-").strip(),
            }
            result[fname] = normalized
    if not result:
        raise ValueError(f"Ground truth kosong: {p}")
    return result

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark_search_grounding")

ALL_6_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
]

ACTIVE_VARIANTS = [
    "v2_text_control",
    "v2_search",
    "v3_text_control",
    "v3_search_cot",
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
SEARCH_QUERY_FEE_USD = 0.014
SEARCH_QUERY_FEE_IDR = round(SEARCH_QUERY_FEE_USD * DEFAULT_EXCHANGE_RATE_IDR, 2)


# ==============================================================================
# PROMPT DEFINITIONS
# ==============================================================================

# --- PROMPT V2 (Scope-Aware Text-Mode) ---
# Digunakan secara identik oleh:
# - v2_text_control (grounding=False)
# - v2_search (grounding=True)
V2_PURE_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
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

# Varian Eksplorasi Sekunder: Dengan panduan search eksplisit di system instruction
V2_SEARCH_GUIDED_SYSTEM_INSTRUCTION = V2_PURE_SYSTEM_INSTRUCTION + """
Pemanfaatan Pencarian Web (Google Search):
- Gunakan Google Search HANYA jika Anda perlu mengonfirmasi skala/tingkat kegiatan (misal: apakah suatu kompetisi/seminar berskala Nasional atau Internasional) atau memverifikasi profil penyelenggara.
- DILARANG KERAS menggunakan informasi dari web untuk nomor sertifikat atau tanggal kegiatan! Nomor sertifikat dan tanggal WAJIB 100% disalin dari teks fisik sertifikat.
"""

V2_USER_PROMPT_TEMPLATE = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
--- TEKS OCR AWAL ---
{raw_ocr_text}
--- TEKS OCR AKHIR ---

Ekstrak 7 field berikut dan hasilkan HANYA dalam blok kode JSON yang valid:
```json
{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "tingkat": "Internasional"|"Nasional"|"Universitas"|"Fakultas"|"Departemen/Program Studi"|"Lainnya" atau null,
  "raw_role": string atau null
}}
```
"""

# --- PROMPT STAGE 1 (Ekstraksi 5 Field Literal Steril) ---
STAGE1_SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: mengekstrak informasi faktual literal dari teks OCR mentah sertifikat ke dalam format JSON yang presisi.

Aturan Wajib:
1. Ekstrak HANYA informasi yang tertulis di teks OCR sertifikat. Jangan berhalusinasi atau menambahkan asumsi.
2. Nomor Sertifikat (nomor_bukti_fisik_nomor_sertifikasi):
   - Ambil nomor resmi sertifikat secara utuh dan lengkap beserta seluruh tanda garis miring (/), titik (.), atau tanda hubung (-) (contoh: "123/UN3.1/KM/2024").
   - Salin persis tanpa mengubah karakter. Jika tidak ada nomor, isi null.
3. Nama Kegiatan (nama_kegiatan_sertifikasi):
   - Salin nama resmi kegiatan. JANGAN sertakan slogan tema atau tagline.
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

Ekstrak 6 field faktual berikut dalam blok kode JSON:
```json
{{
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "nama_kegiatan_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "raw_role": string atau null
}}
```
"""

# --- PROMPT STAGE 2 (Penalaran Tingkat CoT + Search) ---
STAGE2_SEARCH_COT_SYSTEM_INSTRUCTION = """Anda adalah asisten analis tingkat kegiatan sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
Tugas Anda: menentukan tingkat kegiatan secara objektif dan sistematis melalui analisis bertahap (Chain-of-Thought) dan pencarian web (Google Search) sebelum menarik kesimpulan.

Format Jawaban Wajib: Format JSON terstruktur di dalam blok ```json ... ``` yang memuat langkah analisis terpisah dan label tingkat resmi.
"""

STAGE2_SEARCH_COT_USER_PROMPT_TEMPLATE = """Nama Kegiatan: '{nama_kegiatan}'
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
# ==============================================================================
# HELPER PARSING & INFERENCE
# ==============================================================================

def clean_json_from_text(text: str) -> dict[str, Any] | None:
    """Ekstrak blok JSON dari output teks bebas."""
    if not text:
        return None
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if match:
        json_str = match.group(1).strip()
    else:
        json_str = stripped
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Fallback cari kurung kurawal pertama dan terakhir
    first_b = stripped.find("{")
    last_b = stripped.rfind("}")
    if first_b != -1 and last_b != -1 and last_b > first_b:
        try:
            data = json.loads(stripped[first_b : last_b + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def parse_cot_tingkat(data: dict[str, Any] | None) -> tuple[str | None, str]:
    """Ekstrak nilai tingkat dari CoT JSON."""
    if not data or not isinstance(data, dict):
        return None, "parse_error"
    raw_val = data.get("tingkat")
    if not raw_val or not isinstance(raw_val, str):
        return None, "missing_tingkat"
    val = raw_val.strip()
    for opt in FORM_OPTIONS.get("tingkat", []):
        if val.lower() == opt.lower():
            return opt, "cot_match"
    return "Lainnya", "cot_fallback"


def compute_field_confidence_and_review(
    field_name: str,
    value: str | None,
    source: str,
) -> tuple[float, bool]:
    """Hitung calibrated confidence dan review flag."""
    if value is None or str(value).strip() in ("", "-", "None", "null"):
        return 0.50, True

    v_str = str(value).strip()
    if field_name == "nomor_bukti_fisik_nomor_sertifikasi":
        if re.search(r"[\/\-\._]", v_str) and len(v_str) >= 8:
            return 0.90, False
        return 0.70, True
    elif field_name in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        if re.match(r"^\d{2}\/\d{2}\/\d{4}$", v_str):
            return 0.95, False
        return 0.75, True
    elif field_name == "tingkat":
        if v_str in VALID_TINGKAT_OPTIONS:
            return 0.88, False
        return 0.60, True
    elif field_name == "nama_kegiatan_sertifikasi":
        if len(v_str) >= 5:
            return 0.88, False
        return 0.65, True
    elif field_name == "penyelenggara_kegiatan":
        if len(v_str) >= 5:
            return 0.88, False
        return 0.65, True
def _mock_level_from_raw(raw_text: str) -> str:
    text = raw_text.lower()
    if "internasional" in text or "international" in text:
        return "Internasional"
    if "nasional" in text or "national" in text or "se-indonesia" in text:
        return "Nasional"
    if "universitas" in text or "university" in text:
        return "Universitas"
    if "fakultas" in text or "faculty" in text or "bem" in text:
        return "Fakultas"
    if "departemen" in text or "program studi" in text or "prodi" in text:
        return "Departemen/Program Studi"
    return "Lainnya"


def run_mock_inference(
    variant: str,
    raw_text: str,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Mock runner yang hanya memakai raw OCR, bukan ground truth."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    activity = next(
        (
            line
            for line in lines
            if not re.match(r"^(nomor|tanggal|date|oleh|by|sertifikat)\b", line, re.I)
        ),
        "Mock Activity",
    )
    number_match = re.search(r"\b[\w.-]+(?:/[\w.-]+){1,}\b", raw_text)
    dates = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", raw_text)
    organizer_match = re.search(
        r"\b(?:oleh|by)\s*:?\s*(.+?)(?:\n|$)",
        raw_text,
        re.I,
    )
    fields = {
        "nama_kegiatan_sertifikasi": activity[:200],
        "nomor_bukti_fisik_nomor_sertifikasi": number_match.group(0) if number_match else "123/MOCK/2024",
        "penyelenggara_kegiatan": organizer_match.group(1).strip()[:200]
        if organizer_match
        else "BEM MOCK Universitas",
        "waktu_mulai_pelaksanaan": dates[0] if dates else "10/10/2024",
        "waktu_selesai_pelaksanaan": dates[1] if len(dates) > 1 else (dates[0] if dates else "10/10/2024"),
        "tingkat": _mock_level_from_raw(raw_text),
    }
    web_q = [f"kegiatan {activity[:80]}"] if "search" in variant else []
    calls_count = 2 if "v3" in variant else 1
    if calls_count == 2:
        calls_details = [
            {
                "stage": "stage1_literal",
                "status": "success",
                "prompt_tokens": 600,
                "candidates_tokens": 40,
                "cached_tokens": 0,
                "thoughts_tokens": 0,
                "total_tokens": 640,
                "cost_usd": 0.00005,
                "cost_idr": 0.8,
                "latency_s": 0.025,
                "web_search_queries": [],
                "error": None,
            },
            {
                "stage": "stage2_tingkat",
                "status": "success",
                "prompt_tokens": 600,
                "candidates_tokens": 40,
                "cached_tokens": 0,
                "thoughts_tokens": 0,
                "total_tokens": 640,
                "cost_usd": 0.00005,
                "cost_idr": 0.8,
                "latency_s": 0.025,
                "web_search_queries": web_q,
                "error": None,
            },
        ]
    else:
        calls_details = [
            {
                "stage": "single_pass",
                "status": "success",
                "prompt_tokens": 1200,
                "candidates_tokens": 80,
                "cached_tokens": 0,
                "thoughts_tokens": 0,
                "total_tokens": 1280,
                "cost_usd": 0.0001,
                "cost_idr": 1.6,
                "latency_s": 0.05,
                "web_search_queries": web_q,
                "error": None,
            }
        ]
    meta = {
        "status": "success",
        "prompt_tokens": 1200,
        "candidates_tokens": 80,
        "cached_tokens": 0,
        "thoughts_tokens": 0,
        "total_tokens": 1280,
        "cost_usd": 0.0001,
        "cost_idr": 1.6,
        "latency_s": 0.05,
        "calls_count": calls_count,
        "web_search_queries": web_q,
        "web_queries": web_q,
        "calls_details": calls_details,
        "error": None,
        "raw_response": "```json\n" + json.dumps(fields) + "\n```",
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
) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Eksekusi inference aktual ke Gemini API."""
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
            "calls_details": [],
            "web_search_queries": [],
            "error": "Teks mentah kosong",
            "raw_response": "",
        }

    t0 = time.perf_counter()

    if variant == "v2_text_control":
        # Text mode tanpa search grounding (KONTROL PRIMER 100% IDENTIK)
        prompt = V2_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_text(
            prompt=prompt,
            system_instruction=V2_PURE_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=False,
        )
        parsed = clean_json_from_text(res.response_text)
        norm_fields = normalize_llm_json(parsed)
        latency = time.perf_counter() - t0
        meta = {
            "status": res.status if parsed is not None else "parse_failure",
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
            "web_search_queries": res.web_search_queries,
            "error": res.error_message or (None if parsed is not None else "JSON parse failure"),
            "raw_response": res.response_text,
            "calls_details": [_call_detail(res, "single_pass")],
        }
        return norm_fields, meta

    elif variant == "v2_search":
        # Text mode DENGAN search grounding aktif (PROMPT 100% IDENTIK DENGAN KONTROL)
        prompt = V2_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_text(
            prompt=prompt,
            system_instruction=V2_PURE_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=True,
        )
        parsed = clean_json_from_text(res.response_text)
        norm_fields = normalize_llm_json(parsed)
        latency = time.perf_counter() - t0
        meta = {
            "status": res.status if parsed is not None else "parse_failure",
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
            "web_search_queries": res.web_search_queries,
            "error": res.error_message or (None if parsed is not None else "JSON parse failure"),
            "raw_response": res.response_text,
            "calls_details": [_call_detail(res, "single_pass")],
        }
        return norm_fields, meta

    elif variant == "v2_search_guided":
        # Varian eksplorasi: Prompt dengan klausul search eksplisit
        prompt = V2_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res = client.generate_text(
            prompt=prompt,
            system_instruction=V2_SEARCH_GUIDED_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=True,
        )
        parsed = clean_json_from_text(res.response_text)
        norm_fields = normalize_llm_json(parsed)
        latency = time.perf_counter() - t0
        meta = {
            "status": res.status if parsed is not None else "parse_failure",
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
            "web_search_queries": res.web_search_queries,
            "error": res.error_message or (None if parsed is not None else "JSON parse failure"),
            "raw_response": res.response_text,
            "calls_details": [_call_detail(res, "single_pass")],
        }
        return norm_fields, meta

    elif variant in ("v3_text_control", "v3_search_cot"):
        enable_search = (variant == "v3_search_cot")
        # Stage 1: Ekstraksi 5 field literal tanpa search (100% identik)
        prompt1 = STAGE1_USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_text)
        res1 = client.generate_text(
            prompt=prompt1,
            system_instruction=STAGE1_SYSTEM_INSTRUCTION,
            model=model,
            temperature=0.0,
            enable_grounding=False,
        )
        parsed1 = clean_json_from_text(res1.response_text)
        norm_fields = normalize_llm_json(parsed1)

        # Stage 2: Scope-Aware CoT (hanya beda enable_grounding=enable_search)
        act_val = norm_fields.get("nama_kegiatan_sertifikasi") or "-"
        org_val = norm_fields.get("penyelenggara_kegiatan") or "-"
        prompt2 = STAGE2_SEARCH_COT_USER_PROMPT_TEMPLATE.format(
            nama_kegiatan=act_val,
            penyelenggara=org_val,
        )
        res2 = client.generate_text(
            prompt=prompt2,
            system_instruction=None,
            model=model,
            temperature=0.0,
            enable_grounding=enable_search,
        )
        parsed2 = clean_json_from_text(res2.response_text)
        tingkat_val, _ = parse_cot_tingkat(parsed2)
        norm_fields["tingkat"] = tingkat_val

        latency = time.perf_counter() - t0
        meta = {
            "status": "success" if (parsed1 and parsed2) else "parse_failure",
            "prompt_tokens": res1.prompt_tokens + res2.prompt_tokens,
            "candidates_tokens": res1.candidates_tokens + res2.candidates_tokens,
            "cached_tokens": res1.cached_tokens + res2.cached_tokens,
            "thoughts_tokens": res1.thoughts_tokens + res2.thoughts_tokens,
            "total_tokens": res1.total_tokens + res2.total_tokens,
            "cost_usd": res1.cost_usd + res2.cost_usd,
            "cost_idr": res1.cost_idr + res2.cost_idr,
            "latency_s": latency,
            "calls_count": 2,
            "web_queries": res2.web_search_queries,
            "web_search_queries": res2.web_search_queries,
            "calls_details": [
                _call_detail(res1, "stage1_literal"),
                _call_detail(res2, "stage2_tingkat"),
            ],
            "error": None if (parsed1 and parsed2) else "JSON parse failure in Stage 1 or Stage 2",
            "raw_response": f"STAGE1:\n{res1.response_text}\n\nSTAGE2:\n{res2.response_text}",
        }
        return norm_fields, meta
    else:
        raise ValueError(f"Unknown variant: {variant}")


# ==============================================================================
# EVALUATION AGGREGATION & METRICS
# ==============================================================================

def evaluate_predictions(
    preds: dict[str, str | None],
    gt_row: dict[str, str],
) -> dict[str, Any]:
    """Evaluasi exact & fuzzy match per field menggunakan matcher v2 frozen."""
    eval_res: dict[str, Any] = {}
    for f in ALL_6_FIELDS:
        gt_val = str(gt_row.get(f) or "-").strip()
        pred_val = preds.get(f)
        m = match_field(expected=gt_val, actual=pred_val, field_name=f)
        eval_res[f] = {
            "gt": gt_val,
            "pred": pred_val,
            "exact": bool(m.get("exact", False)),
            "fuzzy": bool(m.get("fuzzy", False)),
            "wer": round(float(m.get("wer", 1.0)), 4),
            "cer": round(float(m.get("cer", 1.0)), 4),
        }
    return eval_res


def aggregate_variant_metrics(doc_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Agregasi metrik All-Cells 6F, Framework 5F, Review Recall, Token & Biaya."""
    n_docs = len(doc_results)
    if n_docs == 0:
        return {"n_docs": 0}

    total_all_cells = n_docs * 6
    exact_all_cells = 0
    fuzzy_all_cells = 0

    total_fw_cells = 0
    exact_fw_cells = 0
    fuzzy_fw_cells = 0

    per_field_stats: dict[str, dict[str, Any]] = {
        f: {
            "exact_count": 0,
            "fuzzy_count": 0,
            "total_count": n_docs,
            "avg_wer": 0.0,
            "avg_cer": 0.0,
        }
        for f in ALL_6_FIELDS
    }

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
            is_exact = f_res["exact"]
            is_fuzzy = f_res["fuzzy"]

            if is_exact:
                exact_all_cells += 1
                per_field_stats[f]["exact_count"] += 1
            else:
                doc_has_error = True
                cell_error_total += 1

            if is_fuzzy:
                fuzzy_all_cells += 1
                per_field_stats[f]["fuzzy_count"] += 1

            per_field_stats[f]["avg_wer"] += f_res["wer"]
            per_field_stats[f]["avg_cer"] += f_res["cer"]

            if f in FRAMEWORK_5_FIELDS:
                gt_val = str(f_res["gt"]).strip()
                if gt_val and gt_val != "-":
                    total_fw_cells += 1
                    if is_exact:
                        exact_fw_cells += 1
                    if is_fuzzy:
                        fuzzy_fw_cells += 1

            val = f_res["pred"]
            src = "search" if "search" in r.get("variant", "") else "llm"
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

    # Token, biaya, latensi, status, dan kueri web.
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
        for query in row["meta"].get(
            "web_search_queries",
            row["meta"].get("web_queries", []),
        )
    ]
    calls_details = [
        {"variant": row.get("variant"), **detail}
        for row in doc_results
        for detail in row["meta"].get("calls_details", [])
    ]
    status_counts: dict[str, int] = {}
    for row in doc_results:
        status = row["meta"].get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    tot_web_queries = len(web_search_queries)

    eff_tok_per_doc = round(tot_tokens / n_docs, 1) if n_docs else 0.0
    cost_per_doc_idr = tot_cost_idr / n_docs if n_docs else 0.0

    cell_review_recall = (
        round(cell_flagged_error / cell_error_total * 100.0, 2)
        if cell_error_total > 0
        else 100.0
    )
    doc_review_recall = (
        round(doc_flagged_error / doc_error_total * 100.0, 2)
        if doc_error_total > 0
        else 100.0
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
            "exact_pct": round(exact_fw_cells / total_fw_cells * 100.0, 2)
            if total_fw_cells
            else 0.0,
            "fuzzy_cells": fuzzy_fw_cells,
            "fuzzy_pct": round(fuzzy_fw_cells / total_fw_cells * 100.0, 2)
            if total_fw_cells
            else 0.0,
        },
        "per_field": per_field_stats,
        "safety_net_review": {
            "cell_level": {
                "total_errors": cell_error_total,
                "flagged_errors": cell_flagged_error,
                "total_flagged": cell_flagged_total,
                "recall_pct": cell_review_recall,
            },
            "doc_level": {
                "total_errors": doc_error_total,
                "flagged_errors": doc_flagged_error,
                "total_flagged": doc_flagged_total,
                "recall_pct": doc_review_recall,
            },
        },
        "hierarchical_confusion": {
            "nasional_to_fakultas": nasional_to_fakultas,
            "fakultas_to_nasional": fakultas_to_nasional,
        },
        "token_and_cost": {
            "total_prompt_tokens": tot_prompt_tok,
            "total_candidates_tokens": tot_cand_tok,
            "total_cached_tokens": tot_cached_tok,
            "total_thoughts_tokens": tot_thought_tok,
            "total_tokens": tot_tokens,
            "effective_tokens_per_doc": eff_tok_per_doc,
            "total_calls": tot_calls,
            "total_web_queries": tot_web_queries,
            "total_latency_s": round(tot_latency_s, 4),
            "avg_latency_s": round(tot_latency_s / tot_calls, 4) if tot_calls else 0.0,
            "web_search_queries": web_search_queries,
            "calls_details": calls_details,
            "status_counts": status_counts,
            "total_cost_usd": round(tot_cost_usd, 4),
            "total_cost_idr": round(tot_cost_idr, 2),
            "cost_per_doc_idr": round(cost_per_doc_idr, 2),
            "total_search_fee_usd": round(tot_web_queries * SEARCH_QUERY_FEE_USD, 6),
            "total_search_fee_idr": round(tot_web_queries * SEARCH_QUERY_FEE_IDR, 2),
            "total_effective_cost_idr": round(
                tot_cost_idr + tot_web_queries * SEARCH_QUERY_FEE_IDR,
                2,
            ),
        },
    }


def _input_digest(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Input benchmark tidak ditemukan: {path}")
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    else:
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(str(child.relative_to(path)).encode())
            digest.update(child.read_bytes())
    return digest.hexdigest()


def _build_search_identity(
    manifest_path: Path,
    gt_unified_path: Path,
    gt_primary_path: Path,
    cache_dir: Path,
    active_vars: list[str],
    backend: str,
    gemini_model: str,
    offset: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
    prompt_text = "\n".join(
        (
            V2_PURE_SYSTEM_INSTRUCTION,
            V2_SEARCH_GUIDED_SYSTEM_INSTRUCTION,
            V2_USER_PROMPT_TEMPLATE,
            STAGE1_SYSTEM_INSTRUCTION,
            STAGE1_USER_PROMPT_TEMPLATE,
            STAGE2_SEARCH_COT_USER_PROMPT_TEMPLATE,
        )
    )
    payload: dict[str, Any] = {
        "campaign_id": "EXP-SEARCH-GROUNDING-CAMPAIGN-001",
        "experiment_id": "EXP-SEARCH-GROUNDING-001",
        "manifest_sha256": _input_digest(manifest_path),
        "gt_unified_sha256": _input_digest(gt_unified_path),
        "gt_primary_sha256": _input_digest(gt_primary_path),
        "raw_texts_sha256": _input_digest(cache_dir),
        "variants": list(active_vars),
        "backend": backend,
        "gemini_model": gemini_model,
        "offset": offset,
        "limit": limit,
        "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    payload["identity_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return payload


# ==============================================================================
# RUNNER PIPELINE
# ==============================================================================

def run_benchmark(
    manifest_path: str = "certs_unified/manifest.json",
    gt_unified_path: str = "Ground_Truth_Unified.csv",
    gt_primary_path: str = "Ground_Truth_Sertifikat_v9.csv",
    output_dir: str = "docs/experiments/EXP-SEARCH-GROUNDING-001",
    backend: str = "gemini",
    gemini_model: str = "gemini-3.1-flash-lite",
    variants: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
    reuse_checkpoint: str | None = None,
    cache_dir: str = "docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts",
    pacing_delay: float = 1.2,
    timeout_s: float = 35.0,
    force: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Fungsi eksekusi terpadu benchmark Search Grounding."""
    if force and resume:
        raise ValueError("Pilih salah satu: force atau resume.")
    out_dir_path = Path(REPO_ROOT) / output_dir
    if force or resume:
        out_dir_path.mkdir(parents=True, exist_ok=True)
    else:
        ensure_fresh_directory(out_dir_path)

    active_vars = variants or ACTIVE_VARIANTS
    unknown_variants = sorted(set(active_vars) - set(ACTIVE_VARIANTS))
    if unknown_variants:
        raise ValueError(f"Varian benchmark tidak dikenal: {unknown_variants}")
    logger.info(f"=== Menjalankan EXP-SEARCH-GROUNDING-001 ===")
    logger.info(f"Backend: {backend} | Model: {gemini_model}")
    logger.info(f"Varian aktif: {active_vars}")

    manifest_file = Path(REPO_ROOT) / manifest_path
    gt_unified_file = Path(REPO_ROOT) / gt_unified_path
    gt_primary_file = Path(REPO_ROOT) / gt_primary_path
    raw_texts_dir = Path(REPO_ROOT) / cache_dir
    if not raw_texts_dir.is_dir():
        raise FileNotFoundError(f"Direktori cache raw text tidak ditemukan: {raw_texts_dir}")
    if not manifest_file.exists():
        raise FileNotFoundError(f"Manifest tidak ditemukan: {manifest_file}")
    with open(manifest_file, encoding="utf-8") as f:
        manifest_data = json.load(f)
    if not isinstance(manifest_data, list) or not manifest_data:
        raise ValueError(f"Manifest kosong atau tidak valid: {manifest_file}")

    gt_unified_map = load_and_normalize_gt(gt_unified_file)
    gt_primary_map = load_and_normalize_gt(gt_primary_file)
    logger.info(
        f"Loaded {len(gt_unified_map)} rows from {gt_unified_path}, "
        f"{len(gt_primary_map)} rows from {gt_primary_path}"
    )

    if not limit and offset == 0:
        if len(gt_unified_map) != 104:
            raise ValueError(f"Expected 104 unified GT rows, got {len(gt_unified_map)}")
        if len(gt_primary_map) != 74:
            raise ValueError(f"Expected 74 primary v9 GT rows, got {len(gt_primary_map)}")
    docs = manifest_data[offset : offset + limit] if limit else manifest_data[offset:]
    if not docs:
        raise ValueError("Slice benchmark kosong; periksa offset/limit.")
    for doc in docs:
        fname = doc["nama_file"]
        dset = doc.get("dataset", "v9")
        gt_row = (
            gt_primary_map.get(fname)
            if dset == "v9"
            else gt_unified_map.get(fname)
        ) or gt_unified_map.get(fname)
        if not gt_row:
            raise ValueError(f"Ground truth tidak memiliki baris untuk {fname}")
    expected_raw_stems = {Path(doc["nama_file"]).stem for doc in docs}
    available_raw_stems = {path.stem for path in raw_texts_dir.glob("*.txt")}
    missing_raw = sorted(expected_raw_stems - available_raw_stems)
    if missing_raw:
        raise FileNotFoundError(
            f"Cache raw OCR tidak lengkap ({len(missing_raw)}): {missing_raw[:5]}"
        )
    empty_raw = sorted(
        path.stem
        for path in raw_texts_dir.glob("*.txt")
        if path.stem in expected_raw_stems
        and not path.read_text(encoding="utf-8", errors="replace").strip()
    )
    if empty_raw:
        raise ValueError(f"Cache raw OCR kosong untuk dokumen: {empty_raw[:5]}")
    logger.info(f"Total dokumen dievaluasi: {len(docs)}")

    run_identity = _build_search_identity(
        manifest_file,
        gt_unified_file,
        gt_primary_file,
        raw_texts_dir,
        active_vars,
        backend,
        gemini_model,
        offset=offset,
        limit=limit,
    )
    identity_path = out_dir_path / "run_identity.json"
    if resume:
        if not identity_path.exists():
            raise FileNotFoundError(f"Checkpoint identity tidak ditemukan: {identity_path}")
        stored_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if stored_identity.get("identity_sha256") != run_identity["identity_sha256"]:
            raise ValueError("Checkpoint identity berbeda dari input/configuration saat ini.")
    identity_path.write_text(
        json.dumps(run_identity, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 3. Inisialisasi Klien
    client = None
    if backend == "gemini":
        api_key = load_google_api_key()
        if not api_key:
            raise ValueError("GOOGLE_API_KEY tidak ditemukan di environment.")
        client = GeminiClient(api_key=api_key, default_model=gemini_model, timeout_s=timeout_s)

    # 4. Inisialisasi Checkpoint
    checkpoint_file = out_dir_path / f"checkpoint_{backend}_{gemini_model.replace('/', '_')}.jsonl"
    cached_records: dict[tuple[str, str], dict[str, Any]] = {}

    # Opsi muat checkpoint kontrol lama (misal v2_baseline & v3_pure_llm)
    if reuse_checkpoint:
        reuse_path = Path(reuse_checkpoint)
        if not reuse_path.exists():
            raise FileNotFoundError(f"Checkpoint kontrol tidak ditemukan: {reuse_path}")
        logger.info(f"Memuat checkpoint kontrol lama dari: {reuse_path}")
        with open(reuse_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    rec["run_identity"] = run_identity["identity_sha256"]
                    cached_records[(rec["variant"], rec["nama_file"])] = rec

    if resume and checkpoint_file.exists():
        logger.info(f"Melanjutkan checkpoint aktif: {checkpoint_file}")
        with open(checkpoint_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    if rec.get("run_identity") == run_identity["identity_sha256"]:
                        cached_records[(rec["variant"], rec["nama_file"])] = rec

    records_by_variant: dict[str, list[dict[str, Any]]] = {v: [] for v in active_vars}

    # 5. Loop Eksekusi Dokumen
    cp_writer = open(checkpoint_file, "a" if resume else "w", encoding="utf-8")

    try:
        for idx, doc in enumerate(docs, 1):
            fname = doc["nama_file"]
            dset = doc.get("dataset", "v9")
            is_scan = doc.get("is_scan", False)

            # Pilih GT yang otoritatif
            if dset == "v9" and fname in gt_primary_map:
                gt_row = gt_primary_map[fname]
            else:
                gt_row = gt_unified_map.get(fname, {})
            if not gt_row:
                raise ValueError(f"Ground truth tidak memiliki baris untuk {fname}")

            txt_file = raw_texts_dir / f"{Path(fname).stem}.txt"
            if not txt_file.exists():
                raise FileNotFoundError(f"Raw text cache tidak ditemukan untuk {fname}: {txt_file}")
            raw_text = txt_file.read_text(encoding="utf-8")
            if not raw_text.strip():
                raise ValueError(f"Raw text cache kosong untuk {fname}: {txt_file}")

            for var in active_vars:
                key = (var, fname)
                if key in cached_records:
                    rec = cached_records[key]
                    records_by_variant[var].append(rec)
                    continue

                logger.info(f"[{idx}/{len(docs)}] Running {var} on {fname}...")

                if backend == "gemini":
                    fields, meta = run_gemini_inference(
                        var, raw_text, client, gemini_model
                    )
                    time.sleep(pacing_delay)
                else:
                    fields, meta = run_mock_inference(var, raw_text)
                eval_data = evaluate_predictions(fields, gt_row)

                rec = {
                    "run_identity": run_identity["identity_sha256"],
                    "variant": var,
                    "dataset": dset,
                    "nama_file": fname,
                    "is_scan": is_scan,
                    "raw_text_method": "cached_txt",
                    "tingkat_source": "gemini_search" if "search" in var else "gemini_text",
                    "eval": eval_data,
                    "meta": meta,
                }

                cp_writer.write(json.dumps(rec, ensure_ascii=False) + "\n")
                cp_writer.flush()
                cached_records[key] = rec
                records_by_variant[var].append(rec)

    finally:
        cp_writer.close()

    # 6. Agregasi Metrik Terstratifikasi
    # (Unified N=104, Primary v9 N=74, Elzandi N=30)
    target_complete = all(
        len(records_by_variant[var]) == len(docs) for var in active_vars
    )
    summary_data: dict[str, Any] = {
        "metadata": {
            "campaign_id": "EXP-SEARCH-GROUNDING-CAMPAIGN-001",
            "experiment_id": "EXP-SEARCH-GROUNDING-001",
            "backend": backend,
            "model": gemini_model,
            "status": "STAGING_ONLY",
            "run_identity": run_identity["identity_sha256"],
            "timestamp": datetime.now().isoformat(),
            "total_docs": len(docs),
            "target_complete": target_complete,
        },
        "unified_104": {},
        "primary_v9": {},
        "elzandi_test": {},
    }

    for var in active_vars:
        all_recs = records_by_variant[var]
        v9_recs = [r for r in all_recs if r["dataset"] == "v9"]
        elz_recs = [r for r in all_recs if r["dataset"] in ("elzandi", "elzandi_test")]

        if len(docs) == 104:
            assert len(v9_recs) == 74, f"Expected 74 v9 docs, got {len(v9_recs)}"
            assert len(elz_recs) == 30, f"Expected 30 elzandi docs, got {len(elz_recs)}"

        summary_data["unified_104"][var] = aggregate_variant_metrics(all_recs)
        summary_data["primary_v9"][var] = aggregate_variant_metrics(v9_recs)
        summary_data["elzandi_test"][var] = aggregate_variant_metrics(elz_recs)
    # 7. Tulis JSON Metrics
    metrics_json_path = out_dir_path / "comparative_metrics.json"
    with open(metrics_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    # 8. Tulis CSV Detail Evaluasi
    eval_csv_path = out_dir_path / "evaluation_details.csv"
    with open(eval_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "variant",
            "dataset",
            "nama_file",
            "field",
            "gt_value",
            "pred_value",
            "exact_match",
            "fuzzy_match",
            "wer",
            "cer",
        ])
        for var in active_vars:
            for r in records_by_variant[var]:
                for fld in ALL_6_FIELDS:
                    fd = r["eval"][fld]
                    writer.writerow([
                        var,
                        r["dataset"],
                        r["nama_file"],
                        fld,
                        fd["gt"],
                        fd["pred"],
                        fd["exact"],
                        fd["fuzzy"],
                        fd["wer"],
                        fd["cer"],
                    ])

    # 9. Tulis Prompt Registry
    registry_path = out_dir_path / "PROMPT_REGISTRY.md"
    write_prompt_registry(registry_path, active_vars, gemini_model)

    # 10. Tulis Laporan Markdown
    summary_md_path = out_dir_path / "comparative_summary.md"
    write_markdown_report(summary_md_path, summary_data, active_vars)

    logger.info(f"Evaluasi selesai. Artefak tersimpan di: {out_dir_path}")
    return summary_data


def write_prompt_registry(out_path: Path, variants: list[str], model: str) -> None:
    """Tulis arsip template prompt resmi."""
    content = f"""# PROMPT REGISTRY: EXP-SEARCH-GROUNDING-001

Dokumentasi resmi prompt, system instruction, dan tool configuration untuk pengujian Google Search Grounding.
Model Target: `{model}` | Tanggal: {datetime.now().strftime("%Y-%m-%d")}

---

## 1. Varian V2 (Text-Mode Control vs Search)
Digunakan secara identik oleh:
- `v2_text_control` (Google Search OFF)
- `v2_search` (Google Search ON)

### System Instruction (V2 Pure)
````text
{V2_PURE_SYSTEM_INSTRUCTION}
````

### System Instruction (V2 Search Guided - Eksplorasi)
````text
{V2_SEARCH_GUIDED_SYSTEM_INSTRUCTION}
````

### User Prompt Template (V2)
````text
{V2_USER_PROMPT_TEMPLATE}
````

---

## 2. Varian V3 Search CoT (Decoupled Stage 2 + Search)

### Stage 1: System Instruction (5 Field Literal Faktual)
````text
{STAGE1_SYSTEM_INSTRUCTION}
````

### Stage 1: User Prompt Template
````text
{STAGE1_USER_PROMPT_TEMPLATE}
````

### Stage 2: System Instruction (Penalaran Tingkat Scope-Aware CoT + Search)
````text
{STAGE2_SEARCH_COT_SYSTEM_INSTRUCTION}
````

### Stage 2: User Prompt Template
````text
{STAGE2_SEARCH_COT_USER_PROMPT_TEMPLATE}
````
"""
    out_path.write_text(content, encoding="utf-8")


def write_markdown_report(out_path: Path, data: dict[str, Any], variants: list[str]) -> None:
    """Buat ringkasan laporan komparatif terstruktur."""
    u104 = data["unified_104"]
    v9 = data["primary_v9"]
    elz = data["elzandi_test"]

    lines = [
        "# Laporan Eksekutif: Evaluasi Efektivitas Google Search Grounding (EXP-SEARCH-GROUNDING-001)",
        "",
        f"**Tanggal Evaluasi**: {datetime.now().strftime('%d %B %Y')}  ",
        f"**Model Diuji**: `{data['metadata']['model']}`  ",
        f"**Total Dokumen**: {data['metadata']['total_docs']} Dokumen  ",
        "",
        "---",
        "",
        "## 1. Tabel Komparasi Utama: Unified Dataset ($N=104$)",
        "",
        "| Varian Arsitektur | All-Cells 6F (Exact / Fuzzy) | Framework 5F (Exact / Fuzzy) | Tingkat Exact | Nomor Exact | Nama Kegiatan | Penyelenggara | Web Queries | Total Calls | Biaya Token (IDR) |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for v in variants:
        m = u104.get(v, {})
        ac = m.get("all_cells_6f", {})
        fw = m.get("framework_5f", {})
        pf = m.get("per_field", {})
        tc = m.get("token_and_cost", {})

        ac_str = f"{ac.get('exact_pct', 0.0):.2f}% / {ac.get('fuzzy_pct', 0.0):.2f}%"
        fw_str = f"{fw.get('exact_pct', 0.0):.2f}% / {fw.get('fuzzy_pct', 0.0):.2f}%"
        tkt = f"{pf.get('tingkat', {}).get('exact_pct', 0.0):.2f}%"
        nom = f"{pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}%"
        keg = f"{pf.get('nama_kegiatan_sertifikasi', {}).get('exact_pct', 0.0):.2f}%"
        org = f"{pf.get('penyelenggara_kegiatan', {}).get('exact_pct', 0.0):.2f}%"
        q_cnt = tc.get("total_web_queries", 0)
        calls = tc.get("total_calls", 0)
        cost = f"Rp {tc.get('total_cost_idr', 0.0):,.2f}"

        lines.append(f"| **{v}** | {ac_str} | {fw_str} | {tkt} | {nom} | {keg} | {org} | {q_cnt} | {calls} | {cost} |")

    n_v9 = v9.get(variants[0], {}).get("n_docs", 0) if variants and variants[0] in v9 else 0
    n_elz = elz.get(variants[0], {}).get("n_docs", 0) if variants and variants[0] in elz else 0

    lines.extend([
        "",
        "---",
        "",
        f"## 2. Tabel Terstratifikasi: Primary v9 ($N={n_v9}$) vs Holdout Test Elzandi ($N={n_elz}$)",
        "",
        f"### 2.1 Primary Frozen Benchmark ($N={n_v9}$, Otoritatif `Ground_Truth_Sertifikat_v9.csv`)",
        "",
        "| Varian | All-Cells (Exact / Fuzzy) | Framework 5F | Tingkat | Nomor | Kegiatan | Penyelenggara | Web Queries |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])
    for v in variants:
        m = v9.get(v, {})
        ac = m.get("all_cells_6f", {})
        fw = m.get("framework_5f", {})
        pf = m.get("per_field", {})
        tc = m.get("token_and_cost", {})
        lines.append(
            f"| **{v}** | {ac.get('exact_pct', 0.0):.2f}% / {ac.get('fuzzy_pct', 0.0):.2f}% | "
            f"{fw.get('exact_pct', 0.0):.2f}% | {pf.get('tingkat', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nama_kegiatan_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('penyelenggara_kegiatan', {}).get('exact_pct', 0.0):.2f}% | "
            f"{tc.get('total_web_queries', 0)} |"
        )

    lines.extend([
        "",
        f"### 2.2 Auxiliary Holdout Test Set ($N={n_elz}$, Unseen Dokumen Elzandi)",
        "",
        "| Varian | All-Cells (Exact / Fuzzy) | Framework 5F | Tingkat | Nomor | Kegiatan | Penyelenggara | Web Queries |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for v in variants:
        m = elz.get(v, {})
        ac = m.get("all_cells_6f", {})
        fw = m.get("framework_5f", {})
        pf = m.get("per_field", {})
        tc = m.get("token_and_cost", {})
        lines.append(
            f"| **{v}** | {ac.get('exact_pct', 0.0):.2f}% / {ac.get('fuzzy_pct', 0.0):.2f}% | "
            f"{fw.get('exact_pct', 0.0):.2f}% | {pf.get('tingkat', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('nama_kegiatan_sertifikasi', {}).get('exact_pct', 0.0):.2f}% | "
            f"{pf.get('penyelenggara_kegiatan', {}).get('exact_pct', 0.0):.2f}% | "
            f"{tc.get('total_web_queries', 0)} |"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Google Search Grounding")
    parser.add_argument(
        "--manifest-path",
        default="certs_unified/manifest.json",
        help="Path ke manifest.json",
    )
    parser.add_argument(
        "--gt-unified-path",
        default="Ground_Truth_Unified.csv",
        help="Path ke Ground_Truth_Unified.csv",
    )
    parser.add_argument(
        "--gt-primary-path",
        default="Ground_Truth_Sertifikat_v9.csv",
        help="Path ke Ground_Truth_Sertifikat_v9.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/experiments/EXP-SEARCH-GROUNDING-001",
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
        default="v2_text_control,v2_search,v3_text_control,v3_search_cot",
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
        "--reuse-checkpoint",
        default=None,
        help="Path checkpoint lama untuk pre-load hasil",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Izinkan overwrite eksplisit pada folder output.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Lanjutkan checkpoint dengan identity yang sama.",
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

    args = parser.parse_args()
    var_list = [v.strip() for v in args.variants.split(",") if v.strip()]

    run_benchmark(
        manifest_path=args.manifest_path,
        gt_unified_path=args.gt_unified_path,
        force=args.force,
        resume=args.resume,
        gt_primary_path=args.gt_primary_path,
        output_dir=args.output_dir,
        backend=args.backend,
        gemini_model=args.gemini_model,
        variants=var_list,
        limit=args.limit,
        offset=args.offset,
        reuse_checkpoint=args.reuse_checkpoint,
        pacing_delay=args.pacing_delay,
        timeout_s=args.timeout_s,
    )


if __name__ == "__main__":
    main()
