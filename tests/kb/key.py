"""Key canonicalizer KB tingkat v1 — prototipe (tests only, produksi ditunda).

Key = (normalized_organizer_v3, normalized_role, KEY_VERSION).

- Organizer: `_norm_organizer_v3` (R0-R6, default semua rule — konsisten dgn
  benchmark F3). Port produksi nanti pakai set KEEP OOD-003 (R0/R2/PREFIX_HELD/R6).
- Role: `map_jabatan` (backend form_mapper) → kategori stabil
  (Peserta/Panitia/Ketua/...). Ini membuat key lebih mudah berulang daripada
  raw_role mentah (F3: hanya 2 key berulang di 74 cert).
- KEY_VERSION dibawa DALAM key: normalizer berubah → entry lama tak tercampur.
- Tidak ada key bila organizer ATAU role kosong (tidak lookup, tidak tulis) —
  key (None, ...) hanya menambah noise & risiko salah-propagasi.

Usage:
  uv run python -m tests.kb.key
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from app.services.form_mapper import map_jabatan
from tests.benchmark_organizer_v3 import _norm_organizer_v3

KEY_VERSION = "v1"


def normalize_organizer(value: str | None, raw_text: str) -> str | None:
    return _norm_organizer_v3(value, raw_text)


def normalize_role(raw_role: str | None) -> str | None:
    return map_jabatan(raw_role)


def build_key(
    organizer: str | None,
    raw_role: str | None,
    raw_text: str,
) -> tuple[str, str, str] | None:
    org = normalize_organizer(organizer, raw_text)
    role = normalize_role(raw_role)
    if not org or not role:
        return None
    return (org, role, KEY_VERSION)


def _demo() -> None:
    k = build_key("BEM FTMM Universitas Airlangga", "Peserta", "sertifikat BEM FTMM")
    assert k == ("BEM FTMM Universitas Airlangga", "Peserta", KEY_VERSION), k
    assert build_key(None, "Peserta", "x") is None
    assert build_key("BEM FTMM", None, "x") is None
    assert normalize_role("COMMITTEE") == "Panitia"
    assert normalize_role("as a participant") == "Peserta"
    assert normalize_role("Wakil Ketua") == "Wakil Ketua"
    print("ok: kb.key canonicalizer")


if __name__ == "__main__":
    _demo()
