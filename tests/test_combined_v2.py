"""Unit test suite for Combined v2 Staging & Router Expansion."""

import pytest
from app.config import settings
from app.services.activity_extractor import extract_activity
from app.services.combined_extractor import apply_combined_v2
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.tingkat_router import _sig, route_tingkat, route_tingkat_trace


def test_default_config_disabled():
    """Default configuration must have enable_combined_v2 set to False."""
    assert hasattr(settings, "enable_combined_v2")
    assert settings.enable_combined_v2 is False


def test_apply_combined_v2_overrides():
    """apply_combined_v2 should override activity, organizer, nomor, and tingkat."""
    raw_text = (
        "SERTIFIKAT KEPANITIAAN\n"
        "Diberikan kepada John Doe atas partisipasinya sebagai Peserta \"LOMBA DESAIN NASIONAL\"\n"
        "yang diselenggarakan oleh Himpunan Mahasiswa Teknologi Informasi\n"
        "Nomor: 001/SERT/HIMA-TI/IX/2024"
    )
    initial_extracted = extract_certificate_fields(raw_text)
    combined = apply_combined_v2(initial_extracted, raw_text)

    assert "nama_kegiatan_sertifikasi" in combined
    assert combined["nama_kegiatan_sertifikasi"].source == "activity_v5"
    assert "LOMBA DESAIN NASIONAL" in combined["nama_kegiatan_sertifikasi"].value

    assert "penyelenggara_kegiatan" in combined
    assert combined["penyelenggara_kegiatan"].source in ("organizer_v4", "organizer_v2")

    assert "nomor_bukti_fisik_nomor_sertifikasi" in combined
    assert combined["nomor_bukti_fisik_nomor_sertifikasi"].source == "nomor_v2"

    assert "tingkat" in combined
    assert combined["tingkat"].source.startswith("router:")


def test_string_isolation():
    """Text processing must not mutate input string object."""
    original = "Sample Text with\nMultiple Lines and   Spaces."
    copy_orig = str(original)
    _ = extract_activity(original)
    assert original == copy_orig


def test_router_rules_unit():
    """Verify router rules give expected results for clean synthetic inputs."""
    # 1. tingkat_nasional
    assert route_tingkat("KOMPETISI TINGKAT NASIONAL DATA SCIENCE", "HIMA") == "Nasional"
    # 2. lomba+org
    assert route_tingkat("LOMBA CODING TAHUNAN", "BEM UNIVERSITAS AIRLANGGA") == "Nasional"
    # 3. dept+sem
    assert route_tingkat("SEMINAR KECERDASAN BUATAN", "DEPARTMENT TEKNIK INFORMATIKA") == "Departemen/Program Studi"
    assert route_tingkat("MAGANG PENGURUS ORGANISASI", "UKM ROBOTIKA") == "Universitas"
    # 5. hima_dept
    assert route_tingkat("STUDY PROGRAM WORKSHOP", "HIMPUNAN MAHASISWA TEKNOLOGI INFORMASI") == "Departemen/Program Studi"
    # 6. fak+univ (internal faculty)
    assert route_tingkat("KEGIATAN FAKULTAS TEKNOLOGI MAJU", "FAKULTAS TEKNOLOGI MAJU DAN MULTIDISIPLIN UNIVERSITAS AIRLANGGA") == "Fakultas"


def test_form_mapper_preserves_router_tingkat():
    """map_fields_to_form should preserve tingkat if routed by combined_extractor."""
    extracted = {
        "full_text": ExtractedValue("sample", 1.0, "pipeline"),
        "raw_role": ExtractedValue("Peserta", 0.9, "regex_role"),
        "nama_kegiatan_sertifikasi": ExtractedValue("Lomba Hackathon", 0.88, "activity_v5"),
        "penyelenggara_kegiatan": ExtractedValue("BEM FTMM", 0.85, "organizer_v4"),
        "tingkat": ExtractedValue("Fakultas", 0.95, "router:bem_no_univ"),
    }
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    assert mapped["tingkat"].value == "Fakultas"
    assert mapped["tingkat"].source == "router:bem_no_univ"
