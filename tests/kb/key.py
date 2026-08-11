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

from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_jabatan, map_kelompok_dan_jenis
from tests.benchmark_organizer_v3 import _norm_organizer_v3

KEY_VERSION = "v1"

# KB-005: komponen event utk key. Desain asli (kb_design.md) bilang event_type;
# pipeline tidak ekstrak `jenis_kegiatan` beneran — `map_kelompok_dan_jenis`
# (offline, 0 LLM) menghasilkan kelompok & jenis, diukur mana yang layak.
EVENTS = ("role", "jenis", "kelompok")

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


def compute_event(raw_text: str, raw_role: str | None,
                  organizer: str | None) -> tuple[str | None, str | None]:
    """(jenis_kegiatan, kelompok_kegiatan) — offline, 0 LLM.

    `"--"`/kosong → None (key mati, dihitung sebagai empty rate di benchmark).
    """
    extracted = extract_certificate_fields(raw_text)
    act = extracted.get("nama_kegiatan_sertifikasi")
    activity = act.value if act else None
    kelompok, jenis = map_kelompok_dan_jenis(
        raw_text.upper(), (raw_role or "").upper(), activity or "", organizer or "")
    return ((jenis if jenis and jenis != "--" else None),
            (kelompok if kelompok and kelompok != "--" else None))


def make_key(org_label: str | None, event_label: str | None,
             variant: str = "plain", event: str = "role",
             aliases: dict[str, str] | None = None) -> tuple[str, str, str] | None:
    """Rakit key dari label yang sudah dinormalisasi (efisien utk benchmark).

    - org_label: organizer v3+R6 (belum varian key).
    - event_label: role / jenis_kegiatan / kelompok_kegiatan.
    - variant: plain/stem/alias/both (KB-003); aliases override utk KB-006
      (auto-alias mining).
    Versi: event=role → `v1-{variant}` (kompatibel KB-001..004), selainnya
    `v1-{variant}-{event}`.
    """
    if not org_label or not event_label:
        return None
    if variant in ("alias", "both"):
        org_label = (aliases if aliases is not None else KEY_ALIASES).get(org_label, org_label)
    if variant in ("stem", "both"):
        org_label = _stem_org(org_label)
    version = f"{KEY_VERSION}-{variant}" if event == "role" else f"{KEY_VERSION}-{variant}-{event}"
    return (org_label, event_label, version)


def build_key(
    organizer: str | None,
    raw_role: str | None,
    raw_text: str,
    variant: str = "plain",
    event: str = "role",
) -> tuple[str, str, str] | None:
    """Key v1 + varian normalisasi KB-003 + event KB-005.

    - event="role": key (org, role) — baseline KB-001..004.
    - event="jenis"/"kelompok": key (org, jenis/kelompok_kegiatan) dari
      map_kelompok_dan_jenis (0 LLM). Role tidak wajib utk event ini.
    Versi key = `v1-{variant}[-{event}]` → snapshot tiap kombinasi tidak
    tercampur.
    """
    if variant not in KEY_VARIANTS:
        raise ValueError(f"variant {variant!r} bukan {KEY_VARIANTS}")
    if event not in EVENTS:
        raise ValueError(f"event {event!r} bukan {EVENTS}")
    org = normalize_organizer(organizer, raw_text)
    if not org:
        return None
    if event == "role":
        label = normalize_role(raw_role)
    else:
        jenis, kelompok = compute_event(raw_text, raw_role, organizer)
        label = jenis if event == "jenis" else kelompok
    if not label:
        return None
    return make_key(org, label, variant, event)


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
    # KB-005: event jenis/kelompok dari map_kelompok_dan_jenis (0 LLM)
    kk = build_key("BEM FTMM Universitas Airlangga", "Peserta",
                   "SERTIFIKAT PESERTA seminar Dataquest oleh BEM FTMM",
                   variant="plain", event="kelompok")
    assert kk is not None and kk[1] not in (None, "--"), kk
    assert build_key("BEM FTMM", "Peserta", "x", event="jenis") is None or \
        build_key("BEM FTMM", "Peserta", "x", event="jenis")[2].endswith("-jenis")
    # make_key + aliases override (KB-006)
    mk = make_key("Org A", "Peserta", variant="alias", aliases={"Org A": "Org B"})
    assert mk[0] == "Org B", mk
    print("ok: kb.key canonicalizer + variants + events")


if __name__ == "__main__":
    _demo()
