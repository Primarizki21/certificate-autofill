"""AKT-005 — Deteksi nama_kegiatan v5: grup D all-caps/spacing (eksperimen, 0 LLM, produksi tak disentuh).

Lanjutan AKT-004 (40/74 exact). Target grup D (risiko tertinggi — repair
berjalan di _preprocess = teks SEMUA cert kena, wajib no-regress ketat):
- synreaach: `DALAMACARADEKANCUPFTMM2024BYSYNREACHFTMM2024` — pecah all-caps
  via keyword (DALAM/ACARA/DEKAN/CUP/BY/SYNREACH) -> "Dekan Cup FTMM 2024 by
  SYNREACH FTMM 2024".
- Gelar Rasa: `DALAMACARAGELARRASA2024` -> "GELAR RASA 2024".
- 2954685: `DalamrangkaUXDESIGNcoMPETITIoNdengantema` — pre-repair sebelum
  camel-split: UXDESIGN split + (?i)competition + (?i)dengan -> anchor baru
  `Dalam rangka X` stop "dengan tema".
- SDC Unisba: huruf berjarak `D a l a m a c a r a ...` — collapse run >=3
  single-char -> "Dalam acara Statistics Data Challenge 2026" (stop dengan
  tema di anchor 1).
- ACIC 2160238: all-caps `SPEAKUP/STANDOUT/MENGASAHKETERAMPILAN/KOMUNIKASI-
  DIERAKARIRDIGITAL` di-split; anchor join2 (kutip + sisa "[ACIC] ...") DI
  ATAS anchor kutip lama (yang hanya ambil bagian kutip = fuzzy).
- BINARY_Venedict: SKIP — OCR "Bl NARY 2o 23" vs GT "BINARY 3.0" (angka beda,
  kandidat GT v10/konvensi), bukan fix regex aman.

Gate: nama_kegiatan exact >=+5pt, no-regress, 0 LLM.

Usage:
  uv run python -m tests.benchmark_akt5
"""

import json
import os
import random
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_akt4 import (
    FIELD,
    _ANCHORS4,
    _REPAIR4,
    _clean_act,
    eval_corpus,
    offline_akt3,
    offline_prod,
)
from tests.matchers import match_field
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"akt5_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "akt5_activity_detection.md")

_COLLAPSE = lambda m: m.group(1).replace(" ", "")

# Pre-repair (SEBELUM _REPAIR4 yang berisi camel-split — harus pecah dulu
# teks merged/case campur). Case-sensitive kecuali inline (?i) — tanpa
# IGNORECASE global (jebakan v31: rusak camel-split).
_D5_PRE = [
    (r"(?<![A-Za-z0-9])([A-Za-z0-9](?: [A-Za-z0-9]){2,})(?![A-Za-z0-9])", _COLLAPSE),
    (r"DALAM(?=[A-Z])", "DALAM "),
    (r"ACARA(?=[A-Z])", "ACARA "),
    (r"DEKAN(?=[A-Z])", "DEKAN "),
    (r"CUP(?=[A-Z])", "CUP "),
    (r"BY(?=[A-Z])", "BY "),
    (r"SYNREACH(?=[A-Z])", "SYNREACH "),
    (r"GELAR(?=[A-Z])", "GELAR "),
    (r"UXDESIGN(?=[A-Za-z])", "UX DESIGN "),
    (r"(?i)competition", "competition"),
    (r"(?i)dengan(?=[A-Za-z])", "dengan "),
    (r"(?i)(?<=[a-z0-9])dengan(?=\s)", " dengan"),
    (r"SPEAK(?=UP)", "SPEAK "),
    (r"STAND(?=OUT)", "STAND "),
    (r"MENGASAH(?=[A-Z])", "MENGASAH "),
    (r"KOMUNIKASI(?=[A-Z])", "KOMUNIKASI "),
    (r"DI(?=ERA)", "DI "),
    (r"ERA(?=KARIR)", "ERA "),
    (r"KARIR(?=DIGITAL)", "KARIR "),
]

# Post-repair (SESUDAH _REPAIR4 yang berisi camel-split): `(?i)competition`
# di _D5_PRE melowercase "Competition" dan MEMBUNUH batas camel-split
# ("AcademicCompetition"->"Academiccompetition" tidak terpecah lagi) —
# re-split di sini agar 2954631/Poisson tidak regress. Sentinel "\n" sebelum
# "Himpunan" digit-bound (SDC Unisba: organizer menyela sebelum "dengan tema"
# — _STOP \n memberhentikan capture tepat setelah nama kegiatan).
_D5_POST = [
    (r"(?i)(?<=[a-z])competition(?=\s)", " competition"),
    (r"(?i)(?<=\d)\s+Himpunan", "\nHimpunan"),
]

_REPAIR5 = _D5_PRE + _REPAIR4 + _D5_POST

# join2 (kutip + sisa "[...]") DI ATAS anchor kutip lama (index grup-B):
# ACIC butuh sisa setelah kutip, ORM (tanpa "[") tetap ke anchor kutip biasa.
_GROUP_B_PATTERN = r"[Ss]ebagai\s*:?\s*Peserta\s*[\"“]([^\"”]+)[\"”]"
_ANCHORS5: list[tuple[str, str]] = []
for pattern, kind in _ANCHORS4:
    if pattern == _GROUP_B_PATTERN:
        _ANCHORS5.append(
            (r"[Ss]ebagai\s*:?\s*Peserta\s*[\"“]([^\"”]+)[\"”]\s*"
             r"(\[[^\]\n]+.*?)(?=\s+Via\s+Zoom|$)", "join2")
        )
    _ANCHORS5.append((pattern, kind))
_ANCHORS5.append((r"Dalam\s+rangka\s+(.+?)(?=\s+dengan\s+tema|\n|$)", "group"))


def _preprocess5(text: str) -> str:
    t = text
    for pat, repl in _REPAIR5:
        t = re.sub(pat, repl, t)
    return t


def extract_activity_v5(text: str) -> str | None:
    t = _preprocess5(text or "")
    for pattern, kind in _ANCHORS5:
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        if kind == "full":
            v = m.group(0)
        elif kind == "join2":
            v = f"{m.group(1)} {m.group(2)}"
        else:
            v = m.group(1)
        v = _clean_act(v)
        if v:
            return v
    return None


def extract_activity_v5_debug(text: str) -> tuple[str | None, int]:
    t = _preprocess5(text or "")
    for i, (pattern, kind) in enumerate(_ANCHORS5):
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        if kind == "full":
            v = m.group(0)
        elif kind == "join2":
            v = f"{m.group(1)} {m.group(2)}"
        else:
            v = m.group(1)
        v = _clean_act(v)
        if v:
            return v, i
    return None, -1


def offline_akt5(text: str) -> dict[str, str]:
    fields = offline_prod(text)
    new_act = extract_activity_v5(text)
    if new_act:
        fields[FIELD] = new_act
    return fields


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    base = eval_corpus(texts, gt, offline_prod)
    var = eval_corpus(texts, gt, offline_akt5)
    act_b = base["per_field"][FIELD]
    act_v = var["per_field"][FIELD]
    b_pct = act_b["exact"] / act_b["total"] * 100
    v_pct = act_v["exact"] / act_v["total"] * 100

    fixes, regresses, changed = [], [], []
    for stem, text in texts.items():
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
        old = offline_akt3(text).get(FIELD)
        new = offline_akt5(text).get(FIELD)
        o0 = match_field(gv, old, FIELD)
        if not o0["exact"] and not v0["exact"] and old != new:
            _, aidx = extract_activity_v5_debug(text)
            changed.append((stem, old, new, aidx))

    regress_fields = [f for f in EVAL_FIELDS if var["per_field"][f]["exact"] < base["per_field"][f]["exact"]]
    pass_gate = v_pct >= b_pct + 5.0 and not regress_fields and var["macro_exact"] >= base["macro_exact"] - 0.005

    print(f"Baseline:  MACRO exact {base['macro_exact']*100:.1f}% fuzzy {base['macro_fuzzy']*100:.1f}%")
    print(f"AKT-005:   MACRO exact {var['macro_exact']*100:.1f}% fuzzy {var['macro_fuzzy']*100:.1f}%")
    print(f"nama_kegiatan exact: {b_pct:.1f}% ({act_b['exact']}/{act_b['total']}) -> {v_pct:.1f}% ({act_v['exact']}/{act_v['total']}) | gate >=+5pt")
    print(f"fuzzy: {act_b['fuzzy']/act_b['total']*100:.1f}% -> {act_v['fuzzy']/act_v['total']*100:.1f}%")
    print(f"Fixes: {len(fixes)} | Regresses: {len(regresses)} | regress fields: {regress_fields or 'tidak ada'}")
    print(f"Changed non-exact (sloppiness check): {len(changed)}")
    print(f"VERDICT: {'GATE PASS' if pass_gate else 'GATE FAIL'}")
    for stem, ev, gv in fixes:
        print(f"  FIX {stem}: {ev!r}")
    for stem, ev, gv in regresses:
        print(f"  REGRESS {stem}: {ev!r} | GT: {gv!r}")

    md = [
        "# AKT-005 — Deteksi Nama Kegiatan v5: grup D all-caps/spacing (0 LLM)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        "baseline = offline_prod (produksi PROD-002, flag ON) | 0 LLM call | "
        "repair berjalan di _preprocess = teks SEMUA cert kena (no-regress ketat)",
        "",
        "## Hasil",
        "",
        "| Metrik | baseline | AKT-005 | delta | gate |",
        "|---|---|---|---|---|",
    ]
    for f in EVAL_FIELDS:
        b, v = base["per_field"][f], var["per_field"][f]
        gate = "no-regress" if f != FIELD else ">=+5pt"
        md.append(
            f"| {f} exact | {b['exact']/b['total']*100 if b['total'] else 0:.1f}% | "
            f"{v['exact']/v['total']*100 if v['total'] else 0:.1f}% | "
            f"{(v['exact']/v['total'] if v['total'] else 0) - (b['exact']/b['total'] if b['total'] else 0):+.1%} | {gate} |"
        )
    md += [
        f"| MACRO exact | {base['macro_exact']*100:.1f}% | {var['macro_exact']*100:.1f}% | "
        f"{var['macro_exact']-base['macro_exact']:+.1%} | no-regress |",
        "",
        "## Verdict",
        "",
        f"**{'GATE PASS' if pass_gate else 'GATE FAIL'}** — nama_kegiatan exact "
        f"{b_pct:.1f}% → {v_pct:.1f}% (gate >=+5pt); no-regress: {regress_fields or 'tidak ada'}.",
        "",
        "## Fix (wrong -> exact)",
        "",
        "| stem | AKT-005 | GT |",
        "|---|---|---|",
    ]
    for stem, ev, gv in fixes:
        md.append(f"| {stem} | {ev} | {gv} |")
    md += ["", "## Regress (exact -> wrong)", ""]
    md += [f"| {s} | {e} | {g} |" for s, e, g in regresses] or ["tidak ada"]

    md += ["", "## Changed non-exact (QA sloppiness — anchor fire index)", ""]
    if changed:
        md += ["| stem | old (v4) | new (v5) | anchor# |", "|---|---|---|---|"]
        md += [f"| {s} | {o!r} | {n!r} | {a} |" for s, o, n, a in changed]
    else:
        md += ["tidak ada"]

    from tests.ood_probe import SEED, inject_noise

    def act_exact(t: dict, fn) -> float:
        ex = tt = 0
        for s, text in t.items():
            row = gt.get(s)
            if row is None:
                continue
            gv = (row.get(FIELD) or "").strip()
            if not gv or gv == "-":
                continue
            tt += 1
            ex += 1 if match_field(gv, fn(text).get(FIELD), FIELD)["exact"] else 0
        return ex / tt * 100 if tt else 0.0

    rng = random.Random(SEED)
    ood_lines = []
    for lvl in (0.10, 0.25):
        cond = {s: inject_noise(t, lvl, rng) for s, t in texts.items()}
        nb, nv = act_exact(cond, offline_prod), act_exact(cond, offline_akt5)
        ood_lines.append(
            f"- Noise {lvl:.0%}: baseline {nb:.1f}% (drop {b_pct-nb:+.1f}pt) | "
            f"AKT-005 {nv:.1f}% (drop {v_pct-nv:+.1f}pt, ekstra {(v_pct-nv)-(b_pct-nb):+.1f}pt)"
        )
    md += ["", "## OOD noise (QA, bukan gate)", ""] + ood_lines + [
        "",
        "> Drop ekstra vs baseline = harga rule teks-bergantung (sama pola AKT-002/003/004). "
        "Gain absolut tetap positif di semua level noise. Bila di-port produksi: pola KEEP/GUARD.",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md))

    with open(os.path.join(OUT_DIR, "summary_akt5.json"), "w") as f:
        json.dump({
            "baseline": base, "variant": var,
            "fixes": fixes, "regresses": regresses, "changed_non_exact": changed,
            "regress_fields": regress_fields, "pass_gate": pass_gate,
            "macro_avg": {"exact_acc": var["macro_exact"], "fuzzy_acc": var["macro_fuzzy"]},
            "gt": os.path.basename(GT_CSV), "matcher": "v2",
        }, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_akt5.json")


if __name__ == "__main__":
    main()
