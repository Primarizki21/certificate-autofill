"""Unit tests for Prompt Optimization V2 & V3 Benchmark Runner (EXP-PROMPT-OPT-002)."""

import pytest
from tests.benchmark_prompt_opt_v2_v3 import (
    ACTIVE_VARIANTS,
    ALL_6_FIELDS,
    FRAMEWORK_5_FIELDS,
    VALID_TINGKAT_OPTIONS,
    compute_field_confidence_and_review,
    evaluate_predictions,
    parse_cot_tingkat_json,
    run_mock_inference,
)


def test_active_variants_has_all_four():
    """Memastikan seluruh 4 varian arsitektur prompting terdaftar lengkap."""
    expected = ["v2_baseline", "v2_opt", "v3_pure_llm", "v3_enhanced_router"]
    assert len(ACTIVE_VARIANTS) == 4
    for v in expected:
        assert v in ACTIVE_VARIANTS


def test_parse_cot_tingkat_json_canonical():
    """Memastikan parser mengenali seluruh opsi kanonikal dan mendeteksi langkah CoT."""
    for opt in VALID_TINGKAT_OPTIONS:
        parsed = {
            "langkah_1_penyelenggara": "BEM Fakultas",
            "langkah_2_sifat_kegiatan": "Lomba terbuka",
            "langkah_3_cakupan_peserta": "Skala peserta",
            "tingkat": opt,
        }
        res, has_steps = parse_cot_tingkat_json(parsed)
        assert res == opt
        assert has_steps is True


def test_parse_cot_tingkat_json_case_insensitive_and_fallback():
    """Memastikan parser toleran huruf besar/kecil dan substring."""
    p1 = {"tingkat": "nasional"}
    r1, _ = parse_cot_tingkat_json(p1)
    assert r1 == "Nasional"

    p2 = {"tingkat": "Tingkat Internasional (Global)"}
    r2, _ = parse_cot_tingkat_json(p2)
    assert r2 == "Internasional"

    p3 = {"tingkat": "Himpunan Program Studi"}
    r3, _ = parse_cot_tingkat_json(p3)
    assert r3 == "Departemen/Program Studi"

    p_null = {}
    r_null, steps_null = parse_cot_tingkat_json(p_null)
    assert r_null == "Lainnya"
    assert steps_null is False


def test_compute_field_confidence_and_review():
    """Memastikan kalibrasi confidence dan flag needs_review (<0.85)."""
    # Tanggal valid -> high confidence (0.92, no review)
    conf1, rev1 = compute_field_confidence_and_review("waktu_mulai_pelaksanaan", "24/08/2024")
    assert conf1 >= 0.85
    assert rev1 is False

    # Tanggal invalid format -> low confidence (0.50, needs review)
    conf2, rev2 = compute_field_confidence_and_review("waktu_mulai_pelaksanaan", "Agustus 2024")
    assert conf2 < 0.85
    assert rev2 is True

    # Tingkat router -> confidence 0.98
    conf3, rev3 = compute_field_confidence_and_review("tingkat", "Fakultas", "router:hima_internal")
    assert conf3 == 0.98
    assert rev3 is False

    # Field kosong -> confidence 0.0 (needs review)
    conf4, rev4 = compute_field_confidence_and_review("nomor_bukti_fisik_nomor_sertifikasi", None)
    assert conf4 == 0.0
    assert rev4 is True


def test_run_mock_inference_all_four_variants():
    """Memastikan mock inference menghasilkan 6 field + role untuk seluruh 4 varian."""
    raw_text = "Sertifikat Lomba AI Nasional diselenggarakan BEM FTMM UNAIR"

    for var in ACTIVE_VARIANTS:
        fields, meta = run_mock_inference(var, raw_text)
        for f in ALL_6_FIELDS:
            assert f in fields
            assert fields[f] is not None
        assert "raw_role" in fields

        if var == "v3_pure_llm":
            assert meta["calls_count"] == 2
        elif var in ("v2_baseline", "v2_opt"):
            assert meta["calls_count"] == 1


def test_evaluate_predictions_aggregation():
    """Memastikan penghitungan metrik All-Cells, Framework 5F, dan safety-net recall."""
    doc_results = [
        {
            "variant": "v2_opt",
            "dataset": "v9",
            "nama_file": "doc1.pdf",
            "eval": {
                "nama_kegiatan_sertifikasi": {"gt": "A", "pred": "A", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "nomor_bukti_fisik_nomor_sertifikasi": {"gt": "123", "pred": "123", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "penyelenggara_kegiatan": {"gt": "BEM", "pred": "BEM", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "waktu_mulai_pelaksanaan": {"gt": "01/01/2024", "pred": "01/01/2024", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "waktu_selesai_pelaksanaan": {"gt": "01/01/2024", "pred": "01/01/2024", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "tingkat": {"gt": "Nasional", "pred": "Nasional", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
            },
            "meta": {"prompt_tokens": 400, "candidates_tokens": 80, "total_tokens": 480, "cost_idr": 3.5, "calls_count": 1},
        },
        {
            "variant": "v2_opt",
            "dataset": "v9",
            "nama_file": "doc2.pdf",
            "eval": {
                "nama_kegiatan_sertifikasi": {"gt": "B", "pred": "B", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "nomor_bukti_fisik_nomor_sertifikasi": {"gt": "456", "pred": "999", "exact": False, "fuzzy": False, "wer": 1.0, "cer": 1.0},
                "penyelenggara_kegiatan": {"gt": "HIMA", "pred": "HIMA", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "waktu_mulai_pelaksanaan": {"gt": "02/02/2024", "pred": "02/02/2024", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "waktu_selesai_pelaksanaan": {"gt": "02/02/2024", "pred": "02/02/2024", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
                "tingkat": {"gt": "Fakultas", "pred": "Fakultas", "exact": True, "fuzzy": True, "wer": 0.0, "cer": 0.0},
            },
            "meta": {"prompt_tokens": 400, "candidates_tokens": 80, "total_tokens": 480, "cost_idr": 3.5, "calls_count": 1},
        },
    ]

    res = evaluate_predictions(doc_results)
    assert res["n_docs"] == 2
    # Total cells: 2 * 6 = 12. Exact: 11 (1 nomor salah)
    assert res["all_cells_6f"]["total_cells"] == 12
    assert res["all_cells_6f"]["exact_cells"] == 11
    assert res["all_cells_6f"]["exact_pct"] == round(11 / 12 * 100.0, 2)

    # Framework 5F: 2 * 5 = 10. Exact: 9
    assert res["framework_5f"]["total_cells"] == 10
    assert res["framework_5f"]["exact_cells"] == 9

    # Tokens & Cost: 480 + 480 = 960 total
    assert res["tokens_and_cost"]["total_tokens"] == 960
    assert res["tokens_and_cost"]["eff_tokens_per_doc"] == 480.0
    assert res["tokens_and_cost"]["total_cost_idr"] == 7.0


def test_run_benchmark_mock_smoke(tmp_path):
    """Memastikan run_benchmark dengan backend mock menyelesaikan end-to-end evaluasi dan menghasilkan seluruh artefak."""
    from tests.benchmark_prompt_opt_v2_v3 import run_benchmark

    out_dir = tmp_path / "smoke_out"
    res = run_benchmark(
        manifest_path="certs_unified/manifest.json",
        gt_path="Ground_Truth_Unified.csv",
        output_dir=str(out_dir),
        backend="mock",
        limit=2,
        checkpoint_scope="smoke",
        pacing_delay=0.0,
    )
    assert res is not None
    assert (out_dir / "comparative_summary.md").exists()
    assert (out_dir / "comparative_metrics.json").exists()
    assert (out_dir / "results.xlsx").exists()
    assert (out_dir / "evaluation_details.csv").exists()
    assert len(res["summary"]) == 4
