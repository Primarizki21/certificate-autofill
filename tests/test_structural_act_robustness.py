"""B5 — Unit test robustness ekstraktor kegiatan v9 (anti organizer-bleed).

Kasus dari audit QA B5: capture `_STRUCTURAL_ACT_ID` menelan penyelenggara
karena kata penutup "yang diadakan oleh" tidak ada di daftar closers; fallback
`$` membuat capture meluas; tier generik v7 punya celah closer yang sama
("diadakan oleh"/"hosted by"). Semua kasus negatif WAJIB bersih (0 bleed).
"""

import pytest

from tests.activity_extractor_v9 import extract_activity_v9

BLEED_TOKENS = ["BEM FTMM", "BEM FKM", "HIMATESDA", "pada tanggal", "yang diadakan", "diselenggarakan", "hosted by"]


def _assert_clean(text: str, expect: str | None = None) -> None:
    got = extract_activity_v9(text)
    if expect is not None:
        assert got == expect, f"got {got!r}, expect {expect!r} — text: {text[:80]!r}"
    assert got is not None, f"harus ada kegiatan — text: {text[:80]!r}"
    for tok in BLEED_TOKENS:
        assert tok.lower() not in got.lower(), f"bleed {tok!r} di {got!r} — text: {text[:80]!r}"


def test_plan_case_yang_diadakan_oleh():
    """Kasus audit QA B5 (dari plan): bleed 'yang diadakan oleh BEM FTMM'."""
    text = (
        "sebagai Panitia dalam acara Karya Inovasi Mahasiswa 2026 yang diadakan "
        "oleh BEM FTMM pada tanggal 10 Maret 2026"
    )
    _assert_clean(text, "Karya Inovasi Mahasiswa 2026")


def test_diadakan_oleh_singkat():
    text = "sebagai peserta dalam kegiatan Pelatihan Public Speaking 2026 diadakan oleh BEM FKM pada tanggal 1 Mei 2026"
    _assert_clean(text, "Pelatihan Public Speaking 2026")


def test_bekerja_sama_dengan():
    text = (
        "sebagai peserta dalam kegiatan Pelatihan Public Speaking 2026 yang bekerja "
        "sama dengan BEM FTMM pada tanggal 1 Mei 2026"
    )
    _assert_clean(text, "Pelatihan Public Speaking 2026")


def test_bertempat_di():
    text = "sebagai panitia dalam acara Git Gud 2026 bertempat di Aula FTMM pada tanggal 12 Juni 2026"
    _assert_clean(text, "Git Gud 2026")


def test_english_hosted_by():
    text = (
        "in recognition of his participation as a delegate in the event entitled "
        '"AI Workshop 2026" hosted by BEM FTMM on 10 March 2026'
    )
    _assert_clean(text, "AI Workshop 2026")


def test_english_in_collaboration_with():
    text = (
        "in recognition of her participation as a speaker in the event entitled "
        '"Tech Talk 2026" in collaboration with Faculty of Computer Science on 10 March 2026'
    )
    _assert_clean(text, "Tech Talk 2026")


def test_no_closing_word_no_unbounded_bleed():
    """Tanpa kata penutup baku: capture dipotong pada penanda tema (0 bleed)."""
    text = (
        "sebagai peserta dalam kegiatan Olimpiade Sains Mahasiswa Indonesia yang sangat panjang "
        "dan berkelanjutan dengan berbagai cabang lomba dari seluruh perguruan tinggi negeri "
        "dan swasta di Indonesia pada tahun 2026 dengan tema yang luar biasa sekali"
    )
    got = extract_activity_v9(text)
    assert got is not None, "harus ada kegiatan"
    assert "dengan tema yang luar biasa sekali" not in got, f"bleed tema: {got!r}"
    assert len(got) <= 200, f"capture terlalu panjang: {len(got)} char — {got!r}"


def test_unmatched_quote_sanitized():
    text = 'sebagai peserta dalam kegiatan "Seminar AI 2026 yang diselenggarakan oleh BEM FTMM pada tanggal 1 Maret 2026'
    got = extract_activity_v9(text)
    assert got is not None
    assert '"' not in got and "BEM FTMM" not in got


def test_newline_in_capture_normalized():
    # Bypass tier generik (yang memotong baris) — jalur anchor struktural v9.
    text = (
        "sebagai Pemakalah pada acara Seminar\nTerbuka 2026 yang diselenggarakan "
        "oleh BEM FTMM pada tanggal 12 Juni 2026"
    )
    got = extract_activity_v9(text)
    assert got is not None, f"harus ada kegiatan — {text[:60]!r}"
    assert "\n" not in got
    assert "BEM FTMM" not in got
    assert got == "Seminar Terbuka 2026", f"got {got!r}"


def test_zero_regression_corpus_anchor():
    """Pola struktural klasik v8 tetap berfungsi (anchor 'yang diselenggarakan oleh')."""
    text = (
        "sebagai Panitia dalam kegiatan Festival Teknologi 2025 yang diselenggarakan "
        "oleh BEM FTMM pada tanggal 10 Maret 2025"
    )
    _assert_clean(text, "Festival Teknologi 2025")


def test_quoted_event_fallback():
    text = 'Diberikan kepada peserta kegiatan "Lomba Karya Tulis 2026" yang diselenggarakan oleh HIMATESDA'
    got = extract_activity_v9(text)
    assert got == "Lomba Karya Tulis 2026"
