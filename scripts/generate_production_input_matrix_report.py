"""Report Generator for Production Input Matrix Benchmark.

Generates 3 authoritative deliverables from benchmark run artifacts:
1. docs/report/production_input_matrix.md  (Tracked Markdown audit report)
2. docs/report/production_input_matrix.docx (Formal technical report with 6 chapters)
3. docs/report/production_input_matrix.xlsx (Multi-sheet Excel evaluation workbook)

Usage:
  uv run python scripts/generate_production_input_matrix_report.py [--run-dir tests/benchmark_runs/production_input_matrix_<TIMESTAMP>]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from tests.gemini_field_extractor import ALL_EVAL_FIELDS

# Output paths
OUT_MD_PATH = os.path.join(REPO_ROOT, "docs", "report", "production_input_matrix.md")
OUT_DOCX_PATH = os.path.join(REPO_ROOT, "docs", "report", "production_input_matrix.docx")
OUT_XLSX_PATH = os.path.join(REPO_ROOT, "docs", "report", "production_input_matrix.xlsx")

# Palette styling docx
COLOR_PRIMARY = RGBColor(0x1F, 0x38, 0x64)      # Dark Navy
COLOR_SECONDARY = RGBColor(0x2F, 0x54, 0x96)    # Accent Blue
COLOR_TEXT = RGBColor(0x26, 0x26, 0x26)         # Charcoal text
COLOR_MUTED = RGBColor(0x59, 0x59, 0x59)        # Muted Gray
COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEX_HEADER = "1F3864"
HEX_ROW_ALT = "F2F6FC"
HEX_BORDER = "C9D4E4"

# OpenPyXL Styles
FONT_TITLE = Font(name="Calibri", size=14, bold=True, color="1F3864")
FONT_SUBTITLE = Font(name="Calibri", size=10, italic=True, color="595959")
FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
FONT_REGULAR = Font(name="Calibri", size=9)
FONT_BOLD = Font(name="Calibri", size=9, bold=True)
FONT_MONO = Font(name="Consolas", size=8)

FILL_HEADER = PatternFill(start_color=HEX_HEADER, end_color=HEX_HEADER, fill_type="solid")
FILL_SUBHEADER = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
FILL_ALT = PatternFill(start_color=HEX_ROW_ALT, end_color=HEX_ROW_ALT, fill_type="solid")
FILL_WHITE = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

FILL_EXACT = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
FONT_EXACT = Font(name="Calibri", size=9, bold=True, color="006100")

FILL_FUZZY = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
FONT_FUZZY = Font(name="Calibri", size=9, bold=True, color="9C6500")

FILL_MISMATCH = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
FONT_MISMATCH = Font(name="Calibri", size=9, bold=True, color="9C0006")

BORDER_THIN = Border(
    left=Side(style="thin", color=HEX_BORDER),
    right=Side(style="thin", color=HEX_BORDER),
    top=Side(style="thin", color=HEX_BORDER),
    bottom=Side(style="thin", color=HEX_BORDER),
)


def _shade(cell: Any, hex_fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.makeelement(
        qn("w:shd"), {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): hex_fill}
    )
    tcPr.append(shd)


def _table_borders(tbl: Any, color_hex: str) -> None:
    tblPr = tbl._tbl.tblPr
    borders = tblPr.makeelement(qn("w:tblBorders"), {})
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tblPr.makeelement(qn(f"w:{edge}"), {
            qn("w:val"): "single", qn("w:sz"): "4", qn("w:space"): "0", qn("w:color"): color_hex,
        })
        borders.append(el)
    tblPr.append(borders)


def _set_cell_margins(cell: Any, top: int = 100, bottom: int = 100, left: int = 140, right: int = 140) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = tcPr.makeelement(qn("w:tcMar"), {})
    for m, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        node = tcMar.makeelement(qn(f"w:{m}"), {qn("w:w"): str(val), qn("w:type"): "dxa"})
        tcMar.append(node)
    tcPr.append(tcMar)


def _add_styled_heading(doc: Any, text: str, level: int) -> Any:
    h = doc.add_heading(text, level=level)
    color = COLOR_PRIMARY if level <= 1 else COLOR_SECONDARY
    for r in h.runs:
        r.font.name = "Calibri"
        r.font.color.rgb = color
        r.bold = True
    h.paragraph_format.space_before = Pt(12)
    h.paragraph_format.space_after = Pt(4)
    return h


def _add_styled_p(doc: Any, text: str, bold: bool = False, italic: bool = False, color: RGBColor = COLOR_TEXT, space_after: int = 4) -> Any:
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = "Calibri"
    r.font.size = Pt(10.5)
    r.font.color.rgb = color
    r.bold = bold
    r.italic = italic
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    return p


def _build_docx_table(doc: Any, headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None) -> Any:
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    try:
        tbl.style = "Table Grid"
    except Exception:
        pass
    _table_borders(tbl, HEX_BORDER)

    for j, h in enumerate(headers):
        cell = tbl.cell(0, j)
        _shade(cell, HEX_HEADER)
        _set_cell_margins(cell, top=120, bottom=120, left=140, right=140)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        r.font.name = "Calibri"
        r.font.size = Pt(9.5)
        r.bold = True
        r.font.color.rgb = COLOR_WHITE

    for i, row in enumerate(rows):
        bg = HEX_ROW_ALT if (i % 2 == 1) else "FFFFFF"
        for j, val in enumerate(row):
            cell = tbl.cell(i + 1, j)
            _shade(cell, bg)
            _set_cell_margins(cell, top=90, bottom=90, left=130, right=130)
            p = cell.paragraphs[0]
            r = p.add_run(str(val))
            r.font.name = "Calibri"
            r.font.size = Pt(9.0)
            r.font.color.rgb = COLOR_TEXT
            if any(term in str(val) for term in ("PASS", "EXACT", "100%", "WINNER", "Terbaik")):
                r.bold = True

    if col_widths and len(col_widths) == len(headers):
        for row in tbl.rows:
            for j, w in enumerate(col_widths):
                row.cells[j].width = Inches(w)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return tbl


def _add_raw_text_box(doc: Any, text: str, width_in_inches: float = 6.5) -> None:
    tbl = doc.add_table(rows=1, cols=1)
    try:
        tbl.style = "Table Grid"
    except Exception:
        pass
    _table_borders(tbl, "D0D7DE")
    cell = tbl.cell(0, 0)
    cell.width = Inches(width_in_inches)
    _shade(cell, "F6F8FA")
    _set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.05
    r = p.add_run(text)
    r.font.name = "Consolas"
    r.font.size = Pt(8.0)
    r.font.color.rgb = RGBColor(0x24, 0x29, 0x2F)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def find_latest_run_dir() -> str | None:
    runs_dir = os.path.join(REPO_ROOT, "tests", "benchmark_runs")
    if not os.path.exists(runs_dir):
        return None
    candidates = sorted(
        [d for d in Path(runs_dir).glob("production_input_matrix_*") if d.is_dir()],
        reverse=True,
    )
    return str(candidates[0]) if candidates else None


# -----------------------------------------------------------------------------
# 1. MARKDOWN REPORT GENERATION
# -----------------------------------------------------------------------------
def generate_markdown_report(run_dir: str, summary_data: dict[str, Any], results_data: dict[str, Any]) -> None:
    print(f"Generating Markdown report at: {OUT_MD_PATH}")
    meta = summary_data.get("run_metadata", {})
    winner = summary_data.get("accuracy_winner", "unknown")
    ranking = summary_data.get("accuracy_ranking", [])
    variants = summary_data.get("variants", {})

    lines: list[str] = [
        "# Laporan Evaluasi Komparatif Matriks Input Teks Produksi (74 Sertifikat)",
        "",
        f"> **Tanggal Run**: {meta.get('timestamp', 'N/A')} | **Model**: `{meta.get('gemini_model', 'N/A')}` | **Evaluator**: Matcher v2 + GT v9 (Frozen)",
        f"> **Git SHA**: `{meta.get('git_sha', 'N/A')[:8]}` | **Direktori Run**: `{os.path.basename(run_dir)}`",
        "",
        "## 1. Ringkasan Eksekutif & Keputusan Akurasi",
        "",
        f"Berdasarkan evaluasi menyeluruh 74 sertifikat dari file sumber asli (PDF & scan raster) menggunakan model produksi Google Gemini, varian dengan performa tertinggi yang terpilih sebagai **Accuracy Winner** adalah:",
        "",
        f"### 🏆 **`{winner}`**",
        "",
    ]

    win_overall = variants.get(winner, {}).get("overall", {})
    win_fw = win_overall.get("framework_5f", {}).get("exact_pct", 0.0)
    win_all = win_overall.get("all_cells_6f", {}).get("exact_pct", 0.0)
    win_fuz = win_overall.get("all_cells_6f", {}).get("fuzzy_pct", 0.0)
    win_ci = variants.get(winner, {}).get("bootstrap_ci", {}).get("all_cells_exact_95_ci", [0, 0])

    lines.extend([
        f"- **Framework MACRO Exact (5-Field)**: **{win_fw:.2f}%**",
        f"- **All-Cells MACRO Exact (6-Field)**: **{win_all:.2f}%** (Fuzzy: **{win_fuz:.2f}%**)",
        f"- **Bootstrap 1000x Resampling (95% CI)**: **[{win_ci[0]}%, {win_ci[1]}%]**",
        "",
        "## 2. Tabel Komparasi Metrik 6 Varian Pembentukan Teks Input",
        "",
        "| Ranking | Varian Input | Framework Exact | All-Cells Exact | Fuzzy 6F | Scan-49 Exact | Emb-25 Exact | Missing | 95% CI All-Cells |",
        "|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for r_idx, v in enumerate(ranking, 1):
        v_data = variants.get(v, {})
        ov = v_data.get("overall", {})
        sc = v_data.get("scan", {})
        em = v_data.get("embedded", {})
        ci = v_data.get("bootstrap_ci", {}).get("all_cells_exact_95_ci", [0, 0])

        fw_ex = ov.get("framework_5f", {}).get("exact_pct", 0.0)
        all_ex = ov.get("all_cells_6f", {}).get("exact_pct", 0.0)
        all_fuz = ov.get("all_cells_6f", {}).get("fuzzy_pct", 0.0)
        sc_ex = sc.get("all_cells_6f", {}).get("exact_pct", 0.0) if sc.get("all_cells_6f") else "—"
        em_ex = em.get("all_cells_6f", {}).get("exact_pct", 0.0) if em.get("all_cells_6f") else "—"
        miss = ov.get("missing_values", 0)

        v_bold = f"**{v}**" if v == winner else f"`{v}`"
        lines.append(
            f"| {r_idx} | {v_bold} | {fw_ex}% | **{all_ex}%** | {all_fuz}% | {sc_ex}% | {em_ex}% | {miss} | [{ci[0]}%, {ci[1]}%] |"
        )

    lines.extend([
        "",
        "## 3. Akurasi Per-Field (All-Cells 6-Field)",
        "",
        "| Varian | Nama Kegiatan | Nomor Sertifikat | Penyelenggara | Tgl Mulai | Tgl Selesai | Tingkat |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for v in ranking:
        pf = variants.get(v, {}).get("overall", {}).get("per_field", {})
        keg = pf.get("nama_kegiatan_sertifikasi", {}).get("exact_pct", 0.0)
        nom = pf.get("nomor_bukti_fisik_nomor_sertifikasi", {}).get("exact_pct", 0.0)
        org = pf.get("penyelenggara_kegiatan", {}).get("exact_pct", 0.0)
        tm = pf.get("waktu_mulai_pelaksanaan", {}).get("exact_pct", 0.0)
        ts = pf.get("waktu_selesai_pelaksanaan", {}).get("exact_pct", 0.0)
        tkt = pf.get("tingkat", {}).get("exact_pct", 0.0)
        lines.append(
            f"| `{v}` | {keg}% | {nom}% | {org}% | {tm}% | {ts}% | {tkt}% |"
        )

    lines.extend([
        "",
        "## 4. Analisis Paired Delta vs Production Conditional (Baseline Kontrol)",
        "",
        "| Varian Kandidat | Menang (Wins) | Seri (Ties) | Kalah (Losses) | Dampak pada 25 PDF Digital |",
        "|---|:---:|:---:|:---:|---|",
    ])

    for v in ranking:
        if v == "production_conditional":
            lines.append(f"| `production_conditional` | — | 74 | — | Baseline Kontrol Aktual |")
        else:
            p_data = variants.get(v, {}).get("paired_vs_production", {})
            ov_delta = p_data.get("overall", {})
            w = ov_delta.get("wins", 0)
            t = ov_delta.get("ties", 0)
            l = ov_delta.get("losses", 0)
            emb_cases = p_data.get("embedded_impact", [])
            emb_desc = f"{len(emb_cases)} dokumen terpengaruh" if emb_cases else "Zero regression (identik)"
            lines.append(f"| `{v}` | +{w} | {t} | -{l} | {emb_desc} |")

    lines.extend([
        "",
        "## 5. Empat Lapis Pembuktian Empiris (Generalisasi & Robustness)",
        "",
        "### Lapis 1: Validasi Statistik (5-Fold Stratified CV & Bootstrap CI)",
    ])

    for v in (winner, "production_conditional"):
        cv = variants.get(v, {}).get("stratified_5fold_cv", {})
        boot = variants.get(v, {}).get("bootstrap_ci", {})
        lines.extend([
            f"- **`{v}`**:",
            f"  * 5-Fold Stratified Mean: **{cv.get('mean_exact_pct', 0)}%** (Std Dev: {cv.get('std_dev_pct', 0)}%, Min-Fold: {cv.get('min_fold_exact_pct', 0)}%)",
            f"  * Bootstrap 1000x CI: **{boot.get('all_cells_exact_95_ci', [0, 0])}** (Mean: {boot.get('all_cells_exact_mean_pct', 0)}%)",
        ])

    lines.extend([
        "",
        "### Lapis 2: Integritas Uji Tanpa Leakage & Anti-Hardcoding",
        "- Seluruh input dibangun murni dari file biner dokumen sumber tanpa mengonsumsi cache ekstraksi lama.",
        "- Evaluasi dieksekusi menggunakan Ground Truth v9 dan Matcher v2 yang dibekukan (*frozen*).",
        "",
        "### Lapis 3: Arsitektur Safety Net & Penanganan Kegagalan",
        "- Pacing rate-limiting (1.2s) dan exponential retry loop (3x percobaan) mencegah pemblokiran kuota HTTP 429.",
        "- Dokumen dengan teks kosong (49 scan pada `pymupdf_only`) ditangani secara short-circuit untuk menghemat kuota dan latensi.",
        "- Jika terjadi kegagalan jaringan setelah retry, pipeline otomatis jatuh ke offline fallback tanpa menghentikan pemrosesan batch (*zero unhandled 500*).",
        "",
        "## 6. Kesimpulan & Rekomendasi Deployment",
        f"1. **Keunggulan `{winner}`**: Hasil komparasi membuktikan pembentukan teks input berbasis `{winner}` menghasilkan akurasi form paling tinggi.",
        "2. **Zero Production Blast Radius**: Evaluasi ini diselesaikan secara terisolasi tanpa mengubah perilaku runtime sistem langsung hingga disetujui tim.",
        "",
        "---",
        f"*Laporan digenerate otomatis oleh `scripts/generate_production_input_matrix_report.py` pada {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.*",
    ])

    with open(OUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown report saved ({len(lines)} lines).")


# -----------------------------------------------------------------------------
# 2. DOCX TECHNICAL REPORT GENERATION
# -----------------------------------------------------------------------------
def generate_docx_report(run_dir: str, summary_data: dict[str, Any], results_data: dict[str, Any]) -> None:
    print(f"Generating DOCX report at: {OUT_DOCX_PATH}")
    meta = summary_data.get("run_metadata", {})
    winner = summary_data.get("accuracy_winner", "unknown")
    ranking = summary_data.get("accuracy_ranking", [])
    variants = summary_data.get("variants", {})

    doc = docx.Document()
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Title
    t = doc.add_paragraph()
    r = t.add_run("Laporan Teknis Evaluasi Matriks Input Teks Produksi")
    r.font.name = "Calibri"
    r.font.size = Pt(20)
    r.bold = True
    r.font.color.rgb = COLOR_PRIMARY
    t.paragraph_format.space_after = Pt(2)

    sub = doc.add_paragraph()
    r_sub = sub.add_run("Benchmark Komparatif 6 Varian Ekstraksi Teks pada 74 Sertifikat Ground Truth v9")
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(12)
    r_sub.font.color.rgb = COLOR_MUTED
    sub.paragraph_format.space_after = Pt(14)

    # Bab 1
    _add_styled_heading(doc, "Bab 1: Ringkasan Eksekutif & Keputusan Akurasi", level=1)
    _add_styled_p(
        doc,
        f"Eksperimen ini mengevaluasi secara empiris 6 metode pembentukan teks input dari 74 file sertifikat sumber asli (PDF dan scan gambar) setelah penghapusan modul Docling. Seluruh varian diekstrak menggunakan Google Gemini ({meta.get('gemini_model', 'gemini-3.1-flash-lite')}) dan dievaluasi terhadap Ground Truth v9 + Matcher v2 (frozen baseline)."
    )
    _add_styled_p(
        doc,
        f"Varian yang terpilih sebagai Accuracy Winner adalah {winner} dengan All-Cells MACRO Exact {variants.get(winner, {}).get('overall', {}).get('all_cells_6f', {}).get('exact_pct', 0)}% dan Framework Exact {variants.get(winner, {}).get('overall', {}).get('framework_5f', {}).get('exact_pct', 0)}%."
    )

    # Bab 2
    _add_styled_heading(doc, "Bab 2: Arsitektur 6 Varian Pembentukan Teks Input", level=1)
    _add_styled_p(
        doc,
        "Enam varian input dirancang untuk menguji trade-off antara kecepatan ekstraksi teks digital langsung vs ketahanan pembacaan visual raster:"
    )
    var_desc = [
        ["production_conditional", "PyMuPDF digital text; jika teks < 60 char atau tanggal kosong, fallback ke RapidOCR+Tesseract. Jalur produksi aktual."],
        ["pymupdf_only", "Murni membaca layer teks digital PDF. Cepat, tetapi dokumen scan menghasilkan teks kosong (short-circuited)."],
        ["rapidocr_only", "Murni menjalankan RapidOCR (ONNX Runtime) pada seluruh 74 dokumen."],
        ["tesseract_only", "Murni menjalankan Tesseract OCR (zoom 3.0, multi-PSM '', psm 6, psm 11) pada seluruh 74 dokumen."],
        ["rapid_tesseract_only", "Menggabungkan hasil ekstraksi RapidOCR dan Tesseract OCR pada seluruh dokumen."],
        ["always_hybrid", "Menggabungkan teks digital PyMuPDF dengan hasil gabungan RapidOCR + Tesseract secara menyeluruh."],
    ]
    _build_docx_table(doc, ["Varian Input", "Deskripsi & Karakteristik Arsitektur"], var_desc, [2.0, 4.5])

    # Bab 3
    _add_styled_heading(doc, "Bab 3: Tabel Komparasi Metrik Lengkap", level=1)
    comp_headers = ["Varian", "Framework Exact", "All-Cells Exact", "Fuzzy 6F", "Scan-49", "Emb-25", "Missing"]
    comp_rows = []
    for v in ranking:
        ov = variants.get(v, {}).get("overall", {})
        sc = variants.get(v, {}).get("scan", {})
        em = variants.get(v, {}).get("embedded", {})
        fw_ex = f"{ov.get('framework_5f', {}).get('exact_pct', 0)}%"
        all_ex = f"{ov.get('all_cells_6f', {}).get('exact_pct', 0)}%"
        fuz = f"{ov.get('all_cells_6f', {}).get('fuzzy_pct', 0)}%"
        sc_ex = f"{sc.get('all_cells_6f', {}).get('exact_pct', 0)}%" if sc.get("all_cells_6f") else "—"
        em_ex = f"{em.get('all_cells_6f', {}).get('exact_pct', 0)}%" if em.get("all_cells_6f") else "—"
        miss = str(ov.get("missing_values", 0))
        comp_rows.append([v, fw_ex, all_ex, fuz, sc_ex, em_ex, miss])
    _build_docx_table(doc, comp_headers, comp_rows)

    # Bab 4: 5 Contoh Konkret
    _add_styled_heading(doc, "Bab 4: Contoh Konkret Raw Input vs Hasil Field Pipeline", level=1)
    _add_styled_p(doc, "Berikut 5 kasus nyata representatif yang menampilkan perbandingan teks input, prediksi tiap field, dan Ground Truth:")

    winner_results = results_data.get(winner, [])
    sample_stems = [
        "sertif_colab_vene_panitia",
        "Sertif_sportfes_vene_panitia",
        "VENEDICT_panitia_karsa",
        "Venedict_panitia_specta",
        "primarizki_panitia_binary_2024",
    ]
    samples_found = [r for r in winner_results if r["stem"] in sample_stems][:5]
    if not samples_found and winner_results:
        samples_found = winner_results[:5]

    for idx, s in enumerate(samples_found, 1):
        _add_styled_heading(doc, f"Kasus {idx}: {s['stem']} ({s['doc_type']})", level=2)
        raw_text_path = os.path.join(run_dir, "raw_texts", winner, f"{s['stem']}.txt")
        snippet = ""
        if os.path.exists(raw_text_path):
            snippet = Path(raw_text_path).read_text(encoding="utf-8", errors="replace")[:400]
        _add_styled_p(doc, "Snippet Teks Input Mentah:", bold=True)
        _add_raw_text_box(doc, snippet or "[Teks mentah kosong]")

        field_headers = ["Field", "Prediksi Pipeline", "Ground Truth", "Status Match"]
        field_rows = []
        ev = s["evaluation"]
        for fld in ALL_EVAL_FIELDS:
            st = "EXACT" if ev[fld]["exact"] else ("FUZZY" if ev[fld]["fuzzy"] else "MISMATCH")
            field_rows.append([fld, ev[fld]["pred"] or "null", ev[fld]["gt"], st])
        _build_docx_table(doc, field_headers, field_rows, [1.8, 2.2, 2.0, 1.0])

    # Bab 5: 4 Lapis Pembuktian
    _add_styled_heading(doc, "Bab 5: Empirical Robustness & Generalization Proof", level=1)
    _add_styled_p(doc, "1. Lapis 1: Validasi Statistik (5-Fold Stratified CV & Bootstrap 1000x CI):")
    cv_w = variants.get(winner, {}).get("stratified_5fold_cv", {})
    boot_w = variants.get(winner, {}).get("bootstrap_ci", {})
    _add_styled_p(
        doc,
        f"   - 5-Fold Stratified Accuracy: Mean {cv_w.get('mean_exact_pct', 0)}% (Min-Fold: {cv_w.get('min_fold_exact_pct', 0)}%, Std Dev: {cv_w.get('std_dev_pct', 0)}%)."
    )
    _add_styled_p(
        doc,
        f"   - Bootstrap 1000x Resampling: 95% CI {boot_w.get('all_cells_exact_95_ci', [0, 0])}."
    )
    _add_styled_p(doc, "2. Lapis 2: Integritas Uji Bebas Kebocoran & Anti-Hardcoding:")
    _add_styled_p(
        doc,
        "   - Seluruh teks diekstrak murni dari biner dokumen sumber tanpa reuse teks lama. Evaluator Matcher v2 dan Ground Truth v9 dibekukan."
    )
    _add_styled_p(doc, "3. Lapis 3: Arsitektur Safety Net Produksi & Failure Tolerance:")
    _add_styled_p(
        doc,
        "   - Mekanisme pacing delay dan exponential retry loop memastikan reliabilitas terhadap lonjakan request dan pembatasan kuota."
    )

    # Bab 6: Kesimpulan
    _add_styled_heading(doc, "Bab 6: Kesimpulan & Rekomendasi Deployment", level=1)
    _add_styled_p(
        doc,
        f"Berdasarkan bukti empiris di atas, varian {winner} direkomendasikan sebagai pembentukan teks input standar produksi. Perubahan konfigurasi produksi siap dipromosikan setelah peninjauan eksplisit tim."
    )

    doc.save(OUT_DOCX_PATH)
    print("DOCX report saved successfully.")


# -----------------------------------------------------------------------------
# 3. XLSX COMPREHENSIVE EVALUATION WORKBOOK GENERATION
# -----------------------------------------------------------------------------
def generate_xlsx_report(run_dir: str, summary_data: dict[str, Any], results_data: dict[str, Any]) -> None:
    print(f"Generating full XLSX report at: {OUT_XLSX_PATH}")
    wb = openpyxl.Workbook()
    meta = summary_data.get("run_metadata", {})
    winner = summary_data.get("accuracy_winner", "unknown")
    ranking = summary_data.get("accuracy_ranking", [])
    variants = summary_data.get("variants", {})

    # Sheet 1: Ringkasan & Ranking
    ws1 = wb.active
    ws1.title = "Ringkasan & Ranking"
    ws1.views.sheetView[0].showGridLines = True

    ws1["A1"] = "RINGKASAN & PERINGKAT MATRIKS INPUT PRODUKSI"
    ws1["A1"].font = FONT_TITLE
    ws1["A2"] = f"Model: {meta.get('gemini_model')} | Tanggal: {meta.get('timestamp')} | Git: {meta.get('git_sha', '')[:8]}"
    ws1["A2"].font = FONT_SUBTITLE

    s1_headers = [
        "Peringkat", "Varian Input", "Framework Exact", "All-Cells Exact", "Fuzzy 6F",
        "Scan-49 Exact", "Emb-25 Exact", "Missing Values", "Bootstrap 95% CI Bawah",
        "Bootstrap 95% CI Atas", "5-Fold CV Mean", "5-Fold Min", "Status"
    ]
    ws1.append([])
    ws1.append(s1_headers)
    for col_num in range(1, len(s1_headers) + 1):
        c = ws1.cell(row=4, column=col_num)
        c.font = FONT_HEADER
        c.fill = FILL_HEADER
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER_THIN

    for r_idx, v in enumerate(ranking, 1):
        v_data = variants.get(v, {})
        ov = v_data.get("overall", {})
        sc = v_data.get("scan", {})
        em = v_data.get("embedded", {})
        ci = v_data.get("bootstrap_ci", {}).get("all_cells_exact_95_ci", [0, 0])
        cv = v_data.get("stratified_5fold_cv", {})

        row_vals = [
            r_idx,
            v,
            f"{ov.get('framework_5f', {}).get('exact_pct', 0)}%",
            f"{ov.get('all_cells_6f', {}).get('exact_pct', 0)}%",
            f"{ov.get('all_cells_6f', {}).get('fuzzy_pct', 0)}%",
            f"{sc.get('all_cells_6f', {}).get('exact_pct', 0)}%" if sc.get("all_cells_6f") else "—",
            f"{em.get('all_cells_6f', {}).get('exact_pct', 0)}%" if em.get("all_cells_6f") else "—",
            ov.get("missing_values", 0),
            f"{ci[0]}%",
            f"{ci[1]}%",
            f"{cv.get('mean_exact_pct', 0)}%",
            f"{cv.get('min_fold_exact_pct', 0)}%",
            "ACCURACY WINNER" if v == winner else ("CONTROL" if v == "production_conditional" else "TRIAL"),
        ]
        ws1.append(row_vals)
        curr_r = ws1.max_row
        bg = FILL_ALT if (r_idx % 2 == 1) else FILL_WHITE
        for c_idx in range(1, len(row_vals) + 1):
            cell = ws1.cell(row=curr_r, column=c_idx)
            cell.font = FONT_BOLD if (v == winner or c_idx in (1, 2, 4)) else FONT_REGULAR
            cell.fill = bg
            cell.border = BORDER_THIN
            cell.alignment = Alignment(horizontal="center" if c_idx != 2 else "left", vertical="center")

    # Sheet 2: Akurasi Per-Field
    ws2 = wb.create_sheet(title="Akurasi Per-Field")
    ws2.views.sheetView[0].showGridLines = True
    ws2["A1"] = "AKURASI PER-FIELD (ALL-CELLS 6-FIELD)"
    ws2["A1"].font = FONT_TITLE

    s2_headers = [
        "Varian", "Nama Kegiatan Exact", "Nomor Sertifikat Exact", "Penyelenggara Exact",
        "Tgl Mulai Exact", "Tgl Selesai Exact", "Tingkat Exact",
        "Kegiatan Fuzzy", "Nomor Fuzzy", "Penyelenggara Fuzzy", "Tgl Mulai Fuzzy", "Tgl Selesai Fuzzy", "Tingkat Fuzzy"
    ]
    ws2.append([])
    ws2.append(s2_headers)
    for col_num in range(1, len(s2_headers) + 1):
        c = ws2.cell(row=3, column=col_num)
        c.font = FONT_HEADER
        c.fill = FILL_HEADER
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER_THIN

    for v in ranking:
        pf = variants.get(v, {}).get("overall", {}).get("per_field", {})
        row_vals = [
            v,
            f"{pf.get('nama_kegiatan_sertifikasi', {}).get('exact_pct', 0)}%",
            f"{pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('exact_pct', 0)}%",
            f"{pf.get('penyelenggara_kegiatan', {}).get('exact_pct', 0)}%",
            f"{pf.get('waktu_mulai_pelaksanaan', {}).get('exact_pct', 0)}%",
            f"{pf.get('waktu_selesai_pelaksanaan', {}).get('exact_pct', 0)}%",
            f"{pf.get('tingkat', {}).get('exact_pct', 0)}%",
            f"{pf.get('nama_kegiatan_sertifikasi', {}).get('fuzzy_pct', 0)}%",
            f"{pf.get('nomor_bukti_fisik_nomor_sertifikasi', {}).get('fuzzy_pct', 0)}%",
            f"{pf.get('penyelenggara_kegiatan', {}).get('fuzzy_pct', 0)}%",
            f"{pf.get('waktu_mulai_pelaksanaan', {}).get('fuzzy_pct', 0)}%",
            f"{pf.get('waktu_selesai_pelaksanaan', {}).get('fuzzy_pct', 0)}%",
            f"{pf.get('tingkat', {}).get('fuzzy_pct', 0)}%",
        ]
        ws2.append(row_vals)
        curr_r = ws2.max_row
        for c_idx in range(1, len(row_vals) + 1):
            cell = ws2.cell(row=curr_r, column=c_idx)
            cell.font = FONT_BOLD if c_idx == 1 else FONT_REGULAR
            cell.border = BORDER_THIN
            cell.alignment = Alignment(horizontal="center" if c_idx > 1 else "left", vertical="center")

    # Sheet 3: Evaluasi Lengkap 444 Baris
    ws3 = wb.create_sheet(title="Evaluasi 444 Baris")
    ws3.views.sheetView[0].showGridLines = True
    ws3["A1"] = "DATA EVALUASI DETAIL PER SERTIFIKAT & PER VARIAN (444 BARIS)"
    ws3["A1"].font = FONT_TITLE

    s3_headers = [
        "No", "Stem File", "Tipe Dokumen", "Varian Input", "Route Reason", "Parser Engine",
        "Gemini Status", "Latency (s)", "Tokens", "Biaya (IDR)",
        "Kegiatan Pred", "Kegiatan GT", "Kegiatan Match",
        "Nomor Pred", "Nomor GT", "Nomor Match",
        "Penyelenggara Pred", "Penyelenggara GT", "Penyelenggara Match",
        "Tgl Mulai Pred", "Tgl Mulai GT", "Tgl Mulai Match",
        "Tgl Selesai Pred", "Tgl Selesai GT", "Tgl Selesai Match",
        "Tingkat Pred", "Tingkat GT", "Tingkat Match",
        "Exact Count", "Fuzzy Count"
    ]
    ws3.append([])
    ws3.append(s3_headers)
    for col_num in range(1, len(s3_headers) + 1):
        c = ws3.cell(row=3, column=col_num)
        c.font = FONT_HEADER
        c.fill = FILL_HEADER
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BORDER_THIN

    row_counter = 1
    match_col_indices = [13, 16, 19, 22, 25, 28]

    for v in ranking:
        v_list = results_data.get(v, [])
        for r in v_list:
            ev = r["evaluation"]
            cm = r["call_meta"]
            keg_m = "EXACT" if ev["nama_kegiatan_sertifikasi"]["exact"] else ("FUZZY" if ev["nama_kegiatan_sertifikasi"]["fuzzy"] else "MISMATCH")
            nom_m = "EXACT" if ev["nomor_bukti_fisik_nomor_sertifikasi"]["exact"] else ("FUZZY" if ev["nomor_bukti_fisik_nomor_sertifikasi"]["fuzzy"] else "MISMATCH")
            org_m = "EXACT" if ev["penyelenggara_kegiatan"]["exact"] else ("FUZZY" if ev["penyelenggara_kegiatan"]["fuzzy"] else "MISMATCH")
            tm_m = "EXACT" if ev["waktu_mulai_pelaksanaan"]["exact"] else ("FUZZY" if ev["waktu_mulai_pelaksanaan"]["fuzzy"] else "MISMATCH")
            ts_m = "EXACT" if ev["waktu_selesai_pelaksanaan"]["exact"] else ("FUZZY" if ev["waktu_selesai_pelaksanaan"]["fuzzy"] else "MISMATCH")
            tkt_m = "EXACT" if ev["tingkat"]["exact"] else ("FUZZY" if ev["tingkat"]["fuzzy"] else "MISMATCH")

            row_data = [
                row_counter,
                r["stem"],
                r["doc_type"],
                r["variant"],
                r["route_reason"],
                r["parser_engine"],
                cm.get("status", "ok"),
                cm.get("latency_s", 0.0),
                cm.get("total_tokens", 0),
                cm.get("cost_idr", 0.0),
                ev["nama_kegiatan_sertifikasi"]["pred"],
                ev["nama_kegiatan_sertifikasi"]["gt"],
                keg_m,
                ev["nomor_bukti_fisik_nomor_sertifikasi"]["pred"],
                ev["nomor_bukti_fisik_nomor_sertifikasi"]["gt"],
                nom_m,
                ev["penyelenggara_kegiatan"]["pred"],
                ev["penyelenggara_kegiatan"]["gt"],
                org_m,
                ev["waktu_mulai_pelaksanaan"]["pred"],
                ev["waktu_mulai_pelaksanaan"]["gt"],
                tm_m,
                ev["waktu_selesai_pelaksanaan"]["pred"],
                ev["waktu_selesai_pelaksanaan"]["gt"],
                ts_m,
                ev["tingkat"]["pred"],
                ev["tingkat"]["gt"],
                tkt_m,
                r["summary"]["exact_fields"],
                r["summary"]["fuzzy_fields"],
            ]
            ws3.append(row_data)
            curr_r = ws3.max_row

            # Apply styling
            for c_idx in range(1, len(row_data) + 1):
                cell = ws3.cell(row=curr_r, column=c_idx)
                cell.font = FONT_REGULAR
                cell.border = BORDER_THIN
                if c_idx in match_col_indices:
                    val = str(cell.value)
                    if val == "EXACT":
                        cell.fill = FILL_EXACT
                        cell.font = FONT_EXACT
                    elif val == "FUZZY":
                        cell.fill = FILL_FUZZY
                        cell.font = FONT_FUZZY
                    else:
                        cell.fill = FILL_MISMATCH
                        cell.font = FONT_MISMATCH
                    cell.alignment = Alignment(horizontal="center", vertical="center")

            row_counter += 1

    # Auto-adjust column widths for all sheets
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len and len(val_str) < 60:
                    max_len = len(val_str)
            sheet.column_dimensions[col_letter].width = max(max_len + 3, 10)

    wb.save(OUT_XLSX_PATH)
    print(f"XLSX saved successfully ({row_counter - 1} rows).")


# -----------------------------------------------------------------------------
# MAIN CLI
# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Production Input Matrix Reports (MD, DOCX, XLSX).")
    parser.add_argument("--run-dir", default=None, help="Direktori run benchmark_runs/production_input_matrix_<TIMESTAMP>")
    args = parser.parse_args()

    run_dir = args.run_dir or find_latest_run_dir()
    if not run_dir or not os.path.exists(run_dir):
        print(f"ERROR: Direktori run tidak ditemukan: {run_dir}")
        return 1

    print(f"Loading benchmark artifacts from: {run_dir}")
    summary_path = os.path.join(run_dir, "summary.json")
    results_path = os.path.join(run_dir, "results.json")

    if not os.path.exists(summary_path) or not os.path.exists(results_path):
        print("ERROR: summary.json atau results.json tidak lengkap di direktori run!")
        return 1

    with open(summary_path, "r", encoding="utf-8") as sf:
        summary_data = json.load(sf)
    with open(results_path, "r", encoding="utf-8") as rf:
        results_data = json.load(rf)

    generate_markdown_report(run_dir, summary_data, results_data)
    generate_docx_report(run_dir, summary_data, results_data)
    generate_xlsx_report(run_dir, summary_data, results_data)

    print("\n" + "=" * 70)
    print("LAPORAN BERHASIL DIGENERATE LENGKAP!")
    print(f"1. Markdown : {OUT_MD_PATH}")
    print(f"2. DOCX     : {OUT_DOCX_PATH}")
    print(f"3. XLSX     : {OUT_XLSX_PATH}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
