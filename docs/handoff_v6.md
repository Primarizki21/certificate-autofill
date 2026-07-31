# Handoff v6 — Token-Minimized Hybrid+LLM for Tingkat

> Supersedes `docs/handoff_v5.md`. V5 covered Phase v4 (LLM inference, per-field A1 and full-text A2 v2) — complete. V6 experiments with minimal-token LLM calls for the one field hybrid can never extract: **tingkat**. **EXPERIMENT EXECUTED — see [Results](#results).**

---

## Why This Experiment

The project targets ~10,000 users. Current methods send raw certificate text to the LLM for every cert:
- A1 (per-field): raw text 1-5× per cert
- A2 v2 (full-text): raw text once per cert, but reprocesses ALL fields even ones hybrid already solved

**Goal:** find the minimum-token approach that keeps tingkat accuracy acceptable.

## Design Decisions (from planning)

| Question | Decision | Why |
|----------|----------|-----|
| Gating / selective LLM calls | **Removed entirely** | Any threshold (confidence or keyword) is arbitrary and won't generalize to unseen certs. Variant A is already cheap; just call LLM every time. |
| Variant C (confidence ≥ 0.7 gate) | **Dropped** | Same reason — hardcoded `0.7` had no justification. |
| Raw text in prompt | **`minimize_text()`** instead of full text | OCR noise (~40% of lines) actively confuses the LLM and costs tokens. Score-based line selection keeps only tingkat-relevant lines. |
| JSON input/output | **Rejected** | JSON adds ~20-30 structural tokens (braces/quotes) and doesn't improve LLM accuracy. Plain `field: value` output stays. |
| JSON output for parsing | **Deferred** | Parsing isn't the accuracy bottleneck; tingkat classification is. Fix only if parsing becomes a real failure point. |

### `minimize_text()` — robust by design
- **Keyword scoring, not field extraction.** Lines scored for organizer/scale/role/date/cert relevance; noise (NIM/NIP, garbled OCR) penalized.
- Falls back to looser scoring, then a short prefix — **never returns empty** on any certificate layout (verified on all 74).
- Config (`MINIMIZE_CONFIG`) is data-driven and dumped to `config.json` in every run, so it can be tuned without code changes.

**Measured compression on 74 certs:** 42,205 → 11,289 chars (**73%**), 0 empty results.

## Results

**Run dir:** `tests/benchmark_runs/run_llm_v3_20260731_104523/` (model `llama3.1:8b`, prompt `v3_tingkat_only`)

| Method | Tokens/cert | Tingkat | MACRO exact | Latency/cert |
|--------|:----------:|:-------:|:-----------:|:------------:|
| Hybrid+PP (no LLM) | 0 | 0% | 38.8% | ~0.6s |
| A1 (per-field LLM, Phase v4) | 834 | 47.3% | 49.0% | ~2s |
| A2 v2 (full-text, Phase v4) | 834 | 36.5% | 58.3% | ~2.5s |
| **Variant A (context-only)** | **376** | **29.7%** | **44.5%** | ~1s |
| **Variant B (context + minimized)** | **440** | **33.8%** | **45.3%** | ~1s |

### Accuracy per token (the winner metric)

| Method | Acc/token | vs A1 | vs A2 |
|--------|:---------:|:-----:|:-----:|
| A1 | 0.057 | 1× | — |
| A2 v2 | 0.044 | — | 1× |
| Variant A | **0.079** | **1.4×** | **1.8×** |
| Variant B | **0.077** | **1.4×** | **1.8×** |

### Token math at scale (10K certs)

| Method | Tokens per 10K | vs A1/A2 |
|--------|:--------------:|:--------:|
| A1 / A2 v2 | ~8.3M | 1× |
| **Variant A** | **~3.76M** | **0.45×** |
| **Variant B** | **~4.40M** | **0.53×** |

## Interpretation

1. **Both variants beat hybrid baseline on MACRO** (44.5% / 45.3% vs 38.8%) at minimal token cost.
2. **B > A on raw accuracy** (tingkat 33.8% vs 29.7%, MACRO 45.3% vs 44.5%) — minimized raw text helps the LLM. A is slightly better accuracy-per-token (0.079 vs 0.077).
3. **Both below the original 40% target.** Context-only prompting caps tingkat accuracy because hybrid organizer extraction is only 13.5% — garbage in, garbage out. A1's 47.3% needed full raw text.
4. **Per-field comparison vs Phase v4:** the 5 hybrid fields are untouched (identical to baseline); tingkat is the only LLM contribution. The MACRO gap vs A2 v2 (58.3%) is entirely the other 5 fields — A2 also had LLM fix nama_kegiatan/penyelenggara, which this experiment deliberately does not.

## Recommendation

- **Ship Variant B** if tingkat 33.8% at 440 tok/cert is acceptable — it's the best raw accuracy per token in the v6 family and adds no infrastructure.
- **Ship Variant A** if token budget is the binding constraint — 376 tok/cert, 29.7%, best accuracy-per-token.
- The 40% ceiling comes from hybrid organizer quality, not the prompt. To push tingkat past 40% cheaply, either:
  a. Improve organizer extraction (OCR / NER for `penyelenggara_kegiatan`, currently 13.5%), or
  b. Give the LLM raw text only when organizer confidence is low — a *future* gate, but only after organizer quality improves (the "confident but wrong" risk makes it a loss today).

## Files

| File | Action | Notes |
|------|--------|-------|
| `tests/llm_extractor_v3.py` | **New** | `minimize_text()`, `score_line()`, `debug_minimize()`, 2 prompt builders, `MINIMIZE_CONFIG`, self-check `_demo()` |
| `tests/benchmark_llm_v3.py` | **New** | Runs hybrid+PP once, then Variant A+B for tingkat only. Outputs report.md, summaries, token_usage, minimize_stats, config.json, results.xlsx. `--limit N` for smoke tests. |
| `docs/handoff_v6.md` | Updated | This document |

### Reused from existing code

| Import from | Functions |
|-------------|-----------|
| `tests/llm_extractor.py` | `call_ollama`, `validate_tingkat`, `TokenUsage`, `log_call`, `build_token_usage_summary`, `TINGKAT_OPTIONS`, `TINGKAT_GT_MAP`, `DEFAULT_MODEL` |
| `tests/benchmark_llm.py` | `read_text_file`, `combine_hybrid`, `CSV_PATH`, `TEXTS_DIR`, `RUNS_DIR`, `create_run_dir`, `save_xlsx` |
| `tests/ner_extractor.py` | `load_ner_model`, `extract_entities`, `normalize_for_ner` |
| `tests/ner_to_fields.py` | `map_entities_to_fields` |
| `tests/post_processors.py` | `filter_signer_roles` |
| `tests.evaluation_framework` | `EVAL_FIELDS`, `aggregate_results`, `evaluate_row`, `load_csv`, `print_report` |

## What's NOT in Scope

- **jenis_kegiatan, kelompok_kegiatan** — no GT yet. Deferred.
- **Integration into `extraction_pipeline.py`** — deferred until a winner is confirmed at scale.
- **Model comparison** — `llama3.1:8b` only.
- **OCR improvements** — out of scope, though they cap tingkat accuracy.

## Aturan Main

1. **Commit dulu** sebelum eksperimen. Backup files yang akan diubah.
2. **Mode experiment** — file baru (`*_v3.py`), jangan timpa existing.
3. **Gagal?** `git checkout` untuk balik.
4. **Berhasil?** Merge ke production code, run `uv run python -m pytest tests/ -v`.
5. **Run benchmark** setelah merge untuk dokumentasi improvement.
6. **Semua panggilan Ollama mencatat `prompt_eval_count` dan `eval_count`.**

### Running Tests
```bash
uv run python -m tests.llm_extractor_v3           # self-check: minimize_text + prompts
uv run python -m tests.benchmark_llm_v3           # full 74-cert benchmark (A + B)
uv run python -m tests.benchmark_llm_v3 --limit 10  # smoke test
uv run python -m tests.benchmark_llm_v2           # previous winner (A2 v2) reference
uv run python -m tests.benchmark_llm              # A1 reference
```

## Gotchas

1. **Model naming:** `llama3.2:8b` doesn't exist → use `llama3.1:8b`.
2. **Ollama server:** `setsid bash scripts/start_ollama.sh &` (plain `nohup &` dies when the shell exits). First call loads the model into VRAM (~10s).
3. **`EVAL_FIELDS` double-patch trap:** `tests/benchmark_llm.py` mutates `ev_fw.EVAL_FIELDS` at import time. In v3 the patch is guarded (`if "tingkat" not in ev_fw.EVAL_FIELDS`) and the report dedupes fields.
4. **EVAL_FIELDS aliasing:** `from tests.evaluation_framework import EVAL_FIELDS` is the *same list object* as `ev_fw.EVAL_FIELDS` — mutating one mutates the other.
5. **`benchmark_runs/` is gitignored** — results are local-only.
6. **Tingkat GT normalization:** `Departemen/Prodi` → `Departemen/Program Studi` via `TINGKAT_GT_MAP`.
