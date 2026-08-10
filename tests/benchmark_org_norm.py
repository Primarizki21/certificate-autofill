"""F1 Roadmap v10 — Normalisasi organizer & nomor (offline, zero LLM).

Baseline = pipeline offline current (extract_certificate_fields → organizer_v2 →
map_fields_to_form, no LLM), GT v9 + matcher v2.

Variant pipeline-side (tanpa menyentuh evaluator):
- Organizer post-normalisasi (lapisan luar organizer_v2, tests-only):
  A. strip prefix junk "Which Held From <date> to <date> by " (residu phrase)
  B. strip trailing "Himpunan Mahasiswa X"/"BEM X" bila org sudah punya konteks
     universitas (duplicate capture phrase + signature block)
  C. trailing "Universitas" → "Universitas Airlangga" bila raw punya konteks
     UNAIR/AIRLANGGA (GT canonical)
- Nomor:
  D. fallback ekstraksi pada raw text (tanpa normalize_text — normalize_text
     memecah "UN27"/"NACOESTA4.0" → regex nomor gagal)
  E. pattern ke-4: prefix SERT- + titik ("0101.17/STF/PCR/2025") + spasi internal

Gate (roadmap F1): organizer exact naik ≥+5pt vs baseline · nomor no-regress ·
MACRO no-regress · 0 LLM call.

Usage:
  uv run python -m tests.benchmark_org_norm
"""

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import ExtractedValue, extract_certificate_fields, extract_certificate_number
from app.services.form_mapper import map_fields_to_form
from tests.evaluation_framework import load_csv
from tests.matchers import match_field
from tests.organizer_extractor_v2 import extract_organizer_v2
from tests.ood_probe import EVAL_FIELDS, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"org_norm_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

# --- Variant A: strip prefix junk phrase -------------------------------------
_PREFIX_JUNK = re.compile(
    r"^which\s+was?\s+held\s+from\s+.+?\s+to\s+.+?\s+by\s+",
    re.IGNORECASE,
)
# --- Variant B: trailing HIMA/BEM setelah org berkonteks universitas ---------
# Hanya strip bila value SUDAH punya konteks universitas/fakultas/prodi —
# org yang murni hima (mis. "Himpunan Mahasiswa S1 Akuntansi") TIDAK di-strip.
_TRAILING_ORG = re.compile(
    r"^(?=.*(?:universitas|fakultas|program studi))(.+?)\s+"
    r"(?:himpunan\s+mahasiswa\s+\S+|bem\s+\S+|him[a-z0-9]*)\s*$",
    re.IGNORECASE,
)
# --- Variant C: trailing "Universitas" -> "Universitas Airlangga" -------------
_UNIV_TRAIL = re.compile(r"\s+universitas\s*$", re.IGNORECASE)


def _norm_organizer(value: str, raw_text: str) -> str:
    """Variant organizer: post-normalisasi pipeline-side (tests-only)."""
    v = value or ""
    v = _PREFIX_JUNK.sub("", v).strip()
    upper_raw = (raw_text or "").upper()
    has_unair = bool(re.search(r"UNAIR|UNIVERSITAS\s*AIRLANGGA|AIRLANGGA", upper_raw))
    if has_unair:
        v = _TRAILING_ORG.sub("", v).strip()
        v = _UNIV_TRAIL.sub(" Universitas Airlangga", v).strip()
    return v or None


# --- Variant D+E: nomor dengan fallback raw text + pattern ke-4 ---------------
_SERT_PATTERN = re.compile(
    r"\b(SERT\s*[-.]?\s*[0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]+?/?\s*[0-9]{4})\b",
    re.IGNORECASE,
)
_DOT_PATTERN = re.compile(
    r"\b([0-9]{2,6}\.[0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]+?/?\s*[0-9]{4})\b",
    re.IGNORECASE,
)
_SPACE_PATTERN = re.compile(
    r"\b([0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]+?/?\s*[0-9]{4})\b",
    re.IGNORECASE,
)


def _norm_nomor(raw_text: str) -> str | None:
    """SERT pattern duluan (menangkap prefix), lalu pattern 1-3, lalu titik/spasi."""
    m = _SERT_PATTERN.search(raw_text)
    if m:
        return re.sub(r"\s+", "", m.group(1)).strip(" .,:;-")
    found = extract_certificate_number(raw_text)
    if found:
        return found
    for pat in (_DOT_PATTERN, _SPACE_PATTERN):
        m = pat.search(raw_text)
        if m:
            return re.sub(r"\s+", "", m.group(1)).strip(" .,:;-")
    return None


def offline_variant(text: str) -> dict[str, str]:
    extracted = extract_certificate_fields(text)
    v2 = extract_organizer_v2(text)
    if v2:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
    # Normalisasi pipeline-side
    org = _norm_organizer((extracted.get("penyelenggara_kegiatan") or ExtractedValue(None, 0, "")).value, text)
    if org:
        extracted["penyelenggara_kegiatan"] = ExtractedValue(org, 0.84, "organizer_v2")
    nomor = _norm_nomor(text)
    if nomor:
        extracted["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(nomor, 0.95, "regex_certificate_number")
    mapped = map_fields_to_form(extracted, tahun_akademik="", bukti_fisik="Sertifikat")
    return {f: (mapped.get(f).value if mapped.get(f) else None) for f in EVAL_FIELDS}


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
    from tests.ood_probe import offline_fields

    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    baseline = eval_corpus(texts, gt, offline_fields)
    variant = eval_corpus(texts, gt, offline_variant)
    print(f"Baseline:  MACRO exact {baseline['macro_exact']:.4f} fuzzy {baseline['macro_fuzzy']:.4f}")
    print(f"Variant:   MACRO exact {variant['macro_exact']:.4f} fuzzy {variant['macro_fuzzy']:.4f}")
    print(f"{'field':<40}{'base ex':>8}{'var ex':>8}{'base fu':>8}{'var fu':>8}")
    for f in EVAL_FIELDS:
        b, v = baseline["per_field"][f], variant["per_field"][f]
        print(f"{f:<40}{b['exact']/b['total']*100 if b['total'] else 0:>7.1f}%"
              f"{v['exact']/v['total']*100 if v['total'] else 0:>7.1f}%"
              f"{b['fuzzy']/b['total']*100 if b['total'] else 0:>7.1f}%"
              f"{v['fuzzy']/v['total']*100 if v['total'] else 0:>7.1f}%")

    # Per-cert diff organizer/nomor: yang berubah dari wrong → exact
    print("\nFix organizer (wrong→exact):")
    n_org = n_nom = 0
    for stem, text in texts.items():
        row = gt.get(stem)
        if row is None:
            continue
        gv = (row.get("penyelenggara_kegiatan") or "").strip()
        if gv and gv != "-":
            b0 = match_field(gv, offline_fields(text).get("penyelenggara_kegiatan"), "penyelenggara_kegiatan")
            v0 = match_field(gv, offline_variant(text).get("penyelenggara_kegiatan"), "penyelenggara_kegiatan")
            if not b0["exact"] and v0["exact"]:
                n_org += 1
                print(f"  {stem}: {offline_variant(text).get('penyelenggara_kegiatan')!r}")
        gv = (row.get("nomor_bukti_fisik_nomor_sertifikasi") or "").strip()
        if gv and gv != "-":
            b0 = match_field(gv, offline_fields(text).get("nomor_bukti_fisik_nomor_sertifikasi"), "nomor_bukti_fisik_nomor_sertifikasi")
            v0 = match_field(gv, offline_variant(text).get("nomor_bukti_fisik_nomor_sertifikasi"), "nomor_bukti_fisik_nomor_sertifikasi")
            if not b0["exact"] and v0["exact"]:
                n_nom += 1
                print(f"  {stem}: {offline_variant(text).get('nomor_bukti_fisik_nomor_sertifikasi')!r}")
    print(f"Organizer fixed: {n_org} | Nomor fixed: {n_nom}")

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump({"baseline": baseline, "variant": variant, "n_org_fixed": n_org, "n_nom_fixed": n_nom,
                   "gt": os.path.basename(GT_CSV), "matcher": "v2"}, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_DIR}/summary.json")


if __name__ == "__main__":
    main()
