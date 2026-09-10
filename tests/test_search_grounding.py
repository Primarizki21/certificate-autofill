"""Unit tests untuk Search Grounding Benchmark Runner (EXP-SEARCH-GROUNDING-001)."""

import pytest
from tests.benchmark_search_grounding import (
    ACTIVE_VARIANTS,
    ALL_6_FIELDS,
    FRAMEWORK_5_FIELDS,
    VALID_TINGKAT_OPTIONS,
    aggregate_variant_metrics,
    clean_json_from_text,
    compute_field_confidence_and_review,
    evaluate_predictions,
    parse_cot_tingkat,
    run_mock_inference,
)


def test_active_variants_registered():
    """Memastikan varian text control, search, decoupled control, dan decoupled search terdaftar."""
    expected = ["v2_text_control", "v2_search", "v3_text_control", "v3_search_cot"]
    for v in expected:
        assert v in ACTIVE_VARIANTS
    assert len(ACTIVE_VARIANTS) == 4

def test_clean_json_from_text_markdown_block():
    """Memastikan ekstraksi JSON dari blok markdown ```json ... ```."""
    raw_text = """Berdasarkan pencarian web, berikut datanya:
```json
{
  "nama_kegiatan_sertifikasi": "Lomba Data Mining",
  "tingkat": "Nasional"
}
```
Catatan tambahan."""
    parsed = clean_json_from_text(raw_text)
    assert parsed is not None
    assert parsed["nama_kegiatan_sertifikasi"] == "Lomba Data Mining"
    assert parsed["tingkat"] == "Nasional"


def test_clean_json_from_text_raw_braces():
    """Memastikan ekstraksi JSON dari kurung kurawal langsung tanpa markdown."""
    raw_text = 'Teks sebelum {"tingkat": "Internasional", "nomor": "123"} teks sesudah'
    parsed = clean_json_from_text(raw_text)
    assert parsed is not None
    assert parsed["tingkat"] == "Internasional"
    assert parsed["nomor"] == "123"


def test_clean_json_from_text_invalid():
    """Memastikan nilai None jika teks tidak memuat JSON valid."""
    assert clean_json_from_text("Hanya teks biasa tanpa json") is None
    assert clean_json_from_text("") is None


def test_parse_cot_tingkat():
    """Memastikan parser tingkat mengenali enum standar."""
    for opt in VALID_TINGKAT_OPTIONS:
        data = {"tingkat": opt.lower()}
        val, status = parse_cot_tingkat(data)
        assert val == opt

    # Fallback
    assert parse_cot_tingkat({"tingkat": "tidak_diketahui"})[0] == "Lainnya"
    assert parse_cot_tingkat({})[0] is None


def test_compute_field_confidence_and_review():
    """Memastikan kalkulasi confidence dan flag review bekerja."""
    # Tanggal valid
    c1, r1 = compute_field_confidence_and_review("waktu_mulai_pelaksanaan", "24/08/2024", "llm")
    assert c1 >= 0.85
    assert r1 is False

    # Tingkat valid
    c2, r2 = compute_field_confidence_and_review("tingkat", "Nasional", "search")
    assert c2 >= 0.85
    assert r2 is False

    # Missing value
    c3, r3 = compute_field_confidence_and_review("nomor_bukti_fisik_nomor_sertifikasi", None, "llm")
    assert c3 < 0.85
    assert r3 is True


def test_run_mock_inference():
    """Memastikan mock inference menghasilkan format data yang benar."""
    doc = {"nama_file": "test.pdf"}
    for var in ACTIVE_VARIANTS:
        fields, meta = run_mock_inference(var, "Sample text OCR", doc)
        assert "tingkat" in fields
        assert "nama_kegiatan_sertifikasi" in fields
        assert meta["status"] == "success"
        assert "total_tokens" in meta
        assert "cost_idr" in meta
        if "search" in var:
            assert len(meta["web_queries"]) > 0


def test_aggregate_variant_metrics():
    """Memastikan agregasi metrik menghasilkan persentase dan akuntansi biaya."""
    doc_results = [
        {
            "variant": "v2_search",
            "eval": {
                "nama_kegiatan_sertifikasi": {"gt": "Lomba", "pred": "Lomba", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "nomor_bukti_fisik_nomor_sertifikasi": {"gt": "123", "pred": "123", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "penyelenggara_kegiatan": {"gt": "BEM", "pred": "BEM", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "waktu_mulai_pelaksanaan": {"gt": "10/10/2024", "pred": "10/10/2024", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "waktu_selesai_pelaksanaan": {"gt": "10/10/2024", "pred": "10/10/2024", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "tingkat": {"gt": "Nasional", "pred": "Nasional", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
            },
            "meta": {
                "prompt_tokens": 1000,
                "candidates_tokens": 50,
                "cached_tokens": 0,
                "thoughts_tokens": 0,
                "total_tokens": 1050,
                "cost_usd": 0.0001,
                "cost_idr": 1.6,
                "calls_count": 1,
                "web_queries": ["query 1"],
            },
        }
    ]
    summary = aggregate_variant_metrics(doc_results)
    assert summary["n_docs"] == 1
    assert summary["all_cells_6f"]["exact_pct"] == 100.0
    assert summary["token_and_cost"]["total_web_queries"] == 1
    assert summary["token_and_cost"]["total_cost_idr"] == 1.6

def test_evaluate_predictions_with_real_dict():
    """Memastikan evaluate_predictions memanggil match_field dengan format dict."""
    preds = {
        "nama_kegiatan_sertifikasi": "Lomba Data Mining Gemastik 2025",
        "nomor_bukti_fisik_nomor_sertifikasi": "123/UN3.1/KM/2025",
        "penyelenggara_kegiatan": "Universitas Indonesia",
        "waktu_mulai_pelaksanaan": "24/08/2025",
        "waktu_selesai_pelaksanaan": "25/08/2025",
        "tingkat": "Nasional",
    }
    gt_row = {
        "nama_kegiatan_sertifikasi": "Lomba Data Mining Gemastik 2025",
        "nomor_bukti_fisik_nomor_sertifikasi": "123/UN3.1/KM/2025",
        "penyelenggara_kegiatan": "Universitas Indonesia",
        "waktu_mulai_pelaksanaan": "24/08/2025",
        "waktu_selesai_pelaksanaan": "25/08/2025",
        "tingkat": "Nasional",
    }
    eval_res = evaluate_predictions(preds, gt_row)
    assert len(eval_res) == 6
    for f in ALL_6_FIELDS:
        assert eval_res[f]["exact"] is True
        assert eval_res[f]["fuzzy"] is True
        assert eval_res[f]["wer"] == 0.0
        assert eval_res[f]["cer"] == 0.0
