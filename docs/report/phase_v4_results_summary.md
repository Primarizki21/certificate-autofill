# Phase v4 Results Summary

*Certificate Autofill Prototype - Numerical Results*

## Phase v4 Results Summary

### Method Comparison (Exact Accuracy)

| Field | Regex | NER v1 | Hybrid | Hybrid+PP | A1 (per-field) | A2 v2 (full-text) | Best |
|---|---|---|---|---|---|---|---|
| nama_kegiatan | 6.9% | 16.4% | 24.3% | 24.3% | 25.7% | **43.2%** | A2 v2 |
| penyelenggara | 6.9% | 11.0% | 12.2% | 13.5% | 13.5% | **31.1%** | A2 v2 |
| waktu_mulai | 81.8% | 27.3% | 81.8% | 81.8% | 81.8% | **94.5%** | A2 v2 |
| waktu_selesai | 81.8% | 7.3% | 81.8% | 81.8% | 81.8% | **94.5%** | A2 v2 |
| nomor | 58.0% | 0.0% | 59.6% | 59.6% | 65.4% | **73.1%** | A2 v2 |
| tingkat | — | — | — | — | **47.3%** | 36.5% | A1 |
| **MACRO** | 42.2% | 12.8% | 47.7% | 48.1% | 49.0% | **58.3%** | A2 v2 |

### Method Comparison (Fuzzy Accuracy)

| Field | Regex | NER v1 | Hybrid | Hybrid+PP | A1 (per-field) | A2 v2 (full-text) |
|---|---|---|---|---|---|---|
| nama_kegiatan | 19.2% | 43.8% | 63.5% | 63.5% | 70.3% | **85.1%** |
| penyelenggara | 41.1% | 50.7% | 47.3% | 50.0% | 50.0% | **73.0%** |
| waktu_mulai | 81.8% | 27.3% | 81.8% | 81.8% | 81.8% | **94.5%** |
| waktu_selesai | 81.8% | 7.3% | 81.8% | 81.8% | 81.8% | **94.5%** |
| nomor | 58.0% | 0.0% | 59.6% | 59.6% | 65.4% | **73.1%** |
| tingkat | — | — | — | — | 47.3% | 36.5% |
| **MACRO** | 53.3% | 28.8% | 65.5% | 66.1% | 64.6% | **74.5%** |

### Token Efficiency

| Metric | A1 (per-field) | A2 v2 (full-text) | Winner |
|---|---|---|---|
| MACRO exact | 49.0% | **58.3%** | A2 v2 |
| Total tokens | 61,679 | 61,706 | ~tied |
| Tokens per % MACRO | 1,259 | **1,058** | A2 v2 |
| LLM calls | 125 | **74** | A2 v2 |
| Prompt tokens | 60,851 | **53,788** | A2 v2 |
| Completion tokens | **828** | 7,918 | A1 |
| Avg latency/cert | **503ms** | 2,573ms | A1 |
| Avg tok/s | **63.0** | 54.9 | A1 |

### Progression

| Phase | Date | Method | MACRO | Delta | Cumulative |
|---|---|---|---|---|---|
| v2 | Jul 28 | Regex baseline | 42.2% | — | 42.2% |
| v2 | Jul 28 | NER v1 (pre-trained) | 12.8% | -29.4pp | 12.8% |
| v2 | Jul 30 | Hybrid (NER+regex) | 47.7% | +5.5pp | 47.7% |
| v3 | Jul 30 | Hybrid+PP | 48.1% | +0.4pp | 48.1% |
| v4 A1 | Jul 30 | Per-field LLM | 49.0% | +0.9pp | 49.0% |
| v4 A2 | Jul 30 | Full-text LLM (v1) | 47.7% | — | 47.7% |
| **v4 A2v2** | **Jul 30** | **Full-text LLM (v2)** | **58.3%** | **+10.2pp** | **58.3%** |

### Per-File Results

See `phase_v4_results_summary.xlsx` → Sheet "Per-File Results" for per-certificate comparison across A1 and A2 v2 methods. Each cert has two rows (A2 v2 top, A1 bottom).

### Key Takeaways

1. **Winner: A2 v2 (full-text)** — 58.3% MACRO exact, 61,706 tokens.

2. **Token efficiency** — 1,058 tokens per % MACRO (vs 1,259 for A1). Same token budget, +9.3pp accuracy.

3. **Biggest improvements** — waktu_mulai 81.8%→94.5%, waktu_selesai 81.8%→94.5%, nomor 59.6%→73.1%.

4. **Approach 1 still better at tingkat** — per-field prompt with heuristics (47.3% vs 36.5%).

5. **Full context helps** — LLM extracts nama_kegiatan (43.2%) and penyelenggara (31.1%) much better when it sees the whole text.

## Handoff v7 Results - Cost-Aware Hybrid (Tingkat-Only)

| Variant | Tingkat exact | MACRO exact | Eff. tok/cert | LLM calls |
|---|---|---|---|---|
| Hybrid+PP (no LLM) | 0% | 39.3% | 0 | 0 |
| b_minimized | 74.3% | 53.6% | 249 | 39 |
| c_adaptive | 68.9% | 52.6% | 167 | 39 |
| d_mid | 71.6% | 53.1% | 191 | 39 |
| e_hybrid | 77.0% | 54.2% | 202 | 39 |

Router: 35/74 decisions at 100% precision. Baseline run: tests/benchmark_runs/run_llm_v4_20260803_113310/ (GT raw).

## Handoff v8 Results - Router Fix + LLM Bias + Layout

Fixed GT: Ground_Truth_Sertifikat_v8.csv (3 audited tingkat corrections). Best run: tests/benchmark_runs/run_llm_v4_20260804_115212/.

| Variant | Tingkat exact | MACRO exact | Eff. tok/cert | LLM calls |
|---|---|---|---|---|
| a_context | 71.6% | 53.1% | 196 | 35 |
| b_minimized | 78.4% | 54.4% | 221 | 35 |
| c_adaptive | 71.6% | 53.1% | 149 | 35 |
| d_mid | 75.7% | 53.9% | 169 | 35 |
| e_hybrid | 79.7% | 54.7% | 182 | 35 |
| f_bias (winner) | 82.4% | 55.2% | 214 | 35 |
| g_evidence | 75.7% | 53.9% | 194 | 35 |

### Layout experiments (f_bias prompt)

| Input | Tingkat exact | MACRO exact |
|---|---|---|
| plain text (baseline) | 82.4% | 55.2% |
| layout markdown | 77.0% | 50.8% |
| layout annotated | 78.4% | 51.3% |

Layout rejected - only 25/74 PDFs have embedded text; markers disturb the deterministic extractors.

### GT audit effect (e_hybrid, router on)

| GT | Tingkat exact | MACRO exact | Ceiling-adjusted |
|---|---|---|---|
| raw | 57/74 (77.0%) | 54.2% | 56/71 (78.9%) |
| fixed_v8 | 57/74 (77.0%) | 54.2% | 56/71 (78.9%) |

Net-zero on raw count because 1981676 went correct->wrong while 2954283 went wrong->correct; the label corrections make the evaluation honest, not higher.

### Ship gate check

| Metric | Target | Actual | Status |
|---|---|---|---|
| Tingkat exact | >= 45% | 82.4% | PASS |
| MACRO exact | >= 50% | 55.2% | PASS |
| Eff. tokens/doc | <= 200 | 214 | MARGINAL |
| 100K-request tokens | <= 20M | 21.4M | MARGINAL |
| LLM call reduction | >= 40% | 53% | PASS |
| Rule precision | >= 95% | 100% | PASS |
| Date / number regression | none | none | PASS |

### Progression (tingkat exact, router on)

| Phase | Method | Tingkat | MACRO |
|---|---|---|---|
| v4 | LLM A1 (per-field) | 47.3% | 49.0% |
| v4 | LLM A2 v2 (full-text) | 36.5% | 58.3% |
| v6 | LLM v3 Variant B | 39.2% | 46.4% |
| v7 | v7 P3 router rule-based | 71.6% | 53.1% |
| v7 | v7 P4 e_hybrid + router ** | 77.0% | 54.2% |
| v8 | v8 f_bias + router ** | 82.4% | 55.2% |
