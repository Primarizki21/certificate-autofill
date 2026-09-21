from __future__ import annotations
import json
import urllib.request

from app.config import settings
from app.master_data import KHP_MASTER_OPTIONS, KHP_TINGKAT_LABELS
from app.services.extraction_pipeline import run_extraction_pipeline
from app.services.field_extractor import ExtractedValue
from app.services.gemini_extractor import (
    KHP_STAGING_SYSTEM_INSTRUCTION,
    KHP_STAGING_USER_PROMPT_TEMPLATE,
    extract_fields_with_gemini,
    normalize_llm_json,
)
from app.services.khp_master_staging import (
    Kegiatan2LookupRow,
    MasterKegiatanRule,
    apply_khp_master_mapping,
    lookup_kegiatan_2,
    resolve_khp_master_fields,
)
from app.services.pdf_fast_path import FastPathResult
from app.services.semantic_review import build_semantic_review


def _field(value: str | None) -> ExtractedValue:
    return ExtractedValue(value, 0.90 if value else 0.0, "test")


def test_normalized_catalog_keeps_reference_ids_and_labels() -> None:
    activities = KHP_MASTER_OPTIONS["jenis_kegiatan"]
    assert len(activities) == 51
    assert {int(option["id"]) for option in activities} == {
        41,
        42,
        67,
        68,
        69,
        70,
        71,
        72,
        73,
        74,
        83,
        84,
        85,
        86,
        87,
        88,
        89,
        90,
        91,
        92,
        93,
        98,
        99,
        100,
        101,
        102,
        103,
        104,
        105,
        106,
        107,
        108,
        109,
        110,
        111,
        112,
        113,
        114,
        115,
        116,
        117,
        121,
        127,
        129,
        130,
        131,
        132,
        133,
        134,
        135,
        136,
    }
    assert len(KHP_MASTER_OPTIONS["tingkat"]) == 13
    assert len(KHP_MASTER_OPTIONS["prestasi_partisipasi_jabatan"]) == 31
    assert activities[0] == {
        "id": 41,
        "label": "PKKMB",
        "active": True,
        "group_id": 1,
    }
    assert activities[-1]["id"] == 136
    assert activities[-1]["label"].endswith("Entrepreneurship/Business Plan")
    assert KHP_MASTER_OPTIONS["tingkat"][6]["label"] == "UKM"
    assert KHP_MASTER_OPTIONS["prestasi_partisipasi_jabatan"][20]["label"] == "Panitia"


def test_staging_resolver_splits_pkkmb_activity_from_role(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.khp_master_staging.get_default_aucc_catalog",
        lambda: None,
    )
    fields = {
        "jenis_kegiatan": _field("Peserta PKKMB"),
        "tingkat": _field("Universitas"),
        "prestasi_partisipasi_jabatan": _field("Peserta"),
        "raw_role": _field("Peserta"),
    }

    resolution = resolve_khp_master_fields(
        "Sertifikat PKKMB tingkat universitas", fields
    )

    assert resolution.fields["jenis_kegiatan"].id == 41
    assert resolution.fields["jenis_kegiatan"].label == "PKKMB"
    assert resolution.fields["kelompok_kegiatan"].id == 1
    assert resolution.fields["prestasi_partisipasi_jabatan"].id == 6
    assert resolution.status == "awaiting_kegiatan_2_lookup"
    assert resolution.id_kegiatan_2 is None


def test_kegiatan_2_lookup_matches_nullable_dimensions_exactly() -> None:
    rows = [
        Kegiatan2LookupRow(9001, 41, 4, 6),
        Kegiatan2LookupRow(9002, 41, None, 6),
        Kegiatan2LookupRow(9003, 130, None, None),
    ]

    assert lookup_kegiatan_2(
        rows,
        id_kegiatan_1=41,
        id_tingkat=None,
        id_jabatan_prestasi=6,
    ) == (9002, "matched")
    assert lookup_kegiatan_2(
        rows,
        id_kegiatan_1=130,
        id_tingkat=None,
        id_jabatan_prestasi=None,
    ) == (9003, "matched")
    assert lookup_kegiatan_2(
        rows,
        id_kegiatan_1=41,
        id_tingkat=5,
        id_jabatan_prestasi=6,
    ) == (None, "not_found")


def test_staging_resolver_accepts_explicitly_nullable_dimensions() -> None:
    fields = {
        "jenis_kegiatan": _field("PKKMB"),
        "tingkat": _field(None),
        "prestasi_partisipasi_jabatan": _field("Peserta"),
        "raw_role": _field("Peserta"),
    }

    resolution = resolve_khp_master_fields(
        "Sertifikat PKKMB untuk peserta",
        fields,
        [Kegiatan2LookupRow(9002, 41, None, 6)],
    )
    mapped = apply_khp_master_mapping(fields, resolution)

    assert resolution.status == "resolved"
    assert resolution.id_kegiatan_2 == 9002
    assert resolution.fields["tingkat"].status == "unspecified"
    assert mapped["tingkat"].value is None


def test_staging_resolver_attaches_matching_master_rule() -> None:
    fields = {
        "jenis_kegiatan": _field("PKKMB"),
        "tingkat": _field("Universitas"),
        "prestasi_partisipasi_jabatan": _field("Peserta"),
        "raw_role": _field("Peserta"),
        "bukti_fisik": _field("Sertifikat"),
    }
    rule = MasterKegiatanRule(
        source_no=26,
        id_kelompok_kegiatan=1,
        id_kegiatan_1=41,
        id_tingkat=4,
        id_jabatan_prestasi=6,
        dasar_penilaian="Sert/SK/SP",
        id_kegiatan_2=9001,
    )

    resolution = resolve_khp_master_fields(
        "Sertifikat PKKMB tingkat universitas",
        fields,
        [Kegiatan2LookupRow(9001, 41, 4, 6)],
        [rule],
    )

    assert resolution.status == "resolved"
    assert resolution.rule_status == "matched"
    assert resolution.master_rule == rule
    assert resolution.as_dict()["master_rule"]["dasar_penilaian"] == "Sert/SK/SP"


def test_staging_resolver_flags_disallowed_evidence() -> None:
    fields = {
        "jenis_kegiatan": _field("PKKMB"),
        "tingkat": _field("Universitas"),
        "prestasi_partisipasi_jabatan": _field("Peserta"),
        "raw_role": _field("Peserta"),
        "bukti_fisik": _field("Dokumen"),
    }
    rule = MasterKegiatanRule(
        source_no=26,
        id_kelompok_kegiatan=1,
        id_kegiatan_1=41,
        id_tingkat=4,
        id_jabatan_prestasi=6,
        dasar_penilaian="Sert/SK/SP",
        id_kegiatan_2=9001,
    )

    resolution = resolve_khp_master_fields(
        "Sertifikat PKKMB tingkat universitas",
        fields,
        [Kegiatan2LookupRow(9001, 41, 4, 6)],
        [rule],
    )

    assert resolution.status == "needs_review"
    assert resolution.evidence_status == "not_allowed"
    assert "bukti_fisik_not_allowed" in resolution.reasons


def test_staging_resolver_keeps_explicit_ukm_level() -> None:
    fields = {
        "jenis_kegiatan": _field("--"),
        "tingkat": _field("Lainnya"),
        "prestasi_partisipasi_jabatan": _field("Peserta"),
        "raw_role": _field("Peserta"),
    }

    resolution = resolve_khp_master_fields(
        "Magang UKM pada unit kegiatan mahasiswa tingkat UKM", fields
    )

    assert resolution.fields["jenis_kegiatan"].id == 127
    assert resolution.fields["tingkat"].id == 7
    assert resolution.fields["tingkat"].label == "UKM"
    assert resolution.fields["prestasi_partisipasi_jabatan"].id == 6


def test_kegiatan_2_lookup_requires_one_exact_combination() -> None:
    rows = [Kegiatan2LookupRow(9001, 41, 4, 6)]

    assert lookup_kegiatan_2(
        rows,
        id_kegiatan_1=41,
        id_tingkat=4,
        id_jabatan_prestasi=6,
    ) == (9001, "matched")
    assert lookup_kegiatan_2(
        rows,
        id_kegiatan_1=41,
        id_tingkat=5,
        id_jabatan_prestasi=6,
    ) == (None, "not_found")
    assert lookup_kegiatan_2(
        None,
        id_kegiatan_1=41,
        id_tingkat=4,
        id_jabatan_prestasi=6,
    ) == (None, "not_loaded")


def test_unresolved_master_values_are_cleared_for_staging() -> None:
    fields = {
        "jenis_kegiatan": _field("--"),
        "kelompok_kegiatan": _field("Kegiatan Lainnya"),
        "tingkat": _field(None),
        "prestasi_partisipasi_jabatan": _field(None),
    }

    resolution = resolve_khp_master_fields("Dokumen tanpa klasifikasi", fields)
    mapped = apply_khp_master_mapping(fields, resolution)

    assert resolution.status == "needs_review"
    assert resolution.id_kegiatan_2 is None
    for field_name in (
        "jenis_kegiatan",
        "kelompok_kegiatan",
        "tingkat",
        "prestasi_partisipasi_jabatan",
    ):
        assert mapped[field_name].value is None
        assert mapped[field_name].source == "khp_master_staging"


def test_staging_prompt_and_level_normalization_use_all_master_levels() -> None:
    assert all(label in KHP_STAGING_SYSTEM_INSTRUCTION for label in KHP_TINGKAT_LABELS)
    assert all(label in KHP_STAGING_USER_PROMPT_TEMPLATE for label in KHP_TINGKAT_LABELS)
    assert normalize_llm_json(
        {"tingkat": "regional"},
        valid_tingkat_options=KHP_TINGKAT_LABELS,
    )["tingkat"] == "Regional"
    assert normalize_llm_json(
        {"tingkat": "national not accredited"},
        valid_tingkat_options=KHP_TINGKAT_LABELS,
    )["tingkat"] == "Nasional Tidak Ter-Akreditasi"
    assert normalize_llm_json(
        {"tingkat": "unit kegiatan mahasiswa"},
        valid_tingkat_options=KHP_TINGKAT_LABELS,
    )["tingkat"] == "UKM"


def test_semantic_review_accepts_ukm_in_staging_profile() -> None:
    annotations = build_semantic_review(
        "Tingkat UKM untuk unit kegiatan mahasiswa",
        {"tingkat": _field("UKM")},
        valid_tingkat_options=KHP_TINGKAT_LABELS,
    )

    assert "unmapped_level_enum" not in annotations["tingkat"].reasons
    assert "level_conflicts_with_raw_ocr" not in annotations["tingkat"].reasons


def test_pipeline_attaches_master_resolution_only_when_staging_enabled(monkeypatch) -> None:
    raw_text = "Magang UKM tingkat UKM, diselenggarakan oleh Unit Kegiatan Mahasiswa"
    monkeypatch.setattr(
        "app.services.khp_master_staging.get_default_aucc_catalog",
        lambda: None,
    )
    gemini_fields = {
        "full_text": _field(raw_text),
        "nama_kegiatan_sertifikasi": _field("Magang UKM"),
        "nomor_bukti_fisik_nomor_sertifikasi": _field("01/UKM/2025"),
        "penyelenggara_kegiatan": _field("Unit Kegiatan Mahasiswa"),
        "waktu_mulai_pelaksanaan": _field("01/01/2025"),
        "waktu_selesai_pelaksanaan": _field("01/01/2025"),
        "tingkat": _field("UKM"),
        "raw_role": _field("Peserta"),
    }
    monkeypatch.setattr(
        "app.services.extraction_pipeline.extract_text_with_pymupdf",
        lambda _pdf: FastPathResult(raw_text, 1),
    )
    monkeypatch.setattr(
        "app.services.extraction_pipeline.extract_certificate_fields",
        lambda _text: {"full_text": _field(raw_text)},
    )
    calls: list[dict[str, object]] = []

    def fake_gemini(text: str, **kwargs):
        calls.append({"text": text, **kwargs})
        return gemini_fields, {"model": "gemini-staging-test"}

    monkeypatch.setattr(
        "app.services.gemini_extractor.extract_fields_with_gemini",
        fake_gemini,
    )
    flag_names = (
        "enable_ocr_fallback",
        "enable_tesseract_gemini",
        "enable_combined_v2",
        "enable_combined_v3",
        "enable_combined_v4",
        "enable_combined_v4_1",
        "enable_combined_v4_2",
        "enable_organizer_normalization",
        "enable_khp_master_staging",
    )
    original_flags = {name: getattr(settings, name) for name in flag_names}
    try:
        for name in flag_names:
            object.__setattr__(settings, name, False)
        object.__setattr__(settings, "enable_tesseract_gemini", True)
        object.__setattr__(settings, "enable_khp_master_staging", True)
        result = run_extraction_pipeline(b"not-a-real-pdf", "2024/2025", "Sertifikat")
    finally:
        for name, value in original_flags.items():
            object.__setattr__(settings, name, value)

    assert calls == [{"text": raw_text}]
    assert result.mapped_fields["jenis_kegiatan"].value == "Magang UKM"
    assert result.mapped_fields["tingkat"].value == "UKM"
    assert result.master_resolution is not None
    assert result.master_resolution["fields"]["tingkat"]["id"] == 7
    assert result.master_resolution["status"] == "awaiting_kegiatan_2_lookup"
    assert "khp_master_staging" in result.parser_engine


def test_gemini_extractor_stage_sends_master_profile(monkeypatch) -> None:
    body = {
        "usageMetadata": {
            "promptTokenCount": 12,
            "candidatesTokenCount": 5,
            "totalTokenCount": 17,
        },
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "tingkat": "Regional",
                                    "raw_role": "Peserta",
                                }
                            )
                        }
                    ]
                }
            }
        ],
    }
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, _type, _value, _traceback):
            return False

        def read(self):
            return json.dumps(body).encode()

    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    extracted, meta = extract_fields_with_gemini(
        "Tingkat Regional untuk kegiatan mahasiswa",
        api_key="dummy-secret-key",
        timeout_s=0.01,
        khp_master_staging=True,
    )

    assert extracted is not None
    assert extracted["tingkat"].value == "Regional"
    assert meta["prompt_tokens"] == 12
    payload = captured["payload"]
    system_text = payload["systemInstruction"]["parts"][0]["text"]
    user_text = payload["contents"][0]["parts"][0]["text"]
    assert "UKM" in system_text and "Regional" in system_text
    assert "Nasional Tidak Ter-Akreditasi" in user_text

def test_hima_internal_level_resolves_to_departemen_prodi() -> None:
    from app.services.khp_master_staging import _resolve_level

    hima_raw = "Himpunan Mahasiswa S-1 Akuntansi Fakultas Ekonomi dan Bisnis Universitas Airlangga"
    fields_internal = {
        "penyelenggara_kegiatan": "Himpunan Mahasiswa S-1 Akuntansi",
        "nama_kegiatan_sertifikasi": "Pengabdian ORMAWA masa bakti 2025",
        "tingkat": "Fakultas",
    }
    match_internal = _resolve_level(hima_raw, fields_internal)
    assert match_internal.id == 6
    assert match_internal.label == "Departemen/Program Studi"

    fields_national = {
        "penyelenggara_kegiatan": "Himpunan Mahasiswa S-1 Akuntansi",
        "nama_kegiatan_sertifikasi": "National Accounting Competition 2025",
        "tingkat": "Nasional",
    }
    match_national = _resolve_level(hima_raw, fields_national)
    assert match_national.id == 2
    assert match_national.label == "Nasional"


def test_hima_division_and_supervisor_roles_resolve_to_pengurus_inti_lain() -> None:
    from app.services.khp_master_staging import _resolve_role

    supervisor_fields = {"raw_role": "Supervisor Divisi Komunikasi", "prestasi_partisipasi_jabatan": "Ketua"}
    match_supervisor = _resolve_role("", supervisor_fields)
    assert match_supervisor.id == 4
    assert match_supervisor.label == "Pengurus Inti Lain"

    ketua_divisi_fields = {"raw_role": "Ketua Divisi Hubungan Masyarakat", "prestasi_partisipasi_jabatan": "Ketua"}
    match_kadiv = _resolve_role("", ketua_divisi_fields)
    assert match_kadiv.id == 4
    assert match_kadiv.label == "Pengurus Inti Lain"

    ketua_hima_fields = {"raw_role": "Ketua Himpunan Mahasiswa S-1 Akuntansi"}
    match_ketua = _resolve_role("", ketua_hima_fields)
    assert match_ketua.id == 1
    assert match_ketua.label == "Ketua"


def test_hima_kepengurusan_activity_inference() -> None:
    from app.services.khp_master_staging import _resolve_activity, _group_match

    raw_text = "Atas partisipasi dan pengabdiannya dalam Kepengurusan Himpunan Mahasiswa masa bakti 2025"
    fields = {"nama_kegiatan_sertifikasi": "Piagam Penghargaan Pengurus HIMA"}
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id == 67
    assert activity_match.label == "Pengurus Organisasi"
    group_match = _group_match(activity_match)
    assert group_match.id == 2
    assert group_match.label == "Kegiatan Bidang Organisasi dan Kepemimpinan"

def test_ketua_tim_lomba_does_not_become_pengurus_organisasi() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "Diberikan kepada Ketua Tim atas partisipasinya dalam Data Science Competition 2025"
    fields = {
        "raw_role": "Ketua Tim",
        "nama_kegiatan_sertifikasi": "Data Science Competition 2025",
        "penyelenggara_kegiatan": "Universitas Indonesia",
    }
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id != 67
    assert activity_match.id == 83
    assert activity_match.label == "Mengikuti Kegiatan Lomba Ilmiah"

def test_pengurus_tim_lomba_does_not_become_pengurus_organisasi() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "Diberikan kepada Pengurus Tim atas keikutsertaannya dalam Lomba Inovasi Nasional 2025"
    fields = {
        "raw_role": "Pengurus Tim",
        "nama_kegiatan_sertifikasi": "Lomba Inovasi Nasional 2025",
        "penyelenggara_kegiatan": "Kementerian Riset dan Teknologi",
    }
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id != 67
    assert activity_match.id == 83

def test_action_competition_winner_resolves_to_id74() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "ATAS PRESTASINYA SEBAGAI JUARA 1 pada Academic Competition of Data Science 2024 Tingkat Nasional"
    fields = {
        "raw_role": "Juara 1",
        "nama_kegiatan_sertifikasi": "Academic Competition of Data Science 2024",
        "penyelenggara_kegiatan": "Himpunan Mahasiswa Program Studi Sains Data FMIPA Unesa",
    }
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id == 74
    assert "Lomba" in activity_match.label


def test_gelar_rasa_unresolved_activity_triggers_needs_review() -> None:
    from app.services.khp_master_staging import resolve_khp_master_fields

    raw_text = "DIBERIKAN KEPADA FAZIL ATAS PARTISIPASINYA SEBAGAI PESERTA DALAM ACARA GELAR RASA 2024"
    fields = {
        "raw_role": "Peserta",
        "nama_kegiatan_sertifikasi": "GELAR RASA 2024",
        "penyelenggara_kegiatan": "Himasada, Fakultas Ilmu Komputer",
        "tingkat": "Nasional",
    }
    res = resolve_khp_master_fields(raw_text, fields)
    assert res.fields["jenis_kegiatan"].status == "unresolved"
    assert res.status == "needs_review"
    assert "jenis_kegiatan_activity_not_in_master" in res.reasons

def test_kkn_bbk_resolves_to_id42() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "Diberikan kepada mahasiswa atas partisipasinya dalam Belajar Bersama Komunitas (BBK) Periode 5"
    fields = {"nama_kegiatan_sertifikasi": "Belajar Bersama Komunitas (BBK) Periode 5"}
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id == 42
    assert activity_match.label == "KKN-BBM"

def test_arabic_numeral_winner_role_resolves_to_roman_master_label() -> None:
    from app.services.khp_master_staging import _resolve_role

    match_j1 = _resolve_role("raw text", {"raw_role": "Juara 1"})
    assert match_j1.id == 7
    assert match_j1.label == "Juara I"

    match_j2 = _resolve_role("raw text", {"raw_role": "Juara 2"})
    assert match_j2.id == 8
    assert match_j2.label == "Juara II"

    match_j3 = _resolve_role("raw text", {"raw_role": "Juara 3"})
    assert match_j3.id == 9
    assert match_j3.label == "Juara III"

    match_fin = _resolve_role("raw text", {"raw_role": "Finalist"})
    assert match_fin.id == 10
    assert match_fin.label == "Finalis"

def test_training_and_workshop_resolves_to_forum_ilmiah() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "Diberikan kepada mahasiswa sebagai peserta dalam Training Meeting Internal Vol. 1"
    fields = {"nama_kegiatan_sertifikasi": "Training Meeting Internal Vol. 1"}
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id == 84
    assert "forum ilmiah" in activity_match.label.lower()
def test_leadership_regenerasi_resolves_to_latihan_kepemimpinan() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "Atas partisipasinya dalam rangkaian acara REGTER (REGENERASI TERPADU) 2023"
    fields = {"nama_kegiatan_sertifikasi": "REGTER (REGENERASI TERPADU) 2023"}
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id == 70
    assert activity_match.label == "Latihan Kepemimpinan Lainnya"
def test_freshman_solidarity_resolves_to_pkkmb() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "Diberikan kepada mahasiswa baru dalam acara BINARY (Building Freshman Solidarity and Character Development)"
    fields = {"nama_kegiatan_sertifikasi": "BINARY 3.0 (Building Freshman Solidarity and Character Development)"}
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id == 41
    assert activity_match.label == "PKKMB"
def test_social_campaign_resolves_to_bakti_sosial() -> None:
    from app.services.khp_master_staging import _resolve_activity

    raw_text = "Diberikan atas partisipasinya dalam Digital Campaign 2023"
    fields = {"nama_kegiatan_sertifikasi": "Digital Campaign 2023"}
    activity_match = _resolve_activity(raw_text, fields)
    assert activity_match.id == 106
    assert activity_match.label == "Mengikuti Pelaksanaan Bakti Sosial"


def test_gemastik_competition_and_winner_resolves_to_id74() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "SERTIFIKAT Nomor: 962/KMH01/KMH/2025 Diberikan Kepada: Dyah Ayu Retnoningsih "
        "atas partisipasinya sebagai Juara 3 pada Pagelaran Mahasiswa Tingkat Nasional "
        "Bidang Teknologi Informasi dan Komunikasi (GEMASTIK) XVIII Tahun 2025 "
        "Kementerian Pendidikan Tinggi, Sains, dan Teknologi Republik Indonesia"
    )
    fields = {
        "raw_role": "Juara 3",
        "nama_kegiatan_sertifikasi": "Pagelaran Mahasiswa Tingkat Nasional Bidang Teknologi Informasi dan Komunikasi (GEMASTIK) XVIII",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 9
    assert role_match.label == "Juara III"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 74
    assert "Lomba" in act_match.label


def test_bare_juara_with_ordinal_winner_in_text_resolves_rank() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = "CERTIFICATE OF ACHIEVEMENT Presented To Elzandi as 3rd Winner of Data Science Competition MCF ITB 2024"
    fields = {
        "raw_role": "Juara",
        "nama_kegiatan_sertifikasi": "Data Science Competition MCF ITB 2024",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 9
    assert role_match.label == "Juara III"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 74


def test_kementerian_text_does_not_falsely_match_menteri_role() -> None:
    from app.services.khp_master_staging import _resolve_role

    raw_text = "Diselenggarakan oleh Kementerian Pendidikan Tinggi, Riset, dan Teknologi RI. Sebagai Juara 1."
    fields = {"raw_role": "Juara 1"}
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 7
    assert role_match.label == "Juara I"
    assert role_match.status == "matched"


def test_competition_division_with_ormawa_context_does_not_become_pengurus_organisasi() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "KEMENTERIAN PENDIDIKAN DAN KEBUDAYAAN UNIVERSITAS NEGERI SURABAYA "
        "HIMPUNAN MAHASISWA SAINS DATA Kompleks Ormawa FMIPA Unesa "
        "ATAS PRESTASINYA SEBAGAI JUARA 1 Divisi Data Mining pada Academic Competition of Data Science 2024"
    )
    fields = {
        "raw_role": "JUARA 1 Divisi Data Mining",
        "nama_kegiatan_sertifikasi": "Academic Competition of Data Science 2024",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 7
    assert role_match.label == "Juara I"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 74
    assert act_match.id != 67


def test_panitia_karsa_pkkmb_resolves_to_panitia_id71() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "SERTIFIKAT Nomor: 1944/UN3.FTMM/TM.00.02/2023 Diberikan kepada: VENEDICT "
        "atas partisipasinya sebagai: PANITIA dalam Kegiatan Pengenalan Kehidupan Kampus "
        "bagi Mahasiswa Baru Fakultas (KARSA) 2023 yang diselenggarakan oleh Fakultas Teknologi Maju dan Multidisiplin"
    )
    fields = {
        "raw_role": "Panitia",
        "nama_kegiatan_sertifikasi": "KARSA FTMM 2024",
        "tingkat": "Fakultas",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 21
    assert role_match.label == "Panitia"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 71
    assert act_match.label == "Panitia Dalam Suatu Kegiatan Kemahasiswaan"


def test_peserta_binary_freshman_orientation_resolves_to_pkkmb_id41() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "SERTIFIKAT DIBERIKAN KEPADA Venedict atas partisipasinya sebagai PESERTA "
        "Dalam rangkaian acara BINARY (Building Freshman Solidarity and Character Development) "
        "yang diselenggarakan oleh Program Studi S1 Teknologi Sains Data"
    )
    fields = {
        "raw_role": "Peserta",
        "nama_kegiatan_sertifikasi": "BINARY 2022 (Building Freshman Solidarity and Character Development)",
        "tingkat": "Departemen/Program Studi",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 6
    assert role_match.label == "Peserta"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 41
    assert act_match.label == "PKKMB"
    assert act_match.id != 67


def test_dataquest_peserta_resolves_to_mengikuti_lomba_id83() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "SERTIFIKAT No. 3978/B/UN3.FTMM/KM.06.02/2025 Peserta Objective Quest ELZANDI IRFAN ZIKRA "
        "Dalam kegiatan Dataquest 4.0 part of Airnology 4.0 untuk kategori SMA/Sederajat dan Mahasiswa "
        "yang diselenggarakan oleh BEM FTMM bekerja sama dengan Himpunan Mahasiswa Teknologi Sains Data"
    )
    fields = {
        "raw_role": "Peserta",
        "nama_kegiatan_sertifikasi": "Dataquest 4.0",
        "tingkat": "Nasional",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 6
    assert role_match.label == "Peserta"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 83
    assert act_match.label == "Mengikuti Kegiatan Lomba Ilmiah"


def test_first_place_winner_resolves_to_juara_1_id7() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "CERTIFICATE Awarded to: 25/435/SF/06/RASIO/BEHIMASTA/X/2025\n"
        "As the First Place Winner of the University Infographic Competition RASIO 9.0\n"
        "Organized by Badan Eksekutif Himpunan Mahasiswa Statistika 2025, FMIPA Unpad"
    )
    fields = {
        "raw_role": "First Place Winner",
        "nama_kegiatan_sertifikasi": "University Infographic Competition RASIO 9.0",
        "tingkat": "Nasional",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 7
    assert role_match.label == "Juara I"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 74


def test_vice_president_and_membership_resolves_to_pengurus_organisasi_id67() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "IRIS CERTIFICATE OF MEMBERSHIP Number: 5287/B/UN3.FTMM/KM.06.02/2025\n"
        "THIS CERTIFICATE IS PROUDLY PRESENTED TO: Fazil Putra\n"
        "AS A VICE PRESIDENT OF Innovative Research of Intelligent System (IRIS) "
        "Faculty of Advanced Technology and Multidisciplinary for the period of 2025"
    )
    fields = {
        "raw_role": "Wakil Ketua",
        "nama_kegiatan_sertifikasi": "Innovative Research of Intelligent System (IRIS)",
        "tingkat": "Fakultas",
    }
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 2
    assert role_match.label == "Wakil Ketua"

    act_match = _resolve_activity(raw_text, fields, role_match)
    assert act_match.id == 67
    assert act_match.label == "Pengurus Organisasi"


def test_general_manager_resolves_to_ketua_id1() -> None:
    from app.services.khp_master_staging import _resolve_role

    raw_text = "Diberikan kepada John Doe sebagai General Manager BSO Robotika 2025"
    fields = {"raw_role": "General Manager"}
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 1
    assert role_match.label == "Ketua"


def test_manager_resolves_to_pengurus_inti_id4() -> None:
    from app.services.khp_master_staging import _resolve_role

    raw_text = "Diberikan kepada Jane Doe sebagai Project Manager BSO Robotika 2025"
    fields = {"raw_role": "Project Manager"}
    role_match = _resolve_role(raw_text, fields)
    assert role_match.id == 4
    assert role_match.label == "Pengurus Inti Lain"


def test_bare_certification_typo_does_not_falsely_trigger_sertifikasi_profesi() -> None:
    from app.services.khp_master_staging import _resolve_activity, _resolve_role

    raw_text = (
        "CERTIFICATE OF PARTICIPATION\n"
        "This certification is proudly present to ELZANDI IRFAN ZIKRA "
        "For participation as an attendee in the event AIRNOLOGY 2.0"
    )
    fields = {
        "raw_role": "Peserta",
        "nama_kegiatan_sertifikasi": "AIRNOLOGY 2.0",
        "tingkat": "Fakultas",
    }
    role_match = _resolve_role(raw_text, fields)
    act_match = _resolve_activity(raw_text, fields, role_match)
    # Must NOT falsely match ID 129 (Mengikuti Kegiatan Sertifikasi)
    assert act_match.id != 129
