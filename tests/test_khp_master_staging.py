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
    apply_khp_master_mapping,
    lookup_kegiatan_2,
    resolve_khp_master_fields,
)
from app.services.pdf_fast_path import FastPathResult
from app.services.semantic_review import build_semantic_review


def _field(value: str | None) -> ExtractedValue:
    return ExtractedValue(value, 0.90 if value else 0.0, "test")


def test_normalized_catalog_keeps_reference_ids_and_labels() -> None:
    assert len(KHP_MASTER_OPTIONS["jenis_kegiatan"]) == 44
    assert len(KHP_MASTER_OPTIONS["tingkat"]) == 13
    assert len(KHP_MASTER_OPTIONS["prestasi_partisipasi_jabatan"]) == 31
    assert KHP_MASTER_OPTIONS["jenis_kegiatan"][0] == {
        "id": 41,
        "label": "PKKMB",
        "active": True,
        "group_id": 1,
    }
    assert KHP_MASTER_OPTIONS["tingkat"][6]["label"] == "UKM"
    assert KHP_MASTER_OPTIONS["prestasi_partisipasi_jabatan"][20]["label"] == "Panitia"


def test_staging_resolver_splits_pkkmb_activity_from_role() -> None:
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

    assert calls == [{"text": raw_text, "khp_master_staging": True}]
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
