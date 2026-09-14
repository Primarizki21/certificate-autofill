"""Conservative structural title boundary for production Gemini output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.services.activity_extractor import extract_activity


@dataclass(frozen=True)
class TitleBoundaryResult:
    value: str
    candidate: str | None
    anchor: str | None
    boundary: str | None
    confidence: float
    changed: bool
    reason: str


@dataclass(frozen=True)
class _Candidate:
    value: str
    anchor: str
    boundary: str
    confidence: float


_STRUCTURE_REPAIRS = (
    (r"dalamrangkaian", "dalam rangkaian"),
    (r"dalamrangka", "dalam rangka"),
    (r"dalamacara", "dalam acara"),
    (r"dalamkegiatan", "dalam kegiatan"),
    (r"padakegiatan", "pada kegiatan"),
    (r"padaajang", "pada ajang"),
    (r"padaperlombaan", "pada perlombaan"),
    (r"yangdiselenggarakan", "yang diselenggarakan"),
    (r"yangdiadakan", "yang diadakan"),
    (r"yangdilaksanakan", "yang dilaksanakan"),
    (r"diselenggarakanoleh", "diselenggarakan oleh"),
    (r"diadakanoleh", "diadakan oleh"),
    (r"dilaksanakanoleh", "dilaksanakan oleh"),
    (r"dengantema", "dengan tema"),
    (r"subacara", "sub acara"),
)
_STOP = (
    r"\s+(?:dengan\s+tema|with\s+theme|themed|yang\s+(?:diselenggarakan|"
    r"diadakan|dilaksanakan)|bidang|sub\s+acara|"
    r"pada\s+perlombaan)"
)
_PATTERNS = (
    (
        "dalam_acara",
        re.compile(
            rf"\bdalam\s+(?:rangkaian\s+)?acara\s+(?P<title>.+?)(?P<stop>{_STOP}|\s*[\"“]|\n|$)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "dalam_kegiatan",
        re.compile(
            rf"\bdalam\s+kegiatan\s+(?P<title>.+?)(?P<stop>{_STOP}|\s*[\"“]|\n|$)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "pada_kegiatan",
        re.compile(
            rf"\bpada\s+kegiatan\s+(?P<title>.+?)(?P<stop>{_STOP}|\s*[\"“]|\n|$)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "pada_ajang",
        re.compile(
            rf"\bpada\s+ajang\s+(?P<title>.+?)(?P<stop>{_STOP}|\s*[\"“]|\n|$)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)


def _normalize_structure(text: str) -> str:
    normalized = text or ""
    for pattern, replacement in _STRUCTURE_REPAIRS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized)
    return normalized


def _clean_candidate(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" .,:;-\"“”")


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _candidate_from_existing_extractor(raw_text: str, direct: str) -> str:
    repaired = extract_activity(raw_text or "") or ""
    if _compact(repaired) == _compact(direct) and len(repaired) >= len(direct):
        return repaired
    return direct


def extract_title_candidates(raw_text: str) -> list[_Candidate]:
    normalized = _normalize_structure(raw_text)
    candidates: list[_Candidate] = []
    for anchor, pattern in _PATTERNS:
        for match in pattern.finditer(normalized):
            direct = _clean_candidate(match.group("title"))
            if len(direct) < 3:
                continue
            boundary_text = match.group("stop") or ""
            if re.search(r"[\"“]", boundary_text):
                boundary = "quoted_title"
            else:
                boundary = _clean_candidate(boundary_text).lower() or (
                    "line_end" if "\n" in boundary_text else "end"
                )
            value = _candidate_from_existing_extractor(raw_text, direct)
            candidates.append(
                _Candidate(
                    value=value,
                    anchor=anchor,
                    boundary=boundary,
                    confidence=0.92 if boundary not in {"end", "line_end"} else 0.86,
                )
            )
    unique: dict[tuple[str, str, str], _Candidate] = {}
    for candidate in candidates:
        unique.setdefault(
            (_compact(candidate.value), candidate.anchor, candidate.boundary), candidate
        )
    return list(unique.values())


def _best_candidate(current: str, candidates: Iterable[_Candidate]) -> _Candidate | None:
    current_compact = _compact(current)
    if not current_compact:
        return None
    ranked: list[tuple[int, int, _Candidate]] = []
    for candidate in candidates:
        candidate_compact = _compact(candidate.value)
        if not candidate_compact or candidate_compact == current_compact:
            continue
        is_prefix_trim = (
            candidate.boundary not in {"end", "line_end"}
            and current_compact.startswith(candidate_compact)
        )
        is_main_event = candidate.boundary in {
            "pada perlombaan",
            "sub acara",
            "sub-acara",
        }
        if is_prefix_trim:
            ranked.append((3, len(candidate_compact), candidate))
        elif is_main_event:
            ranked.append((2, len(candidate_compact), candidate))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def apply_title_boundary(raw_text: str, current: str | None) -> TitleBoundaryResult:
    current_value = (current or "").strip()
    candidate = _best_candidate(current_value, extract_title_candidates(raw_text))
    if candidate is None:
        return TitleBoundaryResult(
            value=current_value,
            candidate=None,
            anchor=None,
            boundary=None,
            confidence=0.90 if current_value else 0.0,
            changed=False,
            reason="no_safe_structural_boundary",
        )
    return TitleBoundaryResult(
        value=candidate.value,
        candidate=candidate.value,
        anchor=candidate.anchor,
        boundary=candidate.boundary,
        confidence=candidate.confidence,
        changed=candidate.value != current_value,
        reason="explicit_structural_boundary",
    )
