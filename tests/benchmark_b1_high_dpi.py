"""B1 — Fast Semantic Anchor High-DPI: benchmark 3+1 varian nomor-crop pada 49 scan cert.

Varian:
  A. Baseline (tanpa crop) — nomor dari teks full-page rapid_tess (korpus cached).
  B. Control NC-001 — anchor full-page RapidOCR @ render 3.0x + region re-render
     6.0x + region OCR rapid_tess multi-config. Pembanding resmi (60.6% nomor).
  C. B1 fast anchor — `resolve_number_bbox_fast` (text-search PyMuPDF dulu,
     fallback RapidOCR @ 1.5x) + region re-render 6.0x + region OCR SAMA dgn B.
  D. B1-module — `high_dpi_crop.crop_and_ocr_number_region` (path produksi,
     search_for + psm 6). Diukur utk melengkapi klaim plan (scan: 0 text layer).

Gate B1 (dari plan, koreksi aritmetika FL-1: 60.6% = 20/33, BUKAN 19/33):
  - nomor scan-49 exact >= 60.6% (20/33 sel GT nomor terisi).
  - rata-rata waktu anchor B1 < 0.50s/cert (anchor control NC-003: 3.54s).
  - pertambahan latency total (B1 vs A) <= 1.80s/cert.
  - zero regression tanggal & penyelenggara (crop hanya mengubah nomor).

Anchor control di-cache dari `corpus_nomor_crop_retry_ctrl_cache/anchors.json`
(NC-004) — cache hit = skip full-page RapidOCR (anchor sudah terukur NC-003/004).

Usage:
    uv run python -m tests.benchmark_b1_high_dpi            # full 49 scan
    uv run python -m tests.benchmark_b1_high_dpi --probe 5  # smoke 5 cert
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("APP_ENV", "development")

import fitz

from app.services.field_extractor import extract_certificate_number
from tests import ocr_engine as oe
from tests.benchmark_nomor_crop import (
    CRENDER_ZOOM,
    RUNS_DIR,
    ZOOM,
    _crop_number_from_pdf,
    _line_bbox,
    find_number_line,
    merge_full,
)
from tests.matchers import match_field
from tests.ocr_high_dpi_anchor import resolve_number_bbox_fast

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
BASELINE_DIR = os.path.join(RUNS_DIR, "baseline_rapid_tess", "extracted_texts")
CONTROL_ANCHOR_CACHE = os.path.join(
    RUNS_DIR, "corpus_nomor_crop_retry_ctrl_cache", "anchors.json"
)
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
NOMOR_FIELD = "nomor_bukti_fisik_nomor_sertifikasi"

GATE_NOMOR_MIN = 60.6       # % (NC-001 control, = 20/33)
GATE_ANCHOR_MAX = 0.50      # s/cert (anchor B1; control NC-003 = 3.54s)
GATE_LATENCY_MAX = 1.80     # s/cert total pipeline delta vs baseline

# Gate check hanya pada varian B1 (C); A/B = pembanding.
GATE_VARIANT = "b1_fast"


def _load_manifest() -> dict[str, str]:
    with open(MANIFEST) as f:
        return json.load(f)


def _load_gt() -> dict[str, dict]:
    from tests.evaluation_framework import load_csv

    return {os.path.splitext(r["nama_file"])[0]: r for r in load_csv(GT_CSV)}


def _load_baseline_text(stem: str) -> str:
    with open(os.path.join(BASELINE_DIR, f"{stem}.txt")) as f:
        return "\n".join(l for l in f.read().splitlines() if not l.startswith("#")).strip()


def _render_region_from_pdf(path: str, rect: fitz.Rect) -> bytes:
    """Re-render region pada zoom 6.0x dari PDF asli (piksel nyata)."""
    doc = fitz.open(path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(CRENDER_ZOOM, CRENDER_ZOOM), clip=rect, alpha=False)
    region = pix.tobytes("png")
    del pix
    doc.close()
    return region


def _pad_rect(rect: fitz.Rect, page_w: float, page_h: float) -> fitz.Rect:
    """Padding sama dgn harness: angka bisa di kanan label / baris berikut."""
    w = rect.width
    h = rect.height
    pad = max(5.0, 0.05 * w)
    return fitz.Rect(
        max(0.0, rect.x0 - pad),
        max(0.0, rect.y0 - pad),
        min(page_w, rect.x1 + pad + 0.20 * w),
        min(page_h, rect.y1 + pad + 1.2 * h),
    )


def _b1_crop_from_pdf(path: str, rapid, anchor_bbox=None) -> tuple[str, dict]:
    """B1: fast anchor + re-render 6x + region OCR (control)."""
    stages = {"anchor_s": 0.0, "region_render_s": 0.0, "region_s": 0.0}
    t0 = time.perf_counter()
    if anchor_bbox is None:
        with open(path, "rb") as f:
            pdf_bytes = f.read()
        rect = resolve_number_bbox_fast(pdf_bytes, rapid=rapid)
    else:
        rect = fitz.Rect(*anchor_bbox)
    stages["anchor_s"] = time.perf_counter() - t0
    if rect is None:
        return "", {"bbox": None, "stages": stages}

    doc = fitz.open(path)
    rect = _pad_rect(rect, doc[0].rect.width, doc[0].rect.height)
    t0 = time.perf_counter()
    region = _render_region_from_pdf(path, rect)
    stages["region_render_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    text = oe.ocr_engine("rapid_tess", region)
    stages["region_s"] = time.perf_counter() - t0
    return text, {"bbox": [rect.x0, rect.y0, rect.x1, rect.y1], "stages": stages}


def _eval_nomor(texts: dict[str, str], gt: dict[str, dict]) -> dict:
    total = 0
    exact = 0
    details: dict[str, dict] = {}
    for stem, text in sorted(texts.items()):
        gv = (gt.get(stem, {}).get(NOMOR_FIELD, "") or "").strip()
        if not gv or gv == "-":
            continue
        pv = extract_certificate_number(text) or ""
        res = match_field(gv, pv, NOMOR_FIELD)
        total += 1
        if res["exact"]:
            exact += 1
        details[stem] = {"gt": gv, "pred": pv, "exact": res["exact"]}
    return {
        "total": total,
        "exact": exact,
        "pct": (exact / total * 100) if total else 0.0,
        "details": details,
    }


def _eval_regression(fields: list[str], texts_a: dict[str, str], texts_b: dict[str, str], gt: dict[str, dict]) -> dict:
    """Per-field exact pada teks B (B1) vs A (baseline) — harus identik (0 regresi)."""
    out = {}
    from app.services.field_extractor import extract_certificate_fields
    from app.services.form_mapper import map_fields_to_form

    for f in fields:
        same = 0
        tot = 0
        for stem in sorted(texts_a.keys()):
            gv = (gt.get(stem, {}).get(f, "") or "").strip()
            if not gv or gv == "-":
                continue
            ea = extract_certificate_fields(texts_a[stem])
            eb = extract_certificate_fields(texts_b[stem])
            pa = map_fields_to_form(ea, texts_a[stem], bukti_fisik="Sertifikat")
            pb = map_fields_to_form(eb, texts_b[stem], bukti_fisik="Sertifikat")
            va = (pa.get(f).value if pa.get(f) else None) or ""
            vb = (pb.get(f).value if pb.get(f) else None) or ""
            tot += 1
            if va == vb:
                same += 1
        out[f] = {"identical": same, "total": tot}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe", type=int, default=0, help="batasi N cert pertama (smoke)")
    p.add_argument("--out", type=str, default=None)
    args = p.parse_args()

    run_root = args.out or os.path.join(
        RUNS_DIR, f"b1_high_dpi_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    texts_dir = os.path.join(run_root, "extracted_texts")
    os.makedirs(texts_dir, exist_ok=True)

    manifest = _load_manifest()
    classification = oe.classify_manifest(manifest)
    stems = sorted(s for s, c in classification.items() if c["scan"])
    if args.probe:
        stems = stems[: args.probe]
    gt = _load_gt()
    rapid = oe._get_rapid()
    assert rapid is not None, "RapidOCR tidak tersedia"

    anchor_cache: dict[str, list] = {}
    if os.path.exists(CONTROL_ANCHOR_CACHE):
        with open(CONTROL_ANCHOR_CACHE) as f:
            anchor_cache = json.load(f)

    texts: dict[str, dict[str, str]] = {"baseline": {}, "control": {}, "b1_fast": {}, "b1_module": {}}
    meta: dict[str, dict] = {k: {} for k in texts}
    anchors_b1: dict[str, list] = {}
    lats = {k: [] for k in ("baseline", "control", "b1_fast", "b1_module")}
    stage_sums = {
        k: {"anchor_s": 0.0, "region_render_s": 0.0, "region_s": 0.0, "n": 0}
        for k in ("control", "b1_fast", "b1_module")
    }
    errors: list[dict] = []

    for i, stem in enumerate(stems, 1):
        print(f"[{i}/{len(stems)}] {stem}", flush=True)
        baseline = _load_baseline_text(stem)
        texts["baseline"][stem] = baseline
        path = os.path.join(REPO, manifest[stem])
        row = {"baseline": baseline}

        # B. Control NC-001 (anchor full-page RapidOCR @3x; cache hit skip anchor)
        t0 = time.perf_counter()
        try:
            ctrl_text, info = _crop_number_from_pdf(
                path, rapid, anchor_bbox=anchor_cache.get(stem)
            )
            ctrl_full = merge_full(baseline, ctrl_text)
        except Exception as e:  # noqa: BLE001
            errors.append({"stem": stem, "variant": "control", "error": f"{type(e).__name__}: {e}"})
            ctrl_full = baseline
            info = {"bbox": None, "stages": {}}
        lats["control"].append(time.perf_counter() - t0)
        row["control"] = ctrl_full
        if info.get("stages"):
            s = info["stages"]
            stage_sums["control"]["n"] += 1
            for k in ("anchor_s", "region_render_s", "region_s"):
                stage_sums["control"][k] += s.get(k, 0.0)
        if info.get("bbox"):
            anchors_b1[stem] = info["bbox"]

        # C. B1 fast anchor (yg diukur)
        t0 = time.perf_counter()
        try:
            b1_text, b1_info = _b1_crop_from_pdf(path, rapid)
            b1_full = merge_full(baseline, b1_text)
        except Exception as e:  # noqa: BLE001
            errors.append({"stem": stem, "variant": "b1_fast", "error": f"{type(e).__name__}: {e}"})
            b1_full = baseline
            b1_info = {"bbox": None, "stages": {}}
        lats["b1_fast"].append(time.perf_counter() - t0)
        row["b1_fast"] = b1_full
        if b1_info.get("stages"):
            s = b1_info["stages"]
            stage_sums["b1_fast"]["n"] += 1
            for k in ("anchor_s", "region_render_s", "region_s"):
                stage_sums["b1_fast"][k] += s.get(k, 0.0)

        # D. B1-module (path produksi high_dpi_crop — search_for + psm 6)
        t0 = time.perf_counter()
        try:
            from app.services.high_dpi_crop import crop_and_ocr_number_region

            with open(path, "rb") as f:
                pdf_bytes = f.read()
            mod_num = crop_and_ocr_number_region(pdf_bytes)
            mod_full = (
                f"NOMOR : {mod_num}\n{baseline}"
                if mod_num and mod_num != extract_certificate_number(baseline)
                else baseline
            )
        except Exception as e:  # noqa: BLE001
            errors.append({"stem": stem, "variant": "b1_module", "error": f"{type(e).__name__}: {e}"})
            mod_full = baseline
        lats["b1_module"].append(time.perf_counter() - t0)
        row["b1_module"] = mod_full

        for k, v in row.items():
            texts[k][stem] = v
        with open(os.path.join(texts_dir, f"{stem}.txt"), "w") as f:
            f.write(f"# B1 benchmark\n# Seconds: {lats['b1_fast'][-1]:.3f}\n\n{row['b1_fast']}")

        del row
        gc.collect()

    # ---- Evaluasi nomor ----
    evals = {k: _eval_nomor(v, gt) for k, v in texts.items()}
    regr = _eval_regression(
        ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "penyelenggara_kegiatan"],
        texts["baseline"],
        texts["b1_fast"],
        gt,
    )

    def _avg(l: list) -> float:
        return sum(l) / len(l) if l else 0.0

    def _stage_avg(key: str, stage: str) -> float:
        s = stage_sums[key]
        return s[stage] / s["n"] if s["n"] else 0.0

    summary = {
        "created": datetime.now().isoformat(),
        "stems": stems,
        "n": len(stems),
        "nomor": {k: {kk: vv for kk, vv in v.items() if kk != "details"} for k, v in evals.items()},
        "latency_avg_total": {k: _avg(lats[k]) for k in lats},
        "stages_avg": {
            k: {st: _stage_avg(k, st) for st in ("anchor_s", "region_render_s", "region_s")}
            for k in ("control", "b1_fast")
        },
        "regression_dates_org": regr,
        "errors": errors,
        "anchors_b1": anchors_b1,
        "gates": {
            "nomor_b1_pct": evals["b1_fast"]["pct"],
            "nomor_gate_min": GATE_NOMOR_MIN,
            "nomor_pass": evals["b1_fast"]["pct"] >= GATE_NOMOR_MIN,
            "anchor_b1_s": _stage_avg("b1_fast", "anchor_s"),
            "anchor_gate_max": GATE_ANCHOR_MAX,
            "anchor_pass": _stage_avg("b1_fast", "anchor_s") < GATE_ANCHOR_MAX,
            "anchor_control_s": _stage_avg("control", "anchor_s"),
            "latency_delta_b1_vs_baseline": _avg(lats["b1_fast"]) - _avg(lats["baseline"]),
            "latency_gate_max": GATE_LATENCY_MAX,
            "latency_pass": (_avg(lats["b1_fast"]) - _avg(lats["baseline"])) <= GATE_LATENCY_MAX,
            "zero_regression_pass": all(v["identical"] == v["total"] for v in regr.values()),
        },
    }

    with open(os.path.join(run_root, "eval.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(os.path.join(run_root, "anchors.json"), "w") as f:
        json.dump(anchors_b1, f, indent=2)
    with open(os.path.join(run_root, "meta.json"), "w") as f:
        json.dump(
            {
                "engine": "b1_high_dpi",
                "region_engine": "rapid_tess",
                "created": datetime.now().isoformat(),
                "stems_selected": len(stems),
                "errors": errors,
            },
            f,
            indent=2,
        )

    print("\n" + "=" * 90)
    print("B1 — nomor scan-49 (GT v9 + matcher v2)")
    print("=" * 90)
    for k in ("baseline", "control", "b1_fast", "b1_module"):
        e = evals[k]
        print(f"{k:<10} nomor exact {e['exact']:>2}/{e['total']:>2} = {e['pct']:>5.1f}%   total-lat {_avg(lats[k]):>5.2f}s/cert")
    print(f"\nstage avg: control anchor {summary['gates']['anchor_control_s']:.2f}s | b1_fast anchor {summary['gates']['anchor_b1_s']:.3f}s")
    print(f"latency delta B1 vs baseline: {summary['gates']['latency_delta_b1_vs_baseline']:.2f}s/cert (gate <= {GATE_LATENCY_MAX}s)")
    print(f"regression dates/org identical: {regr}")
    g = summary["gates"]
    print(f"\nGATES: nomor {g['nomor_pass']} ({g['nomor_b1_pct']:.1f}% vs {g['nomor_gate_min']}%) | "
          f"anchor {g['anchor_pass']} ({g['anchor_b1_s']:.3f}s vs <{g['anchor_gate_max']}s) | "
          f"latency {g['latency_pass']} | zero-regression {g['zero_regression_pass']}")
    print(f"\nrun dir: {run_root}")


if __name__ == "__main__":
    main()
