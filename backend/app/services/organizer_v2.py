"""Phrase-anchored organizer extractor v2 (v7 P1) — port ke produksi.

Fixes the three failure modes found in the v6 taxonomy:
  1. Phrase patterns require exact spaces -> OCR-merged "diselenggarakanoleh"
     and "pada tanggal26" defeat the current regex.
  2. Signer lines ("Ketua BEM FKM UNAIR", "Dekan") and NIM/NIP identity lines
     are captured as organizer.
  3. Bare institution ("UNIVERSITAS AIRLANGGA") wins over the specific org.

Design: phrase-anchored candidate + org-keyword line candidates, scored, with
a small versioned map that un-merges known OCR-mangled org names.

Experiment only — production field_extractor.py stays untouched until the
ship gate. Import is guarded in benchmark_llm_v4 (organizer_variant='phrase_v2').
"""

import re

# Versioned expansion map for OCR-mangled org names (non-alnum-compacted key).
# All-caps merged runs can't be split by CamelCase, so map them explicitly.
OCR_ORG_MAP = {
    "BADANEKSEKUTIFMAHASISWA": "Badan Eksekutif Mahasiswa",
    "UNIVERSITASAIRLANGGA": "Universitas Airlangga",
    "UNIVERSITASAIRLANCCA": "Universitas Airlangga",
    "FAKULTASTEKNOLOGIMAJUDANMULTIDISIPLIN": "Fakultas Teknologi Maju dan Multidisiplin",
    "FAKULTASTEKONOMIDANBISNIS": "Fakultas Ekonomi dan Bisnis",
    "FACULTYOFSCIENCEANDTECHNOLOGY": "Faculty of Science and Technology",
    "BEMFTMM": "BEM FTMM",
    "BEMFEBUNAIR": "BEM FEB UNAIR",
    "BEMFKMUNAIR": "BEM FKM UNAIR",
    "BEMFSTUNAIR": "BEM FST UNAIR",
    "HIMPUNANMAHASISWATEKNOLOGISAINSDATA": "Himpunan Mahasiswa Teknologi Sains Data",
    "DEPARTEMENKAJIANDANAKSISTRATEGIS": "Departemen Kajian dan Aksi Strategis",
    "UNIVERSITASNEGERISURABAYA": "Universitas Negeri Surabaya",
    "UNIVERSITASBRAWIJAYA": "Universitas Brawijaya",
    "UNIVERSITASGADJAHMADA": "Universitas Gadjah Mada",
    "UNIVERSITASISLAMBANDUNG": "Universitas Islam Bandung",
    "UNIVERSITASSRIWIJAYA": "Universitas Sriwijaya",
    "HIMASTAT": "Himastat",
    "HIMASADA": "Himasada",
    "HIMATESDA": "Himatesda",
}

# Org keyword => specificity score (higher = more specific than institution).
ORG_KEYWORDS = {
    "BEM": 6, "BADAN EKSEKUTIF": 6, "HIMA": 6, "HIMPUNAN": 5, "UKM": 5,
    "UNIT KEGIATAN": 5, "DEPARTMENT": 5, "DEPT": 5, "STUDY PROGRAM": 5,
    "PROGRAM STUDI": 4, "PRODI": 4, "DEPARTEMEN": 4, "FAKULTAS": 3,
    "FACULTY": 3, "SCHOOL OF": 4, "DIREKTORAT": 3, "REKTORAT": 3,
    "KEMAHASISWAAN": 3, "SENAT": 3, "LEMBAGA": 3, "AIESEC": 5,
    "UNIVERSITAS": 1, "UNIVERSITY": 1,
}
SIGNER_ROLES = [
    "KETUA PELAKSANA", "KETUA", "PRESIDEN", "DEKAN", "WAKIL DEKAN",
    "DIREKTUR", "WAKIL DIREKTUR", "REKTOR", "PEMBINA", "SEKERTARIS",
    "SEKRETARIS", "BENDAHARA", "KEPALA", "A.N",
]
ACRONYMS = {
    "BEM", "HIMA", "UKM", "UNAIR", "FTMM", "FKM", "FEB", "FST", "AIESEC",
    "APHSA", "IRIS", "ITS", "IPB", "USU", "UNIMUS", "FORKAS", "STAN",
    "SMA", "SMP", "DIES", "PNJ",
}

PHRASE_PATTERN = re.compile(
    r"(?:yang\s*)?(?:diselenggarakan\s*oleh|diadakan\s*oleh|"
    r"dilaksanakan\s*oleh|organized\s*by|organised\s*by|held\s*by|"
    r"presented\s*by)\s*(.+?)(?="
    r"pada\s*tanggal|\btanggal\s*\d|\bon\s+\d{1,2}\b|\bpada\s+\d{1,2}\s+[A-Z]|"
    r"\bSurabaya\s*,|\bYogyakarta\s*,|\bBandung\s*,|\bJakarta\s*,|\n\s*\n|$)",
    re.IGNORECASE | re.DOTALL,
)
_CERTNUM_RE = re.compile(r"^\s*\d{1,4}\s*[/\\]", )
CERT_ORG_RE = re.compile(r"(BEM|HIMA|HIMPUNAN|UKM)\s*[-]?\s*([A-Z]{2,4})?\s*(?:[-/]\s*)?(UNAIR|UNIVERSITAS\s+AIRLANGGA)?", re.IGNORECASE)


def _compact(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _preprocess(text: str) -> str:
    """Repair common OCR word merges so phrase/date regexes can see boundaries.

    - Lowercase function word glued to an uppercase word: 'diselenggarakanolehX'.
    - CamelCase merges: 'DepartemenKajian', 'FakultasEkonomi', 'UniversitasAirlangga'.
    - 'tanggal26' date merge.
    """
    t = re.sub(r"oleh(?=[A-Z])", "oleh ", text)
    t = re.sub(r"tanggal(?=\d)", "tanggal ", t)
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    return t


def _expand_ocr(text: str) -> str:
    for key, val in OCR_ORG_MAP.items():
        if _compact(text) == key:
            return val
    return text


def _titleize(value: str) -> str:
    words = []
    for w in re.split(r"\s+", value.strip()):
        if not w:
            continue
        up = _compact(w)
        if up in ACRONYMS or w.isupper():
            words.append(up)
        elif w.islower() and len(w) <= 3:
            words.append(w.lower())
        else:
            words.append(w[:1].upper() + w[1:].lower())
    return " ".join(words)


def _clean(value: str) -> str:
    v = re.sub(r"\s+", " ", value or "").strip(" .,:;-")
    # Drop trailing dates, NIM/NIP tokens, signer-role suffixes.
    v = re.sub(r"\bpada\s*tanggal\s+.+$", "", v, flags=re.IGNORECASE).strip()
    v = re.sub(r"\b(Surabaya|Yogyakarta|Jakarta|Bandung)\s*,\s*\d.*$", "", v, flags=re.IGNORECASE).strip()
    v = re.sub(r"\b(NIM|NIP|NIK)\s*[.:]?\s*[\d\s]+.*$", "", v, flags=re.IGNORECASE).strip()
    v = re.sub(r"\b\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{2,4}\b.*$", "", v).strip()
    v = re.sub(r"^\s*"+ "|".join(re.escape(r) for r in SIGNER_ROLES) + r"\b\s*", "", v, flags=re.IGNORECASE).strip()
    # If we stripped a role prefix, the remainder is the org.
    v = re.sub(r"^\s*(" + "|".join(re.escape(r) for r in SIGNER_ROLES) + r")\s+", "", v, flags=re.IGNORECASE).strip()
    v = re.sub(r"^\s*oleh\s+", "", v, flags=re.IGNORECASE).strip()
    v = re.sub(r"\s+", " ", v).strip(" .,:;-")
    return v


def _org_keyword_score(text: str) -> int:
    upper = text.upper()
    best = 0
    for kw, score in ORG_KEYWORDS.items():
        if kw in upper and score > best:
            best = score
    return best


def _has_sign_penalty(text: str) -> bool:
    upper = text.upper()
    if any(r in upper for r in SIGNER_ROLES):
        return True
    if re.search(r"\b(NIM|NIP|NIK)\s*[.:]?\s*\d", upper):
        return True
    return False


def _phrase_candidates(text: str) -> list[str]:
    out = []
    for m in PHRASE_PATTERN.finditer(text):
        raw = m.group(1).strip()
        expanded = _expand_ocr(raw)
        cleaned = _clean(expanded)
        if cleaned and len(cleaned) >= 3:
            out.append(cleaned)
    return out


def _line_candidates(text: str) -> list[str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    faculty_line = ""
    for line in lines:
        if _CERTNUM_RE.match(line):
            continue
        if not _org_keyword_score(line):
            continue
        if _has_sign_penalty(line):
            cleaned = _clean(line)
            if _org_keyword_score(cleaned) >= 4 and cleaned != line:
                if "FACULTY" in line.upper():
                    faculty_line = cleaned
                yield cleaned
            continue
        expanded = _expand_ocr(line)
        # English faculty + dept join: prefer "Faculty ... Dept." combined.
        if "DEPT" in expanded.upper() or "STUDY PROGRAM" in expanded.upper() or "STUDYPROGRAMME" in expanded.upper():
            yield expanded
            continue
        if "FACULTY" in expanded.upper() or "SCHOOL OF" in expanded.upper():
            faculty_line = expanded
            continue
        yield expanded
    if faculty_line:
        yield faculty_line


def _join_english_candidates(candidates: list[tuple[float, str]], lines: list[str], text: str) -> None:
    """Faculty line + nearby DEPT line -> one candidate (matches curated GT)."""
    dept_idx = -1
    fac_idx = -1
    for i, line in enumerate(lines):
        upper = line.upper()
        if not _CERTNUM_RE.match(line):
            if "DEPT" in upper or "STUDY PROGRAM" in upper or "STUDYPROGRAMME" in upper:
                dept_idx = i
            elif ("FACULTY" in upper or "SCHOOL OF" in upper) and not _has_sign_penalty(line):
                fac_idx = i
    if dept_idx >= 0 and fac_idx >= 0 and abs(dept_idx - fac_idx) <= 4:
        dept = _expand_ocr(lines[dept_idx])
        fac = _expand_ocr(lines[fac_idx])
        joined = f"{fac} {dept}"
        if _org_keyword_score(joined) >= 3:
            candidates.append((_score_candidate(joined, 0, text), joined))


def _score_candidate(cand: str, phrase_idx: int, text: str) -> float:
    upper = cand.upper()
    score = 0.0
    score += _org_keyword_score(cand) * 2.0
    if phrase_idx >= 0:
        score += 6.0 - min(phrase_idx, 3)
    if re.search(r"\bUNIVERSITAS\b|\bUNIVERSITY\b", upper) and _org_keyword_score(cand) <= 1:
        score -= 2.5
    if re.search(r"\b(NIM|NIP|NIK)\b", upper):
        score -= 5.0
    if _has_sign_penalty(cand):
        score -= 3.0
    if len(re.findall(r"[a-z]", cand)) == 0:
        score -= 1.5
    return score


def extract_organizer_v2(text: str) -> str | None:
    if not text or not text.strip():
        return None
    text = _preprocess(text)
    candidates: list[tuple[float, str]] = []

    phrases = _phrase_candidates(text)
    for i, p in enumerate(phrases):
        candidates.append((_score_candidate(p, i, text), p))

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in _line_candidates(text):
        candidates.append((_score_candidate(line, -1, text), line))
    _join_english_candidates(candidates, lines, text)

    if not candidates:
        return None

    scored = sorted(candidates, key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    if best_score <= 0:
        return None
    return _titleize(best)[:300]


# ---------------------------------------------------------------------------
# Self-check on the four v6 taxonomy failure cases.
# ---------------------------------------------------------------------------

_SAMPLES = {
    "1930354": """SERTIFIKAT
Diberikan Kepada: Raafa Agna Rasyada
Atas partisipasinya sebagai : Peserta Campaign
Dalam memperingati Hari Anak Nasional yang diselenggarakan
oleh Social Action pada tanggal 25-27 Juli 2023
542/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023
""",
    "1963507": """SERTIFIKAT
212/E/BEM-FKM/UNAIR/X/2023
dalam kegiatan Mawacana yang diselenggarakan pada tanggal 28 Oktober 2023.
PESERTA
Ketua BEM FKM UNAIR
2023
""",
    "1981676": """SERTIFIKAT
PESERTA
Diberikankepada: Raafa Agna Rasyada
Dalam acara Bincang Santai Intelektual 2
yang diselenggarakanolehDepartemenKajian danAksi Strategis
Badan Eksekutif Mahasiswa FakultasEkonomi dan Bisnis UniversitasAirlangga
pada tanggal26November2023
""",
    "2030325": """SERTIFIKAT
Universitas Airlangga
Raafa Agna Rasyada
164231043
UKM Tari dan Karawitan
Magang UKM Universitas Airlangga
Tahun Akademik 2023 / 2024
Surabaya, 27 Desember 2023
""",
    "bem_ftmm": """SERTIFIKAT
No.3994/B/UN3.FTMM/KM.04/2024
SEBAGAI JUARA II VISUAL QUEST
Dalam kegiatan Dataquest 3.0
yang diselenggarakan oleh BEM FTMM dengan Himpunan Mahasiswa Teknologi Sains Data
Fakultas Teknologi Maju dan Multidisiplin Universitas Airlangga
Surabaya, 24 Agustus - 22 September 2024
""",
    "faculty_dept": """Ananda Aqeel Fathur Rahman
UNIVERSITASAIRLANGGA
FACULTYOFSCIENCEANDTECHNOLOGY
INFORMATION SYSTEMS DEPT.
CERTIFICATE of appreciation : Ananda Ageel Fathur Rahman
as Participant
in the online seminar
on 17 November 2023
""",
}


def _demo():
    for name, text in _SAMPLES.items():
        org = extract_organizer_v2(text)
        print(f"[{name}] {org}")

    o = extract_organizer_v2(_SAMPLES["1981676"])
    assert o and "Departemen Kajian dan Aksi Strategis" in o, o
    assert "NIP" not in o and "NIM" not in o
    o2 = extract_organizer_v2(_SAMPLES["2030325"])
    assert o2 and "UKM" in o2 and "164231043" not in o2, o2
    o3 = extract_organizer_v2(_SAMPLES["1963507"])
    assert o3 and "BEM FKM UNAIR" in o3, o3
    o4 = extract_organizer_v2(_SAMPLES["bem_ftmm"])
    assert o4 and "BEM FTMM" in o4, o4
    o5 = extract_organizer_v2(_SAMPLES["faculty_dept"])
    assert o5 and ("DEPT" in o5.upper() or "Faculty" in o5 or "Systems" in o5), o5
    print("ok: organizer_extractor_v2")


if __name__ == "__main__":
    _demo()
