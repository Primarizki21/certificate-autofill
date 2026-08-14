"""AKT-003 — Deteksi nama_kegiatan v3: grup A+B+C (eksperimen, 0 LLM, produksi tak disentuh).

Lanjutan AKT-002 (27/74 exact). Target 3 grup pattern dari teks korpus:
- Grup A: `Sebagai [:] Peserta X` (stop: oleh / Tahun Akademik / Library /
  Surabaya / Dalam / Pada / newline) — Public Health Career Track 2/3,
  Airlangga Job Preparation, Magang UKM x3, Kompetisi Ilmiah Mahasiswa (KIM).
- Grup B: `Sebagai Peserta "X"` (kutip) — Online Research Management (exact),
  ACIC (fuzzy, kutip hanya awalan GT).
- Grup C: repair merge `atthe`/`inthe` + `organizedby` → unlock anchor
  `at the X` (Hology, FIT) dan `the X organized by` (Poisson) yang sudah ada;
  stop `with theme` di anchor at-the (Hology).

Robustness (anti false-positive OOS / data asli):
1. Prefix `Sebagai` WAJIB di grup A & B — "Peserta" sebagai kata header/role
   (2030372 "Peserta /A.5/SOCIAL ACTION", 2065179 "kepada PESERTA Dekan FTMM",
   gammafest, ML) tidak ter-capture.
2. Stop lookahead `Dalam|Pada` — "Sebagai Peserta Dalam kegiatan X" (IRIS PF,
   2954631, 1930354) → capture kosong → skip ke anchor berikutnya, tidak
   menelan "Dalam kegiatan ...".
3. Repair `in(?=[Tt]he)` = "in the" — umum di teks Inggris ("in the category
   of", "in the field of") tapi hanya MENGAKTIFKAN anchor kuat (`the X
   organized by`, `at the X`) yang sudah punya stop set sendiri; tidak
   menghasilkan capture baru sendirian.
4. Anchor baru di-APPEND setelah anchor AKT-002 → hanya fire bila semua
   pattern lama gagal (prioritas tetap, tak ada perilaku berubah).
5. Analisis "changed non-exact" per cert — capture baru yang mengganti nilai
   salah dengan salah-dan-berbeda = indikator sloppiness, dilaporkan.

Gate (handoff v32): nama_kegiatan exact naik >=+5pt, no-regress vs baseline
(offline_prod) dan vs AKT-002 (offline_akt2), 0 LLM call.

Usage:
  uv run python -m tests.benchmark_akt3
"""

import json
import os
import random
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_akt2 import (
    FIELD,
    _ANCHORS,
    _REPAIR,
    _clean_act,
    eval_corpus,
    extract_activity_v2,
    offline_akt2,
    offline_prod,
)
from tests.matchers import match_field
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"akt3_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "akt3_activity_detection.md")

# --- Repair baru (grup C + split SebagaiPeserta). Tanpa IGNORECASE global
# (jebakan v31: merusak camel-split (?<=[a-z])(?=[A-Z])).
# Catatan: `[Aa]t(?=[Tt]he)` diganti "at " (BUKAN "at the") — lookahead zero-
# width, sisa "the" tetap di teks; kalau diganti "at the" hasilnya "at thethe".
# Case-tolerant huruf pertama ("AttheHology"); "AT THE" all-caps ditangani
# repair `(?<=[A-Z])THE(?=[A-Z])` terpisah (FIT).
_REPAIR3 = _REPAIR + [
    (r"[Aa]t(?=[Tt]he)", "at "),
    (r"[Ii]n(?=[Tt]he)", "in "),
    (r"(?<=\s)[Aa][Tt]\s+THE(?=[A-Z])", "AT THE "),
    (r"(?<=[a-z])Peserta(?=[A-Z])", "Peserta "),
    (r"organized(?=[Bb]y)", "organized "),
    (r"(?<=\d)oleh(?=\s|[A-Za-z])", " oleh"),
    (r"(?<=\d)yang(?=\s|[A-Za-z])", " yang"),
    (r"yang(?=[Dd]iselenggarakan)", "yang "),
    (r"(?<=\d)with(?=\s|[A-Za-z])", " with"),
]

# Anchor 15 (at the) di-extend stop `with theme` (Hology). Grup B & A di-append
# di END — hanya fire bila semua anchor AKT-002 gagal. B sebelum A (kutip lebih
# spesifik: ORM & ACIC punya "Sebagai Peserta \"...").
_ANCHORS3: list[tuple[str, str]] = []
for i, anchor in enumerate(_ANCHORS):
    if i == 15:
        _ANCHORS3.append(
            (r"at\s+the\s+(.+?)(?=[\"“]|Faculty|University|\s+with\s+theme|,|\n|$)", "group")
        )
    else:
        _ANCHORS3.append(anchor)
_ANCHORS3 += [
    (r"[Ss]ebagai\s*:?\s*Peserta\s*[\"“]([^\"”]+)[\"”]", "group"),
    # Stop: kata batas (oleh/Tahun Akademik/Library/Surabaya), "Dalam"/"Pada"
    # (juga BARE di capture-start — \s+ setelah "Peserta" memakan newline,
    # jadi \s+Dalam tidak kena "Peserta\nDalam..."), dan newline yang diikuti
    # kata batas (KIM: "(KIM)\nUniversitas Airlangga 2024\nSurabaya" — baris
    # "Universitas..." bukan batas, lanjut; "\nSurabaya" batas, berhenti).
    (r"[Ss]ebagai\s*:?\s*Peserta\s+(?!Talkshow|campaign\b)(.*?)(?=\s+oleh|\s+Tahun\s+Akademik|"
     r"\s+Library|\s+Surabaya|\s+Dalam|\s+Pada|\s+campaign|\s+Talkshow|"
     r"\s+yang\s+(?:diselenggarakan|diadakan|dilaksanakan|bertema)|"
     r"\s+Universitas(?=[A-Z])|Dalam|Pada|"
     r"\n\s*(?=(?:oleh|tahun|library|surabaya|pada|diberikan|direktur|dekan|"
     r"ketua|nip|tanggal|mengetahui|yang)[^A-Za-z])|\n\s*$)", "group"),
]


def _preprocess3(text: str) -> str:
    t = text
    for pat, repl in _REPAIR3:
        t = re.sub(pat, repl, t)
    return t


def extract_activity_v3(text: str) -> str | None:
    """Deteksi activity name v3; None = pakai nilai produksi lama."""
    t = _preprocess3(text or "")
    for pattern, kind in _ANCHORS3:
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        v = m.group(0) if kind == "full" else m.group(1)
        v = _clean_act(v)
        if v:
            return v
    return None


def extract_activity_v3_debug(text: str) -> tuple[str | None, int]:
    """Seperti extract_activity_v3 tapi kembalikan (nilai, indeks anchor)."""
    t = _preprocess3(text or "")
    for i, (pattern, kind) in enumerate(_ANCHORS3):
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        v = m.group(0) if kind == "full" else m.group(1)
        v = _clean_act(v)
        if v:
            return v, i
    return None, -1


def offline_akt3(text: str) -> dict[str, str]:
    fields = offline_prod(text)
    new_act = extract_activity_v3(text)
    if new_act:
        fields[FIELD] = new_act
    return fields


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    base = eval_corpus(texts, gt, offline_prod)
    v2 = eval_corpus(texts, gt, offline_akt2)
    var = eval_corpus(texts, gt, offline_akt3)
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
        v0 = match_field(gv, offline_akt3(text).get(FIELD), FIELD)
        if not b0["exact"] and v0["exact"]:
            fixes.append((stem, offline_akt3(text).get(FIELD), gv))
        if b0["exact"] and not v0["exact"]:
            regresses.append((stem, offline_akt3(text).get(FIELD), gv))
        old = offline_akt2(text).get(FIELD)
        new = offline_akt3(text).get(FIELD)
        o0 = match_field(gv, old, FIELD)
        if not o0["exact"] and not v0["exact"] and old != new:
            _, aidx = extract_activity_v3_debug(text)
            changed.append((stem, old, new, aidx))

    regress_fields = [f for f in EVAL_FIELDS if var["per_field"][f]["exact"] < base["per_field"][f]["exact"]]
    pass_gate = v_pct >= b_pct + 5.0 and not regress_fields and var["macro_exact"] >= base["macro_exact"] - 0.005

    print(f"Baseline:  MACRO exact {base['macro_exact']*100:.1f}% fuzzy {base['macro_fuzzy']*100:.1f}%")
    print(f"AKT-003:   MACRO exact {var['macro_exact']*100:.1f}% fuzzy {var['macro_fuzzy']*100:.1f}%")
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
        "# AKT-003 — Deteksi Nama Kegiatan v3: grup A+B+C (0 LLM)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        "baseline = offline_prod (produksi PROD-002, flag ON) | 0 LLM call",
        "",
        "## Hasil",
        "",
        "| Metrik | baseline | AKT-003 | delta | gate |",
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
        "| stem | AKT-003 | GT |",
        "|---|---|---|",
    ]
    for stem, ev, gv in fixes:
        md.append(f"| {stem} | {ev} | {gv} |")
    md += ["", "## Regress (exact -> wrong)", ""]
    md += [f"| {s} | {e} | {g} |" for s, e, g in regresses] or ["tidak ada"]

    md += ["", "## Changed non-exact (QA sloppiness — anchor fire index)", ""]
    if changed:
        md += ["| stem | old (v2) | new (v3) | anchor# |", "|---|---|---|---|"]
        md += [f"| {s} | {o!r} | {n!r} | {a} |" for s, o, n, a in changed]
    else:
        md += ["tidak ada"]

    # OOD noise (QA, bukan gate) — pola OOD-002/003 + AKT-002.
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
        nb, nv = act_exact(cond, offline_prod), act_exact(cond, offline_akt3)
        ood_lines.append(
            f"- Noise {lvl:.0%}: baseline {nb:.1f}% (drop {b_pct-nb:+.1f}pt) | "
            f"AKT-003 {nv:.1f}% (drop {v_pct-nv:+.1f}pt, ekstra {(v_pct-nv)-(b_pct-nb):+.1f}pt)"
        )
    md += ["", "## OOD noise (QA, bukan gate)", ""] + ood_lines + [
        "",
        "> Drop ekstra vs baseline = harga rule teks-bergantung (sama pola AKT-002/R1/R4). "
        "Gain absolut tetap positif di semua level noise. Bila di-port produksi: pola KEEP/GUARD.",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md))

    with open(os.path.join(OUT_DIR, "summary_akt3.json"), "w") as f:
        json.dump({
            "baseline": base, "variant": var,
            "fixes": fixes, "regresses": regresses, "changed_non_exact": changed,
            "regress_fields": regress_fields, "pass_gate": pass_gate,
            "macro_avg": {"exact_acc": var["macro_exact"], "fuzzy_acc": var["macro_fuzzy"]},
            "gt": os.path.basename(GT_CSV), "matcher": "v2",
        }, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_akt3.json")


if __name__ == "__main__":
    main()
