from dataclasses import dataclass
import re
import unicodedata

MONTHS_ID = {
    "JANUARI": "01",
    "FEBRUARI": "02",
    "MARET": "03",
    "APRIL": "04",
    "MEI": "05",
    "JUNI": "06",
    "JULI": "07",
    "AGUSTUS": "08",
    "SEPTEMBER": "09",
    "OKTOBER": "10",
    "NOVEMBER": "11",
    "DESEMBER": "12",
}

MONTHS_EN = {
    "JANUARY": "01",
    "FEBRUARY": "02",
    "MARCH": "03",
    "APRIL": "04",
    "MAY": "05",
    "JUNE": "06",
    "JULY": "07",
    "AUGUST": "08",
    "SEPTEMBER": "09",
    "OCTOBER": "10",
    "NOVEMBER": "11",
    "DECEMBER": "12",
}

# Alias untuk OCR yang sering keliru membaca huruf bulan.
MONTH_ALIASES = {
    **{k: k for k in MONTHS_ID},
    **{k: k for k in MONTHS_EN},
    "JAN": "JANUARY",
    "FEB": "FEBRUARY",
    "MAR": "MARCH",
    "APR": "APRIL",
    "AUG": "AUGUST",
    "SEP": "SEPTEMBER",
    "SEPT": "SEPTEMBER",
    "OCT": "OCTOBER",
    "NOV": "NOVEMBER",
    "DEC": "DECEMBER",
    "AGUSTU5": "AGUSTUS",
    "A6USTUS": "AGUSTUS",
    "AGU5TUS": "AGUSTUS",
    "AGUSTWS": "AGUSTUS",
    "SEPTEM8ER": "SEPTEMBER",
    "SEPTEMEER": "SEPTEMBER",
    "SEPTEMRER": "SEPTEMBER",
    "SEPTEMBFR": "SEPTEMBER",
    "DESEM8ER": "DESEMBER",
    "OKTO8ER": "OKTOBER",
}

MONTH_NUMBERS = {**MONTHS_ID, **MONTHS_EN}


@dataclass
class ExtractedValue:
    value: str | None
    confidence: float
    source: str


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00a0", " ")
    text = text.replace("—", "-").replace("–", "-")
    # OCR kadang menempelkan kata dan angka: December7,2024 / fromSeptember.
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    text = re.sub(r"(?<=,)(?=\d{4})", " ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def extract_certificate_fields(raw_text: str) -> dict[str, ExtractedValue]:
    text = normalize_text(raw_text)
    upper = text.upper()

    start_date, end_date, date_conf = extract_dates(text)
    role = extract_role(text)
    activity_name = extract_activity_name(text)
    certificate_number = extract_certificate_number(text)
    organizer = extract_organizer(text)

    return {
        "raw_role": ExtractedValue(role, 0.92 if role else 0.0, "regex_role"),
        "nama_kegiatan_sertifikasi": ExtractedValue(activity_name, 0.86 if activity_name else 0.0, "regex_activity"),
        "waktu_mulai_pelaksanaan": ExtractedValue(start_date, date_conf, "regex_date"),
        "waktu_selesai_pelaksanaan": ExtractedValue(end_date, date_conf, "regex_date"),
        "penyelenggara_kegiatan": ExtractedValue(organizer, 0.84 if organizer else 0.0, "regex_organizer"),
        "nomor_bukti_fisik_nomor_sertifikasi": ExtractedValue(
            certificate_number, 0.95 if certificate_number else 0.0, "regex_certificate_number"
        ),
        "has_kegiatan_keyword": ExtractedValue("true" if "KEGIATAN" in upper else "false", 0.99, "keyword"),
        "has_dekan_keyword": ExtractedValue("true" if ("DEKAN" in upper or "DEAN" in upper) else "false", 0.99, "keyword"),
        "has_direktur_kemahasiswaan_keyword": ExtractedValue(
            "true" if "DIREKTUR KEMAHASISWAAN" in upper else "false", 0.99, "keyword"
        ),
        "full_text": ExtractedValue(text, 1.0, "pipeline"),
    }


def extract_certificate_number(text: str) -> str | None:
    patterns = [
        r"(?:NO\.?|NOMOR|NUMBER)\s*[:\-]?\s*([0-9]{2,6}\s*/\s*[A-Z0-9][A-Z0-9.\-/ ]+?/?\s*[0-9]{4})",
        r"\b([0-9]{2,6}\s*/\s*[A-Z]\s*/\s*UN[0-9A-Z.\-/ ]+?/?\s*[0-9]{4})\b",
        r"\b([0-9]{2,6}\s*/\s*[A-Z0-9.\-/]+\s*/\s*[0-9]{4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = re.sub(r"\s+", "", match.group(1))
            return value.strip(" .,:;-")
    return None


def extract_role(text: str) -> str | None:
    upper = text.upper()

    english_patterns = [
        r"\bas\s+a\s+([A-Za-z][A-Za-z\s/\-]{2,80})",
        r"\bas\s+([A-Za-z][A-Za-z\s/\-]{2,80})",
        r"\bOF\s+PARTICIPATION\b",
        r"\bPARTICIPATION\b",
    ]
    for pattern in english_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            if "PARTICIPATION" in pattern:
                return "Peserta"
            role = clean_inline_phrase(match.group(1))
            role_upper = role.upper()
            if "COMMITTEE" in role_upper:
                return "Panitia"
            if "PARTICIPANT" in role_upper:
                return "Peserta"
            if "MINISTER" in role_upper or "MENTERI" in role_upper:
                return "Menteri"
            if role:
                return title_keep_acronym(role)

    patterns = [
        r"\bSEBAGAI\s*:?\s*\n?\s*([A-Z][A-Z\s/\-]{2,80})",
        r"\bsebagai\s*:?\s*\n?\s*([A-Za-z][A-Za-z\s/\-]{2,80})",
        r"Atas\s+Partisipasinya\s+sebagai\s*:?\s*\n?\s*([A-Za-z][A-Za-z\s/\-]{2,80})",
    ]
    stop_words = ["DALAM", "ATAS", "PENGENALAN", "UNIVERSITAS", "SURABAYA", "MASA", "PADA", "WHICH"]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            role = clean_inline_phrase(match.group(1))
            for stop in stop_words:
                idx = role.upper().find(stop)
                if idx > 0:
                    role = role[:idx].strip()
            if 2 <= len(role) <= 80:
                if "COMMITTEE" in role.upper():
                    return "Panitia"
                return title_keep_acronym(role)
    for keyword in ["PANITIA", "PESERTA", "MENTERI", "KETUA", "SEKRETARIS", "ANGGOTA"]:
        if keyword in upper:
            return title_keep_acronym(keyword)
    return None


def extract_activity_name(text: str) -> str | None:
    upper = text.upper()
    patterns = [
        r"seminar\s+(.+?)\s+yang\s+diselenggarakan",
        r"talkshow\s+(.+?)\s+dengan\s+tema",
        r"kegiatan\s+(.+?)\s+yang\s+diselenggarakan",
        r"KEGIATAN\s+(.+?)\s+YANG\s+DISELENGGARAKAN",
        r"Dalam\s+kegiatan\s+(.+?)\s+pada\s+tanggal",
        r"\bat\s+([A-Za-z0-9][A-Za-z0-9 .&\-]{2,80})\s+which\s+held",
        r"\bat\s+([A-Za-z0-9][A-Za-z0-9 .&\-]{2,80})\s+which\s+was\s+held",
        r"PENGENALAN\s+KEHIDUPAN\s+KAMPUS\s+BAGI\s+MAHASISWA\s+BARU\s*\((PKKMB)\)",
        r"Kepengurusan\s+(.+?)\s+Masa\s+Bakti",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(0 if "PENGENALAN" in pattern else 1)
            value = " ".join(value.split())
            if value.upper() == "PKKMB":
                return "Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB)"
            # Untuk seminar Brief, ambil nama sebelum judul kutipan yang panjang.
            value = re.split(r"[“\"]", value)[0].strip()
            value = re.sub(r"\s+dengan\s+tema.*$", "", value, flags=re.IGNORECASE).strip()
            value = clean_inline_phrase(value)
            if pattern.lower().startswith("talkshow") and value and not value.upper().startswith("TALKSHOW"):
                value = "Talkshow " + value
            if value:
                return title_keep_acronym(value)
    keyword_patterns = [
        ("AIRNOLOGY", r"Airnology\s*[0-9.]*"),
        ("KAKIWIMA", r"(?:Talkshow\s+)?Kakiwima"),
        ("SPECTA", r"SPECTA"),
        ("BRIEF", r"Brief\s*[0-9]{4}"),
    ]
    for keyword, pattern in keyword_patterns:
        if keyword in upper:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return title_keep_acronym(match.group(0).strip())
    if "PKKMB" in upper:
        return "Pengenalan Kehidupan Kampus bagi Mahasiswa Baru (PKKMB)"
    return None


def extract_organizer(text: str) -> str | None:
    clean_text = normalize_text(text)
    direct_patterns = [
        r"diselenggarakan\s+oleh\s+(.+?)(?:\s+pada\s+tanggal|\s+pada\s+\d|\s+tanggal\s+\d|\n|$)",
        r"yang\s+diselenggarakan\s+oleh\s+(.+?)(?:\s+pada\s+tanggal|\s+pada\s+\d|\s+tanggal\s+\d|\n|$)",
        r"\bby\s+([A-Za-z][A-Za-z0-9 .&\-]{2,80})(?:\n|$)",
    ]
    for pattern in direct_patterns:
        match = re.search(pattern, clean_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            value = clean_organizer(match.group(1))
            if value:
                return value

    # Fallback khusus organisasi yang umum muncul di sertifikat FTMM.
    upper = clean_text.upper()
    known_orgs = [
        "HIMATESDA",
        "HIMANO",
        "BEM FTMM",
        "BADAN EKSEKUTIF MAHASISWA",
        "HIMPUNAN MAHASISWA",
        "UNIVERSITAS AIRLANGGA",
        "DIREKTORAT KEMAHASISWAAN",
    ]
    for org in known_orgs:
        if org in upper:
            if org == "BADAN EKSEKUTIF MAHASISWA":
                return "Badan Eksekutif Mahasiswa FTMM Universitas Airlangga"
            if org == "HIMPUNAN MAHASISWA":
                return "Himpunan Mahasiswa FTMM Universitas Airlangga"
            return title_keep_acronym(org)

    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    candidates = []
    for line in lines:
        upper_line = line.upper()
        if any(k in upper_line for k in ["UNIVERSITAS", "BEM", "HIMA", "FAKULTAS", "DIREKTORAT", "KEMENTERIAN", "PT "]):
            if not upper_line.startswith(("SERTIFIKAT", "NO", "NOMOR", "NUMBER")):
                candidates.append(line)
    if candidates:
        best = max(candidates, key=len)
        return clean_organizer(best)[:300]
    return None


def clean_organizer(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" .,:;-")
    value = re.sub(r"^(which\s+held\s+from\s+.+?\s+by\s+)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bfrom\s+.+?\s+to\s+.+?\s+by\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bpada\s+tanggal\s+.+$", "", value, flags=re.IGNORECASE).strip(" .,:;-")
    value = re.sub(r"\bwhich\s+held\s+from\s+.+$", "", value, flags=re.IGNORECASE).strip(" .,:;-")
    value = re.sub(r"\bwhich\s+was\s+held\s+from\s+.+$", "", value, flags=re.IGNORECASE).strip(" .,:;-")
    if not value:
        return ""
    known_upper = {"HIMATESDA", "HIMANO", "BEM FTMM", "UNAIR", "FTMM"}
    compact_upper = re.sub(r"[^A-Z0-9]", "", value.upper())
    for org in known_upper:
        if compact_upper == re.sub(r"[^A-Z0-9]", "", org):
            return org
    return title_keep_acronym(value)


def extract_dates(text: str) -> tuple[str | None, str | None, float]:
    upper = normalize_for_date(text)

    # 1) Format numerik: 24/08/2024 - 22/09/2024 atau 24-08-2024 s.d. 22-09-2024
    numeric_interval = re.search(
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*(?:-|S/D|SD|SAMPAI|S\.D\.|TO)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        upper,
        flags=re.IGNORECASE,
    )
    if numeric_interval:
        d1, m1, y1, d2, m2, y2 = numeric_interval.groups()
        return f"{int(d1):02d}/{int(m1):02d}/{y1}", f"{int(d2):02d}/{int(m2):02d}/{y2}", 0.95

    # 2) English month-first interval: September 21 to December 7, 2024.
    english_interval = re.search(
        r"([A-Z]{3,20})\s+(\d{1,2})(?:,\s*(\d{4}))?\s*(?:-|TO|UNTIL|S/D|SD|SAMPAI)\s*([A-Z]{3,20})\s+(\d{1,2})(?:,?\s*(\d{4}))",
        upper,
        flags=re.IGNORECASE,
    )
    if english_interval:
        m1, d1, y1, m2, d2, y2 = english_interval.groups()
        year = y1 or y2
        start_value = to_ddmmyyyy(d1, m1, year)
        end_value = to_ddmmyyyy(d2, m2, y2 or year)
        if start_value and end_value:
            return start_value, end_value, 0.95

    numeric_single = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", upper)
    if numeric_single:
        d, m, y = numeric_single.groups()
        value = f"{int(d):02d}/{int(m):02d}/{y}"
        return value, value, 0.80

    # 3) Pattern khusus: 18 - 27 Agustus 2022.
    same_month = re.search(
        r"(\d{1,2})\s*(?:-|S/D|SD|SAMPAI|S\.D\.|TO)\s*(\d{1,2})\s+([A-Z0-9]{3,20})\s+(\d{4})",
        upper,
        flags=re.IGNORECASE,
    )
    if same_month:
        d1, d2, month, year = same_month.groups()
        year = re.sub(r"\D", "", year)
        start_value = to_ddmmyyyy(d1, month, year)
        end_value = to_ddmmyyyy(d2, month, year)
        if start_value and end_value:
            return start_value, end_value, 0.95

    # 4) Scanner token tanggal ID/EN.
    date_tokens = scan_date_tokens(upper)
    if len(date_tokens) >= 2:
        best_pair = choose_best_date_pair(upper, date_tokens)
        if best_pair:
            first, second = best_pair
            year = first["year"] or second["year"]
            if year:
                start_value = token_to_ddmmyyyy(first, year)
                end_value = token_to_ddmmyyyy(second, second["year"] or year)
                if start_value and end_value:
                    return start_value, end_value, 0.94

    # 5) Jika hanya satu tanggal, isi mulai dan selesai dengan tanggal yang sama.
    for token in date_tokens:
        if token["year"]:
            value = token_to_ddmmyyyy(token, token["year"])
            if value:
                return value, value, 0.80

    return None, None, 0.0


def scan_date_tokens(upper_text: str) -> list[dict[str, str | int | None]]:
    tokens: list[dict[str, str | int | None]] = []

    # Day-first: 23 NOVEMBER 2024 / 24 AGUSTUS.
    day_first = re.compile(r"\b(\d{1,2})\s+([A-Z0-9]{3,20})\s*(\d{4})?\b", flags=re.IGNORECASE)
    for match in day_first.finditer(upper_text):
        day, month_raw, year = match.groups()
        add_date_token(tokens, day, month_raw, year, match.start(), match.end(), order="day_first")

    # Month-first: SEPTEMBER 21 / DECEMBER 7, 2024 / NOVEMBER 23 2024.
    month_first = re.compile(r"\b([A-Z0-9]{3,20})\s+(\d{1,2})(?:,?\s*(\d{4}))?\b", flags=re.IGNORECASE)
    for match in month_first.finditer(upper_text):
        month_raw, day, year = match.groups()
        add_date_token(tokens, day, month_raw, year, match.start(), match.end(), order="month_first")

    # Buang token month-first palsu yang muncul karena teks day-first tanpa tanda hubung,
    # misalnya "24 AGUSTUS 22 SEPTEMBER 2024" dapat salah terbaca sebagai "AGUSTUS 22".
    day_first_spans = [
        (int(t["start"] or 0), int(t["end"] or 0))
        for t in tokens
        if t.get("order") == "day_first"
    ]
    filtered = []
    for token in tokens:
        start = int(token["start"] or 0)
        if token.get("order") == "month_first" and any(span_start <= start < span_end for span_start, span_end in day_first_spans):
            continue
        filtered.append(token)

    # Deduplicate berdasarkan posisi dan nilai.
    unique = []
    seen = set()
    for token in sorted(filtered, key=lambda x: int(x["start"] or 0)):
        key = (token["day"], token["month"], token["year"], token["start"])
        if key not in seen:
            seen.add(key)
            unique.append(token)
    return unique


def add_date_token(tokens: list, day: str, month_raw: str, year: str | None, start: int, end: int, order: str) -> None:
    canonical_month = normalize_month(month_raw)
    if not canonical_month:
        return
    day_int = int(day)
    if not (1 <= day_int <= 31):
        return
    tokens.append(
        {
            "day": str(day_int),
            "month": canonical_month,
            "year": year,
            "start": start,
            "end": end,
            "order": order,
        }
    )


def choose_best_date_pair(upper_text: str, tokens: list[dict[str, str | int | None]]) -> tuple[dict, dict] | None:
    context_keywords = ["SURABAYA", "DILAKSANAKAN", "PELAKSANAAN", "PADA", "TANGGAL", "HELD", "FROM", "TO", "MASA"]
    best_score = -10**9
    best_pair = None

    for i in range(len(tokens) - 1):
        first = tokens[i]
        second = tokens[i + 1]
        first_start = int(first["start"] or 0)
        second_end = int(second["end"] or 0)
        gap_text = upper_text[int(first["end"] or 0): int(second["start"] or 0)]
        window_start = max(0, first_start - 90)
        window_end = min(len(upper_text), second_end + 60)
        window = upper_text[window_start:window_end]

        distance = int(second["start"] or 0) - int(first["end"] or 0)
        if distance > 90:
            continue

        has_year = bool(first.get("year") or second.get("year"))
        if not has_year:
            continue

        score = 100 - distance
        if re.search(r"-|S/D|SD|SAMPAI|S\.D\.|TO|UNTIL", gap_text):
            score += 50
        if any(keyword in window for keyword in context_keywords):
            score += 25
        if "NIP" in window or "NIM" in window or "NIK" in window:
            score -= 35

        if score > best_score:
            best_score = score
            best_pair = (first, second)

    return best_pair


def normalize_for_date(text: str) -> str:
    upper = normalize_text(text).upper()
    upper = upper.replace("—", "-").replace("–", "-")
    upper = re.sub(r"(?<=[A-Z])(?=\d)", " ", upper)
    upper = re.sub(r"(?<=\d)(?=[A-Z])", " ", upper)
    upper = re.sub(r"(?<=,)(?=\d{4})", " ", upper)
    upper = re.sub(r"\s+", " ", upper)
    return upper


def normalize_month(month_name: str) -> str | None:
    clean = re.sub(r"[^A-Z0-9]", "", month_name.upper())
    if clean in MONTH_ALIASES:
        return MONTH_ALIASES[clean]
    for canonical in MONTH_NUMBERS:
        if len(clean) >= 3 and (clean.startswith(canonical[:5]) or canonical.startswith(clean[:5]) or clean.startswith(canonical[:3])):
            return canonical
    return None


def month_to_number(month_name: str) -> str | None:
    canonical_month = normalize_month(month_name)
    if not canonical_month:
        return None
    return MONTH_NUMBERS.get(canonical_month)


def to_ddmmyyyy(day: str, month_name: str, year: str) -> str | None:
    month = month_to_number(month_name)
    if not month or not year:
        return None
    return f"{int(day):02d}/{month}/{year}"


def token_to_ddmmyyyy(token: dict, year: str) -> str | None:
    month = MONTH_NUMBERS.get(str(token["month"]))
    if not month or not year:
        return None
    return f"{int(str(token['day'])):02d}/{month}/{year}"


def clean_inline_phrase(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" .,:;-")
    value = re.split(r"\n|\s{2,}|\s+AT\s+|\s+WHICH\s+|\s+YANG\s+|\s+DALAM\s+", value, flags=re.IGNORECASE)[0]
    return value.strip(" .,:;-")


def title_keep_acronym(value: str) -> str:
    words = []
    for word in re.split(r"(\s+)", value.strip()):
        if not word.strip():
            words.append(word)
            continue
        clean = re.sub(r"[^A-Za-z0-9]", "", word)
        if clean.isupper() and len(clean) <= 15:
            words.append(word.upper())
        else:
            words.append(word.capitalize())
    return "".join(words).strip()
