from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.master_data import KHP_MASTER_OPTIONS
from app.services.aucc_catalog import (
    Kegiatan2LookupRow,
    MasterKegiatanRule,
    get_default_aucc_catalog,
)
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
    master_rule: MasterKegiatanRule | None = None
    rule_status: str = "not_loaded"
    evidence_status: str = "not_checked"

    def as_dict(self) -> dict[str, object]:
        return {
            "fields": {
                field_name: field_match.as_dict()
                for field_name, field_match in self.fields.items()
            },
            "status": self.status,
            "id_kegiatan_2": self.id_kegiatan_2,
            "lookup_status": self.lookup_status,
            "master_rule": self.master_rule.as_dict() if self.master_rule else None,
            "rule_status": self.rule_status,
            "evidence_status": self.evidence_status,
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
    (67, (r"pengurus\s+organisasi", r"pengurus\s+inti", r"kepengurusan", r"pengabdian.*(?:ormawa|organisasi|himpunan|bem)", r"masa\s+bakti")),
    (68, (r"anggota aktif organisasi",)),
    (69, (r"\blkmm\b", r"pelatihan kepemimpinan")),
    (70, (r"latihan kepemimpinan",)),
    (71, (r"panitia", r"organizing committee")),
)

_ROLE_PATTERNS = (
    (27, (r"juara harapan iii", r"harapan iii")),
    (25, (r"juara harapan i\b", r"harapan i\b")),
    (26, (r"juara harapan ii", r"harapan ii")),
    (7, (r"juara i\b", r"juara 1\b", r"first winner", r"1st winner", r"1st place")),
    (8, (r"juara ii\b", r"juara 2\b", r"juara ll\b", r"second winner", r"2nd winner", r"2nd place")),
    (9, (r"juara iii\b", r"juara 3\b", r"juara lll\b", r"third winner", r"3rd winner", r"3rd place")),
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
    (
        4,
        (
            r"supervisor(?:\s+divisi)?",
            r"kepala\s+(?:divisi|bidang|seksi|departemen|biro)",
            r"ketua\s+(?:divisi|bidang|seksi|departemen|biro)",
            r"bendahara(?:\s+[12i]+|\s+umum)?",
            r"wakil\s+(?:sekretaris|bendahara)",
            r"\bbph\b",
            r"\bmenteri\b",
            r"koordinator",
            r"kepala\s+bidang",
            r"pengurus\s+inti(?:\s+lain)?",
        ),
    ),
    (
        1,
        (
            r"\bketua\s+umum\b",
            r"\bketua\s+himpunan\b",
            r"\bketua\s+hima\b",
            r"\bketua\s+bem\b",
            r"\bketua(?!\s+(?:divisi|bidang|seksi|departemen|biro|panitia))\b",
            r"chair(?!\s+(?:division|department|committee))",
        ),
    ),
    (3, (r"sekretaris", r"secretary")),
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


def _resolve_activity(
    raw_text: str,
    mapped_fields: Mapping[str, Any],
    role_match: KHPFieldMatch | None = None,
) -> KHPFieldMatch:
    if role_match is None:
        role_match = _resolve_role(raw_text, mapped_fields)

    role = _field_value(mapped_fields, "raw_role") or ""
    role_label = role_match.label or ""
    role_combined = f"{role} {role_label}".lower()
    activity_name = _field_value(mapped_fields, "nama_kegiatan_sertifikasi") or ""
    text = f"{activity_name} {raw_text}".lower()

    # 1. ATURAN EMAS PANITIA: Seluruh kepanitiaan diarahkan ke ID 71
    is_panitia = (
        role_match.id == 21
        or "panitia" in role_label.lower()
        or bool(re.search(r"\bpanitia\b|organizing committee|steering committee", role_combined))
        or bool(re.search(r"\bpanitia\b|\bsteering committee\b|\borganizing committee\b", raw_text.lower()))
    )
    if is_panitia:
        panitia_match = _match_label(ACTIVITY_FIELD, "Panitia Dalam Suatu Kegiatan Kemahasiswaan")
        if panitia_match is not None:
            return panitia_match

    mapped_value = _field_value(mapped_fields, ACTIVITY_FIELD)
    if _fold(mapped_value) == "peserta pkkmb":
        return _match_label(ACTIVITY_FIELD, "PKKMB") or _unresolved("activity_not_in_master")
    is_lomba = bool(re.search(r"lomba|kompetisi|competition|championship|contest|olympiad|olimpiade|hackathon|challenge|fest|fair|turnamen|tournament|gemastik|pimnas|kontes|pagelaran\s+mahasiswa|quest|cup|league|liga|slayer|datathon|ideathon", text))
    is_winner = bool(re.search(r"juara|winner|finalis|finalist|best|pemenang", role_combined)) or bool(re.search(r"\bjuara\b|\bwinner\b|\bfinalis\b|\bpemenang\b", raw_text.lower()))
    is_ormawa_context = bool(re.search(r"hima|bem|ormawa|organisasi\s+kemahasiswaan|himpunan|badan\s+eksekutif", text))
    is_not_team = not bool(re.search(r"\b(?:ketua|pengurus|anggota|leader)\s+tim\b|\bteam\s+(?:leader|member)\b|\btim\b|\bteam\b", role_combined))
    has_explicit_pengurus_role = bool(re.search(r"\bpengurus\b|\bbph\b|\bbidang\b|\bkoordinator\b", role_combined))

    if (is_lomba and is_winner) or is_winner or (role_match.id in (7, 8, 9, 10, 25, 26, 27, 29)):
        lomba_win = _match_label(ACTIVITY_FIELD, "Memperoleh prestasi dalam Lomba Karya Tulis Ilmiah/Lingkungan Hidup/Kreativitas/Inovatif/Pemikiran Kritis/Populer/Interpreneurship/Business Plan")
        if lomba_win is not None:
            return lomba_win
    elif is_lomba and (not is_not_team or not (is_ormawa_context and has_explicit_pengurus_role)):
        lomba_peserta = _match_label(ACTIVITY_FIELD, "Mengikuti Kegiatan Lomba Ilmiah")
        if lomba_peserta is not None:
            return lomba_peserta

    # 3. PKKMB / ORIENTASI MAHASISWA BARU (Peserta)
    is_pkkmb = bool(re.search(
        r"\bpkkmb\b|pengenalan\s+kehidupan\s+kampus|freshman\s+(?:solidarity|orientation|welcome|induction)|"
        r"orientasi\s+(?:mahasiswa|studi|kampus|akademik)|penerimaan\s+mahasiswa\s+baru|new\s+student\s+orientation",
        text,
    ))
    if is_pkkmb:
        pkkmb_match = _match_label(ACTIVITY_FIELD, "PKKMB")
        if pkkmb_match is not None:
            return pkkmb_match

    # 4. MAWAPRES
    if re.search(r"\bmawapres\b|mahasiswa berprestasi", text):
        mawapres_match = _match_label(ACTIVITY_FIELD, "MAWAPRES")
        if mawapres_match is not None:
            return mawapres_match

    # 5. KKN / BBK
    if re.search(r"\bkkn\b|\bbbk\b|belajar bersama komunitas|kuliah kerja nyata", text):
        kkn_match = _match_label(ACTIVITY_FIELD, "KKN-BBM")
        if kkn_match is not None:
            return kkn_match

    # 6. Magang UKM
    if re.search(r"\bmagang\b", text) and re.search(r"\bukm\b", text):
        magang_match = _match_label(ACTIVITY_FIELD, "Magang UKM")
        if magang_match is not None:
            return magang_match

    # 7. Bakti Sosial / Campaign Sosial / Pengabdian Masyarakat
    if re.search(r"bakti sosial|social service|social action|campaign|pengabdian masyarakat", text):
        baksos_match = _match_label(ACTIVITY_FIELD, "Mengikuti Pelaksanaan Bakti Sosial")
        if baksos_match is not None:
            return baksos_match

    # 8. Latihan Kepemimpinan / Regenerasi
    if re.search(r"lkmm|latihan\s+keterampilan\s+manajemen\s+mahasiswa|latihan\s+kepemimpinan|leadership\s+training|regenerasi|sekolah\s+bem|sekolah\s+kader", text):
        lkm_match = _match_label(ACTIVITY_FIELD, "Latihan Kepemimpinan Lainnya")
        if lkm_match is not None:
            return lkm_match

    # 9. KIM
    if re.search(r"\bkim\b|kompetisi ilmiah mahasiswa", text):
        kim_match = _match_label(ACTIVITY_FIELD, "Kompetisi Ilmiah Mahasiswa (KIM) tingkat Fakultas")
        if kim_match is not None:
            return kim_match

    # 10. Pengurus Organisasi (guarded against competition and orientation context)
    if is_not_team and not (is_lomba and not has_explicit_pengurus_role) and not is_pkkmb and (
        ("pengurus" in role_combined and not re.search(r"\btim\b|\bteam\b", role_combined))
        or any(k in text for k in ["kepengurusan", "masa bakti"])
        or (
            any(k in role_combined for k in ["ketua", "sekretaris", "bendahara", "supervisor"])
            and is_ormawa_context
        )
    ):
        pengurus_match = _match_label(ACTIVITY_FIELD, "Pengurus Organisasi")
        if pengurus_match is not None:
            return pengurus_match
    # 10. Seminar / Forum Ilmiah / Pelatihan
    if re.search(r"seminar|workshop|lokakarya|webinar|talkshow|forum|kuliah tamu|pameran|guest lecture|conference|symposium|simposium|training|pelatihan|webcast|course|bootcamp|coaching|mentoring|job preparation|career track|literasi digital", text):
        forum_match = _match_label(ACTIVITY_FIELD, "Mengikuti kegiatan/forum ilmiah (seminar, lokakarya, workshop, pameran)")
        if forum_match is not None:
            return forum_match

    match = _match_patterns(ACTIVITY_FIELD, f"{text} {role}", _ACTIVITY_PATTERNS)
    return match or _unresolved("activity_not_in_master")

def _resolve_level(raw_text: str, mapped_fields: Mapping[str, Any]) -> KHPFieldMatch:
    mapped = _match_label(LEVEL_FIELD, _field_value(mapped_fields, LEVEL_FIELD))

    organizer = _field_value(mapped_fields, "penyelenggara_kegiatan") or ""
    activity_name = _field_value(mapped_fields, "nama_kegiatan_sertifikasi") or ""
    is_hima = bool(re.search(r"\bhima\b|\bhimpunan\s+mahasiswa\b", f"{organizer} {raw_text}", re.I))
    is_national_scope = bool(
        re.search(
            r"\bnasional\b|\binternasional\b|\bregional\b|\bcompetition\b|\blomba\b|\bchampionship\b|\bcontest\b",
            f"{activity_name} {organizer}",
            re.I,
        )
    )
    if is_hima and not is_national_scope:
        if mapped is None or mapped.id == 5:
            hima_match = _match_label(LEVEL_FIELD, "Departemen/Program Studi")
            if hima_match is not None:
                return hima_match

    if mapped is not None:
        if mapped.id == 13:
            ukm_match = _match_patterns(LEVEL_FIELD, raw_text, _LEVEL_PATTERNS)
            if ukm_match is not None and ukm_match.id == 7:
                return ukm_match
        return mapped
    match = _match_patterns(LEVEL_FIELD, raw_text, _LEVEL_PATTERNS)
    if match is not None:
        return match

    return _unspecified("level_not_provided")


def _resolve_role(raw_text: str, mapped_fields: Mapping[str, Any]) -> KHPFieldMatch:
    role_value = _field_value(mapped_fields, "raw_role")
    mapped_value = _field_value(mapped_fields, ROLE_FIELD)

    if role_value:
        if re.search(
            r"supervisor|divisi|bidang|seksi|biro|bendahara|bph", role_value, re.I
        ) and not re.search(r"panitia|committee", role_value, re.I):
            match = _match_patterns(ROLE_FIELD, role_value, _ROLE_PATTERNS)
            if match is not None and match.status == "matched":
                return match
        role_match = _match_patterns(ROLE_FIELD, role_value, _ROLE_PATTERNS)
        if role_match is not None and role_match.status == "matched":
            return role_match

        # If bare "juara", "winner", or "pemenang", search raw_text for rank
        if _fold(role_value) in ("juara", "winner", "pemenang"):
            m_rank = re.search(
                r"\bjuara\s+(?:harapan\s+)?(?:i{1,3}|[1-3]|iv|v)\b|\b(?:1st|2nd|3rd|first|second|third)\s+(?:winner|place)\b|\bbest\b|\bfinalis\b",
                raw_text,
                re.I,
            )
            if m_rank:
                rank_match = _match_patterns(ROLE_FIELD, m_rank.group(0), _ROLE_PATTERNS)
                if rank_match is not None and rank_match.status == "matched":
                    return rank_match

    direct = _match_label(ROLE_FIELD, role_value) or _match_label(ROLE_FIELD, mapped_value)
    if direct is not None:
        if direct.id == 1 and role_value and re.search(r"divisi|bidang|seksi|departemen|biro", role_value, re.I):
            sub_match = _match_patterns(ROLE_FIELD, role_value, _ROLE_PATTERNS)
            if sub_match is not None and sub_match.status == "matched":
                return sub_match
        return direct

    # Fallback to direct word presence in raw text (Prioritaskan Juara/Winner sebelum Panitia)
    upper = raw_text.upper()
    m_juara = re.search(
        r"\bJUARA\s+(?:HARAPAN\s+)?(?:I{1,3}|[1-3])\b|\b(?:1ST|2ND|3RD|FIRST|SECOND|THIRD)\s+(?:WINNER|PLACE)\b|\bBEST\b|\bFINALIS\b",
        upper,
    )
    if m_juara:
        juara_match = _match_patterns(ROLE_FIELD, m_juara.group(0), _ROLE_PATTERNS)
        if juara_match is not None and juara_match.status == "matched":
            return juara_match

    if re.search(r"\bPANITIA\b|\bORGANIZING COMMITTEE\b|\bSTEERING COMMITTEE\b|\bAS\s+COMMITTEE\b", upper):
        panitia_match = _match_label(ROLE_FIELD, "Panitia")
        if panitia_match is not None:
            return panitia_match

    if re.search(r"\bPESERTA\b|\bPARTICIPANT\b", upper):
        peserta_match = _match_label(ROLE_FIELD, "Peserta")
        if peserta_match is not None:
            return peserta_match

    return _unspecified("role_not_provided")


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


_EVIDENCE_ALIASES = {
    "sert": {"sertifikat"},
    "sk": {"surat keputusan"},
    "sp": {"surat perintah"},
    "foto kopi karya": {"fotocopi hasil karya", "hasil karya"},
    "daftar hadir": {"daftar hadir"},
    "presensi": {"presensi"},
    "kartu pemilih": {"kartu pemilih"},
    "hasil karya": {"hasil karya", "fotocopi hasil karya"},
    "paten": {"patent"},
    "dok": {"dokumen"},
}


def _evidence_status(
    mapped_fields: Mapping[str, Any],
    rule: MasterKegiatanRule | None,
) -> str:
    if rule is None:
        return "not_checked"
    if "bukti_fisik" not in mapped_fields:
        return "not_available"
    value = _field_value(mapped_fields, "bukti_fisik")
    if _is_unset(value):
        return "missing"
    accepted = {
        accepted_label
        for requirement in rule.dasar_penilaian.split("/")
        for accepted_label in _EVIDENCE_ALIASES.get(_fold(requirement), ())
    }
    return "matched" if _fold(value) in accepted else "not_allowed"


def _lookup_master_rule(
    rules: Iterable[MasterKegiatanRule] | None,
    *,
    id_kelompok_kegiatan: int,
    id_kegiatan_1: int,
    id_tingkat: int | None,
    id_jabatan_prestasi: int | None,
) -> tuple[MasterKegiatanRule | None, str]:
    if rules is None:
        return None, "not_loaded"
    matches = [
        rule
        for rule in rules
        if rule.is_active
        and rule.id_kelompok_kegiatan == id_kelompok_kegiatan
        and rule.id_kegiatan_1 == id_kegiatan_1
        and rule.id_tingkat == id_tingkat
        and rule.id_jabatan_prestasi == id_jabatan_prestasi
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
    master_rules: Iterable[MasterKegiatanRule] | None = None,
) -> KHPMasterResolution:
    use_default_rows = kegiatan2_rows is None
    catalog = get_default_aucc_catalog() if use_default_rows else None
    if use_default_rows:
        kegiatan2_rows = catalog.kegiatan2_rows if catalog else None
    if master_rules is None and use_default_rows:
        master_rules = catalog.master_rules if catalog else None

    role = _resolve_role(raw_text, mapped_fields)
    activity = _resolve_activity(raw_text, mapped_fields, role)
    level = _resolve_level(raw_text, mapped_fields)
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

    master_rule = None
    rule_status = "not_loaded"
    if id_kegiatan_2 is not None and lookup_status == "matched":
        master_rule, rule_status = _lookup_master_rule(
            master_rules,
            id_kelompok_kegiatan=group.id if group.id is not None else -1,
            id_kegiatan_1=activity.id,
            id_tingkat=level.id,
            id_jabatan_prestasi=role.id,
        )
        if rule_status == "ambiguous":
            reasons.append("master_rule_ambiguous")
    evidence_status = _evidence_status(mapped_fields, master_rule)
    if evidence_status in {"missing", "not_allowed"}:
        reasons.append(f"bukti_fisik_{evidence_status}")

    if field_reasons or rule_status == "ambiguous" or evidence_status in {
        "missing",
        "not_allowed",
    }:
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
        master_rule=master_rule,
        rule_status=rule_status,
        evidence_status=evidence_status,
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
