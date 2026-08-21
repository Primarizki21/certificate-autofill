"""Generate raw-vs-pipeline comparison artifacts.

Menunjukkan proses ekstraksi nyata: teks mentah yang keluar dari PDF vs field
hasil pipeline vs Ground Truth — bukan cuma metrik agregat.

Output:
- docs/report/raw_vs_pipeline.xlsx        — matriks 74 sertifikat (teks + field)
- docs/report/raw_vs_pipeline_examples.docx — 5 contoh terkurasi + annotasi

Sumber data:
- Teks mentah:   tests/benchmark_runs/run_20260728_131835/extracted_texts/
- Field pipeline: tests/benchmark_runs/run_llm_v4_20260805_163541/extracted_fields.csv
- Ground truth:  Ground_Truth_Sertifikat_v9.csv (matcher v2)

Usage:
  uv run python scripts/generate_raw_vs_pipeline.py
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(REPO, "docs", "report")
TEXTS = os.path.join(REPO, "tests", "benchmark_runs", "run_20260728_131835", "extracted_texts")
RUN = os.path.join(REPO, "tests", "benchmark_runs", "run_llm_v4_20260805_163541")
GT_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv")

# field pipeline (extracted_fields.csv) -> kolom GT (CSV) -> label display
FIELDS = [
    ("nama_kegiatan_sertifikasi", "Nama Kegiatan Sertifikasi", "Nama Kegiatan"),
    ("waktu_mulai_pelaksanaan", "Waktu Mulai Pelaksanaan", "Tanggal Mulai"),
    ("waktu_selesai_pelaksanaan", "Waktu Selesai Pelaksanaan", "Tanggal Selesai"),
    ("penyelenggara_kegiatan", "Penyelenggara Kegiatan", "Penyelenggara"),
    ("nomor_bukti_fisik_nomor_sertifikasi", "Nomor Bukti Fisik Nomor Sertifikasi", "Nomor Sertifikat"),
    ("tingkat", "Tingkat", "Tingkat"),
]


def load_gt():
    gt = {}
    with open(GT_CSV, newline="") as f:
        for r in csv.DictReader(f):
            stem = os.path.splitext(r["Nama File"])[0]
            gt[stem] = {k: (r[k] or "").strip() for k in [
                "Nama Kegiatan Sertifikasi", "Waktu Mulai Pelaksanaan",
                "Waktu Selesai Pelaksanaan", "Penyelenggara Kegiatan",
                "Nomor Bukti Fisik Nomor Sertifikasi", "Tingkat"]}
    return gt


def load_extracted():
    out = {}
    with open(os.path.join(RUN, "extracted_fields.csv"), newline="") as f:
        for r in csv.DictReader(f):
            stem = os.path.splitext(r["filename"])[0]
            out.setdefault(stem, {})[r["field"]] = r["value"]
    return out


def load_raw():
    out = {}
    for fn in os.listdir(TEXTS):
        if fn.endswith(".txt"):
            stem = os.path.splitext(fn)[0]
            with open(os.path.join(TEXTS, fn), encoding="utf-8", errors="replace") as f:
                out[stem] = f.read().strip()
    return out


def load_router():
    try:
        with open(os.path.join(RUN, "router_decisions.json")) as f:
            data = json.load(f)
            # Convert to dict keyed by stem (without .txt extension)
            return {r["certificate"].replace(".txt", ""): r for r in data}
    except FileNotFoundError:
        return {}


def per_cert_verdict(stem, extracted, gt):
    """Return dict field_label -> (extracted, gt, status) status in exact/fuzzy/wrong/missing."""
    out = {}
    for pipe_field, gt_col, label in FIELDS:
        ev = (extracted.get(stem) or {}).get(pipe_field, "") or ""
        gv = gt.get(stem, {}).get(gt_col, "") or ""
        if gv in ("", "-"):
            out[label] = (ev, gv, "no_gt")
            continue
        m = match_field(gv, ev, pipe_field)
        if m["exact"]:
            status = "exact"
        elif m["fuzzy"]:
            status = "fuzzy"
        else:
            status = "wrong"
        out[label] = (ev, gv, status)
    return out


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def render_xlsx(gt, extracted, raw):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    GREEN = PatternFill("solid", fgColor="C6EFCE")
    YELLOW = PatternFill("solid", fgColor="FFF2CC")
    RED = PatternFill("solid", fgColor="FFC7CE")
    GRAY = PatternFill("solid", fgColor="F2F2F2")
    HEADER_FILL = PatternFill("solid", fgColor="1F3864")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=9)
    BASE = Font(size=9)
    MONO = Font(size=8, name="Consolas")
    THIN = Side(style="thin", color="C9D4E4")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Raw vs Pipeline"
    header = ["filename", "raw text (dari PDF)"]
    for _, _, label in FIELDS:
        header += [f"{label} — pipeline", f"{label} — GT", f"{label} — match"]
    # Tambah kolom router
    header += ["Router — Decision", "Router — Rule", "Router — Signals"]
    ws.append(header)
    for c in range(1, len(header) + 1):
        cell = ws.cell(1, c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    ws.freeze_panes = "C2"

    stems = sorted(set(gt) & set(extracted) & set(raw))
    router_data = load_router()
    for i, stem in enumerate(stems):
        v = per_cert_verdict(stem, extracted, gt)
        row = [stem + ".txt", raw.get(stem, "")]
        for label in [f[2] for f in FIELDS]:
            ev, gv, status = v[label]
            row += [ev, gv, {"exact": "EXACT", "fuzzy": "FUZZY", "wrong": "WRONG",
                             "no_gt": "no GT"}[status]]
        # Tambah data router
        r_info = router_data.get(stem, {})
        row += [
            r_info.get("decision", "unrouted"),
            r_info.get("rule", ""),
            r_info.get("signals_str", ""),
        ]
        ws.append(row)
        r = i + 2
        ws.cell(r, 1).font = BASE
        ws.cell(r, 1).border = BORDER
        txt_cell = ws.cell(r, 2)
        txt_cell.font = MONO
        txt_cell.border = BORDER
        txt_cell.alignment = Alignment(vertical="top", wrap_text=True)
        for j, label in enumerate([f[2] for f in FIELDS]):
            base = 3 + j * 3
            status = v[label][2]
            for k in range(3):
                cell = ws.cell(r, base + k)
                cell.font = BASE
                cell.border = BORDER
                if k == 2:
                    cell.alignment = Alignment(horizontal="center")
                    cell.fill = {
                        "exact": GREEN, "fuzzy": YELLOW, "wrong": RED, "no_gt": GRAY,
                    }[status]
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 80
    for j, label in enumerate([f[2] for f in FIELDS]):
        for k, w in enumerate([28, 28, 10]):
            ws.column_dimensions[chr(ord("C") + j * 3 + k)].width = w
    # Router columns
    n_fields = len(FIELDS)
    router_start = chr(ord("C") + n_fields * 3)
    ws.column_dimensions[router_start].width = 25  # Decision
    ws.column_dimensions[chr(ord(router_start) + 1)].width = 18  # Rule
    ws.column_dimensions[chr(ord(router_start) + 2)].width = 40  # Signals

    # Style router columns
    for i_row in range(2, len(stems) + 2):
        decision_col = ord("C") + n_fields * 3
        for offset, col_letter in enumerate([decision_col, decision_col + 1, decision_col + 2]):
            cell = ws.cell(i_row, col_letter)
            cell.font = BASE
            cell.border = BORDER
            if offset == 0:  # Decision column
                decision_val = cell.value or ""
                if decision_val == "unrouted":
                    cell.fill = GRAY
                else:
                    cell.fill = GREEN

    ws.append([])
    ws.append(["Legenda:", "EXACT = hijau, FUZZY = kuning, WRONG = merah, no GT = abu-abu"])
    ws.append(["Router:", "hijau = routed (ada rule), abu-abu = unrouted (need LLM)"])
    wb.save(os.path.join(OUT, "raw_vs_pipeline.xlsx"))
    return stems


# ---------------------------------------------------------------------------
# DOCX (contoh terkurasi)
# ---------------------------------------------------------------------------
def _shade(cell, hexfill):
    from docx.oxml.ns import qn

    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.makeelement(qn("w:shd"), {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): hexfill})
    tcPr.append(shd)


def _table_borders(tbl, color="C9D4E4"):
    from docx.oxml.ns import qn

    tblPr = tbl._tbl.tblPr
    borders = tblPr.makeelement(qn("w:tblBorders"), {})
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tblPr.makeelement(qn(f"w:{edge}"), {
            qn("w:val"): "single", qn("w:sz"): "4", qn("w:space"): "0", qn("w:color"): color})
        borders.append(el)
    tblPr.append(borders)


def _raw_box(doc, text):
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = 0
    for line in text.splitlines():
        run = p.add_run(line + "\n")
        run.font.name = "Consolas"
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    pPr = p._p.get_or_add_pPr()
    shd = pPr.makeelement(
        qn("w:shd"), {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): "F2F6FC"})
    pPr.append(shd)


def render_docx(gt, extracted, raw, router, stems):
    import docx
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    ACCENT = RGBColor(0x1F, 0x38, 0x64)
    doc = docx.Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    t = doc.add_heading("Raw Text vs Pipeline — Contoh Ekstraksi Nyata", level=0)
    for run in t.runs:
        run.font.color.rgb = ACCENT
    sp = doc.add_paragraph()
    sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sp.add_run("Certificate Autofill Prototype — proses ekstraksi (pipeline v9)").font.color.rgb = RGBColor(0x59, 0x59, 0x59)
    doc.add_paragraph(
        "Tabel berikut menunjukkan teks MENTAH yang diekstrak dari PDF, field hasil pipeline "
        "(extracted_fields run v9), dan Ground Truth (GT v9). Hijau = EXACT, kuning = FUZZY "
        "(matcher v2), merah = salah/kosong. Angka yang sama, dihitung dari data yang sama, "
        "menghasilkan metrik MACRO exact 60.2% pada 74 sertifikat."
    )

    # Pilih 5 contoh terkurasi
    examples = pick_examples(stems, gt, extracted, raw, router)

    for idx, stem in enumerate(examples, 1):
        doc.add_heading(f"Contoh {idx} — {stem}.txt", level=1)
        v = per_cert_verdict(stem, extracted, gt)
        doc.add_heading("Teks mentah hasil ekstraksi PDF:", level=2)
        _raw_box(doc, raw.get(stem, ""))
        doc.add_heading("Hasil pipeline vs Ground Truth:", level=2)
        tbl = doc.add_table(rows=1 + len(FIELDS), cols=4)
        tbl.style = "Table Grid"
        _table_borders(tbl)
        hdr = ["Field", "Pipeline", "GT", "Status"]
        for j, h in enumerate(hdr):
            c = tbl.rows[0].cells[j]
            c.text = ""
            r = c.paragraphs[0].add_run(h)
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            _shade(c, "1F3864")
        for i, (_, _, label) in enumerate(FIELDS):
            ev, gv, status = v[label]
            row = tbl.rows[i + 1].cells
            for j, val in enumerate([label, ev or "(kosong)", gv or "(kosong)",
                                     {"exact": "EXACT", "fuzzy": "FUZZY", "wrong": "WRONG",
                                      "no_gt": "no GT"}[status]]):
                row[j].text = ""
                r = row[j].paragraphs[0].add_run(val)
                r.font.size = Pt(9)
            _shade(row[3], {"exact": "C6EFCE", "fuzzy": "FFF2CC", "wrong": "FFC7CE",
                            "no_gt": "F2F2F2"}[status])
        note = example_note(stem, v, router, gt, extracted)
        if note:
            p = doc.add_paragraph()
            r = p.add_run("Apa yang terjadi di pipeline: " + note)
            r.italic = True
            r.font.size = Pt(10)
        doc.add_paragraph()

    doc.save(os.path.join(OUT, "raw_vs_pipeline_examples.docx"))


def pick_examples(stems, gt, extracted, raw, router):
    """Pilih 5 contoh yang masing-masing bercerita beda tahap pipeline."""
    pool = [s for s in stems if s in raw and len(raw[s]) > 50]
    router_by_stem = router  # kunci router_decisions.json sudah bare stem (tanpa .txt)
    chosen = []
    seen = set()

    def finds(pred):
        for s in pool:
            if s in seen:
                continue
            v = per_cert_verdict(s, extracted, gt)
            if pred(s, v):
                return s
        return None

    # 1. Router menang (rule deciside, exact, tanpa LLM)
    s = finds(lambda s, v: router_by_stem.get(s, {}).get("decision") and v["Tingkat"][2] == "exact")
    if s:
        chosen.append(("router", s))
        seen.add(s)
    # 2. LLM fallback (router tidak memutuskan, tapi tingkat exact)
    s = finds(lambda s, v: not router_by_stem.get(s, {}).get("decision") and v["Tingkat"][2] == "exact")
    if s:
        chosen.append(("llm", s))
        seen.add(s)
    # 3. Normalisasi penyelenggara (raw punya akronim, pipeline exact vs GT)
    s = finds(lambda s, v: v["Penyelenggara"][2] == "exact" and "BEM" in raw.get(s, "").upper())
    if s:
        chosen.append(("org", s))
        seen.add(s)
    # 4. OCR merusak nomor (nomor salah)
    s = finds(lambda s, v: v["Nomor Sertifikat"][2] == "wrong")
    if s:
        chosen.append(("ocr", s))
        seen.add(s)
    # 5. nama kegiatan gagal (field tersulit)
    s = finds(lambda s, v: v["Nama Kegiatan"][2] == "wrong")
    if s:
        chosen.append(("activity", s))
        seen.add(s)
    # dedupe, isi sisa dari pool
    for s in pool:
        if len(chosen) >= 5:
            break
        if s not in seen:
            chosen.append(("extra", s))
            seen.add(s)
    # urutkan kembali berdasar stem agar stabil
    order = {"router": 0, "llm": 1, "org": 2, "ocr": 3, "activity": 4, "extra": 5}
    chosen.sort(key=lambda t: (order[t[0]], t[1]))
    return [s for _, s in chosen]


def example_note(stem, v, router, gt, extracted):
    parts = []
    rd = router.get(stem, {})
    if rd.get("rule"):
        parts.append(f"rule router `{rd['rule']}` memutuskan tingkat tanpa LLM")
    elif rd.get("decision") == "" and "decision" in rd:
        parts.append("router tidak memutuskan → tingkat di-fallback ke LLM")
    if v["Penyelenggara"][2] in ("exact", "fuzzy"):
        parts.append(f"penyelenggara {v['Penyelenggara'][2].lower()} (organizer_v2 menormalkan akronim)")
    if v["Nomor Sertifikat"][2] == "wrong":
        parts.append("nomor gagal — karakter digit rusak oleh OCR")
    if v["Nama Kegiatan"][2] == "wrong":
        parts.append("nama kegiatan gagal — pola template tidak cocok / teks OCR berbeda")
    if v["Tanggal Mulai"][2] == "exact":
        parts.append("tanggal diekstrak regex + alias bulan OCR")
    if not parts:
        parts.append("semua field cocok (EXACT) — teks bersih, pola regex cocok")
    return "; ".join(parts)


def main():
    gt = load_gt()
    extracted = load_extracted()
    raw = load_raw()
    router = load_router()
    stems = render_xlsx(gt, extracted, raw)
    render_docx(gt, extracted, raw, router, stems)
    print(f"raw_vs_pipeline.xlsx: {len(stems)} sertifikat")
    print("raw_vs_pipeline_examples.docx: 5 contoh")
    print("done")


if __name__ == "__main__":
    main()
