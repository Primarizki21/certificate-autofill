"""Gemini Field Extractor & Schema Normalizer.

Takes raw OCR text from Tesseract, builds structured system instruction and prompt,
queries Gemini via GeminiClient, normalizes date and enum formats, and adapts
the output to `ExtractedValue` and `form_mapper.map_fields_to_form`.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from typing import Any

# Pastikan import module backend/app tersedia
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.master_data import FORM_OPTIONS
from app.services.field_extractor import ExtractedValue
from app.services.form_mapper import map_fields_to_form
from tests.gemini_client import GeminiCallResult, GeminiClient
from tests.matchers import normalize_date

# 6 Field Evaluasi Baku KHP
EVAL_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi",
]
ALL_EVAL_FIELDS = list(EVAL_FIELDS) + ["tingkat"]

VALID_TINGKAT_OPTIONS = set(FORM_OPTIONS.get("tingkat", [
    "Internasional",
    "Nasional",
    "Universitas",
    "Fakultas",
    "Departemen/Program Studi",
    "Lainnya",
]))

SYSTEM_INSTRUCTION_STANDARD = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
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

USER_PROMPT_TEMPLATE = """Berikut adalah teks OCR mentah dari sebuah dokumen sertifikat:
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

MONTH_NAME_MAP = {
    "januari": "01", "january": "01", "jan": "01",
    "februari": "02", "february": "02", "feb": "02",
    "maret": "03", "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "mei": "05", "may": "05",
    "juni": "06", "june": "06", "jun": "06",
    "juli": "07", "july": "07", "jul": "07",
    "agustus": "08", "august": "08", "aug": "08",
    "september": "09", "sep": "09",
    "oktober": "10", "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "desember": "12", "december": "12", "dec": "12",
}


def standardize_date(date_str: str | None) -> str | None:
    """Standardisasi string tanggal ke format 'DD/MM/YYYY' untuk Matcher v2."""
    if not date_str or not isinstance(date_str, str):
        return None

    raw = date_str.strip()
    if not raw or raw.lower() in ("null", "none", "-", ""):
        return None

    # 1. Coba matcher v2 normalize_date terlebih dahulu
    try:
        norm = normalize_date(raw)
        if norm and re.match(r"^\d{2}/\d{2}/\d{4}$", norm):
            return norm
    except Exception:
        pass

    # 2. Tangani format ISO YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", raw)
    if m_iso:
        yyyy, mm, dd = m_iso.groups()
        return f"{int(dd):02d}/{int(mm):02d}/{yyyy}"

    # 3. Tangani format DD-MM-YYYY atau DD/MM/YYYY
    m_dmy = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", raw)
    if m_dmy:
        dd, mm, yyyy = m_dmy.groups()
        return f"{int(dd):02d}/{int(mm):02d}/{yyyy}"

    # 4. Tangani format tekstual "24 Agustus 2024" atau "September 23, 2024"
    # Pola: Day Month Year
    m_text = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m_text:
        dd, m_name, yyyy = m_text.groups()
        mm = MONTH_NAME_MAP.get(m_name.lower())
        if mm:
            return f"{int(dd):02d}/{mm}/{yyyy}"

    # Pola: Month Day Year
    m_text2 = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(\d{4})", raw)
    if m_text2:
        m_name, dd, yyyy = m_text2.groups()
        mm = MONTH_NAME_MAP.get(m_name.lower())
        if mm:
            return f"{int(dd):02d}/{mm}/{yyyy}"

    return raw


def normalize_llm_json(data: dict[str, Any] | None) -> dict[str, str | None]:
    """Normalisasi dictionary JSON hasil ekstraksi LLM."""
    out: dict[str, str | None] = {
        "nama_kegiatan_sertifikasi": None,
        "nomor_bukti_fisik_nomor_sertifikasi": None,
        "penyelenggara_kegiatan": None,
        "waktu_mulai_pelaksanaan": None,
        "waktu_selesai_pelaksanaan": None,
        "tingkat": None,
        "raw_role": None,
    }

    if not data or not isinstance(data, dict):
        return out

    # Bersihkan string fields
    for k in ("nama_kegiatan_sertifikasi", "nomor_bukti_fisik_nomor_sertifikasi", "penyelenggara_kegiatan", "raw_role"):
        val = data.get(k)
        if val is not None and isinstance(val, str):
            s = val.strip()
            if s and s.lower() not in ("null", "none", "-", ""):
                out[k] = s

    # Normalisasi tanggal
    t_mulai = standardize_date(data.get("waktu_mulai_pelaksanaan"))
    t_selesai = standardize_date(data.get("waktu_selesai_pelaksanaan"))

    # Jika hanya ada salah satu tanggal, samakan mulai & selesai
    if t_mulai and not t_selesai:
        t_selesai = t_mulai
    elif t_selesai and not t_mulai:
        t_mulai = t_selesai

    out["waktu_mulai_pelaksanaan"] = t_mulai
    out["waktu_selesai_pelaksanaan"] = t_selesai

    # Normalisasi tingkat
    tingkat_raw = data.get("tingkat")
    if tingkat_raw and isinstance(tingkat_raw, str):
        t_clean = tingkat_raw.strip()
        # Cari exact match atau case-insensitive match pada VALID_TINGKAT_OPTIONS
        matched_tingkat = None
        for opt in VALID_TINGKAT_OPTIONS:
            if opt.lower() == t_clean.lower():
                matched_tingkat = opt
                break
        if matched_tingkat:
            out["tingkat"] = matched_tingkat
        else:
            # Fallback jika mirip
            t_low = t_clean.lower()
            if "internasional" in t_low or "international" in t_low:
                out["tingkat"] = "Internasional"
            elif "nasional" in t_low or "national" in t_low:
                out["tingkat"] = "Nasional"
            elif "prodi" in t_low or "departemen" in t_low or "department" in t_low or "study program" in t_low:
                out["tingkat"] = "Departemen/Program Studi"
            elif "fakultas" in t_low or "faculty" in t_low:
                out["tingkat"] = "Fakultas"
            elif "universitas" in t_low or "university" in t_low:
                out["tingkat"] = "Universitas"
            else:
                out["tingkat"] = "Lainnya"

    return out


def llm_json_to_extracted_values(
    norm_data: dict[str, str | None],
    raw_ocr_text: str,
    confidence_default: float = 0.90,
) -> dict[str, ExtractedValue]:
    """Konversi dict JSON normal ke dict[str, ExtractedValue].

    CRITICAL FIX (Advisory & Flaw 9): Menginjeksi `extracted["full_text"] = raw_ocr_text`
    agar form_mapper dapat memetakan kelompok_kegiatan, jenis_kegiatan, dan jenis_penyelenggara.
    """
    extracted: dict[str, ExtractedValue] = {}

    # Injeksi full_text mentah untuk form_mapper
    extracted["full_text"] = ExtractedValue(
        value=raw_ocr_text,
        confidence=1.0,
        source="tesseract_raw",
    )

    for field_name in (
        "nama_kegiatan_sertifikasi",
        "nomor_bukti_fisik_nomor_sertifikasi",
        "penyelenggara_kegiatan",
        "waktu_mulai_pelaksanaan",
        "waktu_selesai_pelaksanaan",
        "tingkat",
        "raw_role",
    ):
        val = norm_data.get(field_name)
        if val:
            extracted[field_name] = ExtractedValue(
                value=val,
                confidence=confidence_default,
                source="gemini_llm",
            )
        else:
            extracted[field_name] = ExtractedValue(
                value=None,
                confidence=0.0,
                source="gemini_llm",
            )

    return extracted


def extract_fields_from_ocr(
    raw_ocr_text: str,
    client: GeminiClient,
    model: str | None = None,
    temperature: float = 0.0,
    tahun_akademik: str = "2024/2025",
    bukti_fisik: str = "Sertifikat",
) -> tuple[dict[str, ExtractedValue], GeminiCallResult]:
    """Ekstraksi teks OCR sertifikat via Gemini LLM lalu petakan ke form KHP produksi."""
    prompt = USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_ocr_text)

    call_result = client.generate_json(
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION_STANDARD,
        model=model,
        temperature=temperature,
    )

    norm_json = normalize_llm_json(call_result.parsed_json)
    extracted_values = llm_json_to_extracted_values(norm_json, raw_ocr_text)

    # Proses via form_mapper produksi
    mapped_form = map_fields_to_form(
        extracted_values,
        tahun_akademik=tahun_akademik,
        bukti_fisik=bukti_fisik,
    )

    return mapped_form, call_result
