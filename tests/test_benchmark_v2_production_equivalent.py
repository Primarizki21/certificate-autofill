"""Unit tests for the production-equivalent V2 Scope-Aware benchmark."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.benchmark_v2_production_equivalent import (
    ALL_EVAL_FIELDS,
    _assert_prompt_parity,
    _call_single_pass,
    _ensure_fresh_output,
    _gate_report,
    _safety_metrics,
)


def _evaluation_row(
    variant: str,
    *,
    wrong_fields: set[str] | None = None,
) -> dict:
    wrong_fields = wrong_fields or set()
    values = {
        "nama_kegiatan_sertifikasi": "Kegiatan Utama",
        "waktu_mulai_pelaksanaan": "01/01/2024",
        "waktu_selesai_pelaksanaan": "02/01/2024",
        "penyelenggara_kegiatan": "BEM FTMM",
        "nomor_bukti_fisik_nomor_sertifikasi": "01/FTMM/2024",
        "tingkat": "Nasional",
    }
    evaluation = {}
    for field_name in ALL_EVAL_FIELDS:
        gt_value = values[field_name]
        pred_value = "Fakultas" if field_name in wrong_fields else gt_value
        exact = pred_value == gt_value
        evaluation[field_name] = {
            "gt": gt_value,
            "pred": pred_value,
            "exact": exact,
            "fuzzy": exact,
            "wer": 0.0 if exact else 1.0,
            "cer": 0.0 if exact else 1.0,
            "confidence": 0.90 if pred_value else 0.0,
            "source": "gemini_llm",
        }
    return {
        "stem": f"{variant}-sample",
        "filename": f"{variant}-sample.pdf",
        "doc_type": "embedded",
        "variant": variant,
        "parser_engine": "pymupdf_fast_path",
        "tingkat_source": "llm",
        "call_meta": {"calls_count": 1},
        "evaluation": evaluation,
        "summary": {
            "exact_fields": sum(item["exact"] for item in evaluation.values()),
            "fuzzy_fields": sum(item["fuzzy"] for item in evaluation.values()),
            "total_fields": len(ALL_EVAL_FIELDS),
        },
    }


def test_prompt_parity_and_scope_rule_are_explicit() -> None:
    _assert_prompt_parity()


def test_gate_rejects_literal_field_decrease() -> None:
    baseline = [_evaluation_row("v1_production")]
    candidate = [_evaluation_row("v2_scope_aware", wrong_fields={"penyelenggara_kegiatan"})]

    report = _gate_report(baseline, candidate, min_tingkat_gain=0.0)

    assert report["gates"]["literal_field_preservation"]["pass"] is False
    assert report["gates"]["literal_field_preservation"]["per_field_pass"]["penyelenggara_kegiatan"] is False
    assert report["gates"]["all_pass"] is False


def test_production_confidence_does_not_flag_valid_wrong_enum() -> None:
    candidate = [_evaluation_row("v2_scope_aware", wrong_fields={"tingkat"})]

    safety = _safety_metrics(candidate, production_confidence=True)

    assert safety["cell_level"]["total_errors"] == 1
    assert safety["cell_level"]["flagged_errors"] == 0
    assert safety["doc_level"]["recall_pct"] == 0.0


def test_legacy_safety_calibration_has_same_semantic_gap() -> None:
    candidate = [_evaluation_row("v2_scope_aware", wrong_fields={"tingkat"})]

    safety = _safety_metrics(candidate, production_confidence=False)

    assert safety["cell_level"]["total_errors"] == 1
    assert safety["cell_level"]["flagged_errors"] == 0
    assert safety["doc_level"]["recall_pct"] == 0.0


def test_b14_guard_rejects_nonempty_output(tmp_path) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    (output_dir / "summary.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="B14 Immutability Guard"):
        _ensure_fresh_output(output_dir)


def test_single_pass_v2_uses_scope_prompt_and_maps_fields() -> None:
    calls: list[dict] = []

    class FakeClient:
        def generate_json(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                status="success",
                model="gemini-3.1-flash-lite",
                parsed_json={
                    "nama_kegiatan_sertifikasi": "Kegiatan Utama",
                    "nomor_bukti_fisik_nomor_sertifikasi": "01/FTMM/2024",
                    "penyelenggara_kegiatan": "BEM FTMM",
                    "waktu_mulai_pelaksanaan": "01/01/2024",
                    "waktu_selesai_pelaksanaan": "02/01/2024",
                    "tingkat": "Nasional",
                    "raw_role": "Peserta",
                },
                prompt_tokens=10,
                candidates_tokens=5,
                cached_tokens=0,
                thoughts_tokens=0,
                total_tokens=15,
                cost_usd=0.001,
                cost_idr=1.0,
                latency_s=0.1,
                web_search_queries=[],
                error_message=None,
            )

    mapped, metadata = _call_single_pass(
        variant="v2_scope_aware",
        raw_text="TEKS OCR SAMPLE",
        client=FakeClient(),
        model="gemini-3.1-flash-lite",
        skip_gemini=False,
    )

    assert len(calls) == 1
    assert "Cakupan Sasaran Peserta" in calls[0]["system_instruction"]
    assert "TEKS OCR SAMPLE" in calls[0]["prompt"]
    assert mapped["tingkat"].value == "Nasional"
    assert metadata["calls_details"][0]["total_tokens"] == 15
