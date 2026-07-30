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


def _levenshtein(s1: str, s2: str) -> int:
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insert = curr[j] + 1
            delete = prev[j + 1] + 1
            subst = prev[j] + (c1 != c2)
            curr.append(min(insert, delete, subst))
        prev = curr
    return prev[-1]


def wer_score(reference: str, hypothesis: str) -> float:
    if not reference:
        return 0.0
    if not hypothesis:
        return 1.0
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 0.0
    edit_dist = _levenshtein(ref_words, hyp_words)
    return min(edit_dist / len(ref_words), 1.0)


def cer_score(reference: str, hypothesis: str) -> float:
    if not reference:
        return 0.0
    if not hypothesis:
        return 1.0
    if not reference.strip():
        return 0.0
    edit_dist = _levenshtein(reference, hypothesis)
    return min(edit_dist / len(reference), 1.0)


def is_abbreviation_of(abbr: str, full: str) -> bool:
    abbr_clean = re.sub(r"[^a-zA-Z]", "", abbr).lower()
    if not abbr_clean or len(abbr_clean) < 2:
        return False
    full_words = re.sub(r"[^a-zA-Z\s]", "", full).lower().split()
    if len(full_words) < 2 or len(full_words) > len(abbr_clean) * 3:
        return False
    i = 0
    for word in full_words:
        if not word:
            continue
        if i < len(abbr_clean) and word[0] == abbr_clean[i]:
            i += 1
    return i >= len(abbr_clean) * 0.5


def abbreviation_match(expected: str, actual: str | None) -> bool:
    if not actual:
        return False
    return is_abbreviation_of(expected, actual) or is_abbreviation_of(actual, expected)


def match_field(expected: str, actual: str | None, field_name: str) -> dict:
    if not actual:
        return {
            "exact": False, "contains": False, "token_overlap": 0.0, "fuzzy": False,
            "wer": 1.0, "cer": 1.0,
        }

    field_name = field_name.replace(" ", "_")

    if field_name in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
        exp_date = normalize_date(expected)
        act_date = normalize_date(actual)
        exact = exp_date == act_date if exp_date and act_date else False
        date_wer = wer_score(exp_date or "", act_date or "")
        date_cer = cer_score(exp_date or "", act_date or "")
        return {
            "exact": exact, "contains": exact, "token_overlap": 1.0 if exact else 0.0, "fuzzy": exact,
            "wer": date_wer, "cer": date_cer,
        }

    if field_name == "nomor_bukti_fisik_nomor_sertifikasi":
        exact = normalize_nomor(expected) == normalize_nomor(actual)
        nomor_wer = wer_score(normalize_nomor(expected), normalize_nomor(actual))
        nomor_cer = cer_score(normalize_nomor(expected), normalize_nomor(actual))
        return {
            "exact": exact, "contains": exact, "token_overlap": 1.0 if exact else 0.0, "fuzzy": exact,
            "wer": nomor_wer, "cer": nomor_cer,
        }

    exact = exact_match(expected, actual)
    contains = contains_match(expected, actual)
    overlap = token_overlap_score(expected, actual)
    norm_exp = normalize_value(expected)
    norm_act = normalize_value(actual)
    w = wer_score(norm_exp, norm_act)
    c = cer_score(norm_exp, norm_act)
    fuzzy = contains or overlap >= 0.5

    if not fuzzy and field_name in ("penyelenggara_kegiatan", "nama_kegiatan_sertifikasi"):
        if abbreviation_match(expected, actual):
            fuzzy = True
            exact = True

    return {
        "exact": exact,
        "contains": contains,
        "token_overlap": overlap,
        "fuzzy": fuzzy,
        "wer": w,
        "cer": c,
    }
