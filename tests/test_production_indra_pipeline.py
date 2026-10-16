"""Unit and integration tests for production Indra OCR pipeline."""

import io
from pathlib import Path
import fitz
import numpy as np
from PIL import Image
import pytest

from app.config import settings
from app.services.pdf_fast_path import PageImageBuffer
from app.services.ocr_fallback import (
    _load_indra_ocr,
    _ocr_with_indra,
    extract_text_with_ocr,
)
from app.services.extraction_pipeline import run_extraction_pipeline


def _make_dummy_pdf_bytes(text: str = "SERTIFIKAT PENGHARGAAN NO: 123/UN3/2026") -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.insert_text((50, 80), text, fontsize=14)
    pix = page.get_pixmap()
    doc_scan = fitz.open()
    scan_page = doc_scan.new_page(width=400, height=200)
    scan_page.insert_image(scan_page.rect, stream=pix.tobytes("png"))
    pdf_bytes = doc_scan.write()
    doc.close()
    doc_scan.close()
    return pdf_bytes


def test_page_image_buffer_to_grayscale_ndarray():
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))
    buf = PageImageBuffer(
        samples=img.tobytes(),
        width=100,
        height=50,
        mode="RGB",
    )
    arr = buf.to_grayscale_ndarray()
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (50, 100)
    assert arr.dtype == np.uint8


def test_load_indra_ocr_singleton():
    engine = _load_indra_ocr()
    assert engine is not None
    engine2 = _load_indra_ocr()
    assert engine is engine2


def test_ocr_with_indra():
    engine = _load_indra_ocr()
    assert engine is not None
    gray = np.full((100, 300), 255, dtype=np.uint8)
    text = _ocr_with_indra(engine, gray)
    assert isinstance(text, str)


def test_extract_text_with_ocr_indra_enabled(monkeypatch):
    import dataclasses
    mock_settings = dataclasses.replace(settings, enable_indra_ocr=True)
    monkeypatch.setattr("app.services.ocr_fallback.settings", mock_settings)
    pdf_bytes = _make_dummy_pdf_bytes("SERTIFIKAT JUARA 1 NASIONAL")
    text = extract_text_with_ocr(pdf_bytes)
    assert isinstance(text, str)
    assert len(text) > 0


def test_extract_text_with_ocr_indra_disabled_fallback(monkeypatch):
    import dataclasses
    mock_settings = dataclasses.replace(settings, enable_indra_ocr=False)
    monkeypatch.setattr("app.services.ocr_fallback.settings", mock_settings)
    pdf_bytes = _make_dummy_pdf_bytes("SERTIFIKAT PESERTA")
    text = extract_text_with_ocr(pdf_bytes)
    assert isinstance(text, str)


def test_extraction_pipeline_with_indra(monkeypatch):
    import dataclasses
    mock_settings = dataclasses.replace(
        settings,
        enable_indra_ocr=True,
        enable_tesseract_gemini=False,
        enable_combined_v4_2=True,
    )
    monkeypatch.setattr("app.services.extraction_pipeline.settings", mock_settings)
    monkeypatch.setattr("app.services.ocr_fallback.settings", mock_settings)
    pdf_bytes = _make_dummy_pdf_bytes("SERTIFIKAT PANITIA")
    res = run_extraction_pipeline(pdf_bytes, tahun_akademik="2025/2026", bukti_fisik="Sertifikat")
    assert res is not None
    assert res.parser_engine is not None
