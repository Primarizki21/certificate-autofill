"""Production tests for the scope-aware Tesseract-to-Gemini path.

Verifies prompt parity, normalization, primary Gemini extraction, structural
boundaries, offline toggling, and Combined v4.2 fallback behavior.
"""

import os
import sys
from unittest.mock import patch
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.config import settings
from app.services.field_extractor import ExtractedValue
from app.services.gemini_extractor import (
    SYSTEM_INSTRUCTION,
    USER_PROMPT_TEMPLATE,
    extract_fields_with_gemini,
    normalize_llm_json,
    standardize_date,
)
from app.services.extraction_pipeline import run_extraction_pipeline
from app.services.pdf_fast_path import FastPathResult


class TestGeminiExtractorProduction:
    def test_missing_api_key_returns_graceful_error(self):
        orig_key = settings.google_api_key
        try:
            object.__setattr__(settings, "google_api_key", None)
            extracted, meta = extract_fields_with_gemini("Contoh teks", api_key=None)
            assert extracted is None
            assert "error" in meta
        finally:
            object.__setattr__(settings, "google_api_key", orig_key)

    def test_standardize_date_variations(self):
        """Uji parsing tanggal di modul produksi."""
        assert standardize_date("2024-08-24") == "24/08/2024"
        assert standardize_date("24/08/2024") == "24/08/2024"
        assert standardize_date("15 Oktober 2024") == "15/10/2024"
        assert standardize_date("October 15, 2024") == "15/10/2024"
        assert standardize_date(None) is None

    def test_normalize_llm_json_fields(self):
        """Uji normalisasi dict LLM ke format form KHP."""
        data = {
            "nama_kegiatan_sertifikasi": "Lomba AI Nasional",
            "nomor_bukti_fisik_nomor_sertifikasi": "01/AI/2024",
            "penyelenggara_kegiatan": "BEM FTMM",
            "waktu_mulai_pelaksanaan": "2024-11-01",
            "waktu_selesai_pelaksanaan": None,
            "tingkat": "fakultas",
            "raw_role": "Peserta",
        }
        norm = normalize_llm_json(data)
        assert norm["nama_kegiatan_sertifikasi"] == "Lomba AI Nasional"
        assert norm["nomor_bukti_fisik_nomor_sertifikasi"] == "01/AI/2024"
        assert norm["penyelenggara_kegiatan"] == "BEM FTMM"
        assert norm["waktu_mulai_pelaksanaan"] == "01/11/2024"
        assert norm["waktu_selesai_pelaksanaan"] == "01/11/2024"  # Disamakan jika selesai kosong
        assert norm["tingkat"] == "Fakultas"
        assert norm["raw_role"] == "Peserta"

    def test_pipeline_option_a_toggle_off(self):
        """Ketika toggle false, pipeline memakai mode offline tanpa menyentuh Gemini."""
        sample_pdf_dir = os.path.join(REPO_ROOT, "Sertifikat_Ground_Truth", "Peserta Seminar")
        sample_files = [f for f in os.listdir(sample_pdf_dir) if f.endswith(".pdf")]
        assert len(sample_files) > 0
        pdf_path = os.path.join(sample_pdf_dir, sample_files[0])
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        orig_val = settings.enable_tesseract_gemini
        try:
            object.__setattr__(settings, "enable_tesseract_gemini", False)
            res = run_extraction_pipeline(pdf_bytes, "2024/2025", "Sertifikat")
            assert "gemini" not in res.parser_engine
            assert "nama_kegiatan_sertifikasi" in res.mapped_fields
        finally:
            object.__setattr__(settings, "enable_tesseract_gemini", orig_val)

    def test_pipeline_option_a_graceful_fallback_on_error(self):
        """Ketika Gemini error (misal jaringan down), pipeline fallback otomatis ke offline."""
        sample_pdf_dir = os.path.join(REPO_ROOT, "Sertifikat_Ground_Truth", "Peserta Seminar")
        sample_files = [f for f in os.listdir(sample_pdf_dir) if f.endswith(".pdf")]
        pdf_path = os.path.join(sample_pdf_dir, sample_files[0])
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Simulasikan Gemini error
        with patch("app.services.gemini_extractor.extract_fields_with_gemini", return_value=(None, {"error": "Connection refused"})):
            res = run_extraction_pipeline(pdf_bytes, "2024/2025", "Sertifikat")
            assert res is not None
            assert "nama_kegiatan_sertifikasi" in res.mapped_fields
            assert "gemini" not in res.parser_engine
    def test_production_prompt_uses_scope_aware_v2_rules(self):
        assert "Cakupan Sasaran Peserta" in SYSTEM_INSTRUCTION
        assert "Jenjang Penyelenggara" in SYSTEM_INSTRUCTION
        assert "MESKIPUN diselenggarakan oleh BEM Fakultas" in SYSTEM_INSTRUCTION
        assert '"tingkat": "Internasional"|"Nasional"' in USER_PROMPT_TEMPLATE

    def test_gemini_success_applies_production_boundaries(self, monkeypatch):
        from app.services import extraction_pipeline

        raw_text = (
            "Dalam kegiatan MAIN SUMMIT 2025 pada perlombaan DATA TRACK "
            "yang diselenggarakan oleh Primary Institute\n"
            "Certificate of participation"
        )
        gemini_fields = {
            "full_text": ExtractedValue(raw_text, 1.0, "tesseract_raw"),
            "nama_kegiatan_sertifikasi": ExtractedValue(
                "MAIN SUMMIT 2025 DATA TRACK", 0.90, "gemini_llm"
            ),
            "nomor_bukti_fisik_nomor_sertifikasi": ExtractedValue(
                "01/DS/2025", 0.90, "gemini_llm"
            ),
            "penyelenggara_kegiatan": ExtractedValue(
                "Primary Institute in collaboration with Partner University",
                0.90,
                "gemini_llm",
            ),
            "waktu_mulai_pelaksanaan": ExtractedValue(None, 0.0, "gemini_llm"),
            "waktu_selesai_pelaksanaan": ExtractedValue(None, 0.0, "gemini_llm"),
            "tingkat": ExtractedValue("Nasional", 0.90, "gemini_llm"),
            "raw_role": ExtractedValue("Peserta", 0.90, "gemini_llm"),
        }
        calls: list[str] = []

        monkeypatch.setattr(
            extraction_pipeline,
            "extract_text_with_pymupdf",
            lambda _pdf: FastPathResult(raw_text, 1),
        )
        monkeypatch.setattr(
            extraction_pipeline,
            "extract_certificate_fields",
            lambda text: {"full_text": ExtractedValue(text, 1.0, "pymupdf")},
        )

        def fake_gemini(text: str):
            calls.append(text)
            return gemini_fields, {"model": "gemini-test"}

        monkeypatch.setattr(
            "app.services.gemini_extractor.extract_fields_with_gemini",
            fake_gemini,
        )

        original_flags = {
            name: getattr(settings, name)
            for name in (
                "enable_ocr_fallback",
                "enable_tesseract_gemini",
                "enable_combined_v2",
                "enable_combined_v3",
                "enable_combined_v4",
                "enable_combined_v4_1",
                "enable_combined_v4_2",
                "enable_organizer_normalization",
            )
        }
        try:
            object.__setattr__(settings, "enable_ocr_fallback", False)
            object.__setattr__(settings, "enable_tesseract_gemini", True)
            for name in original_flags:
                if name.startswith("enable_combined_") or name == "enable_organizer_normalization":
                    object.__setattr__(settings, name, False)
            result = run_extraction_pipeline(
                b"not-a-real-pdf",
                "2024/2025",
                "Sertifikat",
            )
        finally:
            for name, value in original_flags.items():
                object.__setattr__(settings, name, value)

        assert calls == [raw_text]
        assert result.parser_engine.endswith("+gemini-test")
        assert result.mapped_fields["nama_kegiatan_sertifikasi"].value == "MAIN SUMMIT 2025"
        assert result.mapped_fields["nama_kegiatan_sertifikasi"].source == "title_boundary"
        assert result.mapped_fields["penyelenggara_kegiatan"].value == "Primary Institute"
        assert result.mapped_fields["penyelenggara_kegiatan"].source == "organizer_boundary"

    def test_gemini_failure_keeps_combined_v42_fallback(self, monkeypatch):
        from app.services import combined_extractor, extraction_pipeline

        raw_text = (
            "Certificate for DATA TRACK 2025, held by Primary Institute. "
            "Participant recognition issued by the organizing committee."
        )
        extracted = {
            "full_text": ExtractedValue(raw_text, 1.0, "pymupdf"),
            "nama_kegiatan_sertifikasi": ExtractedValue(
                "DATA TRACK 2025", 0.90, "regex"
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
        combined_calls: list[dict] = []

        monkeypatch.setattr(
            extraction_pipeline,
            "extract_text_with_pymupdf",
            lambda _pdf: FastPathResult(raw_text, 1),
        )
        monkeypatch.setattr(
            extraction_pipeline,
            "extract_certificate_fields",
            lambda _text: dict(extracted),
        )
        monkeypatch.setattr(
            "app.services.gemini_extractor.extract_fields_with_gemini",
            lambda _text: (None, {"error": "API unavailable"}),
        )

        def fake_combined(fields, text):
            combined_calls.append(fields)
            assert text == raw_text
            return fields

        monkeypatch.setattr(combined_extractor, "apply_combined_v4_2", fake_combined)
        original_flags = {
            name: getattr(settings, name)
            for name in (
                "enable_ocr_fallback",
                "enable_tesseract_gemini",
                "enable_combined_v2",
                "enable_combined_v3",
                "enable_combined_v4",
                "enable_combined_v4_1",
                "enable_combined_v4_2",
                "enable_organizer_normalization",
            )
        }
        try:
            object.__setattr__(settings, "enable_ocr_fallback", False)
            object.__setattr__(settings, "enable_tesseract_gemini", True)
            for name in original_flags:
                object.__setattr__(settings, name, False)
            object.__setattr__(settings, "enable_combined_v4_2", True)
            result = run_extraction_pipeline(
                b"not-a-real-pdf",
                "2024/2025",
                "Sertifikat",
            )
        finally:
            for name, value in original_flags.items():
                object.__setattr__(settings, name, value)

        assert len(combined_calls) == 1
        assert result.raw_json is None
        assert result.parser_engine.endswith("+combined_v4_2")


    def test_pipeline_option_a_live_smoke(self):
        """Smoke test live: ekstraksi nyata via run_extraction_pipeline dengan Gemini aktif."""
        sample_pdf_path = os.path.join(
            REPO_ROOT, "Sertifikat_Ground_Truth", "Peserta Seminar", "1952296_219642_skp.pdf"
        )
        if not os.path.exists(sample_pdf_path):
            pytest.skip("Sample PDF 1952296_219642_skp.pdf tidak ditemukan")

        with open(sample_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        res = run_extraction_pipeline(pdf_bytes, "2024/2025", "Sertifikat")
        assert res is not None
        assert "gemini" in res.parser_engine.lower()
        assert res.mapped_fields["nama_kegiatan_sertifikasi"].value is not None
        assert res.mapped_fields["penyelenggara_kegiatan"].value is not None
        assert res.mapped_fields["tingkat"].value is not None
        assert res.mapped_fields["prestasi_partisipasi_jabatan"].value is not None
        assert res.mapped_fields["kelompok_kegiatan"].value is not None
