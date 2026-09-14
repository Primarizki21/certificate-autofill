"""Warm up raw text cache sequentially with memory guard.

Runs single-process with explicit garbage collection to prevent WSL OOM/crashes.
Skips already cached files.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.ocr_fallback import extract_text_with_ocr
from app.services.pdf_fast_path import extract_text_with_pymupdf
from tests.ocr_engine import ocr_rapid, ocr_tess


def main() -> None:
    manifest_path = Path("certs_unified/manifest.json")
    cache_dir = Path("docs/experiments/EXP-ALL6F-PROMPT-001/raw_texts")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"Total manifest docs: {len(manifest)}")
    cached_count = len(list(cache_dir.glob("*.txt")))
    print(f"Already cached: {cached_count}")

    t_start = time.perf_counter()
    processed = 0

    for idx, doc in enumerate(manifest, start=1):
        fname = doc["nama_file"].strip()
        stem = Path(fname).stem
        cache_file = cache_dir / f"{stem}.txt"

        if cache_file.is_file() and cache_file.stat().st_size > 0:
            continue
        file_path = Path(doc["unified_path"])
        if not file_path.exists():
            file_path = Path(doc.get("source_path", ""))

        if not file_path.exists():
            print(f"[{idx}/{len(manifest)}] {fname}: MISSING FILE")
            continue

        t0 = time.perf_counter()
        file_bytes = file_path.read_bytes()
        ext = file_path.suffix.lower()

        if ext == ".pdf":
            fast = extract_text_with_pymupdf(file_bytes)
            txt = fast.text.strip()
            if len(txt) >= 60:
                raw_text = txt
                method = "pymupdf"
            else:
                raw_text = extract_text_with_ocr(file_bytes).strip()
                method = "ocr_fallback"
        elif ext in (".png", ".jpeg", ".jpg"):
            rapid_txt = ocr_rapid(file_bytes)
            tess_txt = ocr_tess(file_bytes)
            raw_text = f"{rapid_txt}\n{tess_txt}".strip()
            method = "image_ocr"
        else:
            raw_text = ""
            method = "unsupported"
        tmp_file = cache_file.with_suffix(".tmp")
        tmp_file.write_text(raw_text, encoding="utf-8")
        os.replace(tmp_file, cache_file)
        dur = time.perf_counter() - t0
        processed += 1
        print(f"[{idx}/{len(manifest)}] {fname}: {method} ({len(raw_text)} chars, {dur:.2f}s)")
        # Periodic memory cleanup
        del file_bytes
        gc.collect()

    total_dur = time.perf_counter() - t_start
    final_cached = len(list(cache_dir.glob("*.txt")))
    print(f"\nDone. Processed {processed} new docs. Total cached: {final_cached}/{len(manifest)} ({total_dur:.2f}s)")


if __name__ == "__main__":
    main()
