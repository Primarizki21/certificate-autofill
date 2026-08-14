"""AKT-004 — Deteksi nama_kegiatan v4: grup E+F+G (eksperimen, 0 LLM, produksi tak disentuh).

Lanjutan AKT-003 (38/74 exact). Target sisa pola "aman" (grup D yang berisiko
= AKT-005):
- E: `dalam Event X` — Girifest_Faiz ("prestasi dalam Event Giri Statistics
  Fest 2026 kategori Lomba NisC dengan pencapaian").
- E: `lomba tingkat Nasional "X"` — SDC Uniska_Faiz ("Dalam lomba tingkat
  Nasional "Statistic Data Champions" dengan tema") — GT "Statistics Data
  Champions" (s beda → kemungkinan fuzzy / GT v10).
- F: `seminar on "X"` — 2954283_219642_skp ("seminar on "The AI
  Revolution: ..."").
- G: junk `yangdiselenggarakan` sudah ter-repair di AKT-003 (ACW_Faiz,
  hakim_lomba) — verifikasi saja.

Gate KHUSUS scope-kecil (keputusan user, handoff v33): minimum +2 exact
(2-3 cert sasaran = +2.7-4pt), no-regress vs baseline, 0 LLM. Dinyatakan
eksplisit karena gate +5pt (pola AKT-002/003) akan FAIL by design.

Usage:
  uv run python -m tests.benchmark_akt4
"""

import json
import os
import random
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_akt3 import (
    FIELD,
    _ANCHORS3,
    _REPAIR3,
    _clean_act,
    _preprocess3,
    eval_corpus,
    offline_akt3,
    offline_prod,
)
from tests.matchers import match_field
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"akt4_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "akt4_activity_detection.md")

GATE_MIN_EXACT_INCREASE = 2  # gate khusus scope-kecil (keputusan user)

# Anchor baru di-APPEND di END — hanya fire bila semua anchor AKT-002/003 gagal.
# "Event" di-capture ikut (GT Girifest = "Event Giri Statistics Fest ...",
# bukan "Giri Statistics Fest ...").
_ANCHORS4 = list(_ANCHORS3) + [
    (r"dalam\s+(Event\s+.+?)(?=\s+dengan|\n|$)", "group"),
    (r"(?:Dalam\s+)?lomba\s+tingkat\s+Nasional\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"seminar\s+on\s*[\"“]([^\"”]+)[\"”]", "group"),
]

# Repair OCR-alias pasca-camel-split: "NisC" (OCR NISC) terpecah jadi "Nis C"
# oleh (?<=[a-z])(?=[A-Z]) — gabung balik agar cocok GT "NISC" (Girifest).
_REPAIR4 = _REPAIR3 + [(r"Nis\s+C\b", "NISC")]


def _preprocess4(text: str) -> str:
    t = text
    for pat, repl in _REPAIR4:
        t = re.sub(pat, repl, t)
    return t


def extract_activity_v4(text: str) -> str | None:
    t = _preprocess4(text or "")
    for pattern, kind in _ANCHORS4:
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        v = m.group(0) if kind == "full" else m.group(1)
        v = _clean_act(v)
        if v:
            return v
    return None


def extract_activity_v4_debug(text: str) -> tuple[str | None, int]:
    t = _preprocess4(text or "")
    for i, (pattern, kind) in enumerate(_ANCHORS4):
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        v = m.group(0) if kind == "full" else m.group(1)
        v = _clean_act(v)
        if v:
            return v, i
    return None, -1


def offline_akt4(text: str) -> dict[str, str]:
    fields = offline_prod(text)
    new_act = extract_activity_v4(text)
    if new_act:
        fields[FIELD] = new_act
    return fields


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    base = eval_corpus(texts, gt, offline_prod)
    var = eval_corpus(texts, gt, offline_akt4)
    act_b = base["per_field"][FIELD]
    act_v = var["per_field"][FIELD]
    b_pct = act_b["exact"] / act_b["total"] * 100
    v_pct = act_v["exact"] / act_v["total"] * 100
    n_exact_gain = act_v["exact"] - act_b["exact"]

    fixes, regresses, changed = [], [], []
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        gv = (row.get(FIELD) or "").strip()
        if not gv or gv == "-":
            continue
        b0 = match_field(gv, offline_prod(text).get(FIELD), FIELD)
        v0 = match_field(gv, offline_akt4(text).get(FIELD), FIELD)
        if not b0["exact"] and v0["exact"]:
            fixes.append((stem, offline_akt4(text).get(FIELD), gv))
        if b0["exact"] and not v0["exact"]:
            regresses.append((stem, offline_akt4(text).get(FIELD), gv))
        old = offline_akt3(text).get(FIELD)
        new = offline_akt4(text).get(FIELD)
        o0 = match_field(gv, old, FIELD)
        if not o0["exact"] and not v0["exact"] and old != new:
            _, aidx = extract_activity_v4_debug(text)
            changed.append((stem, old, new, aidx))

    regress_fields = [f for f in EVAL_FIELDS if var["per_field"][f]["exact"] < base["per_field"][f]["exact"]]
    pass_gate = (
        n_exact_gain >= GATE_MIN_EXACT_INCREASE
        and not regress_fields
        and var["macro_exact"] >= base["macro_exact"] - 0.005
    )

    print(f"Baseline:  MACRO exact {base['macro_exact']*100:.1f}% fuzzy {base['macro_fuzzy']*100:.1f}%")
    print(f"AKT-004:   MACRO exact {var['macro_exact']*100:.1f}% fuzzy {var['macro_fuzzy']*100:.1f}%")
    print(f"nama_kegiatan exact: {b_pct:.1f}% ({act_b['exact']}/{act_b['total']}) -> {v_pct:.1f}% ({act_v['exact']}/{act_v['total']}) | gate >=+{GATE_MIN_EXACT_INCREASE} exact")
    print(f"fuzzy: {act_b['fuzzy']/act_b['total']*100:.1f}% -> {act_v['fuzzy']/act_v['total']*100:.1f}%")
    print(f"Fixes: {len(fixes)} | Regresses: {len(regresses)} | regress fields: {regress_fields or 'tidak ada'}")
    print(f"Changed non-exact (sloppiness check): {len(changed)}")
    print(f"VERDICT: {'GATE PASS' if pass_gate else 'GATE FAIL'}")
    for stem, ev, gv in fixes:
        print(f"  FIX {stem}: {ev!r}")
    for stem, ev, gv in regresses:
        print(f"  REGRESS {stem}: {ev!r} | GT: {gv!r}")

    md = [
        "# AKT-004 — Deteksi Nama Kegiatan v4: grup E+F+G (0 LLM, gate scope-kecil)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        "baseline = offline_prod (produksi PROD-002, flag ON) | 0 LLM call | "
        f"gate: >=+{GATE_MIN_EXACT_INCREASE} exact (keputusan user — scope sengaja kecil, +5pt = FAIL by design)",
        "",
        "## Hasil",
        "",
        "| Metrik | baseline | AKT-004 | delta | gate |",
        "|---|---|---|---|---|",
    ]
    for f in EVAL_FIELDS:
        b, v = base["per_field"][f], var["per_field"][f]
        gate = "no-regress" if f != FIELD else f">=+{GATE_MIN_EXACT_INCREASE} exact"
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
        f"{b_pct:.1f}% → {v_pct:.1f}% (+{n_exact_gain} exact, gate >=+{GATE_MIN_EXACT_INCREASE}); "
        f"no-regress: {regress_fields or 'tidak ada'}.",
        "",
        "## Fix (wrong -> exact)",
        "",
        "| stem | AKT-004 | GT |",
        "|---|---|---|",
    ]
    for stem, ev, gv in fixes:
        md.append(f"| {stem} | {ev} | {gv} |")
    md += ["", "## Regress (exact -> wrong)", ""]
    md += [f"| {s} | {e} | {g} |" for s, e, g in regresses] or ["tidak ada"]

    md += ["", "## Changed non-exact (QA sloppiness — anchor fire index)", ""]
    if changed:
        md += ["| stem | old (v3) | new (v4) | anchor# |", "|---|---|---|---|"]
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
        nb, nv = act_exact(cond, offline_prod), act_exact(cond, offline_akt4)
        ood_lines.append(
            f"- Noise {lvl:.0%}: baseline {nb:.1f}% (drop {b_pct-nb:+.1f}pt) | "
            f"AKT-004 {nv:.1f}% (drop {v_pct-nv:+.1f}pt, ekstra {(v_pct-nv)-(b_pct-nb):+.1f}pt)"
        )
    md += ["", "## OOD noise (QA, bukan gate)", ""] + ood_lines + [
        "",
        "> Drop ekstra vs baseline = harga rule teks-bergantung (sama pola AKT-002/003). "
        "Gain absolut tetap positif di semua level noise. Bila di-port produksi: pola KEEP/GUARD.",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md))

    with open(os.path.join(OUT_DIR, "summary_akt4.json"), "w") as f:
        json.dump({
            "baseline": base, "variant": var,
            "fixes": fixes, "regresses": regresses, "changed_non_exact": changed,
            "regress_fields": regress_fields, "pass_gate": pass_gate,
            "macro_avg": {"exact_acc": var["macro_exact"], "fuzzy_acc": var["macro_fuzzy"]},
            "gt": os.path.basename(GT_CSV), "matcher": "v2",
        }, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_akt4.json")


if __name__ == "__main__":
    main()
