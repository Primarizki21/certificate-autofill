"""Unit tests for Combined v4 staging bundle and normalize_organizer_v7."""

import pytest
from app.services.field_extractor import ExtractedValue
from app.services.combined_extractor import (
    normalize_organizer_v7,
    apply_combined_v4,
)


def test_normalize_organizer_v7_s1_canonicalization():
    raw = "HIMA S1 Akuntansi"
    out = normalize_organizer_v7(raw, raw)
    assert out is not None
    assert "S-1" in out


def test_normalize_organizer_v7_acronym_repair():
    raw = "Panitia Pelaksana Us U 2024"
    out = normalize_organizer_v7("Us U", raw)
    assert out is not None
    assert "USU" in out


def test_apply_combined_v4_basic_structure():
    mock_extracted = {
        "nama_kegiatan_sertifikasi": ExtractedValue("Seminar Nasional", 0.8, "regex"),
        "penyelenggara_kegiatan": ExtractedValue("BEM FTMM", 0.8, "regex"),
        "nomor_bukti_fisik_nomor_sertifikasi": ExtractedValue(None, 0.0, "none"),
        "waktu_mulai_pelaksanaan": ExtractedValue(None, 0.0, "none"),
        "waktu_selesai_pelaksanaan": ExtractedValue(None, 0.0, "none"),
    }
    raw_text = """
    SERTIFIKAT PENGHARGAAN
    Diberikan kepada Venedict
    Atas partisipasinya dalam acara Falcon Project 2024
    Yang diselenggarakan oleh Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga
    Pada tanggal 24 Agustus 2024 - 22 September 2024
    No: 3944/B/UN3.FTMM/KM.04/XI1/2024
    """

    res = apply_combined_v4(mock_extracted, raw_text)
    assert isinstance(res, dict)
    assert "nama_kegiatan_sertifikasi" in res
    assert "penyelenggara_kegiatan" in res
    assert "nomor_bukti_fisik_nomor_sertifikasi" in res
    assert "waktu_mulai_pelaksanaan" in res
    assert "tingkat" in res

    # Verification of repairs
    assert res["waktu_mulai_pelaksanaan"].value == "24/08/2024"
    assert res["waktu_selesai_pelaksanaan"].value == "22/09/2024"
    assert "XII" in (res["nomor_bukti_fisik_nomor_sertifikasi"].value or "")
