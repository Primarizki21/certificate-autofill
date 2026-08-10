"""F1b — Taksonomi mismatch penyelenggara_kegiatan (offline, zero LLM).

Klasifikasi semua kasus non-exact organizer (fuzzy + wrong) dari variant F1
(`offline_variant` di benchmark_org_norm.py — pipeline current 39.2% exact)
menjadi taksonomi penyebab → ceiling riil per kategori + daftar perbaikan.

Kategori:
- kurang_lengkap : extracted benar tapi lebih pendek dari GT (GT menambah
  detail, mis. `Himasada` vs `Himasada, Fakultas Ilmu Komputer`) — masalah
  ekstraksi (butuh enrich konteks fakultas/prodi dari teks).
- kelebihan      : extracted lebih panjang dari GT (residu signature/junk) —
  masalah normalisasi/strip.
- format_residu  : org benar tapi dibungkus junk prefix/suffix (rasio panjang
  ekstrem atau gv ada di ujung ev) — masalah strip residu.
- format         : fuzzy tanpa relasi substring (alias universitas, case/spasi,
  OCR corrupt) — masalah canonical alias / matcher / OCR.
- salah_org      : wrong tapi ada nilai (salah tangkap organisasi lain) —
  masalah scoring ekstraksi.
- kosong         : wrong & nilai kosong (tak terdeteksi).

Gate: taksonomi = input untuk F1 lanjutan; fokus 2 kategori terbesar.

Usage:
  uv run python -m tests.f1b_organizer_taxonomy
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_org_norm import offline_variant
from tests.matchers import match_field
from tests.ood_probe import load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"f1b_taxonomy_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "f1b_organizer_taxonomy.md")

FIELD = "penyelenggara_kegiatan"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def classify(ev: str | None, gv: str) -> tuple[str, str]:
    """Klasifikasi mismatch organizer → (kategori, alasan singkat)."""
    if not ev:
        return "kosong", "nilai kosong (tak terdeteksi)"
    ev_n, gv_n = norm(ev), norm(gv)
    if ev_n and ev_n in gv_n and len(ev_n) < len(gv_n):
        return "kurang_lengkap", f"extracted '{ev}' < GT '{gv}' (GT tambah detail)"
    if gv_n in ev_n:
        return "kelebihan", f"extracted '{ev}' > GT '{gv}' (residu/junk ikut ke-capture)"
    shared = sum(1 for w in ev.lower().split() if w.strip(" ,-") and w.strip(" ,-") in gv.lower().split())
    if shared:
        if ev_n.endswith(gv_n) or ev_n.startswith(gv_n) or len(ev_n) >= 1.5 * len(gv_n):
            return "format_residu", f"junk prefix/suffix di sekitar org: '{ev}' vs '{gv}'"
        return "format", f"fuzzy tanpa substring: '{ev}' vs '{gv}' ({shared} kata sama)"
    return "salah_org", f"extracted '{ev}' tidak menyerupai GT '{gv}'"


def render_md(rows: list[dict], by_cat: dict, stats: dict) -> str:
    lines = [
        "# F1b — Taksonomi Mismatch Penyelenggara (ceiling riil)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"pipeline = offline_variant (F1: organizer_v2 + normalisasi A/B/C) | zero LLM",
        "",
        f"Organizer exact saat ini: **{stats['exact_pct']:.1f}%** "
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
            "kurang_lengkap": "ekstraksi (enrich fakultas/prodi dari teks)",
            "kelebihan": "normalisasi/strip (paling murah)",
            "format_residu": "strip junk prefix/suffix (murah, tanpa sentuh scoring)",
            "format": "canonical alias / matcher / OCR (DIHINDARI dulu — keputusan user)",
            "salah_org": "scoring organizer_v2",
            "kosong": "scoring/deteksi organizer_v2",
        }[cat]
        lines.append(f"| {cat} | {n} | {ceiling}/{stats['total']} ({ceiling/stats['total']*100:.1f}%) | {kind} |")
    lines += [
        "",
        "> Ceiling total (semua kategori, 100% perbaikan): "
        f"**{stats['total']}/{stats['total']} (100.0%)** — target realistis dipilih dari "
        "kategori terbesar, bukan semua sekaligus.",
        "",
        "## Rincian per sertifikat (non-exact)",
        "",
        "| stem | status | extracted | GT | kategori | alasan |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (x["category"], x["stem"])):
        lines.append(
            f"| {r['stem']} | {r['status']} | {r['extracted'] or '(kosong)'} | "
            f"{r['gt']} | {r['category']} | {r['reason']} |"
        )
    lines += [
        "",
        "## Implikasi F1 lanjutan",
        "",
        "- Fokus kategori terbesar dulu (urutan di atas).",
        "- `kurang_lengkap` (ekstraksi benar, GT lebih spesifik): perbaikan = ambil "
        "konteks fakultas/prodi di sekitar organizer dalam teks (mis. `Himasada` + "
        "baris `Fakultas Ilmu Komputer` → `Himasada, Fakultas Ilmu Komputer`).",
        "- `kelebihan`: tambah aturan strip residu — paling murah, tanpa sentuh scoring.",
        "- `format_residu`: strip junk prefix/suffix (mis. `for Being Active ... at`, "
        "`Public Health Career Track 3 Oleh`) — target utama F1 lanjutan (0 LLM, "
        "murni normalisasi).",
        "- `format`: canonical alias = ranah matcher v2.1 (KEPUTUSAN USER: ditunda, "
        "hasil F1 lanjutan menentukan).",
        "- `salah_org`/`kosong`: butuh perbaikan scoring organizer_v2 (luar scope "
        "normalisasi ringan).",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    stats = {"exact": 0, "total": 0}
    by_cat: Counter = Counter()
    rows: list[dict] = []
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        gv = (row.get(FIELD) or "").strip()
        if not gv or gv == "-":
            continue
        ev = offline_variant(text).get(FIELD)
        m = match_field(gv, ev, FIELD)
        stats["total"] += 1
        if m["exact"]:
            stats["exact"] += 1
            continue
        cat, reason = classify(ev, gv)
        by_cat[cat] += 1
        rows.append({
            "stem": stem, "status": "fuzzy" if m["fuzzy"] else "wrong",
            "extracted": ev, "gt": gv, "category": cat, "reason": reason,
        })
    stats["exact_pct"] = stats["exact"] / stats["total"] * 100

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump({"stats": stats, "by_category": dict(by_cat), "rows": rows,
                   "gt": os.path.basename(GT_CSV), "matcher": "v2"}, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(rows, by_cat, stats))
    print(f"Organizer exact: {stats['exact']}/{stats['total']} ({stats['exact_pct']:.1f}%)")
    for cat, n in by_cat.most_common():
        print(f"  {cat:<15} {n}")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
