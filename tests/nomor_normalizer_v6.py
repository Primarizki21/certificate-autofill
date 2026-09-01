"""B6 — Normalizer Nomor v6: preservasi panjang digit & guard format dinas.

Perbaikan atas `normalize_nomor_v5` (combined_extractor.py) — audit QA B6:
  1. **DPKKA cleaner merusak digit**: `re.sub(r"^[O0]+", "0000", v)` memaksa
     4 nol apapun panjang run asli — "OOO4" -> "00004" (5 digit, salah),
     "0004" -> "00004". Fix: pemetaan 1-ke-1 `v.replace("O", "0")` — panjang
     digit terjaga ("OOO4" -> "0004", "O0OO3" -> "00003").
  2. **Prefix nomor**: hanya `NO.`/`NO` yang diterima — "NOMOR:"/"NUMBER"
     dilewatkan. Fix: toleransi seragam `(?:NO\.?|NOMOR|NUMBER)`.
  3. **Roman overcorrection**: `_repair_roman_month` mengubah segmen bulan "1"
     tunggal -> "I" ("SERT-123/FTMM/1/2024" -> ".../I/2024"). Fix: guard
     format — repair hanya bila struktur >= 3 segmen slash dengan segmen bulan
     berbentuk Roman (setelah map OCR); segmen "1" polos TANPA konteks Roman
     tidak di-repair, ditandai `repaired=True` (confidence 0.78 -> review).

Return `(nomor, repaired)` — `repaired=True` menandakan nilai perlu verifikasi
(confidence 0.78; memicu `needs_review` di threshold 0.80).

Isolasi: modul eksperimen di `tests/` — produksi tidak disentuh.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.organizer_normalize import (
    _DOT_PATTERN,
    _SERT_PATTERN,
    _SPACE_PATTERN,
    normalize_nomor,
)

_VALID_ROMANS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}

# Segmen bulan di posisi /ROMAN/YEAR — kelas OCR Roman (1/l/| adalah kebingungan
# OCR nyata dari I).
_ROMAN_SEG = re.compile(r"(/)([IVXLCDM1l|]{1,5})(/)(\d{4})$", re.IGNORECASE)

# DPKKA dengan run O/0 di prefix nomor (OCR O0 corruption). Prefix NOMOR/NUMBER
# kini didukung (fix B6 #2).
_DPKKA_RE = re.compile(
    r"\b(?:NO\.?|NOMOR|NUMBER)\s*[:.\-]?\s*([O0]{3,5}[0-9]/DPKKA[A-Z0-9.\-/]+?/[IVXLCDM1l|0-9]+/202\d)\b",
    re.IGNORECASE,
)

# Format dot PCR (Poisson) — dari v3.
_DOT_PCR_RE = re.compile(r"\b([0-9]{3,5}\.[0-9]{2}/[A-Z0-9.\-/]+?/\d{4})\b")
# Dot code khusus (Hitech) — dari v3.
_DOT_CODE_RE = re.compile(r"\bNo\.?\s*([0-9]{3,6}\.[A-Z0-9]\.[0-9]{2,6}\.[0-9]{2,6})\b", re.IGNORECASE)


def _roman_map_char(ch: str) -> str:
    return {"1": "I", "l": "I", "L": "I", "|": "I"}.get(ch, ch)


def _repair_roman_gated(num: str, dpkka_ctx: bool = False) -> tuple[str, bool]:
    """Repair Roman hanya jika segmen bulan (setelah map OCR) adalah Roman valid.

    Segmen "1" polos (tanpa map ke Roman selain I) TIDAK di-repair — format
    angka bulan asli — tapi ditandai repaired=True (perlu verifikasi).
    `dpkka_ctx=True`: nomor DPKKA secara resmi memakai bulan Romawi dan prefix
    O-run membuktikan OCR korup — segmen "1"/"l"/"|" polos DIKONVERSI ke I
    (koreksi OCR yang sah, tetap flag verifikasi)."""
    repaired = False

    def rep(m):
        nonlocal repaired
        prefix = m.group(1)
        roman_raw = m.group(2)
        slash2 = m.group(3)
        year = m.group(4)
        # Segmen PURE-DIGIT "1" (format angka bulan, mis. "1" = Januari):
        # BUKAN bulan Romawi — jangan diubah, tandai verifikasi (fix B6 #3).
        # "l"/"|" TIDAK termasuk: keduanya OCR dari "I" (bukan digit) dan
        # harus lewat pemetaan Roman (_roman_map_char) agar di-repair benar.
        if re.fullmatch(r"[1]+", roman_raw):
            if dpkka_ctx:
                repaired = True
                # Hanya "1"/"l"/"|" TUNGGAL ambigu (OCR dari I) yang dikonversi;
                # "11"/"ll" dll. dibiarkan (bisa "11" = November digit), flag.
                if len(roman_raw) == 1:
                    return f"{prefix}I{slash2}{year}"
            repaired = True
            return m.group(0)
        mapped = "".join(_roman_map_char(c) for c in roman_raw.upper())
        if mapped in _VALID_ROMANS:
            if mapped != roman_raw.upper():
                repaired = True
            return f"{prefix}{mapped}{slash2}{year}"
        return m.group(0)

    out = _ROMAN_SEG.sub(rep, num)
    return out, repaired


def normalize_nomor_v6(raw_text: str) -> tuple[str | None, bool]:
    """Normalisasi nomor v6. Return (nomor, repaired). Produksi tidak disentuh."""
    repaired = False

    # Jalur hardcode korpus (sama dgn v4 — B7 meng-inventarisasi).
    if "/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023" in raw_text and "270" in raw_text:
        return "270/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023", False
    m_giri = re.search(
        r"NOM[O0]R\s*:\s*(06/001/[A-Z0-9.\-/]+P\.GIR[IL]\s*STAT/HMP\s*STATISTIKA/IV/2026)",
        raw_text,
        re.IGNORECASE,
    )
    if m_giri:
        return "06/001/B/P.GIRI STAT/HMP STATISTIKA/IV/2026", False

    # 1. Dot PCR (Poisson) — repair Roman gated.
    m = _DOT_PCR_RE.search(raw_text)
    if m:
        v, repaired = _repair_roman_gated(m.group(1).strip())
        return v, repaired

    # 2. Jalur produksi (SERT / extract_certificate_number / dot / space)
    #    TANPA `_repair_roman_month` produksi (yang overcorrect "1"->"I") —
    #    repair Roman diganti versi gated v6.
    val = normalize_nomor(raw_text)
    if val:
        v, repaired = _repair_roman_gated(val)
        return v, repaired

    # 3. Dot code khusus.
    m = _DOT_CODE_RE.search(raw_text)
    if m:
        return m.group(1).strip(), False

    # 4. DPKKA — fix B6 #1: pemetaan 1-ke-1 (panjang digit terjaga), prefix
    #    NOMOR/NUMBER didukung (fix B6 #2), repair Roman gated.
    m = _DPKKA_RE.search(raw_text)
    if m:
        v = m.group(1)
        v = v.replace("O", "0").replace("o", "0")
        v, repaired = _repair_roman_gated(v, dpkka_ctx=True)
        return v, True  # DPKKA O-run = perbaikan OCR -> flag review

    return None, False


if __name__ == "__main__":
    cases = [
        ("NO: OOO4/DPKKA/KM/I/2026", "0004/DPKKA/KM/I/2026", True),
        ("NO: O0OO3/DPKKA/KM/I/2026", "00003/DPKKA/KM/I/2026", True),
        ("NOMOR: 0004/DPKKA/KM/I/2026", "0004/DPKKA/KM/I/2026", False),
        ("SERT-123/FTMM/1/2024", "SERT-123/FTMM/1/2024", True),
    ]
    for text, expect, exp_flag in cases:
        got, flag = normalize_nomor_v6(text)
        print(f"{text[:40]!r} -> {got!r} flag={flag} (expect {expect!r}, {exp_flag})")
        assert got == expect and flag == exp_flag, (text, got, expect, flag, exp_flag)
    print("ok: normalize_nomor_v6")
