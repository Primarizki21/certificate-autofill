import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from app.services.field_extractor import ExtractedValue
from tests.ner_extractor import NEREntity
from tests.post_processors import score_entity_for_field


def map_entities_to_fields(entities: list[NEREntity], full_text: str = "") -> dict[str, ExtractedValue]:
    fields: dict[str, ExtractedValue] = {}

    orgs = [e for e in entities if e.entity_type == "ORG"]
    if orgs:
        merged = _merge_consecutive(orgs)
        if merged:
            best = max(merged, key=lambda e: score_entity_for_field(e, full_text))
            fields["penyelenggara_kegiatan"] = ExtractedValue(
                value=best.text,
                confidence=round(score_entity_for_field(best, full_text), 2),
                source="ner_indobert",
            )

    evts = [e for e in entities if e.entity_type == "EVT"]
    if evts:
        merged = _merge_consecutive(evts)
        if merged:
            best = max(merged, key=lambda e: score_entity_for_field(e, full_text))
            fields["nama_kegiatan_sertifikasi"] = ExtractedValue(
                value=best.text,
                confidence=round(score_entity_for_field(best, full_text), 2),
                source="ner_indobert",
            )

    dats = [e for e in entities if e.entity_type == "DAT"]
    if dats:
        merged = _merge_consecutive(dats)
        if merged:
            first = merged[0].text
            start, end = _split_date_range(first)
            fields["waktu_mulai_pelaksanaan"] = ExtractedValue(
                value=start or first,
                confidence=round(merged[0].score, 2),
                source="ner_indobert",
            )
            if end:
                fields["waktu_selesai_pelaksanaan"] = ExtractedValue(
                    value=end,
                    confidence=round(merged[0].score, 2),
                    source="ner_indobert",
                )
            elif len(merged) > 1:
                last = merged[-1].text
                _, end = _split_date_range(last)
                fields["waktu_selesai_pelaksanaan"] = ExtractedValue(
                    value=end or last,
                    confidence=round(merged[-1].score, 2),
                    source="ner_indobert",
                )

    nums = [e for e in entities if e.entity_type == "NUM"]
    if nums:
        merged = _merge_consecutive(nums)
        if merged:
            best = max(merged, key=lambda e: score_entity_for_field(e, full_text))
            fields["nomor_bukti_fisik_nomor_sertifikasi"] = ExtractedValue(
                value=best.text,
                confidence=round(score_entity_for_field(best, full_text), 2),
                source="ner_indobert",
            )

    return fields


_DATE_RANGE_RE = re.compile(
    r"(\d{1,2}\s+\w+\s+\d{4})\s*(?:-|\u2013|\u2014|s/d|s\.d\.|sd|sampai|to|until)\s*(\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE,
)


def _split_date_range(text: str) -> tuple[str | None, str | None]:
    m = _DATE_RANGE_RE.search(text.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text, None


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
