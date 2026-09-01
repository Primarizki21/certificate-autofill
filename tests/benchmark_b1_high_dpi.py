"""B1 — Fast Semantic Anchor High-DPI: benchmark nomor-crop pada 49 scan cert.

Varian (korpus scan-49 yang sama, eval GT v9 + matcher v2):
  A. Baseline (tanpa crop)      — teks full-page rapid_tess (korpus cached,
                                   `baseline_rapid_tess/`). Nomor 57.6% (NC-004).
  B. Control NC-001             — teks hasil crop anchor full-page RapidOCR @3x
                                   + region re-render 6x + region rapid_tess
                                   multi-config (`corpus_nomor_crop/` cached).
                                   Nomor 60.6% (NC-001, angka pembanding resmi).
  C. B1 fast anchor (fresh)     — `resolve_number_bbox_fast` (text-search
                                   PyMuPDF dulu; fallback RapidOCR @1.5x) +
                                   region re-render 6x + region OCR:
                                   - C1 multi-config rapid_tess (kualitas = control)
                                   - C2 tess psm6 tunggal (murah, kurva tradeoff)
  D. B1-module                  — `high_dpi_crop.crop_and_ocr_number_region`
                                   (path produksi: search_for + psm 6).

Anchor B1 diukur fresh (stage timing); control & baseline dievaluasi dari
artefak cached (runtime 0). Latency control dirujuk dari artefak NC-003/004
(anchor 3.54s uncached; total 6.05s/cert, NC-004).

Gate B1 (plan, koreksi aritmetika FL-1: 60.6% = 20/33, bukan 19/33):
  - nomor scan-49 exact >= 60.6% (20/33 sel GT nomor terisi).
  - rata-rata waktu anchor B1 < 0.50s/cert.
  - pertambahan latency total pipeline <= 1.80s/cert.
  - zero regression tanggal & penyelenggara.

Usage:
    uv run python -m tests.benchmark_b1_high_dpi            # full 49 scan
    uv run python -m tests.benchmark_b1_high_dpi --probe 5  # smoke 5 cert
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("APP_ENV", "development")

import fitz

from app.services.form_mapper import map_fields_to_form
from tests.benchmark_hybrid_ocr import extract_all
from tests.evaluation_framework import EVAL_FIELDS, evaluate_row
from tests import ocr_engine as oe
from tests.benchmark_nomor_crop import CRENDER_ZOOM, RUNS_DIR, merge_full
from tests.matchers import match_field
from tests.ocr_high_dpi_anchor import resolve_number_bbox_fast

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
BASELINE_DIR = os.path.join(RUNS_DIR, "baseline_rapid_tess", "extracted_texts")
CONTROL_DIR = os.path.join(RUNS_DIR, "corpus_nomor_crop", "extracted_texts")
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
NOMOR_FIELD = "nomor_bukti_fisik_nomor_sertifikasi"

GATE_NOMOR_MIN = 60.6       # % (NC-001 control, = 20/33)
GATE_ANCHOR_MAX = 0.50      # s/cert (anchor B1; control NC-003 = 3.54s)
GATE_LATENCY_MAX = 1.80     # s/cert total pipeline delta vs baseline

# Referensi timing control dari artefak NC-003/004 (dikutip, bukan diukur ulang).
CONTROL_REF = {
    "anchor_uncached_s": 3.54,   # NC-003 stage timing
    "total_avg_s": 6.05,         # NC-004 avg (cache-assisted)
}
# Referensi latency pipeline baseline (rapid_tess full-page, scan-49):
# dari ocr_meta.json baseline_rapid_tess (avg_seconds 8.609).
BASELINE_REF_TOTAL_S = 8.609


def _load_manifest() -> dict[str, str]:
    with open(MANIFEST) as f:
        return json.load(f)


def _load_gt() -> dict[str, dict]:
    from tests.evaluation_framework import load_csv

    return {os.path.splitext(r["nama_file"])[0]: r for r in load_csv(GT_CSV)}


def _load_text(stem: str, d: str) -> str:
    with open(os.path.join(d, f"{stem}.txt")) as f:
        return "\n".join(l for l in f.read().splitlines() if not l.startswith("#")).strip()


def _pad_rect(rect: fitz.Rect, page_w: float, page_h: float) -> fitz.Rect:
    """Padding sama dgn harness NC: angka bisa di kanan label / baris berikut."""
    w = rect.width
    h = rect.height
    pad = max(5.0, 0.05 * w)
    return fitz.Rect(
        max(0.0, rect.x0 - pad),
        max(0.0, rect.y0 - pad),
        min(page_w, rect.x1 + pad + 0.20 * w),
        min(page_h, rect.y1 + pad + 1.2 * h),
    )


def _b1_crop_from_pdf(path: str, rapid) -> tuple[str | None, dict]:
    """B1: fast anchor + re-render region 6x. Return (region_png|None, stages)."""
    stages = {"anchor_s": 0.0, "region_render_s": 0.0}
    t0 = time.perf_counter()
    with open(path, "rb") as f:
        pdf_bytes = f.read()
    rect = resolve_number_bbox_fast(pdf_bytes, rapid=rapid)
    stages["anchor_s"] = time.perf_counter() - t0
    if rect is None:
        return None, stages
    doc = fitz.open(path)
    rect = _pad_rect(rect, doc[0].rect.width, doc[0].rect.height)
    t0 = time.perf_counter()
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(CRENDER_ZOOM, CRENDER_ZOOM), clip=rect, alpha=False)
    region = pix.tobytes("png")
    del pix
    doc.close()
    stages["region_render_s"] = time.perf_counter() - t0
    return region, stages


def _eval_corpus(texts: dict[str, str], gt: dict[str, dict]) -> dict:
    """Evaluasi resmi harness OCR (extract_all -> map -> evaluate_row, GT v9 + matcher v2)."""
    results = []
    details: dict[str, dict] = {}
    for stem, text in sorted(texts.items()):
        row = gt.get(stem)
        if row is None:
            continue
        mapped = map_fields_to_form(extract_all(text), tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
        fr = evaluate_row(mapped, row)
        results.append(fr)
        details[stem] = {f: {"exact": r["exact"], "pred": r["actual"]} for f, r in fr.items()}
    agg = _safe_agg(results)
    nom = agg.get(NOMOR_FIELD, {"total": 0, "exact": 0})
    return {
        "nomor_total": nom["total"],
        "nomor_exact": nom["exact"],
        "nomor_pct": (nom["exact"] / nom["total"] * 100) if nom["total"] else 0.0,
        "agg": agg,
        "details": details,
    }


def _safe_agg(results: list) -> dict:
    from tests.benchmark_hybrid_ocr import _safe_agg as _sa

    return _sa(results)


def _eval_regression(fields: list[str], texts_a: dict[str, str], texts_b: dict[str, str], gt: dict[str, dict]) -> dict:
    """Per-field: hasil evaluate_row pada teks B (B1) harus identik dgn A (baseline)."""
    out = {}
    for f in fields:
        same = tot = 0
        for stem in sorted(texts_a.keys()):
            gv = (gt.get(stem, {}).get(f, "") or "").strip()
            if not gv or gv == "-":
                continue
            ma = map_fields_to_form(extract_all(texts_a[stem]), tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
            mb = map_fields_to_form(extract_all(texts_b[stem]), tahun_akademik="2024/2025", bukti_fisik="Sertifikat")
            va = (ma.get(f).value if ma.get(f) else None) or ""
            vb = (mb.get(f).value if mb.get(f) else None) or ""
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

    texts: dict[str, dict[str, str]] = {"baseline": {}, "control": {}, "b1_multi": {}, "b1_psm6": {}, "b1_module": {}}
    lats: dict[str, list[float]] = {k: [] for k in ("b1_multi", "b1_psm6", "b1_module")}
    stage_sums = {"anchor_s": 0.0, "region_render_s": 0.0, "region_multi_s": 0.0, "region_psm6_s": 0.0, "n": 0, "n_anchor_found": 0}
    errors: list[dict] = []
    anchor_bboxes: dict[str, list] = {}

    for i, stem in enumerate(stems, 1):
        print(f"[{i}/{len(stems)}] {stem}", flush=True)
        baseline = _load_text(stem, BASELINE_DIR)
        control = _load_text(stem, CONTROL_DIR)
        texts["baseline"][stem] = baseline
        texts["control"][stem] = control

        # C. B1 fresh
        t0 = time.perf_counter()
        try:
            region, stages = _b1_crop_from_pdf(os.path.join(REPO, manifest[stem]), rapid)
            if region is not None:
                t_r0 = time.perf_counter()
                crop_multi = oe.ocr_engine("rapid_tess", region)
                t_r1 = time.perf_counter()
                crop_psm6 = oe.ocr_tess_psm(region, 6)
                t_r2 = time.perf_counter()
                stages["region_multi_s"] = t_r1 - t_r0
                stages["region_psm6_s"] = t_r2 - t_r1
                stage_sums["n"] += 1
                stage_sums["n_anchor_found"] += 1
                for k, v in stages.items():
                    stage_sums[k] = stage_sums.get(k, 0.0) + v
                b1_multi_full = merge_full(baseline, crop_multi)
                b1_psm6_full = merge_full(baseline, crop_psm6)
            else:
                stage_sums["n"] += 1
                stage_sums["anchor_s"] += stages["anchor_s"]
                b1_multi_full = baseline
                b1_psm6_full = baseline
            lats["b1_multi"].append(time.perf_counter() - t0)
            lats["b1_psm6"].append(lats["b1_multi"][-1])
        except Exception as e:  # noqa: BLE001
            errors.append({"stem": stem, "variant": "b1", "error": f"{type(e).__name__}: {e}"})
            b1_multi_full = b1_psm6_full = baseline
            lats["b1_multi"].append(time.perf_counter() - t0)
            lats["b1_psm6"].append(lats["b1_multi"][-1])
        texts["b1_multi"][stem] = b1_multi_full
        texts["b1_psm6"][stem] = b1_psm6_full

        # D. B1-module (path produksi high_dpi_crop — search_for + psm 6)
        t0 = time.perf_counter()
        try:
            from app.services.high_dpi_crop import crop_and_ocr_number_region

            with open(os.path.join(REPO, manifest[stem]), "rb") as f:
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
        texts["b1_module"][stem] = mod_full

        with open(os.path.join(texts_dir, f"{stem}.txt"), "w") as f:
            f.write(f"# B1 benchmark\n# Seconds: {lats['b1_multi'][-1]:.3f}\n\n{b1_multi_full}")
        del baseline, control
        gc.collect()

    evals = {k: _eval_corpus(v, gt) for k, v in texts.items()}
    regr = _eval_regression(
        ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "penyelenggara_kegiatan"],
        texts["baseline"], texts["b1_multi"], gt,
    )

    def _avg(l: list) -> float:
        return sum(l) / len(l) if l else 0.0

    n = stage_sums["n"] or 1
    b1_anchor_avg = stage_sums["anchor_s"] / n
    summary = {
        "created": datetime.now().isoformat(),
        "n": len(stems),
        "nomor": {k: {"total": v["nomor_total"], "exact": v["nomor_exact"], "pct": v["nomor_pct"]} for k, v in evals.items()},
        "nomor_details": evals["b1_multi"]["details"],
        "per_field_agg": {k: v["agg"] for k, v in evals.items()},
        "latency_avg": {k: _avg(lats[k]) for k in lats},
        "b1_stage_avg": {
            "anchor_s": b1_anchor_avg,
            "region_render_s": stage_sums["region_render_s"] / n,
            "region_multi_s": stage_sums.get("region_multi_s", 0.0) / n,
            "region_psm6_s": stage_sums.get("region_psm6_s", 0.0) / n,
        },
        "anchor_found_count": stage_sums["n_anchor_found"],
        "b1_added_latency_multi": (
            stage_sums["anchor_s"] + stage_sums["region_render_s"] + stage_sums.get("region_multi_s", 0.0)
        ) / n,
        "b1_added_latency_psm6": (
            stage_sums["anchor_s"] + stage_sums["region_render_s"] + stage_sums.get("region_psm6_s", 0.0)
        ) / n,
        "control_ref": CONTROL_REF,
        "regression_dates_org": regr,
        "errors": errors,
    }
    gates = {
        "nomor_b1_pct": evals["b1_multi"]["nomor_pct"],
        "nomor_gate_min": GATE_NOMOR_MIN,
        "nomor_pass": evals["b1_multi"]["nomor_pct"] >= GATE_NOMOR_MIN,
        "anchor_b1_s": b1_anchor_avg,
        "anchor_gate_max": GATE_ANCHOR_MAX,
        "anchor_pass": b1_anchor_avg < GATE_ANCHOR_MAX,
        "latency_delta_vs_baseline": summary["b1_added_latency_multi"],
        "latency_gate_max": GATE_LATENCY_MAX,
        "latency_pass": summary["b1_added_latency_multi"] <= GATE_LATENCY_MAX,
        "latency_psm6_delta": summary["b1_added_latency_psm6"],
        "latency_psm6_pass": summary["b1_added_latency_psm6"] <= GATE_LATENCY_MAX,
        "zero_regression_pass": all(v["identical"] == v["total"] for v in regr.values()),
    }
    summary["gates"] = gates

    with open(os.path.join(run_root, "eval.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(os.path.join(run_root, "meta.json"), "w") as f:
        json.dump(
            {
                "engine": "b1_high_dpi",
                "region_engines": ["rapid_tess", "tess_psm6"],
                "created": datetime.now().isoformat(),
                "stems_selected": len(stems),
                "errors": errors,
            },
            f,
            indent=2,
        )

    print("\n" + "=" * 92)
    print("B1 — nomor scan-49 (GT v9 + matcher v2)")
    print("=" * 92)
    for k in ("baseline", "control", "b1_multi", "b1_psm6", "b1_module"):
        e = evals[k]
        lat = _avg(lats[k]) if k in lats else 0.0
        print(f"{k:<10} nomor exact {e['nomor_exact']:>2}/{e['nomor_total']:>2} = {e['nomor_pct']:>5.1f}%   lat {lat:>5.2f}s/cert")
    print(f"\nb1 stage avg: anchor {b1_anchor_avg:.2f}s | region_render {stage_sums['region_render_s']/n:.2f}s "
          f"| region_multi {stage_sums.get('region_multi_s',0.0)/n:.2f}s | region_psm6 {stage_sums.get('region_psm6_s',0.0)/n:.2f}s")
    print(f"control ref (NC-003/004): anchor {CONTROL_REF['anchor_uncached_s']}s uncached | total {CONTROL_REF['total_avg_s']}s/cert")
    print(f"anchor found: {stage_sums['n_anchor_found']}/{len(stems)}")
    print(f"regression dates/org identical: {regr}")
    g = gates
    print(f"\nGATES: nomor {g['nomor_pass']} ({g['nomor_b1_pct']:.1f}% vs {g['nomor_gate_min']}%) | "
          f"anchor {g['anchor_pass']} ({g['anchor_b1_s']:.2f}s vs <{g['anchor_gate_max']}s) | "
          f"latency {g['latency_pass']} ({g['latency_delta_vs_baseline']:.2f}s vs <= {g['latency_gate_max']}s) | "
          f"zero-regression {g['zero_regression_pass']}")
    print(f"\nrun dir: {run_root}")


if __name__ == "__main__":
    main()
