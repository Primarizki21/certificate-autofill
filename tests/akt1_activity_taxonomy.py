"""AKT-001 — Taksonomi mismatch nama_kegiatan_sertifikasi (offline, zero LLM).

Klasifikasi semua kasus non-exact activity name dari jalur produksi PROD-002
(`offline_prod` — pipeline produksi, flag ENABLE_ORGANIZER_NORMALIZATION ON)
menjadi taksonomi penyebab → ceiling riil per kategori + daftar perbaikan.

Kategori (adaptasi dari F1b organizer, khusus activity name):
- kosong         : extractor return None — masalah DETEKSI (pattern coverage).
- salah_kegiatan : extracted kegiatan LAIN (false positive keyword, mis. PKKMB/
                   Specta/Mawacana) — masalah guard/scoring keyword.
- kurang_lengkap : extracted substring GT (prefix "Kepengurusan", suffix tahun,
                   truncation) — masalah enrich/normalisasi.
- kelebihan      : GT substring extracted (junk suffix "Untuk Kat...",
                   "Pada Perlombaan...") — masalah strip residu.
- format_ocr     : near-match dgn overlap kata (case/OCR typo, mis.
                   "Psy-accretion 2.o" vs "Psy-Accretation 2.0").

Kolom tambahan `in_text` (khusus kosong): apakah nama kegiatan GT muncul di teks
raw (compact match / overlap kata ≥0.5) — membedakan "pattern coverage kurang"
(deteksi feasible dari teks) vs "nama kegiatan tidak ada di teks" (butuh
LLM/OCR baru). Sinyal langsung untuk arah AKT-002.

Report-only (preceden F1B): peta sebelum AKT-002, bukan eksperimen gate.

Usage:
  uv run python -m tests.akt1_activity_taxonomy
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_prod_port import offline_prod
from tests.matchers import match_field
from tests.ood_probe import load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"akt1_taxonomy_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "akt1_activity_taxonomy.md")

FIELD = "nama_kegiatan_sertifikasi"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def in_text(gv: str, text: str) -> bool:
    """Apakah nama kegiatan GT (sebagian besar) ada di teks raw?"""
    if not text or not gv:
        return False
    cg = norm(gv)
    if cg and cg in norm(text):
        return True
    gw = {w.strip(" ,-") for w in gv.lower().split() if w.strip(" ,-")}
    if not gw:
        return False
    tw = set(re.findall(r"[a-z0-9]+", text.lower()))
    hit = sum(1 for w in gw if w in tw)
    return hit / len(gw) >= 0.5


def classify(ev: str | None, gv: str) -> tuple[str, str]:
    """Klasifikasi mismatch activity name → (kategori, alasan singkat)."""
    if not ev:
        return "kosong", "nilai kosong (tak terdeteksi)"
    ev_n, gv_n = norm(ev), norm(gv)
    if ev_n and ev_n in gv_n and len(ev_n) < len(gv_n):
        return "kurang_lengkap", f"extracted '{ev}' < GT '{gv}' (prefix/suffix/tahun hilang)"
    if gv_n in ev_n:
        return "kelebihan", f"extracted '{ev}' > GT '{gv}' (junk ikut ke-capture)"
    ev_words = [w.strip(" ,-") for w in ev.lower().split() if w.strip(" ,-")]
    gv_words = [w.strip(" ,-") for w in gv.lower().split() if w.strip(" ,-")]
    shared = sum(1 for w in ev_words if w in gv_words)
    if shared:
        return "format_ocr", f"near-match (case/OCR/alias): '{ev}' vs '{gv}' ({shared} kata sama)"
    return "salah_kegiatan", f"extracted '{ev}' != GT '{gv}' (false positive/org lain)"


def render_md(rows: list[dict], by_cat: dict, stats: dict, kosong_in_text: int) -> str:
    lines = [
        "# AKT-001 — Taksonomi Mismatch Nama Kegiatan (ceiling riil)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"pipeline = offline_prod (produksi PROD-002, flag ON) | zero LLM",
        "",
        f"Nama kegiatan exact saat ini: **{stats['exact_pct']:.1f}%** "
        f"({stats['exact']}/{stats['total']}). Sisa {stats['total'] - stats['exact']} non-exact "
        f"diklasifikasikan di bawah. Ceiling per kategori = jumlah kasus — kalau SEMUA kasus "
        "kategori itu diperbaiki (asumsi optimis, ceiling atas).",
        "",
        "## Taksonomi & ceiling",
        "",
        "| Kategori | Kasus | Ceiling exact bila diperbaiki | Jenis perbaikan |",
        "|---|---|---|---|",
    ]
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        ceiling = stats["exact"] + n
        kind = {
            "kosong": "DETEKSI (perluas pattern + repair OCR-merge)",
            "salah_kegiatan": "guard/scoring keyword extractor",
            "kurang_lengkap": "enrich prefix/suffix dari teks",
            "kelebihan": "strip junk suffix (murah)",
            "format_ocr": "canonical alias / case norm (matcher v2.1)",
        }[cat]
        lines.append(f"| {cat} | {n} | {ceiling}/{stats['total']} ({ceiling/stats['total']*100:.1f}%) | {kind} |")
    lines += [
        "",
        "## Sinyal deteksi (kosong) — feasibility AKT-002",
        "",
        f"- **{kosong_in_text}/{by_cat.get('kosong', 0)}** kasus kosong: nama kegiatan GT "
        "MUNCUL di teks raw (compact/overlap) → deteksi regex feasible dari teks, tinggal "
        "pattern coverage.",
        f"- {by_cat.get('kosong', 0) - kosong_in_text} kasus kosong: nama kegiatan TIDAK "
        "terwakili di teks (OCR gagal / hanya lewat konteks) → butuh LLM per-field atau OCR baru.",
        "",
        "> Ceiling total (semua kategori, 100% perbaikan): "
        f"**{stats['total']}/{stats['total']} (100.0%)** — target realistis dipilih dari "
        "kategori terbesar, bukan semua sekaligus.",
        "",
        "## Rincian per sertifikat (non-exact)",
        "",
        "| stem | status | extracted | GT | kategori | alasan | in_text |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (x["category"], x["stem"])):
        lines.append(
            f"| {r['stem']} | {r['status']} | {r['extracted'] or '(kosong)'} | "
            f"{r['gt']} | {r['category']} | {r['reason']} | {'ya' if r['in_text'] else 'tidak'} |"
        )
    lines += [
        "",
        "## Implikasi AKT-002",
        "",
        "- Dominan `kosong` = masalah DETEKSI, bukan normalisasi (berbeda dari organizer). "
        "Perbaikan = perluas pola regex (Indonesia + Inggris) + repair OCR word-merge "
        "(pola `_preprocess` organizer_v2: `dalamkegiatan`, `dalamrangkaianacara`).",
        "- `salah_kegiatan` (PKKMB/Specta/Mawacana false positive): keyword hardcode "
        "`AIRNOLOGY/KAKIWIMA/SPECTA/BRIEF` terlalu agresif — perlu guard konteks "
        "(mis. hanya fire bila tak ada pattern lain yang match).",
        "- `kurang_lengkap`/`kelebihan`: normalisasi ringan (strip junk + enrich prefix).",
        "- `format_ocr`: alias/case normalization — ranah matcher v2.1 (keputusan user).",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    stats = {"exact": 0, "total": 0}
    by_cat: Counter = Counter()
    rows: list[dict] = []
    kosong_in_text = 0
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        gv = (row.get(FIELD) or "").strip()
        if not gv or gv == "-":
            continue
        ev = offline_prod(text).get(FIELD)
        m = match_field(gv, ev, FIELD)
        stats["total"] += 1
        if m["exact"]:
            stats["exact"] += 1
            continue
        cat, reason = classify(ev, gv)
        by_cat[cat] += 1
        it = in_text(gv, text)
        if cat == "kosong" and it:
            kosong_in_text += 1
        rows.append({
            "stem": stem, "status": "fuzzy" if m["fuzzy"] else "wrong",
            "extracted": ev, "gt": gv, "category": cat, "reason": reason, "in_text": it,
        })
    stats["exact_pct"] = stats["exact"] / stats["total"] * 100

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump({"stats": stats, "by_category": dict(by_cat), "rows": rows,
                   "kosong_in_text": kosong_in_text,
                   "gt": os.path.basename(GT_CSV), "matcher": "v2"}, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(rows, by_cat, stats, kosong_in_text))
    print(f"Nama kegiatan exact: {stats['exact']}/{stats['total']} ({stats['exact_pct']:.1f}%)")
    for cat, n in by_cat.most_common():
        print(f"  {cat:<15} {n}")
    print(f"  kosong dengan GT ada di teks: {kosong_in_text}/{by_cat.get('kosong', 0)}")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
