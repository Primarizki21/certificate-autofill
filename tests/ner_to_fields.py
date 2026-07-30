import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import ExtractedValue
from tests.ner_extractor import NEREntity


def map_entities_to_fields(entities: list[NEREntity]) -> dict[str, ExtractedValue]:
    fields: dict[str, ExtractedValue] = {}

    orgs = [e for e in entities if e.entity_type == "ORG"]
    if orgs:
        merged = _merge_consecutive(orgs)
        if merged:
            best = max(merged, key=lambda e: len(e.text))
            fields["penyelenggara_kegiatan"] = ExtractedValue(
                value=best.text,
                confidence=round(best.score, 2),
                source="ner_indobert",
            )

    evts = [e for e in entities if e.entity_type == "EVT"]
    if evts:
        merged = _merge_consecutive(evts)
        if merged:
            best = max(merged, key=lambda e: len(e.text))
            fields["nama_kegiatan_sertifikasi"] = ExtractedValue(
                value=best.text,
                confidence=round(best.score, 2),
                source="ner_indobert",
            )

    dats = [e for e in entities if e.entity_type == "DAT"]
    if dats:
        merged = _merge_consecutive(dats)
        if merged:
            date_text = merged[0].text
            fields["waktu_mulai_pelaksanaan"] = ExtractedValue(
                value=date_text,
                confidence=round(merged[0].score, 2),
                source="ner_indobert",
            )
            if len(merged) > 1:
                fields["waktu_selesai_pelaksanaan"] = ExtractedValue(
                    value=merged[-1].text,
                    confidence=round(merged[-1].score, 2),
                    source="ner_indobert",
                )

    nums = [e for e in entities if e.entity_type == "NUM"]
    if nums:
        merged = _merge_consecutive(nums)
        if merged:
            best = max(merged, key=lambda e: len(e.text))
            fields["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(
                value=best.text,
                confidence=round(best.score, 2),
                source="ner_indobert",
            )

    return fields


def _merge_consecutive(entities: list[NEREntity]) -> list[NEREntity]:
    if not entities:
        return []
    sorted_ents = sorted(entities, key=lambda e: e.start)
    merged = []
    current = sorted_ents[0]
    for e in sorted_ents[1:]:
        gap = e.start - current.end
        if 0 <= gap <= 3:
            current = NEREntity(
                entity_type=current.entity_type,
                text=current.text + (" " if text_requires_space(current.text, e.text) else "") + e.text,
                start=current.start,
                end=e.end,
                score=max(current.score, e.score),
            )
        else:
            merged.append(current)
            current = e
    merged.append(current)
    return merged


def text_requires_space(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a[-1].isalpha() and b[0].isalpha()
