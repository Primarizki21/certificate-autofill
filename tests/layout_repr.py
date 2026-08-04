"""v8 Phase 3 — layout-aware input representation (LayIE-LLM / EMNLP 2025).

Pipeline hari ini meratakan PDF dengan page.get_text("text") sehingga posisi
dan ukuran font hilang. Modul ini membangun dua representasi dari PyMuPDF
page.get_text("dict"):

  - markdown: baris title (font besar) diberi prefix '## ', body polos.
  - annotated: tiap baris diberi hint struktural [TITLE]/[BODY]/[SMALL].

Untuk sertifikat hasil scan (pymupdf hampir tidak menghasilkan teks), konten
kembali ke teks ekstraksi yang sudah ada (mengandung OCR) — layout tidak
menambah apa pun pada gambar murni.

Eksperimen murni; production pdf_fast_path.py tidak disentuh.
"""

import json
import os
import re

import fitz

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "layout_manifest.json")
ORIG_TEXTS_DIR = os.path.join(
    REPO_ROOT, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts",
)

# Ambang: PDF yang menghasilkan teks pymupdf < MIN_PYMUPDF_CHARS dianggap scan.
MIN_PYMUPDF_CHARS = 60
# Ambang ukuran font relatif terhadap median untuk deteksi title/small.
TITLE_RATIO = 1.35
SMALL_RATIO = 0.8


def _lines_from_page(page) -> list[dict]:
    """Kumpulkan baris (teks, ukuran font maks, posisi y, x) dari satu halaman."""
    raw = page.get_text("dict")
    lines = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue
            max_size = max(s["size"] for s in spans)
            bbox = line.get("bbox") or spans[0].get("bbox") or (0, 0, 0, 0)
            lines.append({
                "text": text,
                "size": max_size,
                "y": bbox[1],
                "x": bbox[0],
            })
    return lines


def _median(sizes: list[float]) -> float:
    if not sizes:
        return 12.0
    s = sorted(sizes)
    return s[len(s) // 2]


def _render(lines: list[dict], median_size: float, mode: str) -> list[str]:
    out = []
    for ln in lines:
        ratio = ln["size"] / median_size if median_size else 1.0
        text = re.sub(r"[ \t]+", " ", ln["text"])
        if mode == "markdown":
            if ratio >= TITLE_RATIO:
                out.append(f"## {text}")
            else:
                out.append(text)
        elif mode == "annotated":
            if ratio >= TITLE_RATIO:
                out.append(f"[TITLE] {text}")
            elif ratio <= SMALL_RATIO:
                out.append(f"[SMALL] {text}")
            else:
                out.append(f"[BODY] {text}")
    return out


def layout_text(pdf_path: str, mode: str) -> str | None:
    """Representasi layout dari PDF. None bila PDF tidak punya teks (scan)."""
    doc = fitz.open(pdf_path)
    try:
        all_lines = []
        for page in doc:
            all_lines.extend(_lines_from_page(page))
        if not all_lines:
            return None
        if sum(len(ln["text"]) for ln in all_lines) < MIN_PYMUPDF_CHARS:
            return None
        median = _median([ln["size"] for ln in all_lines])
        rendered = _render(all_lines, median, mode)
        return "\n".join(rendered).strip()
    finally:
        doc.close()


def build_layout_corpus(mode: str, out_dir: str) -> int:
    """Generate korpus layout ke out_dir; fallback teks asli utk cert scan."""
    manifest = json.load(open(MANIFEST_PATH))
    os.makedirs(out_dir, exist_ok=True)
    used_layout = 0
    used_fallback = 0
    for stem, pdf_path in manifest.items():
        layout = layout_text(pdf_path, mode)
        if layout:
            content = layout
            used_layout += 1
        else:
            orig = os.path.join(ORIG_TEXTS_DIR, stem + ".txt")
            if os.path.exists(orig):
                with open(orig) as f:
                    content = "\n".join(
                        l for l in f.read().splitlines() if not l.startswith("#")
                    ).strip()
            else:
                content = ""
            used_fallback += 1
        with open(os.path.join(out_dir, stem + ".txt"), "w") as f:
            f.write(content + "\n")
    print(f"[layout:{mode}] {used_layout} layout + {used_fallback} fallback -> {out_dir}")
    return used_layout


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["markdown", "annotated"])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    build_layout_corpus(args.mode, args.out)
