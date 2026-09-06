"""Production unit tests for Tesseract-to-Gemini (Option A) integration.

Verifies:
  1. Graceful error return when API key is missing (no exception raised).
  2. Date standardization and tingkat normalization in production service.
  3. Pipeline execution when ENABLE_TESSERACT_GEMINI=false (offline path).
  4. Graceful fallback to offline pipeline when Gemini encounters an error.
  5. End-to-end execution of run_extraction_pipeline with Gemini enabled on real PDF bytes.
"""

import os
import sys
from dataclasses import replace
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
    extract_fields_with_gemini,
    normalize_llm_json,
    standardize_date,
)
from app.services.extraction_pipeline import run_extraction_pipeline


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
