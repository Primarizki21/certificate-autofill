"""B8 — Benchmark komparasi 3 arah: Baseline v9 vs Staging v4.2 vs Composite B8.

Korpus teks offline (run_20260728_131835, 74 cert), GT v9 + matcher v2.
Metrik: MACRO exact/fuzzy all-cells (440) + framework non-empty (310, konvensi
handoff: tanpa tingkat) + per-field + zero-regression per field vs v4.2.

Tabel tambahan (report-only):
  - OOD curve composite (mutation + noise 10/25/50%, pola B2).
  - HYB-003: organizer rapid-only merge pada korpus OCR scan-49 (dari artefak
    `hybrid_rapid_org` — 0 OCR baru).

Gate B8 (plan):
  - MACRO exact all-cells >= 78.0% (v4.2 = 76.82%).
  - Framework MACRO exact >= 89.0% (v4.2 = 87.42%).
  - Zero regression per field vs v4.2.
  - 4 lapis pembuktian empiris (CV B4, OOD B2, katalog B7, review B3).

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_composite_v4_candidate
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.composite_v4_candidate import apply_composite_v4_candidate
from tests.matchers import match_field
from tests.ood_probe import (
    EVAL_FIELDS,
    SEED,
    eval_corpus,
    free_inst_macro,
    inject_noise,
    load_gt,
    load_texts,
    mutate,
    offline_fields,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"composite_v4_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "composite_v4_candidate_report.md")

GATE_ALLCELLS = 78.0
GATE_FRAMEWORK = 89.0

# Framework resmi (konvensi handoff v44): 310 sel = semua field kecuali tingkat.
FRAMEWORK_FIELDS = [f for f in EVAL_FIELDS if f != "tingkat"]


def run_pipeline(raw_text: str, version: str) -> dict[str, str]:
    extracted = extract_certificate_fields(raw_text)
    if version == "v9":
        # offline produksi: extractor dasar + form map (pola OOD-001 baseline)
        mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
        return {f: (mapped.get(f).value if mapped.get(f) else "") for f in EVAL_FIELDS}
    if version == "v4_2":
        extracted = apply_combined_v4_2(extracted, raw_text)
    elif version == "composite":
        extracted = apply_composite_v4_candidate(extracted, raw_text)
    mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
    return {k: v.value or "" for k, v in mapped.items()}


def eval_all(texts, gt) -> dict:
    """Per-field exact + all-cells + framework."""
    stats = {}
    for ver in ("v9", "v4_2", "composite"):
        per = {f: {"exact": 0, "fuzzy": 0, "cell_total": 0} for f in EVAL_FIELDS}
        details = {}
        for stem, text in texts.items():
            row = gt.get(stem, {})
            pred = run_pipeline(text, ver)
            details[stem] = pred
            for f in EVAL_FIELDS:
                gv = (row.get(f) or "").strip()
                # ALL-CELLS (konvensi handoff v44): SEMUA sel GT dievaluasi,
                # termasuk placeholder "-"/"" (pred tidak akan pernah exact).
                per[f]["cell_total"] += 1
                res = match_field(gv, pred.get(f, ""), f)
                per[f]["exact"] += int(res["exact"])
                per[f]["fuzzy"] += int(res["fuzzy"])
        all_total = sum(p["cell_total"] for p in per.values())
        all_exact = sum(p["exact"] for p in per.values())
        all_fuzzy = sum(p["fuzzy"] for p in per.values())
        # Framework: hanya sel GT TERISI, tanpa tingkat (310 = 74+55+55+52+74).
        fw_total = 0
        for s in gt:
            for f in FRAMEWORK_FIELDS:
                gv = (gt[s].get(f) or "").strip()
                if gv and gv != "-":
                    fw_total += 1
        fw_exact = sum(per[f]["exact"] for f in FRAMEWORK_FIELDS)
        fw_fuzzy = sum(per[f]["fuzzy"] for f in FRAMEWORK_FIELDS)
        stats[ver] = {
            "allcells_exact_pct": all_exact / all_total * 100 if all_total else 0,
            "allcells_fuzzy_pct": all_fuzzy / all_total * 100 if all_total else 0,
            "framework_exact_pct": fw_exact / fw_total * 100 if fw_total else 0,
            "framework_fuzzy_pct": fw_fuzzy / fw_total * 100 if fw_total else 0,
            "per_field": {f: {k: v for k, v in p.items()} for f, p in per.items()},
        }
        stats[ver]["details"] = details
    return stats


def ood_curve_composite(texts, gt) -> dict:
    """Kurva OOD composite (pola B2): mutation + noise 10/25/50%, drop MACRO exact."""
    mutated = {s: mutate(t) for s, t in texts.items()}
    rng = random.Random(SEED)
    noisy = {lvl: {s: inject_noise(t, lvl, rng) for s, t in texts.items()} for lvl in (0.10, 0.25, 0.50)}

    def offline_composite(text: str) -> dict[str, str]:
        extracted = extract_certificate_fields(text)
        extracted = apply_composite_v4_candidate(extracted, text)
        mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
        return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}

    base = eval_corpus(texts, gt, "composite_base", offline_composite)
    mut = eval_corpus(mutated, gt, "composite_mut", offline_composite)
    curve = {"baseline_macro": base["macro_exact"], "mutation_macro": mut["macro_exact"],
             "free_inst_base": free_inst_macro(base)[0], "free_inst_mutation": free_inst_macro(mut)[0]}
    curve["mutation_free_inst_drop_pt"] = (curve["free_inst_base"] - curve["free_inst_mutation"]) * 100
    for lvl in (0.10, 0.25, 0.50):
        n = eval_corpus(noisy[lvl], gt, f"composite_noise_{lvl}", offline_composite)
        curve[f"noise_{lvl:.0%}"] = {"macro": n["macro_exact"],
                                     "drop_pt": (base["macro_exact"] - n["macro_exact"]) * 100}
    return curve


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()
    stats = eval_all(texts, gt)

    v9, v42, comp = stats["v9"], stats["v4_2"], stats["composite"]
    gates = {
        "allcells_exact": comp["allcells_exact_pct"],
        "allcells_gate": GATE_ALLCELLS,
        "allcells_pass": comp["allcells_exact_pct"] >= GATE_ALLCELLS,
        "framework_exact": comp["framework_exact_pct"],
        "framework_gate": GATE_FRAMEWORK,
        "framework_pass": comp["framework_exact_pct"] >= GATE_FRAMEWORK,
        "zero_regression": {},
    }
    for f in EVAL_FIELDS:
        gates["zero_regression"][f] = {
            "v42": v42["per_field"][f]["exact"],
            "comp": comp["per_field"][f]["exact"],
            "pass": comp["per_field"][f]["exact"] >= v42["per_field"][f]["exact"],
        }
    gates["zero_regression_pass"] = all(g["pass"] for g in gates["zero_regression"].values())

    curve = ood_curve_composite(texts, gt)

    summary = {
        "created": datetime.now().isoformat(),
        "stats": stats,
        "gates": gates,
        "ood_curve": curve,
        "gt": os.path.basename(GT_CSV),
    }
    with open(os.path.join(OUT_DIR, "summary_composite_v4.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    lines = [
        "# B8 — Composite Candidate: v9 vs v4.2 vs Composite (N=74, 0 LLM)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | korpus teks offline.",
        "",
        "## 3-Arah Benchmark",
        "",
        "| Metrik | v9 offline | v4.2 staging | **Composite B8** |",
        "|---|---|---|---|",
        f"| MACRO exact (all-cells) | {v9['allcells_exact_pct']:.2f}% | {v42['allcells_exact_pct']:.2f}% | **{comp['allcells_exact_pct']:.2f}%** |",
        f"| MACRO fuzzy (all-cells) | {v9['allcells_fuzzy_pct']:.2f}% | {v42['allcells_fuzzy_pct']:.2f}% | **{comp['allcells_fuzzy_pct']:.2f}%** |",
        f"| MACRO exact (framework) | {v9['framework_exact_pct']:.2f}% | {v42['framework_exact_pct']:.2f}% | **{comp['framework_exact_pct']:.2f}%** |",
        "",
        "| Field exact | v9 | v4.2 | Composite |",
        "|---|---|---|---|",
    ]
    for f in EVAL_FIELDS:
        p = lambda v: f"{v['per_field'][f]['exact']}/{v['per_field'][f]['cell_total']}"
        lines.append(f"| {f} | {p(v9)} | {p(v42)} | {p(comp)} |")
    lines += [
        "",
        f"**Gate all-cells >= {GATE_ALLCELLS}%**: {'PASS' if gates['allcells_pass'] else 'FAIL'} "
        f"({comp['allcells_exact_pct']:.2f}%)",
        f"**Gate framework >= {GATE_FRAMEWORK}%**: {'PASS' if gates['framework_pass'] else 'FAIL'} "
        f"({comp['framework_exact_pct']:.2f}%)",
        f"**Zero regression per field**: {'PASS' if gates['zero_regression_pass'] else 'FAIL'}",
        "",
        "> Komponen B4/B5/B6 adalah pengerasan OOD (0 perubahan nilai di korpus ini —",
        "> kasus audit QA adalah OOD/sintetik). Composite == v4.2 secara numerik;",
        "> gate akurasi plan (>=78.0%) TIDAK tercapai karena target mengasumsikan",
        "> bug korpus-visible yang ternyata tidak ada.",
        "",
        "## Tabel 1 — Stratified 5-Fold CV router v7 (B4)",
        "",
        "Lihat `docs/report/b4_router_hardening_report.md` — min-fold precision 100%, coverage 64/74.",
        "",
        "## Tabel 2 — Kurva OOD Composite (mutation + noise)",
        "",
        f"| Kondisi | MACRO exact | drop vs baseline |",
        "|---|---|---|",
        f"| baseline | {curve['baseline_macro']:.1%} | — |",
        f"| mutation | {curve['mutation_macro']:.1%} | {-(curve['mutation_macro'] - curve['baseline_macro']) * 100:+.1f}pt |",
        f"| mutation free-inst | {curve['free_inst_mutation']:.1%} | {curve['mutation_free_inst_drop_pt']:+.1f}pt |",
    ]
    for lvl in (0.10, 0.25, 0.50):
        d = curve[f"noise_{lvl:.0%}"]
        lines.append(f"| noise {lvl:.0%} | {d['macro']:.1%} | {d['drop_pt']:+.1f}pt |")
    lines += [
        "",
        "## Tabel 3 — Audit Structural Semantic Anchors (B7)",
        "",
        "Lihat `docs/report/decorpusing_catalog.md` — Pure Semantic MACRO 79.4% (assist +8.6pt);",
        "nomor 0 assist (literal 270/GIRI dapat dilepas gratis), organizer +31.1pt (alias).",
        "",
        "## Tabel 4 — Kalibrasi Review & Safety Net (B3)",
        "",
        "Lihat `docs/report/b3_calibrated_confidence_report.md` — cert recall 100%, weak-field",
        "nomor 25% & false alarm 90% (GATE FAIL) → B3 TIDAK dimasukkan ke composite;",
        "flag review tetap dari confidence B6 (0.78 utk nomor repaired).",
        "",
        "## HYB-003 (korpus OCR scan-49, report-only)",
        "",
        "Organizer rapid-only text merge (0 OCR baru, artefak `hybrid_rapid_org`, HYB-003 ledger):",
        "organizer exact 26.5% → 34.7% (+8.2pt), MACRO scan 47.26% → 49.2%. Berlaku hanya",
        "pada korpus OCR — di korpus teks offline composite tidak menyentuh OCR.",
        "",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))

    print(f"all-cells: v9 {v9['allcells_exact_pct']:.2f}% | v4.2 {v42['allcells_exact_pct']:.2f}% | composite {comp['allcells_exact_pct']:.2f}%")
    print(f"framework: v4.2 {v42['framework_exact_pct']:.2f}% | composite {comp['framework_exact_pct']:.2f}%")
    print(f"zero-regression: {'PASS' if gates['zero_regression_pass'] else 'FAIL'}")
    print(f"OOD composite: mutation free-inst drop {curve['mutation_free_inst_drop_pt']:+.1f}pt | "
          f"noise 10% {curve['noise_10%']['drop_pt']:+.1f}pt | 25% {curve['noise_25%']['drop_pt']:+.1f}pt | 50% {curve['noise_50%']['drop_pt']:+.1f}pt")
    print(f"VERDICT: {'PASS' if gates['allcells_pass'] and gates['framework_pass'] and gates['zero_regression_pass'] else 'FAIL'}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
