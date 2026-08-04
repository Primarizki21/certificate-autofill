# Handoff v8 - Variants Experiment: GT Audit, Router Fix, LLM Bias, Layout

> Supersedes `docs/handoff_v7.md`. This handoff defines the next improvement
> cycle on top of the v7 P4 experiment (hybrid full/compact `tingkat` prompt +
> merged-lomba router), which reached **77.0% tingkat exact**. It targets the
> remaining error sources found by analyzing all 17 wrong certificates.

---

## Current Baseline

Latest completed experiment: **v7 P4 `e_hybrid`** (`run_llm_v4_20260803_113310/`).

| Metric | v7 P4 e_hybrid |
|--------|---------------:|
| Tingkat exact | **77.0%** (0.7703) |
| MACRO exact | 54.2% (0.5417) |
| Tokens per certificate | 202.2 |
| LLM calls | 39 (35 routed @ prec 1.0 + 4) |
| Damaged certs correct | 5/5 |

Variant comparison (same run):

| Variant | Tingkat exact | MACRO exact | Tokens/cert |
|---------|:------------:|:-----------:|:-----------:|
| b_minimized | 74.3% | — | 249.3 |
| c_adaptive | 68.9% | — | 167.3 |
| d_mid | 71.6% | — | 191.2 |
| **e_hybrid** | **77.0%** | 54.2% | **202.2** |

Token budget is effectively at the ~200 tok/cert gate. The next gains must come
from routing more certs to rules (0 tokens) or from fixing the LLM, not from
more tokens.

### Error Analysis of the 17 Wrong Certificates

Three distinct error sources, none of which is a hard ceiling:

1. **Ground-truth errors (~3 certs)** — GT contradicts explicit cert evidence.
   Inflates the "wrong" count; the true accuracy is higher than measured.
2. **Router gaps (~4-5 certs)** — word-boundary matching misses merged OCR
   tokens (`BEMFKM`, `BEMFEBUNAIR`, `HIMATESDA`), forcing LLM calls.
3. **Real LLM/OCR limits (~6-7 certs)** — English-text bias toward
   "Internasional", sparse-evidence hallucination, HIMA-vs-national-lomba
   conflict. This is the actual remaining ceiling.

---

## Phase 0 — GT Audit + Fix (honest baseline)

**Files:** `Ground_Truth_Sertifikat.csv`, `docs/gt_verification_report.txt`,
`tests/verify_ground_truth.py`

The GT verification report has **zero "tingkat" patterns** — tingkat was never
scale-checked, which is why label noise survived. Fix and extend it.

### GT Fixes (audited against raw text)

| Cert | Old GT | New GT | Evidence |
|------|:------:|:------:|----------|
| `2954283_219642_skp` | Fakultas | **Internasional** | Institut français d'Indonésie + Univ. Paris-Saclay + Embassy of France (user confirmed: label was a mistake) |
| `1981676_219642_skp` | Fakultas | **Nasional** | literal `TINGKAT NASIONAL` text, BEM FEB UNAIR template |
| `2030372_219642_skp` | Nasional | Nasional (unchanged) | identical template/text to 1981676; both now consistent |
| `1966887_221065_skp` | Lainnya | **Nasional** | AIESEC in Indonesia national chapter (user decision) |

### Verification Check

- Add a **tingkat scale-evidence check** to `verify_ground_truth.py`: scan for
  `TINGKAT NASIONAL`, `LOMBA NASIONAL`, `INTERNASIONAL`, `INTERNATIONAL`,
  foreign-institution names, and flag GT that contradicts the text.
- Re-run the benchmark with fixed GT. Report both **raw** and
  **ceiling-adjusted** (GT-errors excluded) accuracy so method quality is
  separated from label noise.

**Expected:** +2-3pp from GT fixes alone.

---

## Phase 1 — Router Contains-Matching Fix (bug fix)

**Files:** `tests/llm_router_v4.py` (`_sig`), `tests/test_generalized_parser.py`

The router uses word-boundary `\bBEM\b` / `\bHIMA\b`, but OCR merges words:
`BEMFKM`, `BEMFEBUNAIR`, `SERT2128BEM2026`, `HIMATESDA`. These fall through to
the LLM unnecessarily (certs `1952296`, `2030372`, ACW, `Venedict_specta`).

- Replace word-boundary with **contains-based** matching, guarded so merged
  alnum tokens fire only when plausible as an org name (uppercase alnum run),
  never as an arbitrary substring of an unrelated word.
- Add explicit `TINGKAT NASIONAL` text rule → Nasional, **only after Phase 0**
  (today it is 4/5 correct; the 5th is the GT error being fixed).
- Validate router precision ≥95% on all 74 before adopting; keep a
  traceability table (cert → rule → label) in the benchmark run.

**Expected:** +4-5 certs routed at 0 tokens.

---

## Phase 2 — LLM Bias + Calibration (method)

**Files:** `tests/llm_extractor_v4.py` (prompt builders),
`tests/benchmark_llm_v4.py` (VARIANTS)

1. **English ≠ International:** add prompt rule — English text or English event
   names do NOT imply international scope. Indonesian-institution context
   (UNAIR, BEM, HIMA) wins unless a foreign institution/organizer is explicit.
   Targets: `BTF`, `data slayer`, `2955331`, `2954571`, `synreaach`.
2. **Evidence-output prompt (FaR-style, arXiv 2504.02190):** request a short
   evidence line + answer:
   `Evidence: ... -> Tingkat: X`. Enables a post-hoc confidence proxy (empty or
   vague evidence → fall back to rule-based class) and gives debuggable
   mismatches stored in `calls_*.json`.
3. **Sparse-evidence guard:** no scale info present → prefer
   `Fakultas`/`Nasional` priors over hallucinated `Internasional` (targets
   `AQEEL_Seminar`).
4. Register `f_bias` and `g_evidence` variants in `VARIANTS`; benchmark on
   fixed GT.

**Expected:** +3-5 certs.

---

## Phase 3 — Layout-Aware Input (biggest untapped lever)

**Files:** `tests/llm_extractor_v4.py`, `tests/benchmark_llm_v4.py`, new
`tests/layout_repr.py`

LayIE-LLM (EMNLP 2025) shows input representation is the top LLM-IE lever
(+13.3-37.5 F1 vs naive text). Today we flatten with `get_text("text")` —
layout/position is discarded (`backend/app/services/pdf_fast_path.py:16`).

- Build a layout representation from PyMuPDF `page.get_text("dict")` (blocks /
  lines with font size + bbox):
  - **markdown variant:** heading lines (font-size heuristics) + body, compact,
    ~same token budget;
  - **annotated variant:** structural hints per line only where needed.
- Compare against plain-text baseline at matched token budget (≤200 tok/cert);
  measure token delta precisely.
- Targets merged-word OCR failures at the source (`BEMFKM`,
  `SERT2128BEM2026`).

**Expected:** largest single delta; may recover several of the ~6-7 real-limit
certs.

---

## Phase 4 — Reporting Artifacts

Generate/update with `python-docx` + `openpyxl` (both installed):

- `docs/report/phase_v4_methodology.md` + `.docx` — append v8 methodology:
  phases, router rules, prompt fixes, layout representation, literature
  citations (LayIE-LLM / EMNLP 2025, Hybrid LLM routing arXiv 2404.14618, FaR
  arXiv 2504.02190).
- `docs/report/phase_v4_results_summary.md` + `.xlsx` — new rows: v7 P4 (77.0%
  / 54.2% / 202 tok / 39 calls) → v8 final variant; per-file results sheet;
  progression table (v2 → v8).
- Report workspace: `docs/report/` (`.docx` + pasangan `.md` mirror). Lihat
  `docs/report/README.md`.

---

## Sequencing & Verification

- Order: Phase 0 → 1 → 2 → 3. Each phase ends with a full 74-cert benchmark run
  on the fixed GT.
- Final gate: `uv run python -m pytest tests/ -v`
  (field_extractor, generalized_parser, evaluation_framework, llm_extractor_v4
  self-check).
- All runs recorded under `tests/benchmark_runs/run_<ts>/`.

### Experiments

```bash
uv run python -m tests.benchmark_llm_v4
uv run python -m tests.llm_extractor_v4   # self-check
uv run python -m tests.verify_ground_truth
uv run python -m pytest tests/ -v
```

---

## Files of Interest

| File | Purpose |
|------|---------|
| `docs/handoff_v7.md` | Superseded baseline (77.0% P4) |
| `tests/llm_router_v4.py` | Router `_sig` + `route_tingkat` — contains-match target |
| `tests/llm_extractor_v4.py` | Prompt builders + `_needs_full_tingkat_prompt` |
| `tests/benchmark_llm_v4.py` | `VARIANTS` registry, GT normalization, xlsx output |
| `tests/benchmark_runs/run_20260728_131835/extracted_texts/` | Raw text for all 74 certs (error analysis) |
| `Ground_Truth_Sertifikat.csv` | GT source — Phase 0 fixes apply here |
| `docs/gt_verification_report.txt` | No tingkat checks today — extend |
| `backend/app/services/pdf_fast_path.py` | Flattens layout at line 16 — Phase 3 source |

## Expected Next Session Output

- Fixed GT committed + verification report including tingkat checks.
- A v8 baseline report on fixed GT (raw + ceiling-adjusted).
- `f_bias` / `g_evidence` / layout variants benchmarked.
- Decision on which variant wins the production gate (budget ≤200 tok/cert).
- Updated `docs/report/phase_v4_methodology.{md,docx}` +
  `docs/report/phase_v4_results_summary.{md,xlsx}` + pasangan `.md` mirror.

Do not integrate changes into `backend/app/services/extraction_pipeline.py`
until the final ship gate passes.
