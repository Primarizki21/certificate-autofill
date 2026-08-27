"""C1-001 — Verifikasi AKT-005 pada korpus OCR branch (baseline_rapid_tess).

Frontier handoff v38 #5: "nama_kegiatan exact 6.1% semua varian" di cabang OCR.
Hipotesis: angka itu artefak harness — eval cabang OCR (`benchmark_hybrid_ocr.py`)
memakai extractor PRODUKSI untuk nama_kegiatan, sementara perbaikan deteksi
AKT-002..005 (`extract_activity_v5`, all-74 -> 62.2%) tidak pernah dipasang di
harness itu. C1-001 = verifikasi 1 langkah: pasang extract_activity_v5 di teks
OCR branch (baseline_rapid_tess), evaluasi scan-49 vs baseline offline_prod.

Korpus: tests/benchmark_runs/ocr_experiment/baseline_rapid_tess/extracted_texts
(74 teks: 49 scan rapid_tess + 25 embedded) — BUKAN run_20260728_131835 yang
dipakai AKT (teks pipeline produksi; terbukti BEDA untuk stem yang sama).

Gate (verifikasi): nama_kegiatan exact scan-49 naik material vs offline_prod,
0 regress field lain (offline_akt5 hanya menyentuh nama_kegiatan by design).

Usage:
  uv run python -m tests.verify_c1_akt_scan
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("APP_ENV", "development")

from tests.benchmark_akt2 import eval_corpus
from tests.benchmark_akt5 import offline_akt5
from tests.benchmark_prod_port import offline_prod
from tests.matchers import match_field
from tests.ocr_engine import classify_manifest
from tests.ood_probe import EVAL_FIELDS, load_gt

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
TEXTS_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", "ocr_experiment", "baseline_rapid_tess", "extracted_texts"
)
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"c1_akt_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "c1_akt_scan.md")

FIELD = "nama_kegiatan_sertifikasi"


def load_texts() -> dict[str, str]:
    out = {}
    for fn in os.listdir(TEXTS_DIR):
        if fn.endswith(".txt"):
            with open(os.path.join(TEXTS_DIR, fn), encoding="utf-8", errors="replace") as f:
                out[os.path.splitext(fn)[0]] = f.read()
    return out


def scan_stems() -> set[str]:
    with open(MANIFEST) as f:
        manifest = json.load(f)
    classification = classify_manifest(manifest)
    return {s for s, c in classification.items() if c["scan"]}


def pct(pf: dict, key: str) -> float:
    return pf[key] / pf["total"] * 100 if pf["total"] else 0.0


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    scans = scan_stems()
    texts_scan = {s: t for s, t in texts.items() if s in scans}

    print(f"teks total={len(texts)} scan={len(texts_scan)}")
    base_all = eval_corpus(texts, gt, offline_prod)
    var_all = eval_corpus(texts, gt, offline_akt5)
    base_scan = eval_corpus(texts_scan, gt, offline_prod)
    var_scan = eval_corpus(texts_scan, gt, offline_akt5)

    fixes, regresses = [], []
    for stem, text in texts_scan.items():
        row = gt.get(stem)
        if row is None:
            continue
        gv = (row.get(FIELD) or "").strip()
        if not gv or gv == "-":
            continue
        b0 = match_field(gv, offline_prod(text).get(FIELD), FIELD)
        v0 = match_field(gv, offline_akt5(text).get(FIELD), FIELD)
        if not b0["exact"] and v0["exact"]:
            fixes.append((stem, offline_akt5(text).get(FIELD), gv))
        if b0["exact"] and not v0["exact"]:
            regresses.append((stem, offline_akt5(text).get(FIELD), gv))

    ab, av = base_scan["per_field"][FIELD], var_scan["per_field"][FIELD]
    ab_all, av_all = base_all["per_field"][FIELD], var_all["per_field"][FIELD]
    regress_fields = [
        f for f in EVAL_FIELDS
        if var_scan["per_field"][f]["exact"] < base_scan["per_field"][f]["exact"]
    ]

    print(f"\n=== SCAN-49 (baseline_rapid_tess) ===")
    print(f"offline_prod : MACRO {base_scan['macro_exact']*100:.2f}% | {FIELD} exact {pct(ab,'exact'):.1f}% fuzzy {pct(ab,'fuzzy'):.1f}%")
    print(f"offline_akt5 : MACRO {var_scan['macro_exact']*100:.2f}% | {FIELD} exact {pct(av,'exact'):.1f}% fuzzy {pct(av,'fuzzy'):.1f}%")
    print(f"fixes={len(fixes)} regresses={len(regresses)} regress_fields={regress_fields or 'tidak ada'}")
    for stem, ev, gv in fixes:
        print(f"  FIX  {stem}: {ev!r}")
    for stem, ev, gv in regresses:
        print(f"  REGRESS {stem}: {ev!r} | GT: {gv!r}")

    print(f"\n=== ALL-74 (pembanding AKT-005 asli) ===")
    print(f"offline_prod : {FIELD} exact {pct(ab_all,'exact'):.1f}% | offline_akt5: {pct(av_all,'exact'):.1f}%")

    summary = {
        "scan49": {
            "base_macro_exact": base_scan["macro_exact"],
            "var_macro_exact": var_scan["macro_exact"],
            "nama_kegiatan": {
                "base": {"exact": ab["exact"], "total": ab["total"]},
                "akt5": {"exact": av["exact"], "total": av["total"]},
            },
            "fixes": fixes,
            "regresses": regresses,
        },
        "all74": {
            "base": {"exact": ab_all["exact"], "total": ab_all["total"]},
            "akt5": {"exact": av_all["exact"], "total": av_all["total"]},
        },
    }
    with open(os.path.join(OUT_DIR, "summary_c1.json"), "w") as f:
        json.dump(summary, f, indent=2)

    md = [
        "# C1-001 — Verifikasi AKT-005 di korpus OCR branch (scan-49)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        "teks = baseline_rapid_tess (OCR branch) | 0 LLM call",
        "",
        "## Latar",
        "",
        "Frontier handoff v38 #5 mencatat nama_kegiatan 6.1% exact 'semua varian' di cabang OCR.",
        "Hipotesis: artefak harness — eval cabang OCR memakai extractor produksi, "
        "sedangkan perbaikan AKT-002..005 (62.2% all-74) tidak pernah dipasang di sana.",
        "Catatan: korpus AKT (run_20260728_131835, teks pipeline produksi) TERBUKTI BEDA "
        "dari baseline_rapid_tess (raw OCR) utk stem yang sama — verifikasi ini sah.",
        "",
        "## Hasil — scan-49 (baseline_rapid_tess)",
        "",
        "| Metrik | offline_prod | +AKT-005 |",
        "|---|---|---|",
        f"| {FIELD} exact | {pct(ab,'exact'):.1f}% ({ab['exact']}/{ab['total']}) | {pct(av,'exact'):.1f}% ({av['exact']}/{av['total']}) |",
        f"| {FIELD} fuzzy | {pct(ab,'fuzzy'):.1f}% | {pct(av,'fuzzy'):.1f}% |",
        f"| MACRO exact | {base_scan['macro_exact']*100:.2f}% | {var_scan['macro_exact']*100:.2f}% |",
        "",
        f"Fixes: **{len(fixes)}** | Regresses: **{len(regresses)}** | "
        f"regress field lain: {regress_fields or 'tidak ada'}",
        "",
        "## Fix (wrong -> exact, scan-49)",
        "",
    ]
    for stem, ev, gv in fixes:
        md.append(f"- `{stem}`: {ev!r} (GT: {gv!r})")
    md += ["", "## Regress (exact -> wrong, scan-49)", ""]
    for stem, ev, gv in regresses:
        md.append(f"- `{stem}`: {ev!r} (GT: {gv!r})")
    md += [
        "",
        "## Pembanding all-74 (korpus AKT asli)",
        "",
        "| Metrik | offline_prod | +AKT-005 |",
        "|---|---|---|",
        f"| {FIELD} exact | {pct(ab_all,'exact'):.1f}% ({ab_all['exact']}/{ab_all['total']}) | "
        f"{pct(av_all,'exact'):.1f}% ({av_all['exact']}/{av_all['total']}) |",
        "",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md) + "\n")
    print(f"\nwrote {OUT_MD}")


if __name__ == "__main__":
    main()
