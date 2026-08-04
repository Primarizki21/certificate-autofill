# Handoff v9 — v8 Executed: Router Fix + LLM Bias Win, Layout Rejected

> Supersedes `docs/handoff_v8.md`. v8 was executed end-to-end (Phase 0-3, 5-7 of
> the v8 plan) with commits per experiment. This handoff records the actual
> results and the production integration.

---

## Current Baseline

| Metric | v7 P4 e_hybrid | **v8 f_bias (winner)** |
|--------|:-------------:|:----------------------:|
| Tingkat exact | 77.0% (57/74) | **82.4% (61/74)** |
| MACRO exact | 54.2% | **55.2%** |
| Eff. tokens/cert | 202 | 214 |
| LLM calls / 74 | 39 | **35** |
| Router decisions | 35 (100% prec) | **39 (100% prec)** |
| GT | raw | fixed_v8 |

Best run: `tests/benchmark_runs/run_llm_v4_20260804_095412/` (7 variants, router
on, GT v8).

---

## What Was Executed

### Phase 0 — Harness repair
`c337b12` — `results.xlsx` populated, taxonomy tied to explicit
`TAXONOMY_VARIANT` (e_hybrid), report lists all variants, eff. tokens/cert
amortized over 74, GT/text paths overridable via env, router rule traced in
`router_decisions.json`. Baseline reproduced within 1pp.

### Phase 1 — GT audit
`8d5578f` — `Ground_Truth_Sertifikat_v8.csv` (3 audited corrections) +
tingkat scale-evidence check in `verify_ground_truth.py`. Effect was net-zero
on the count (1981676 correct->wrong, 2954283 wrong->correct) but makes the
evaluation honest. Ceiling-adjusted (excl. 3 disputed): 56/71 = 78.9%.

### Phase 2 — Router contains-match + TINGKAT NASIONAL
`a2d0600` — BEM/HIMA detected in uppercase alnum runs with a guard; explicit
`TINGKAT/LOMBA NASIONAL` rule. Routed 39/74 at 100% precision, LLM calls
35 (-53%). e_hybrid on fixed GT: 60/74 = 81.08%.

### Phase 3 — Prompt variants f_bias / g_evidence
`0aa9679` — `f_bias` (English != International, Indonesian context wins) won at
**82.4%**; fixed data-slayer, 2955331, IRIS without regressions. `g_evidence`
(FaR-style evidence output) regressed to 75.7% and was rejected. A compressed
bias version cut tokens to 197 but lost accuracy (78.4%) and was rejected —
accuracy floor takes precedence per v8 rules.

### Phase 4 — Layout-aware input
`514b81f` — markdown (`##` title) and annotated (`[TITLE]`) representations
from PyMuPDF dict. **Rejected**: only 25/74 PDFs have embedded text (rest are
scanned); both variants underperformed plain text (77.0% / 78.4% vs 82.4%) and
markers disturbed the deterministic extractors. Input quality is OCR-bound.

### Phase 5 — Production integration
`b19d1c0` — `backend/app/services/` gained `tingkat_router.py`,
`llm_tingkat.py`, `organizer_v2.py` (ports, no tests dependency).
`form_mapper.map_tingkat_v8` = router -> LLM (if `ENABLE_LLM_TINGKAT`) ->
legacy rules. UKM now maps to `Lainnya`. Full suite: **30 passed**.

---

## Final Ship Gate

| Metric | Target | Actual | Status |
|--------|:------:|:------:|:------:|
| Tingkat exact | >= 45% | 82.4% | PASS |
| MACRO exact | >= 50% | 55.2% | PASS |
| Eff. tokens/doc | <= 200 | 214 | MARGINAL |
| 100K-request tokens | <= 20M | 21.4M | MARGINAL |
| LLM call reduction | >= 40% | 53% | PASS |
| High-confidence rule precision | >= 95% | 100% | PASS |
| Date / certificate-number regression | none | none | PASS |

The token target is slightly exceeded (214 vs 200). Per the v8 rule
"preserve the accuracy floor first", the f_bias prompt ships as-is; a token
optimization is a follow-up, not a blocker.

---

## Docs / Reports

- Report workspace: `docs/report/` (see `README.md` for the docx/md convention).
- `benchmark_methods.{docx,md}` — Methods 7 & 8 appended.
- `evaluation_methodology.{docx,md}` — section 10 (GT versioning, router,
  tokens, layout, ship gate) appended.
- `phase_v4_methodology.{docx,md}` — sections 11 & 12 appended.
- `phase_v4_results_summary.{md,xlsx}` — v7/v8 results + v8 sheets appended.
- `docs/gt_verification_report.txt` — regenerated with tingkat evidence checks.

## Commits

| Commit | Experiment |
|--------|-----------|
| `339a8cc` | R0: report workspace + md mirrors |
| `c337b12` | P0: harness repair, baseline reproduced |
| `8d5578f` | P1: GT audit + v8 CSV + verifier |
| `a2d0600` | P2: router contains-match + TINGKAT NASIONAL |
| `0aa9679` | P3: f_bias / g_evidence, f_bias wins |
| `514b81f` | P4: layout representation — rejected |
| `b19d1c0` | P5: production integration + UKM->Lainnya |

## Next Steps (future sessions)

- Token optimization for f_bias (target <=200 eff tok/cert) — trim instructions
  without the accuracy drop observed in the compressed-bias attempt.
- Better OCR (PaddleOCR) — the real input-quality ceiling (organizer 16.2%).
- Collect 200-500 corrected certs before any fine-tuning/classifier work.
- Measure duplicate-traffic (content-hash reuse) and Ollama concurrency before
  scaling decisions.
- A2 v2 full-field LLM integration remains deferred until tingkat path is stable
  in production.
