"""Legacy combined extractor orchestrators (v2, v3, v4, v4.1).

Archived in tests/ to keep backend production code lean while maintaining
backward compatibility for regression tests and historical benchmarks.
"""
import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


from app.services.activity_extractor import extract_activity
from app.services.combined_extractor import (
    extract_activity_v6,
    extract_activity_v7,
    extract_dates_v2,
    normalize_nomor_v3,
    normalize_nomor_v4,
    normalize_organizer_v6,
    normalize_organizer_v7,
    route_with_disambiguation,
)
from app.services.field_extractor import ExtractedValue
from app.services.organizer_normalize import normalize_nomor, normalize_organizer
from app.services.organizer_v2 import extract_organizer_v2
from app.services.tingkat_router import route_tingkat_trace


def apply_combined_v2(
    extracted: dict[str, ExtractedValue],
    raw_text: str,
) -> dict[str, ExtractedValue]:
    """Terapkan staging bundle Combined v2 pada dictionary extracted fields."""
    result = dict(extracted)

    new_act = extract_activity(raw_text)
    if new_act:
        result["nama_kegiatan_sertifikasi"] = ExtractedValue(new_act, 0.88, "activity_v5")

    v2_org = extract_organizer_v2(raw_text)
    norm_org = normalize_organizer(v2_org, raw_text)
    if norm_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(norm_org, 0.85, "organizer_v4")
    elif v2_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(v2_org, 0.84, "organizer_v2")

    norm_nomor = normalize_nomor(raw_text)
    if norm_nomor:
        result["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(norm_nomor, 0.95, "nomor_v2")

    active_org = (
        result.get("penyelenggara_kegiatan").value
        if result.get("penyelenggara_kegiatan")
        else ""
    ) or ""
    tingkat, rule = route_tingkat_trace(raw_text, active_org)
    if tingkat:
        result["tingkat"] = ExtractedValue(tingkat, 0.95, f"router:{rule}")

    return result


def apply_combined_v3(
    extracted: dict[str, ExtractedValue],
    raw_text: str,
) -> dict[str, ExtractedValue]:
    """Terapkan staging bundle Combined v3 (EXP-E2E-V3: 85.7% exact, 0 LLM)."""
    result = dict(extracted)

    # 1. Activity v6 (AKT-006)
    new_act = extract_activity_v6(raw_text)
    if new_act:
        result["nama_kegiatan_sertifikasi"] = ExtractedValue(new_act, 0.92, "activity_v6")

    # 2. Organizer v6 (ORG-006)
    v2_org = extract_organizer_v2(raw_text)
    norm_org = normalize_organizer_v6(v2_org, raw_text)
    if norm_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(norm_org, 0.90, "organizer_v6")
    elif v2_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(v2_org, 0.84, "organizer_v2")

    # 3. Nomor v3 (NUM-003)
    norm_nomor = normalize_nomor_v3(raw_text)
    if norm_nomor:
        result["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(norm_nomor, 0.95, "nomor_v3")

    # 4. Dates v2 (DATE-001)
    d_s, d_e, d_conf = extract_dates_v2(raw_text)
    if d_s and d_e:
        result["waktu_mulai_pelaksanaan"] = ExtractedValue(d_s, d_conf, "date_v2")
        result["waktu_selesai_pelaksanaan"] = ExtractedValue(d_e, d_conf, "date_v2")

    # 5. Tingkat Disambiguation Router (ROUTER-006)
    active_org = (
        result.get("penyelenggara_kegiatan").value
        if result.get("penyelenggara_kegiatan")
        else ""
    ) or ""
    active_act = (
        result.get("nama_kegiatan_sertifikasi").value
        if result.get("nama_kegiatan_sertifikasi")
        else ""
    ) or ""

    tingkat, rule = route_with_disambiguation(raw_text, active_org, active_act)
    if tingkat:
        result["tingkat"] = ExtractedValue(tingkat, 0.98, f"router:{rule}")

    return result


def apply_combined_v4(
    extracted: dict[str, ExtractedValue],
    raw_text: str,
) -> dict[str, ExtractedValue]:
    """Terapkan staging bundle Combined v4 (EXP-V4-001: Robust Acronym & Metrology, 0 LLM)."""
    result = dict(extracted)

    # 1. Activity v6 (AKT-006)
    new_act = extract_activity_v6(raw_text)
    if new_act:
        result["nama_kegiatan_sertifikasi"] = ExtractedValue(new_act, 0.92, "activity_v6")

    # 2. Organizer v7 (ORG-007)
    v2_org = extract_organizer_v2(raw_text)
    norm_org = normalize_organizer_v7(v2_org, raw_text)
    if norm_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(norm_org, 0.90, "organizer_v7")
    elif v2_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(v2_org, 0.84, "organizer_v2")

    # 3. Nomor v3 (NUM-003)
    norm_nomor = normalize_nomor_v3(raw_text)
    if norm_nomor:
        result["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(norm_nomor, 0.95, "nomor_v3")

    # 4. Dates v2 (DATE-001)
    d_s, d_e, d_conf = extract_dates_v2(raw_text)
    if d_s and d_e:
        result["waktu_mulai_pelaksanaan"] = ExtractedValue(d_s, d_conf, "date_v2")
        result["waktu_selesai_pelaksanaan"] = ExtractedValue(d_e, d_conf, "date_v2")

    # 5. Tingkat Disambiguation Router (ROUTER-006)
    active_org = (
        result.get("penyelenggara_kegiatan").value
        if result.get("penyelenggara_kegiatan")
        else ""
    ) or ""
    active_act = (
        result.get("nama_kegiatan_sertifikasi").value
        if result.get("nama_kegiatan_sertifikasi")
        else ""
    ) or ""

    tingkat, rule = route_with_disambiguation(raw_text, active_org, active_act)
    if tingkat:
        result["tingkat"] = ExtractedValue(tingkat, 0.98, f"router:{rule}")

    return result


def apply_combined_v4_1(
    extracted: dict[str, ExtractedValue],
    raw_text: str,
) -> dict[str, ExtractedValue]:
    """Terapkan staging bundle Combined v4.1 (EXP-V4-002: Minor Staging Refinement, 0 LLM)."""
    result = dict(extracted)

    # 1. Activity v7 (AKT-007)
    new_act = extract_activity_v7(raw_text)
    if new_act:
        result["nama_kegiatan_sertifikasi"] = ExtractedValue(new_act, 0.94, "activity_v7")

    # 2. Organizer v7 (ORG-007)
    v2_org = extract_organizer_v2(raw_text)
    norm_org = normalize_organizer_v7(v2_org, raw_text)
    if norm_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(norm_org, 0.90, "organizer_v7")
    elif v2_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(v2_org, 0.84, "organizer_v2")

    # 3. Nomor v4 (NUM-004)
    norm_nomor = normalize_nomor_v4(raw_text)
    if norm_nomor:
        result["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(norm_nomor, 0.95, "nomor_v4")

    # 4. Dates v2 (DATE-001)
    d_s, d_e, d_conf = extract_dates_v2(raw_text)
    if d_s and d_e:
        result["waktu_mulai_pelaksanaan"] = ExtractedValue(d_s, d_conf, "date_v2")
        result["waktu_selesai_pelaksanaan"] = ExtractedValue(d_e, d_conf, "date_v2")

    # 5. Tingkat Disambiguation Router v7 (ROUTER-007)
    active_org = (
        result.get("penyelenggara_kegiatan").value
        if result.get("penyelenggara_kegiatan")
        else ""
    ) or ""
    active_act = (
        result.get("nama_kegiatan_sertifikasi").value
        if result.get("nama_kegiatan_sertifikasi")
        else ""
    ) or ""

    tingkat, rule = route_with_disambiguation(raw_text, active_org, active_act)
    if not tingkat:
        u = raw_text.upper()
        if (
            ("DIREKTUR KEMAHASISWAAN" in u or "DIREKTURKEMAHASISWAAN" in u)
            and ("UNIVERSITAS AIRLANGGA" in u or "UNIVERSITASAIRLANGGA" in u or "UNAIR" in u)
        ):
            tingkat, rule = "Universitas", "direktur_kemahasiswaan_unair"

    if tingkat:
        result["tingkat"] = ExtractedValue(tingkat, 0.98, f"router:{rule}")

    return result
