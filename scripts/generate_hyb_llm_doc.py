"""Generate HYB-LLM pipeline report (docx + md) — gabungan terbaik dengan LLM.

Output:
- docs/report/hyb_llm_pipeline.docx
- docs/report/hyb_llm_pipeline.md

Usage:
  python scripts/generate_hyb_llm_doc.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_report import render_docx, render_md

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(REPO, "docs", "report")
PER_CERT = os.path.join(REPO, "tests", "benchmark_runs", "hyb_llm_20260821_135619", "per_cert_results.json")
SUMMARY = os.path.join(REPO, "tests", "benchmark_runs", "hyb_llm_20260821_135619", "summary_hybrid_llm.json")


def load_data():
    with open(PER_CERT) as f:
        per_cert = json.load(f)
    with open(SUMMARY) as f:
        summary = json.load(f)
    return per_cert, summary


def build_blocks(per_cert, summary):
    b = []

    # Overview
    b.append({"t": "h1", "x": "HYB-LLM Pipeline"})
    b.append({"t": "p", "x": "Hybrid pipeline dengan LLM fallback untuk 26 cert unrouted. Gabungan terbaik dari semua improvements: router rules (tingkat), AKT-005 (nama kegiatan), ORG-004 (organizer), PROD-002 (nomor)."})

    b.append({"t": "h2", "x": "Overview"})
    b.append({"t": "table", "x": {"h": ["Aspek", "Nilai"], "r": [
        ["Versi", "HYB-LLM (supersedes HYB-COMBINED)"],
        ["Model LLM", "llama3.1:8b (Ollama, Q4_K_M)"],
        ["Dataset", "74 sertifikat mahasiswa (Universitas Airlangga)"],
        ["Ground Truth", "Ground_Truth_Sertifikat_v9.csv"],
        ["Matcher evaluasi", "v2 (abbr subsequence + rasio kata, anti false-positive)"],
        ["Run benchmark", "tests/benchmark_runs/hyb_llm_20260821_135619"],
    ]}})

    # Results
    b.append({"t": "h2", "x": "Results — per-field"})
    b.append({"t": "table", "x": {"h": ["Field", "Exact", "Fuzzy"], "r": [
        ["nama_kegiatan_sertifikasi", "62.2%", "81.1%"],
        ["waktu_mulai_pelaksanaan", "81.8%", "81.8%"],
        ["waktu_selesai_pelaksanaan", "81.8%", "81.8%"],
        ["penyelenggara_kegiatan", "63.5%", "78.4%"],
        ["nomor_bukti_fisik_nomor_sertifikasi", "76.9%", "76.9%"],
        ["tingkat", "83.8%", "83.8%"],
        ["MACRO", "74.2%", "80.7%"],
    ]}})

    # Router + LLM stats
    llm_stats = summary.get("llm_stats", {})
    b.append({"t": "h2", "x": "Router + LLM Stats"})
    b.append({"t": "table", "x": {"h": ["Metrik", "Nilai"], "r": [
        ["Router coverage", "48/74 @100% precision"],
        ["Unrouted (need LLM)", str(llm_stats.get("unrouted", 26))],
        ["LLM correct", f"{llm_stats.get('correct', 15)}/{llm_stats.get('unrouted', 26)} ({llm_stats.get('accuracy', 0)*100:.1f}%)"],
        ["LLM wrong", str(llm_stats.get("wrong", 11))],
        ["LLM time", f"{llm_stats.get('total_time_s', 0):.1f}s total, {llm_stats.get('avg_time_s', 0):.1f}s/cert"],
        ["Tokens/cert", "~176 (untuk 26 cert unrouted)"],
        ["Total LLM calls", "26"],
    ]}})

    # Comparison with previous
    b.append({"t": "h2", "x": "Comparison with Previous Pipelines"})
    b.append({"t": "table", "x": {"h": ["Pipeline", "MACRO", "Tingkat", "LLM Calls", "Status"], "r": [
        ["v9 (baseline)", "60.2%", "83.8%", "29", "Old winner"],
        ["HYB-COMBINED (offline)", "73.7%", "81.1%", "0", "Best offline"],
        ["HYB-LLM (this)", "74.2%", "83.8%", "26", "NEW WINNER"],
    ]}})

    # Pipeline flow
    b.append({"t": "h2", "x": "Pipeline Flow"})
    b.append({"t": "table", "x": {"h": ["Stage", "Komponen", "Peran"], "r": [
        ["1", "Text Extraction", "PyMuPDF + Docling + OCR (RapidOCR+Tesseract)"],
        ["2", "Field Extraction", "Regex: tanggal, role, nomor"],
        ["3", "Organizer v2 + Normalization", "ORG-001 + ORG-004 canonical format"],
        ["4", "Activity Detection v5", "AKT-005: 16+ anchor patterns (62.2% exact)"],
        ["5", "Form Mapping", "Mapping ke form KHP + needs_review"],
        ["6", "Tingkat Router", "15 rules (48/74 @100% precision)"],
        ["7", "LLM Tingkat (fallback)", "Ollama llama3.1:8b untuk 26 cert unrouted"],
        ["8", "Persistence", "PostgreSQL + needs_review flag"],
    ]}})

    # Router rules
    b.append({"t": "h2", "x": "Router Rules (15 rules, 48/74 @100%)"})
    b.append({"t": "table", "x": {"h": ["Rule", "Signals", "Decision"], "r": [
        ["tingkat_nasional", "TINGKAT NASIONAL / LOMBA NASIONAL eksplisit", "Nasional"],
        ["lomba+org", "lomba dan (hima | univ | nasw | luar | fak | bem)", "Nasional"],
        ["lomba_merged+org", "kata tergabung OCR (CUP/academicweeks)", "Nasional"],
        ["dept+sem", "dept dan seminar, tanpa lomba/nasw", "Departemen/Program Studi"],
        ["hima+luar", "hima dan organisasi luar", "Nasional"],
        ["univ+luar", "univ dan luar, tanpa fak", "Nasional"],
        ["dept+fak", "dept dan fak", "Departemen/Program Studi"],
        ["dept+hima+univ", "dept dan hima dan univ", "Departemen/Program Studi"],
        ["fak+univ", "fak dan univ, tanpa sem/nasw/lomba", "Fakultas"],
        ["bem+sem", "bem dan sem, tanpa lomba/hima/nasw", "Fakultas"],
        ["bem_no_univ", "bem tanpa konteks univ/lomba/nasw/luar/hima", "Fakultas"],
        ["bem+hima", "bem dan hima (panitia internal FTMM)", "Fakultas"],
        ["sem+univ", "sem dan univ, tanpa fak/bem/hima/lomba", "Universitas"],
        ["ukm_org", "organizer UKM tanpa lomba/luar/nasw/sem/fak/dept", "Universitas"],
        ["hima_dept", "hima_org dan dept", "Departemen/Program Studi"],
    ]}})

    # Field methods
    b.append({"t": "h2", "x": "Field Extraction Methods"})
    b.append({"t": "table", "x": {"h": ["Field", "Method", "Akurasi"], "r": [
        ["nama_kegiatan", "AKT-005: 16+ anchor patterns, collapse all-caps, repair OCR-merge", "62.2%"],
        ["tanggal_mulai/selesai", "Regex 5-tier + alias bulan OCR", "81.8%"],
        ["penyelenggara", "ORG-004: organizer_v2 + normalize + canonical format", "63.5%"],
        ["nomor", "Regex 4 pola + fallback raw text (ORG-002)", "76.9%"],
        ["tingkat", "Router 15 rules + LLM fallback (llama3.1:8b)", "83.8%"],
    ]}})

    # LLM configuration
    b.append({"t": "h2", "x": "LLM Configuration"})
    b.append({"t": "table", "x": {"h": ["Parameter", "Nilai"], "r": [
        ["Model", "llama3.1:8b"],
        ["Prompt", "Tentukan TINGKAT KEGIATAN (dengan aturan BEM/HIMA/UNIV/Nasional)"],
        ["Temperature", "0"],
        ["Num predict", "30"],
        ["Budget teks", "140/200/300 char (strong/normal/poor OCR)"],
        ["Context fields", "nama_kegiatan, penyelenggara, peran"],
        ["Host", "http://127.0.0.1:11434"],
    ]}})

    # Production status
    b.append({"t": "h2", "x": "Production Status"})
    b.append({"t": "table", "x": {"h": ["Aspek", "Status"], "r": [
        ["Dipromosikan", "organizer_v2.py, tingkat_router.py"],
        ["Belum dipromosikan", "AKT-005 activity detection, ORG-004 normalization"],
        ["ENABLE_LLM_TINGKAT", "false (default) — produksi deterministik"],
        ["ENABLE_ORGANIZER_NORMALIZATION", "false (keputusan user)"],
    ]}})

    b.append({"t": "p", "x": "HYB-LLM = pipeline terbaik saat ini (MACRO 74.2%). Offline mode (HYB-COMBINED, 73.7%) sudah sangat bagus tanpa LLM. LLM hanya menambah +0.5pp dengan 26 calls."})

    return b


def main():
    per_cert, summary = load_data()
    blocks = build_blocks(per_cert, summary)

    # Generate docx
    docx_path = os.path.join(OUT, "hyb_llm_pipeline.docx")
    render_docx(blocks, docx_path, "HYB-LLM Pipeline", "Certificate Autofill Prototype — Best Pipeline with LLM")
    print(f"  hyb_llm_pipeline.docx")

    # Generate md
    md_path = os.path.join(OUT, "hyb_llm_pipeline.md")
    render_md(blocks, md_path, "HYB-LLM Pipeline", "Certificate Autofill Prototype — Best Pipeline with LLM")
    print(f"  hyb_llm_pipeline.md")


if __name__ == "__main__":
    main()
