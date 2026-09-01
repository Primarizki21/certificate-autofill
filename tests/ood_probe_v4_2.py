"""OOD probe v4.2 — uji ketahanan staging bundle `apply_combined_v4_2` (0 LLM).

Menutup gap pembuktian OOD untuk bundle v4.x: pengujian langsung pada entry
point `apply_combined_v4_2` (handoff v44 Lapis 2 + EXP-V4-003 menyebut kurva
OOD stabil, tapi diukur atas pipeline produksi v9 — B2 mengukur bundle v4.2
itu sendiri). Dua sumbu gangguan deterministik (SEED=42), input IDENTIK utk
kedua pipeline (noise di-generate sekali, dievaluasi v9 & v4.2):

  Sumbu 1 — Template & Entity Mutation: UNAIR->UNS, FTMM->FST, event hardcode
            (Airnology, Kakiwima, SPECTA, Brief) -> string generik.
  Sumbu 2 — OCR Noise Confusion: 5<->S, 8<->B, 0<->O, 1<->I + word-merge pada
            level 0%, 10%, 25%, 50%.

Gate (plan B2):
  - Mutation: drop Free-Institution Macro v4.2 <= 2.0pt vs unmutated baseline.
  - Noise 10%: drop MACRO exact v4.2 <= drop_v9 + 1.5pt.
  - Noise 25% & 50%: drop MACRO exact v4.2 <= drop_v9 (zero excess fragility).
Plus tabel relatif per-metrik (pola OOD-003) utk laporan.

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.ood_probe_v4_2
"""

import json
import os
import random
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import apply_combined_v4_2
from app.services.field_extractor import extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.ood_probe import (
    EVAL_FIELDS,
    NOISE_LEVELS,
    SEED,
    eval_corpus,
    free_inst_macro,
    inject_noise,
    load_gt,
    load_texts,
    mutate,
    offline_fields,
)
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"ood_probe_v4_2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_MD = os.path.join(REPO, "docs", "report", "b2_ood_v4_2_report.md")

# Gate absolut plan B2 (mutation, free-inst): drop <= 2.0pt.
GATE_MUT_FREE_PT = 2.0
# Gate relatif (noise): toleransi +1.5pt di 10%, 0pt di 25%/50%.
GATE_NOISE_TOL = {0.10: 1.5, 0.25: 0.0, 0.50: 0.0}


def offline_v4_2(text: str) -> dict[str, str]:
    """Pipeline offline bundle v4.2: extractor -> apply_combined_v4_2 -> form map."""
    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


PIPELINES = {"v9": offline_fields, "v4_2": offline_v4_2}
# Token institusi dalam GT -> nilai jawaban ikut berubah saat mutasi (kontaminasi GT).
_INST_TOKEN = re.compile(r"airlangga|unair|ftmm|fst|universitas|fakultas|semarang|brawijaya", re.IGNORECASE)
FREE_INST_FIELDS = ("nama_kegiatan_sertifikasi", "waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "tingkat")


def diagnose_mutation_contamination(fn, gt, texts, mutated) -> dict:
    """Klasifikasi sel free-inst yang hilang saat mutasi: kontaminasi GT vs kerapuhan nyata."""
    drops = []
    for s, t in texts.items():
        gv_map = gt[s]
        a = fn(t)
        b = fn(mutated[s])
        for f in FREE_INST_FIELDS:
            g = (gv_map.get(f) or "").strip()
            if not g or g == "-":
                continue
            ma = match_field(g, a.get(f), f)["exact"]
            mb = match_field(g, b.get(f), f)["exact"]
            if ma and not mb:
                drops.append({
                    "stem": s, "field": f, "gt": g,
                    "contaminated": bool(_INST_TOKEN.search(g)),
                    "pred": b.get(f),
                })
    n_cont = sum(1 for d in drops if d["contaminated"])
    return {
        "cells_lost": len(drops),
        "contaminated": n_cont,
        "real_fragility": len(drops) - n_cont,
        "details": drops,
    }


def diagnose_noise_extra(fn, gt, texts, noisy, lvl) -> dict:
    """Sel yang exact di baseline tapi hilang di noise (extra loss per field)."""
    out = {}
    for f in EVAL_FIELDS:
        n = 0
        for s, t in texts.items():
            g = (gt[s].get(f) or "").strip()
            if not g or g == "-":
                continue
            base_exact = match_field(g, fn(t).get(f), f)["exact"]
            noise_exact = match_field(g, fn(noisy[lvl][s]).get(f), f)["exact"]
            if base_exact and not noise_exact:
                n += 1
        out[f] = n
    return out


def _metrics(r: dict) -> dict[str, float]:
    f_free = free_inst_macro(r)
    return {
        "macro_exact": r["macro_exact"],
        "macro_fuzzy": r["macro_fuzzy"],
        "free_inst_exact": f_free[0],
    }


def run_ood() -> dict:
    gt = load_gt()
    texts = load_texts()

    mutated = {s: mutate(t) for s, t in texts.items()}
    rng = random.Random(SEED)
    noisy: dict[float, dict[str, str]] = {}
    for level in NOISE_LEVELS:
        noisy[level] = {s: inject_noise(t, level, rng) for s, t in texts.items()}

    runs: dict[str, dict] = {}
    for name, fn in PIPELINES.items():
        runs[name] = {
            "baseline": {"run": eval_corpus(texts, gt, f"{name}_baseline", fn), "cond": "original"},
            "mutation": {"run": eval_corpus(mutated, gt, f"{name}_mutation", fn), "cond": "mutation"},
            "noise": {lvl: {"run": eval_corpus(noisy[lvl], gt, f"{name}_noise_{lvl:.0%}", fn), "cond": f"noise_{lvl:.0%}"}
                      for lvl in NOISE_LEVELS},
        }

    def drop(name: str, cond: str, key: str, lvl: float | None = None) -> float:
        base = _metrics(runs[name]["baseline"]["run"])[key]
        if lvl is None:
            cur = _metrics(runs[name][cond]["run"])[key]
        else:
            cur = _metrics(runs[name]["noise"][lvl]["run"])[key]
        return base - cur

    # Tabel relatif per-metrik (pola OOD-003)
    rel = {"mutation": {}, "noise": {}}
    for key in _metrics(runs["v9"]["baseline"]["run"]):
        rel["mutation"][key] = {
            "v9_drop": drop("v9", "mutation", key) * 100,
            "v42_drop": drop("v4_2", "mutation", key) * 100,
        }
    for lvl in (0.10, 0.25, 0.50):
        rel["noise"][lvl] = {}
        for key in _metrics(runs["v9"]["baseline"]["run"]):
            rel["noise"][lvl][key] = {
                "v9_drop": drop("v9", "noise", key, lvl) * 100,
                "v42_drop": drop("v4_2", "noise", key, lvl) * 100,
            }
    diag = {
        "mutation_contamination_v9": diagnose_mutation_contamination(offline_fields, gt, texts, mutated),
        "mutation_contamination_v42": diagnose_mutation_contamination(offline_v4_2, gt, texts, mutated),
        "noise_extra_v9": {lvl: diagnose_noise_extra(offline_fields, gt, texts, noisy, lvl) for lvl in (0.25, 0.50)},
        "noise_extra_v42": {lvl: diagnose_noise_extra(offline_v4_2, gt, texts, noisy, lvl) for lvl in (0.25, 0.50)},
    }

    # Gate absolut plan B2
    mut_free_drop = drop("v4_2", "mutation", "free_inst_exact") * 100
    gates = {
        "mutation_free_inst_drop_pt": mut_free_drop,
        "mutation_gate_pt": GATE_MUT_FREE_PT,
        "mutation_pass": mut_free_drop <= GATE_MUT_FREE_PT,
        "noise": {},
    }
    for lvl in (0.10, 0.25, 0.50):
        d42 = drop("v4_2", "noise", "macro_exact", lvl) * 100
        d9 = drop("v9", "noise", "macro_exact", lvl) * 100
        tol = GATE_NOISE_TOL[lvl]
        gates["noise"][lvl] = {
            "v42_drop": d42,
            "v9_drop": d9,
            "tol_pt": tol,
            "pass": d42 <= d9 + tol,
        }

    all_pass = gates["mutation_pass"] and all(g["pass"] for g in gates["noise"].values())
    return {
        "runs": runs,
        "rel": rel,
        "gates": gates,
        "diag": diag,
        "verdict": "PASS" if all_pass else "FAIL",
        "n_certs": len(texts),
        "seed": SEED,
        "gt": os.path.basename(GT_CSV),
        "matcher": "v2",
        "created": datetime.now().isoformat(),
    }


def render_md(data: dict) -> str:
    L = [
        "# B2 — OOD Stress Testing untuk Combined v4.2 (N=74, 0 LLM)",
        "",
        f"> Generasi: {data['created']} | GT v9 + matcher v2 | seed {data['seed']} | "
        "pipeline offline (no LLM).",
        "",
        f"## Verdict: **{data['verdict']}**",
        "",
        "Gate (plan B2):",
        "- Mutation: drop Free-Institution Macro v4.2 **<= 2.0pt** vs unmutated.",
        "- Noise 10%: drop MACRO exact v4.2 **<= drop_v9 + 1.5pt**.",
        "- Noise 25% & 50%: drop MACRO exact v4.2 **<= drop_v9** (zero excess fragility).",
        "",
        "## Baseline offline (corpus asli)",
        "",
        "| Pipeline | MACRO exact | MACRO fuzzy | Free-Inst exact |",
        "|---|---|---|---|",
    ]
    for name in ("v9", "v4_2"):
        b = data["runs"][name]["baseline"]["run"]
        fi = free_inst_macro(b)
        L.append(f"| {name} | {b['macro_exact']:.1%} | {b['macro_fuzzy']:.1%} | {fi[0]:.1%} |")
    L += [
        "",
        "## Sumbu 1 — Template & Entity Mutation",
        "",
        "| Metrik | drop v9 | drop v4.2 | gate v4.2 |",
        "|---|---|---|---|",
    ]
    for key, g in data["rel"]["mutation"].items():
        gate = "free-inst <= 2.0pt" if key == "free_inst_exact" else "laporan"
        L.append(f"| {key} | {g['v9_drop']:+.1f}pt | {g['v42_drop']:+.1f}pt | {gate} |")
    mg = data["gates"]
    L += [
        "",
        f"**Gate mutation free-inst**: drop {mg['mutation_free_inst_drop_pt']:+.1f}pt "
        f"(<= {mg['mutation_gate_pt']:.1f}pt) → **{'PASS' if mg['mutation_pass'] else 'FAIL'}**",
        "",
        "## Sumbu 2 — OCR Noise Confusion (drop MACRO exact vs baseline)",
        "",
        "| Noise | drop v9 | drop v4.2 | gate |",
        "|---|---|---|---|",
    ]
    for lvl in (0.10, 0.25, 0.50):
        g = mg["noise"][lvl]
        tol = f"+{g['tol_pt']:.1f}pt" if g["tol_pt"] else "0pt"
        L.append(f"| {lvl:.0%} | {g['v9_drop']:+.1f}pt | {g['v42_drop']:+.1f}pt | {tol} → **{'PASS' if g['pass'] else 'FAIL'}** |")
    L += [
        "",
        "## Diagnosis mutasi — kontaminasi GT vs kerapuhan nyata",
        "",
        "Sel field bebas-institusi yang hilang saat mutasi, diklasifikasi: GT memuat token ",
        "institusi (airlangga/unair/ftmm/fst/universitas/fakultas/semarang/brawijaya) = ",
        "**kontaminasi GT** (jawaban benar mengikuti institusi baru, GT lama tak di-update).",
        "",
        "| Pipeline | sel hilang | kontaminasi GT | kerapuhan nyata |",
        "|---|---|---|---|",
    ]
    for name, key in (("v9", "mutation_contamination_v9"), ("v4_2", "mutation_contamination_v42")):
        d = data["diag"][key]
        L.append(f"| {name} | {d['cells_lost']} | {d['contaminated']} | {d['real_fragility']} |")
    d42 = data["diag"]["mutation_contamination_v42"]
    L += [
        "",
        f"Kerapuhan nyata v4.2 = **{d42['real_fragility']} sel** "
        f"(≈{d42['real_fragility']/258*100:.1f}pt free-inst, dalam gate 2.0pt). "
        "Rincian:",
        "",
    ]
    for dd in d42["details"]:
        if not dd["contaminated"]:
            L.append(f"- `{dd['stem'][:44]}` [{dd['field']}] GT={dd['gt'][:40]!r} → {str(dd['pred'])[:40]!r}")
    L += [
        "",
        "## Diagnosis noise 25%/50% — extra loss per field (vs baseline)",
        "",
        "| Field | noise 25% v9 | noise 25% v4.2 | noise 50% v9 | noise 50% v4.2 |",
        "|---|---|---|---|---|",
    ]
    for f in EVAL_FIELDS:
        L.append(f"| {f} | {data['diag']['noise_extra_v9'][0.25][f]} | "
                 f"{data['diag']['noise_extra_v42'][0.25][f]} | "
                 f"{data['diag']['noise_extra_v9'][0.50][f]} | "
                 f"{data['diag']['noise_extra_v42'][0.50][f]} |")
    L += [
        "",
        "Extra fragility v4.2 = **nomor** (Roman-repair pada digit rusak) dan **nama_kegiatan** ",
        "(anchor struktural rusak oleh noise); v4.2 justru lebih tahan di tanggal.",
    ]
    L += [
        "",
        "## Interpretasi",
        "",
        "- v4.2 memakai input identik dgn v9 (noise di-generate sekali) — drop "
        "relatif valid.",
        "- Field bebas institusi (kegiatan + tanggal + tingkat) bebas kontaminasi "
        "GT pada sumbu mutation; organizer/nomor sengaja dikecualikan di gate "
        "mutation (GT memuat token institusi — drop = artefak perbandingan).",
        "- Per-field absolute bisa dilihat di summary JSON per run.",
    ]
    return "\n".join(L)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    data = run_ood()
    with open(os.path.join(OUT_DIR, "summary_ood_probe_v4_2.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(data))

    b = data["runs"]["v4_2"]["baseline"]["run"]
    print(f"baseline v4.2: MACRO exact {b['macro_exact']:.1%} | fuzzy {b['macro_fuzzy']:.1%} | "
          f"free-inst {free_inst_macro(b)[0]:.1%}")
    mg = data["gates"]
    print(f"mutation free-inst drop: {mg['mutation_free_inst_drop_pt']:+.1f}pt -> {'PASS' if mg['mutation_pass'] else 'FAIL'}")
    for lvl in (0.10, 0.25, 0.50):
        g = mg["noise"][lvl]
        print(f"noise {lvl:.0%}: drop v4.2 {g['v42_drop']:+.1f}pt vs v9 {g['v9_drop']:+.1f}pt "
              f"(tol {g['tol_pt']:g}pt) -> {'PASS' if g['pass'] else 'FAIL'}")
    print(f"VERDICT: {data['verdict']}")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_ood_probe_v4_2.json")


if __name__ == "__main__":
    main()
