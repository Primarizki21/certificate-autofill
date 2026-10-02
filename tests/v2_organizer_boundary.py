"""Compatibility shim re-exporting production organizer boundary."""

from app.services.organizer_boundary import (
    OrganizerBoundaryResult,
    apply_organizer_boundary,
    _clean,
    _compact,
    _looks_broad_institution,
    _looks_office,
    _line_before,
    _issuer_candidate,
    _pre_certificate_organization,
)

__all__ = [
    "OrganizerBoundaryResult",
    "apply_organizer_boundary",
    "_clean",
    "_compact",
    "_looks_broad_institution",
    "_looks_office",
    "_line_before",
    "_issuer_candidate",
    "_pre_certificate_organization",
]
