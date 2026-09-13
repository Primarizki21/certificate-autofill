"""Production semantic safety and redacted Gemini telemetry tests."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from app.config import settings
from app.services.extraction_pipeline import run_extraction_pipeline
from app.services.field_extractor import ExtractedValue
from app.services.gemini_extractor import extract_fields_with_gemini
from app.services.pdf_fast_path import FastPathResult
from app.services.semantic_review import build_semantic_review
from tests.benchmark_production_input_matrix import aggregate_retry_telemetry


def test_semantic_review_allows_absent_optional_dates_without_raw_date() -> None:
    annotations = build_semantic_review(
        "Dalam kegiatan MAIN SUMMIT yang diselenggarakan oleh Host University",
        {
            "waktu_mulai_pelaksanaan": ExtractedValue(None, 0.0, "gemini_llm"),
            "waktu_selesai_pelaksanaan": ExtractedValue(None, 0.0, "gemini_llm"),
        },
    )

    assert annotations["waktu_mulai_pelaksanaan"].needs_review is False
    assert annotations["waktu_selesai_pelaksanaan"].needs_review is False


def test_semantic_review_flags_missing_date_when_raw_anchor_exists() -> None:
    annotations = build_semantic_review(
        "Held on 24/08/2024 for MAIN SUMMIT",
        {
            "waktu_mulai_pelaksanaan": ExtractedValue(None, 0.0, "gemini_llm"),
            "waktu_selesai_pelaksanaan": ExtractedValue(None, 0.0, "gemini_llm"),
        },
    )

    for field_name in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        assert annotations[field_name].needs_review is True
        assert "date_value_missing_despite_raw_anchor" in annotations[field_name].reasons


def test_semantic_review_flags_ambiguous_level_evidence() -> None:
    annotations = build_semantic_review(
        "Tingkat: Nasional. Tingkat: Fakultas.",
        {"tingkat": ExtractedValue("Nasional", 0.90, "gemini_llm")},
    )

    assert annotations["tingkat"].needs_review is True
    assert "ambiguous_level_evidence" in annotations["tingkat"].reasons


def test_pipeline_attaches_semantic_review_to_offline_result(monkeypatch) -> None:
    raw_text = (
        "Dalam kegiatan MAIN SUMMIT 2025 pada perlombaan DATA TRACK "
        "yang diselenggarakan oleh Primary Institute\n"
        "Nomor: 01/DS/2025"
    )
    extracted = {
        "full_text": ExtractedValue(raw_text, 1.0, "pymupdf"),
        "nama_kegiatan_sertifikasi": ExtractedValue(
            "MAIN SUMMIT 2025 DATA TRACK", 0.90, "regex"
        ),
        "nomor_bukti_fisik_nomor_sertifikasi": ExtractedValue(
            "01/DS/2025", 0.90, "regex"
        ),
        "penyelenggara_kegiatan": ExtractedValue(
            "Primary Institute", 0.90, "regex"
        ),
        "waktu_mulai_pelaksanaan": ExtractedValue(None, 0.0, "regex"),
        "waktu_selesai_pelaksanaan": ExtractedValue(None, 0.0, "regex"),
        "tingkat": ExtractedValue("Nasional", 0.90, "regex"),
        "raw_role": ExtractedValue("Peserta", 0.90, "regex"),
    }
    monkeypatch.setattr(
        "app.services.extraction_pipeline.extract_text_with_pymupdf",
        lambda _pdf: FastPathResult(raw_text, 1),
    )
    monkeypatch.setattr(
        "app.services.extraction_pipeline.extract_certificate_fields",
        lambda _text: dict(extracted),
    )
    flag_names = (
        "enable_ocr_fallback",
        "enable_tesseract_gemini",
        "enable_combined_v2",
        "enable_combined_v3",
        "enable_combined_v4",
        "enable_combined_v4_1",
        "enable_combined_v4_2",
        "enable_organizer_normalization",
    )
    original_flags = {name: getattr(settings, name) for name in flag_names}
    try:
        for name in flag_names:
            object.__setattr__(settings, name, False)
        result = run_extraction_pipeline(
            b"not-a-real-pdf", "2024/2025", "Sertifikat"
        )
    finally:
        for name, value in original_flags.items():
            object.__setattr__(settings, name, value)

    title_review = result.review_annotations["nama_kegiatan_sertifikasi"]
    assert title_review.needs_review is True
    assert "explicit_structural_boundary" in title_review.reasons


def test_gemini_missing_key_logs_status_without_ocr(caplog, monkeypatch) -> None:
    original_key = settings.google_api_key
    private_ocr = "PRIVATE OCR CONTENT 7f9c2a"
    try:
        object.__setattr__(settings, "google_api_key", None)
        caplog.set_level(logging.INFO, logger="app.services.gemini_extractor")
        extracted, meta = extract_fields_with_gemini(private_ocr, api_key=None)
    finally:
        object.__setattr__(settings, "google_api_key", original_key)

    assert extracted is None
    assert meta["status"] == "skipped"
    assert meta["fallback_reason"] == "missing_api_key"
    assert meta["calls_count"] == 0
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "missing_api_key" in logged
    assert private_ocr not in logged


def test_gemini_network_error_redacts_exception_and_key(caplog, monkeypatch) -> None:
    private_ocr = "PRIVATE OCR CONTENT network-case"
    private_error = "PRIVATE ERROR BODY"

    def fail_urlopen(_request, timeout=None):
        raise urllib.error.URLError(f"{private_error} timeout={timeout}")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    caplog.set_level(logging.INFO, logger="app.services.gemini_extractor")
    extracted, meta = extract_fields_with_gemini(
        private_ocr,
        api_key="dummy-secret-key",
        timeout_s=0.01,
    )

    assert extracted is None
    assert meta["status"] == "error"
    assert meta["fallback_reason"] == "network_error"
    assert meta["error_type"] == "URLError"
    assert meta["calls_count"] == 1
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert private_ocr not in logged
    assert private_error not in logged
    assert "dummy-secret-key" not in logged


def test_gemini_success_records_complete_token_accounting(caplog, monkeypatch) -> None:
    private_ocr = "PRIVATE OCR CONTENT success-case"
    body = {
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 4,
            "cachedContentTokenCount": 2,
            "thoughtsTokenCount": 3,
            "totalTokenCount": 19,
        },
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "nama_kegiatan_sertifikasi": "MAIN SUMMIT",
                                    "nomor_bukti_fisik_nomor_sertifikasi": "01/DS/2025",
                                    "penyelenggara_kegiatan": "Primary Institute",
                                    "waktu_mulai_pelaksanaan": "24/08/2025",
                                    "waktu_selesai_pelaksanaan": "24/08/2025",
                                    "tingkat": "Nasional",
                                    "raw_role": "Peserta",
                                }
                            )
                        }
                    ]
                }
            }
        ],
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, _type, _value, _traceback):
            return False

        def read(self):
            return json.dumps(body).encode("utf-8")

    monkeypatch.setattr(urllib.request, "urlopen", lambda _request, timeout=None: FakeResponse())
    caplog.set_level(logging.INFO, logger="app.services.gemini_extractor")
    extracted, meta = extract_fields_with_gemini(
        private_ocr,
        api_key="dummy-secret-key",
        model="gemini-3.1-flash-lite",
        timeout_s=0.01,
    )

    assert extracted is not None
    assert meta["status"] == "success"
    assert meta["prompt_tokens"] == 10
    assert meta["candidates_tokens"] == 4
    assert meta["cached_tokens"] == 2
    assert meta["thoughts_tokens"] == 3
    assert meta["total_tokens"] == 19
    assert meta["cost_usd"] > 0
    assert meta["cost_idr"] > 0
    assert meta["calls_count"] == 1
    assert meta["calls_details"][0]["total_tokens"] == 19
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert private_ocr not in logged
    assert "dummy-secret-key" not in logged
    assert "prompt_tokens=10" in logged


def test_retry_telemetry_aggregates_each_attempt() -> None:
    metas = [
        {
            "status": "error",
            "model": "gemini-3.1-flash-lite",
            "fallback_reason": "network_error",
            "error_type": "URLError",
            "latency_s": 0.5,
            "prompt_tokens": 10,
            "candidates_tokens": 0,
            "cached_tokens": 0,
            "thoughts_tokens": 0,
            "total_tokens": 10,
            "calls_count": 1,
        },
        {
            "status": "success",
            "model": "gemini-3.1-flash-lite",
            "latency_s": 0.7,
            "prompt_tokens": 10,
            "candidates_tokens": 4,
            "cached_tokens": 0,
            "thoughts_tokens": 2,
            "total_tokens": 16,
            "calls_count": 1,
        },
    ]

    meta = aggregate_retry_telemetry(metas, model="gemini-3.1-flash-lite")

    assert meta["status"] == "success"
    assert meta["calls_count"] == 2
    assert meta["retry_count"] == 1
    assert meta["prompt_tokens"] == 20
    assert meta["candidates_tokens"] == 4
    assert meta["thoughts_tokens"] == 2
    assert meta["total_tokens"] == 26
    assert len(meta["calls_details"]) == 2
    assert meta["latency_s"] == 1.2
