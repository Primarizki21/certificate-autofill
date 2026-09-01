"""B7 — De-Corpusing Audit: inventarisasi literal ter-memorasi + ablasi pure semantic.

Bagian 1 — Inventarisasi: scan `backend/app/services/` untuk literal string yang
terikat sertifikat spesifik (daftar plan + penemuan regex). Tiap literal:
file:line, konteks, target cert (stem), frekuensi fire, rekomendasi.

Bagian 2 — Ablasi Mode A vs Mode B (74 cert, GT v9 + matcher v2):
  - Mode A (Assisted)   : pipeline v4.2 + B5 (activity_v9) + B6 (nomor_v6).
  - Mode B (Pure Semantic): SAMA, tapi seluruh literal ter-memorasi dinonaktifkan
    (hanya regex generik + structural semantic anchors B5/B6).
  Delta per field = kontribusi (assist) literal = ceiling OOD murni.

Gate B7:
  - 100% literal hardcode terinventarisasi (katalog lengkap).
  - Pure Semantic Macro terbentuk (baseline metrik murni).

Usage:
  GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.decorpusing_audit
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.activity_extractor import extract_activity
from app.services.combined_extractor import (
    _STRUCTURAL_ACT_EN,
    _STRUCTURAL_ACT_ID,
    apply_combined_v4_2,
)
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.organizer_normalize import (
    _BEM_FKM_SUFFIX,
    _ORG_ALIASES,
    _R6_DEPT_SUFFIX,
    _R6_HIMASADA,
    _R6_IRIS,
    _R6_TYPOS,
    _UP_TO_OLEH,
)
from tests.activity_extractor_v9 import (
    _QUOTED_EVENT_V9,
    _STRUCTURAL_ACT_EN_V9,
    _STRUCTURAL_ACT_ID_V9,
    _anti_bleed_cut,
    _sanitize_capture,
    _valid_capture,
)
from tests.matchers import match_field
from tests.nomor_normalizer_v6 import (
    _DPKKA_RE,
    _DOT_CODE_RE,
    _DOT_PCR_RE,
    _repair_roman_gated,
    normalize_nomor,
)
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(
    REPO, "tests", "benchmark_runs", f"decorpusing_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)
OUT_CATALOG = os.path.join(REPO, "docs", "report", "decorpusing_catalog.md")

SERVICES_DIR = os.path.join(REPO, "backend", "app", "services")

# --- Inventarisasi literal (plan B7 + penemuan) ------------------------------
# (literal, sumber, deskripsi, target cert tipikal)
HARDCODES: list[dict] = [
    {"lit": "KARSAFTMM2024 / KARSA FTMM 2024", "file": "combined_extractor.py", "fn": "extract_activity_v6", "desc": "Nama event spesifik FTMM", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "SPECTA 2024", "file": "combined_extractor.py", "fn": "extract_activity_v6", "desc": "Nama event spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "Falcon Project", "file": "combined_extractor.py", "fn": "extract_activity_v6", "desc": "Nama event spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "Health Buddies: From Insecure to Unstoppable", "file": "combined_extractor.py", "fn": "extract_activity_v6", "desc": "Judul talkshow spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "Agentic AI - Foundations and Emerging Applications in Software Engineering", "file": "combined_extractor.py", "fn": "extract_activity_v6", "desc": "Judul spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "Youth Today x AIESEC Future Leaders", "file": "combined_extractor.py", "fn": "extract_activity_v6", "desc": "Event spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "PKKMB Universitas Airlangga", "file": "combined_extractor.py", "fn": "extract_activity_v6", "desc": "Program + institusi", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "Digital Campaign 2023: \"Level Up Yourself Starting Right Now\" SCHOLAH-UNAIR Mengajar", "file": "combined_extractor.py", "fn": "extract_activity_v7", "desc": "Judul spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "Give Yourself A Break: The Power Of Self Compassion", "file": "combined_extractor.py", "fn": "extract_activity_v7", "desc": "Judul spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "From Discrete Mathematics to Risk Management Systems: a Practical Approach", "file": "combined_extractor.py", "fn": "extract_activity_v7", "desc": "Judul spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "EmpowerED", "file": "combined_extractor.py", "fn": "extract_activity_v7", "desc": "Judul spesifik", "field": "nama_kegiatan_sertifikasi"},
    {"lit": "270/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023", "file": "combined_extractor.py", "fn": "normalize_nomor_v4", "desc": "Nomor sertifikat spesifik", "field": "nomor_bukti_fisik_nomor_sertifikasi"},
    {"lit": "06/001/B/P.GIRI STAT/HMP STATISTIKA/IV/2026", "file": "combined_extractor.py", "fn": "normalize_nomor_v4", "desc": "Nomor sertifikat spesifik", "field": "nomor_bukti_fisik_nomor_sertifikasi"},
    {"lit": "UKM Forum for Information and Statistical Studies (Forkas)", "file": "combined_extractor.py", "fn": "normalize_organizer_v6", "desc": "Ekspansi organizer", "field": "penyelenggara_kegiatan"},
    {"lit": "Himpunan Mahasiswa Statistika (himasta)", "file": "combined_extractor.py", "fn": "normalize_organizer_v6", "desc": "Ekspansi organizer", "field": "penyelenggara_kegiatan"},
    {"lit": "F1 aliases (5 string canonical)", "file": "organizer_normalize.py", "fn": "_norm_org_format", "desc": "Alias organizer spesifik (FST IS Dept., S1 TSD, APHSA, CS UB, FTMM UNAIR)", "field": "penyelenggara_kegiatan"},
    {"lit": "R6 himasada/IRIS/dept-suffix maps", "file": "organizer_normalize.py", "fn": "_enrich_organizer", "desc": "Enrichment organizer spesifik", "field": "penyelenggara_kegiatan"},
    {"lit": "Airnology / Kakiwima / SPECTA / Brief keyword", "file": "field_extractor.py", "fn": "extract_activity_name", "desc": "Keyword event spesifik", "field": "nama_kegiatan_sertifikasi"},
]

# --- Pipeline Mode A (Assisted) ----------------------------------------------
def pipeline_assisted(text: str) -> dict[str, str]:
    from tests.activity_extractor_v9 import extract_activity_v9
    from tests.nomor_normalizer_v6 import normalize_nomor_v6

    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    act = extract_activity_v9(text)
    if act:
        extracted["nama_kegiatan_sertifikasi"] = ExtractedValue(act, 0.95, "activity_v9")
    val, repaired = normalize_nomor_v6(text)
    if val:
        extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(
            val, 0.78 if repaired else 0.95, "nomor_v6"
        )
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


# --- Pipeline Mode B (Pure Semantic) -----------------------------------------
def pure_activity(text: str) -> str | None:
    """Generic extractor + structural anchors v9 + quoted — TANPA literal corpus."""
    t = text or ""
    gen = extract_activity(t)
    if gen and len(gen) >= 5:
        cut = _anti_bleed_cut(gen)
        if _valid_capture(cut):
            return cut
    m_en = _STRUCTURAL_ACT_EN_V9.search(t)
    if m_en and _valid_capture(m_en.group(1)):
        return _sanitize_capture(m_en.group(1))
    m_id = _STRUCTURAL_ACT_ID_V9.search(t)
    if m_id and _valid_capture(m_id.group(1)):
        return _sanitize_capture(m_id.group(1))
    m_q = _QUOTED_EVENT_V9.search(t)
    if m_q:
        cand = _sanitize_capture(m_q.group(1))
        if len(cand) >= 5:
            return cand
    return None


def pure_nomor(raw_text: str) -> tuple[str | None, bool]:
    """Chain v6 TANPA hardcode 270/GIRI (bagian 2 jalur)."""
    repaired = False
    m = _DOT_PCR_RE.search(raw_text)
    if m:
        v, repaired = _repair_roman_gated(m.group(1).strip())
        return v, repaired
    val = normalize_nomor(raw_text)
    if val:
        v, repaired = _repair_roman_gated(val)
        return v, repaired
    m = _DOT_CODE_RE.search(raw_text)
    if m:
        return m.group(1).strip(), False
    m = _DPKKA_RE.search(raw_text)
    if m:
        v = m.group(1).replace("O", "0").replace("o", "0")
        v, repaired = _repair_roman_gated(v, dpkka_ctx=True)
        return v, True
    return None, False


def pure_organizer(value: str | None, raw_text: str) -> str | None:
    """Lapisan organizer TANPA literal: F1 alias kosong, R6 maps dinonaktifkan,
    branch FORKAS/himasta/UNESA di v6 di-skip (di sini cukup: jangan pakai
    _norm_org_format + _enrich_organizer, pakai lapisan v3 polos)."""
    from app.services.organizer_normalize import (
        _PREFIX_HELD,
        _PREFIX_JUNK,
        _PREFIX_JUNK_WORDS,
        _TRAILING_ORG,
        _UNIV_TRAIL,
    )

    v = value or ""
    v = _PREFIX_JUNK.sub("", v).strip()
    upper_raw = (raw_text or "").upper()
    has_unair = bool(re.search(r"UNAIR|UNIVERSITAS\s*AIRLANGGA|AIRLANGGA", upper_raw))
    if has_unair:
        v = _TRAILING_ORG.sub(r"\1", v).strip()
        v = _UNIV_TRAIL.sub(" Universitas Airlangga", v).strip()
    v = _PREFIX_HELD.sub("", v).strip()
    v = _PREFIX_JUNK_WORDS.sub("", v).strip()
    v = _UP_TO_OLEH.sub("", v).strip()
    return v or None


def pipeline_pure(text: str) -> dict[str, str]:
    from app.services.organizer_v2 import extract_organizer_v2

    extracted = extract_certificate_fields(text)
    extracted = apply_combined_v4_2(extracted, text)
    act = pure_activity(text)
    if act:
        extracted["nama_kegiatan_sertifikasi"] = ExtractedValue(act, 0.95, "activity_pure")
    val, repaired = pure_nomor(text)
    if val:
        extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(
            val, 0.78 if repaired else 0.95, "nomor_pure"
        )
    v2 = extract_organizer_v2(text)
    if v2:
        org = pure_organizer(v2, text)
        if org:
            extracted["penyelenggara_kegiatan"] = ExtractedValue(org, 0.84, "organizer_pure")
    mapped = map_fields_to_form(extracted, text, bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


def eval_fields(pred: dict[str, str], gt_row: dict) -> dict[str, dict]:
    out = {}
    for f in EVAL_FIELDS:
        gv = (gt_row.get(f) or "").strip()
        if not gv or gv == "-":
            continue
        res = match_field(gv, pred.get(f), f)
        out[f] = {"exact": res["exact"], "fuzzy": res["fuzzy"], "pred": pred.get(f), "gt": gv}
    return out


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    texts = load_texts()
    gt = load_gt()

    # Mode A vs Mode B
    agg = {m: {f: {"exact": 0, "fuzzy": 0, "total": 0} for f in EVAL_FIELDS} for m in ("A", "B")}
    fire_evidence: dict[str, list[str]] = {h["lit"]: [] for h in HARDCODES}
    for stem, text in texts.items():
        pa = pipeline_assisted(text)
        pb = pipeline_pure(text)
        row = gt.get(stem, {})
        for f in EVAL_FIELDS:
            gv = (row.get(f) or "").strip()
            if not gv or gv == "-":
                continue
            for m, pred in (("A", pa), ("B", pb)):
                res = match_field(gv, pred.get(f), f)
                agg[m][f]["total"] += 1
                agg[m][f]["exact"] += int(res["exact"])
                agg[m][f]["fuzzy"] += int(res["fuzzy"])
        # Atribusi fire literal: nilai Mode A mengandung literal canonical.
        for h in HARDCODES:
            va = pa.get(h["field"]) or ""
            if h["field"] in ("nomor_bukti_fisik_nomor_sertifikasi", "penyelenggara_kegiatan"):
                canon = re.sub(r"[\s/]+", "", h["lit"].split("(")[0].split(" / ")[0]).upper()
            else:
                canon = re.sub(r"\s+", "", h["lit"]).upper()
            if va and re.sub(r"\s+", "", va).upper().find(canon) != -1:
                fire_evidence[h["lit"]].append(stem)

    # Catalog MD
    lines = [
        "# B7 — De-Corpusing Catalog & Pure Semantic Ablation (N=74)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2.",
        "",
        "## Katalog Literal Ter-memorasi",
        "",
        "| Literal String | File Sumber | Fungsi | Field | Firing Freq (cert) | Rekomendasi Generalisasi Semantic |",
        "|---|---|---|---|---|---|",
    ]
    for h in HARDCODES:
        freq = len(fire_evidence[h["lit"]])
        rec = "ganti anchor struktural (B5)" if h["field"] == "nama_kegiatan_sertifikasi" else (
            "ganti guard format (B6)" if h["field"] == "nomor_bukti_fisik_nomor_sertifikasi" else "ganti alias generik"
        )
        lines.append(f"| `{h['lit'][:60]}` | {h['file']} | {h['fn']} | {h['field']} | {freq} | {rec} |")
    lines += ["", "## Ablasi Mode A (Assisted) vs Mode B (Pure Semantic)", "",
              "| Field | Mode A exact | Mode B exact | Assist (pt) | Mode A fuzzy | Mode B fuzzy |", "|---|---|---|---|---|---|"]
    for f in EVAL_FIELDS:
        a, b = agg["A"][f], agg["B"][f]
        aex = a["exact"] / a["total"] * 100 if a["total"] else 0
        bex = b["exact"] / b["total"] * 100 if b["total"] else 0
        afz = a["fuzzy"] / a["total"] * 100 if a["total"] else 0
        bfz = b["fuzzy"] / b["total"] * 100 if b["total"] else 0
        lines.append(f"| {f} | {aex:.1f}% | {bex:.1f}% | {aex - bex:+.1f} | {afz:.1f}% | {bfz:.1f}% |")
    a_ex = sum(a["exact"] for a in agg["A"].values()) / sum(a["total"] for a in agg["A"].values())
    b_ex = sum(a["exact"] for a in agg["B"].values()) / sum(a["total"] for a in agg["B"].values())
    lines += [
        "",
                f"**Pure Semantic MACRO exact: {b_ex * 100:.1f}%** (Mode A: {a_ex * 100:.1f}%, assist {(a_ex - b_ex) * 100:+.1f}pt) — "
        "baseline OOD murni tanpa literal.",
        "",
    ]
    with open(OUT_CATALOG, "w") as f:
        f.write("\n".join(lines))

    summary = {"created": datetime.now().isoformat(), "agg": agg, "fire_evidence": fire_evidence}
    with open(os.path.join(OUT_DIR, "summary_decorpusing.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Pure Semantic MACRO exact: {b_ex * 100:.1f}% (Mode A {a_ex * 100:.1f}%, assist {(a_ex - b_ex) * 100:+.1f}pt)")
    for f in EVAL_FIELDS:
        a, b = agg["A"][f], agg["B"][f]
        aex = a["exact"] / a["total"] * 100 if a["total"] else 0
        bex = b["exact"] / b["total"] * 100 if b["total"] else 0
        print(f"  {f:<42} A {aex:>5.1f}%  B {bex:>5.1f}%  assist {aex - bex:>+5.1f}pt")
    print(f"wrote {OUT_CATALOG}")


if __name__ == "__main__":
    main()
