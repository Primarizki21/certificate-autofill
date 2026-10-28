"""Unit tests for generative & AUCC evaluation metrics (tests/evaluation_generative_v2.py)."""

import pytest
from tests.evaluation_generative_v2 import (
    evaluate_certificate_fields,
    normalize_cert_number,
    normalize_text_tokens,
    score_anls,
    score_cert_number_field,
    score_date_field,
    score_tingkat_field,
    score_token_f1,
    summarize_corpus_evaluations,
)


def test_token_f1_identical():
    p, r, f1 = score_token_f1(
        "Himpunan Mahasiswa Sistem Informasi",
        "Himpunan Mahasiswa Sistem Informasi",
    )
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0


def test_token_f1_partial():
    # 4 of 5 gold tokens captured, 0 extra tokens
    p, r, f1 = score_token_f1(
        "Himpunan Mahasiswa Sistem Informasi",
        "Himpunan Mahasiswa Sistem Informasi UNAIR",
    )
    assert p == 1.0
    assert r == 4.0 / 5.0
    assert pytest.approx(f1, 0.001) == (2 * 1.0 * 0.8) / (1.0 + 0.8)


def test_token_f1_empty_and_none():
    assert score_token_f1(None, None) == (1.0, 1.0, 1.0)
    assert score_token_f1("", "") == (1.0, 1.0, 1.0)
    assert score_token_f1("Webinar", None) == (0.0, 0.0, 0.0)
    assert score_token_f1(None, "Webinar") == (0.0, 0.0, 0.0)


def test_token_f1_disjoint():
    p, r, f1 = score_token_f1("Seminar Nasional", "Lomba Robotika")
    assert p == 0.0
    assert r == 0.0
    assert f1 == 0.0


def test_anls_scores():
    assert score_anls("Universitas Airlangga", "Universitas Airlangga") == 1.0
    # 1 edit distance in 21 chars: similarity 20/21 = ~0.952
    sim = score_anls("Universitas Airlanga", "Universitas Airlangga")
    assert sim >= 0.90

    # Below threshold (0.5) returns 0.0
    assert score_anls("Alpha", "Omega") == 0.0


def test_date_field_canonical_and_components():
    # Identical canonical dates in different string formats
    exact, comp = score_date_field("12 Januari 2024", "12/01/2024")
    assert exact is True
    assert comp == 1.0

    # Same month and year, different day
    exact, comp = score_date_field("15 Januari 2024", "12 Januari 2024")
    assert exact is False
    assert pytest.approx(comp, 0.001) == 2.0 / 3.0

    # Both empty / dash
    assert score_date_field("-", "-") == (True, 1.0)
    assert score_date_field(None, None) == (True, 1.0)
    assert score_date_field("12/01/2024", "-") == (False, 0.0)


def test_cert_number_normalization_and_scores():
    assert normalize_cert_number("045/UN3.1.8/KM/2023") == "045un318km2023"
    assert normalize_cert_number("045.un3-1-8 km 2023") == "045un318km2023"

    # Exact delimiter-normalized match
    exact, sim, cer = score_cert_number_field(
        "045/UN3.1.8/KM/2023",
        "045.un3-1-8 km 2023",
    )
    assert exact is True
    assert sim == 1.0
    assert cer == 0.0

    # OCR character confusion: 'O' instead of '0'
    exact, sim, cer = score_cert_number_field(
        "O45/UN3/2023",
        "045/UN3/2023",
    )
    assert exact is False
    assert sim > 0.85
    assert cer < 0.20


def test_tingkat_field_matching():
    exact, p_c, g_c = score_tingkat_field("nasional", "Nasional")
    assert exact is True
    assert p_c == "Nasional"
    assert g_c == "Nasional"

    exact, p_c, g_c = score_tingkat_field("Tingkat Internasional", "Internasional")
    assert exact is True
    assert p_c == "Internasional"

    exact, p_c, g_c = score_tingkat_field("Fakultas", "Nasional")
    assert exact is False


def test_single_certificate_and_corpus_summary():
    preds = {
        "nama_kegiatan_sertifikasi": "Webinar Nasional AI",
        "nomor_bukti_fisik_nomor_sertifikasi": "001/UNAIR/2024",
        "penyelenggara_kegiatan": "BEM UNAIR",
        "waktu_mulai_pelaksanaan": "10/05/2024",
        "waktu_selesai_pelaksanaan": "10/05/2024",
        "tingkat": "Nasional",
        "kelompok_kegiatan": "Penalaran dan Keilmuan",
        "jenis_kegiatan": "Mengikuti seminar/webinar",
        "prestasi_partisipasi_jabatan": "Peserta",
        "jenis_penyelenggara": "Internal UNAIR",
    }
    gt = {
        "nama_kegiatan_sertifikasi": "Webinar Nasional AI",
        "nomor_bukti_fisik_nomor_sertifikasi": "001/UNAIR/2024",
        "penyelenggara_kegiatan": "BEM UNAIR",
        "waktu_mulai_pelaksanaan": "10/05/2024",
        "waktu_selesai_pelaksanaan": "10/05/2024",
        "tingkat": "Nasional",
        "kelompok_kegiatan": "Penalaran dan Keilmuan",
        "jenis_kegiatan": "Mengikuti seminar/webinar",
        "prestasi_partisipasi_jabatan": "Peserta",
        "jenis_penyelenggara": "Internal UNAIR",
    }

    cert_res = evaluate_certificate_fields("test1.pdf", "folderA", preds, gt)
    assert cert_res.record_exact_6f is True
    assert cert_res.record_exact_all is True
    assert cert_res.aucc_triplet_exact is True

    # Summary
    summary = summarize_corpus_evaluations([cert_res])
    assert summary.total_docs == 1
    assert summary.record_exact_6f_count == 1
    assert summary.tingkat_macro_f1 == 1.0
    stats = summary.as_dict()
    assert stats["record_exact_6f_pct"] == 100.0
    assert stats["aucc_triplet_pct"] == 100.0
