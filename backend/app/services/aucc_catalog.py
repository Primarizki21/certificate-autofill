from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Kegiatan2LookupRow:
    id_kegiatan_2: int
    id_kegiatan_1: int
    id_tingkat: int | None
    id_jabatan_prestasi: int | None


@dataclass(frozen=True, slots=True)
class MasterKegiatanRule:
    source_no: int
    id_kelompok_kegiatan: int
    id_kegiatan_1: int
    id_tingkat: int | None
    id_jabatan_prestasi: int | None
    dasar_penilaian: str
    id_kegiatan_2: int
    is_active: bool = True
