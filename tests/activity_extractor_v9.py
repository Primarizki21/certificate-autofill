"""B5 — Ekstraktor Kegiatan v9: structural semantic anchors anti-bleed.

Perbaikan atas `extract_activity_v8` (combined_extractor.py) — audit QA B5:
  1. `_STRUCTURAL_ACT_ID` kekurangan kata penutup variasi Indonesia
     ("diadakan", "diadakan oleh", "yang diadakan", "bekerja sama dengan",
     "bertempat di") -> capture menelan penyelenggara ("yang diadakan oleh
     BEM FTMM" ikut menjadi nama kegiatan).
  2. `_STRUCTURAL_ACT_EN` kekurangan "hosted by", "presented by",
     "in cooperation with", "in collaboration with".
  3. Fallback `$` tanpa batas di closing alternation -> capture meluas ke
     akhir teks saat kata penutup tidak baku. Diganti batas ketat:
     panjang <= 120 karakter dan <= 18 kata; gagal -> fall through.
  4. Sanitasi residu: strip tanda petik tak sepasang, newline -> spasi.
  5. Tier v7 (extractor generik produksi) punya celah closer yang sama
     ("diadakan oleh"/"hosted by" tidak memotong) -> hasil v7 dipotong
     dengan `_anti_bleed_cut` (closer "masa bakti"/"tahun" dikecualikan
     karena v6 sengaja mempertahankannya di output).

Urutan prioritas MENGIKUTI v8: literal corpus v7 dulu (B7 meng-inventarisasi),
lalu EN anchor, ID anchor, quoted event, fallback v7. Produksi tidak disentuh.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import extract_activity_v7

# Closers ID: kata penutup yang membatasi judul kegiatan (tanpa `$` fallback).
_ACT_ID_CLOSERS = (
    r"yang\s+diselenggarakan\s+oleh|yang\s+diselenggarakan|diselenggarakan\s+oleh|diselenggarakan"
    r"|yang\s+diadakan\s+oleh|yang\s+diadakan|diadakan\s+oleh|diadakan"
    r"|yang\s+bekerja\s+sama\s+dengan|bekerja\s+sama\s+dengan|bertempat\s+di"
    r"|held\s+by|organized\s+by|hosted\s+by|presented\s+by"
    r"|pada\s+tanggal|dilaksanakan|with\s+theme|dengan\s+tema|periode|masa\s+bakti|tahun"
)

_STRUCTURAL_ACT_ID_V9 = re.compile(
    r"(?:sebagai|partisipasinya\s+sebagai)\s+[A-Za-z0-9\s/]+?\s+"
    r"(?:pada|dalam|di|atas\s+partisipasinya\s+dalam)\s+"
    r"(?:kegiatan|acara|event|program|kompetisi|lomba)?\s*"
    r"(?:yang\s+berjudul|entitled|titled)?\s*[\"“']?"
    r"([A-Za-z0-9\s:,\-\.()]+?)"
    r"[\"”']?\s*(?:" + _ACT_ID_CLOSERS + r")",
    re.IGNORECASE,
)

_STRUCTURAL_ACT_EN_V9 = re.compile(
    r"in\s+recognition\s+of\s+(?:their|his|her)\s+participation\s+as\s+[A-Za-z0-9\s/]+?\s+in\s+"
    r"(?:the\s+event\s+entitled)?\s*[\"“']?"
    r"([A-Za-z0-9\s:,\-\.()]+?)"
    r"[\"”']?\s*(?:organized\s+by|held\s+by|hosted\s+by|presented\s+by"
    r"|in\s+cooperation\s+with|in\s+collaboration\s+with|on\s+[A-Za-z]+|\d{1,2})",
    re.IGNORECASE,
)

_QUOTED_EVENT_V9 = re.compile(
    r'(?:kegiatan|acara|event|lomba|webinar|seminar|workshop|talkshow|competition)\s*["“]([A-Za-z0-9\s:,\-\.()]{5,100})["”]',
    re.IGNORECASE,
)

MAX_CAPTURE_CHARS = 120
MAX_CAPTURE_WORDS = 18

# Penanda bleed pada hasil tier v7 (extractor generik produksi punya celah
# closer yang sama: "diadakan oleh"/"hosted by" tidak memotong capture).
# Urutan longest-first. "masa bakti"/"tahun" DIKECUALIKAN — v6 sengaja
# mempertahankannya di output ("Kepengurusan ... masa bakti tahun 2024").
_BLEED_CLOSERS = [
    "in collaboration with",
    "in cooperation with",
    "yang bekerja sama dengan",
    "bekerja sama dengan",
    "yang diselenggarakan oleh",
    "diselenggarakan oleh",
    "yang diadakan oleh",
    "diadakan oleh",
    "bertempat di",
    "yang diselenggarakan",
    "diselenggarakan",
    "yang diadakan",
    "diadakan",
    "hosted by",
    "presented by",
    "organized by",
    "held by",
    "pada tanggal",
    "with theme",
    "dengan tema",
    "periode",
]


def _sanitize_capture(cand: str) -> str:
    """Sanitasi residu: petik tak sepasang dibuang, newline -> satu spasi."""
    v = re.sub(r"\s+", " ", cand or "")
    if v.count('"') % 2 == 1:
        v = v.replace('"', "")
    if v.count("'") % 2 == 1:
        v = v.replace("'", "")
    v = v.strip().strip("\"'“”")
    return v


def _valid_capture(cand: str) -> bool:
    v = _sanitize_capture(cand)
    if len(v) < 5:
        return False
    if len(v) > MAX_CAPTURE_CHARS:
        return False
    if len(v.split()) > MAX_CAPTURE_WORDS:
        return False
    return " " in v


def _anti_bleed_cut(value: str) -> str:
    """Potong hasil tier v7 pada penanda bleed pertama (penyelenggara/tanggal)."""
    v = _sanitize_capture(value)
    low = v.lower()
    best = None
    for closer in _BLEED_CLOSERS:
        idx = low.find(closer)
        if idx != -1 and (best is None or idx < best):
            best = idx
    if best is None:
        return v
    cut = v[:best].strip()
    if len(cut) >= 5:
        return cut
    return v


def extract_activity_v9(text: str) -> str | None:
    """Ekstraksi nama kegiatan v9: anchor semantik struktural anti-bleed."""
    t = text or ""
    v7_act = extract_activity_v7(t)
    if v7_act and len(v7_act) >= 5:
        cut = _anti_bleed_cut(v7_act)
        # Tier v7: hanya anti-bleed + sanity cap longgar (korpus punya nilai
        # sah >120 char, mis. "Kepengurusan ... Universitas Airlangga" ~135);
        # batas ketat 120/18 hanya untuk capture anchor struktural.
        if 5 <= len(cut) <= 200:
            return cut
        v7_act = None

    m_en = _STRUCTURAL_ACT_EN_V9.search(t)
    if m_en and _valid_capture(m_en.group(1)):
        return _sanitize_capture(m_en.group(1))

    m_id = _STRUCTURAL_ACT_ID_V9.search(t)
    if m_id and _valid_capture(m_id.group(1)):
        return _sanitize_capture(m_id.group(1))

    m_q = _QUOTED_EVENT_V9.search(t)
    if m_q:
        cand = _sanitize_capture(m_q.group(1))
        if len(cand) >= 5:
            return cand

    return v7_act


if __name__ == "__main__":
    cases = [
        (
            "sebagai Panitia dalam acara Karya Inovasi Mahasiswa 2026 yang diadakan oleh BEM FTMM "
            "pada tanggal 10 Maret 2026",
            "Karya Inovasi Mahasiswa 2026",
        ),
    ]
    for text, expect in cases:
        got = extract_activity_v9(text)
        print(f"{got!r} == {expect!r}: {got == expect}")
        assert got == expect, (got, expect)
    print("ok: extract_activity_v9")
