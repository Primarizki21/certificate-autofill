import re

from tests.date_normalizer import normalize_date

NOMOR_NORMALIZE = re.compile(r"[ .\-\t]+")
TEXT_NORMALIZE = re.compile(r"[^a-z0-9/]+")


def normalize_value(value: str) -> str:
    return TEXT_NORMALIZE.sub(" ", value.lower()).strip()


def normalize_nomor(value: str) -> str:
    return NOMOR_NORMALIZE.sub("", value.lower()).strip()


def exact_match(expected: str, actual: str | None) -> bool:
    if not actual:
        return False
    return normalize_value(expected) == normalize_value(actual)


def contains_match(expected: str, actual: str | None) -> bool:
    if not actual:
        return False
    e = normalize_value(expected)
    a = normalize_value(actual)
    if not e or not a:
        return False
    return e in a or a in e


def token_overlap_score(expected: str, actual: str | None) -> float:
    if not actual:
        return 0.0
    e_tokens = set(normalize_value(expected).split())
    a_tokens = set(normalize_value(actual).split())
    if not e_tokens or not a_tokens:
        return 0.0
    overlap = e_tokens & a_tokens
    return len(overlap) / min(len(e_tokens), len(a_tokens))


def match_field(expected: str, actual: str | None, field_name: str) -> dict:
    if not actual:
        return {"exact": False, "contains": False, "token_overlap": 0.0, "fuzzy": False}

    field_name = field_name.replace(" ", "_")

    if field_name in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        exp_date = normalize_date(expected)
        act_date = normalize_date(actual)
        exact = exp_date == act_date if exp_date and act_date else False
        return {"exact": exact, "contains": exact, "token_overlap": 1.0 if exact else 0.0, "fuzzy": exact}

    if field_name == "nomor_bukti_fisik_nomor_sertifikasi":
        exact = normalize_nomor(expected) == normalize_nomor(actual)
        return {"exact": exact, "contains": exact, "token_overlap": 1.0 if exact else 0.0, "fuzzy": exact}

    exact = exact_match(expected, actual)
    contains = contains_match(expected, actual)
    overlap = token_overlap_score(expected, actual)

    return {
        "exact": exact,
        "contains": contains,
        "token_overlap": overlap,
        "fuzzy": contains or overlap >= 0.5,
    }
