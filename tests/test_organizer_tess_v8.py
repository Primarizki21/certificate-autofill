"""Regression tests for ORG-TESS-V8-001 organizer repairs."""

from pathlib import Path

from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from tests.composite_v4_candidate import apply_composite_v4_candidate
from tests.organizer_tess_v8 import extract_organizer_v8, extract_organizer_v8_result


FIXTURE_DIR = Path(__file__).resolve().parent / "benchmark_runs/ocr_experiment/tesseract_pure_all74_v4/extracted_texts"


def read_fixture(stem: str) -> str:
    path = FIXTURE_DIR / f"{stem}.txt"
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")).strip()


def test_gelar_rasa_signer_columns_reconstruct_organizer() -> None:
    raw = read_fixture("Gelar Rasa_Muhammad Fazil Irvan Putra")
    result = extract_organizer_v8_result(raw)
    assert result.value == "Himasada, Fakultas Ilmu Komputer"
    assert result.source == "organizer_v8:signer_join"
    assert result.confidence < 0.85


def test_vendedict_noisy_date_closer_stops_phrase_before_footer() -> None:
    raw = read_fixture("VENEDICT_panitia_karsa")
    result = extract_organizer_v8_result(raw)
    assert result.value == "BEM FTMM Universitas Airlangga"
    assert "pada" not in result.value.lower()
    assert "ketua" not in result.value.lower()

def test_composite_v8_variant_is_explicit_and_default_stays_baseline() -> None:
    raw = read_fixture("VENEDICT_panitia_karsa")
    baseline = extract_certificate_fields(raw)
    baseline["full_text"] = ExtractedValue(raw, 1.0, "ocr_text")
    v2 = apply_composite_v4_candidate(baseline, raw)

    candidate = extract_certificate_fields(raw)
    candidate["full_text"] = ExtractedValue(raw, 1.0, "ocr_text")
    v8 = apply_composite_v4_candidate(candidate, raw, organizer_variant="v8")

    assert not v2["penyelenggara_kegiatan"].source.startswith("organizer_v8")
    assert v8["penyelenggara_kegiatan"].value == "BEM FTMM Universitas Airlangga"
    assert v8["penyelenggara_kegiatan"].source.startswith("organizer_v8")

def test_valid_number_line_does_not_override_organizer() -> None:
    raw = read_fixture("1981676_219642_skp")
    result = extract_organizer_v8_result(raw)
    assert result.value == (
        "Departemen Kajian dan Aksi Strategis Badan Eksekutif Mahasiswa "
        "Fakultas Ekonomi dan Bisnis Universitas Airlangga"
    )
    assert not result.value.startswith("542")

def test_isolated_number_noise_line_is_not_an_organizer() -> None:
    raw = r"""
    SERTIFIKAT
    \ 2 | 542/A.5/BINCANG SANTAI INTELEKTUAL/BEM FEB UNAIR/XI/2023
    """
    assert extract_organizer_v8(raw) is None


def test_existing_structural_phrase_is_preserved() -> None:
    raw = """
    Dalam acara Bincang Santai Intelektual 2
    yang diselenggarakan oleh Departemen Kajian dan Aksi Strategis
    Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga
    pada tanggal 26 November 2023
    """
    assert extract_organizer_v8(raw) == (
        "Departemen Kajian dan Aksi Strategis Badan Eksekutif Mahasiswa "
        "Fakultas Ekonomi dan Bisnis Universitas Airlangga"
    )


def test_on_inside_organizer_is_not_a_date_closer() -> None:
    raw = "organized by Keluarga Mahasiswa Teknik Elektro on Campus"
    assert extract_organizer_v8(raw) == "Keluarga Mahasiswa Teknik Elektro on Campus"


def test_fuzzy_alias_is_marked_low_confidence() -> None:
    result = extract_organizer_v8_result("Ketua RIMASADA")
    assert result.value == "Himasada"
    assert result.confidence < 0.85
    assert result.source == "organizer_v8:signer"
