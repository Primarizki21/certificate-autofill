"""B6 — Unit test preservasi panjang digit & guard format nomor v6."""

import pytest

from tests.nomor_normalizer_v6 import normalize_nomor_v6


@pytest.mark.parametrize(
    "text,expect,expect_flag",
    [
        # DPKKA: panjang digit WAJIB terjaga (4 digit tetap 4 digit).
        ("NO: OOO4/DPKKA/KM/I/2026", "0004/DPKKA/KM/I/2026", True),
        ("NO: O0OO3/DPKKA/KM/I/2026", "00003/DPKKA/KM/I/2026", True),
        ("NO: O0002/DPKKA/KM/IV/2026", "00002/DPKKA/KM/IV/2026", True),
        # Prefix NOMOR/NUMBER didukung (v6 #2).
        ("NOMOR: 0004/DPKKA/KM/I/2026", "0004/DPKKA/KM/I/2026", False),
        ("NUMBER: OOO4/DPKKA/KM/I/2026", "0004/DPKKA/KM/I/2026", True),
        ("NOMOR : O0OO3/DPKKA/KM/II/2026", "00003/DPKKA/KM/II/2026", True),
        # Guard Roman: "1" polos tanpa konteks Romawi -> tidak di-repair, flag.
        ("SERT-123/FTMM/1/2024", "SERT-123/FTMM/1/2024", True),
        ("NO: 270/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023", "270/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023", False),
    ],
)
def test_nomor_v6_invariants(text, expect, expect_flag):
    got, flag = normalize_nomor_v6(text)
    assert got == expect, f"{text!r}: got {got!r}, expect {expect!r}"
    assert flag == expect_flag, f"{text!r}: flag {flag}, expect {expect_flag}"


def test_digit_count_preserved():
    """Invariant utama: jumlah digit prefix nomor tidak berubah oleh cleaner."""
    cases = [
        ("NO: OOO4/DPKKA/KM/I/2026", 4),
        ("NO: O0OO3/DPKKA/KM/I/2026", 5),
        ("NO: OOOO5/DPKKA/KM/I/2026", 5),
        ("NO: 0004/DPKKA/KM/I/2026", 4),
    ]
    for text, ndigits in cases:
        got, _ = normalize_nomor_v6(text)
        prefix = got.split("/")[0]
        assert len(prefix) == ndigits and prefix.isdigit(), (
            f"{text!r}: prefix {prefix!r} harus {ndigits} digit"
        )


def test_roman_repair_still_works():
    # Repair Roman yang sah tetap berjalan (XI1 -> XII, X1 -> XI).
    got, flag = normalize_nomor_v6("NO: 123/FTMM/XI1/2024")
    assert got == "123/FTMM/XII/2024" and flag, (got, flag)
    got, flag = normalize_nomor_v6("NO: 123/FTMM/X1/2024")
    assert got == "123/FTMM/XI/2024" and flag, (got, flag)


def test_roman_no_repair_when_valid():
    # Bulan Romawi valid tidak berubah, tanpa flag.
    got, flag = normalize_nomor_v6("NO: 123/FTMM/XII/2024")
    assert got == "123/FTMM/XII/2024" and not flag, (got, flag)


def test_overcorrection_guard_single_digit():
    # "1" polos TIDAK diubah menjadi "I" (Roman overcorrection — bug v3/v5).
    got, flag = normalize_nomor_v6("SERT-123/FTMM/1/2024")
    assert got == "SERT-123/FTMM/1/2024", got
    assert flag  # tetapi perlu verifikasi (confidence 0.78)


def test_empty_and_none():
    assert normalize_nomor_v6("") == (None, False)
    assert normalize_nomor_v6("Sertifikat tanpa nomor apapun disini") == (None, False)
