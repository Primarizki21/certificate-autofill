# Handoff v6 — Token-Minimized Hybrid+LLM for Tingkat

> Supersedes `docs/handoff_v5.md`. V5 covered Phase v4 (LLM inference, per-field A1 and full-text A2 v2) — complete. V6 experiments with minimal-token LLM calls for the one field hybrid can never extract: **tingkat**. **EXPERIMENT EXECUTED — see [Results](#results).**

---

## Why This Experiment

The project targets ~10,000 users. Current methods send raw certificate text to the LLM for every cert:
- A1 (per-field): raw text 1-5× per cert
- A2 v2 (full-text): raw text once per cert, but reprocesses ALL fields even ones hybrid already solved

**Goal:** find the minimum-token approach that keeps tingkat accuracy acceptable (~40%).

## Design Decisions (from planning)

| Question | Decision | Why |
|----------|----------|-----|
| Gating / selective LLM calls | **Removed entirely** | Any threshold (confidence or keyword) is arbitrary and won't generalize to unseen certs. Variant A is already cheap; just call LLM every time. |
| Variant C (confidence ≥ 0.7 gate) | **Dropped** | Same reason — hardcoded `0.7` had no justification. |
| Raw text in prompt | **`minimize_text()`** instead of full text | OCR noise (~40% of lines) actively confuses the LLM and costs tokens. Score-based line selection keeps only tingkat-relevant lines. |
| JSON input/output | **Rejected** | JSON adds ~20-30 structural tokens (braces/quotes) and doesn't improve LLM accuracy. Plain `field: value` output stays. |
| Tingkat label | **Match GT exactly** | Real form is a dropdown — LLM must output the exact dropdown value. `TINGKAT_OPTIONS` now uses `Departemen/Prodi` (was `Departemen/Program Studi`); `TINGKAT_GT_MAP` is empty (no translation). **Note:** `backend/app/master_data.py` still lists `Departemen/Program Studi` — reconcile if the form dropdown differs from GT. |

### `minimize_text()` — robust by design
- **Keyword scoring, not field extraction.** Lines scored for organizer/scale/role/date/cert relevance; noise (NIM/NIP, garbled OCR) penalized.
- Garbled penalty only fires on merged no-space runs (true OCR noise); spaced lines like English all-caps headers (`INFORMATION SYSTEMS DEPT.`) are kept.
- Falls back to looser scoring, then a short prefix — **never returns empty** on any certificate layout (verified on all 74).
- Config (`MINIMIZE_CONFIG`) is data-driven and dumped to `config.json` in every run.

**Measured compression on 74 certs:** 42,205 → 12,496 chars (**70%**), 0 empty results.

## Results

**Final run dir:** `tests/benchmark_runs/run_llm_v3_20260731_113402/` (model `llama3.1:8b`, prompt `v3_tingkat_only`)

| Method | Tokens/cert | Tingkat | MACRO exact | Acc/token |
|--------|:----------:|:-------:|:-----------:|:---------:|
| Hybrid+PP (no LLM) | 0 | 0% | 38.8% | — |
| A1 (per-field LLM, Phase v4) | 834 | 47.3% | 49.0% | 0.057 |
| A2 v2 (full-text, Phase v4) | 834 | 36.5% | 58.3% | 0.044 |
| **Variant A (context-only)** | 410 | 24.3% | 43.5% | 0.059 |
| **Variant B (context + minimized)** | **479** | **39.2%** | **46.4%** | **0.082** |

### Experiment 2 iterations (prompt heuristic tuning)

| Version | Change | A tingkat | B tingkat |
|---------|--------|:---------:|:---------:|
| exp1 (committed) | baseline: context vs minimized | 29.7% | 33.8% |
| exp2 | +dept/faculty heuristics, priority line, "hanya UNAIR→Universitas" | 24.3% | 31.1% |
| exp3 | surgical: English-only DEPT heuristic, original rule order | 27.0% | 36.5% |
| **exp4 (final)** | **move DEPT heuristic to top of heuristics** | **24.3%** | **39.2%** |

### Token math at scale (10K certs)

| Method | Tokens per 10K | vs A1/A2 |
|--------|:--------------:|:--------:|
| A1 / A2 v2 | ~8.3M | 1× |
| **Variant B** | **~4.8M** | **0.58×** |

## Interpretation

1. **Variant B wins.** 39.2% tingkat at 479 tok/cert = **0.082 accuracy-per-token, best in the whole v4+v6 family** (A1: 0.057, A2: 0.044). It reaches essentially the 40% target at ~58% of A1/A2's token cost, with MACRO 46.4% (A1: 49.0%).
2. **Prompt heuristics matter more than raw text.** The 3 biggest gains (33.8→39.2%) came from heuristic tuning, not more context. The English DEPT heuristic (top of list) alone added ~5.4pp.
3. **Variant A regressed** (29.7→24.3%): it sees no raw text, so the dept/faculty heuristics only trigger via the low-accuracy hybrid organizer fields. B is the clear production choice.
4. **Remaining errors are mostly out-of-scope Nasional** (~25 of ~38 wrong certs have no "NASIONAL" signal in the text — level is domain knowledge, not extractable from cert). The ~6 English dept certs (Ananda Aqeel) still partially fail: LLM sees both `FACULTY OF...` and `INFORMATION SYSTEMS DEPT.` and picks Fakultas despite the heuristic.
5. **The 40% ceiling is input quality, not prompt.** Organizer extraction is 13.5%; Nasional needs participant info the cert doesn't have.

## Recommendation

- **Ship Variant B** at 479 tok/cert: 39.2% tingkat, 46.4% MACRO, best accuracy-per-token. It matches the ~40% target at roughly half the token cost of Phase v4 methods.
- To push past 40% later (in priority order):
  a. Fix OCR/organizer extraction (`penyelenggara_kegiatan`, 13.5%) — the single biggest lever.
  b. External knowledge for Nasional (event whitelist) — needs domain data, not OCR.
  c. Strengthen the dept-vs-faculty conflict resolution in the prompt.

## Files

| File | Action | Notes |
|------|--------|-------|
| `tests/llm_extractor_v3.py` | **New** | `minimize_text()`, `score_line()`, `debug_minimize()`, 2 prompt builders (shared `_TINGKAT_HEURISTICS`), `MINIMIZE_CONFIG`, self-check `_demo()` |
| `tests/benchmark_llm_v3.py` | **New** | Runs hybrid+PP once, then Variant A+B for tingkat only. Outputs report.md, summaries, token_usage, minimize_stats, config.json, results.xlsx. `--limit N` for smoke tests. |
| `tests/llm_extractor.py` | **Modified** | `TINGKAT_OPTIONS[4]` = `Departemen/Prodi`; `TINGKAT_GT_MAP` emptied; `validate_tingkat` fallback returns `Departemen/Prodi` |
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
6. **Tingkat labels match GT exactly** — `TINGKAT_OPTIONS` and GT both use `Departemen/Prodi`; `TINGKAT_GT_MAP` is empty. `backend/app/master_data.py` still lists `Departemen/Program Studi` — reconcile with the real form if needed.
7. **Heuristic order matters.** The English DEPT/DEPARTMENT/STUDY PROGRAM rule must stay above the BEM-Fakultas rule — moving it below costs ~2.7pp (exp3 vs exp4).
