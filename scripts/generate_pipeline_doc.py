"""Generate the "current best pipeline" report (docx + md + xlsx) from
docs/report/pipeline_data.json. Data-driven: update the JSON (version, results,
stages, router_rules, progression) then re-run — the stable output
pipeline_best.docx / .xlsx / .md always reflects the latest best pipeline.

Reuses docx/md renderers from scripts/generate_report.py (no duplication).

Usage:
  uv run python scripts/generate_pipeline_doc.py
"""

import json
import os
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_report import render_docx, render_md  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "docs", "report", "pipeline_data.json")
OUT = os.path.join(REPO, "docs", "report", "pipeline_best")


def load_data() -> dict:
    with open(DATA) as f:
        return json.load(f)


def _kv_table(rows: list[tuple[str, str]]) -> dict:
    return {"h": ["Aspek", "Nilai"], "r": [[k, v] for k, v in rows]}


def build_blocks(d: dict) -> list[dict]:
    exp = d["experiment"]
    llm = d["llm"]
    pr = d["production"]
    tok_per_pct = round(exp["tokens_cert"] / float(exp["macro_exact"].rstrip("%")), 1)
    budget = " / ".join(str(v) for v in llm["budget_chars"].values())

    b = []

    b.append({"t": "h2", "x": "Overview"})
    b.append({"t": "table", "x": _kv_table([
        ("Versi", f"{d['version']} (supersedes {d['supersedes']})"),
        ("Model LLM", d["model"]),
        ("Dataset", d["dataset"]),
        ("Ground Truth", d["gt"]),
        ("Matcher evaluasi", d["matcher"]),
        ("Run benchmark", d["run_dir"]),
    ])})
    b.append({"t": "p", "x": (
        f"Pipeline terbaik saat ini: MACRO exact {exp['macro_exact']} / fuzzy "
        f"{exp['macro_fuzzy']}, tingkat exact {exp['tingkat_exact']}, "
        f"{exp['tokens_cert']} tok/cert, {exp['llm_calls']} LLM calls, "
        f"router {exp['router_coverage']}."
    )})

    b.append({"t": "h2", "x": "Pipeline Flow"})
    b.append({"t": "table", "x": {
        "h": ["Stage", "Komponen", "Modul / Fungsi", "Peran"],
        "r": [[s["stage"], s["name"], f"{s['module']} / {s['fn']}", s["role"]] for s in d["stages"]],
    }})

    for s in d["stages"]:
        b.append({"t": "h3", "x": f"Stage {s['stage']} — {s['name']}"})
        b.append({"t": "p", "x": f"Modul: {s['module']}"})
        b.append({"t": "p", "x": f"Fungsi: {s['fn']}"})
        b.append({"t": "p", "x": s["role"]})

    b.append({"t": "h2", "x": f"Tingkat Router — {len(d['router_rules'])} rules ({exp['router_coverage']})"})
    b.append({"t": "table", "x": {
        "h": ["Rule", "Signals", "Decision"],
        "r": [[r["rule"], r["signals"], r["decision"]] for r in d["router_rules"]],
    }})

    b.append({"t": "h2", "x": "LLM Tingkat (fallback router)"})
    b.append({"t": "table", "x": _kv_table([
        ("Model", llm["model"]),
        ("Prompt", llm["prompt"]),
        ("Temperature / num_predict", f"{llm['temperature']} / {llm['num_predict']}"),
        ("Budget teks (strong/normal/poor_ocr)", budget),
        ("Context fields", ", ".join(llm["context_fields"])),
        ("Host", llm["host"]),
    ])})

    b.append({"t": "h2", "x": f"Results — per-field ({d['gt']} + matcher v2)"})
    b.append({"t": "table", "x": {
        "h": ["Field", "Exact", "Fuzzy"],
        "r": [[r["field"], r["exact"], r["fuzzy"]] for r in d["results"]],
    }})
    b.append({"t": "p", "x": f"MACRO exact {exp['macro_exact']} / fuzzy {exp['macro_fuzzy']}."})

    b.append({"t": "h2", "x": "Cost & Efficiency"})
    b.append({"t": "table", "x": _kv_table([
        ("Effective tokens/cert", str(exp["tokens_cert"])),
        ("LLM calls (74 cert)", str(exp["llm_calls"])),
        ("Router coverage", exp["router_coverage"]),
        ("Tokens per % MACRO", str(tok_per_pct)),
    ])})

    b.append({"t": "h2", "x": "Progression (tingkat & MACRO exact)"})
    b.append({"t": "table", "x": {
        "h": ["Phase", "Method", "Tingkat", "MACRO", "Tok/cert", "Calls"],
        "r": [[p["phase"], p["method"], p["tingkat"], p["macro"], str(p["tok"]), str(p["calls"])] for p in d["progression"]],
    }})

    b.append({"t": "h2", "x": "Production Status"})
    b.append({"t": "table", "x": _kv_table([
        ("Dipromosikan ke produksi", ", ".join(pr["promoted"])),
        ("ENABLE_LLM_TINGKAT", "false (default) — produksi deterministik"),
        ("ENABLE_OCR_NUMBER_2PASS", "false — keputusan deploy-time"),
        ("ENABLE_OCR_FALLBACK", str(pr["enable_ocr_fallback"])),
        ("MACRO scan (produksi, GT v9)", pr["scan_macro_production"]),
        ("Organizer scan (produksi)", pr["scan_organizer_production"]),
    ])})
    b.append({"t": "p", "x": pr["note"]})

    b.append({"t": "h2", "x": "Cara Mengganti saat Best Baru"})
    b.append({"t": "b", "x": [
        "Update docs/report/pipeline_data.json (version, experiment, results, stages, router_rules, progression).",
        "Jalankan: uv run python scripts/generate_pipeline_doc.py",
        "pipeline_best.docx / .xlsx / .md ter-regenerate otomatis. Copy JSON dulu untuk history bila perlu.",
    ]})
    return b


def render_xlsx(d: dict, path: str) -> None:
    exp = d["experiment"]
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Overview"
    ws.append(["Aspek", "Nilai"])
    for k, v in [
        ("Version", d["version"]), ("Label", d["label"]),
        ("Model", d["model"]), ("Dataset", d["dataset"]),
        ("GT", d["gt"]), ("Matcher", d["matcher"]),
        ("Tingkat exact", exp["tingkat_exact"]),
        ("MACRO exact", exp["macro_exact"]), ("MACRO fuzzy", exp["macro_fuzzy"]),
        ("Tokens/cert", exp["tokens_cert"]), ("LLM calls", exp["llm_calls"]),
        ("Router", exp["router_coverage"]),
    ]:
        ws.append([k, v])

    ws2 = wb.create_sheet("Stages")
    ws2.append(["Stage", "Name", "Module", "Function", "Role"])
    for s in d["stages"]:
        ws2.append([s["stage"], s["name"], s["module"], s["fn"], s["role"]])

    ws3 = wb.create_sheet("Router Rules")
    ws3.append(["Rule", "Signals", "Decision"])
    for r in d["router_rules"]:
        ws3.append([r["rule"], r["signals"], r["decision"]])

    ws4 = wb.create_sheet("Field Results")
    ws4.append(["Field", "Exact", "Fuzzy"])
    for r in d["results"]:
        ws4.append([r["field"], r["exact"], r["fuzzy"]])
    ws4.append(["MACRO", exp["macro_exact"], exp["macro_fuzzy"]])

    ws5 = wb.create_sheet("Progression")
    ws5.append(["Phase", "Method", "Tingkat", "MACRO", "Tok/cert", "Calls"])
    for p in d["progression"]:
        ws5.append([p["phase"], p["method"], p["tingkat"], p["macro"], p["tok"], p["calls"]])

    run_xlsx = os.path.join(REPO, d["run_dir"], "results.xlsx")
    if os.path.exists(run_xlsx):
        src = openpyxl.load_workbook(run_xlsx).active
        ws6 = wb.create_sheet("Per-File")
        for row in src.iter_rows(values_only=True):
            ws6.append(["" if c is None else c for c in row])

    wb.save(path)


def main() -> None:
    data = load_data()
    blocks = build_blocks(data)
    title = f"Pipeline {data['version']}"
    subtitle = data["label"]
    render_docx(blocks, OUT + ".docx", title, subtitle)
    render_md(blocks, OUT + ".md", title, subtitle)
    render_xlsx(data, OUT + ".xlsx")
    print(f"  {OUT}.docx / .md / .xlsx")


if __name__ == "__main__":
    main()
