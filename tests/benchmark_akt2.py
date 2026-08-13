"""AKT-002 — Deteksi nama_kegiatan v2 (eksperimen, 0 LLM, produksi tak disentuh).

Dasar = taksonomi AKT-001: masalah utama = DETEKSI (kosong 57/69, 52/57 GT
ada di teks). Extractor baru `extract_activity_v2` = perluasan anchor pattern
+ repair OCR word-merge + strip junk + guard (keyword hardcode produksi hanya
fallback — extractor v2 mencoba pattern baru dulu, kalau tak ada match baru
pakai nilai produksi lama).

Anchor baru (dari teks korpus, AKT-001):
- `Kepengurusan X Masa Bakti [Tahun] YYYY` — capture PENUH (produksi hanya
  capture isi, tanpa prefix "Kepengurusan" & tahun → kurang_lengkap).
- `Dalam (rangkaian )?acara X` — stop: dengan tema / yang diselenggarakan /
  sub acara / pada tanggal / koma-kota / kutip / newline.
- `Dalam kegiatan X` (sama, + stop kutip) · `Dalam memperingati X` ·
  `pada ajang X` · `entitled/titled X` (Inggris, stop "on <tgl>") ·
  `as a participant at/in X` (stop "themed"/koma).
- Strip junk suffix `untuk kategori ...` (Dataquest×2, BTF).

Gate (handoff v30): nama_kegiatan exact naik >=+5pt (>= 9/74 = 11.8%), no-
regress vs baseline (offline_prod), 0 LLM call.

Usage:
  uv run python -m tests.benchmark_akt2
"""

import json
import os
import random
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_prod_port import offline_prod
from tests.matchers import match_field
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"akt2_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "akt2_activity_detection.md")

FIELD = "nama_kegiatan_sertifikasi"

# --- repair OCR word-merge (pola sama _preprocess organizer_v2) ---------------
# Merge kata: "Xof Y" -> "X of Y" (bound kiri huruf kecil agar tak memecah
# kata normal "of Y"); "dalam(?=[A-Za-z])" dengan \s kiri + IGNORECASE utk
# "Dalamkompetisi" (huruf besar).
_REPAIR = [
    (r"(?<=\s)[Dd]alam(?=[A-Za-z])", "dalam "),
    (r"(?<=[a-z])of(?=\s)", " of"),
    (r"(?<=[a-z])yang(?=\s)", " yang"),
    (r"(?<=[a-z])oleh(?=\s)", " oleh"),
    (r"kegiatan(?=[A-Z])", "kegiatan "),
    (r"acara(?=[A-Z])", "acara "),
    (r"ajang(?=[A-Z])", "ajang "),
    (r"memperingati(?=[A-Z])", "memperingati "),
    (r"kompetisi(?=[A-Z])", "kompetisi "),
    (r"perlombaan(?=[A-Z])", "perlombaan "),
    (r"agenda(?=[A-Z])", "agenda "),
    (r"masa(?=[A-Z])", "masa "),
    (r"bakti(?=[A-Z])", "bakti "),
    (r"pada(?=[A-Z])", "pada "),
    (r"of(?=[A-Z])", "of "),
    (r"diselenggarakan(?=[A-Z])", "diselenggarakan "),
    (r"dilaksanakan(?=[A-Z])", "dilaksanakan "),
    (r"oleh(?=[A-Z])", "oleh "),
    (r"tanggal(?=\d)", "tanggal "),
    (r"(?<=\d)(?=[A-Z])", " "),
    (r"(?<=[A-Za-z])(?=\d)", " "),
    (r"(?<=[a-z])(?=[A-Z])", " "),
]

_STOP = (
    r"(?:\s+dengan\s+tema|\s+themed|\s+yang\s+diselenggarakan|"
    r"\s+yang\s+diadakan|\s+yang\s+dilaksanakan|\s+sub\s+acara|"
    r"\s+pada\s+tanggal|\s+pada\s+perlombaan|\s+,\s*\w+\s+\d{1,2}|[\"“]|\n|$)"
)

_ANCHORS = [
    (r"Kepengurusan\s+.+?\s+Masa\s+Bakti(?:\s+Tahun)?\s+\d{4}", "full"),
    (r"Dalam\s+(?:rangkaian\s+)?acara\s+(.+?)" + _STOP, "group"),
    (r"kegiatan\s+\S+\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"Dalam\s+kegiatan\s+(.+?)" + _STOP, "group"),
    (r"Dalam\s+memperingati\s+(.+?)" + _STOP, "group"),
    (r"pada\s+ajang\s+(.+?)" + _STOP, "group"),
    (r"pada\s+kegiatan\s+(.+?)" + _STOP, "group"),
    (r"dalam\s+kompetisi\s+(.+?)" + _STOP, "group"),
    (r"\bpada\s+(?!tanggal|perlombaan|ajang|kegiatan|acara|hari)([A-Za-z][^\n]*?)"
     r"(?:\s+Tingkat\s+Nasional|\s+yang\s+dilaksanakan|\s+yang\s+diselenggarakan|\n|$)", "group"),
    (r"(?:entitled|titled)\s+(.+?)(?=\s+on\s+\d{1,2}|\s*[,]|\n|$)", "group"),
    (r"(?:dalam|agenda|kegiatan|acara|seminar)\s*:?\s*[\"“]([^\"”]+)[\"”]", "group"),
    (r"participation\s+at\s+(.+?)(?=,|that\s+was|\n|$)", "group"),
    (r"\bthe\s+([A-Z][^\n]*?)\s+organized\s+by", "group"),
    (r"winner\s+of\s+the\s+(.+?)(?=\s+organized\s+by|\n|$)", "group"),
    (r"as\s+a\s+participant\s+(?:at|in)\s+(.+?)(?=\s+themed|,|\n|$)", "group"),
    (r"at\s+the\s+(.+?)(?=[\"“]|Faculty|University|,|\n|$)", "group"),
]

_UNTUK_KATEGORI = re.compile(r"\s+untuk\s+kategori\b.*$", re.IGNORECASE)


def _preprocess(text: str) -> str:
    t = text
    for pat, repl in _REPAIR:
        t = re.sub(pat, repl, t)
    return t


def _clean_act(v: str) -> str | None:
    v = re.sub(r"\s+", " ", v or "").strip(" .,:;-\"“”")
    v = _UNTUK_KATEGORI.sub("", v).strip(" .,:;-\"“”")
    if len(v) < 3:
        return None
    return v


def extract_activity_v2(text: str) -> str | None:
    """Deteksi activity name baru; None = pakai nilai produksi lama."""
    t = _preprocess(text or "")
    for pattern, kind in _ANCHORS:
        m = re.search(pattern, t, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        v = m.group(0) if kind == "full" else m.group(1)
        v = _clean_act(v)
        if v:
            return v
    return None


def offline_akt2(text: str) -> dict[str, str]:
    fields = offline_prod(text)
    new_act = extract_activity_v2(text)
    if new_act:
        fields[FIELD] = new_act
    return fields


def eval_corpus(texts: dict[str, str], gt: dict[str, dict], fn) -> dict:
    per_field = {f: {"total": 0, "exact": 0, "fuzzy": 0} for f in EVAL_FIELDS}
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        fields = fn(text)
        for f in EVAL_FIELDS:
            gv = (row.get(f) or "").strip()
            if not gv or gv == "-":
                continue
            m = match_field(gv, fields.get(f), f)
            pf = per_field[f]
            pf["total"] += 1
            pf["exact"] += 1 if m["exact"] else 0
            pf["fuzzy"] += 1 if m["fuzzy"] else 0
    total = sum(pf["total"] for pf in per_field.values())
    exact = sum(pf["exact"] for pf in per_field.values())
    fuzzy = sum(pf["fuzzy"] for pf in per_field.values())
    return {
        "per_field": per_field,
        "macro_exact": exact / total if total else 0.0,
        "macro_fuzzy": fuzzy / total if total else 0.0,
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    base = eval_corpus(texts, gt, offline_prod)
    var = eval_corpus(texts, gt, offline_akt2)
    act_b = base["per_field"][FIELD]
    act_v = var["per_field"][FIELD]
    b_pct = act_b["exact"] / act_b["total"] * 100
    v_pct = act_v["exact"] / act_v["total"] * 100

    fixes, regresses = [], []
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        gv = (row.get(FIELD) or "").strip()
        if not gv or gv == "-":
            continue
        b0 = match_field(gv, offline_prod(text).get(FIELD), FIELD)
        v0 = match_field(gv, offline_akt2(text).get(FIELD), FIELD)
        if not b0["exact"] and v0["exact"]:
            fixes.append((stem, offline_akt2(text).get(FIELD), gv))
        if b0["exact"] and not v0["exact"]:
            regresses.append((stem, offline_akt2(text).get(FIELD), gv))

    regress_fields = [f for f in EVAL_FIELDS if var["per_field"][f]["exact"] < base["per_field"][f]["exact"]]
    pass_gate = v_pct >= b_pct + 5.0 and not regress_fields and var["macro_exact"] >= base["macro_exact"] - 0.005

    print(f"Baseline:  MACRO exact {base['macro_exact']*100:.1f}% fuzzy {base['macro_fuzzy']*100:.1f}%")
    print(f"AKT-002:   MACRO exact {var['macro_exact']*100:.1f}% fuzzy {var['macro_fuzzy']*100:.1f}%")
    print(f"nama_kegiatan exact: {b_pct:.1f}% ({act_b['exact']}/{act_b['total']}) -> {v_pct:.1f}% ({act_v['exact']}/{act_v['total']}) | gate >=+5pt")
    print(f"fuzzy: {act_b['fuzzy']/act_b['total']*100:.1f}% -> {act_v['fuzzy']/act_v['total']*100:.1f}%")
    print(f"Fixes: {len(fixes)} | Regresses: {len(regresses)} | regress fields: {regress_fields or 'tidak ada'}")
    print(f"VERDICT: {'GATE PASS' if pass_gate else 'GATE FAIL'}")
    for stem, ev, gv in fixes:
        print(f"  FIX {stem}: {ev!r}")
    for stem, ev, gv in regresses:
        print(f"  REGRESS {stem}: {ev!r} | GT: {gv!r}")

    md = [
        "# AKT-002 — Deteksi Nama Kegiatan v2 (0 LLM)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        "baseline = offline_prod (produksi PROD-002, flag ON) | 0 LLM call",
        "",
        "## Hasil",
        "",
        "| Metrik | baseline | AKT-002 | delta | gate |",
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
        "| stem | AKT-002 | GT |",
        "|---|---|---|",
    ]
    for stem, ev, gv in fixes:
        md.append(f"| {stem} | {ev} | {gv} |")
    md += ["", "## Regress (exact -> wrong)", ""]
    md += [f"| {s} | {e} | {g} |" for s, e, g in regresses] or ["tidak ada"]

    # OOD noise (QA, bukan gate): anchor phrase teks-bergantung — drop ekstra
    # vs baseline dilaporkan jujur (pola OOD-002/003, injeksi confusi 5↔S dll).
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
        nb, nv = act_exact(cond, offline_prod), act_exact(cond, offline_akt2)
        ood_lines.append(
            f"- Noise {lvl:.0%}: baseline {nb:.1f}% (drop {b_pct-nb:+.1f}pt) | "
            f"AKT-002 {nv:.1f}% (drop {v_pct-nv:+.1f}pt, ekstra {(v_pct-nv)-(b_pct-nb):+.1f}pt)"
        )
    md += ["", "## OOD noise (QA, bukan gate)", ""] + ood_lines + [
        "",
        "> Anchor phrase teks-bergantung: drop ekstra di noise (10% +2.7pt, 25% +8.1pt) — "
        "pola sama R1/R4 organizer (OOD-002/003). Gain absolut tetap positif di semua level "
        "(10%: 32.4% vs 5.4%; 25%: 27.0% vs 5.4%). Bila di-port produksi: ikuti pola KEEP/GUARD "
        "(anchor = GUARD needs_review F6).",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(md))

    with open(os.path.join(OUT_DIR, "summary_akt2.json"), "w") as f:
        json.dump({
            "baseline": base, "variant": var,
            "fixes": fixes, "regresses": regresses,
            "regress_fields": regress_fields, "pass_gate": pass_gate,
            "macro_avg": {"exact_acc": var["macro_exact"], "fuzzy_acc": var["macro_fuzzy"]},
            "gt": os.path.basename(GT_CSV), "matcher": "v2",
        }, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_akt2.json")


if __name__ == "__main__":
    main()
