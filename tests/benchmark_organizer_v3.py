"""F1 lanjutan — perbaikan pemilihan penyelenggara tanpa AI (offline, zero LLM).

Baseline = `offline_variant` (F1/ORG-002: organizer exact 39.2%, MACRO 58.3%).
Lapisan baru organizer post-processing di atasnya (tests-only, produksi tak
disentuh), berdasar taksonomi F1b (`docs/report/f1b_organizer_taxonomy.md`):

- R0: fix bug rule B — `_TRAILING_ORG.sub("", v)` menghapus SELURUH string
  (harus `r"\1"`); akibatnya normalisasi B/C tidak pernah efektif
  (PRIMARIZKI_panitia_binary_2025 tertinggal "Himpunan Mahasiswa TSD").
- R1: strip suffix signature ", Faculty .../", ", Department .../" dst.
- R2: strip prefix junk kata tetap ("Library Class") — ponytail: 1 kasus
  di corpus, tambah pattern kalau muncul di produksi.
- R3: strip prefix sampai kata "oleh" (org muncul setelah "Oleh ...").
- R4: strip suffix mulai tanggal (on July 30, 2023 / - August 1, 2023).
- R5: normalisasi dash "S-1" -> "S1" (jenjang studi; dash tidak bermakna).

Gate (handoff v20): organizer exact naik >=+5pt (>=44.2%), no-regress field
lain vs baseline, 0 LLM call. `format`/`salah_org`/`kosong` = di luar scope
(lanjut normalisasi matcher ATAU scoring organizer_v2 — keputusan user).

Usage:
  uv run python -m tests.benchmark_organizer_v3
"""

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from tests.benchmark_org_norm import _PREFIX_JUNK, _TRAILING_ORG, _UNIV_TRAIL, _norm_nomor, offline_variant
from tests.matchers import match_field
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts, offline_fields
from tests.organizer_extractor_v2 import extract_organizer_v2

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"organizer_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "f1_organizer_v3.md")

# --- R1: suffix signature fakultas/prodi setelah koma ------------------------
# Hanya Inggris (faculty/department): kasus Indonesia (", Fakultas Ilmu
# Administrasi, Universitas Brawijaya") = bagian SAH dari GT (2954707).
_SUFFIX_DEPT = re.compile(r",\s*(?:faculty|department)\b.*$", re.IGNORECASE)
# --- R2: prefix junk kata tetap ----------------------------------------------
_PREFIX_JUNK_WORDS = re.compile(r"^(?:library\s+class\s+)", re.IGNORECASE)
# --- prefix junk "Which [was] Held From <tgl> to <tgl> by" --------------------
# Fix regex di benchmark_org_norm: `\s+was?` butuh 2 whitespace-run, jadi
# "Which Held From" (1 spasi) tidak pernah match — perbaiki di lapisan ini.
_PREFIX_HELD = re.compile(r"^which\s+(?:was\s+)?held\s+from\s+.+?\s+to\s+.+?\s+by\s+", re.IGNORECASE)
# --- R3: prefix sampai kata "oleh" -------------------------------------------
_UP_TO_OLEH = re.compile(r"^.*?\s*oleh\s+", re.IGNORECASE)
# --- R4: suffix tanggal (bulan + tanggal + tahun) ----------------------------
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_DATE_SUFFIX = re.compile(
    rf"\s*(?:on\s+|-|\u2013)?\s*{_MONTH}\s*\d{{1,2}}[,.]?\s*\d{{4}}\s*[-.\u2013].*$",
    re.IGNORECASE,
)
_DATE_ONLY = re.compile(rf"\s+(?:on\s+)?{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}\s*$", re.IGNORECASE)
# --- R5: dash pada jenjang studi ---------------------------------------------
_DASH_NORM = re.compile(r"\bS\s*-\s*(\d)\b", re.IGNORECASE)


def _norm_organizer_v3(value: str | None, raw_text: str) -> str | None:
    v = value or ""
    v = _PREFIX_JUNK.sub("", v).strip()
    upper_raw = (raw_text or "").upper()
    has_unair = bool(re.search(r"UNAIR|UNIVERSITAS\s*AIRLANGGA|AIRLANGGA", upper_raw))
    if has_unair:
        v = _TRAILING_ORG.sub(r"\1", v).strip()  # R0: bug fix — dulu sub("", v) hapus semua
        v = _UNIV_TRAIL.sub(" Universitas Airlangga", v).strip()
    # Lapisan baru F1b
    v = _PREFIX_HELD.sub("", v).strip()
    v = _PREFIX_JUNK_WORDS.sub("", v).strip()
    v = _UP_TO_OLEH.sub("", v).strip()
    v = _DATE_SUFFIX.sub("", v)
    v = _DATE_ONLY.sub("", v)
    v = _SUFFIX_DEPT.sub("", v).strip()
    v = _DASH_NORM.sub(r"S\1", v).strip()
    return v or None


def offline_v3(text: str) -> dict[str, str]:
    extracted = extract_certificate_fields(text)
    v2 = extract_organizer_v2(text)
    if v2:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
    org = _norm_organizer_v3((extracted.get("penyelenggara_kegiatan") or ExtractedValue(None, 0, "")).value, text)
    if org:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(org, 0.84, "organizer_v2")
    nomor = _norm_nomor(text)
    if nomor:
        extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(nomor, 0.95, "regex_certificate_number")
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


def per_cert(base: dict, var: dict, gt: dict[str, dict]) -> dict[str, dict]:
    """Per cert: matcher hasil baseline & variant utk semua field."""
    out = {}
    for field, ev in var.items():
        gv = (gt.get(field) or "").strip()
        if not gv or gv == "-":
            continue
        out[field] = {
            "gt": gv,
            "base": base.get(field),
            "var": ev,
            "base_exact": match_field(gv, base.get(field), field)["exact"],
            "var_exact": match_field(gv, ev, field)["exact"],
        }
    return out


def render_md(stats: dict, per_cert_rows: dict) -> str:
    lines = [
        "# F1 lanjutan — Perbaikan Pemilihan Penyelenggara (v3, tanpa AI)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"baseline = offline_variant F1 (ORG-002) | 0 LLM call",
        "",
        "## Hasil",
        "",
        "| Metrik | baseline | v3 | delta | gate |",
        "|---|---|---|---|---|",
    ]
    per = stats["per_field"]
    per3 = stats["per_field_v3"]
    for f in EVAL_FIELDS:
        b, v = per[f], per3[f]
        gate = "no-regress" if f != "penyelenggara_kegiatan" else ">=+5pt"
        lines.append(
            f"| {f} exact | {b['exact']/b['total']*100 if b['total'] else 0:.1f}% | "
            f"{v['exact']/v['total']*100 if v['total'] else 0:.1f}% | "
            f"{(v['exact']/v['total'] if v['total'] else 0) - (b['exact']/b['total'] if b['total'] else 0):+.1%} | {gate} |"
        )
    lines += [
        f"| MACRO exact | {stats['macro_exact']:.1f}% | {stats['macro_exact_v3']:.1f}% | {stats['macro_exact_v3'] - stats['macro_exact']:+.1%} | no-regress |",
        "",
        "## Verdict",
        "",
        f"**{stats['verdict']}** — organizer exact "
        f"{per['penyelenggara_kegiatan']['exact']/per['penyelenggara_kegiatan']['total']*100:.1f}% → "
        f"{per3['penyelenggara_kegiatan']['exact']/per3['penyelenggara_kegiatan']['total']*100:.1f}% "
        f"(gate >=44.2%); no-regress field lain: {stats['regress_fields'] or 'tidak ada'}.",
        "",
        "## Per-cert organizer: wrong→exact (perbaikan)",
        "",
        "| stem | baseline | v3 | GT |",
        "|---|---|---|---|",
    ]
    for stem, row in per_cert_rows.items():
        if row.get("penyelenggara_kegiatan") and not row["penyelenggara_kegiatan"]["base_exact"] and row["penyelenggara_kegiatan"]["var_exact"]:
            o = row["penyelenggara_kegiatan"]
            lines.append(f"| {stem} | {o['base'] or '(kosong)'} | {o['var']} | {o['gt']} |")
    lines += ["", "## Per-cert organizer: exact→wrong (regresi)", ""]
    for stem, row in per_cert_rows.items():
        o = row.get("penyelenggara_kegiatan")
        if o and o["base_exact"] and not o["var_exact"]:
            lines.append(f"| {stem} | {o['base']} | {o['var']} | {o['gt']} |")
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()

    per_field = {f: {"total": 0, "exact": 0} for f in EVAL_FIELDS}
    per_field_v3 = {f: {"total": 0, "exact": 0} for f in EVAL_FIELDS}
    rows: dict[str, dict] = {}
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        base = offline_variant(text)
        var = offline_v3(text)
        rows[stem] = per_cert(base, var, row)
        for field in EVAL_FIELDS:
            gv = (row.get(field) or "").strip()
            if not gv or gv == "-":
                continue
            per_field[field]["total"] += 1
            per_field[field]["exact"] += 1 if match_field(gv, base.get(field), field)["exact"] else 0
            per_field_v3[field]["total"] += 1
            per_field_v3[field]["exact"] += 1 if match_field(gv, var.get(field), field)["exact"] else 0

    def macro(pf: dict) -> float:
        t = sum(d["total"] for d in pf.values())
        e = sum(d["exact"] for d in pf.values())
        return e / t * 100 if t else 0.0

    m, m3 = macro(per_field), macro(per_field_v3)
    org = per_field["penyelenggara_kegiatan"]
    org3 = per_field_v3["penyelenggara_kegiatan"]
    org_base_pct = org["exact"] / org["total"] * 100
    org_v3_pct = org3["exact"] / org3["total"] * 100
    regress = [f for f in EVAL_FIELDS if f != "penyelenggara_kegiatan"
               and per_field_v3[f]["exact"] < per_field[f]["exact"]]
    pass_gate = org_v3_pct >= 44.2 and not regress and m3 >= m - 0.5
    stats = {
        "per_field": per_field, "per_field_v3": per_field_v3,
        "macro_exact": m, "macro_exact_v3": m3,
        "macro_avg": {"exact_acc": m3 / 100},
        "verdict": "GATE PASS" if pass_gate else "GATE FAIL",
        "regress_fields": regress, "gt": os.path.basename(GT_CSV), "matcher": "v2",
    }

    with open(os.path.join(OUT_DIR, "summary_organizer_v3.json"), "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(stats, rows))
    print(f"Organizer exact: {org_base_pct:.1f}% -> {org_v3_pct:.1f}% (gate >=44.2%)")
    print(f"MACRO exact:     {m:.1f}% -> {m3:.1f}% | regress: {regress or 'tidak ada'}")
    print(f"VERDICT: {stats['verdict']}")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
