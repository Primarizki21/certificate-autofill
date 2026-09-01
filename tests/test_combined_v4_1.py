"""Unit tests for Combined v4.1 minor staging refinement (EXP-V4-002)."""

import pytest
from app.config import settings
from app.services.field_extractor import ExtractedValue
from app.services.combined_extractor import (
    extract_activity_v7,
    normalize_nomor_v4,
    apply_combined_v4_1,
)
from tests.date_normalizer import normalize_date
from tests.matchers import match_field


def test_default_config_v4_1_disabled():
    assert settings.enable_combined_v4_1 is False


def test_date_normalizer_english_ordinals():
    assert normalize_date("September 23th 2023") == "23/09/2023"
    assert normalize_date("23rd September 2024") == "23/09/2024"
    assert normalize_date("1st August 2024") == "01/08/2024"
    assert normalize_date("2nd October 2024") == "02/10/2024"


def test_nomor_matcher_underscore_equivalence():
    n1 = "063/A/UNITY_UKMRT/UNY/VI/2026"
    n2 = "063/A/UNITYUKMRT/UNY/VI/2026"
    res = match_field(n1, n2, "nomor_bukti_fisik_nomor_sertifikasi")
    assert res["exact"] is True


def test_extract_activity_v7_word_merge():
    raw = 'Yang telah berpartisipasi sebagaipeserta campaign dalam Digital Campaign 2023: "Level Up Yourself Starting Right Now" oleh SCOLAH'
    act = extract_activity_v7(raw)
    assert act is not None
    assert "Digital Campaign 2023" in act


def test_normalize_nomor_v4_multiblock():
    raw = """
    No.
    /A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023
    270
    """
    nomor = normalize_nomor_v4(raw)
    assert nomor == "270/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023"


def test_apply_combined_v4_1_direktur_kemahasiswaan_rule():
    mock_extracted = {
        "nama_kegiatan_sertifikasi": ExtractedValue("Kegiatan Mahasiswa 2024", 0.8, "regex"),
        "penyelenggara_kegiatan": ExtractedValue("Panitia Mahasiswa", 0.8, "regex"),
    }
    raw = """
    UNIVERSITAS AIRLANGGA
    DIREKTUR KEMAHASISWAAN
    Prof. Dr. M. Hadi Shubhan
    """
    res = apply_combined_v4_1(mock_extracted, raw)
    assert res["tingkat"].value == "Universitas"
    assert res["tingkat"].source == "router:direktur_kemahasiswaan_unair"
