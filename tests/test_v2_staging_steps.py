from tests.v2_ocr_normalizer import normalize_raw_ocr
from tests.v2_organizer_boundary import apply_organizer_boundary
from tests.v2_safety_review import build_review_annotations
from tests.v2_title_boundary import apply_title_boundary


def test_title_boundary_trims_explicit_subevent_suffix() -> None:
    raw = "Dalam kegiatan MAIN SUMMIT 2025 pada perlombaan DATA TRACK yang diselenggarakan oleh Host"
    result = apply_title_boundary(raw, "DATA TRACK")
    assert result.value == "MAIN SUMMIT 2025"
    assert result.changed is True
    assert result.boundary == "pada perlombaan"


def test_title_boundary_preserves_category_as_title_content() -> None:
    raw = "Pada kegiatan HI-TECH 7 Kategori Visualisasi Data Mahasiswa dengan tema \"Ideas\""
    current = "HI - TECH 7 Kategori Visualisasi Data Mahasiswa"
    result = apply_title_boundary(raw, current)
    assert result.value == current
    assert result.changed is False


def test_title_boundary_rejects_line_end_without_structural_marker() -> None:
    raw = "Dalam kegiatan FULL TITLE\nsecondary OCR line"
    result = apply_title_boundary(raw, "FULL TITLE EXTRA")
    assert result.value == "FULL TITLE EXTRA"
    assert result.changed is False


def test_organizer_boundary_strips_partner_after_primary() -> None:
    raw = "Held by Primary Institute in collaboration with Partner University on 30 April 2026"
    result = apply_organizer_boundary(
        raw,
        "Primary Institute in collaboration with Partner University",
    )
    assert result.value == "Primary Institute"
    assert result.changed is True
    assert result.reason == "primary_organizer_before_partner_connector"


def test_organizer_boundary_preserves_unverified_coorganizer() -> None:
    raw = "Peserta webinar dimulai.id bekerja sama dengan BIGIO"
    current = "dimulai.id bekerja sama dengan BIGIO"
    result = apply_organizer_boundary(raw, current)
    assert result.value == current
    assert result.changed is False


def test_organizer_boundary_preserves_explicit_coorganizer_logo() -> None:
    raw = (
        "Diselenggarakan oleh dimulai.id bekerja sama dengan BIGIO.\n"
        "dimulai.id x BIGIO"
    )
    current = "dimulai.id bekerja sama dengan BIGIO"
    result = apply_organizer_boundary(raw, current)
    assert result.value == current
    assert result.changed is False


def test_organizer_boundary_uses_issuer_not_signer_office() -> None:
    raw = "UNIVERSITY EXAMPLE\ndengan ini memberikan penghargaan kepada:"
    result = apply_organizer_boundary(
        raw,
        "Student Affairs Office University Example",
    )
    assert result.value == "University Example"
    assert result.changed is True


def test_ocr_normalizer_limits_character_repairs_to_number_region() -> None:
    raw = "Nomor: O0OO3/UNIT/1/2024\nNama B8T tetap\nhttps://example.test/O0OO3"
    result = normalize_raw_ocr(raw)
    assert "00003/UNIT/1/2024" in result.text
    assert "Nama B8T tetap" in result.text
    assert "https://example.test/O0OO3" in result.text
    assert result.replacements == 3


def test_safety_review_emits_field_reason_without_changing_value() -> None:
    annotations = build_review_annotations(
        "Dalam kegiatan MAIN SUMMIT yang diselenggarakan oleh Host University",
        {
            "nama_kegiatan_sertifikasi": "MAIN SUMMIT",
            "waktu_mulai_pelaksanaan": "",
            "waktu_selesai_pelaksanaan": "",
            "penyelenggara_kegiatan": "Host University",
            "nomor_bukti_fisik_nomor_sertifikasi": "",
            "tingkat": "Nasional",
        },
    )
    assert annotations["waktu_mulai_pelaksanaan"]["needs_review"] is True
    assert "missing_value" in annotations["waktu_mulai_pelaksanaan"]["reasons"]
    assert annotations["nomor_bukti_fisik_nomor_sertifikasi"]["needs_review"] is True
    assert annotations["tingkat"]["needs_review"] is True
