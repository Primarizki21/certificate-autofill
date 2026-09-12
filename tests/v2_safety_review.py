"""Semantic review annotations for V2 staging outputs."""

from __future__ import annotations

import re
from typing import Any

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
_DATE_ANCHOR_RE = re.compile(
    r"(?:\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}\s+"
    r"(?:januari|februari|maret|april|mei|juni|juli|agustus|september|"
    r"oktober|november|desember|january|february|march|may|june|july|"
    r"august|september|october|november|december)\s+\d{4}\b)",
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
    if not value or not _DATE_ANCHOR_RE.search(raw_text or ""):
        return False
    digits = re.sub(r"\D", "", value)
    if len(digits) != 8:
        return False
    day, month, year = digits[:2], digits[2:4], digits[4:]
    month_names = (
        "januari|februari|maret|april|mei|juni|juli|agustus|september|"
        "oktober|november|desember|january|february|march|may|june|july|"
        "august|october|december"
    )
    if year not in (raw_text or ""):
        return False
    if re.search(rf"\b{int(day)}[/-]{int(month)}[/-]{year}\b", raw_text or ""):
        return True
    return bool(
        re.search(
            rf"\b{int(day)}\s+(?:{month_names})\s+{year}\b",
            raw_text or "",
            re.IGNORECASE,
        )
    )


def _number_seen(raw_text: str, value: str) -> bool:
    compact_value = _compact(value)
    return bool(compact_value and compact_value in _compact(raw_text))


def _level_evidence(raw_text: str) -> set[str]:
    evidence: set[str] = set()
    for level, patterns in _LEVEL_PATTERNS.items():
        if any(re.search(pattern, raw_text or "", re.IGNORECASE) for pattern in patterns):
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
        if not (value or "").strip():
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
        if len(evidence) != 1 or level not in evidence:
            add("tingkat", "ambiguous_level_evidence")

    return annotations


def apply_review_policy(
    raw_text: str,
    fields: dict[str, str],
    *,
    confidence: float = 0.90,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    annotations = build_review_annotations(raw_text, fields, confidence=confidence)
    return dict(fields), annotations
