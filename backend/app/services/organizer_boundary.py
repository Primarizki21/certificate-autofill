"""Conservative structural organizer boundary for production Gemini output."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OrganizerBoundaryResult:
    value: str
    candidate: str | None
    boundary: str | None
    confidence: float
    changed: bool
    reason: str


_PARTNER_RE = re.compile(
    r"\s+(?:in\s+collaboration\s+with|in\s+cooperation\s+with|"
    r"collaborating\s+with|berkolaborasi\s+dengan|bekerja\s+sama\s+dengan)\b.*$",
    re.IGNORECASE | re.DOTALL,
)
_PRIMARY_RE = re.compile(
    r"(?:diselenggarakan|diadakan|dilaksanakan)\s+oleh|"
    r"(?:(?:proudly\s+)?presented|organized|organised|held|hosted)\s+by",
    re.IGNORECASE,
)
_COORGANIZER_RE = re.compile(
    r"\b[\w.-]+\s+[x×&]\s+[\w.-]+\b",
    re.IGNORECASE,
)
_ISSUER_RE = re.compile(
    r"dengan\s*ini\s*memberikan|"
    r"hereby\s*(?:gives|awards|presents)|"
    r"(?:is\s+)?hereby\s+(?:awarded|presented)\s+to|"
    r"(?:is\s+)?proudly\s+presented\s+to|"
    r"this\s+certificate\s+is\s+(?:proudly\s+)?presented\s+to|"
    r"this\s+is\s+to\s+certify\s+that",
    re.IGNORECASE,
)
_CERTIFICATE_RE = re.compile(
    r"(?:sertifikat|certificate|piagam|penghargaan|certification)", re.IGNORECASE
)
_ORGANIZATION_LINE_RE = re.compile(
    r"^(?:UKM|BEM|HIMA|DPM|MPM|BSO|Himpunan|Badan\s+Eksekutif|Badan\s+Semi\s+Otonom|"
    r"Student\s+Association|Student\s+Executive|Student\s+Council|Student\s+Chapter|"
    r"Student\s+Club|Student\s+Society|Society|Chapter|Club|Council|Committee)\b.*$",
    re.IGNORECASE,
)
_BROAD_INSTITUTION_TERMS = (
    "universitas",
    "university",
    "institut",
    "institute",
    "politeknik",
    "fakultas",
    "faculty",
    "direktorat",
)
_OFFICE_TERMS = (
    "direktorat",
    "direktur",
    "kemahasiswaan",
    "student affairs",
    "student services",
    "office",
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" .,:;-\"“”")


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _looks_broad_institution(value: str) -> bool:
    lowered = (value or "").lower()
    return any(term in lowered for term in _BROAD_INSTITUTION_TERMS)


def _looks_office(value: str) -> bool:
    lowered = (value or "").lower()
    return any(term in lowered for term in _OFFICE_TERMS)


def _line_before(text: str, offset: int) -> str:
    prefix = text[:offset]
    return next((line.strip() for line in reversed(prefix.splitlines()) if line.strip()), "")


def _issuer_candidate(raw_text: str, current: str) -> str | None:
    current_tokens = current.split()
    for match in _ISSUER_RE.finditer(raw_text or ""):
        line = _line_before(raw_text, match.start())
        if not line:
            continue
        line_compact = _compact(line)
        if not line_compact:
            continue
        for index in range(len(current_tokens)):
            suffix = _clean(" ".join(current_tokens[index:]))
            if _compact(suffix) == line_compact:
                return suffix
    return None


def _pre_certificate_organization(raw_text: str, current: str) -> str | None:
    first_certificate = _CERTIFICATE_RE.search(raw_text or "")
    head = (raw_text or "")[: first_certificate.start() if first_certificate else 600]
    lines = [_clean(line) for line in head.splitlines() if _clean(line)]
    candidates = [line for line in lines if _ORGANIZATION_LINE_RE.fullmatch(line)]
    if not candidates or not _looks_broad_institution(current):
        return None
    body_compact = _compact(raw_text)
    for candidate in reversed(candidates):
        candidate_words = candidate.split()
        candidate_compact = _compact(candidate)
        if candidate_compact in {"bem", "hima", "ukm", "dpm", "mpm", "himpunanmahasiswa"}:
            continue
        if len(candidate_words) < 2:
            continue
        if candidate_compact and body_compact.count(candidate_compact) >= 2:
            return candidate
    return None


def apply_organizer_boundary(raw_text: str, current: str | None) -> OrganizerBoundaryResult:
    current_value = _clean(current or "")
    partner_match = _PARTNER_RE.search(current_value)
    if (
        partner_match
        and _PRIMARY_RE.search(raw_text or "")
        and not _COORGANIZER_RE.search(raw_text or "")
    ):
        candidate = _clean(current_value[: partner_match.start()])
        if candidate and candidate != current_value:
            return OrganizerBoundaryResult(
                value=candidate,
                candidate=candidate,
                boundary=partner_match.group(0).strip().lower(),
                confidence=0.96,
                changed=True,
                reason="primary_organizer_before_partner_connector",
            )

    student_organization = _pre_certificate_organization(raw_text, current_value)
    if student_organization and student_organization != current_value:
        return OrganizerBoundaryResult(
            value=student_organization,
            candidate=student_organization,
            boundary="organization_before_certificate_header",
            confidence=0.88,
            changed=True,
            reason="organization_header_over_broad_institution",
        )

    issuer = _issuer_candidate(raw_text, current_value)
    if issuer and _looks_office(current_value) and issuer != current_value:
        return OrganizerBoundaryResult(
            value=issuer,
            candidate=issuer,
            boundary="issuer_before_award_phrase",
            confidence=0.94,
            changed=True,
            reason="issuer_organizer_over_signer_office",
        )

    return OrganizerBoundaryResult(
        value=current_value,
        candidate=None,
        boundary=None,
        confidence=0.90 if current_value else 0.0,
        changed=False,
        reason="no_safe_organizer_boundary",
    )
