"""Unit tests for Indra OCR integration in tests/ocr_engine.py."""

import numpy as np
from PIL import Image
import io
import pytest

from tests.ocr_engine import ENGINES, ocr_engine, _get_indra, ocr_indra


def _create_test_image_bytes(text: str = "TEST") -> bytes:
    img = Image.new("RGB", (300, 80), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_indra_engine_registered():
    assert "indra" in ENGINES
    assert ENGINES["indra"] is ocr_indra


def test_indra_engine_loader():
    engine = _get_indra()
    assert engine is not None


def test_ocr_indra_execution():
    img_bytes = _create_test_image_bytes()
    text = ocr_indra(img_bytes)
    assert isinstance(text, str)


def test_ocr_engine_dispatch_indra():
    img_bytes = _create_test_image_bytes()
    text = ocr_engine("indra", img_bytes)
    assert isinstance(text, str)


def test_ocr_engine_dispatch_indra_tess():
    img_bytes = _create_test_image_bytes()
    text = ocr_engine("indra_tess", img_bytes)
    assert isinstance(text, str)


def test_ocr_engine_dispatch_indra_rapid():
    img_bytes = _create_test_image_bytes()
    text = ocr_engine("indra_rapid", img_bytes)
    assert isinstance(text, str)


def test_ocr_engine_dispatch_trio():
    img_bytes = _create_test_image_bytes()
    text = ocr_engine("trio", img_bytes)
    assert isinstance(text, str)
