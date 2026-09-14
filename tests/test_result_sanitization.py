import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.main import get_result
from app.models import Document, ExtractedField, KHPMasterResolution


def test_html_and_js_contain_no_internal_review_panel() -> None:
    root = Path(__file__).resolve().parent.parent
    html_files = [
        root / "frontend" / "index.html",
        root / "backend" / "app" / "static" / "index.html",
    ]
    js_files = [
        root / "frontend" / "app.js",
        root / "backend" / "app" / "static" / "app.js",
    ]

    forbidden_terms = [
        "auccResolutionSection",
        "ID Kegiatan 2",
        "kegiatan_2",
        "Catatan Review",
        "auccStatusBadge",
        "auccMasterSummary",
        "auccEvidenceSummary",
    ]

    for html_path in html_files:
        assert html_path.exists(), f"File {html_path} must exist"
        content = html_path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in content, f"Forbidden term '{term}' leaked in {html_path}"

    for js_path in js_files:
        assert js_path.exists(), f"File {js_path} must exist"
        content = js_path.read_text(encoding="utf-8")
        assert "renderAuccResolution" not in content, f"renderAuccResolution found in {js_path}"
        assert "humanizeReason" not in content, f"humanizeReason found in {js_path}"
        assert "error.message" not in content, f"error.message leaked in {js_path}"
        assert "Cek terminal backend" not in content, f"Internal terminal reference leaked in {js_path}"
        assert "Status parsing:" not in content, f"Raw status parsing string leaked in {js_path}"


def test_get_result_uses_public_extraction_result_with_zero_internal_leakage(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings", SimpleNamespace(enable_khp_master_staging=True))
    mock_db = MagicMock()
    doc = Document(
        id="doc-test-123",
        original_file_name="sertifikat.pdf",
        checksum_sha256="fake_sha",
        tahun_akademik="2024/2025",
        mime_type="application/pdf",
        file_size=1024,
        status="completed",
        parser_engine="tesseract_gemini",
    )
    field = ExtractedField(
        id="f1",
        document_id="doc-test-123",
        form_field_name="nama_kegiatan_sertifikasi",
        extracted_value="FIT COMPETITION 2025",
        confidence=0.95,
        source="gemini",
        needs_review=False,
    )

    full_internal_resolution = {
        "status": "needs_review",
        "id_kegiatan_2": 4098,
        "lookup_status": "matched",
        "master_rule": {
            "id": 100,
            "dasar_penilaian": "Sertifikat Resmi",
            "skp": 15,
        },
        "rule_status": "matched",
        "evidence_status": "matched",
        "reasons": ["jenis_kegiatan_activity_not_in_master"],
        "fields": {
            "jenis_kegiatan": {"id": 41, "label": "PKKMB", "status": "matched", "source": "rule", "confidence": 0.9},
            "kelompok_kegiatan": {"id": 1, "label": "Kegiatan Wajib Universitas", "status": "matched", "source": "rule", "confidence": 0.9},
        },
    }
    resolution_row = KHPMasterResolution(
        id="res-123",
        document_id="doc-test-123",
        resolution_json=json.dumps(full_internal_resolution),
    )

    def mock_query(model):
        q = MagicMock()
        if model == Document:
            q.filter.return_value.first.return_value = doc
        elif model == ExtractedField:
            q.filter.return_value.all.return_value = [field]
        elif model == KHPMasterResolution:
            q.filter.return_value.one_or_none.return_value = resolution_row
        return q

    mock_db.query.side_effect = mock_query
    mock_db.get.return_value = doc

    result = get_result("doc-test-123", db=mock_db)
    payload = result.model_dump()

    # 1. Field form tetap ada untuk autofill
    assert "fields" in payload
    assert payload["fields"]["nama_kegiatan_sertifikasi"]["value"] == "FIT COMPETITION 2025"

    # 2. Public schema sama sekali tidak memiliki key master_resolution, parser_engine, raw_text_preview
    assert "master_resolution" not in payload, "Public response must not expose master_resolution"
    assert "parser_engine" not in payload, "Public response must not expose parser_engine"
    assert "raw_text_preview" not in payload, "Public response must not expose raw_text_preview"

    # 3. Serialized JSON bebas dari ID internal, rules, atau review chips
    raw_json_str = json.dumps(payload)
    for forbidden in ["id_kegiatan_2", "kegiatan_2", "master_rule", "reasons", "lookup_status", "rule_status"]:
        assert forbidden not in raw_json_str, f"Forbidden internal property '{forbidden}' found in serialized payload"
