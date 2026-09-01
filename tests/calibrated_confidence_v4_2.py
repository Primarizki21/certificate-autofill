"""B3 — Kalibrasi Confidence Berbasis Pola untuk Safety Net Review v4.2.

Masalah (REVIEW-001 + audit QA): confidence bundle v4.2 di-set statis tinggi
(nama_kegiatan 0.95, nomor 0.95, tingkat 0.98) sehingga field lemah TIDAK
pernah ter-flag `needs_review` walau salah — silent error. `field_needs_review`
(form_mapper) mem-flag bila confidence < 0.80.

B3 menurunkan confidence secara DINAMIS per pola ekstraksi, supaya:
- nilai yang lahir dari literal corpus (SPECTA/KARSA/Falcon/Health Buddies)
  memicu review (0.55) — event baru tidak lolos diam-diam;
- nomor yang mengalami perbaikan OCR (Roman month / DPKKA O-run) memicu
  review (0.78);
- single-date numerik (0.75) & token-pair (0.88) dikalibrasi vs interval
  eksplisit (0.95);
- rule disambiguasi router LOW-N (0.84) dibedakan dari base router (0.98).

Isolasi: modul eksperimen di `tests/` — produksi tidak disentuh. Confidence
tidak mengubah NILAI field (akurasi benchmark tidak terpengaruh), hanya flag
review.

Usage (lihat benchmark_review_v4_2.py).
"""

from __future__ import annotations

import re

from app.services.combined_extractor import _STRUCTURAL_ACT_EN, _STRUCTURAL_ACT_ID
from app.services.field_extractor import ExtractedValue

# Literal corpus yang ter-memorasi (B7 men-de-corpusing; di sini dipakai utk
# menurunkan confidence -> review, bukan utk meningkatkan nilai).
_HARDCODED_CORPUS_KEYWORDS = [
    "SPECTA",
    "KARSA",
    "FALCON",
    "HEALTH BUDDIES",
    "DIGITAL CAMPAIGN 2023",
    "GIVE YOURSELF A BREAK",
    "FROM DISCRETE MATHEMATICS",
    "AGENTIC AI",
    "AIRNOLOGY",
    "KAKIWIMA",
    "BRIEF",
    "PKKMB UNIVERSITAS AIRLANGGA",
]

_QUOTED_EVENT = re.compile(
    r'(?:kegiatan|acara|event|lomba|webinar|seminar|workshop|talkshow|competition)\s*["“]([A-Za-z0-9\s:,\-\.()]{5,100})["”]',
    re.IGNORECASE,
)

# Bukti perbaikan nomor: segmen bulan berisi 1/l/| (OCR Roman rusak) di posisi
# /ROMAN/YEAR — pola yang di-repair normalize_nomor_v5/_repair_roman_month.
_ROMAN_REPAIR_EVIDENCE = re.compile(r"/[IVXLCDM]*[1l|][IVXLCDM1l|]*/\d{4}\b", re.IGNORECASE)
# Bukti perbaikan DPKKA: prefix nomor dengan run O/0 (OCR O0 corruption).
_DPKKA_REPAIR_EVIDENCE = re.compile(
    r"\b(?:NO\.?|NOMOR|NUMBER)\s*[:.\-]?\s*[O0]{3,5}[0-9]/DPKKA", re.IGNORECASE
)
# Format nomor strict resmi tanpa modifikasi.
_STRICT_NUMBER = re.compile(
    r"\b[0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]*?/?\s*[0-9]{4}\b", re.IGNORECASE
)

# Remap confidence tanggal extract_dates_v2 -> kalibrasi B3.
_DATE_CONF_MAP = {0.95: 0.95, 0.92: 0.92, 0.94: 0.88}

CONF_ACTIVITY = {"pkkmb": 0.95, "hardcoded": 0.55, "quoted": 0.82, "structural": 0.85, "base": 0.60}
CONF_NOMOR = {"strict": 0.95, "repaired": 0.78}
CONF_DATE_SINGLE = 0.75
CONF_TINGKAT = {"base": 0.98, "disambig": 0.84}


def _activity_pattern(raw_text: str, value: str) -> str:
    """Klasifikasi pola nama_kegiatan: pkkmb | hardcoded | quoted | structural | base."""
    u = (value or "").upper()
    if "PKKMB" in u:
        return "pkkmb"
    if any(kw in u for kw in _HARDCODED_CORPUS_KEYWORDS):
        return "hardcoded"
    if _QUOTED_EVENT.search(raw_text or ""):
        return "quoted"
    if _STRUCTURAL_ACT_ID.search(raw_text or "") or _STRUCTURAL_ACT_EN.search(raw_text or ""):
        return "structural"
    return "base"


def _nomor_pattern(raw_text: str) -> str:
    if _DPKKA_REPAIR_EVIDENCE.search(raw_text or "") or _ROMAN_REPAIR_EVIDENCE.search(raw_text or ""):
        return "repaired"
    return "strict"


def calibrate_v4_2_confidence(
    fields: dict[str, ExtractedValue], raw_text: str
) -> dict[str, ExtractedValue]:
    """Set confidence per pola (B3) pada field hasil bundle v4.2. Nilai tidak berubah."""
    out = dict(fields)

    ev = out.get("nama_kegiatan_sertifikasi")
    if ev and ev.value:
        pat = _activity_pattern(raw_text, ev.value)
        out["nama_kegiatan_sertifikasi"] = ExtractedValue(ev.value, CONF_ACTIVITY[pat], f"calibrated:{pat}")

    ev = out.get("nomor_bukti_fisik_nomor_sertifikasi")
    if ev and ev.value:
        pat = _nomor_pattern(raw_text)
        out["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(ev.value, CONF_NOMOR[pat], f"calibrated:{pat}")

    for f in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        ev = out.get(f)
        if ev and ev.value:
            conf = _DATE_CONF_MAP.get(round(ev.confidence, 2), CONF_DATE_SINGLE)
            out[f] = ExtractedValue(ev.value, conf, f"calibrated:{ev.source}")

    ev = out.get("tingkat")
    if ev and ev.value and isinstance(ev.source, str) and ev.source.startswith("router"):
        conf = CONF_TINGKAT["disambig"] if ("disambig_" in ev.source or "direktur_kemahasiswaan_unair" in ev.source) else CONF_TINGKAT["base"]
        out["tingkat"] = ExtractedValue(ev.value, conf, f"calibrated:{ev.source}")

    return out


    import os
    import sys
+
+    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
+    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))
     from app.services.field_extractor import extract_certificate_fields
    from app.services.field_extractor import extract_certificate_fields

    t = "Nomor: 123/FTMM/1/2024, dilaksanakan pada 5/3/2024 oleh BEM FTMM"
    fields = extract_certificate_fields(t)
    cal = calibrate_v4_2_confidence(fields, t)
    print("nomor conf:", cal["nomor_bukti_fisik_nomor_sertifikasi"].confidence)
    print("date conf:", cal["waktu_mulai_pelaksanaan"].confidence)
    assert cal["nomor_bukti_fisik_nomor_sertifikasi"].confidence == 0.78  # Roman-repair flag
    assert cal["waktu_mulai_pelaksanaan"].confidence == 0.75
    print("ok: calibrate_v4_2_confidence")
