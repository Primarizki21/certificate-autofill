"""Compatibility shim re-exporting production title boundary."""

from app.services.title_boundary import (
    TitleBoundaryResult,
    _Candidate,
    apply_title_boundary,
    extract_title_candidates,
    _best_candidate,
    _clean_candidate,
    _compact,
    _candidate_from_existing_extractor,
    _normalize_structure,
)

__all__ = [
    "TitleBoundaryResult",
    "_Candidate",
    "apply_title_boundary",
    "extract_title_candidates",
    "_best_candidate",
    "_clean_candidate",
    "_compact",
    "_candidate_from_existing_extractor",
    "_normalize_structure",
]
