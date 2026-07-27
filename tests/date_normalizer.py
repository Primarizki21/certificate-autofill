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


def normalize_date(value: str | None) -> str | None:
    if not value or value.strip() == "-" or value.strip() == "":
        return None
    value = value.strip()

    parts = value.replace(",", " ").split()
    if len(parts) == 3:
        day, month, year = parts
        month_num = ALL_MONTHS.get(month.lower())
        if month_num and day.isdigit() and year.isdigit():
            return f"{int(day):02d}/{month_num}/{year}"
    return None
