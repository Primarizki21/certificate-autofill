"""Integration & regression tests for production Jenis Penyelenggara extraction pipeline."""

import pytest
from app.services.field_extractor import ExtractedValue
from app.services.form_mapper import map_fields_to_form, map_jenis_penyelenggara
from app.services.gemini_extractor import (
    KHP_JENIS_PENYELENGGARA_OPTIONS,
    normalize_llm_json,
)


def test_normalize_llm_json_includes_jenis_penyelenggara():
    raw_data = {
        "nama_kegiatan_sertifikasi": "Data Science Competition",
        "nomor_bukti_fisik_nomor_sertifikasi": "123/IT3/2025",
        "penyelenggara_kegiatan": "IPB University",
        "jenis_penyelenggara": "PTN di Indonesia",
        "tingkat": "Nasional",
    }
    normalized = normalize_llm_json(raw_data)
    assert normalized["jenis_penyelenggara"] == "PTN di Indonesia"
    assert normalized["tingkat"] == "Nasional"


def test_normalize_llm_json_fuzzy_variations():
    assert normalize_llm_json({"jenis_penyelenggara": "ptn"})["jenis_penyelenggara"] == "PTN di Indonesia"
    assert normalize_llm_json({"jenis_penyelenggara": "swasta"})["jenis_penyelenggara"] == "PTS di Indonesia"
    assert normalize_llm_json({"jenis_penyelenggara": "luar negeri"})["jenis_penyelenggara"] == "PT di luar negeri"
    assert normalize_llm_json({"jenis_penyelenggara": "kementerian"})["jenis_penyelenggara"] == "Kementerian Negara"
    assert normalize_llm_json({"jenis_penyelenggara": "bumn"})["jenis_penyelenggara"] == "BUMN"
    assert normalize_llm_json({"jenis_penyelenggara": "yayasan"})["jenis_penyelenggara"] == "Lembaga/Yayasan lain"


def test_normalize_llm_json_null_and_empty():
    assert normalize_llm_json({"jenis_penyelenggara": None})["jenis_penyelenggara"] is None
    assert normalize_llm_json({"jenis_penyelenggara": "null"})["jenis_penyelenggara"] is None
    assert normalize_llm_json({"jenis_penyelenggara": "-"})["jenis_penyelenggara"] is None
    assert normalize_llm_json({"jenis_penyelenggara": ""})["jenis_penyelenggara"] is None


def test_form_mapper_prioritizes_gemini_extracted_value():
    extracted = {
        "nama_kegiatan_sertifikasi": ExtractedValue("Data Slayer 2.0", 0.95, "gemini_llm"),
        "nomor_bukti_fisik_nomor_sertifikasi": ExtractedValue("804/AKD01/2024", 0.95, "gemini_llm"),
        "penyelenggara_kegiatan": ExtractedValue("Telkom University Purwokerto", 0.95, "gemini_llm"),
        "tingkat": ExtractedValue("Departemen/Program Studi", 0.90, "gemini_llm"),
        "jenis_penyelenggara": ExtractedValue("PTS di Indonesia", 0.90, "gemini_llm"),
    }
    mapped = map_fields_to_form(extracted, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
    assert mapped["jenis_penyelenggara"].value == "PTS di Indonesia"
    assert mapped["jenis_penyelenggara"].source == "gemini_llm"


def test_form_mapper_offline_safety_net_handles_external_ptn_and_pts():
    # Test IPB University (PTN beyond the 9 legacy keywords)
    jp_ipb = map_jenis_penyelenggara("Teks sertifikat", tingkat="Nasional", organizer="IPB University")
    assert jp_ipb == "PTN di Indonesia"

    # Test Telkom University (PTS with Departemen level - should not be forced into PTN)
    jp_telkom = map_jenis_penyelenggara("Teks sertifikat", tingkat="Departemen/Program Studi", organizer="Telkom University")
    assert jp_telkom == "PTS di Indonesia"

    # Test Universitas Islam Bandung (Unisba)
    jp_unisba = map_jenis_penyelenggara("Teks sertifikat", tingkat="Nasional", organizer="Universitas Islam Bandung")
    assert jp_unisba == "PTS di Indonesia"

    # Test PKN STAN
    jp_stan = map_jenis_penyelenggara("Teks sertifikat", tingkat="Nasional", organizer="Politeknik Keuangan Negara STAN")
    assert jp_stan == "PTN di Indonesia"

def test_form_mapper_fallback_when_gemini_returns_null():
    extracted = {
        "full_text": ExtractedValue("UNIVERSITAS AIRLANGGA", 1.0, "ocr"),
        "nama_kegiatan_sertifikasi": ExtractedValue("Seminar Nasional", 0.95, "gemini_llm"),
        "penyelenggara_kegiatan": ExtractedValue("IPB University", 0.95, "gemini_llm"),
        "tingkat": ExtractedValue("Nasional", 0.90, "gemini_llm"),
        "jenis_penyelenggara": ExtractedValue(None, 0.0, "gemini_llm"),
    }
    mapped = map_fields_to_form(extracted, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
    assert mapped["jenis_penyelenggara"].value == "PTN di Indonesia"
    assert mapped["jenis_penyelenggara"].source == "rule_mapper_strict"
