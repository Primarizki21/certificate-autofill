from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.master_data import KHP_MASTER_OPTIONS
from app.services.aucc_catalog import Kegiatan2LookupRow
from app.services.field_extractor import ExtractedValue

ACTIVITY_FIELD = "jenis_kegiatan"
GROUP_FIELD = "kelompok_kegiatan"
LEVEL_FIELD = "tingkat"
ROLE_FIELD = "prestasi_partisipasi_jabatan"


def _fold(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


def _is_unset(value: str | None) -> bool:
    return _fold(value) in {"", "--", "pilih", "pilih kelompok kegiatan"}


def _field_value(fields: Mapping[str, Any], field_name: str) -> str | None:
    value = fields.get(field_name)
    if isinstance(value, ExtractedValue):
        return value.value
    if value is None:
        return None
    return str(value)


def _options(key: str) -> tuple[dict[str, object], ...]:
    return tuple(KHP_MASTER_OPTIONS[key])


def _match_label(key: str, value: str | None) -> "KHPFieldMatch | None":
    if _is_unset(value):
        return None
    value_text = str(value).strip()
    exact_matches = [
        option for option in _options(key) if str(option["label"]).strip() == value_text
    ]
    if len(exact_matches) == 1:
        option = exact_matches[0]
        return KHPFieldMatch(
            id=int(option["id"]),
            label=str(option["label"]),
            status="matched",
        )
    folded = _fold(value_text)
    folded_matches = [
        option for option in _options(key) if _fold(str(option["label"])) == folded
    ]
    if len(folded_matches) == 1:
        option = folded_matches[0]
        return KHPFieldMatch(
            id=int(option["id"]),
            label=str(option["label"]),
            status="matched",
        )
    if len(folded_matches) > 1:
        return KHPFieldMatch(
            id=None,
            label=None,
            status="ambiguous",
            reasons=("ambiguous_master_label",),
        )
    return None


def _match_patterns(
    key: str,
    text: str,
    patterns: Iterable[tuple[int, tuple[str, ...]]],
) -> "KHPFieldMatch | None":
    folded = _fold(text)
    matched_ids = [
        option_id
        for option_id, option_patterns in patterns
        if any(re.search(pattern, folded) for pattern in option_patterns)
    ]
    unique_ids = tuple(dict.fromkeys(matched_ids))
    if len(unique_ids) != 1:
        if not unique_ids:
            return None
        return KHPFieldMatch(
            id=None,
            label=None,
            status="ambiguous",
            reasons=("ambiguous_structural_anchor",),
        )
    option_id = unique_ids[0]
    option = next(item for item in _options(key) if int(item["id"]) == option_id)
    return KHPFieldMatch(
        id=option_id,
        label=str(option["label"]),
        status="matched",
        reasons=("structural_anchor_match",),
    )


@dataclass(frozen=True)
class KHPFieldMatch:
    id: int | None
    label: str | None
    status: str
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "reasons": list(self.reasons),
        }



@dataclass(frozen=True)
class KHPMasterResolution:
    fields: dict[str, KHPFieldMatch]
    status: str
    id_kegiatan_2: int | None
    lookup_status: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "fields": {
                field_name: field_match.as_dict()
                for field_name, field_match in self.fields.items()
            },
            "status": self.status,
            "id_kegiatan_2": self.id_kegiatan_2,
            "lookup_status": self.lookup_status,
            "reasons": list(self.reasons),
        }


_ACTIVITY_PATTERNS = (
    (41, (r"\bpkkmb\b", r"pengenalan kehidupan kampus")),
    (42, (r"\bkkn\s*bbm\b", r"kuliah kerja nyata")),
    (72, (r"mencalonkan diri", r"calon ketua", r"calon anggota organisasi")),
    (73, (r"\bpemira\b", r"pemilihan raya mahasiswa")),
    (129, (r"sertifikasi", r"sertifikat kompetensi", r"certification")),
    (117, (r"\bkim\b", r"kompetisi ilmiah mahasiswa")),
    (121, (r"\bpkl\b", r"praktik kerja lapangan")),
    (127, (r"magang ukm", r"internship ukm")),
    (114, (r"magang penelitian", r"research internship")),
    (113, (r"magang kerja", r"work internship")),
    (91, (r"kuliah tamu", r"guest lecture")),
    (85, (r"dipatenkan", r"paten", r"patent")),
    (86, (r"dipublikasikan", r"publikasi ilmiah", r"jurnal ilmiah", r"majalah ilmiah")),
    (87, (r"surat kabar", r"media populer", r"karya populer")),
    (88, (r"didanai", r"pendanaan pemerintah", r"funded by")),
    (89, (r"bimbingan.*karya tulis", r"pelatihan.*karya tulis")),
    (90, (r"tidak dipublikasikan", r"unpublished")),
    (93, (r"mawapres", r"mahasiswa berprestasi")),
    (74, (r"business plan", r"interpreneurship", r"pemikiran kritis", r"kreativitas")),
    (83, (r"lomba ilmiah", r"olimpiade ilmiah", r"scientific competition")),
    (84, (r"seminar", r"lokakarya", r"workshop", r"forum ilmiah")),
    (100, (r"pelatih", r"pembimbing kegiatan minat dan bakat")),
    (101, (r"latihan gabungan", r"joint training")),
    (102, (r"aktivitas rutin.*ukm", r"kegiatan rutin.*ukm")),
    (103, (r"mitra tanding", r"sparring partner")),
    (104, (r"karya seni", r"konser", r"fotografi", r"teater", r"pameran seni")),
    (105, (r"kewirausahaan", r"entrepreneurship")),
    (98, (r"prestasi.*minat dan bakat", r"juara.*olahraga", r"juara.*seni")),
    (99, (r"minat dan bakat", r"kegiatan olahraga", r"kegiatan kerohanian")),
    (106, (r"bakti sosial", r"social service")),
    (107, (r"penanganan bencana", r"tanggap bencana", r"disaster response")),
    (108, (r"\blbb\b", r"pengajian", r"\btpa\b", r"\bpaud\b")),
    (109, (r"individual sosial", r"individual social")),
    (110, (r"upacara bendera", r"flag ceremony")),
    (111, (r"kegiatan alumni", r"alumni activity")),
    (112, (r"studi banding", r"kunjungan", r"benchmark visit")),
    (115, (r"\besq\b",)),
    (116, (r"jati diri",)),
    (67, (r"pengurus organisasi", r"pengurus inti")),
    (68, (r"anggota aktif organisasi",)),
    (69, (r"\blkmm\b", r"pelatihan kepemimpinan")),
    (70, (r"latihan kepemimpinan",)),
    (71, (r"panitia", r"organizing committee")),
)

_ROLE_PATTERNS = (
    (27, (r"juara harapan iii", r"harapan iii")),
    (25, (r"juara harapan i\b", r"harapan i\b")),
    (26, (r"juara harapan ii", r"harapan ii")),
    (7, (r"juara i\b", r"juara 1\b", r"first winner")),
    (8, (r"juara ii\b", r"juara 2\b", r"second winner")),
    (9, (r"juara iii\b", r"juara 3\b", r"third winner")),
    (29, (r"\bbest\b", r"terbaik")),
    (10, (r"finalis", r"finalist")),
    (11, (r"peserta terpilih", r"selected participant")),
    (12, (r"pembicara", r"speaker", r"narasumber")),
    (13, (r"moderator",)),
    (15, (r"delegasi", r"delegate")),
    (16, (r"peserta undangan", r"invited participant")),
    (17, (r"peserta biasa", r"regular participant")),
    (18, (r"fasilitator", r"facilitator")),
    (34, (r"lsp una ir", r"lsp unair")),
    (35, (r"fakultas.?prodi", r"faculty.?program study")),
    (30, (r"kompetensi", r"competency")),
    (32, (r"\bbnsp\b",)),
    (33, (r"brevet",)),
    (20, (r"kemitraan", r"partnership")),
    (19, (r"mandiri", r"independent")),
    (21, (r"panitia", r"committee")),
    (2, (r"wakil ketua", r"vice chair")),
    (1, (r"\bketua\b", r"chair")),
    (3, (r"sekretaris", r"secretary")),
    (4, (r"menteri", r"koordinator", r"kepala bidang", r"pengurus inti lain")),
    (5, (r"anggota pengurus", r"board member")),
    (14, (r"\banggota\b", r"member")),
    (6, (r"\bpeserta\b", r"participant", r"partisipan")),
)

_LEVEL_PATTERNS = (
    (8, (r"nasional\s+ter[\s-]?\s*akreditasi", r"accredited national")),
    (
        9,
        (
            r"nasional\s+tidak\s+ter[\s-]?\s*akreditasi",
            r"national\s+not[\s-]?\s*accredited",
            r"non[\s-]?\s*accredited national",
        ),
    ),
    (1, (r"tingkat internasional", r"skala internasional", r"international level")),
    (3, (r"tingkat regional", r"skala regional", r"regional level")),
    (6, (r"departemen", r"program studi", r"prodi", r"department", r"study program")),
    (5, (r"tingkat fakultas", r"skala fakultas", r"faculty level")),
    (4, (r"tingkat universitas", r"skala universitas", r"university level")),
    (7, (r"unit kegiatan mahasiswa", r"\bukm\b", r"student activity unit")),
    (2, (r"tingkat nasional", r"skala nasional", r"national level")),
    (10, (r"tingkat lanjut", r"advanced level")),
    (11, (r"tingkat menengah", r"intermediate level")),
    (12, (r"tingkat dasar", r"basic level")),
)


def _unresolved(reason: str) -> KHPFieldMatch:
    return KHPFieldMatch(id=None, label=None, status="unresolved", reasons=(reason,))


def _unspecified(reason: str) -> KHPFieldMatch:
    return KHPFieldMatch(id=None, label=None, status="unspecified", reasons=(reason,))


def _resolve_activity(raw_text: str, mapped_fields: Mapping[str, Any]) -> KHPFieldMatch:
    mapped_value = _field_value(mapped_fields, ACTIVITY_FIELD)
    mapped = _match_label(ACTIVITY_FIELD, mapped_value)
    if mapped is not None:
        return mapped
    if _fold(mapped_value) == "peserta pkkmb":
        return _match_label(ACTIVITY_FIELD, "PKKMB") or _unresolved("activity_not_in_master")
    text = raw_text
    role = _field_value(mapped_fields, "raw_role") or ""
    if re.search(r"panitia|organizing committee", _fold(role)):
        text = f"{text} {role}"
    match = _match_patterns(ACTIVITY_FIELD, text, _ACTIVITY_PATTERNS)
    return match or _unresolved("activity_not_in_master")


def _resolve_level(raw_text: str, mapped_fields: Mapping[str, Any]) -> KHPFieldMatch:
    match = _match_patterns(LEVEL_FIELD, raw_text, _LEVEL_PATTERNS)
    if match is not None:
        return match
    mapped = _match_label(LEVEL_FIELD, _field_value(mapped_fields, LEVEL_FIELD))
    return mapped or _unspecified("level_not_provided")


def _resolve_role(raw_text: str, mapped_fields: Mapping[str, Any]) -> KHPFieldMatch:
    role_value = _field_value(mapped_fields, "raw_role")
    mapped_value = _field_value(mapped_fields, ROLE_FIELD)
    direct = _match_label(ROLE_FIELD, role_value) or _match_label(ROLE_FIELD, mapped_value)
    if direct is not None:
        return direct
    role_text = role_value or ""
    mapped_text = mapped_value or ""
    text = f"{role_text} {mapped_text} {raw_text}"
    match = _match_patterns(ROLE_FIELD, text, _ROLE_PATTERNS)
    return match or _unspecified("role_not_provided")


def _group_match(activity: KHPFieldMatch) -> KHPFieldMatch:
    if activity.id is None:
        return _unresolved("group_blocked_by_activity")
    activity_option = next(
        item for item in _options(ACTIVITY_FIELD) if int(item["id"]) == activity.id
    )
    group_id = activity_option.get("group_id")
    if group_id is None:
        return _unresolved("group_missing_for_activity")
    group_option = next(
        item
        for item in _options(GROUP_FIELD)
        if int(item["id"]) == int(group_id)
    )
    return KHPFieldMatch(
        id=int(group_option["id"]),
        label=str(group_option["label"]),
        status="matched",
        reasons=("activity_group_lookup",),
    )


def lookup_kegiatan_2(
    rows: Iterable[Kegiatan2LookupRow] | None,
    *,
    id_kegiatan_1: int,
    id_tingkat: int | None,
    id_jabatan_prestasi: int | None,
) -> tuple[int | None, str]:
    if rows is None:
        return None, "not_loaded"
    matches = [
        row.id_kegiatan_2
        for row in rows
        if row.id_kegiatan_1 == id_kegiatan_1
        and row.id_tingkat == id_tingkat
        and row.id_jabatan_prestasi == id_jabatan_prestasi
    ]
    if len(matches) == 1:
        return matches[0], "matched"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "not_found"


def resolve_khp_master_fields(
    raw_text: str,
    mapped_fields: Mapping[str, Any],
    kegiatan2_rows: Iterable[Kegiatan2LookupRow] | None = None,
) -> KHPMasterResolution:
    activity = _resolve_activity(raw_text, mapped_fields)
    level = _resolve_level(raw_text, mapped_fields)
    role = _resolve_role(raw_text, mapped_fields)
    group = _group_match(activity)
    fields = {
        ACTIVITY_FIELD: activity,
        GROUP_FIELD: group,
        LEVEL_FIELD: level,
        ROLE_FIELD: role,
    }
    field_reasons = [
        f"{field_name}_{reason}"
        for field_name, field_match in fields.items()
        if field_match.status in {"unresolved", "ambiguous"}
        for reason in field_match.reasons
    ]
    reasons = list(field_reasons)
    id_kegiatan_2 = None
    lookup_status = "blocked_by_missing_field"
    lookup_fields = (activity, level, role)
    if activity.id is not None and all(
        match.status in {"matched", "unspecified"} for match in lookup_fields
    ):
        id_kegiatan_2, lookup_status = lookup_kegiatan_2(
            kegiatan2_rows,
            id_kegiatan_1=activity.id,
            id_tingkat=level.id,
            id_jabatan_prestasi=role.id,
        )
        if lookup_status != "matched":
            reasons.append(f"kegiatan_2_{lookup_status}")
    if field_reasons:
        status = "needs_review"
    elif id_kegiatan_2 is not None and lookup_status == "matched":
        status = "resolved"
    elif lookup_status == "not_loaded":
        status = "awaiting_kegiatan_2_lookup"
    else:
        status = "needs_review"
    return KHPMasterResolution(
        fields=fields,
        status=status,
        id_kegiatan_2=id_kegiatan_2,
        lookup_status=lookup_status,
        reasons=tuple(reasons),
    )


def apply_khp_master_mapping(
    mapped_fields: Mapping[str, ExtractedValue],
    resolution: KHPMasterResolution,
) -> dict[str, ExtractedValue]:
    updated = dict(mapped_fields)
    for field_name in (ACTIVITY_FIELD, GROUP_FIELD, LEVEL_FIELD, ROLE_FIELD):
        match = resolution.fields[field_name]
        if match.status == "matched":
            updated[field_name] = ExtractedValue(
                match.label,
                max(0.90, updated.get(field_name, ExtractedValue(None, 0.0, "")).confidence),
                "khp_master_staging",
            )
        else:
            updated[field_name] = ExtractedValue(None, 0.0, "khp_master_staging")
    return updated
