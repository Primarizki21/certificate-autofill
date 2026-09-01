"""Unit tests for Combined v4.2 staging bundle (EXP-V4-003: 3 Pillars & High-DPI Robustness)."""

import pytest
from app.config import settings
from app.services.field_extractor import ExtractedValue
from app.services.combined_extractor import (
    extract_activity_v8,
    normalize_nomor_v5,
    apply_combined_v4_2,
)
from app.services.high_dpi_crop import crop_and_ocr_number_region


def test_default_config_v4_2_disabled(monkeypatch):
    import os
    from app.config import Settings
    monkeypatch.delenv("ENABLE_COMBINED_V4_2", raising=False)
    unconfigured = Settings(enable_combined_v4_2=os.getenv("ENABLE_COMBINED_V4_2", "false").lower() == "true")
    assert unconfigured.enable_combined_v4_2 is False


def test_extract_activity_v8_structural_anchors_id():
    raw = """
    SERTIFIKAT PENGHARGAAN
    Diberikan kepada Ahmad
    sebagai Peserta Terbaik dalam acara Lomba Desain Inovasi Nasional 2026 yang diselenggarakan oleh BEM FTMM
    pada tanggal 10 Maret 2026
    """
    act = extract_activity_v8(raw)
    assert act is not None
    assert "Lomba Desain Inovasi Nasional 2026" in act


def test_extract_activity_v8_structural_anchors_en():
    raw = """
    CERTIFICATE OF ACHIEVEMENT
    In recognition of their participation as Finalist in the event entitled "Global AI Hackathon 2026" organized by IEEE
    on October 15, 2026
    """
    act = extract_activity_v8(raw)
    assert act is not None
    assert "Global AI Hackathon 2026" in act


def test_normalize_nomor_v5_roman_repairs():
    assert normalize_nomor_v5("100/SK/XI1/2024") == "100/SK/XII/2024"
    assert normalize_nomor_v5("200/SK/X1/2024") == "200/SK/XI/2024"
    assert normalize_nomor_v5("300/SK/V1/2024") == "300/SK/VI/2024"
    assert normalize_nomor_v5("400/SK/VII1/2024") == "400/SK/VIII/2024"


def test_high_dpi_crop_empty_safe():
    assert crop_and_ocr_number_region(b"") is None
    assert crop_and_ocr_number_region(b"not a valid pdf") is None


def test_apply_combined_v4_2_confidence_and_structure():
    mock_extracted = {
        "nama_kegiatan_sertifikasi": ExtractedValue(None, 0.0, "none"),
        "penyelenggara_kegiatan": ExtractedValue("BEM FTMM", 0.8, "regex"),
    }
    raw = """
    SERTIFIKAT
    Diberikan kepada Siswa
    sebagai Peserta dalam Seminar Nasional Kecerdasan Buatan 2025 yang diselenggarakan oleh BEM FTMM
    pada tanggal 20 Oktober 2025
    No: 123/FTMM/X1/2025
    """
    res = apply_combined_v4_2(mock_extracted, raw)
    assert res["nama_kegiatan_sertifikasi"].value is not None
    assert res["nama_kegiatan_sertifikasi"].confidence >= 0.90
    assert "XI" in (res["nomor_bukti_fisik_nomor_sertifikasi"].value or "")
