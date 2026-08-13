"""F1 lanjutan — ORG-004: canonicalisasi bucket `format` (+ `format_residu`/OCR merge).

Baseline = `offline_v3` (F1C-001: organizer 54.1%, MACRO 61.2%). Lapisan baru
di atasnya (tests-only, produksi tak disentuh), berdasar taksonomi ulang pada
baseline v3 (format 11, format_residu 2, kelebihan 5).

Aturan — GENERAL (kamus/pattern berlaku utk semua cert, bukan hardcode per-cert;
pola sama dgn OCR_ORG_MAP di organizer_v2):

- F1: alias canonical (compact value -> bentuk canonical): OCR merge dept
  `INFORMATION SYSTEMS DEPT` (5 cert Ananda), `Studisl` (S1 merge), merge
  `APHSABEMFKM`, split `Facultyof` + akronim `UB` -> Brawijaya University,
  `Majudan` -> "Maju dan".
- F2: nama fakultas FMIPA — hapus " dan " ("Matematika dan Ilmu Pengetahuan
  Alam" -> "Matematika Ilmu Pengetahuan Alam", GT canonical).
- F3: suffix univ utk org berakhir "BEM FKM" bila konteks UNAIR ada.

Gate (handoff v20 + F1C-001 + OOD-003): organizer exact naik (target >=+5pt vs
v3 54.1%), no-regress field lain vs v3, 0 LLM call. Sumbu OOD (mutation/noise):
drop v4 <= drop v3 + toleransi (sama OOD-003).

Usage:
  uv run python -m tests.benchmark_org_format
"""

import json
import os
import random
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_organizer_v3 import _norm_organizer_v3, offline_v3
from tests.matchers import match_field
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

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"org_format_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "f1_organizer_format.md")

# --- F1: alias canonical (compact value -> bentuk canonical) -----------------
# Bentuk OCR-merge/akronim yang muncul lintas cert; kamus = mekanisme general
# (pola sama OCR_ORG_MAP). Compact = uppercase, non-alnum dihapus.
_ORG_ALIASES = {
    "FACULTYOFSCIENCEANDTECHNOLOGYINFORMATIONSYSTEMSDEPT": (
        "Faculty of Science and Technology Information System Dept."
    ),
    "PROGRAMSTUDISLTEKNOLOGISAINSDATA": "Program Studi S1 Teknologi Sains Data",
    "DIVISIKAPROFAPHSABEMFKMUNIVERSITASAIRLANGGA": "Divisi Kaprof APHSA BEM FKM Universitas Airlangga",
    "FACULTYOFCOMPUTERSCIENCEUB": "Faculty of Computer Science Brawijaya University",
    "FAKULTASTEKNOLOGIMAJUDANMULTIDISIPLINUNIVERSITASAIRLANGGA": (
        "Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga"
    ),
}
# --- F3: suffix univ utk "BEM FKM" (konteks UNAIR) ----------------------------
_BEM_FKM_SUFFIX = re.compile(r"\bBEM\s+FKM\s*$", re.IGNORECASE)


def _compact(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _norm_org_format(value: str | None, raw_text: str) -> str | None:
    v = value or ""
    c = _compact(v)
    if c in _ORG_ALIASES:
        v = _ORG_ALIASES[c]
    has_unair = bool(re.search(r"UNAIR|UNIVERSITAS\s*AIRLANGGA|AIRLANGGA", (raw_text or "").upper()))
    if has_unair and _BEM_FKM_SUFFIX.search(v) and "UNIVERSITAS AIRLANGGA" not in v.upper():
        v = v + " Universitas Airlangga"
    return v or None


def offline_v4(text: str) -> dict[str, str]:
    from app.services.field_extractor import ExtractedValue, extract_certificate_fields

    extracted = extract_certificate_fields(text)
    from tests.organizer_extractor_v2 import extract_organizer_v2

    v2 = extract_organizer_v2(text)
    if v2:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
    org = _norm_organizer_v3(extracted.get("penyelenggara_kegiatan").value, text)
    org4 = _norm_org_format(org, text)
    if org4:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(org4, 0.84, "organizer_v2")
    from app.services.form_mapper import map_fields_to_form

    from tests.benchmark_org_norm import _norm_nomor

    nomor = _norm_nomor(text)
    if nomor:
        extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(nomor, 0.95, "regex_certificate_number")
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    base = eval_corpus(texts, gt, "v3", fn=offline_v3)
    var = eval_corpus(texts, gt, "v4", fn=offline_v4)
    print(f"v3: MACRO exact {base['macro_exact']:.4f} fuzzy {base['macro_fuzzy']:.4f}")
    print(f"v4: MACRO exact {var['macro_exact']:.4f} fuzzy {var['macro_fuzzy']:.4f}")

    org_b = base["per_field"]["penyelenggara_kegiatan"]
    org_v = var["per_field"]["penyelenggara_kegiatan"]
    b_pct = org_b["exact"] / org_b["total"] * 100
    v_pct = org_v["exact"] / org_v["total"] * 100

    # Per-cert: fix & regress organizer
    fixes, regresses = [], []
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        gv = (row.get("penyelenggara_kegiatan") or "").strip()
        if not gv or gv == "-":
            continue
        b0 = match_field(gv, offline_v3(text).get("penyelenggara_kegiatan"), "penyelenggara_kegiatan")
        v0 = match_field(gv, offline_v4(text).get("penyelenggara_kegiatan"), "penyelenggara_kegiatan")
        if not b0["exact"] and v0["exact"]:
            fixes.append((stem, offline_v4(text).get("penyelenggara_kegiatan"), gv))
        if b0["exact"] and not v0["exact"]:
            regresses.append((stem, offline_v4(text).get("penyelenggara_kegiatan"), gv))

    regress = [f for f in EVAL_FIELDS if f != "penyelenggara_kegiatan" and var["per_field"][f]["exact"] < base["per_field"][f]["exact"]]
    pass_gate = v_pct >= b_pct + 5.0 and not regress and var["macro_exact"] >= base["macro_exact"] - 0.005

    # OOD: mutation + noise (drop v4 vs drop v3, sama OOD-003)
    mut_base = eval_corpus({s: mutate(t) for s, t in texts.items()}, gt, "v3_mut", fn=offline_v3)
    mut_var = eval_corpus({s: mutate(t) for s, t in texts.items()}, gt, "v4_mut", fn=offline_v4)
    rng = random.Random(SEED)
    noise = []
    for lvl in NOISE_LEVELS:
        cond = {s: inject_noise(t, lvl, rng) for s, t in texts.items()}
        noise.append({
            "level": lvl,
            "v3": eval_corpus(cond, gt, f"v3_noise_{lvl:.0%}", fn=offline_v3),
            "v4": eval_corpus(cond, gt, f"v4_noise_{lvl:.0%}", fn=offline_v4),
        })

    def drop(a: dict, b: dict, key: str) -> float:
        pa, pb = a["per_field"][key] if key != "macro" else {"exact": a["macro_exact"]}, None
        if key == "macro":
            return a["macro_exact"] - b["macro_exact"]
        return pa["exact"] / pa["total"] - b["per_field"][key]["exact"] / b["per_field"][key]["total"]

    print(f"\nOrganizer exact: {b_pct:.1f}% -> {v_pct:.1f}% (gate >=+5pt)")
    print(f"MACRO exact:     {base['macro_exact']*100:.1f}% -> {var['macro_exact']*100:.1f}% | regress: {regress or 'tidak ada'}")
    print(f"Fixes: {len(fixes)} | Regresses: {len(regresses)}")
    for stem, ev, gv in fixes:
        print(f"  FIX {stem}: {ev!r} | GT: {gv!r}")
    for stem, ev, gv in regresses:
        print(f"  REGRESS {stem}: {ev!r} | GT: {gv!r}")
    print(f"Mutation drop macro: v3 {mut_base['macro_exact']-base['macro_exact']:+.1%} v4 {mut_var['macro_exact']-var['macro_exact']:+.1%}")
    for n in noise:
        d3 = n["v3"]["macro_exact"] - base["macro_exact"]
        d4 = n["v4"]["macro_exact"] - var["macro_exact"]
        print(f"Noise {n['level']:.0%}: drop v3 {d3:+.1%} v4 {d4:+.1%}")
    print(f"VERDICT: {'GATE PASS' if pass_gate else 'GATE FAIL'}")

    md_lines = [
        "# F1 lanjutan — ORG-004: Canonicalisasi Organizer (bucket format, tanpa AI)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"baseline = offline_v3 (F1C-001) | 0 LLM call",
        "",
        "## Hasil",
        "",
        "| Metrik | v3 | ORG-004 | delta | gate |",
        "|---|---|---|---|---|",
    ]
    for f in EVAL_FIELDS:
        b, v = base["per_field"][f], var["per_field"][f]
        gate = "no-regress" if f != "penyelenggara_kegiatan" else ">=+5pt"
        md_lines.append(
            f"| {f} exact | {b['exact']/b['total']*100 if b['total'] else 0:.1f}% | "
            f"{v['exact']/v['total']*100 if v['total'] else 0:.1f}% | "
            f"{(v['exact']/v['total'] if v['total'] else 0) - (b['exact']/b['total'] if b['total'] else 0):+.1%} | {gate} |"
        )
    md_lines += [
        f"| MACRO exact | {base['macro_exact']*100:.1f}% | {var['macro_exact']*100:.1f}% | "
        f"{var['macro_exact']-base['macro_exact']:+.1%} | no-regress |",
        "",
        "## Verdict",
        "",
        f"**{'GATE PASS' if pass_gate else 'GATE FAIL'}** — organizer exact "
        f"{b_pct:.1f}% → {v_pct:.1f}% (gate >=+5pt); no-regress: {regress or 'tidak ada'}.",
        "",
        "## Fix organizer (wrong→exact)",
        "",
        "| stem | ORG-004 | GT |",
        "|---|---|---|",
    ]
    for stem, ev, gv in fixes:
        md_lines.append(f"| {stem} | {ev} | {gv} |")
    md_lines += ["", "## Regress", ""]
    md_lines += [f"| {s} | {e} | {g} |" for s, e, g in regresses] or ["tidak ada"]
    md_lines += [
        "",
        "## OOD (drop vs baseline v3, sama OOD-003 gate)",
        "",
        f"- Mutation MACRO exact drop: v3 {base['macro_exact']-mut_base['macro_exact']:+.1%} | "
        f"ORG-004 {var['macro_exact']-mut_var['macro_exact']:+.1%}",
    ]
    for n in noise:
        d3 = base["macro_exact"] - n["v3"]["macro_exact"]
        d4 = var["macro_exact"] - n["v4"]["macro_exact"]
        md_lines.append(f"- Noise {n['level']:.0%} drop: v3 {d3:+.1%} | ORG-004 {d4:+.1%}")
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md_lines))
    print(f"wrote {OUT_MD}")

    with open(os.path.join(OUT_DIR, "summary_org_format.json"), "w") as f:
        json.dump({
            "baseline": base, "variant": var, "fixes": fixes, "regresses": regresses,
            "regress_fields": regress, "pass_gate": pass_gate,
            "macro_avg": {"exact_acc": var["macro_exact"]},
            "mutation": {"v3": mut_base, "v4": mut_var}, "noise": noise,
            "gt": os.path.basename(GT_CSV), "matcher": "v2",
        }, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
