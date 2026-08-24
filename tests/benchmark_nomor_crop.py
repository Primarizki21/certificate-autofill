"""Eksperimen preprocessing nomor sertifikat (GATE HYB-001 → NC-001).

Eksperimen OCR — TIDAK menyentuh pipeline produksi (`ocr_fallback.py` tetap
otoritatif).

Idea: bottleneck OCR scan adalah nomor sertifikat (baseline rapid_tess 57.6%
di GT v9, semua engine gagal di digit). Daripada ganti engine, perbaiki
kualitas glyph di REGION nomor: cari baris yang mengandung keyword
`NOMOR`/`NO.`/`NUMBER` (atau pola nomor) lewat bounding-box RapidOCR,
crop region itu, upscale, lalu re-OCR dengan baseline rapid_tess.

Robust (TANPA hardcode koordinat template):
- anchor = SEMANTIK teks (keyword/pola nomor), bukan posisi absolut
- kalau anchor tak ditemukan -> fallback ke baseline penuh (no-regress by construction)
- merge: teks crop hanya dipakai bila mengandung nomor STRICT
  (extract_certificate_number); selain itu baseline apa adanya

Usage:
  uv run python -m tests.benchmark_nomor_crop build \
      --out tests/benchmark_runs/ocr_experiment/corpus_nomor_crop
  uv run python -m tests.benchmark_nomor_crop run \   # build + eval sekali
      --out tests/benchmark_runs/ocr_experiment/corpus_nomor_crop \
      --csv Ground_Truth_Sertifikat_v9.csv
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import resource
import sys
import time
from io import BytesIO
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("APP_ENV", "development")

from PIL import Image

from app.services.field_extractor import extract_certificate_number
from tests import ocr_engine as oe
from tests.ocr_engine import classify_manifest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
RUNS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "ocr_experiment")
DEFAULT_BASELINE = os.path.join(RUNS_DIR, "baseline_rapid_tess", "extracted_texts")
DEFAULT_GT = os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv")
ZOOM = 3.0
CROP_SCALE = 3  # upscale crop (hanya utk sumber PNG)
CRENDER_ZOOM = 6.0  # re-render region PDF di zoom tinggi = real pixels

_KEYWORD = re.compile(r"\bNOMOR\b|\bNO\.\b|\bNUMBER\b", re.I)
_STRICT_NUMBER = re.compile(
    r"[0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]*?/?\s*[0-9]{4}", re.I
)


def _load_manifest() -> dict[str, str]:
    with open(MANIFEST) as f:
        return json.load(f)


def _line_bbox(item: list) -> tuple[float, float, float, float]:
    box = item[0]
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return min(xs), min(ys), max(xs), max(ys)


def find_number_line(items: list) -> list | None:
    """Cari baris nomor: keyword `NOMOR`/`NO.` dulu, lalu pola nomor strict."""
    for item in items:
        if _KEYWORD.search((item[1] or "").strip()):
            return item
    for item in items:
        if _STRICT_NUMBER.search((item[1] or "").strip()):
            return item
    return None


# NC-002: region-OCR MURAH — tes mana yg pertahankan recovery nomor NC-001
# (rapid_tess = control ~5.2s/cert) dgn cost <<. Pilih via --region-engine.
_REGION_ENGINES: dict[str, Callable[[bytes], str]] = {
    "rapid_tess": lambda b: oe.ocr_engine("rapid_tess", b),
    "rapid": lambda b: oe.ocr_engine("rapid", b),
    "rapid_tess_psm13": lambda b: oe.merge_unique_lines(
        [oe.ocr_engine("rapid", b), oe.ocr_tess_psm(b, 13)]
    ),
    "tess_psm6": lambda b: oe.ocr_tess_psm(b, 6),
    "tess_psm13": lambda b: oe.ocr_tess_psm(b, 13),
    "rapid_tess_psm6": lambda b: oe.merge_unique_lines(
        [oe.ocr_engine("rapid", b), oe.ocr_tess_psm(b, 6)]
    ),
    "tess_lines_psm7": lambda b: oe.ocr_tess_lines_psm7(b),
}
REGION_ENGINE_KEY = "rapid_tess"


def ocr_region(png_bytes: bytes) -> str:
    return _REGION_ENGINES[REGION_ENGINE_KEY](png_bytes)


def merge_full(baseline_text: str, crop_text: str) -> str:
    """Voting disagreement: crop dipakai hanya bila nomornya beda dari baseline.
    Extractor lebih dulu menangkap pola ber-label NOMOR, jadi prepend label.
    Spasi OCR dinormalisasi dulu (noise spacing != sinyal digit)."""
    base_num = extract_certificate_number(baseline_text)
    crop_num = extract_certificate_number(re.sub(r"\s+", "", crop_text)) if crop_text else None
    if crop_num and crop_num != base_num:
        return f"NOMOR : {crop_num}\n{crop_text}\n{baseline_text}"
    return baseline_text


def _crop_number_from_pdf(path: str, rapid, anchor_bbox=None) -> tuple[str, dict]:
    """Anchor + crop nomor. Return (teks_region, info): info.bbox utk anchor
    cache (NC-003), info.stages = timing per tahap (siapa makan latency?)."""
    stages = {"render_s": 0.0, "anchor_s": 0.0, "region_render_s": 0.0, "region_s": 0.0}
    is_png = path.lower().endswith(".png")
    doc = None
    t0 = time.perf_counter()
    if is_png:
        img = Image.open(path).convert("RGB")
        buf = BytesIO()
        img.save(buf, "PNG")
        png = buf.getvalue()
    else:
        import fitz
        doc = fitz.open(path)
        matrix = fitz.Matrix(ZOOM, ZOOM)
        pix = doc[0].get_pixmap(matrix=matrix, alpha=False)
        png = pix.tobytes("png")
        del pix
        img = Image.open(BytesIO(png)).convert("RGB")
    stages["render_s"] = time.perf_counter() - t0

    bbox = list(anchor_bbox) if anchor_bbox is not None else None
    if bbox is None:
        t0 = time.perf_counter()
        try:
            result, _ = rapid(png)
        except Exception:
            if doc is not None:
                doc.close()
            return "", {"bbox": None, "stages": stages}
        stages["anchor_s"] = time.perf_counter() - t0
        if not result:
            if doc is not None:
                doc.close()
            return "", {"bbox": None, "stages": stages}
        item = find_number_line(result)
        if item is None:
            if doc is not None:
                doc.close()
            return "", {"bbox": None, "stages": stages}
        x0, y0, x1, y1 = _line_bbox(item)
        bbox = [x0, y0, x1, y1]
    x0, y0, x1, y1 = bbox
    w = x1 - x0
    h = y1 - y0
    pad = max(5, int(0.05 * w))
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(img.width, x1 + pad + int(0.20 * w))  # angka bisa di kanan label
    y1 = min(img.height, y1 + pad + int(1.2 * h))  # angka bisa di baris berikut
    t0 = time.perf_counter()
    if is_png:
        crop = img.crop((x0, y0, x1, y1)).convert("RGB").resize(
            (int((x1 - x0) * CROP_SCALE), int((y1 - y0) * CROP_SCALE)), Image.LANCZOS
        )
        buf = BytesIO()
        crop.save(buf, "PNG")
        region = buf.getvalue()
    else:
        # PDF: re-render REGION di zoom tinggi — utk scan native dpi tinggi atau
        # teks vektor ini memberi piksel NYATA (bukan interpolasi dari render 3x).
        rect = fitz.Rect(x0 / ZOOM, y0 / ZOOM, x1 / ZOOM, y1 / ZOOM)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(CRENDER_ZOOM, CRENDER_ZOOM), clip=rect, alpha=False)
        region = pix.tobytes("png")
        del pix
        doc.close()
    stages["region_render_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    text = ocr_region(region)
    stages["region_s"] = time.perf_counter() - t0
    return text, {"bbox": bbox, "stages": stages}


def cmd_build(args) -> dict:
    global REGION_ENGINE_KEY
    REGION_ENGINE_KEY = args.region_engine
    manifest = _load_manifest()
    classification = classify_manifest(manifest)
    run_root = args.out or os.path.join(RUNS_DIR, "corpus_nomor_crop")
    texts_dir = os.path.join(run_root, "extracted_texts")
    os.makedirs(texts_dir, exist_ok=True)
    anchor_cache: dict[str, list] = {}
    if args.anchor_json and os.path.exists(args.anchor_json):
        with open(args.anchor_json) as f:
            anchor_cache = json.load(f)

    if args.mem_cap_gb:
        cap = int(args.mem_cap_gb * 1024 ** 3)
        resource.setrlimit(resource.RLIMIT_AS, (cap, resource.RLIM_INFINITY))

    stems = sorted(s for s, c in classification.items() if c["scan"])
    rapid = oe._get_rapid()
    n_ok = 0
    n_crop = 0
    n_anchor_miss = 0
    errors: list[dict] = []
    lats: list[float] = []
    new_anchors: dict[str, list] = {}
    n_hits = 0
    n_timed = 0
    stage_sums = {"render_s": 0.0, "anchor_s": 0.0, "region_render_s": 0.0, "region_s": 0.0}

    for stem in stems:
        out_file = os.path.join(texts_dir, f"{stem}.txt")
        if args.skip_existing and os.path.exists(out_file):
            continue
        base_path = os.path.join(args.baseline, f"{stem}.txt")
        if not os.path.exists(base_path):
            errors.append({"stem": stem, "error": "baseline txt tak ada"})
            continue
        with open(base_path) as f:
            baseline = "\n".join(l for l in f.read().splitlines() if not l.startswith("#")).strip()
        info = {"bbox": None, "stages": {}}
        t0 = time.perf_counter()
        try:
            crop_text, info = _crop_number_from_pdf(
                os.path.join(REPO, manifest[stem]), rapid, anchor_bbox=anchor_cache.get(stem)
            )
            full = merge_full(baseline, crop_text)
        except Exception as e:  # noqa: BLE001 — satu cert gagal tidak boleh bunuh run
            errors.append({"stem": stem, "error": f"{type(e).__name__}: {e}"})
            crop_text = ""
            full = baseline
        elapsed = round(time.perf_counter() - t0, 3)
        lats.append(elapsed)
        if stem in anchor_cache:
            n_hits += 1
        if info["stages"]:
            n_timed += 1
            for k, v in info["stages"].items():
                stage_sums[k] += v
        if info["bbox"] is not None:
            new_anchors[stem] = info["bbox"]
        if full != baseline:
            n_crop += 1
        if not crop_text:
            n_anchor_miss += 1
        if full.strip():
            n_ok += 1
            with open(out_file, "w") as f:
                f.write(f"# Engine: nomor_crop\n# Seconds: {elapsed}\n\n{full}")
        del full, crop_text
        gc.collect()

    meta = {
        "engine": "nomor_crop",
        "region_engine": REGION_ENGINE_KEY,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "subset": "scan",
        "zoom": ZOOM,
        "crop_scale": CROP_SCALE,
        "stems_selected": len(stems),
        "stems_ok": n_ok,
        "scan_count": len(stems),
        "embedded_count": 0,
        "stems_cropped": n_crop,
        "stems_anchor_miss": n_anchor_miss,
        "errors": errors,
        "latency": {
            "avg_seconds": round(sum(lats) / len(lats), 3) if lats else None,
            "median_seconds": round(sorted(lats)[len(lats) // 2], 3) if lats else None,
        },
        "stages": {
            k: round(stage_sums[k] / n_timed, 3) if n_timed else None for k in stage_sums
        },
        "anchor_cache": {
            "arg": args.anchor_json,
            "loaded": len(anchor_cache),
            "hits": n_hits,
            "collected": len(new_anchors),
        },
    }
    with open(os.path.join(run_root, "ocr_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    merged = dict(anchor_cache)
    merged.update(new_anchors)
    anchors_out = os.path.join(run_root, "anchors.json")
    with open(anchors_out, "w") as f:
        json.dump(merged, f, indent=2)
    if args.anchor_json and os.path.abspath(args.anchor_json) != os.path.abspath(anchors_out):
        with open(args.anchor_json, "w") as f:
            json.dump(merged, f, indent=2)
    print(f"\n[crop] ok={n_ok}/{len(stems)} cropped={n_crop} anchor_miss={n_anchor_miss}")
    print(f"Latency: {meta['latency']}")
    print(f"Stages avg/cert: {meta['stages']}")
    print(f"Anchors: loaded={len(anchor_cache)} collected={len(new_anchors)} -> {anchors_out}")
    print(f"Output: {texts_dir}")
    return meta


def cmd_run(args) -> None:
    run_root = args.out or os.path.join(RUNS_DIR, "corpus_nomor_crop")
    texts_dir = os.path.join(run_root, "extracted_texts")
    cmd_build(args)
    from types import SimpleNamespace
    from tests import benchmark_ocr
    benchmark_ocr.cmd_eval(
        SimpleNamespace(texts=texts_dir, csv=args.csv, out=os.path.join(run_root, "eval.json"))
    )


def demo() -> None:
    """Self-check: anchor + merge rule."""
    fake_items = [
        ([[10, 10], [300, 10], [300, 40], [10, 40]], "NOMOR : 106/STF.E/HOLOGY7.0/x1t/2024", 0.95),
        ([[10, 50], [300, 50], [300, 80], [10, 80]], "SERTIFIKAT PELATIHAN", 0.97),
    ]
    item = find_number_line(fake_items)
    assert item is not None and "NOMOR" in item[1], "anchor keyword harus menang"

    fake_items2 = [
        ([[10, 50], [300, 50], [300, 80], [10, 80]], "GARBAGE 12/STF E G 7. X1/2024", 0.6),
    ]
    assert find_number_line(fake_items2) is not None, "anchor pola nomor harus ketemu"

    # merge: crop beda -> menang; crop garbage -> baseline utuh; crop sama -> baseline
    m1 = merge_full("SERTIFIKAT A\nNOMOR: 106/STF.E/X1/2024", "106 / STF.E / HOLOGY 7.0 / X1T / 2024")
    assert extract_certificate_number(m1) == "106/STF.E/HOLOGY7.0/X1T/2024", "nomor crop harus menang"
    m2 = merge_full("SERTIFIKAT A\nNOMOR: 106/STF.E/X1/2024", "TEXT GARBAGE TANPA NOMOR")
    assert m2 == "SERTIFIKAT A\nNOMOR: 106/STF.E/X1/2024", "crop garbage tak boleh mengubah baseline"
    m3 = merge_full("SERTIFIKAT A\nNOMOR: 106/STF.E/X1/2024", "106/STF.E/X1/2024")
    assert m3 == "SERTIFIKAT A\nNOMOR: 106/STF.E/X1/2024", "crop sama tak boleh duplikat"
    print("ok: nomor_crop anchor + merge rules")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("build", cmd_build), ("run", cmd_run)):
        b = sub.add_parser(name)
        b.add_argument("--out", default=None, help="root run dir (default corpus_nomor_crop)")
        b.add_argument("--baseline", default=DEFAULT_BASELINE, help="korpus baseline rapid_tess")
        b.add_argument("--csv", default=DEFAULT_GT, help="GT CSV (default v9)")
        b.add_argument("--skip-existing", action="store_true")
        b.add_argument("--mem-cap-gb", type=float, default=6.5)
        b.add_argument(
            "--region-engine", default="rapid_tess",
            choices=sorted(_REGION_ENGINES),
            help="OCR utk region nomor (NC-002: murah vs control rapid_tess)",
        )
        b.add_argument("--anchor-json", default=None,
                       help="JSON {stem: bbox} anchor cache — skip full-page anchor OCR saat trial ulang")
        b.set_defaults(fn=fn)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    demo()
    main()
