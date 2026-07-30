import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.ner_extractor import NEREntity


def score_entity_for_field(entity: NEREntity, full_text: str) -> float:
    text = entity.text.strip()
    if not text:
        return -1.0

    score = entity.score

    words = [w for w in text.split() if w]
    n_words = len(words)
    if n_words > 0 and full_text and entity.start < len(full_text):
        if full_text[entity.start].isupper():
            score += 0.15

    if re.search(r"\d", text):
        score += 0.10

    if len(text) < 3:
        score -= 0.3
    if len(text) < 5 and n_words == 1:
        score -= 0.1
    if len(text) > 100:
        score -= 0.15

    if re.search(r"[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{5,}", text):
        score -= 0.2

    text_lower = text.lower()
    full_lower = full_text.lower()
    pos = full_lower.find(text_lower)
    if pos >= 0 and pos < len(full_text) * 0.3:
        score += 0.10

    return score


def is_likely_person_name(text: str, full_text: str) -> bool:
    text_lower = text.lower().strip()
    full_lower = full_text.lower()
    pos = full_lower.find(text_lower)
    if pos < 0:
        return False
    before = full_lower[max(0, pos - 80):pos]
    if re.search(r"diberikan\s+kepada|menghargaan\s+kepada|diberikan\s+kpd", before):
        return True
    return False


def has_nip_or_nim_nearby(full_text: str, entity_end: int, look_after: int = 200) -> bool:
    after = full_text[entity_end:entity_end + look_after]
    if re.search(r"NIP\.?\s*[:\s]*\d", after, re.IGNORECASE):
        return True
    if re.search(r"NIM\.?\s*[:\s]*\d", after, re.IGNORECASE):
        return True
    return False


def has_dedication_prefix(full_text: str, entity_start: int, look_before: int = 40) -> bool:
    before = full_text[max(0, entity_start - look_before):entity_start]
    if re.search(r"A\.\s*N\.|ATAS\s+NAMA|UNTUK", before, re.IGNORECASE):
        return True
    return False


def is_signer_role(entity: NEREntity, full_text: str) -> bool:
    if has_dedication_prefix(full_text, entity.start):
        return True
    if has_nip_or_nim_nearby(full_text, entity.end):
        return True
    if len(full_text) > 0 and entity.start / len(full_text) > 0.7:
        if has_nip_or_nim_nearby(full_text, entity.start, look_after=500):
            return True
    return False


def filter_signer_roles(entities: list[NEREntity], full_text: str) -> list[NEREntity]:
    org_entities = [e for e in entities if e.entity_type == "ORG"]
    if not org_entities:
        return entities

    filtered = []
    for e in entities:
        if e.entity_type == "ORG" and is_signer_role(e, full_text):
            continue
        if e.entity_type == "ORG" and is_likely_person_name(e.text, full_text):
            continue
        filtered.append(e)

    remaining_orgs = [e for e in filtered if e.entity_type == "ORG"]
    if not remaining_orgs and org_entities:
        return entities

    return filtered
