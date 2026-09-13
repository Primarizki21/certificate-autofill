"""Semantic safety review untuk hasil ekstraksi production."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from app.master_data import FORM_OPTIONS
from app.services.field_extractor import (
    ExtractedValue,
    normalize_for_date,
    scan_date_tokens,
    token_to_ddmmyyyy,
)
from app.services.gemini_extractor import standardize_date
from app.services.organizer_boundary import apply_organizer_boundary
from app.services.title_boundary import apply_title_boundary


@dataclass(frozen=True)
class SemanticReviewAnnotation:
    """Alasan aman dan terstruktur mengapa satu field perlu diperiksa."""

    needs_review: bool
    reasons: tuple[str, ...] = ()


SEMANTIC_FIELDS = (
    "nama_kegiatan_sertifikasi",
    "nomor_bukti_fisik_nomor_sertifikasi",
    "penyelenggara_kegiatan",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "tingkat",
)
OPTIONAL_EMPTY_FIELDS = frozenset(
    {
        "waktu_mulai_pelaksanaan",
        "waktu_selesai_pelaksanaan",
    }
)
_EMPTY_MARKERS = frozenset({"", "-", "null", "none"})
VALID_TINGKAT = frozenset(FORM_OPTIONS.get("tingkat", ()))

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
_NUMERIC_DATE_RE = re.compile(r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b")
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


def _value_and_confidence(value: object) -> tuple[str | None, float]:
    if isinstance(value, ExtractedValue):
        return value.value, float(value.confidence)
    if value is None:
        return None, 0.0
    text = str(value).strip()
    return (text or None), 0.90


def _is_empty(value: str | None) -> bool:
    return not value or value.strip().lower() in _EMPTY_MARKERS


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _canonical_date(value: str | None) -> str | None:
    normalized = standardize_date(value)
    if not normalized:
        return None
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", normalized.strip())
    if not match:
        return None
    day, month, year = match.groups()
    return f"{int(day):02d}/{int(month):02d}/{year}"


def _date_anchor_seen(raw_text: str) -> bool:
    text = normalize_for_date(raw_text or "")
    if _DATE_ANCHOR_RE.search(text):
        return True
    return any(
        token.get("year")
        for token in scan_date_tokens(text)
    )


def _date_seen(raw_text: str, value: str | None) -> bool:
    expected = _canonical_date(value)
    if not expected:
        return False
    text = normalize_for_date(raw_text or "")
    for match in _NUMERIC_DATE_RE.finditer(text):
        if _canonical_date(match.group(0)) == expected:
            return True
    for token in scan_date_tokens(text):
        year = token.get("year")
        if year and token_to_ddmmyyyy(token, str(year)) == expected:
            return True
    for match in _DATE_ANCHOR_RE.finditer(text):
        if _canonical_date(match.group(0)) == expected:
            return True
    return False


def _number_seen(raw_text: str, value: str | None) -> bool:
    compact_value = _compact(value or "")
    return bool(compact_value and compact_value in _compact(raw_text))


def _level_evidence(raw_text: str) -> set[str]:
    text = raw_text or ""
    evidence: set[str] = set()
    for level, patterns in _LEVEL_PATTERNS.items():
        term = "(?:" + "|".join(patterns) + ")"
        before_label = (
            rf"\b(?:tingkat|level|scope|skala|jenjang|cakupan)\b"
            rf"\s*(?:kegiatan|acara|event|competition)?\s*[:\-]?\s*{term}"
        )
        after_label = rf"{term}\s+\b(?:level|scope|scale|tier)\b"
        if re.search(before_label, text, re.IGNORECASE) or re.search(
            after_label, text, re.IGNORECASE
        ):
            evidence.add(level)
    return evidence


def build_semantic_review(
    raw_text: str,
    fields: Mapping[str, object],
) -> dict[str, SemanticReviewAnnotation]:
    """Bangun flag review tanpa mengubah nilai hasil ekstraksi."""
    reasons: dict[str, list[str]] = {
        field_name: [] for field_name in fields if field_name in SEMANTIC_FIELDS
    }

    def add(field_name: str, reason: str) -> None:
        if field_name not in reasons:
            return
        if reason not in reasons[field_name]:
            reasons[field_name].append(reason)

    values: dict[str, str | None] = {}
    for field_name in SEMANTIC_FIELDS:
        if field_name not in fields:
            continue
        value, confidence = _value_and_confidence(fields[field_name])
        values[field_name] = value
        if field_name in OPTIONAL_EMPTY_FIELDS and _is_empty(value):
            if _date_anchor_seen(raw_text):
                add(field_name, "date_value_missing_despite_raw_anchor")
            continue
        if _is_empty(value):
            add(field_name, "missing_value")
        elif confidence < 0.85:
            add(field_name, "low_confidence")

    title_result = apply_title_boundary(
        raw_text, values.get("nama_kegiatan_sertifikasi")
    )
    if title_result.changed:
        add("nama_kegiatan_sertifikasi", title_result.reason)

    organizer_value = values.get("penyelenggara_kegiatan")
    organizer_result = apply_organizer_boundary(raw_text, organizer_value)
    if organizer_result.changed:
        add("penyelenggara_kegiatan", organizer_result.reason)
    elif organizer_value and not _PRIMARY_ORGANIZER_RE.search(raw_text or ""):
        add("penyelenggara_kegiatan", "primary_organizer_anchor_unverified")

    for field_name in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        value = values.get(field_name)
        if value and not _date_seen(raw_text, value):
            add(field_name, "date_value_not_verified_in_raw_ocr")

    number_field = "nomor_bukti_fisik_nomor_sertifikasi"
    number_value = values.get(number_field)
    if number_value and not _number_seen(raw_text, number_value):
        add(number_field, "number_value_not_verified_in_raw_ocr")

    level = values.get("tingkat")
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

    return {
        field_name: SemanticReviewAnnotation(bool(field_reasons), tuple(field_reasons))
        for field_name, field_reasons in reasons.items()
    }


def merge_semantic_reviews(
    *annotation_maps: Mapping[str, SemanticReviewAnnotation],
) -> dict[str, SemanticReviewAnnotation]:
    """Gabungkan flag dari tahap sebelum dan sesudah boundary."""
    merged_reasons: dict[str, list[str]] = {}
    for annotations in annotation_maps:
        for field_name, annotation in annotations.items():
            field_reasons = merged_reasons.setdefault(field_name, [])
            for reason in annotation.reasons:
                if reason not in field_reasons:
                    field_reasons.append(reason)
    return {
        field_name: SemanticReviewAnnotation(bool(field_reasons), tuple(field_reasons))
        for field_name, field_reasons in merged_reasons.items()
    }
