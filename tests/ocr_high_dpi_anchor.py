"""B1 — Fast Semantic Anchor untuk High-DPI Region Crop (re-try NC-003/NC-004).

Masalah NC-003/004: floor latency nomor-crop ≈ 3.5s/cert = full-page RapidOCR
pada render ZOOM=3.0 (9x piksel) yang dipakai HANYA untuk mencari koordinat
baris nomor ("anchor"). Anchor penuh itu bukan kerja ekstraksi — hanya mencari
kotak.

B1 — anchor dua tingkat yang lebih murah:
  1. **Fast text-search (PyMuPDF)**: `page.search_for()` keyword nomor
     (`NOMOR`/`Nomor`/`NO.`/`No.`/`NUMBER`/`SERTIFIKAT`); validasi bahwa blok
     teks tersebut berdekatan dengan pola angka atau slash dinas
     (`\\d{1,5}\\s*/` atau pola nomor strict). 0 biaya OCR.
  2. **Fallback scan (RapidOCR murah)**: bila PDF murni scan gambar (tanpa
     text layer), RapidOCR pada render ZOOM_FAST=1.5x (≈1/4 piksel vs anchor
     lama 3.0x) hanya untuk koordinat baris nomor; bbox dikonversi balik ke
     ruang koordinat halaman.

Hasil = `fitz.Rect` dalam koordinat halaman PDF (dipakai untuk re-render
region pada zoom 6.0x oleh `high_dpi_crop` / harness benchmark).

Isolasi: modul eksperimen di `tests/` — produksi `backend/app/` tidak disentuh.
"""

from __future__ import annotations

import re

import fitz  # PyMuPDF

SEARCH_KEYWORDS: list[str] = ["NOMOR", "Nomor", "NO.", "No.", "NUMBER", "SERTIFIKAT"]

# Adjacency: label nomor berdekatan dengan angka/slash (mis. "NO. 123/ABC/2024").
_NUM_ADJACENT = re.compile(r"\d{1,5}\s*/")
# Pola nomor dinas strict — sama dengan _STRICT_NUMBER di harness benchmark.
_STRICT_NUMBER = re.compile(r"[0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]*?/?\s*[0-9]{4}", re.IGNORECASE)
# Keyword baris nomor (dipakai saat fallback RapidOCR — mirror benchmark_nomor_crop).
_KEYWORD = re.compile(r"\bNOMOR\b|\bNO\.\b|\bNUMBER\b", re.IGNORECASE)

# Render cepat untuk anchor fallback: 1.5x (anchor lama = 3.0x).
ZOOM_FAST = 1.5


def _block_has_number(block_text: str) -> bool:
    """Blok teks dianggap memuat nomor bila ada pola angka-slash dinas."""
    t = re.sub(r"\s+", " ", block_text or "")
    return bool(_STRICT_NUMBER.search(t)) or bool(_NUM_ADJACENT.search(t))


def _search_text_anchor(page: fitz.Page) -> fitz.Rect | None:
    """Tingkat 1: cari keyword lewat text layer, validasi adjacency angka."""
    blocks = page.get_text("blocks")
    for kw in SEARCH_KEYWORDS:
        kw_u = kw.upper()
        for b in blocks:
            text = b[4]
            if kw_u not in text.upper():
                continue
            if _block_has_number(text):
                return fitz.Rect(b[0], b[1], b[2], b[3])
        rects = page.search_for(kw)
        for rect in rects:
            padded = fitz.Rect(
                max(0.0, rect.x0 - 20.0),
                max(0.0, rect.y0 - 10.0),
                min(page.rect.width, rect.x1 + 400.0),
                min(page.rect.height, rect.y1 + 80.0),
            )
            near = page.get_text("text", clip=padded)
            if _block_has_number(near):
                return rect
    return None


def _item_text(item: list) -> str:
    """Teks item OCR. RapidOCR saat ini = word-level `[box, text, conf]`;
    versi lama = line-level `[box, [(text, conf), ...]]`. Dukung keduanya."""
    t = item[1] if len(item) > 1 else ""
    if isinstance(t, str):
        return t.strip()
    if isinstance(t, (list, tuple)):
        return " ".join(str(w[1]) for w in t).strip()
    return str(t)


def _group_word_items_into_lines(items: list) -> list[tuple[list, str]]:
    """Kelompokkan item word-level jadi baris (y-center dekat) -> (items, teks baris)."""
    lines: list[tuple[list, str, float]] = []
    for item in items:
        box = item[0]
        ys = [p[1] for p in box]
        yc = (min(ys) + max(ys)) / 2.0
        h = max(ys) - min(ys)
        placed = False
        for i, (mitems, mtext, myc) in enumerate(lines):
            if abs(yc - myc) < max(0.6 * h, 14.0):
                mitems.append(item)
                mtext += " " + _item_text(item)
                lines[i] = (mitems, mtext, (myc * len(mitems) + yc) / (len(mitems) + 1))
                placed = True
                break
        if not placed:
            lines.append(([item], _item_text(item), yc))
    return [(mitems, mtext) for mitems, mtext, _ in lines]


def _line_union_bbox(items: list) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for item in items:
        for p in item[0]:
            xs.append(float(p[0]))
            ys.append(float(p[1]))
    return min(xs), min(ys), max(xs), max(ys)


def _find_number_line_rapid(items: list) -> list | None:
    """Cari baris nomor pada hasil RapidOCR (word-level ATAU line-level):
    keyword label dulu, lalu pola nomor strict — join kata dalam baris sama.
    Return daftar item OCR (grup baris) atau None."""
    lines = _group_word_items_into_lines(items)
    for mitems, text in lines:
        if _KEYWORD.search(text):
            return mitems
    for mitems, text in lines:
        if _STRICT_NUMBER.search(text):
            return mitems
    return None


def _rapid_fallback_anchor(page: fitz.Page, rapid) -> fitz.Rect | None:
    """Tingkat 2: RapidOCR murah pada render 1.5x — hanya koordinat baris nomor."""
    if rapid is None:
        return None
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM_FAST, ZOOM_FAST), alpha=False)
        png = pix.tobytes("png")
        del pix
        result, _ = rapid(png)
        if not result:
            return None
        found = _find_number_line_rapid(result)
        if found is None:
            return None
        x0, y0, x1, y1 = _line_union_bbox(found)
        # Koordinat gambar (zoom 1.5x) -> koordinat halaman PDF.
        return fitz.Rect(x0 / ZOOM_FAST, y0 / ZOOM_FAST, x1 / ZOOM_FAST, y1 / ZOOM_FAST)
    except Exception:
        return None


def resolve_number_bbox_fast(pdf_bytes: bytes, rapid=None) -> fitz.Rect | None:
    """Resolve kotak baris nomor: text-search dulu, fallback RapidOCR murah.

    Return `fitz.Rect` dalam koordinat halaman pertama, atau None bila tidak
    ditemukan. `rapid` = callable RapidOCR (mis. `ocr_engine._get_rapid()`);
    hanya dipakai pada PDF tanpa text layer (scan).
    """
    if not pdf_bytes:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            return None
        page = doc[0]
        rect = _search_text_anchor(page)
        if rect is not None:
            doc.close()
            return rect
        rect = _rapid_fallback_anchor(page, rapid)
        doc.close()
        return rect
    except Exception:
        return None


if __name__ == "__main__":
    # Self-check ringan: bbox dari PDF ber-teks-layer harus ketemu tanpa OCR.
    import json
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from tests.ocr_engine import classify_manifest

    manifest_path = os.path.join(os.path.dirname(__file__), "layout_manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    classification = classify_manifest(manifest)
    embedded = [s for s, c in sorted(classification.items()) if not c["scan"]]
    assert embedded, "butuh >=1 cert embedded di manifest"
    stem = embedded[0]
    with open(os.path.join(os.path.dirname(__file__), "..", manifest[stem]), "rb") as f:
        pdf_bytes = f.read()
    rect = resolve_number_bbox_fast(pdf_bytes, rapid=None)
    print(f"ok: resolve_number_bbox_fast embedded[{stem}] -> {rect}")
    assert rect is not None and rect.width > 0 and rect.height > 0
