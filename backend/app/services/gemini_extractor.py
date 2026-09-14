"""Production service for Tesseract-to-Gemini Scope-Aware extraction.

Extracts structured certificate metadata directly from raw OCR text using Google Gemini
with the promoted V2 scope rules, strict JSON generationConfig, deterministic temperature
0.0, date standardization, and mandatory full_text injection for form_mapper compatibility.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Collection
from typing import Any

from app.config import settings
from app.master_data import FORM_OPTIONS, KHP_TINGKAT_LABELS
from app.services.field_extractor import ExtractedValue

logger = logging.getLogger(__name__)
_MODEL_PRICING: dict[str, tuple[float, float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50, 0.03),
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.01),
    "gemini-3.1-flash-lite": (0.25, 1.50, 0.025),
}
_DEFAULT_EXCHANGE_RATE_IDR = 17758.0


def _usage_int(usage: dict[str, Any], key: str) -> int:
    try:
        return max(0, int(usage.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _calculate_cost(
    model: str,
    prompt_tokens: int,
    candidates_tokens: int,
    cached_tokens: int,
    thoughts_tokens: int,
) -> tuple[float, float]:
    input_rate, output_rate, cache_rate = _MODEL_PRICING.get(
        model, _MODEL_PRICING["gemini-2.5-flash"]
    )
    try:
        exchange_rate = float(
            os.getenv("EXCHANGE_RATE_IDR_PER_USD", str(_DEFAULT_EXCHANGE_RATE_IDR))
        )
    except ValueError:
        exchange_rate = _DEFAULT_EXCHANGE_RATE_IDR
    cost_usd = (
        (prompt_tokens * input_rate)
        + ((candidates_tokens + thoughts_tokens) * output_rate)
        + (cached_tokens * cache_rate)
    ) / 1_000_000.0
    return round(cost_usd, 6), round(cost_usd * exchange_rate, 2)


def _build_telemetry(
    *,
    model: str,
    status: str,
    latency_s: float,
    fallback_reason: str | None = None,
    prompt_tokens: int = 0,
    candidates_tokens: int = 0,
    cached_tokens: int = 0,
    thoughts_tokens: int = 0,
    total_tokens: int = 0,
    calls_count: int = 0,
    error_type: str | None = None,
) -> dict[str, Any]:
    total = total_tokens or (
        prompt_tokens + candidates_tokens + thoughts_tokens
    )
    cost_usd, cost_idr = _calculate_cost(
        model,
        prompt_tokens,
        candidates_tokens,
        cached_tokens,
        thoughts_tokens,
    )
    detail = {
        "stage": "gemini_extract",
        "status": status,
        "fallback_reason": fallback_reason,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "candidates_tokens": candidates_tokens,
        "cached_tokens": cached_tokens,
        "thoughts_tokens": thoughts_tokens,
        "total_tokens": total,
        "cost_usd": cost_usd,
        "cost_idr": cost_idr,
        "latency_s": round(latency_s, 4),
        "web_search_queries": [],
        "error": error_type,
    }
    return {
        "status": status,
        "gemini_status": status,
        "model": model,
        "fallback_reason": fallback_reason,
        "error_fallback": status != "success",
        "error": error_type,
        "error_type": error_type,
        "latency_s": round(latency_s, 4),
        "prompt_tokens": prompt_tokens,
        "candidates_tokens": candidates_tokens,
        "cached_tokens": cached_tokens,
        "thoughts_tokens": thoughts_tokens,
        "total_tokens": total,
        "cost_usd": cost_usd,
        "cost_idr": cost_idr,
        "calls_count": calls_count,
        "web_search_queries": [],
        "calls_details": [detail] if calls_count else [],
    }


def _log_telemetry(meta: dict[str, Any], level: int = logging.INFO) -> None:
    logger.log(
        level,
        (
            "Gemini extraction status=%s model=%s fallback_reason=%s "
            "latency_s=%.4f calls_count=%d prompt_tokens=%d "
            "candidates_tokens=%d cached_tokens=%d thoughts_tokens=%d "
            "total_tokens=%d cost_usd=%.6f cost_idr=%.2f error_type=%s"
        ),
        meta.get("status", "unknown"),
        meta.get("model", "unknown"),
        meta.get("fallback_reason"),
        float(meta.get("latency_s", 0.0) or 0.0),
        int(meta.get("calls_count", 0) or 0),
        int(meta.get("prompt_tokens", 0) or 0),
        int(meta.get("candidates_tokens", 0) or 0),
        int(meta.get("cached_tokens", 0) or 0),
        int(meta.get("thoughts_tokens", 0) or 0),
        int(meta.get("total_tokens", 0) or 0),
        float(meta.get("cost_usd", 0.0) or 0.0),
        float(meta.get("cost_idr", 0.0) or 0.0),
        meta.get("error_type"),
    )


def _error_meta(
    *,
    model: str,
    started_at: float,
    status: str,
    fallback_reason: str,
    error_type: str,
) -> dict[str, Any]:
    meta = _build_telemetry(
        model=model,
        status=status,
        latency_s=time.perf_counter() - started_at,
        fallback_reason=fallback_reason,
        calls_count=1,
        error_type=error_type,
    )
    _log_telemetry(meta, logging.WARNING)
    return meta


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
KHP_STAGING_SYSTEM_INSTRUCTION = f"""Anda adalah ekstraktor fakta sertifikat untuk staging KHP yang memakai master data resmi.
Ekstrak hanya teks OCR. Jangan mengarang nilai atau mengubah nama kegiatan bebas.

Tanggal harus "DD/MM/YYYY" atau null. Nomor sertifikat harus dipertahankan utuh.
Penyelenggara hanya organisasi atau institusi, bukan nama penerima atau penandatangan.
Untuk tingkat, pilih tepat satu label master berdasarkan cakupan yang tertulis:
[{", ".join(repr(label) for label in KHP_TINGKAT_LABELS)}].
Jangan mengganti tingkat UKM dengan Universitas atau Lainnya bila teks menyebut UKM secara eksplisit.
raw_role harus memuat peran atau capaian faktual selengkap yang tertulis, misalnya "Juara II",
"Peserta Terpilih", "Pembicara", "Panitia", atau "Brevet A/B/C". Jika tidak tertulis, isi null.

Untuk jenis_kegiatan, pilih label kegiatan resmi berikut yang paling sesuai jika teridentifikasi jelas:
- Kepanitiaan -> 'Panitia Dalam Suatu Kegiatan Kemahasiswaan'
- Peserta Lomba/Kompetisi ilmiah -> 'Mengikuti Kegiatan Lomba Ilmiah'
- Prestasi/Juara Lomba ilmiah -> 'Memperoleh prestasi dalam Lomba Karya Tulis Ilmiah/Lingkungan Hidup/Kreativitas/Inovatif/Pemikiran Kritis/Populer/Entrepreneurship/Business Plan'
- Seminar/Workshop/Webinar/Lokakarya/Forum Ilmiah -> 'Mengikuti kegiatan/forum ilmiah (seminar, lokakarya, workshop, pameran)'
- Kuliah Tamu -> 'Mengikuti kuliah tamu'
- Sertifikasi Kompetensi/Profesi -> 'Mengikuti Kegiatan Sertifikasi'
- PKKMB -> 'PKKMB'
- KKN -> 'KKN-BBM'
- Kepengurusan Organisasi/BEM/HIMA -> 'Pengurus Organisasi'
- Anggota Organisasi -> 'Anggota Aktif Organisasi'
- Pelatihan Kepemimpinan -> 'Mengikuti Pelatihan Kepemimpinan LKMM' atau 'Latihan Kepemimpinan Lainnya'
- Bakti Sosial -> 'Mengikuti Pelaksanaan Bakti Sosial'
- Kegiatan Minat/Bakat/Olahraga/Seni -> 'Mengikuti kegiatan Minat dan Bakat (Olahraga, Seni dan Kerohanian)' atau 'Memperoleh prestasi dalam kegiatan Minat dan Bakat (Olahraga, Seni,Kerohanian dan IT)'
- Magang -> 'Magang Kerja' atau 'Magang UKM'
Jika tidak yakin atau belum jelas, isi null.
"""

KHP_STAGING_USER_PROMPT_TEMPLATE = f"""Berikut teks OCR mentah dokumen sertifikat:
--- TEKS OCR AWAL ---
{{raw_ocr_text}}
--- TEKS OCR AKHIR ---

Ekstrak 8 field berikut dalam format JSON. Field tingkat wajib memakai enum master berikut:
[{", ".join(repr(label) for label in KHP_TINGKAT_LABELS)}].
{{{{
  "nama_kegiatan_sertifikasi": string atau null,
  "nomor_bukti_fisik_nomor_sertifikasi": string atau null,
  "penyelenggara_kegiatan": string atau null,
  "waktu_mulai_pelaksanaan": "DD/MM/YYYY" atau null,
  "waktu_selesai_pelaksanaan": "DD/MM/YYYY" atau null,
  "tingkat": string dari enum master atau null,
  "raw_role": string atau null,
  "jenis_kegiatan": string kategori resmi atau null
}}}}
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


def normalize_llm_json(
    data: dict[str, Any] | None,
    *,
    valid_tingkat_options: Collection[str] | None = None,
) -> dict[str, str | None]:
    """Normalisasi dictionary JSON hasil ekstraksi LLM."""
    out: dict[str, str | None] = {
        "nama_kegiatan_sertifikasi": None,
        "nomor_bukti_fisik_nomor_sertifikasi": None,
        "penyelenggara_kegiatan": None,
        "waktu_mulai_pelaksanaan": None,
        "waktu_selesai_pelaksanaan": None,
        "tingkat": None,
        "raw_role": None,
        "jenis_kegiatan": None,
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
        valid_options = tuple(
            VALID_TINGKAT_OPTIONS
            if valid_tingkat_options is None
            else valid_tingkat_options
        )
        matched = None
        for opt in valid_options:
            if opt.lower() == t_clean.lower():
                matched = opt
                break
        if matched:
            out["tingkat"] = matched
        elif valid_tingkat_options is not None:
            t_low = t_clean.lower()
            stage_fallbacks = (
                (
                    r"nasional\s+tidak\s+ter[\s-]?\s*akreditasi|"
                    r"national\s+not[\s-]?\s*accredited|"
                    r"non[\s-]?\s*accredited\s+national",
                    "Nasional Tidak Ter-Akreditasi",
                ),
                (
                    r"nasional\s+ter[\s-]?\s*akreditasi|"
                    r"accredited\s+national",
                    "Nasional Ter-Akreditasi",
                ),
                (r"internasional|international", "Internasional"),
                (r"regional", "Regional"),
                (r"departemen|department|prodi|study program", "Departemen/Program Studi"),
                (r"fakultas|faculty", "Fakultas"),
                (r"universitas|university", "Universitas"),
                (r"\bukm\b|unit kegiatan mahasiswa|student activity unit", "UKM"),
                (r"nasional|national", "Nasional"),
                (r"lanjut|advanced", "Lanjut"),
                (r"menengah|intermediate", "Menengah"),
                (r"dasar|basic", "Dasar"),
            )
            for pattern, label in stage_fallbacks:
                if re.search(pattern, t_low) and label in valid_options:
                    out["tingkat"] = label
                    break
            else:
                out["tingkat"] = "Lainnya"
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

    jenis_raw = data.get("jenis_kegiatan")
    if jenis_raw and isinstance(jenis_raw, str):
        j_clean = jenis_raw.strip()
        if j_clean.lower() not in ("null", "none", "-", ""):
            from app.master_data import KHP_ACTIVITY_MASTER
            canonical_labels = {item[1] for item in KHP_ACTIVITY_MASTER}
            matched_j = next(
                (lbl for lbl in canonical_labels if lbl.lower() == j_clean.lower()),
                None,
            )
            out["jenis_kegiatan"] = matched_j or j_clean

    return out


def extract_fields_with_gemini(
    raw_ocr_text: str,
    api_key: str | None = None,
    model: str | None = None,
    timeout_s: float | None = None,
    khp_master_staging: bool = False,
) -> tuple[dict[str, ExtractedValue] | None, dict[str, Any]]:
    """Ekstraksi teks mentah via Gemini REST API tanpa mencatat isi dokumen."""
    target_model = model or settings.google_gemini_model
    effective_key = api_key or settings.google_api_key
    if not effective_key:
        meta = _build_telemetry(
            model=target_model,
            status="skipped",
            latency_s=0.0,
            fallback_reason="missing_api_key",
            calls_count=0,
            error_type="MissingApiKey",
        )
        meta["error"] = "GOOGLE_API_KEY tidak dikonfigurasi"
        _log_telemetry(meta)
        return None, meta

    effective_timeout = (
        settings.gemini_timeout_seconds if timeout_s is None else timeout_s
    )
    endpoint_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
    )
    prompt_template = (
        KHP_STAGING_USER_PROMPT_TEMPLATE
        if khp_master_staging
        else USER_PROMPT_TEMPLATE
    )
    system_instruction = (
        KHP_STAGING_SYSTEM_INSTRUCTION
        if khp_master_staging
        else SYSTEM_INSTRUCTION
    )
    prompt = prompt_template.format(raw_ocr_text=raw_ocr_text)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
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
            raw_body = resp.read().decode("utf-8")
            res_json = json.loads(raw_body)
            usage = res_json.get("usageMetadata") or {}
            prompt_tokens = _usage_int(usage, "promptTokenCount")
            candidates_tokens = _usage_int(usage, "candidatesTokenCount")
            cached_tokens = _usage_int(usage, "cachedContentTokenCount")
            thoughts_tokens = _usage_int(usage, "thoughtsTokenCount")
            total_tokens = _usage_int(usage, "totalTokenCount") or (
                prompt_tokens + candidates_tokens + thoughts_tokens
            )

            cand_text = ""
            candidates = res_json.get("candidates") or []
            if candidates:
                cand_text = (
                    candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                )
            cleaned_json_text = clean_json_markdown(cand_text)
            parsed_data = json.loads(cleaned_json_text)
            norm_data = normalize_llm_json(
                parsed_data,
                valid_tingkat_options=(
                    KHP_TINGKAT_LABELS if khp_master_staging else None
                ),
            )

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
            if khp_master_staging and norm_data.get("jenis_kegiatan"):
                extracted["jenis_kegiatan"] = ExtractedValue(
                    norm_data["jenis_kegiatan"], 0.90, "gemini_llm"
                )

            meta = _build_telemetry(
                model=target_model,
                status="success",
                latency_s=time.perf_counter() - t_start,
                prompt_tokens=prompt_tokens,
                candidates_tokens=candidates_tokens,
                cached_tokens=cached_tokens,
                thoughts_tokens=thoughts_tokens,
                total_tokens=total_tokens,
                calls_count=1,
            )
            _log_telemetry(meta)
            return extracted, meta
    except urllib.error.HTTPError as exc:
        reason = "rate_limited" if exc.code == 429 else "http_error"
        status = "rate_limited" if exc.code == 429 else "error"
        return None, _error_meta(
            model=target_model,
            started_at=t_start,
            status=status,
            fallback_reason=reason,
            error_type=f"HTTPError_{exc.code}",
        )
    except urllib.error.URLError as exc:
        return None, _error_meta(
            model=target_model,
            started_at=t_start,
            status="error",
            fallback_reason="network_error",
            error_type=type(exc).__name__,
        )
    except json.JSONDecodeError as exc:
        return None, _error_meta(
            model=target_model,
            started_at=t_start,
            status="error",
            fallback_reason="invalid_response",
            error_type=type(exc).__name__,
        )
    except (TypeError, ValueError) as exc:
        return None, _error_meta(
            model=target_model,
            started_at=t_start,
            status="error",
            fallback_reason="invalid_response",
            error_type=type(exc).__name__,
        )
    except Exception as exc:
        return None, _error_meta(
            model=target_model,
            started_at=t_start,
            status="error",
            fallback_reason="unexpected_error",
            error_type=type(exc).__name__,
        )
