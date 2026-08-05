import re

from tests.date_normalizer import normalize_date

NOMOR_NORMALIZE = re.compile(r"[ .\-\t]+")
TEXT_NORMALIZE = re.compile(r"[^a-z0-9/]+")

# Kata sambung/filler yang tidak memberi sinyal pembeda organisasi.
# "universitas"/"fakultas" TIDAK dimasukkan: UNAIR/FTMM adalah portmanteau
# yang hurufnya harus tetap ikut check subsequence (UNAIR=Universitas Airlangga).
ABBR_STOPWORDS = {"dan", "dengan", "di", "yang", "of", "the", "for", "and", "de"}


def normalize_value(value: str) -> str:
    return TEXT_NORMALIZE.sub(" ", value.lower()).strip()


def normalize_nomor(value: str) -> str:
    return NOMOR_NORMALIZE.sub("", value.lower()).strip()


def _words(value: str) -> list[str]:
    return [w for w in re.sub(r"[^a-zA-Z0-9\s/]", " ", value or "").split() if w]


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
    """True bila `abbr` adalah akronim/singkatan dari `full`.

    Robust vs OCR & urutan: huruf akronim harus muncul berurutan (subsequence)
    di huruf nama lengkap, dengan stopword di-skip. Sinyal huruf (bukan inisial
    kata) yang membedakan BEM FEB UNAIR vs BEM FKM UNAIR / BEM FEB UGM /
    BEM FEB UPNVJT (beda organisasi) — inisialnya identik, isi hurufnya beda.

    Rasio cakupan kata mencegah partial-string dipuji sebagai akronim
    (mis. "Himpunan Surabaya" dari nama 14 kata = BUKAN akronim, hanya
    potongan teks).
    """
    abbr_words = [w.lower() for w in _words(abbr) if w.lower() not in ABBR_STOPWORDS]
    full_words = [w.lower() for w in _words(full) if w.lower() not in ABBR_STOPWORDS]
    if len(abbr_words) < 2:
        return False
    if len(full_words) < 2 or len(abbr_words) / len(full_words) < 0.3:
        return False
    abbr_letters = "".join(abbr_words)
    full_letters = "".join(full_words)
    if not abbr_letters or len(full_letters) <= len(abbr_letters):
        return False
    # Akronim sejati jauh lebih pendek dari nama penuh (rasio huruf kecil).
    # Potongan OCR/parsial hampir sepanjang nama penuh (rasio ~0.7+) -> bukan akronim.
    if len(abbr_letters) / len(full_letters) > 0.6:
        return False
    # Parsial kontigu (kata abbr muncul berurutan sebagai substring full) =
    # containment, bukan akronim -> biarkan fuzzy/contains yang menangani.
    if " ".join(abbr_words) in " ".join(full_words):
        return False
    j = 0
    for c in full_letters:
        if j < len(abbr_letters) and c == abbr_letters[j]:
            j += 1
    return j >= len(abbr_letters)


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

    is_org_like = field_name in ("penyelenggara_kegiatan", "nama_kegiatan_sertifikasi")
    abbr = abbreviation_match(expected, actual) if is_org_like else False

    if is_org_like:
        # Threshold organizer dinaikkan 0.5 -> 0.75: overlap 0.67 terbukti false
        # positive (BEM FEB UNAIR vs BEM FKM UNAIR = 0.67 tapi beda org), sementara
        # overlap 0.75+ umumnya organizer yang benar. Akronim-valid menaikkan exact.
        fuzzy = contains or abbr or overlap >= 0.75
        if abbr:
            exact = True
    else:
        fuzzy = contains or overlap >= 0.5

    return {
        "exact": exact,
        "contains": contains,
        "token_overlap": overlap,
        "fuzzy": fuzzy,
        "wer": w,
        "cer": c,
    }
