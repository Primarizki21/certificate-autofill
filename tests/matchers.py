import re

from tests.date_normalizer import normalize_date

NOMOR_NORMALIZE = re.compile(r"[ .\-\t_]+")
TEXT_NORMALIZE = re.compile(r"[^a-z0-9/]+")
DEGREE_NORM = re.compile(r"\b([sd])\s*[-–—]?\s*([0-9])\b", re.IGNORECASE)
# Kata sambung/filler yang tidak memberi sinyal pembeda organisasi.
ABBR_STOPWORDS = {"dan", "dengan", "di", "yang", "of", "the", "for", "and", "de", "in", "pada", "part", "by"}

KNOWN_PORTMANTEAUS = {
    "unair": [["universitas", "airlangga"]],
    "unesa": [["universitas", "negeri", "surabaya"]],
    "unpad": [["universitas", "padjadjaran"]],
    "undip": [["universitas", "diponegoro"]],
    "uns": [["universitas", "sebelas", "maret"]],
    "ui": [["universitas", "indonesia"]],
    "itb": [["institut", "teknologi", "bandung"]],
    "its": [["institut", "teknologi", "sepuluh", "nopember"]],
    "ipb": [["institut", "pertanian", "bogor"]],
    "ugm": [["universitas", "gadjah", "mada"]],
    "usu": [["universitas", "sumatera", "utara"]],
    "unhas": [["universitas", "hasanuddin"]],
    "unand": [["universitas", "andalas"]],
    "kemendikbud": [["kementerian", "pendidikan", "kebudayaan"], ["kementerian", "pendidikan", "dan", "kebudayaan"]],
    "kemendikbudristek": [["kementerian", "pendidikan", "kebudayaan", "riset", "teknologi"], ["kementerian", "pendidikan", "kebudayaan", "riset", "dan", "teknologi"]],
    "kemenkes": [["kementerian", "kesehatan"]],
    "kemenkeu": [["kementerian", "keuangan"]],
    "kemenag": [["kementerian", "agama"]],
    "kemkominfo": [["kementerian", "komunikasi", "informatika"], ["kementerian", "komunikasi", "dan", "informatika"]],
    "kominfo": [["kementerian", "komunikasi", "informatika"], ["kementerian", "komunikasi", "dan", "informatika"]],
    "himasada": [["himpunan", "mahasiswa", "teknologi", "sains", "data"], ["himpunan", "mahasiswa", "sains", "data"]],
    "himatesda": [["himpunan", "mahasiswa", "teknik", "elektro", "rekayasa", "biomedis"], ["himpunan", "mahasiswa", "teknik", "elektro", "dan", "rekayasa", "biomedis"]],
    "himatektro": [["himpunan", "mahasiswa", "teknik", "elektro"]],
    "himatif": [["himpunan", "mahasiswa", "teknik", "informatika"]],
    "himatekk": [["himpunan", "mahasiswa", "teknik", "kimia"]],
    "himatek": [["himpunan", "mahasiswa", "teknik"]],
    "bappenas": [["badan", "perencanaan", "pembangunan", "nasional"]],
}

KNOWN_ACRONYM_SEGMENTS = {
    "bem": ["badan", "eksekutif", "mahasiswa"],
    "dpm": ["dewan", "perwakilan", "mahasiswa"],
    "mpm": ["majelis", "permusyawaratan", "mahasiswa"],
    "hima": ["himpunan", "mahasiswa"],
    "ftmm": ["fakultas", "teknologi", "maju", "multidisiplin"],
    "feb": ["fakultas", "ekonomi", "bisnis"],
    "fkm": ["fakultas", "kesehatan", "masyarakat"],
    "fst": ["fakultas", "sains", "teknologi"],
    "fk": ["fakultas", "kedokteran"],
    "fkg": ["fakultas", "kedokteran", "gigi"],
    "fpk": ["fakultas", "perikanan", "kelautan"],
    "ff": ["fakultas", "farmasi"],
    "fib": ["fakultas", "ilmu", "budaya"],
    "fisip": ["fakultas", "ilmu", "sosial", "ilmu", "politik"],
    "fh": ["fakultas", "hukum"],
    "fpsi": ["fakultas", "psikologi"],
    "fkh": ["fakultas", "kedokteran", "hewan"],
    "fkes": ["fakultas", "kesehatan"],
    "pasca": ["sekolah", "pascasarjana"],
}

def normalize_value(value: str) -> str:
    v = DEGREE_NORM.sub(r"\1\2", (value or "").lower())
    return TEXT_NORMALIZE.sub(" ", v).strip()

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


def is_initialism_of(abbr: str, full: str) -> bool:
    """True bila `abbr` adalah inisial/akronim berbasis huruf depan kata pada `full`."""
    abbr_words = [w.lower() for w in _words(abbr) if w.lower() not in ABBR_STOPWORDS]
    full_words = [w.lower() for w in _words(full) if w.lower() not in ABBR_STOPWORDS]
    if not abbr_words or not full_words:
        return False

    abbr_letters = "".join(abbr_words)
    full_initials = "".join(w[0] for w in full_words)

    if abbr_letters == full_initials:
        return True

    if len(abbr_letters) >= 2 and full_initials.startswith(abbr_letters):
        if len(abbr_letters) / len(full_initials) >= 0.5:
            return True

    expanded_abbr_options = [[]]
    has_known_expansion = False
    for aw in abbr_words:
        if aw in KNOWN_ACRONYM_SEGMENTS:
            has_known_expansion = True
            seg = KNOWN_ACRONYM_SEGMENTS[aw]
            expanded_abbr_options = [opt + seg for opt in expanded_abbr_options]
        elif aw in KNOWN_PORTMANTEAUS:
            has_known_expansion = True
            new_opts = []
            for opt in expanded_abbr_options:
                for variant in KNOWN_PORTMANTEAUS[aw]:
                    var_filtered = [w for w in variant if w not in ABBR_STOPWORDS]
                    new_opts.append(opt + var_filtered)
            expanded_abbr_options = new_opts
        else:
            expanded_abbr_options = [opt + [aw] for opt in expanded_abbr_options]

    if has_known_expansion:
        for opt in expanded_abbr_options:
            if opt == full_words:
                return True
            if len(opt) >= 2 and " ".join(opt) in " ".join(full_words):
                return True
            if len(full_words) >= 2 and " ".join(full_words) in " ".join(opt):
                return True

    return False


def is_portmanteau_of(abbr: str, full: str) -> bool:
    """True bila `abbr` adalah portmanteau yang terdaftar atau berbasis silabel."""
    abbr_w = [w.lower() for w in _words(abbr) if w.lower() not in ABBR_STOPWORDS]
    full_w = [w.lower() for w in _words(full) if w.lower() not in ABBR_STOPWORDS]
    if not abbr_w or not full_w:
        return False

    abbr_str = "".join(abbr_w)
    if abbr_str in KNOWN_PORTMANTEAUS:
        for expected_full in KNOWN_PORTMANTEAUS[abbr_str]:
            exp_filtered = [w for w in expected_full if w not in ABBR_STOPWORDS]
            if exp_filtered == full_w or " ".join(exp_filtered) in " ".join(full_w):
                return True

    return False


def is_abbreviation_of(abbr: str, full: str) -> bool:
    """True bila `abbr` adalah akronim/singkatan dari `full`."""
    if is_initialism_of(abbr, full):
        return True
    if is_portmanteau_of(abbr, full):
        return True

    abbr_words = [w.lower() for w in _words(abbr) if w.lower() not in ABBR_STOPWORDS]
    full_words = [w.lower() for w in _words(full) if w.lower() not in ABBR_STOPWORDS]
    if len(abbr_words) < 2 or len(full_words) < 2:
        return False
    if len(abbr_words) / len(full_words) < 0.3:
        return False
    abbr_letters = "".join(abbr_words)
    full_letters = "".join(full_words)
    if not abbr_letters or len(full_letters) <= len(abbr_letters):
        return False
    if len(abbr_letters) / len(full_letters) > 0.6:
        return False
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
