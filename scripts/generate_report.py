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

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "docs", "report", "report_data.json")
OUTDIR = os.path.join(REPO, "docs", "report")

BLUE = RGBColor(0x2F, 0x54, 0x96)


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
def render_docx(blocks: list[dict], path: str, title: str, subtitle: str):
    doc = docx.Document()
    styles = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(11)

    t = doc.add_heading(title, level=0)
    for run in t.runs:
        run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    if subtitle:
        sp = doc.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = sp.add_run(subtitle)
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    doc.add_paragraph()

    for blk in blocks:
        kind = blk["t"]
        x = blk["x"]
        if kind == "h1":
            doc.add_heading(x, level=1)
        elif kind == "h2":
            doc.add_heading(x, level=2)
        elif kind == "h3":
            doc.add_heading(x, level=3)
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
            hdr, rows = x["h"], x["r"]
            tbl = doc.add_table(rows=1 + len(rows), cols=len(hdr))
            try:
                tbl.style = "Table Grid"
            except KeyError:
                pass
            for j, cell in enumerate(hdr):
                c = tbl.cell(0, j)
                c.text = ""
                r = c.paragraphs[0].add_run(str(cell))
                r.bold = True
                r.font.size = Pt(9)
            for i, row in enumerate(rows):
                for j, val in enumerate(row):
                    c = tbl.cell(i + 1, j)
                    c.text = ""
                    r = c.paragraphs[0].add_run(str(val).replace("**", ""))
                    r.font.size = Pt(9)
            doc.add_paragraph()
        elif kind == "auto":
            tbl_data = resolve_auto(x, DATA_CACHE)
            render_docx_table(doc, tbl_data)
    doc.save(path)


def render_docx_table(doc, tbl_data: dict):
    hdr, rows = tbl_data["h"], tbl_data["r"]
    tbl = doc.add_table(rows=1 + len(rows), cols=len(hdr))
    try:
        tbl.style = "Table Grid"
    except KeyError:
        pass
    for j, cell in enumerate(hdr):
        c = tbl.cell(0, j)
        c.text = ""
        r = c.paragraphs[0].add_run(str(cell))
        r.bold = True
        r.font.size = Pt(9)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = tbl.cell(i + 1, j)
            c.text = ""
            r = c.paragraphs[0].add_run(str(val).replace("**", ""))
            r.font.size = Pt(9)
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
# XLSX for results summary
# ---------------------------------------------------------------------------
def render_xlsx(data: dict, path: str):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results Summary"
    t = results_table(data)
    ws.append(t["h"])
    for r in t["r"]:
        ws.append([str(v).replace("**", "") for v in r])

    ws2 = wb.create_sheet("Progression")
    p = progression_table(data)
    ws2.append(p["h"])
    for r in p["r"]:
        ws2.append([str(v).replace("**", "") for v in r])

    # Per-file sheet from the winning experiment's run dir (if present).
    # Source run didefinisikan di report_data.json (field `run_dir`), bukan
    # hardcoded di sini — mencegah drift ke run yang bukan otoritatif.
    # Ambil winner TERAKHIR (array eksperimen kronologis; bisa ada >1 winner).
    winners = [e for e in data["experiments"] if e.get("is_winner")]
    winner = winners[-1] if winners else None
    run_rel = (winner or {}).get("run_dir", "")
    run_path = os.path.join(REPO, run_rel, "results.xlsx") if run_rel else ""
    if run_path and os.path.exists(run_path):
        src = openpyxl.load_workbook(run_path).active
        ws3 = wb.create_sheet("v8 Per-File f_bias")
        hdr = [c.value for c in src[1]]
        keep = ["filename", "f_bias_tingkat_expected", "f_bias_tingkat_actual",
                "f_bias_tingkat_exact", "e_hybrid_tingkat_actual", "e_hybrid_tingkat_exact"]
        idx = {h: hdr.index(h) for h in hdr if h in hdr}
        ws3.append(keep)
        for row in src.iter_rows(min_row=2, values_only=True):
            ws3.append([row[idx[h]] for h in keep])

    # v8 variants static
    ws4 = wb.create_sheet("v8 Variants")
    ws4.append(["Variant", "Tingkat exact", "MACRO exact", "Eff tok/cert", "LLM calls"])
    v8 = [
        ["b_minimized", "78.4%", "54.4%", "221", "35"],
        ["e_hybrid", "79.7%", "54.7%", "182", "35"],
        ["f_bias (winner)", "82.4%", "55.2%", "214", "35"],
        ["g_evidence", "75.7%", "53.9%", "194", "35"],
        ["layout_md (f_bias)", "77.0%", "50.8%", "235", "-"],
        ["layout_ann (f_bias)", "78.4%", "51.3%", "-", "-"],
    ]
    for r in v8:
        ws4.append(r)
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
    render_xlsx(data, os.path.join(OUTDIR, "phase_v4_results_summary.xlsx"))
    print("  phase_v4_results_summary.xlsx")
    print("done")


if __name__ == "__main__":
    main()
