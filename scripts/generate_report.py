"""Generate the four experiment reports (docx + md + xlsx) from
docs/report/report_data.json. Data-driven: adding an experiment to the JSON
'experiments' array updates every auto table (comparison / progression /
results) in the correct section. Idempotent.

Usage:
  uv run python scripts/generate_report.py
"""

import json
import os
import sys

import docx
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "docs", "report", "report_data.json")
OUTDIR = os.path.join(REPO, "docs", "report")

# Palette dokumen (indigo profesional — kontras tinggi, tidak mencolok)
ACCENT = RGBColor(0x1F, 0x38, 0x64)      # judul & heading utama
ACCENT_BLUE = RGBColor(0x2F, 0x54, 0x96)  # heading sekunder
TEXT_MUTED = RGBColor(0x59, 0x59, 0x59)   # subtitle
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEADER_FILL = "1F3864"                    # header tabel
ROW_ALT_FILL = "F2F6FC"                   # baris selang-seling
WINNER_FILL = "FDF3D7"                    # baris pemenang (progression)
BORDER_COLOR = "C9D4E4"                   # border tabel lembut


def load_data() -> dict:
    with open(DATA) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Auto tables from experiments[]
# ---------------------------------------------------------------------------
def experiments_table(data) -> dict:
    rows = []
    for e in data["experiments"]:
        rows.append([
            e["label"],
            e["tingkat"],
            e["macro"],
            str(e["tokens_cert"]),
            str(e["calls"]),
            e.get("router", "-"),
            e.get("gt", "raw"),
            e.get("date", ""),
        ])
    return {"h": ["Experiment", "Tingkat", "MACRO", "Eff tok/cert", "LLM calls", "Router", "GT", "Date"], "r": rows}


def progression_table(data) -> dict:
    rows = []
    for e in data["experiments"]:
        mark = " **" if e.get("is_winner") else ""
        rows.append([e.get("phase", ""), e["label"] + mark, e["tingkat"], e["macro"]])
    return {"h": ["Phase", "Method", "Tingkat", "MACRO"], "r": rows}


def results_table(data) -> dict:
    rows = []
    for e in data["experiments"]:
        rows.append([
            e["label"],
            e["tingkat"],
            e["macro"],
            str(e["tokens_cert"]),
            str(e["calls"]),
            e.get("router", "-"),
            e.get("gt", "raw"),
        ])
    return {"h": ["Experiment", "Tingkat exact", "MACRO exact", "Eff tok/cert", "LLM calls", "Router", "GT"], "r": rows}


def resolve_auto(kind: str, data: dict) -> dict:
    if kind == "comparison":
        return experiments_table(data)
    if kind == "progression":
        return progression_table(data)
    if kind == "results":
        return results_table(data)
    raise ValueError(f"unknown auto table: {kind}")


# ---------------------------------------------------------------------------
# DOCX renderer
# ---------------------------------------------------------------------------
def _shade(cell, hexfill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.makeelement(
        qn("w:shd"), {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): hexfill}
    )
    tcPr.append(shd)


def _table_borders(tbl, color: str) -> None:
    tblPr = tbl._tbl.tblPr
    borders = tblPr.makeelement(qn("w:tblBorders"), {})
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tblPr.makeelement(qn(f"w:{edge}"), {
            qn("w:val"): "single", qn("w:sz"): "4", qn("w:space"): "0", qn("w:color"): color,
        })
        borders.append(el)
    tblPr.append(borders)


def _heading(doc, text: str, level: int):
    h = doc.add_heading(text, level=level)
    color = ACCENT if level <= 1 else ACCENT_BLUE
    for run in h.runs:
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return h


def _build_table(doc, hdr, rows):
    tbl = doc.add_table(rows=1 + len(rows), cols=len(hdr))
    try:
        tbl.style = "Table Grid"
    except KeyError:
        pass
    _table_borders(tbl, BORDER_COLOR)
    for j, cell in enumerate(tbl.rows[0].cells):
        _shade(cell, HEADER_FILL)
        cell.text = ""
        r = cell.paragraphs[0].add_run(str(hdr[j]))
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = WHITE
    for i, row in enumerate(rows):
        is_winner = any("**" in str(v) for v in row)
        if is_winner:
            for c in tbl.rows[i + 1].cells:
                _shade(c, WINNER_FILL)
        elif i % 2 == 1:
            for c in tbl.rows[i + 1].cells:
                _shade(c, ROW_ALT_FILL)
        for j, val in enumerate(row):
            c = tbl.rows[i + 1].cells[j]
            c.text = ""
            r = c.paragraphs[0].add_run(str(val).replace("**", ""))
            r.font.size = Pt(9)
            if is_winner:
                r.bold = True
    return tbl


def render_docx(blocks: list[dict], path: str, title: str, subtitle: str):
    doc = docx.Document()
    styles = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(11)

    t = doc.add_heading(title, level=0)
    for run in t.runs:
        run.font.color.rgb = ACCENT
    if subtitle:
        sp = doc.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = sp.add_run(subtitle)
        run.font.size = Pt(12)
        run.font.color.rgb = TEXT_MUTED
    doc.add_paragraph()

    for blk in blocks:
        kind = blk["t"]
        x = blk["x"]
        if kind == "h1":
            _heading(doc, x, 1)
        elif kind == "h2":
            _heading(doc, x, 2)
        elif kind == "h3":
            _heading(doc, x, 3)
        elif kind == "p":
            p = doc.add_paragraph()
            lines = x.split("\n")
            for i, ln in enumerate(lines):
                if i > 0:
                    p.add_run().add_break()
                p.add_run(ln)
        elif kind == "b":
            for item in x:
                doc.add_paragraph(item, style="List Bullet")
        elif kind == "table":
            _build_table(doc, x["h"], x["r"])
            doc.add_paragraph()
        elif kind == "auto":
            render_docx_table(doc, resolve_auto(x, DATA_CACHE))
    doc.save(path)


def render_docx_table(doc, tbl_data: dict):
    _build_table(doc, tbl_data["h"], tbl_data["r"])
    doc.add_paragraph()


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------
def md_table(tbl_data: dict) -> str:
    hdr, rows = tbl_data["h"], tbl_data["r"]
    out = ["| " + " | ".join(hdr) + " |", "|" + "|".join(["---"] * len(hdr)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(v) for v in r) + " |")
    return "\n".join(out)


def render_md(blocks: list[dict], path: str, title: str, subtitle: str):
    lines = [f"# {title}", "", f"*{subtitle}*", ""]
    for blk in blocks:
        kind = blk["t"]
        x = blk["x"]
        if kind == "h1":
            lines += [f"## {x}", ""]
        elif kind == "h2":
            lines += [f"### {x}", ""]
        elif kind == "h3":
            lines += [f"#### {x}", ""]
        elif kind == "p":
            lines += [x, ""]
        elif kind == "b":
            lines += [f"- {item}" for item in x] + [""]
        elif kind == "table":
            lines += [md_table(x), ""]
        elif kind == "auto":
            lines += [md_table(resolve_auto(x, DATA_CACHE)), ""]
    with open(path, "w") as f:
        f.write("\n".join(lines).rstrip() + "\n")


# ---------------------------------------------------------------------------
# XLSX — results comparison (styled: grid, header fill, direction-aware deltas)
# ---------------------------------------------------------------------------
def _xlsx_styles():
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")
    RED_FILL = PatternFill("solid", fgColor="FFC7CE")
    GREEN_FONT = Font(color="006100", size=9)
    RED_FONT = Font(color="9C0006", size=9)
    HEADER_FILL = PatternFill("solid", fgColor="1F3864")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=9)
    ALT_FILL = PatternFill("solid", fgColor="F2F6FC")
    WINNER_FILL = PatternFill("solid", fgColor="FDF3D7")
    BASE_FONT = Font(size=9)
    BOLD_FONT = Font(size=9, bold=True)
    THIN = Side(style="thin", color="C9D4E4")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    WRAP = Alignment(vertical="center", wrap_text=True)
    return {
        "GREEN_FILL": GREEN_FILL, "RED_FILL": RED_FILL, "GREEN_FONT": GREEN_FONT,
        "RED_FONT": RED_FONT, "HEADER_FILL": HEADER_FILL, "HEADER_FONT": HEADER_FONT,
        "ALT_FILL": ALT_FILL, "WINNER_FILL": WINNER_FILL, "BASE_FONT": BASE_FONT,
        "BOLD_FONT": BOLD_FONT, "BORDER": BORDER, "WRAP": WRAP,
    }


def _pct(value) -> float | None:
    """'83.8%' -> 83.8 ; 'n/a'/None -> None."""
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "-", "n/a", "—"):
        return None
    try:
        return float(s.replace("%", ""))
    except ValueError:
        return None


def _style_header(ws, S, ncols):
    from openpyxl.styles import Alignment
    for c in range(1, ncols + 1):
        cell = ws.cell(1, c)
        cell.fill = S["HEADER_FILL"]
        cell.font = S["HEADER_FONT"]
        cell.border = S["BORDER"]
        cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    ws.freeze_panes = "A2"


def _style_rows(ws, S, nrows, ncols, winner_idx=None, deltas=None, n_fixed=1):
    """deltas: dict col_index -> ('acc'|'cost'), kolom yang di-warnai arah."""
    for r in range(2, nrows + 2):
        is_alt = (r % 2 == 0)
        for c in range(1, ncols + 1):
            cell = ws.cell(r, c)
            if cell.font is None or not cell.font.bold:
                cell.font = S["BOLD_FONT"] if (winner_idx and r - 2 == winner_idx) else S["BASE_FONT"]
            cell.border = S["BORDER"]
            if winner_idx and r - 2 == winner_idx:
                cell.fill = S["WINNER_FILL"]
            elif is_alt:
                cell.fill = S["ALT_FILL"]
        # Delta coloring (setelah border; fill hanya cell delta)
        for c, kind in (deltas or {}).items():
            cell = ws.cell(r, c)
            v = cell.value
            if v is None or (isinstance(v, str) and v in ("-", "", "—")):
                continue
            try:
                n = float(str(v).replace("+", "").replace("pp", "").replace(",", ""))
            except ValueError:
                continue
            if n == 0:
                continue
            up = n > 0
            good = up if kind == "acc" else not up  # cost: naik = buruk
            cell.fill = S["GREEN_FILL"] if good else S["RED_FILL"]
            cell.font = S["GREEN_FONT"] if good else S["RED_FONT"]


def _fmt_delta(cur, prev, suffix="pp") -> str:
    if cur is None or prev is None:
        return "-"
    d = cur - prev
    if d == 0:
        return "0"
    return f"{d:+.{1}f}{suffix}"


def _best_col(vals, prev=None):
    """Index kolom bernilai tertinggi (untuk highlight per-field)."""
    parsed = [(_pct(v), i) for i, v in enumerate(vals)]
    parsed = [(v, i) for v, i in parsed if v is not None]
    if not parsed:
        return None
    return max(parsed)[1]


# Per-field tables (metode v2-v4, GT raw) — dari phase_v4_results_summary.md
PER_FIELD_METHODS = ["Regex", "NER v1", "Hybrid", "Hybrid+PP", "A1 (per-field)", "A2 v2 (full-text)"]
PER_FIELD_EXACT = [
    ["nama_kegiatan", 6.9, 16.4, 24.3, 24.3, 25.7, 43.2],
    ["penyelenggara", 6.9, 11.0, 12.2, 13.5, 13.5, 31.1],
    ["waktu_mulai", 81.8, 27.3, 81.8, 81.8, 81.8, 94.5],
    ["waktu_selesai", 81.8, 7.3, 81.8, 81.8, 81.8, 94.5],
    ["nomor", 58.0, 0.0, 59.6, 59.6, 65.4, 73.1],
    ["tingkat", None, None, None, None, 47.3, 36.5],
    ["MACRO", 42.2, 12.8, 47.7, 48.1, 49.0, 58.3],
]
PER_FIELD_FUZZY = [
    ["nama_kegiatan", 19.2, 43.8, 63.5, 63.5, 70.3, 85.1],
    ["penyelenggara", 41.1, 50.7, 47.3, 50.0, 50.0, 73.0],
    ["waktu_mulai", 81.8, 27.3, 81.8, 81.8, 81.8, 94.5],
    ["waktu_selesai", 81.8, 7.3, 81.8, 81.8, 81.8, 94.5],
    ["nomor", 58.0, 0.0, 59.6, 59.6, 65.4, 73.1],
    ["tingkat", None, None, None, None, 47.3, 36.5],
    ["MACRO", 53.3, 28.8, 65.5, 66.1, 64.6, 74.5],
]
# v9 per-field (GT v9 + matcher v2) — metrologi berbeda dari baris di atas.
PER_FIELD_V9 = [
    ["nama_kegiatan_sertifikasi", 25.7, 52.7],
    ["waktu_mulai_pelaksanaan", 81.8, 81.8],
    ["waktu_selesai_pelaksanaan", 81.8, 81.8],
    ["penyelenggara_kegiatan", 39.2, 79.7],
    ["nomor_bukti_fisik_nomor_sertifikasi", 59.6, 59.6],
    ["tingkat", 83.8, 89.2],
    ["MACRO", 60.2, 74.2],
]
OCR_LINE = [
    # [Engine / approach, scan MACRO, nomor scan, verdict]
    ["RapidOCR (baseline)", "47.3%", "57.6%", "baseline"],
    ["RapidOCR+Tesseract (prod-equivalent)", "47.3%", "57.6%", "baseline"],
    ["PaddleOCR 2.9 (CPU)", "39.8%", "39.4%", "FAIL"],
    ["EasyOCR (CPU, max-side 960)", "34.3%", "15.2%", "FAIL"],
    ["EasyOCR (GPU, full-res)", "39.3%", "33.3%", "FAIL"],
    ["DocTR probe (OCR-006)", "40.0%", "14.3%", "FAIL"],
    ["DocTR hybrid per-field (HYB-001)", "46.8%", "57.6%", "PASS"],
    ["NC-001 nomor crop (re-render zoom 6x)", "46.3%", "60.6%", "PASS"],
    ["NC-002 region-OCR murah", "47.3%", "57.6%", "FAIL"],
]


def render_xlsx(data: dict, path: str):
    import openpyxl

    S = _xlsx_styles()
    wb = openpyxl.Workbook()

    # --- Sheet 1: Results Comparison (semua eksperimen + delta arah) ---
    ws = wb.active
    ws.title = "Results Comparison"
    exps = data["experiments"]
    ncols = 12
    ws.append(["Experiment", "Phase", "Tingkat", "ΔTingkat", "MACRO", "ΔMACRO",
               "Eff tok/cert", "Δtokens", "LLM calls", "Δcalls", "Router", "GT"])
    prev = {"tk": None, "macro": None, "tok": None, "calls": None}
    prev_ocr = {"macro": None}
    winner_idx = None
    for i, e in enumerate(exps):
        tk, macro = _pct(e.get("tingkat")), _pct(e.get("macro"))
        is_ocr = e.get("phase") == "ocr"
        tok = None if is_ocr else (e.get("tokens_cert") if isinstance(e.get("tokens_cert"), (int, float)) else None)
        calls = None if is_ocr else (e.get("calls") if isinstance(e.get("calls"), (int, float)) else None)
        # Delta dihitung vs eksperimen SEJENIS sebelumnya (LLM/rule vs OCR terpisah)
        # agar perbandingan like-for-like (korpus berbeda tidak dicampur).
        d_macro = _fmt_delta(macro, prev_ocr["macro"] if is_ocr else prev["macro"])
        ws.append([
            e["label"],
            e.get("phase", ""),
            e.get("tingkat", "-"),
            "-" if is_ocr else _fmt_delta(tk, prev["tk"]),
            e.get("macro", "-"),
            d_macro,
            "n/a" if is_ocr else e.get("tokens_cert", "-"),
            "n/a" if is_ocr else _fmt_delta(tok, prev["tok"], suffix=""),
            "n/a" if is_ocr else e.get("calls", "-"),
            "n/a" if is_ocr else _fmt_delta(calls, prev["calls"], suffix=""),
            e.get("router", "-"),
            e.get("gt", "raw"),
        ])
        if is_ocr:
            if macro is not None:
                prev_ocr["macro"] = macro
            continue
        if tk is not None:
            prev["tk"] = tk
        if macro is not None:
            prev["macro"] = macro
        if tok is not None:
            prev["tok"] = tok
        if calls is not None:
            prev["calls"] = calls
        if e.get("is_winner"):
            winner_idx = i
    _style_header(ws, S, ncols)
    deltas = {4: "acc", 6: "acc", 8: "cost", 10: "cost"}
    _style_rows(ws, S, len(exps), ncols, winner_idx=winner_idx, deltas=deltas)
    ws.column_dimensions["A"].width = 42
    for col in "BCDEFGHIJKL":
        ws.column_dimensions[col].width = 11
    ws.append([])
    ws.append(["Legenda:", "Accuracy (Tingkat/MACRO): naik = hijau, turun = merah. "
              "Cost (tokens/calls): turun = hijau (hemat), naik = merah."])
    ws.append(["Winner row (v9):", "kuning. Delta dihitung vs eksperimen sebelumnya."])

    # --- Sheet 2: Progression (ringkas, delta MACRO) ---
    ws2 = wb.create_sheet("Progression")
    ws2.append(["Phase", "Method", "Tingkat", "MACRO", "ΔMACRO", "Tok/cert", "Calls"])
    prev_macro = None
    prev_ocr_macro = None
    winner_idx2 = None
    for i, e in enumerate(exps):
        macro = _pct(e.get("macro"))
        is_ocr = e.get("phase") == "ocr"
        d_macro = _fmt_delta(macro, prev_ocr_macro if is_ocr else prev_macro)
        ws2.append([e.get("phase", ""), e["label"], e.get("tingkat", "-"),
                    e.get("macro", "-"), d_macro,
                    "n/a" if is_ocr else e.get("tokens_cert", "-"),
                    "n/a" if is_ocr else e.get("calls", "-")])
        if is_ocr:
            if macro is not None:
                prev_ocr_macro = macro
            continue
        if macro is not None:
            prev_macro = macro
        if e.get("is_winner"):
            winner_idx2 = i
    _style_header(ws2, S, 7)
    _style_rows(ws2, S, len(exps), 7, winner_idx=winner_idx2, deltas={5: "acc"})
    ws2.column_dimensions["B"].width = 42
    for col in "ACDEFG":
        ws2.column_dimensions[col].width = 11

    # --- Sheet 3: Per-Field (exact + fuzzy per metode) ---
    ws3 = wb.create_sheet("Per-Field")
    ws3.append(["Field", "Metric"] + PER_FIELD_METHODS)
    for i, row in enumerate(PER_FIELD_EXACT):
        ws3.append([row[0], "exact"] + [f"{v}%" if v is not None else "-" for v in row[1:]])
        best = _best_col(row[1:])
        if best is not None:
            ws3.cell(i + 2, best + 3).font = S["BOLD_FONT"]
            ws3.cell(i + 2, best + 3).fill = S["GREEN_FILL"]
    base = len(PER_FIELD_EXACT) + 2
    for i, row in enumerate(PER_FIELD_FUZZY):
        ws3.append([row[0], "fuzzy"] + [f"{v}%" if v is not None else "-" for v in row[1:]])
        best = _best_col(row[1:])
        if best is not None:
            ws3.cell(base + i, best + 3).font = S["BOLD_FONT"]
            ws3.cell(base + i, best + 3).fill = S["GREEN_FILL"]
    _style_header(ws3, S, 8)
    _style_rows(ws3, S, len(PER_FIELD_EXACT) + len(PER_FIELD_FUZZY), 8)
    ws3.append([])
    ws3.append(["v9 per-field (GT v9 + matcher v2) — metrologi berbeda dari tabel di atas"])
    r0 = len(PER_FIELD_EXACT) + len(PER_FIELD_FUZZY) + 3
    ws3.cell(r0, 1).value = "Field"
    ws3.cell(r0, 2).value = "Exact"
    ws3.cell(r0, 3).value = "Fuzzy"
    ws3.cell(r0, 1).font = ws3.cell(r0, 2).font = ws3.cell(r0, 3).font = S["BOLD_FONT"]
    for i, (f, ex, fu) in enumerate(PER_FIELD_V9):
        ws3.cell(r0 + 1 + i, 1).value = f
        ws3.cell(r0 + 1 + i, 2).value = f"{ex}%"
        ws3.cell(r0 + 1 + i, 3).value = f"{fu}%"
    for col in "ABCDEFGH":
        ws3.column_dimensions[col].width = 13
    ws3.column_dimensions["A"].width = 30

    # --- Sheet 4: OCR Line ---
    ws4 = wb.create_sheet("OCR Line")
    ws4.append(["Engine / approach", "scan MACRO", "nomor scan", "verdict"])
    for row in OCR_LINE:
        ws4.append(row)
    _style_header(ws4, S, 4)
    for r in range(2, len(OCR_LINE) + 2):
        verdict = ws4.cell(r, 4).value
        for c in range(1, 5):
            cell = ws4.cell(r, c)
            cell.border = S["BORDER"]
            if r % 2 == 0:
                cell.fill = S["ALT_FILL"]
        if verdict == "PASS":
            ws4.cell(r, 4).fill = S["GREEN_FILL"]
            ws4.cell(r, 4).font = S["GREEN_FONT"]
        elif verdict == "FAIL":
            ws4.cell(r, 4).fill = S["RED_FILL"]
            ws4.cell(r, 4).font = S["RED_FONT"]
    ws4.column_dimensions["A"].width = 44
    for col in "BCD":
        ws4.column_dimensions[col].width = 13

    # --- Sheet 5: v8 Variants (static) ---
    ws5 = wb.create_sheet("v8 Variants")
    ws5.append(["Variant", "Tingkat exact", "MACRO exact", "Eff tok/cert", "LLM calls"])
    v8 = [
        ["b_minimized", "78.4%", "54.4%", "221", "35"],
        ["e_hybrid", "79.7%", "54.7%", "182", "35"],
        ["f_bias (winner)", "82.4%", "55.2%", "214", "35"],
        ["g_evidence", "75.7%", "53.9%", "194", "35"],
        ["layout_md (f_bias)", "77.0%", "50.8%", "235", "-"],
        ["layout_ann (f_bias)", "78.4%", "51.3%", "-", "-"],
    ]
    for r in v8:
        ws5.append(r)
    _style_header(ws5, S, 5)
    _style_rows(ws5, S, len(v8), 5)
    ws5.column_dimensions["A"].width = 22
    for col in "BCDE":
        ws5.column_dimensions[col].width = 13

    # --- Sheet 6: Per-file tingkat (winner run) ---
    winners = [e for e in data["experiments"] if e.get("is_winner")]
    winner = winners[-1] if winners else None
    run_rel = (winner or {}).get("run_dir", "")
    run_path = os.path.join(REPO, run_rel, "results.xlsx") if run_rel else ""
    if run_path and os.path.exists(run_path):
        src = openpyxl.load_workbook(run_path).active
        ws6 = wb.create_sheet("Per-File tingkat")
        hdr = [c.value for c in src[1]]
        keep = ["filename", "f_bias_tingkat_expected", "f_bias_tingkat_actual",
                "f_bias_tingkat_exact", "e_hybrid_tingkat_actual", "e_hybrid_tingkat_exact"]
        idx = {h: hdr.index(h) for h in hdr if h in hdr}
        ws6.append(keep)
        for row in src.iter_rows(min_row=2, values_only=True):
            ws6.append([row[idx[h]] for h in keep])
        _style_header(ws6, S, len(keep))
        for r in range(2, ws6.max_row + 1):
            exact = ws6.cell(r, 4).value
            for c in range(1, len(keep) + 1):
                cell = ws6.cell(r, c)
                cell.border = S["BORDER"]
                if r % 2 == 0:
                    cell.fill = S["ALT_FILL"]
            if exact == 1:
                ws6.cell(r, 4).fill = S["GREEN_FILL"]
                ws6.cell(r, 4).font = S["GREEN_FONT"]
            elif exact == 0:
                ws6.cell(r, 4).fill = S["RED_FILL"]
                ws6.cell(r, 4).font = S["RED_FONT"]
        ws6.column_dimensions["A"].width = 30
        for col in "BCDEF":
            ws6.column_dimensions[col].width = 16

    wb.save(path)


# ---------------------------------------------------------------------------
TITLES = {
    "benchmark_methods": ("Benchmark Methods", "Input, Process, and Output - Certificate Autofill Prototype"),
    "evaluation_methodology": ("Evaluation Methodology Report", "Certificate Autofill Prototype - Benchmark Metrics, Formulas, and Analysis"),
    "phase_v4_methodology": ("Phase v4 Methodology", "Certificate Autofill Prototype - Experiment Methodology and Results"),
    "phase_v4_results_summary": ("Phase v4 Results Summary", "Certificate Autofill Prototype - Numerical Results"),
}


def main():
    global DATA_CACHE
    data = load_data()
    DATA_CACHE = data
    docs = data["documents"]
    for name, blocks in docs.items():
        title, subtitle = TITLES[name]
        render_docx(blocks, os.path.join(OUTDIR, name + ".docx"), title, subtitle)
        render_md(blocks, os.path.join(OUTDIR, name + ".md"), title, subtitle)
        print(f"  {name}.docx + .md")
    render_xlsx(data, os.path.join(OUTDIR, "results_comparison.xlsx"))
    print("  results_comparison.xlsx")
    print("done")


if __name__ == "__main__":
    main()
