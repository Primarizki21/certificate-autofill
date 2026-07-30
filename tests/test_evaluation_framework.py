from tests.date_normalizer import normalize_date
from tests.matchers import match_field


def test_normalize_date_indonesian():
    assert normalize_date("21 Agustus 2024") == "21/08/2024"
    assert normalize_date("23 Agustus 2025") == "23/08/2025"
    assert normalize_date("1 Oktober 2023") == "01/10/2023"
    assert normalize_date("6 Mei 2026") == "06/05/2026"


def test_normalize_date_english():
    assert normalize_date("21 September 2024") == "21/09/2024"
    assert normalize_date("7 December 2024") == "07/12/2024"


def test_normalize_date_empty():
    assert normalize_date(None) is None
    assert normalize_date("") is None
    assert normalize_date("-") is None


def test_match_exact_dropdown():
    r = match_field("Fakultas", "fakultas", "tingkat")
    assert r["exact"] is True
    assert r["fuzzy"] is True

    r = match_field("Fakultas", "Universitas", "tingkat")
    assert r["exact"] is False
    assert r["fuzzy"] is False


def test_match_contains_activity():
    r = match_field("SPECTA", "SPECTA 2024", "nama_kegiatan_sertifikasi")
    assert r["exact"] is False
    assert r["contains"] is True
    assert r["fuzzy"] is True


def test_match_token_overlap():
    expected = "BEM FTMM Universitas Airlangga"
    actual = "Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga"
    r = match_field(expected, actual, "penyelenggara_kegiatan")
    assert r["exact"] is False
    assert r["token_overlap"] >= 0.5


def test_match_date():
    r = match_field("21 Agustus 2024", "21 Agustus 2024", "waktu_mulai_pelaksanaan")
    assert r["exact"] is True

    r = match_field("21 Agustus 2024", "22 Agustus 2024", "waktu_mulai_pelaksanaan")
    assert r["exact"] is False


def test_match_nomor():
    r = match_field("3944/B/UN3.FTMM/KM.04/2024", "3944/B/UN3.FTMM/KM.04/2024", "nomor")
    assert r["exact"] is True


def test_match_missing_actual():
    r = match_field("sesuatu", None, "nama_kegiatan_sertifikasi")
    assert r["exact"] is False
    assert r["fuzzy"] is False


def test_wer_cer_exact():
    r = match_field("Dataquest 4.0", "Dataquest 4.0", "nama_kegiatan_sertifikasi")
    assert r["wer"] == 0.0
    assert r["cer"] == 0.0


def test_wer_cer_partial():
    r = match_field("Dataquest 4.0", "Dataquest 5.0", "nama_kegiatan_sertifikasi")
    assert 0 < r["wer"] < 1.0
    assert 0 < r["cer"] < 1.0


def test_wer_cer_null():
    r = match_field("Dataquest 4.0", None, "nama_kegiatan_sertifikasi")
    assert r["wer"] == 1.0
    assert r["cer"] == 1.0


def test_wer_cer_normalized_case():
    r = match_field("HOLOGY 7.0", "Hology 7.0", "nama_kegiatan_sertifikasi")
    assert r["wer"] == 0.0
    assert r["cer"] == 0.0


def test_wer_cer_partial_word():
    r = match_field("Dataquest 4.0", "Dataquest 5.0", "nama_kegiatan_sertifikasi")
    assert 0 < r["wer"] < 1.0
    assert 0 < r["cer"] < 1.0
