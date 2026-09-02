"""Production service for Tesseract-to-Gemini Direct Extraction (Option A).

Extracts structured certificate metadata directly from raw OCR text using Google Gemini
with strict JSON generationConfig, deterministic temperature 0.0, date standardization,
and mandatory full_text injection for form_mapper compatibility.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from app.config import settings
from app.master_data import FORM_OPTIONS
from app.services.field_extractor import ExtractedValue

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """Anda adalah asisten ekstraksi data sertifikat akademik resmi untuk pengisian form Kartu Hasil Prestasi (KHP).
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

VALID_TINGKAT_OPTIONS = set(FORM_OPTIONS.get("tingkat", [
    "Internasional",
    "Nasional",
    "Universitas",
    "Fakultas",
    "Departemen/Program Studi",
    "Lainnya",
]))

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


def clean_json_markdown(text: str) -> str:
    """Bersihkan markdown code block jika model membungkus respons dengan ```json ... ```."""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if match:
        return match.group(1).strip()
    return stripped


def standardize_date(date_str: str | None) -> str | None:
    """Standardisasi tanggal ke 'DD/MM/YYYY'."""
    if not date_str or not isinstance(date_str, str):
        return None

    raw = date_str.strip()
    if not raw or raw.lower() in ("null", "none", "-", ""):
        return None

    m_iso = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", raw)
    if m_iso:
        yyyy, mm, dd = m_iso.groups()
        return f"{int(dd):02d}/{int(mm):02d}/{yyyy}"

    m_dmy = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", raw)
    if m_dmy:
        dd, mm, yyyy = m_dmy.groups()
        return f"{int(dd):02d}/{int(mm):02d}/{yyyy}"

    m_text = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m_text:
        dd, m_name, yyyy = m_text.groups()
        mm = MONTH_NAME_MAP.get(m_name.lower())
        if mm:
            return f"{int(dd):02d}/{mm}/{yyyy}"

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

    for k in ("nama_kegiatan_sertifikasi", "nomor_bukti_fisik_nomor_sertifikasi", "penyelenggara_kegiatan", "raw_role"):
        val = data.get(k)
        if val is not None and isinstance(val, str):
            s = val.strip()
            if s and s.lower() not in ("null", "none", "-", ""):
                out[k] = s

    t_mulai = standardize_date(data.get("waktu_mulai_pelaksanaan"))
    t_selesai = standardize_date(data.get("waktu_selesai_pelaksanaan"))

    if t_mulai and not t_selesai:
        t_selesai = t_mulai
    elif t_selesai and not t_mulai:
        t_mulai = t_selesai

    out["waktu_mulai_pelaksanaan"] = t_mulai
    out["waktu_selesai_pelaksanaan"] = t_selesai

    tingkat_raw = data.get("tingkat")
    if tingkat_raw and isinstance(tingkat_raw, str):
        t_clean = tingkat_raw.strip()
        matched = None
        for opt in VALID_TINGKAT_OPTIONS:
            if opt.lower() == t_clean.lower():
                matched = opt
                break
        if matched:
            out["tingkat"] = matched
        else:
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


def extract_fields_with_gemini(
    raw_ocr_text: str,
    api_key: str | None = None,
    model: str | None = None,
    timeout_s: float | None = None,
) -> tuple[dict[str, ExtractedValue] | None, dict[str, Any]]:
    """Ekstraksi teks mentah via Gemini REST API.

    Returns:
        (extracted_dict, metadata_dict)
        Jika gagal atau API key hilang, mengembalikan (None, {"error": ...})
        sehingga pipeline produksi dapat melakukan graceful fallback tanpa crash.
    """
    effective_key = api_key or settings.google_api_key
    if not effective_key:
        return None, {"error": "GOOGLE_API_KEY tidak dikonfigurasi"}

    target_model = model or settings.google_gemini_model
    effective_timeout = timeout_s or settings.gemini_timeout_seconds

    endpoint_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
    )

    prompt = USER_PROMPT_TEMPLATE.format(raw_ocr_text=raw_ocr_text)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": effective_key,
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint_url, data=data_bytes, headers=headers)

    t_start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
            latency = time.perf_counter() - t_start
            raw_body = resp.read().decode("utf-8")
            res_json = json.loads(raw_body)

            cand_text = ""
            candidates = res_json.get("candidates") or []
            if candidates:
                cand_text = (
                    candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                )

            cleaned_json_text = clean_json_markdown(cand_text)
            parsed_data = json.loads(cleaned_json_text)
            norm_data = normalize_llm_json(parsed_data)

            # Injeksi full_text untuk form_mapper produksi
            extracted: dict[str, ExtractedValue] = {
                "full_text": ExtractedValue(raw_ocr_text, 1.0, "tesseract_raw"),
            }

            for fld in (
                "nama_kegiatan_sertifikasi",
                "nomor_bukti_fisik_nomor_sertifikasi",
                "penyelenggara_kegiatan",
                "waktu_mulai_pelaksanaan",
                "waktu_selesai_pelaksanaan",
                "tingkat",
                "raw_role",
            ):
                val = norm_data.get(fld)
                if val:
                    extracted[fld] = ExtractedValue(val, 0.90, "gemini_llm")
                else:
                    extracted[fld] = ExtractedValue(None, 0.0, "gemini_llm")

            usage = res_json.get("usageMetadata") or {}
            meta = {
                "status": "success",
                "model": target_model,
                "latency_s": round(latency, 3),
                "total_tokens": usage.get("totalTokenCount", 0),
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "candidates_tokens": usage.get("candidatesTokenCount", 0),
            }
            return extracted, meta

    except Exception as e:
        latency = time.perf_counter() - t_start
        err_str = str(e)
        if effective_key and effective_key in err_str:
            err_str = err_str.replace(effective_key, "[REDACTED_API_KEY]")
        logger.warning(f"Gemini extraction failed ({latency:.2f}s): {err_str}")
        return None, {
            "status": "error",
            "model": target_model,
            "latency_s": round(latency, 3),
            "error": err_str,
        }
