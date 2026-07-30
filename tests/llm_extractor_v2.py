import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any

from tests.llm_extractor import (
    OLLAMA_BASE,
    DEFAULT_MODEL,
    MAX_RETRIES,
    RETRY_DELAY_S,
    TINGKAT_OPTIONS,
    TINGKAT_GT_MAP,
    validate_tingkat,
    validate_free_text,
    call_ollama,
    log_call,
    build_token_usage_summary,
    TokenUsage,
)

PROMPT_VERSION = "v2_fulltext"

# Field names in the LLM output
FIELD_MAP = {
    "tingkat": "tingkat",
    "nama_kegiatan": "nama_kegiatan_sertifikasi",
    "penyelenggara": "penyelenggara_kegiatan",
    "waktu_mulai": "waktu_mulai_pelaksanaan",
    "waktu_selesai": "waktu_selesai_pelaksanaan",
    "nomor_bukti": "nomor_bukti_fisik_nomor_sertifikasi",
}

# Aliases for flexible parsing
FIELD_ALIASES = {
    k.replace("_", ""): k for k in FIELD_MAP
}
for k in FIELD_MAP:
    FIELD_ALIASES[k.upper()] = k
    FIELD_ALIASES[k.lower()] = k
    FIELD_ALIASES[k.replace("_", " ")] = k
FIELD_ALIASES["nama kegiatan"] = "nama_kegiatan"
FIELD_ALIASES["nama acara"] = "nama_kegiatan"
FIELD_ALIASES["certificate number"] = "nomor_bukti"
FIELD_ALIASES["nomor"] = "nomor_bukti"
FIELD_ALIASES["no"] = "nomor_bukti"
FIELD_ALIASES["waktu mulai"] = "waktu_mulai"
FIELD_ALIASES["waktu selesai"] = "waktu_selesai"
FIELD_ALIASES["tanggal mulai"] = "waktu_mulai"
FIELD_ALIASES["tanggal selesai"] = "waktu_selesai"
FIELD_ALIASES["start date"] = "waktu_mulai"
FIELD_ALIASES["end date"] = "waktu_selesai"
FIELD_ALIASES["tingkat kegiatan"] = "tingkat"
FIELD_ALIASES["level"] = "tingkat"
FIELD_ALIASES["organizer"] = "penyelenggara"
FIELD_ALIASES["penyelenggara kegiatan"] = "penyelenggara"
FIELD_ALIASES["activity name"] = "nama_kegiatan"
FIELD_ALIASES["event name"] = "nama_kegiatan"


def build_prompt_v2(raw_text: str) -> str:
    option_lines = "\n".join(f"   - {o}" for o in TINGKAT_OPTIONS)
    lines = [
        "Dari sertifikat berikut, ekstrak semua field yang diperlukan.",
        "",
        "ATURAN WAJIB:",
        "- Jawaban HANYA format \"field: nilai\" (satu field per baris)",
        "- Setiap field harus dijawab, jangan ada yang dilewati",
        "- Jika field tidak ditemukan, tulis: field: TIDAK_DITEMUKAN",
        "- Jangan tambahkan penjelasan, hanya field dan nilai",
        "- Format tanggal: DD/MM/YYYY",
        "",
        "Field yang perlu diekstrak:",
        "1. tingkat: (pilih salah satu dari daftar ini)",
        option_lines,
        "2. nama_kegiatan: (nama acara/kegiatan, maks 100 karakter)",
        "3. penyelenggara: (organisasi/panitia penyelenggara, maks 100 karakter)",
        "4. waktu_mulai: (tanggal mulai, format DD/MM/YYYY)",
        "5. waktu_selesai: (tanggal selesai, format DD/MM/YYYY)",
        "6. nomor_bukti: (nomor sertifikat/bukti)",
        "",
        "Teks sertifikat:",
        raw_text,
        "",
        "Jawaban:",
    ]
    return "\n".join(lines)


def parse_llm_response(response: str) -> dict[str, str]:
    results = {}
    for line in response.strip().split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key_raw, value = line.split(":", 1)
        key_raw = key_raw.strip().lower()
        key_raw = re.sub(r"^\d+[\.\)]?\s*", "", key_raw)
        value = value.strip().rstrip(",")

        alias_key = FIELD_ALIASES.get(key_raw)
        if alias_key is None:
            compact = key_raw.replace(" ", "").replace("_", "").replace("-", "")
            alias_key = FIELD_ALIASES.get(compact)
        if alias_key is None:
            for lookup, alias in FIELD_ALIASES.items():
                if isinstance(lookup, str) and lookup.replace(" ", "").replace("_", "") == compact:
                    alias_key = alias
                    break
        if alias_key is None:
            alias_key = FIELD_ALIASES.get(key_raw.replace("_", ""))
        if alias_key is None:
            continue

        if alias_key not in results:
            results[alias_key] = value
    return results


def extract_field_date(line_value: str) -> str | None:
    clean = line_value.strip().rstrip(".")
    if clean.upper() in ("TIDAK_DITEMUKAN", "NOT FOUND", "NONE", "UNKNOWN"):
        return None
    if not clean:
        return None
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", clean):
        parts = clean.split("/")
        return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"
    if re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", clean):
        parts = clean.split("-")
        return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"
    return None


def extract_field_nomor(line_value: str) -> str | None:
    clean = line_value.strip().rstrip(".")
    if clean.upper() in ("TIDAK_DITEMUKAN", "NOT FOUND", "NONE", "UNKNOWN", "-"):
        return None
    if not clean or len(clean) < 3:
        return None
    clean_compact = re.sub(r"\s+", "", clean)
    return clean_compact[:100]


def parse_and_validate(response: str) -> dict[str, str]:
    parsed = parse_llm_response(response)
    validated = {}
    for alias, gt_key in FIELD_MAP.items():
        raw_value = parsed.get(alias)
        if raw_value is None:
            continue
        if alias == "tingkat":
            val = validate_tingkat(raw_value)
            if val:
                validated[gt_key] = val
        elif alias in ("waktu_mulai", "waktu_selesai"):
            val = extract_field_date(raw_value)
            if val:
                validated[gt_key] = val
        elif alias == "nomor_bukti":
            val = extract_field_nomor(raw_value)
            if val:
                validated[gt_key] = val
        else:
            val = validate_free_text(raw_value)
            if val:
                validated[gt_key] = val
    return validated
