"""Generate docs/report/gt_review_v12.xlsx for handoff v12 GT audit.

Sheets:
  1. Typo Disetujui   - typos already confirmed by user (Kementriann, Akuntasi).
  2. Review Organizer - GT organizers NOT found literally in text, with text
                        context, so user can judge correctness / form.
  3. Valid Keep       - organizers confirmed valid (e.g. Faculty...Dept x7).

User fills the 'keputusan' column; decisions get applied to
Ground_Truth_Sertifikat_v9.csv afterwards.
"""

import csv
import os
import re

import openpyxl
from openpyxl.styles import Font, PatternFill

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V8_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v8.csv")
TEXTS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts")
OUT = os.path.join(REPO, "docs", "report", "gt_review_v12.xlsx")

STOPWORDS = {"dan", "of", "the", "for", "and", "de"}


def read_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _texts():
    out = {}
    for tf in os.listdir(TEXTS_DIR):
        if tf.endswith(".txt"):
            out[tf[:-4]] = open(os.path.join(TEXTS_DIR, tf)).read()
    return out


def find_text(fname, texts):
    """Mapping stem-exact seperti benchmark asli (os.path.splitext).
    Heuristic prefix bisa salah pilih file -> konteks menyesatkan."""
    base = fname.replace(".pdf", "").replace(".PDF", "").strip()
    return texts.get(base)


def literal_hit(gt, text):
    g = re.sub(r"[^a-z0-9/]+", " ", gt.lower()).strip()
    t = re.sub(r"[^a-z0-9/]+", " ", text.lower())
    return g in t


def abbr_hit(gt, text):
    gi = [w[0] for w in gt.lower().split() if re.sub(r"[^a-z]", "", w) and re.sub(r"[^a-z]", "", w) not in STOPWORDS]
    ti = [w[0] for w in text.lower().split() if re.sub(r"[^a-z]", "", w) and re.sub(r"[^a-z]", "", w) not in STOPWORDS]
    if len(gi) < 2:
        return False
    i = 0
    for c in ti:
        if i < len(gi) and c == gi[i]:
            i += 1
    return i >= len(gi)


ORG_PAT = re.compile(
    r"(?:by|oleh|BEM|HIMA|Himpunan|Program Studi|UKM|Fakultas|University|Institut|Direktorat|Kementerian|"
    r"Departemen|Divisi|Biro|Tax Center|Telkom|STAN|dari)\s[^\n]{0,110}",
    re.IGNORECASE,
)


def context(text, maxlen=110):
    body = re.sub(r"^\s*#\s*(?:Method|Time).*$", "", text, flags=re.MULTILINE)
    clean = re.sub(r"\s+", " ", body).strip()
    if not clean:
        return "(teks kosong)"
    hits = list(ORG_PAT.finditer(clean))
    if hits:
        return re.sub(r"\s+", " ", hits[0].group(0))[:maxlen]
    return clean[:maxlen]


def _notes():
    return {
        "FIT_Faiz.pdf": "GT: 'Informatioon' (double-o) kemungkinan typo -> 'Information'",
        "2954685_219642_skp.pdf": "GT tampaknya NAMA ACARA (ITASE 6.0 Dies Natalis), bukan organisasi",
        "NIC_Faiz.pdf": "teks: 'HIMASTA/UNIMUS' -> GT 'Himpunan Mahasiswa UNIMUS' kurang spesifik? Himasta=Statistika",
        "Poisson.Faiz.pdf": "teks: 'FOPKAS CERTIFICATE' vs GT 'Forkas' -> mana ejaan benar?",
        "SERTIF76.png": "tidak ada teks hasil ekstraksi -> OCR gagal total, cek manual",
        "Airno_Faiz.pdf": "teks: 'oleh BEM FTMM dengan Himpunan Mahasiswa Teknologi Sains Data' -> organisasi ganda?",
    }


def main():
    rows = read_rows(V8_CSV)
    texts = _texts()

    wb = openpyxl.Workbook()
    hdr_fill = PatternFill("solid", fgColor="D5E8F0")
    bold = Font(bold=True)
    warn = PatternFill("solid", fgColor="FFF2CC")

    def sheet(name, headers, widths):
        ws = wb.create_sheet(name)
        ws.append(headers)
        for c in ws[1]:
            c.fill = hdr_fill
            c.font = bold
        for letter, w in zip("ABCDEF", widths):
            ws.column_dimensions[letter].width = w
        return ws

    # --- Sheet 1: Typo Disetujui ---
    ws = sheet("Typo Disetujui", ["file", "field", "gt_v8", "fix", "bukti", "keputusan"], [40, 22, 60, 60, 50, 14])
    typos = [
        ("AQEEL_Seminar.pdf", "Penyelenggara Kegiatan",
         "Kementriann Komunikasi dan Informatika Republik Indonesia dan Gerakan Nasional Literasi Digital Siberkreasi",
         "Kementerian Komunikasi dan Informatika Republik Indonesia dan Gerakan Nasional Literasi Digital Siberkreasi",
         "typo 'Kementriann' -> 'Kementerian' (user approved)"),
        ("Piagam HIMA S1-AK 2025-compressed_69.pdf", "Penyelenggara Kegiatan",
         "Himpunan Mahasiswa S-1 Akuntasi",
         "Himpunan Mahasiswa S-1 Akuntansi",
         "teks asli: 'Himpunan Mahasiswa S-1 Akuntansi' (user approved)"),
    ]
    for fname, field, old, new, ev in typos:
        ws.append([fname, field, old, new, ev, ""])

    # --- Sheet 2: Review Organizer ---
    ws = sheet("Review Organizer", ["file", "gt_v8", "bukti", "konteks_teks", "catatan", "keputusan"], [44, 55, 12, 70, 30, 14])
    notes = _notes()
    for r in rows:
        org = (r["Penyelenggara Kegiatan"] or "").strip()
        if not org:
            continue
        fname = r["Nama File"].strip()
        text = find_text(fname, texts)
        if text is None:
            ws.append([fname, org, "NO-TEXT", "(tidak ada teks hasil ekstraksi)", notes.get(fname, "cek manual"), ""])
            continue
        if literal_hit(org, text):
            continue
        if abbr_hit(org, text):
            continue
        ws.append([fname, org, "TIDAK literal", context(text), notes.get(fname, "verifikasi nama organisasi"), ""])

    # --- Sheet 3: Valid Keep ---
    ws = sheet("Valid Keep", ["file", "gt_v8", "catatan", "keputusan"], [50, 60, 60, 14])
    valid = [
        "Faculty of Science and Technology Information System Dept.",
        "BEM FTMM Universitas Airlangga",
        "Himatesda",
        "Universitas Airlangga",
        "BEM FEB UNAIR",
    ]
    seen = set()
    for r in rows:
        org = (r["Penyelenggara Kegiatan"] or "").strip()
        if org in valid and org not in seen:
            seen.add(org)
            note = {
                "Faculty of Science and Technology Information System Dept.":
                    "VALID (user confirm); pipeline-gap -> target LLM di Exp5; English hasil extract OK",
                "BEM FTMM Universitas Airlangga": "VALID (akronim); matcher v2 kredit via inisial-subsequence",
                "Himatesda": "VALID (akronim organisasi)",
                "Universitas Airlangga": "VALID (bentuk umum)",
                "BEM FEB UNAIR": "VALID (akronim)",
            }[org]
            ws.append([r["Nama File"].strip(), org, note, ""])

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]
    wb.save(OUT)
    print(f"wrote {OUT}")
    for n in wb.sheetnames:
        print(f"  sheet '{n}': {wb[n].max_row - 1} baris")


if __name__ == "__main__":
    main()
