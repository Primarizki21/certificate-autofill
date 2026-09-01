import re

INDONESIAN_MONTHS = {
    "januari": "01", "februari": "02", "maret": "03", "april": "04",
    "mei": "05", "juni": "06", "juli": "07", "agustus": "08",
    "september": "09", "oktober": "10", "november": "11", "desember": "12",
}

ENGLISH_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

ALL_MONTHS = {**INDONESIAN_MONTHS, **ENGLISH_MONTHS}

# ponytail: handles all date formats found in certificate CSV + pipeline output
_RE_DMY_SLASH = re.compile(r"^(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{4})$")
_RE_MONTH_FIRST = re.compile(
    r"^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})$", re.IGNORECASE
)
_RE_DAY_FIRST = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})$", re.IGNORECASE
)


def normalize_date(value: str | None) -> str | None:
    if not value or value.strip() in ("-", ""):
        return None
    value = value.strip().rstrip(".")

    # DD/MM/YYYY or DD-MM-YYYY
    m = _RE_DMY_SLASH.match(value)
    if m:
        d, mo, y = m.groups()
        return f"{int(d):02d}/{int(mo):02d}/{y}"

    # "29 September 2024" or "9 November 2024"
    m = _RE_DAY_FIRST.match(value)
    if m:
        day, month_str, year = m.groups()
        month_num = ALL_MONTHS.get(month_str.lower())
        if month_num:
            return f"{int(day):02d}/{month_num}/{year}"

    # "September 29, 2024" or "September 29 2024"
    m = _RE_MONTH_FIRST.match(value)
    if m:
        month_str, day, year = m.groups()
        month_num = ALL_MONTHS.get(month_str.lower())
        if month_num:
            return f"{int(day):02d}/{month_num}/{year}"

    return None
