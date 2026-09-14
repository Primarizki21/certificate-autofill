"""Semantic review annotations for V2 staging outputs."""

from __future__ import annotations

import re
from typing import Any

from tests.date_normalizer import normalize_date
from tests.v2_organizer_boundary import apply_organizer_boundary
from tests.v2_title_boundary import apply_title_boundary

VALID_TINGKAT = {
    "Internasional",
    "Nasional",
    "Universitas",
    "Fakultas",
    "Departemen/Program Studi",
    "Lainnya",
}
OPTIONAL_EMPTY_FIELDS = frozenset(
    {
        "waktu_mulai_pelaksanaan",
        "waktu_selesai_pelaksanaan",
    }
)
_EMPTY_MARKERS = frozenset({"", "-", "null"})


def is_optional_absence(
    field_name: str,
    expected: str | None,
    predicted: str | None,
) -> bool:
    """True bila field opsional kosong di sumber dan hasil ekstraksi."""
    if field_name not in OPTIONAL_EMPTY_FIELDS:
        return False
    expected_text = str(expected or "").strip().lower()
    predicted_text = str(predicted or "").strip().lower()
    return expected_text in _EMPTY_MARKERS and predicted_text in _EMPTY_MARKERS


_DATE_ANCHOR_RE = re.compile(
    r"(?:\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\b\d{1,2}\s+(?:januari|februari|maret|april|mei|juni|juli|agustus|"
    r"september|oktober|november|desember|january|february|march|may|"
    r"june|july|august|october|november|december)\s+\d{4}\b|"
    r"\b(?:januari|februari|maret|april|mei|juni|juli|agustus|september|"
    r"oktober|november|desember|january|february|march|may|june|july|"
    r"august|october|november|december)\s+\d{1,2},?\s+\d{4}\b)",
    re.IGNORECASE,
)
_PRIMARY_ORGANIZER_RE = re.compile(
    r"(?:diselenggarakan|diadakan|dilaksanakan)\s+oleh|"
    r"(?:organized|organised|held|hosted|presented)\s+by",
    re.IGNORECASE,
)
_LEVEL_PATTERNS = {
    "Internasional": (r"\binternasional\b", r"\binternational\b"),
    "Nasional": (r"\bnasional\b", r"\bnational\b"),
    "Universitas": (r"\buniversitas\b", r"\buniversity\b"),
    "Fakultas": (r"\bfakultas\b", r"\bfaculty\b"),
    "Departemen/Program Studi": (
        r"\bdepartemen\b",
        r"\bdepartment\b",
        r"\bprogram\s+studi\b",
        r"\bprodi\b",
        r"\bstudy\s+program\b",
    ),
    "Lainnya": (r"\bukm\b", r"\bbs[o0]\b", r"\bstudent\s+association\b"),
}


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _date_seen(raw_text: str, value: str) -> bool:
    expected = normalize_date(value)
    if not expected:
        return False
    return any(
        normalize_date(match.group(0)) == expected
        for match in _DATE_ANCHOR_RE.finditer(raw_text or "")
    )


def _number_seen(raw_text: str, value: str) -> bool:
    compact_value = _compact(value)
    return bool(compact_value and compact_value in _compact(raw_text))


def _level_evidence(raw_text: str) -> set[str]:
    """Find level terms only near explicit scope/level labels."""
    text = raw_text or ""
    evidence: set[str] = set()
    for level, patterns in _LEVEL_PATTERNS.items():
        term = "(?:" + "|".join(patterns) + ")"
        before_label = (
            rf"\b(?:tingkat|level|scope|skala|jenjang|cakupan)\b"
            rf"\s*(?:kegiatan|acara|event|competition)?\s*[:\-]?\s*{term}"
        )
        after_label = (
            rf"{term}\s+"
            r"\b(?:level|scope|scale|tier)\b"
        )
        if re.search(before_label, text, re.IGNORECASE) or re.search(
            after_label, text, re.IGNORECASE
        ):
            evidence.add(level)
    return evidence


def build_review_annotations(
    raw_text: str,
    fields: dict[str, str],
    *,
    confidence: float = 0.90,
) -> dict[str, dict[str, Any]]:
    title_result = apply_title_boundary(raw_text, fields.get("nama_kegiatan_sertifikasi"))
    organizer_result = apply_organizer_boundary(
        raw_text, fields.get("penyelenggara_kegiatan")
    )
    annotations: dict[str, dict[str, Any]] = {
        field: {"needs_review": False, "reasons": [], "confidence": confidence}
        for field in fields
    }

    def add(field: str, reason: str) -> None:
        if field not in annotations:
            return
        annotations[field]["needs_review"] = True
        if reason not in annotations[field]["reasons"]:
            annotations[field]["reasons"].append(reason)

    for field, value in fields.items():
        value_text = str(value or "").strip().lower()
        if field in OPTIONAL_EMPTY_FIELDS and value_text in _EMPTY_MARKERS:
            if _DATE_ANCHOR_RE.search(raw_text or ""):
                add(field, "date_value_missing_despite_raw_anchor")
            continue
        if not value_text:
            add(field, "missing_value")
        if value and confidence < 0.85:
            add(field, "low_confidence")

    if title_result.changed:
        add("nama_kegiatan_sertifikasi", title_result.reason)

    if organizer_result.changed:
        add("penyelenggara_kegiatan", organizer_result.reason)
    elif fields.get("penyelenggara_kegiatan") and not _PRIMARY_ORGANIZER_RE.search(raw_text or ""):
        add("penyelenggara_kegiatan", "primary_organizer_anchor_unverified")

    for field in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        value = fields.get(field, "")
        if value and not _date_seen(raw_text, value):
            add(field, "date_value_not_verified_in_raw_ocr")

    number_field = "nomor_bukti_fisik_nomor_sertifikasi"
    number_value = fields.get(number_field, "")
    if number_value and not _number_seen(raw_text, number_value):
        add(number_field, "number_value_not_verified_in_raw_ocr")

    level = fields.get("tingkat", "")
    if not level or level not in VALID_TINGKAT:
        add("tingkat", "unmapped_level_enum")
    else:
        evidence = _level_evidence(raw_text)
        if not evidence:
            add("tingkat", "level_evidence_unverified")
        elif len(evidence) > 1:
            add("tingkat", "ambiguous_level_evidence")
        elif level not in evidence:
            add("tingkat", "level_conflicts_with_raw_ocr")

    return annotations


def apply_review_policy(
    raw_text: str,
    fields: dict[str, str],
    *,
    confidence: float = 0.90,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    annotations = build_review_annotations(raw_text, fields, confidence=confidence)
    return dict(fields), annotations
