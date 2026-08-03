"""Handoff v7 — mismatch taxonomy for organizer / tingkat errors.

Classifies each mismatched row into one or more of the v7 error categories so
the team can triage where to spend extraction effort. This is a triage helper,
not a tuned classifier: the point is consistent, auditable categorization.

Categories (v7 section "Phase 0 - Reproduce and Classify Errors"):
- organizer_missing_or_wrong
- ocr_garbled_or_duplicated
- english_faculty_dept_conflict
- hima_bem_scope_ambiguity
- national_international_scale_ambiguity
- missing_evidence_in_certificate
- wrong_llm_output_or_invalid
"""

import re
from collections import Counter

ORGANIZER_PHRASES = [
    "DISELENGGARAKAN", "DIADAKAN", "ORGANIZED", "ORGANISED",
    "HELD BY", "PRESENTED BY", "ORGANIZER", "ORGANISER",
]
ORGANIZER_KEYWORDS = [
    "BEM", "BADAN EKSEKUTIF", "HIMA", "HIMPUNAN", "UKM", "UNIT KEGIATAN",
    "FAKULTAS", "DEPARTEMEN", "PRODI", "PROGRAM STUDI", "DEPT", "DEPARTMENT",
    "REKTORAT", "DIREKTORAT", "KEMAHASISWAAN", "SENAT", "LEMBAGA", "UNIVERSITAS",
    "SCHOOL OF", "FACULTY",
]
SCALE_KEYWORDS = [
    "NASIONAL", "NATIONAL", "INTERNASIONAL", "INTERNATIONAL",
]
SIGNER_ROLES = ["DEKAN", "DIREKTUR", "KETUA", "NIP", "REKTOR", "PRESIDEN"]

_JOINED_PHRASES = "|".join(re.escape(p) for p in ORGANIZER_PHRASES)
_GARBLED_RE = re.compile(r"^[A-Z0-9]{9,}$")
_CERT_RE = re.compile(r"\b\d{2,4}/[A-Z0-9.]+/[A-Z0-9./]+/\d{4}\b")
# Legit single-word all-caps boilerplate headers — not OCR garbling.
_HEADER_WORDS = {
    "SERTIFIKAT", "CERTIFICATE", "PIAGAM", "PENGHARGAAN",
    "APPRECIATION", "ACKNOWLEDGMENT", "DELIBERATION", "UNIVERSITAS",
    "AIRLANGGA",
}


def _has_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


def _garbled_lines(text: str) -> list[str]:
    return [
        l for l in text.splitlines()
        if _GARBLED_RE.match(l.strip()) and l.strip() not in _HEADER_WORDS
    ]


def classify(
    field: str,
    expected: str,
    actual: str,
    raw_text: str,
) -> list[str]:
    """Return category list for one mismatch row.

    field: 'penyelenggara_kegiatan' or 'tingkat' (others return []).
    expected/actual: ground truth vs extracted value.
    raw_text: full certificate text (uppercased internally).
    """
    if field not in ("penyelenggara_kegiatan", "tingkat"):
        return []
    upper = (raw_text or "").upper()
    cats = []

    garbled = _garbled_lines(upper)
    phrase = _has_any(upper, ORGANIZER_PHRASES)
    org_kw = _has_any(upper, ORGANIZER_KEYWORDS)
    scale = _has_any(upper, SCALE_KEYWORDS)
    has_faculty = "FACULTY" in upper
    has_dept = any(k in upper for k in ("DEPT", "DEPARTMENT", "STUDY PROGRAM"))
    has_hima = any(k in upper for k in ("HIMA", "HIMPUNAN"))
    has_bem = any(k in upper for k in ("BEM", "BADAN EKSEKUTIF"))

    # 1) OCR garbled: merged all-caps runs, or no clean organizer line despite phrase.
    if garbled and (phrase or not org_kw):
        cats.append("ocr_garbled_or_duplicated")

    # 2) English FACULTY vs DEPT conflict.
    if has_faculty and has_dept:
        cats.append("english_faculty_dept_conflict")

    # 3) Scale ambiguity when a scale word appears and GT is Nasional/Internasional.
    if scale and expected in ("Nasional", "Internasional"):
        cats.append("national_international_scale_ambiguity")

    # 4) HIMA/BEM scope ambiguity when level is not spelled out.
    if (has_hima or has_bem) and not (
        has_faculty or "REKTORAT" in upper or "DIREKTORAT" in upper or "UNIVERSITAS" in upper
    ):
        cats.append("hima_bem_scope_ambiguity")

    # 5) No evidence at all in the certificate.
    if not phrase and not org_kw and not scale:
        cats.append("missing_evidence_in_certificate")

    # 6) Organizer specific: organizer signal exists but extraction lost it.
    if field == "penyelenggara_kegiatan":
        if phrase and not cats:
            cats.append("organizer_missing_or_wrong")
        if not cats:
            cats.append("organizer_missing_or_wrong")

    # 7) Tingkat default: evidence present but LLM picked wrong label.
    if field == "tingkat" and not cats:
        cats.append("wrong_llm_output_or_invalid")

    return cats


def build_taxonomy_report(rows: list[dict]) -> dict:
    """Summarize categorized rows.

    rows: list of dicts with keys filename, field, expected, actual, categories.
    """
    by_field = {"penyelenggara_kegiatan": Counter(), "tingkat": Counter()}
    totals = {"penyelenggara_kegiatan": 0, "tingkat": 0}
    for r in rows:
        f = r["field"]
        if f not in by_field:
            continue
        totals[f] += 1
        for c in r["categories"]:
            by_field[f][c] += 1
    return {
        "total_mismatches": sum(totals.values()),
        "totals": totals,
        "by_field": {f: dict(c) for f, c in by_field.items()},
    }


if __name__ == "__main__":
    sample = """SERTIFIKAT
UNIVERSITAS AIRLANGGA
542/A.5/SOCIAL ACTION/BEM FEB UNAIR/XI/2023
PESERTA
dalam acara yang diselenggarakan oleh Badan Eksekutif
Mahasiswa Fakultas Ekonomi dan Bisnis Universitas Airlangga
"""
    got = classify("penyelenggara_kegiatan", "BEM FEB UNAIR", "Universitas Airlangga", sample)
    assert "organizer_missing_or_wrong" in got, got
    en = "FACULTY OF SCIENCE AND TECHNOLOGY\nINFORMATION SYSTEMS DEPT."
    got_en = classify("penyelenggara_kegiatan", "Departemen", "Faculty", en)
    assert "english_faculty_dept_conflict" in got_en, got_en
    national = "LOMBA KARYA TULIS NASIONAL yang diselenggarakan oleh KEMENRISTEK"
    got_n = classify("tingkat", "Nasional", "Universitas", national)
    assert "national_international_scale_ambiguity" in got_n, got_n
    print("ok: mismatch_taxonomy")
