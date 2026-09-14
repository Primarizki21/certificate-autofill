from __future__ import annotations

from datetime import date

from app.services.aucc_persistence import build_krp_khp_values
from app.services.field_extractor import ExtractedValue


def test_build_krp_khp_values_maps_pipeline_metadata() -> None:
    fields = {
        "nama_kegiatan_sertifikasi": ExtractedValue("PKKMB", 0.9, "test"),
        "penyelenggara_kegiatan": ExtractedValue("Panitia PKKMB", 0.9, "test"),
        "waktu_mulai_pelaksanaan": ExtractedValue("18/08/2024", 0.9, "test"),
        "waktu_selesai_pelaksanaan": ExtractedValue("19/08/2024", 0.9, "test"),
        "jenis_penyelenggara": ExtractedValue("PTN di Indonesia", 0.9, "test"),
        "nomor_bukti_fisik_nomor_sertifikasi": ExtractedValue(
            "1849/UN3.FTMM/KM.05/2023", 0.9, "test"
        ),
    }

    values = build_krp_khp_values(
        "document-1",
        fields,
        {"id_kegiatan_2": 4098, "status": "resolved"},
    )

    assert values["document_id"] == "document-1"
    assert values["id_kegiatan_2"] == 4098
    assert values["nm_krp_khp"] == "PKKMB"
    assert values["penyelenggara_krp_khp"] == "Panitia PKKMB"
    assert values["waktu_krp_khp"] == date(2024, 8, 18)
    assert values["waktu_krp_khp_selesai"] == date(2024, 8, 19)
    assert values["jenis_penyelenggara"] == "PTN di Indonesia"
    assert values["no_bukti_fisik"] == "1849/UN3.FTMM/KM.05/2023"
    assert values["id_semester"] is None
    assert values["id_bukti_fisik"] is None
