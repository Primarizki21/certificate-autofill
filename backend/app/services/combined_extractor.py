"""Combined Extractor v2 — Staging Bundle (0 LLM).

Menyatukan seluruh modul offline berkinerja tinggi yang telah lolos validasi (PASS):
1. AKT-005 (activity_extractor): nama_kegiatan_sertifikasi -> 62.2% exact (+55.4pt)
2. ORG-004 + PROD-002 (organizer_normalize): penyelenggara_kegiatan -> 66.2% exact
3. PROD-002 (organizer_normalize): nomor_bukti_fisik_nomor_sertifikasi -> 76.9% exact
4. ROUTER-002..004 (tingkat_router): tingkat -> 50/74 @ 100% precision

Gating: Terisolasi di belakang `settings.enable_combined_v2` (default: False).
"""

from app.services.activity_extractor import extract_activity
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

    # 1. Ekstraksi nama kegiatan v5 (AKT-005)
    new_act = extract_activity(raw_text)
    if new_act:
        result["nama_kegiatan_sertifikasi"] = ExtractedValue(
            new_act, 0.88, "activity_v5"
        )

    # 2. Ekstraksi & normalisasi penyelenggara v4 (ORG-004)
    v2_org = extract_organizer_v2(raw_text)
    norm_org = normalize_organizer(v2_org, raw_text)
    if norm_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(
            norm_org, 0.85, "organizer_v4"
        )
    elif v2_org:
        result["penyelenggara_kegiatan"] = ExtractedValue(
            v2_org, 0.84, "organizer_v2"
        )

    # 3. Normalisasi nomor sertifikat v2 (PROD-002)
    norm_nomor = normalize_nomor(raw_text)
    if norm_nomor:
        result["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(
            norm_nomor, 0.95, "nomor_v2"
        )

    # 4. Routing tingkat (ROUTER-002..004)
    active_org = (
        result.get("penyelenggara_kegiatan").value
        if result.get("penyelenggara_kegiatan")
        else ""
    ) or ""
    tingkat, rule = route_tingkat_trace(raw_text, active_org)
    if tingkat:
        result["tingkat"] = ExtractedValue(
            tingkat, 0.95, f"router:{rule}"
        )

    return result
