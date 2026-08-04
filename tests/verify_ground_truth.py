import csv
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CSV_PATH = os.environ.get(
    "GT_CSV_PATH", os.path.join(os.path.dirname(__file__), "..", "Ground_Truth_Sertifikat.csv")
)
TEXTS_DIR = os.path.join(
    os.path.dirname(__file__), "benchmark_runs", "run_20260728_131835", "extracted_texts",
)

EVAL_FIELDS = [
    "nama_kegiatan_sertifikasi",
    "waktu_mulai_pelaksanaan",
    "waktu_selesai_pelaksanaan",
    "penyelenggara_kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi",
]

CSV_COLUMN_MAP = {
    "nama_kegiatan_sertifikasi": "Nama Kegiatan Sertifikasi",
    "waktu_mulai_pelaksanaan": "Waktu Mulai Pelaksanaan",
    "waktu_selesai_pelaksanaan": "Waktu Selesai Pelaksanaan",
    "penyelenggara_kegiatan": "Penyelenggara Kegiatan",
    "nomor_bukti_fisik_nomor_sertifikasi": "Nomor Bukti Fisik Nomor Sertifikasi",
    "tingkat": "Tingkat",
}

CHECKLIST = [
    ("Sertif_sportfes_vene_panitia.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("primarizki_panitia_binary_2024.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("PRIMARIZKI_panitia_binary_2025.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("Primarizki_panitia_synreaach_2024.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("Primarizki_kim_unair_2024.png", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Piagam HIMA S1-AK 2025-compressed_69.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Primarizki_hima.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("VENEDICT_sertif_bem.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("2065179_219642_skp.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Sertifikat Kepengurusan IRIS 2025_Muhammad Fazil Irvan Putra.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("BINARY_Venedict_peserta.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Sertif_ppkmb_univ_peserta.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("SERTIF76.png", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Sertif sinem_vene_magang UKM.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "nomor_bukti_fisik_nomor_sertifikasi"]),
    ("2030325_219642_skp.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "nomor_bukti_fisik_nomor_sertifikasi"]),
    ("2071996_221065_skp.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "nomor_bukti_fisik_nomor_sertifikasi"]),
    ("1966887_221065_skp.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("2954283_219642_skp.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("AQEEL_Seminar.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 9 Nov 2023.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Ananda Aqeel Fathur Rahman_Guest Lecture 25 October 2024.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Ananda Aqeel Fathur Rahman_Guest Lecture FDM 29 November 2024.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("E-certificate Ananda Aqeel Fathur Rahman (1).pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("File sertifikat untuk _VenedictGrinaldyPrasetyo__240103_143733_ORM.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Venedict G. P_peserta talkshow.pdf", ["penyelenggara_kegiatan", "waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan", "nomor_bukti_fisik_nomor_sertifikasi"]),
    ("2954685_219642_skp.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("2954933_219642_skp.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Airno_Faiz.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("FIT_Faiz.pdf", ["nomor_bukti_fisik_nomor_sertifikasi"]),
    ("Girifest_Faiz.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("NIC_Faiz.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("Poisson.Faiz.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("Primarizki Ahmad Hariyono_data slayer 2_lomba.png", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("SDC Unisba_Faiz.pdf", ["nama_kegiatan_sertifikasi", "waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
    ("Sertifikat_Peserta_Primarizki Ahmad Hariyono_ML.pdf", ["waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"]),
]

CAT2_NER_FAIL_ALL = [
    "1930354_219642_skp.pdf", "1952296_219642_skp.pdf", "1966887_221065_skp.pdf",
    "2030372_219642_skp.pdf", "2160238_221065_skp.pdf", "2398697_219642_skp.pdf",
    "2398703_219642_skp.pdf", "2439919_221065_skp.pdf", "2954421_219642_skp.pdf",
    "2954571_219642_skp.pdf", "2954631_219642_skp.pdf", "2954685_219642_skp.pdf",
    "2955331_219642_skp.pdf", "ACTION_Muhammad Fazil Irvan Putra_compressed.pdf",
    "ACW_Faiz.pdf", "Ananda Aqeel Fathur Rahman_Certificate Guest Lecture 17 Nov 2023.pdf",
    "Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025.pdf",
    "Ananda Aqeel Fathur Rahman_Guest Lecture ERP SAP 25 April 2025.pdf",
    "BINARY_Venedict_peserta.pdf", "E-certificate Ananda Aqeel Fathur Rahman (1).pdf",
    "FIT_Faiz.pdf", "Falcon_Faiz.pdf", "Gelar Rasa_Muhammad Fazil Irvan Putra.pdf",
    "Girifest_Faiz.pdf", "KARSA_Venedict_peserta.pdf", "MLQ - Primarizki Ahmad Hariyono.pdf",
    "NIC_Faiz.pdf", "PRIMARIZKI_panitia_binary_2025.pdf",
    "PRIMARIZKI_panitia_dataquest_2025.pdf", "Poisson.Faiz.pdf",
    "Primarizki Ahmad Hariyono_data slayer 2_lomba.png",
    "Primarizki Ahmad Hariyono_gammafest_lomba.pdf", "Primarizki_hima.pdf",
    "Primarizki_panitia_synreaach_2024.pdf", "PsyAcc_Faiz.pdf", "Rasio_Faiz.pdf",
    "Sertif_sportfes_vene_panitia.pdf", "UNITY_Muhammad Fazil Irvan Putra.pdf",
    "VENEDICT_panitia_karsa.pdf", "Venedict_panitia_specta.pdf", "hakim_lomba.png",
    "primarizki_panitia_binary_2024.pdf",
]

CAT3_REGEX_FAIL_ALL = [
    "1966887_221065_skp.pdf", "2030325_219642_skp.pdf", "2071996_221065_skp.pdf",
    "Ananda Aqeel Fathur Rahman_E - Certificate Agentic AI 17 November 2025.pdf",
    "FIT_Faiz.pdf", "Girifest_Faiz.pdf", "KARSA_Venedict_peserta.pdf", "NIC_Faiz.pdf",
    "Piagam HIMA S1-AK 2025-compressed_69.pdf", "Poisson.Faiz.pdf",
    "Primarizki Ahmad Hariyono_data slayer 2_lomba.png", "Rasio_Faiz.pdf",
    "Sertif sinem_vene_magang UKM.pdf", "Sertifikat_Peserta_Primarizki Ahmad Hariyono_ML.pdf",
    "Venedict G. P_peserta talkshow.pdf",
]


def read_text(filename):
    stem = os.path.splitext(filename)[0]
    txt_path = os.path.join(TEXTS_DIR, stem + ".txt")
    if not os.path.exists(txt_path):
        return None
    lines = []
    with open(txt_path) as f:
        for line in f:
            if not line.startswith("#"):
                lines.append(line)
    return "".join(lines).strip()


def normalize(value):
    value = value.lower()
    value = re.sub(r"[^a-z0-9]", "", value)
    return value


def ocr_contains(needle, haystack):
    if not needle or not haystack:
        return False
    needle = normalize(needle)
    haystack = normalize(haystack)
    if not needle:
        return False
    if needle in haystack:
        return True
    if len(needle) > 4 and needle[:-2] in haystack:
        return True
    if len(needle) > 4 and needle[2:] in haystack:
        return True
    return False


def extract_cert_number(text):
    m = re.search(r"\b(\d{3,4}/[A-Za-z0-9./]+/\d{4})\b", text)
    return m.group(1) if m else None


def extract_date(text):
    months = r"(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember|January|February|March|April|May|June|July|August|September|October|November|December)"
    m = re.search(rf"(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s+{months}\s+(\d{{4}})", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(3)} {m.group(4)}", f"{m.group(2)} {m.group(3)} {m.group(4)}"
    m2 = re.search(rf"(\d{{1,2}})\s+{months}\s+(\d{{4}})", text, re.IGNORECASE)
    if m2:
        return f"{m2.group(1)} {m2.group(2)} {m2.group(3)}", None
    return None, None


def find_in_text(gt_value, text):
    if not gt_value or gt_value == "-":
        return "GT_EMPTY", None
    if ocr_contains(gt_value, text):
        return "FOUND", None
    return "NOT_FOUND", "GT value not found in extracted text (may be OCR quality, not GT error)"


NATIONAL_EVIDENCE = ["NASIONAL", "NATIONAL", "LOMBA", "KOMPETISI", "COMPETITION", "OLIMPIADE"]
INTERNATIONAL_EVIDENCE = ["INTERNASIONAL", "INTERNATIONAL", "INSTITUT FRANÇAIS", "INSTITUT FRANCAIS", "EMBASSY"]
FOREIGN_ORG_HINTS = [
    "AIESEC", "SACLAY", "INSTITUT FRANÇAIS", "INSTITUT FRANCAIS", "EMBASSY",
    "PARIS", "INTERNATIONAL", "INTERNASIONAL",
]


def check_tingkat_evidence(gt_value, text):
    """Tingkat scale-evidence check. Returns list of warning strings."""
    if not gt_value or gt_value == "-":
        return []
    upper = (text or "").upper()
    warnings = []
    nat = any(k in upper for k in NATIONAL_EVIDENCE)
    inter = any(k in upper for k in INTERNATIONAL_EVIDENCE)
    foreign = any(k in upper for k in FOREIGN_ORG_HINTS)

    if gt_value == "Nasional" and not nat:
        warnings.append("GT=Nasional tapi tidak ada bukti skala nasional di teks (mungkin domain knowledge)")
    if gt_value == "Internasional":
        if not inter:
            warnings.append("GT=Internasional tapi tidak ada bukti internasional di teks")
        elif not foreign:
            warnings.append("GT=Internasional tapi tidak ada organisasi/indikator asing eksplisit")
    if gt_value != "Nasional" and "TINGKAT NASIONAL" in upper:
        warnings.append("teks menyebut 'TINGKAT NASIONAL' tapi GT != Nasional")
    if gt_value != "Internasional" and inter:
        warnings.append("teks menyebut internasional tapi GT != Internasional")
    if gt_value == "Internasional" and foreign:
        pass  # evidence konsisten
    return warnings


def main():
    rows = list(csv.DictReader(open(CSV_PATH, newline="")))
    csv_lookup = {r.get("Nama File", ""): r for r in rows}

    s = []
    s.append("=" * 80)
    s.append("GROUND TRUTH VERIFICATION REPORT")
    s.append(f"Files in CSV: {len(rows)}")
    s.append("=" * 80)

    cat1_fixes = []
    cat23_interesting = []

    s.append("\n--- CATEGORY 1: GT has empty/dash fields ---")
    s.append("These files have fields marked as '-' (unknown) in GT.")
    s.append("Checking if the extracted text contains plausible values.\n")

    for fname, empty_fields in CHECKLIST:
        row = csv_lookup.get(fname)
        if not row:
            continue
        text = read_text(fname)
        if text is None:
            s.append(f"  {fname}: no extracted text")
            continue

        file_issues = []
        for field in empty_fields:
            col = CSV_COLUMN_MAP[field]
            gt_value = row.get(col, "")
            if gt_value and gt_value != "-":
                continue

            if field == "nomor_bukti_fisik_nomor_sertifikasi":
                cert_num = extract_cert_number(text)
                if cert_num:
                    file_issues.append(f"  {field}: GT empty, but cert number '{cert_num}' found in text")
                    cat1_fixes.append((fname, field, cert_num))
            elif field in ("waktu_mulai_pelaksanaan", "waktu_selesai_pelaksanaan"):
                d1, d2 = extract_date(text)
                if field == "waktu_mulai_pelaksanaan" and d1:
                    file_issues.append(f"  {field}: GT empty, but date '{d1}' found in text")
                    cat1_fixes.append((fname, field, d1))
                elif field == "waktu_selesai_pelaksanaan" and d2:
                    file_issues.append(f"  {field}: GT empty, but date '{d2}' found in text")
                    cat1_fixes.append((fname, field, d2))

        if file_issues:
            s.append(f"  {fname}")
            s.extend(file_issues)

    s.append(f"\n  Cat 1 total: {len(cat1_fixes)} potential auto-fill candidates")

    s.append("\n--- CATEGORY 2 + 3: Full failure files ---")
    s.append("NER failed all fields (Cat2), or regex failed all fields (Cat3).")
    s.append("Checking if GT values are present in extracted text.\n")

    all_cat23 = list(dict.fromkeys(CAT2_NER_FAIL_ALL + CAT3_REGEX_FAIL_ALL))
    for fname in all_cat23:
        row = csv_lookup.get(fname)
        if not row:
            s.append(f"  {fname}: not in CSV")
            continue
        text = read_text(fname)
        if text is None:
            s.append(f"  {fname}: no extracted text")
            continue

        results = {}
        for field in EVAL_FIELDS:
            col = CSV_COLUMN_MAP[field]
            gt_value = row.get(col, "")
            status, note = find_in_text(gt_value, text)
            results[field] = status

        n_ok = sum(1 for v in results.values() if v == "FOUND")
        n_empty = sum(1 for v in results.values() if v == "GT_EMPTY")

        if n_ok > 0:
            s.append(f"  {fname} — {n_ok}/5 found in text {'' if n_empty == 0 else f'({n_empty} empty fields)'}")
            for field, status in results.items():
                if status != "FOUND":
                    continue
                col = CSV_COLUMN_MAP[field]
                gt_value = row.get(col, "")
                s.append(f"    ✓ {field}: '{gt_value[:60]}...' " if len(gt_value) > 60 else f"    ✓ {field}: '{gt_value}'")
            for field, status in results.items():
                if status == "NOT_FOUND":
                    col = CSV_COLUMN_MAP[field]
                    gt_value = row.get(col, "")
                    s.append(f"    ✗ {field}: '{gt_value[:60]}...' NOT FOUND" if len(gt_value) > 60 else f"    ✗ {field}: '{gt_value}' NOT FOUND")

        found_count = n_ok
        if found_count >= 4:
            cat23_interesting.append((fname, "likely OK", f"{found_count}/5 fields found in text"))
        elif found_count >= 2:
            cat23_interesting.append((fname, "partial", f"{found_count}/5 fields found in text"))
        else:
            cat23_interesting.append((fname, "likely bad GT", f"{found_count}/5 fields found in text"))

    s.append("\n--- CATEGORY 4: Tingkat scale-evidence check ---")
    s.append("Memindai teks untuk bukti skala (NASIONAL/INTERNASIONAL/TINGKAT NASIONAL/")
    s.append("organisasi asing) lalu membandingkan dengan label GT.\n")

    tingkat_warnings = 0
    for fname, row in csv_lookup.items():
        text = read_text(fname)
        if text is None:
            continue
        gt_t = row.get("Tingkat", "").strip()
        warnings = check_tingkat_evidence(gt_t, text)
        if warnings:
            tingkat_warnings += len(warnings)
            s.append(f"  {fname} (GT={gt_t or '-'})")
            for w in warnings:
                s.append(f"    ⚠ {w}")
    if tingkat_warnings == 0:
        s.append("  Tidak ada kontradiksi tingkat yang terdeteksi.")

    s.append("\n--- SUMMARY ---")
    s.append(f"Cat 1 potential auto-fills: {len(cat1_fixes)}")
    for fname, field, val in cat1_fixes:
        s.append(f"  {fname}: {field} → '{val}'")

    s.append("\nCat 2+3 files with 0-1/5 fields found in text (likely GT issues or very garbled OCR):")
    for fname, verdict, detail in cat23_interesting:
        if "likely bad" in verdict or "0/" in detail:
            s.append(f"  ⚠ {fname}: {detail}")

    s.append(f"\nCat 2+3 files with 2-3/5 fields found (partial match, worth checking):")
    for fname, verdict, detail in cat23_interesting:
        if "partial" in verdict:
            s.append(f"  ? {fname}: {detail}")

    s.append("\nCat 2+3 files with 4-5/5 fields found (GT likely correct, extraction issue):")
    for fname, verdict, detail in cat23_interesting:
        if "likely OK" in verdict:
            s.append(f"  ✓ {fname}: {detail}")

    report_path = os.path.join(os.path.dirname(__file__), "..", "docs", "gt_verification_report.txt")
    with open(report_path, "w") as f:
        f.write("\n".join(s) + "\n")
    print(f"Report written to {report_path}")
    print(f"Cat 1 auto-fill candidates: {len(cat1_fixes)}")
    print(f"Cat 2+3 files with <2/5 found: {sum(1 for _,v,_ in cat23_interesting if 'bad' in v)}")

    return cat1_fixes


def auto_fix_csv(fixes):
    if not fixes:
        print("No fixes to apply.")
        return
    rows = list(csv.DictReader(open(CSV_PATH, newline="")))
    fieldnames = rows[0].keys()
    fixed = 0
    for r in rows:
        fname = r.get("Nama File", "")
        for fix_fname, field, val in fixes:
            if fix_fname != fname:
                continue
            col = CSV_COLUMN_MAP[field]
            old = r.get(col, "")
            if not old or old == "-":
                r[col] = val
                print(f"  FIXED {fname}: {col} = '{val}' (was '{old}')")
                fixed += 1
    csv_path_fixed = CSV_PATH.replace(".csv", "_fixed.csv")
    with open(csv_path_fixed, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Fixed CSV: {csv_path_fixed} ({fixed} changes)")


if __name__ == "__main__":
    fixes = main()
    if "--fix" in sys.argv:
        auto_fix_csv(fixes)
