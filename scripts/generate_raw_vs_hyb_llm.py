"""Generate raw_vs_pipeline for HYB-LLM — menunjukkan kontribusi LLM.

Sama seperti raw_vs_pipeline, tapi:
- Pipeline = HYB-LLM (router + LLM fallback)
- Tambah kolom: Router Decision, Router Rule, LLM Answer, LLM Match
- Menunjukkan cert mana yang dibantu LLM vs router

Usage:
  python scripts/generate_raw_vs_hyb_llm.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(REPO, "docs", "report")
PER_CERT = os.path.join(REPO, "tests", "benchmark_runs", "hyb_llm_20260821_135619", "per_cert_results.json")
GT_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv")

FIELDS = [
    ("nama_kegiatan_sertifikasi", "Nama Kegiatan Sertifikasi", "Nama Kegiatan"),
    ("waktu_mulai_pelaksanaan", "Waktu Mulai Pelaksanaan", "Tanggal Mulai"),
    ("waktu_selesai_pelaksanaan", "Waktu Selesai Pelaksanaan", "Tanggal Selesai"),
    ("penyelenggara_kegiatan", "Penyelenggara Kegiatan", "Penyelenggara"),
    ("nomor_bukti_fisik_nomor_sertifikasi", "Nomor Bukti Fisik Nomor Sertifikasi", "Nomor Sertifikat"),
    ("tingkat", "Tingkat", "Tingkat"),
]


def load_per_cert():
    with open(PER_CERT) as f:
        return {r["stem"]: r for r in json.load(f)}


def render_xlsx(per_cert):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    GREEN = PatternFill("solid", fgColor="C6EFCE")
    YELLOW = PatternFill("solid", fgColor="FFF2CC")
    RED = PatternFill("solid", fgColor="FFC7CE")
    GRAY = PatternFill("solid", fgColor="F2F2F2")
    BLUE = PatternFill("solid", fgColor="D6EAF8")
    HEADER_FILL = PatternFill("solid", fgColor="1F3864")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=9)
    BASE = Font(size=9)
    MONO = Font(size=8, name="Consolas")
    THIN = Side(style="thin", color="C9D4E4")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "HYB-LLM Raw vs Pipeline"

    # Header
    header = ["filename"]
    for _, _, label in FIELDS:
        header += [f"{label} — HYB-LLM", f"{label} — GT", f"{label} — match"]
    header += ["Router Decision", "Router Rule", "LLM Answer (tingkat)", "LLM Match"]
    ws.append(header)

    # Style header
    for c in range(1, len(header) + 1):
        cell = ws.cell(1, c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
    ws.freeze_panes = "B2"

    # Data rows
    stems = sorted(per_cert.keys())
    llm_correct = 0
    llm_wrong = 0
    llm_routed = 0

    for i, stem in enumerate(stems):
        cert = per_cert[stem]
        is_routed = cert["router_decision"] != "unrouted"

        row = [stem]
        tingkat_verdict = None
        for pipe_field, gt_col, label in FIELDS:
            fv = cert["fields"].get(pipe_field, {})
            pipe_val = fv.get("llm", "")  # Use LLM version
            gt_val = fv.get("gt", "")
            match_status = fv.get("llm_match", "wrong")
            row += [pipe_val, gt_val, match_status.upper()]
            if pipe_field == "tingkat":
                tingkat_verdict = match_status

        # Router columns
        row += [cert["router_decision"], cert["router_rule"]]

        # LLM columns (only for tingkat)
        if is_routed:
            row += ["(router)", "routed"]
            llm_routed += 1
        else:
            llm_answer = cert["fields"].get("tingkat", {}).get("llm", "")
            row += [llm_answer, tingkat_verdict.upper() if tingkat_verdict else "N/A"]
            if tingkat_verdict == "exact":
                llm_correct += 1
            elif tingkat_verdict == "wrong":
                llm_wrong += 1

        ws.append(row)
        r = i + 2

        # Style row
        ws.cell(r, 1).font = BASE
        ws.cell(r, 1).border = BORDER

        for j, (pipe_field, gt_col, label) in enumerate(FIELDS):
            base = 2 + j * 3
            fv = cert["fields"].get(pipe_field, {})
            match_status = fv.get("llm_match", "wrong")
            for k in range(3):
                cell = ws.cell(r, base + k)
                cell.font = BASE
                cell.border = BORDER
                if k == 2:  # match column
                    cell.alignment = Alignment(horizontal="center")
                    cell.fill = {
                        "exact": GREEN, "fuzzy": YELLOW, "wrong": RED,
                    }.get(match_status, GRAY)

        # Router column styling
        router_col = 2 + len(FIELDS) * 3
        router_cell = ws.cell(r, router_col)
        router_cell.font = BASE
        router_cell.border = BORDER
        if is_routed:
            router_cell.fill = GREEN
        else:
            router_cell.fill = GRAY

        # Rule column
        rule_cell = ws.cell(r, router_col + 1)
        rule_cell.font = BASE
        rule_cell.border = BORDER

        # LLM answer column
        llm_col = router_col + 2
        llm_cell = ws.cell(r, llm_col)
        llm_cell.font = BASE
        llm_cell.border = BORDER

        # LLM match column
        llm_match_col = router_col + 3
        llm_match_cell = ws.cell(r, llm_match_col)
        llm_match_cell.font = BASE
        llm_match_cell.border = BORDER
        if not is_routed:
            llm_match_cell.alignment = Alignment(horizontal="center")
            llm_match_cell.fill = {
                "exact": GREEN, "fuzzy": YELLOW, "wrong": RED,
            }.get(tingkat_verdict, GRAY)

    # Column widths
    ws.column_dimensions["A"].width = 45
    for j in range(len(FIELDS)):
        base = 2 + j * 3
        ws.column_dimensions[chr(ord("B") + j * 3)].width = 30  # pipeline
        ws.column_dimensions[chr(ord("B") + j * 3 + 1)].width = 30  # GT
        ws.column_dimensions[chr(ord("B") + j * 3 + 2)].width = 10  # match

    router_start = chr(ord("B") + len(FIELDS) * 3)
    ws.column_dimensions[router_start].width = 20  # Decision
    ws.column_dimensions[chr(ord(router_start) + 1)].width = 18  # Rule
    ws.column_dimensions[chr(ord(router_start) + 2)].width = 25  # LLM Answer
    ws.column_dimensions[chr(ord(router_start) + 3)].width = 12  # LLM Match

    # Legend
    ws.append([])
    ws.append(["Legenda:", "EXACT = hijau, FUZZY = kuning, WRONG = merah"])
    ws.append(["Router:", "hijau = routed (48 cert, tanpa LLM), abu-abu = unrouted (26 cert, pakai LLM)"])
    ws.append(["LLM:", f"correct = {llm_correct}/{llm_routed + llm_correct + llm_wrong} unrouted, "
              f"wrong = {llm_wrong}, routed = {llm_routed} (router handles)"])

    wb.save(os.path.join(OUT, "raw_vs_hyb_llm.xlsx"))
    print(f"raw_vs_hyb_llm.xlsx: {len(stems)} sertifikat")
    print(f"Router: {llm_routed} routed, {llm_correct + llm_wrong} unrouted")
    print(f"LLM: {llm_correct} correct, {llm_wrong} wrong")


def main():
    per_cert = load_per_cert()
    render_xlsx(per_cert)


if __name__ == "__main__":
    main()
