"""EXP-OCR-LATENCY-001: konfigurasi thread ONNX Runtime untuk RapidOCR."""

import pytest

from app.config import settings
from app.services import ocr_fallback


@pytest.fixture
def restore_thread_setting():
    original = settings.ocr_rapid_threads
    yield
    object.__setattr__(settings, "ocr_rapid_threads", original)


@pytest.mark.parametrize(
    ("configured", "quota", "expected"),
    [
        (-1, 4, {}),
        (0, 4, {"intra_op_num_threads": 4, "inter_op_num_threads": 1}),
        (0, 2, {"intra_op_num_threads": 2, "inter_op_num_threads": 1}),
        (3, 4, {"intra_op_num_threads": 3, "inter_op_num_threads": 1}),
    ],
)
def test_rapidocr_thread_kwargs(monkeypatch, restore_thread_setting, configured, quota, expected):
    object.__setattr__(settings, "ocr_rapid_threads", configured)
    monkeypatch.setattr(ocr_fallback, "_cgroup_cpu_quota", lambda: quota)

    assert ocr_fallback._rapidocr_thread_kwargs() == expected


def test_thread_kwargs_fall_back_to_cpu_count_without_cgroup(monkeypatch, restore_thread_setting):
    object.__setattr__(settings, "ocr_rapid_threads", 0)
    monkeypatch.setattr(ocr_fallback, "_cgroup_cpu_quota", lambda: None)
    monkeypatch.setattr(ocr_fallback.os, "cpu_count", lambda: 6)

    assert ocr_fallback._rapidocr_thread_kwargs()["intra_op_num_threads"] == 6


@pytest.mark.parametrize(
    ("cpu_max", "expected"),
    [("400000 100000\n", 4), ("150000 100000\n", 1), ("max 100000\n", None)],
)
def test_cgroup_cpu_quota_parsing(monkeypatch, cpu_max, expected):
    monkeypatch.setattr(ocr_fallback.Path, "read_text", lambda self: cpu_max)

    assert ocr_fallback._cgroup_cpu_quota() == expected


def test_cgroup_cpu_quota_missing_file(monkeypatch):
    def raise_missing(self):
        raise FileNotFoundError(self)

    monkeypatch.setattr(ocr_fallback.Path, "read_text", raise_missing)

    assert ocr_fallback._cgroup_cpu_quota() is None
