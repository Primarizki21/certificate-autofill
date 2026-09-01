"""Unit tests for robust acronym, initialism, and discrimination engine in tests/matchers.py."""

import pytest
from tests.matchers import (
    is_initialism_of,
    is_portmanteau_of,
    is_abbreviation_of,
    abbreviation_match,
    match_field,
)


def test_pure_initialisms_positive():
    cases = [
        ("USU", "Universitas Sumatera Utara"),
        ("UGM", "Universitas Gadjah Mada"),
        ("ITS", "Institut Teknologi Sepuluh Nopember"),
        ("UI", "Universitas Indonesia"),
        ("ITB", "Institut Teknologi Bandung"),
        ("IPB", "Institut Pertanian Bogor"),
        ("DPM FTMM", "Dewan Perwakilan Mahasiswa Fakultas Teknologi Maju dan Multidisiplin"),
    ]
    for abbr, full in cases:
        assert is_initialism_of(abbr, full) is True, f"Failed for {abbr} -> {full}"
        assert abbreviation_match(abbr, full) is True, f"Bidirectional match failed for {abbr} <-> {full}"
        assert abbreviation_match(full, abbr) is True, f"Bidirectional match failed for {full} <-> {abbr}"


def test_hierarchical_acronyms_positive():
    cases = [
        ("BEM FTMM", "Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin"),
        (
            "BEM FTMM Universitas Airlangga",
            "Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga",
        ),
        ("BEM FEB UNAIR", "Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga"),
    ]
    for abbr, full in cases:
        assert abbreviation_match(abbr, full) is True, f"Failed for {abbr} <-> {full}"
        r = match_field(full, abbr, "penyelenggara_kegiatan")
        assert r["exact"] is True, f"match_field exact failed for {abbr} <-> {full}"
        assert r["fuzzy"] is True, f"match_field fuzzy failed for {abbr} <-> {full}"


def test_portmanteaus_positive():
    cases = [
        ("UNAIR", "Universitas Airlangga"),
        ("UNESA", "Universitas Negeri Surabaya"),
        ("UNPAD", "Universitas Padjadjaran"),
        ("UNDIP", "Universitas Diponegoro"),
        ("HIMASADA", "Himpunan Mahasiswa Teknologi Sains Data"),
        ("HIMASADA", "Himpunan Mahasiswa Sains Data"),
        ("HIMATESDA", "Himpunan Mahasiswa Teknik Elektro dan Rekayasa Biomedis"),
        ("KEMENDIKBUD", "Kementerian Pendidikan dan Kebudayaan"),
        ("KEMENDIKBUDRISTEK", "Kementerian Pendidikan, Kebudayaan, Riset, dan Teknologi"),
    ]
    for abbr, full in cases:
        assert is_portmanteau_of(abbr, full) is True or is_initialism_of(abbr, full) is True, (
            f"Failed portmanteau for {abbr} -> {full}"
        )
        assert abbreviation_match(abbr, full) is True, f"Bidirectional match failed for {abbr} <-> {full}"


def test_strict_negative_discrimination():
    negative_pairs = [
        ("BEM FEB UNAIR", "BEM FKM UNAIR"),
        ("BEM FEB UGM", "BEM FEB UNAIR"),
        ("USU", "UNAIR"),
        ("USU", "Universitas Airlangga"),
        ("UNAIR", "Universitas Sumatera Utara"),
        ("BEM FST UNAIR", "BEM FTMM UNAIR"),
        ("HIMASADA", "HIMATESDA"),
    ]
    for a, b in negative_pairs:
        assert is_initialism_of(a, b) is False, f"False positive initialism for {a} vs {b}"
        assert is_portmanteau_of(a, b) is False, f"False positive portmanteau for {a} vs {b}"
        assert abbreviation_match(a, b) is False, f"False positive abbreviation_match for {a} vs {b}"
        r = match_field(a, b, "penyelenggara_kegiatan")
        assert r["exact"] is False, f"False positive match_field exact for {a} vs {b}"
        assert r["fuzzy"] is False, f"False positive match_field fuzzy for {a} vs {b}"
