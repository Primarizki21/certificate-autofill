from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.aucc_models import KRP_KHP
from app.services.field_extractor import ExtractedValue

_PIPELINE_OWNED_FIELDS = (
    "id_kegiatan_2",
    "penyelenggara_krp_khp",
    "nm_krp_khp",
    "waktu_krp_khp",
    "waktu_krp_khp_selesai",
    "jenis_penyelenggara",
    "no_bukti_fisik",
)


def _value(fields: Mapping[str, Any], field_name: str) -> str | None:
    value = fields.get(field_name)
    if isinstance(value, ExtractedValue):
        return value.value
    if value is None:
        return None
    return str(value)


def _date_value(fields: Mapping[str, Any], field_name: str) -> date | None:
    value = _value(fields, field_name)
    if not value:
        return None
    value = value.strip()
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def _kegiatan_2_id(resolution: Mapping[str, Any] | None) -> int | None:
    if not resolution:
        return None
    value = resolution.get("id_kegiatan_2")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_krp_khp_values(
    document_id: str,
    mapped_fields: Mapping[str, Any],
    master_resolution: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "id_semester": None,
        "id_kegiatan_2": _kegiatan_2_id(master_resolution),
        "id_bukti_fisik": None,
        "id_mhs": None,
        "penyelenggara_krp_khp": _value(mapped_fields, "penyelenggara_kegiatan"),
        "nm_krp_khp": _value(mapped_fields, "nama_kegiatan_sertifikasi"),
        "skor_krp_khp": None,
        "waktu_krp_khp": _date_value(mapped_fields, "waktu_mulai_pelaksanaan"),
        "id_pengguna": None,
        "is_ajukan_reward": False,
        "waktu_krp_khp_selesai": _date_value(
            mapped_fields, "waktu_selesai_pelaksanaan"
        ),
        "jenis_penyelenggara": _value(mapped_fields, "jenis_penyelenggara"),
        "pembimbing_nidn": None,
        "pembimbing_nama": None,
        "url_publikasi": None,
        "no_bukti_fisik": _value(
            mapped_fields, "nomor_bukti_fisik_nomor_sertifikasi"
        ),
        "pembimbing_nuptk": None,
    }


def upsert_krp_khp(
    db: Session,
    document_id: str,
    mapped_fields: Mapping[str, Any],
    master_resolution: Mapping[str, Any] | None,
) -> str:
    values = build_krp_khp_values(document_id, mapped_fields, master_resolution)
    row = (
        db.query(KRP_KHP)
        .filter(KRP_KHP.document_id == document_id)
        .one_or_none()
    )
    if row is None:
        db.add(KRP_KHP(**values))
        return "created"
    for field_name in _PIPELINE_OWNED_FIELDS:
        setattr(row, field_name, values[field_name])
    return "updated"
