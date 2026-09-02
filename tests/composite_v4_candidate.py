"""B8 — Kandidat Produksi Komposit (Composite Candidate) — modul terisolasi.

Menyatukan komponen yang LULUS gate cabang B1–B7 di atas bundle v4.2
(`apply_combined_v4_2`), semuanya di `tests/` — produksi TIDAK disentuh:

  - B4: router disambiguasi hardened v7      (`route_with_disambiguation_v7`)
  - B5: ekstraktor kegiatan v9 anti-bleed    (`extract_activity_v9`)
  - B6: normalizer nomor v6 (preservasi + guard) (`normalize_nomor_v6`)

Komponen yang TIDAK lulus gate (B1 fast anchor FAIL, B2 probe, B3 confidence
FAIL) TIDAK dimasukkan — confidence B3 tidak mengubah nilai (hanya flag review)
sehingga absennya tidak memengaruhi akurasi.

HYB-003 (organizer rapid-only merge) hanya berlaku di korpus OCR scan-49 —
dievaluasi terpisah di benchmark (tabel report-only), bukan di korpus teks.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.combined_extractor import extract_dates_v2, normalize_organizer_v7
from app.services.field_extractor import ExtractedValue, extract_certificate_fields
from app.services.form_mapper import map_fields_to_form
from app.services.organizer_v2 import extract_organizer_v2
from tests.organizer_tess_v8 import extract_organizer_v8_result
from tests.activity_extractor_v9 import extract_activity_v9
from tests.nomor_normalizer_v6 import normalize_nomor_v6
from tests.router_disambig_v7 import route_with_disambiguation_v7


def apply_composite_v4_candidate(
    extracted: dict[str, ExtractedValue],
    raw_text: str,
    organizer_variant: str = "v2",
) -> dict[str, ExtractedValue]:
    """Komposit B8 dengan varian organizer staging yang eksplisit."""
    if organizer_variant not in {"v2", "v8"}:
        raise ValueError(f"Unknown organizer variant: {organizer_variant}")
    result = dict(extracted)

    # B5: activity v9 (anti-bleed) — menggantikan activity_v8.
    act = extract_activity_v9(raw_text)
    if act:
        result["nama_kegiatan_sertifikasi"] = ExtractedValue(act, 0.95, "activity_v9")

    content_lines = [line for line in raw_text.splitlines() if line.strip()]
    if organizer_variant == "v8" and len(content_lines) >= 6:
        v8_org = extract_organizer_v8_result(raw_text)
        if v8_org.value:
            result["penyelenggara_kegiatan"] = ExtractedValue(
                v8_org.value,
                v8_org.confidence,
                v8_org.source,
            )
        else:
            # Jangan menghapus baseline bila v8 tidak menemukan kandidat.
            v2_org = extract_organizer_v2(raw_text)
            norm_org = normalize_organizer_v7(v2_org, raw_text)
            if norm_org:
                result["penyelenggara_kegiatan"] = ExtractedValue(norm_org, 0.90, "organizer_v7")
            elif v2_org:
                result["penyelenggara_kegiatan"] = ExtractedValue(v2_org, 0.84, "organizer_v2")
    else:
        # Organizer v7 (ORG-007 — baseline resmi) untuk v2 atau teks pendek.
        v2_org = extract_organizer_v2(raw_text)
        norm_org = normalize_organizer_v7(v2_org, raw_text)
        if norm_org:
            result["penyelenggara_kegiatan"] = ExtractedValue(norm_org, 0.90, "organizer_v7")
        elif v2_org:
            result["penyelenggara_kegiatan"] = ExtractedValue(v2_org, 0.84, "organizer_v2")

    # B6: nomor v6 (preservasi panjang digit + guard Roman) — confidence 0.78
    # bila ada perbaikan OCR (memicu needs_review di <0.80).
    val, repaired = normalize_nomor_v6(raw_text)
    if val:
        result["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(
            val, 0.78 if repaired else 0.95, "nomor_v6"
        )

    # Dates v2 (DATE-001 — sama dgn v4.2).
    d_s, d_e, d_conf = extract_dates_v2(raw_text)
    if d_s and d_e:
        result["waktu_mulai_pelaksanaan"] = ExtractedValue(d_s, d_conf, "date_v2")
        result["waktu_selesai_pelaksanaan"] = ExtractedValue(d_e, d_conf, "date_v2")

    # B4: router disambiguasi hardened v7.
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
    tingkat, rule = route_with_disambiguation_v7(raw_text, active_org, active_act)
    if tingkat:
        result["tingkat"] = ExtractedValue(tingkat, 0.98, f"router:{rule}")

    return result


def run_composite(raw_text: str, organizer_variant: str = "v2") -> dict[str, str]:
    extracted = extract_certificate_fields(raw_text)
    extracted = apply_composite_v4_candidate(extracted, raw_text, organizer_variant)
    mapped = map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")
    return {k: v.value or "" for k, v in mapped.items()}


if __name__ == "__main__":
    t = "NO: OOO4/DPKKA/KM/I/2026 — Panitia dalam acara Karya Inovasi Mahasiswa 2026 yang diadakan oleh BEM FTMM"
    out = run_composite(t)
    print("nomor:", out.get("nomor_bukti_fisik_nomor_sertifikasi"))
    print("kegiatan:", out.get("nama_kegiatan_sertifikasi"))
    assert out.get("nomor_bukti_fisik_nomor_sertifikasi") == "0004/DPKKA/KM/I/2026"
    assert out.get("nama_kegiatan_sertifikasi") == "Karya Inovasi Mahasiswa 2026"
    print("ok: apply_composite_v4_candidate")
