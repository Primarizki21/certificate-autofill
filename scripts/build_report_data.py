"""One-time migration: build docs/report/report_data.json from original
pre-append markdown + inject v7/v8 experiment content.

Output is the single source of truth for scripts/generate_report.py.
Kept in scripts/ for reproducibility; agents edit report_data.json directly
after this (no need to touch generator or this builder).

Usage:
  uv run python scripts/build_report_data.py
"""

import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(REPO, "docs", "report", "report_data.json")
SRC = "/tmp/rep"  # pre-append originals: git show 81da89c^:docs/report/<f>.md


def md_to_blocks(text: str) -> list[dict]:
    lines = text.split("\n")
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("### "):
            blocks.append({"t": "h3", "x": line[4:].strip()})
        elif line.startswith("## "):
            blocks.append({"t": "h2", "x": line[3:].strip()})
        elif line.startswith("# "):
            blocks.append({"t": "h1", "x": line[2:].strip()})
        elif line.strip().startswith("- "):
            bullets = []
            while i < len(lines) and lines[i].rstrip().strip().startswith("- "):
                bullets.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append({"t": "b", "x": bullets})
            continue
        elif line.startswith("```"):
            # code fence: collect until closing fence as a paragraph
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            blocks.append({"t": "p", "x": "\n".join(code).strip()})
            continue
        elif line.startswith("|") and "|" in line[1:]:
            # table if a separator row (contains ---) appears within the run
            run = []
            while i < len(lines) and lines[i].rstrip().startswith("|"):
                run.append(lines[i].rstrip())
                i += 1
            has_sep = any("---" in r for r in run)
            if has_sep:
                rows = []
                for r in run:
                    if "---" in r:
                        continue
                    cells = [c.strip() for c in r.strip().strip("|").split("|")]
                    rows.append(cells)
                blocks.append({"t": "table", "x": {"h": rows[0], "r": rows[1:]}})
            else:
                for r in run:
                    blocks.append({"t": "p", "x": r})
            continue
        else:
            blocks.append({"t": "p", "x": line.strip()})
        i += 1
    return blocks


def load_blocks(name: str) -> list[dict]:
    with open(os.path.join(SRC, name + ".md")) as f:
        return md_to_blocks(f.read())


def h(level: int, text: str) -> dict:
    return {"t": f"h{level}", "x": text}


def p(text: str) -> dict:
    return {"t": "p", "x": text}


def b(items: list[str]) -> dict:
    return {"t": "b", "x": items}


def table(header: list[str], rows: list[list]) -> dict:
    return {"t": "table", "x": {"h": header, "r": rows}}


# ---------------------------------------------------------------------------
# Method 7 & Method 8 blocks (inserted before the Comparison section)
# ---------------------------------------------------------------------------
M7 = [
    h(1, "Method 7: Cost-Aware Hybrid Extraction (Handoff v7)"),
    h(2, "Overview"),
    p("Handoff v7 moves from full-text LLM extraction to a cost-aware hybrid that extracts "
      "only the tingkat field with an LLM while every other field stays on the deterministic "
      "hybrid (NER + regex + post-processing). The goal is the best accuracy/cost Pareto point, "
      "not minimum tokens at any cost."),
    h(2, "Input"),
    p("Same 74 certificates. Ground truth: Ground_Truth_Sertifikat.csv (raw)."),
    h(2, "Process"),
    b(["Run hybrid + post-processing once per certificate (regex + NER + phrase-v2 organizer).",
       "Run the rule-based tingkat router: high-precision rules decide tingkat at 0 tokens.",
       "For certificates the router does not decide, call the local LLM with a compact tingkat prompt.",
       "Validate the LLM answer against the 6 form options; keep the value empty when invalid."]),
    h(2, "Configuration"),
    table(["Key", "Value"], [
        ["Prompt", "v3 minimized / v4 adaptive (variants a-e)"],
        ["Router", "rule-based, 35/74 decisions at 100% precision"],
        ["Model", "llama3.1:8b (Ollama)"],
        ["Token budget", "minimize_text(), ~202 eff tokens/cert"],
    ]),
    h(2, "Results (v7 P4 e_hybrid)"),
    table(["Metric", "Value"], [
        ["Tingkat exact", "77.0% (57/74)"],
        ["MACRO exact", "54.2%"],
        ["Eff. tokens/cert", "202.2"],
        ["LLM calls", "39 of 74 (router: 35, 100% precision)"],
        ["Run", "tests/benchmark_runs/run_llm_v4_20260803_113310/"],
    ]),
    h(2, "Strengths"),
    b(["Router removes ~47% of LLM calls at 0 tokens and 100% precision.",
       "Best accuracy-per-token in the v4+v6+v7 family (0.082 acc/token)."]),
    h(2, "Limitations"),
    b(["Word-boundary router misses OCR-merged tokens (BEMFKM, BEMFEBUNAIR, HIMATESDA).",
       "Ground truth had un-audited tingkat labels.",
       "LLM biased English certificate text toward Internasional."]),
    h(2, "Code Reference"),
    b(["tests/benchmark_llm_v4.py, tests/llm_extractor_v3.py, tests/llm_extractor_v4.py",
       "tests/llm_router_v4.py, tests/organizer_extractor_v2.py, tests/mismatch_taxonomy.py"]),
]

M8 = [
    h(1, "Method 8: v8 Router Fix + LLM Bias + Layout (Handoff v8)"),
    h(2, "Overview"),
    p("Handoff v8 repairs the v7 router, audits ground truth, and tests two accuracy levers: "
      "a bias-corrected LLM prompt and layout-aware input. Winner: contains-match router + "
      "f_bias prompt at 82.4% tingkat exact."),
    h(2, "Input"),
    p("Same 74 certificates. Versioned ground truth: Ground_Truth_Sertifikat_v8.csv (3 audited "
      "tingkat label corrections)."),
    h(2, "Process"),
    b(["GT audit: 1966887->Nasional, 1981676->Nasional, 2954283->Internasional; 2030372 stays Nasional.",
       "Router contains-match: BEM/HIMA detected in uppercase alnum runs (BEMFKM, SERT2128BEM2026) with a guard.",
       "New rule: explicit TINGKAT/LOMBA NASIONAL text -> Nasional.",
       "f_bias prompt: English text is not automatically Internasional; Indonesian-institution context wins.",
       "Layout experiment (markdown / annotated from PyMuPDF dict) measured and rejected."]),
    h(2, "Configuration"),
    table(["Key", "Value"], [
        ["Prompt", "f_bias (e_hybrid + bias rules)"],
        ["Router", "contains-match, 39/74 decisions at 100% precision"],
        ["GT", "fixed_v8 (Ground_Truth_Sertifikat_v8.csv)"],
        ["Model", "llama3.1:8b (Ollama)"],
    ]),
    h(2, "Results"),
    table(["Variant", "Tingkat exact", "MACRO exact", "Eff. tokens/cert"], [
        ["b_minimized", "78.4%", "54.4%", "221"],
        ["e_hybrid", "79.7%", "54.7%", "182"],
        ["f_bias (winner)", "82.4%", "55.2%", "214"],
        ["g_evidence", "75.7%", "53.9%", "194"],
        ["layout_md (f_bias)", "77.0%", "50.8%", "235"],
        ["layout_ann (f_bias)", "78.4%", "51.3%", "-"],
    ]),
    h(2, "Strengths"),
    b(["Contains-match router routes 39/74 at 100% precision (-53% LLM calls).",
       "f_bias fixes English-name scale bias (data slayer, 2955331, IRIS) without breaking BEM-fakultas."]),
    h(2, "Limitations"),
    b(["g_evidence (FaR-style) regresses accuracy and adds completion tokens -> rejected.",
       "Layout does not help: only 25/74 PDFs have embedded text, and markers disturb deterministic extractors.",
       "f_bias is 214 eff tokens/cert, slightly over the 200 gate."]),
    h(2, "Code Reference"),
    b(["tests/llm_router_v4.py, tests/llm_extractor_v4.py, tests/benchmark_llm_v4.py",
       "tests/layout_repr.py, tests/verify_ground_truth.py",
       "Production: backend/app/services/{tingkat_router,llm_tingkat,organizer_v2}.py"]),
]

# ---------------------------------------------------------------------------
# Experiments manifest (drives auto tables + progression)
# ---------------------------------------------------------------------------
EXPERIMENTS = [
    {"id": "v4_a1", "phase": "v4", "label": "LLM A1 (per-field)", "variant": "a1",
     "tingkat": "47.3%", "macro": "49.0%", "tokens_cert": 834, "calls": 125,
     "gt": "raw", "date": "Jul 30", "notes": "per-field LLM, Phase v4"},
    {"id": "v4_a2", "phase": "v4", "label": "LLM A2 v2 (full-text)", "variant": "a2v2",
     "tingkat": "36.5%", "macro": "58.3%", "tokens_cert": 834, "calls": 74,
     "gt": "raw", "date": "Jul 30", "notes": "full-text LLM, Phase v4"},
    {"id": "v6_b", "phase": "v6", "label": "LLM v3 Variant B", "variant": "b",
     "tingkat": "39.2%", "macro": "46.4%", "tokens_cert": 479, "calls": 74,
     "gt": "raw", "date": "Jul 31", "notes": "context + minimized text"},
    {"id": "v7_p3", "phase": "v7", "label": "v7 P3 router rule-based", "variant": "e_hybrid",
     "tingkat": "71.6%", "macro": "53.1%", "tokens_cert": 191, "calls": 42,
     "gt": "raw", "date": "Aug 3", "notes": "rule-based router, LLM calls -43%"},
    {"id": "v7_p4", "phase": "v7", "label": "v7 P4 e_hybrid + router", "variant": "e_hybrid",
     "tingkat": "77.0%", "macro": "54.2%", "tokens_cert": 202, "calls": 39,
     "router": "35/74 @100%", "gt": "raw", "date": "Aug 3", "is_winner": True,
     "notes": "merged-lomba router; baseline run run_llm_v4_20260803_113310"},
    {"id": "v8_final", "phase": "v8", "label": "v8 f_bias + router", "variant": "f_bias",
     "tingkat": "82.4%", "macro": "55.2%", "tokens_cert": 214, "calls": 35,
     "router": "39/74 @100%", "gt": "fixed_v8", "date": "Aug 4", "is_winner": True,
     "notes": "contains-match router + bias prompt; run run_llm_v4_20260804_095412"},
]

# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
bm = load_blocks("benchmark_methods")
# find index of the Comparison section (h1 "9. Comparison Table" or any '# 9.')
insert_at = None
for idx, blk in enumerate(bm):
    if blk["t"] == "h1" and blk["x"].lstrip("0123456789. ").startswith("Comparison"):
        insert_at = idx
        break
if insert_at is None:
    # fallback: before any '# 9.'
    for idx, blk in enumerate(bm):
        if blk["t"] == "h1" and blk["x"].startswith("9."):
            insert_at = idx
            break
if insert_at is None:
    insert_at = len(bm)
bm = bm[:insert_at] + M7 + M8 + bm[insert_at:]

# auto comparison + progression table appended at end of benchmark_methods
bm += [
    h(2, "Comparison Across Experiments"),
    {"t": "auto", "x": "comparison"},
    {"t": "auto", "x": "progression"},
]

ev = load_blocks("evaluation_methodology")
ev += [
    h(1, "10. Handoff v7/v8 Evaluation Addendum"),
    h(2, "10.1 Ground Truth Versioning"),
    p("Starting from v8, evaluation runs state which ground truth they used. "
      "Ground_Truth_Sertifikat.csv is the raw historical CSV (unchanged). "
      "Ground_Truth_Sertifikat_v8.csv applies 3 audited tingkat corrections: "
      "1966887 Lainnya->Nasional, 1981676 Fakultas->Nasional, 2954283 Fakultas->Internasional. "
      "2030372 stays Nasional (consistent with the identical-template 1981676)."),
    p("Metrics are reported three ways: (a) raw-GT accuracy, (b) fixed-GT accuracy, "
      "(c) ceiling-adjusted accuracy with the disputed certificates excluded, so label noise "
      "is separated from method quality."),
    h(2, "10.2 Tingkat Scale-Evidence Check"),
    p("verify_ground_truth.py now scans the raw text for scale evidence (TINGKAT NASIONAL, "
      "LOMBA, INTERNASIONAL, INTERNATIONAL, foreign-institution hints) and flags ground-truth "
      "labels that contradict the text. Pre-v8 this check did not exist, which is why label "
      "noise survived."),
    h(2, "10.3 Router Precision and Call Reduction"),
    table(["Metric", "v7 (P4)", "v8"], [
        ["Router decisions", "35/74", "39/74"],
        ["Router precision", "100%", "100%"],
        ["LLM calls / 74", "39", "35"],
        ["Call reduction vs no-router", "47%", "53%"],
    ]),
    p("v8 adds contains-based BEM/HIMA matching for OCR-merged tokens and the explicit "
      "TINGKAT NASIONAL rule. Precision stays at 100% on the fixed ground truth."),
    h(2, "10.4 Token Accounting"),
    p("Effective tokens per document = total tokens (prompt + completion) across all LLM calls, "
      "amortized over all 74 certificates. Certificates routed by rules contribute 0 tokens. "
      "This is reported per variant in token_usage_*.json. v8 final: f_bias = 214 eff tokens/cert "
      "(21.4M tokens per 100K requests), slightly above the 200 gate; per the handoff rule, the "
      "accuracy floor is preserved first."),
    h(2, "10.5 Layout Representation Evaluation"),
    p("Markdown (## title) and annotated ([TITLE]/[BODY]/[SMALL]) representations built from "
      "PyMuPDF page.get_text('dict') were compared against the plain-text baseline at matched "
      "token budgets. Only 25/74 certificates contain embedded text; the rest are scanned and "
      "fall back to OCR text. Both layout variants underperformed the plain baseline "
      "(77.0% / 78.4% vs 82.4% tingkat), so layout is rejected. Input quality is bound by OCR, "
      "not layout, on this dataset."),
    h(2, "10.6 Final v8 Ship Gate"),
    table(["Metric", "Target", "Actual", "Status"], [
        ["Tingkat exact", ">= 45%", "82.4%", "PASS"],
        ["MACRO exact", ">= 50%", "55.2%", "PASS"],
        ["Eff. tokens/doc", "<= 200", "214", "MARGINAL"],
        ["100K-request tokens", "<= 20M", "21.4M", "MARGINAL"],
        ["LLM call reduction", ">= 40%", "53%", "PASS"],
        ["Rule precision", ">= 95%", "100%", "PASS"],
        ["Date / number regression", "none", "none", "PASS"],
    ]),
    p("Caveats: the 74-certificate dataset is small, skewed to UNAIR templates, and not held-out; "
      "Ollama quantization adds run-to-run variance of about +/-1-2pp; the macro_avg label is a "
      "micro-average (see Section 4.2)."),
    h(2, "10.7 Results Summary (experiments)"),
    {"t": "auto", "x": "results"},
]

pm = load_blocks("phase_v4_methodology")
pm += [
    h(1, "11. Handoff v7 Addendum - Cost-Aware Hybrid Extraction"),
    p("v7 replaced full-text LLM extraction with a cost-aware hybrid that routes "
      "high-confidence certificates through a rule-based tingkat router (0 tokens) and calls "
      "the LLM only for the remaining certificates. Variant e_hybrid (full prompt for risky "
      "categories, compact elsewhere) won at 77.0% tingkat exact, 54.2% MACRO, 202.2 eff "
      "tokens/cert, 39 LLM calls. Router precision: 35/35 (100%)."),
    h(1, "12. Handoff v8 Addendum - GT Audit, Router Fix, LLM Bias, Layout"),
    p("v8 executed in order: GT audit, router contains-match fix, prompt bias variants, and "
      "layout experiments. Ground truth received 3 audited tingkat corrections. The router "
      "gained contains-based BEM/HIMA matching and the TINGKAT NASIONAL rule (39/74 decisions, "
      "100% precision, -53% calls). Variant f_bias (English != International bias) is the winner "
      "at 82.4% tingkat exact, 55.2% MACRO, 214 eff tokens/cert. g_evidence and layout "
      "representations regressed and were rejected. The winner was integrated into production "
      "behind ENABLE_LLM_TINGKAT."),
    table(["Metric", "v7 P4 e_hybrid", "v8 f_bias"], [
        ["Tingkat exact", "77.0%", "82.4%"],
        ["MACRO exact", "54.2%", "55.2%"],
        ["Eff. tokens/cert", "202", "214"],
        ["LLM calls / 74", "39", "35"],
        ["GT", "raw", "fixed_v8"],
    ]),
]

rs = load_blocks("phase_v4_results_summary")
rs += [
    h(1, "Handoff v7 Results - Cost-Aware Hybrid (Tingkat-Only)"),
    {"t": "auto", "x": "v7_variants"},
    p("Router: 35/74 decisions at 100% precision. Baseline run: "
      "tests/benchmark_runs/run_llm_v4_20260803_113310/ (GT raw)."),
    h(1, "Handoff v8 Results - Router Fix + LLM Bias + Layout"),
    p("Fixed GT: Ground_Truth_Sertifikat_v8.csv (3 audited tingkat corrections). Best run: "
      "tests/benchmark_runs/run_llm_v4_20260804_095412/."),
    {"t": "auto", "x": "v8_variants"},
    h(2, "Layout experiments (f_bias prompt)"),
    table(["Input", "Tingkat exact", "MACRO exact"], [
        ["plain text (baseline)", "82.4%", "55.2%"],
        ["layout markdown", "77.0%", "50.8%"],
        ["layout annotated", "78.4%", "51.3%"],
    ]),
    p("Layout rejected - only 25/74 PDFs have embedded text; markers disturb the deterministic "
      "extractors."),
    h(2, "GT audit effect (e_hybrid, router on)"),
    table(["GT", "Tingkat exact", "MACRO exact", "Ceiling-adjusted"], [
        ["raw", "57/74 (77.0%)", "54.2%", "56/71 (78.9%)"],
        ["fixed_v8", "57/74 (77.0%)", "54.2%", "56/71 (78.9%)"],
    ]),
    p("Net-zero on raw count because 1981676 went correct->wrong while 2954283 went "
      "wrong->correct; the label corrections make the evaluation honest, not higher."),
    h(2, "Ship gate check"),
    table(["Metric", "Target", "Actual", "Status"], [
        ["Tingkat exact", ">= 45%", "82.4%", "PASS"],
        ["MACRO exact", ">= 50%", "55.2%", "PASS"],
        ["Eff. tokens/doc", "<= 200", "214", "MARGINAL"],
        ["100K-request tokens", "<= 20M", "21.4M", "MARGINAL"],
        ["LLM call reduction", ">= 40%", "53%", "PASS"],
        ["Rule precision", ">= 95%", "100%", "PASS"],
        ["Date / number regression", "none", "none", "PASS"],
    ]),
    h(2, "Progression (tingkat exact, router on)"),
    {"t": "auto", "x": "progression"},
]

V7_VARIANTS = table(["Variant", "Tingkat exact", "MACRO exact", "Eff. tok/cert", "LLM calls"], [
    ["Hybrid+PP (no LLM)", "0%", "39.3%", "0", "0"],
    ["b_minimized", "74.3%", "53.6%", "249", "39"],
    ["c_adaptive", "68.9%", "52.6%", "167", "39"],
    ["d_mid", "71.6%", "53.1%", "191", "39"],
    ["e_hybrid", "77.0%", "54.2%", "202", "39"],
])

V8_VARIANTS = table(["Variant", "Tingkat exact", "MACRO exact", "Eff. tok/cert", "LLM calls"], [
    ["a_context", "71.6%", "53.1%", "196", "35"],
    ["b_minimized", "78.4%", "54.4%", "221", "35"],
    ["c_adaptive", "71.6%", "53.1%", "149", "35"],
    ["d_mid", "75.7%", "53.9%", "169", "35"],
    ["e_hybrid", "79.7%", "54.7%", "182", "35"],
    ["f_bias (winner)", "82.4%", "55.2%", "214", "35"],
    ["g_evidence", "75.7%", "53.9%", "194", "35"],
])

# replace auto 'v7_variants' / 'v8_variants' blocks with static tables
for blk in rs:
    if blk.get("t") == "auto" and blk["x"] == "v7_variants":
        blk.update({"t": "table", "x": V7_VARIANTS["x"]})
    if blk.get("t") == "auto" and blk["x"] == "v8_variants":
        blk.update({"t": "table", "x": V8_VARIANTS["x"]})

def main():
    data = {
        "meta": {
            "title": "Certificate Autofill Prototype - Experiment Reports",
            "date": "August 2026",
            "model": "llama3.1:8b",
            "dataset": "74 certificates (Universitas Airlangga)",
        },
        "experiments": EXPERIMENTS,
        "documents": {
            "benchmark_methods": bm,
            "evaluation_methodology": ev,
            "phase_v4_methodology": pm,
            "phase_v4_results_summary": rs,
        },
    }

    with open(OUT, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT}")
    print("documents:", {k: len(v) for k, v in data["documents"].items()})


if __name__ == "__main__":
    main()
