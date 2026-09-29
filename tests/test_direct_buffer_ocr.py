"""Unit tests for PageImageBuffer and zero-copy direct buffer OCR pipeline."""

from io import BytesIO
import fitz
import numpy as np
import pytest
from PIL import Image

from app.services.pdf_fast_path import (
    PageImageBuffer,
    render_pdf_pages_to_image_buffers,
    render_pdf_pages_to_png_bytes,
)
from app.services.ocr_fallback import extract_text_with_ocr, _ocr_with_rapidocr, _ocr_with_tesseract


class TestPageImageBuffer:
    def test_buffer_creation_and_pil_conversion(self):
        # Create a simple 10x10 RGB image buffer
        raw_samples = bytes([255, 0, 0] * 100)  # 100 red pixels
        buf = PageImageBuffer(samples=raw_samples, width=10, height=10, mode="RGB")

        # Convert to PIL
        pil_img = buf.to_pil()
        assert pil_img.size == (10, 10)
        assert pil_img.mode == "RGB"
        assert pil_img.getpixel((0, 0)) == (255, 0, 0)

        # Convert to Grayscale
        gray_img = buf.to_pil(mode="L")
        assert gray_img.size == (10, 10)
        assert gray_img.mode == "L"

    def test_buffer_to_bgr_ndarray(self):
        # Red pixel: RGB (255, 0, 0) -> BGR (0, 0, 255)
        raw_samples = bytes([255, 0, 0] * 4)  # 2x2 red pixels
        buf = PageImageBuffer(samples=raw_samples, width=2, height=2, mode="RGB")

        arr = buf.to_bgr_ndarray()
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (2, 2, 3)
        assert (arr[0, 0] == [0, 0, 255]).all()

    def test_lazy_png_bytes_cache(self):
        raw_samples = bytes([0, 255, 0] * 16)  # 4x4 green pixels
        buf = PageImageBuffer(samples=raw_samples, width=4, height=4, mode="RGB")
        assert buf._png_cache is None

        png1 = buf.to_png_bytes()
        assert isinstance(png1, bytes)
        assert png1.startswith(b"\x89PNG")
        assert buf._png_cache is not None
        assert buf._png_cache is png1

        # Second call returns cached bytes without re-encoding
        png2 = buf.to_png_bytes()
        assert png2 is png1

    def test_render_pdf_to_buffers_vs_png_bytes(self):
        # Generate a minimal valid 1-page PDF
        doc = fitz.open()
        page = doc.new_page(width=300, height=200)
        page.insert_text((50, 50), "Hello Buffer Test", fontsize=14)
        pdf_bytes = doc.tobytes()
        doc.close()

        # Render via both methods
        buffers = render_pdf_pages_to_image_buffers(pdf_bytes, zoom=2.0)
        png_bytes_list = render_pdf_pages_to_png_bytes(pdf_bytes, zoom=2.0)

        assert len(buffers) == 1
        assert len(png_bytes_list) == 1
        buf = buffers[0]

        # Verify dimensions match
        with Image.open(BytesIO(png_bytes_list[0])) as im_from_png:
            assert buf.width == im_from_png.width
            assert buf.height == im_from_png.height

        # Verify pixel samples are identical bit-for-bit
        pil_from_buf = buf.to_pil()
        with Image.open(BytesIO(png_bytes_list[0])) as im_from_png:
            arr_buf = np.array(pil_from_buf)
            arr_png = np.array(im_from_png)
            np.testing.assert_array_equal(arr_buf, arr_png)

    def test_image_fast_circuit(self):
        # Create a test PNG image
        im = Image.new("RGB", (20, 20), color=(10, 20, 30))
        out = BytesIO()
        im.save(out, format="PNG")
        png_bytes = out.getvalue()

        buffers = render_pdf_pages_to_image_buffers(png_bytes)
        assert len(buffers) == 1
        assert buffers[0].width == 20
        assert buffers[0].height == 20
        assert buffers[0]._png_cache == png_bytes

    def test_ocr_fallback_accepts_direct_objects(self):
        # Test that _ocr_with_tesseract accepts PIL Image directly
        img = Image.new("RGB", (100, 30), color="white")
        # Draw some text
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        d.text((10, 10), "TEST", fill="black")

        text = _ocr_with_tesseract(img)
        assert isinstance(text, str)
