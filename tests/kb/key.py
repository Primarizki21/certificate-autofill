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
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from app.services.form_mapper import map_jabatan
from tests.benchmark_organizer_v3 import _norm_organizer_v3

KEY_VERSION = "v1"

# KB-003: alias eksplisit (data-driven dari fragmentasi FST, KB-002) —
# varian R6 "Information System Dept." disatukan ke bentuk baris asli yang
# lebih sering muncul ("INFORMATION SYSTEMS DEPT", 5 vs 2 cert). Hanya
# pasangan yang terverifikasi ada di data; tambah saat data riil datang.
KEY_ALIASES = {
    "Faculty of Science and Technology Information System Dept.":
        "Faculty of Science and Technology INFORMATION SYSTEMS DEPT",
}

KEY_VARIANTS = ("plain", "stem", "alias", "both")


def normalize_organizer(value: str | None, raw_text: str) -> str | None:
    return _norm_organizer_v3(value, raw_text)


def normalize_role(raw_role: str | None) -> str | None:
    return map_jabatan(raw_role)


def _stem_org(value: str) -> str:
    """Stem kasar utk key: lowercase + case/punct collapse + singular per kata
    (strip 's' akhir utk kata >3 huruf) — menangkap varian SYSTEMS vs SYSTEM."""
    words = [
        re.sub(r"s$", "", w) if len(w) > 3 else w
        for w in re.sub(r"[^a-z0-9]+", " ", value.lower()).split()
    ]
    return " ".join(words)


def build_key(
    organizer: str | None,
    raw_role: str | None,
    raw_text: str,
    variant: str = "plain",
) -> tuple[str, str, str] | None:
    """Key v1 + varian normalisasi KB-003.

    - plain: organizer v3+R6 apa adanya (baseline KB-001/002).
    - alias: tabel alias eksplisit (konservatif, data-driven).
    - stem: case/punct collapse + singular-stem (umum, risiko over-merge).
    - both: alias dulu, lalu stem.
    Versi key = f"{KEY_VERSION}-{variant}" → snapshot tiap varian tidak
    tercampur.
    """
    if variant not in KEY_VARIANTS:
        raise ValueError(f"variant {variant!r} bukan {KEY_VARIANTS}")
    org = normalize_organizer(organizer, raw_text)
    role = normalize_role(raw_role)
    if not org or not role:
        return None
    if variant in ("alias", "both"):
        org = KEY_ALIASES.get(org, org)
    if variant in ("stem", "both"):
        org = _stem_org(org)
    return (org, role, f"{KEY_VERSION}-{variant}")


def _demo() -> None:
    k = build_key("BEM FTMM Universitas Airlangga", "Peserta", "sertifikat BEM FTMM")
    assert k == ("BEM FTMM Universitas Airlangga", "Peserta", "v1-plain"), k
    assert build_key(None, "Peserta", "x") is None
    assert build_key("BEM FTMM", None, "x") is None
    assert normalize_role("COMMITTEE") == "Panitia"
    assert normalize_role("as a participant") == "Peserta"
    assert normalize_role("Wakil Ketua") == "Wakil Ketua"
    # varian: alias menyatukan pasangan FST; stem menormalkan case/plural
    a = build_key("Faculty of Science and Technology Information System Dept.",
                  "Peserta", "x", variant="alias")
    b = build_key("Faculty of Science and Technology INFORMATION SYSTEMS DEPT",
                  "Peserta", "x", variant="alias")
    assert a is not None and b is not None and a[:2] == b[:2], (a, b)
    s = build_key("BEM FTMM Universitas Airlangga", "Peserta", "x", variant="stem")
    assert s[0] == "bem ftmm universita airlangga", s
    # versi key beda antar varian → snapshot tak tercampur
    assert build_key("BEM FTMM", "Peserta", "x", variant="plain")[2] != \
        build_key("BEM FTMM", "Peserta", "x", variant="stem")[2]
    print("ok: kb.key canonicalizer + variants")


if __name__ == "__main__":
    _demo()
