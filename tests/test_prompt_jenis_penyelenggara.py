"""Unit tests for Jenis Penyelenggara prompt normalization and evaluation (EXP-ALL6F-PROMPT-007)."""

import pytest
from tests.benchmark_prompt_jenis_penyelenggara import (
    ALL_7_FIELDS,
    VALID_JP_OPTIONS,
    clean_json_markdown,
    evaluate_single,
    normalize_parsed_output,
)


def test_normalize_valid_enum_case_insensitive():
    for opt in VALID_JP_OPTIONS:
        res = normalize_parsed_output({"jenis_penyelenggara": opt.lower()})
        assert res["jenis_penyelenggara"] == opt


def test_normalize_fuzzy_fallback():
    assert normalize_parsed_output({"jenis_penyelenggara": "Universitas Negeri"})["jenis_penyelenggara"] == "PTN di Indonesia"
    assert normalize_parsed_output({"jenis_penyelenggara": "Kampus Swasta"})["jenis_penyelenggara"] == "PTS di Indonesia"
    assert normalize_parsed_output({"jenis_penyelenggara": "Overseas University"})["jenis_penyelenggara"] == "PT di luar negeri"
    assert normalize_parsed_output({"jenis_penyelenggara": "Ministry of Education"})["jenis_penyelenggara"] == "Kementerian Negara"
    assert normalize_parsed_output({"jenis_penyelenggara": "State-Owned Enterprise"})["jenis_penyelenggara"] == "BUMN"
    assert normalize_parsed_output({"jenis_penyelenggara": "Random Association"})["jenis_penyelenggara"] == "Lembaga/Yayasan lain"


def test_clean_json_markdown():
    text = "```json\n{\"jenis_penyelenggara\": \"PTN di Indonesia\"}\n```"
    assert clean_json_markdown(text) == "{\"jenis_penyelenggara\": \"PTN di Indonesia\"}"


def test_evaluate_single_exact_match():
    pred = {fld: "PTN di Indonesia" if fld == "jenis_penyelenggara" else "Test" for fld in ALL_7_FIELDS}
    gt = {
        "Nama Kegiatan Sertifikasi": "Test",
        "Nomor Bukti Fisik Nomor Sertifikasi": "Test",
        "Penyelenggara Kegiatan": "Test",
        "Waktu Mulai Pelaksanaan": "Test",
        "Waktu Selesai Pelaksanaan": "Test",
        "Tingkat": "Test",
        "Jenis Penyelenggara": "PTN di Indonesia",
    }
    ev = evaluate_single(pred, gt)
    assert ev["jenis_penyelenggara"]["exact"] is True
    assert ev["jenis_penyelenggara"]["match_type"] == "EXACT"
