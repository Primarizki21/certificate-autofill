"""Unit test suite for Combined v3 Composite Staging & Gating."""

import pytest
from app.config import settings
from app.services.combined_extractor import (
    apply_combined_v2,
    apply_combined_v3,
    extract_activity_v6,
    normalize_organizer_v6,
    normalize_nomor_v3,
    extract_dates_v2,
    route_with_disambiguation,
)
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form


def test_default_config_v3_disabled():
    """Default configuration must have enable_combined_v3 set to False."""
    assert hasattr(settings, "enable_combined_v3")
    assert settings.enable_combined_v3 is False


def test_apply_combined_v3_overrides():
    """apply_combined_v3 should override activity, organizer, nomor, dates, and tingkat."""
    raw_text = (
        "SERTIFIKAT KEPANITIAAN\n"
        "Diberikan kepada John Doe atas partisipasinya sebagai Peserta \"LOMBA DESAIN NASIONAL\"\n"
        "yang diselenggarakan oleh Himpunan Mahasiswa S1 Akuntansi\n"
        "pada tanggal 21-23 Agustus 2024\n"
        "Nomor: 043/FIN/FP14/FIT-UPH/XI1/2024"
    )
    initial_extracted = extract_certificate_fields(raw_text)
    combined = apply_combined_v3(initial_extracted, raw_text)

    # Activity v6
    assert "nama_kegiatan_sertifikasi" in combined
    assert combined["nama_kegiatan_sertifikasi"].source == "activity_v6"

    # Organizer v6
    assert "penyelenggara_kegiatan" in combined
    assert combined["penyelenggara_kegiatan"].source == "organizer_v6"
    assert "S-1 Akuntansi" in combined["penyelenggara_kegiatan"].value

    # Nomor v3 (Roman repair XI1 -> XII)
    assert "nomor_bukti_fisik_nomor_sertifikasi" in combined
    assert combined["nomor_bukti_fisik_nomor_sertifikasi"].source == "nomor_v3"
    assert "XII/2024" in combined["nomor_bukti_fisik_nomor_sertifikasi"].value

    # Dates v2
    assert "waktu_mulai_pelaksanaan" in combined
    assert combined["waktu_mulai_pelaksanaan"].source == "date_v2"
    assert combined["waktu_mulai_pelaksanaan"].value == "21/08/2024"
    assert combined["waktu_selesai_pelaksanaan"].value == "23/08/2024"

    # Tingkat
    assert "tingkat" in combined
    assert combined["tingkat"].source.startswith("router:")


def test_dates_v2_ordinals():
    """Test date parsing with English ordinals."""
    text = "that was held on Saturday, September 23th 2023."
    s, e, conf = extract_dates_v2(text)
    assert s == "23/09/2023"
    assert e == "23/09/2023"
    assert conf > 0.80


def test_organizer_v6_cleaners():
    """Test organizer cleaners for OCR spacing and acronyms."""
    res = normalize_organizer_v6("BEM Fakultas Psikologi Us U", "raw text")
    assert res == "BEM Fakultas Psikologi USU"


def test_nomor_v3_roman_repairs():
    """Test roman numeral month repair."""
    raw = "Nomor: 04/012/PSY-ACCRETION2.0/XIl/2024"
    res = normalize_nomor_v3(raw)
    assert res == "04/012/PSY-ACCRETION2.0/XII/2024"


def test_router_disambiguation():
    """Test contextual disambiguation router."""
    val, rule = route_with_disambiguation("Kompetisi Ilmiah Mahasiswa UNAIR 2024", "UNAIR", "KIM")
    assert val == "Universitas"
    assert rule.startswith("disambig_")
