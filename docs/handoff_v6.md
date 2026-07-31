# Handoff v6 — Token-Minimized Hybrid+LLM for Tingkat

> Supersedes `docs/handoff_v5.md` for the next experiment. V5 covered Phase v4 (LLM inference, both per-field A1 and full-text A2 v2) — now **complete**. This document proposes the next experiment: minimize LLM token usage for production scale.

---

## Why This Experiment

The project targets ~10,000 users. At production scale, **every token costs money**. Current methods send the raw certificate text to the LLM for every cert — even when the hybrid pipeline already extracted most fields.

The biggest cost is the **raw text duplication**:
- A1 (per-field) sends raw text 1-5× per cert (once per empty field)
- A2 v2 (full-text) sends raw text once per cert, but reprocesses ALL fields even ones hybrid already solved

**Goal:** find the minimum-token approach that maintains tingkat accuracy — the one field hybrid can never extract.

---

## Current Status (Phase v4 complete)

| Method | Tokens/cert | Tingkat | MACRO exact | Latency/cert |
|--------|:----------:|:-------:|:-----------:|:------------:|
| Hybrid+PP (no LLM) | 0 | 0% | 38.8% | ~0.6s |
| A1 (per-field LLM) | 834 | **47.3%** | 49.0% | ~2s |
| A2 v2 (full-text LLM) | 834 | 36.5% | **58.3%** | ~2.5s |

**Key insight:** Hybrid+PP already extracts 5 of 6 fields reasonably:
- waktu_mulai: 81.8%, waktu_selesai: 81.8%, nomor: 59.6%
- nama_kegiatan: 24.3%, penyelenggara: 13.5%
- **tingkat: 0%** — NEVER extracted by regex/NER → LLM required

So the LLM's real value-add for the form is **tingkat** (and future jenis_kegiatan/kelompok_kegiatan). Everything else hybrid can attempt for free.

### Token math at scale (10K certs)

| Method | Tokens per 10K | LLM calls per 10K | Cost multiplier |
|--------|:--------------:|:-----------------:|:---------------:|
| Hybrid only | 0 | 0 | 1× |
| A1 | ~8.3M | ~17K | ~50× |
| A2 v2 | ~8.3M | ~10K | ~50× |
| **Proposed (inference-only)** | **~1.5-5M** | **~10K** | **~9-30×** |

---

## Proposed Experiment — 3 Variants

All variants use hybrid+PP extraction first, then call LLM **only** for tingkat (the always-missing field).

### Variant A — Context-only inference (cheapest)

**Prompt (no raw text):**
```
Tentukan tingkat kegiatan dari informasi berikut.

ATURAN WAJIB:
- Jawaban HARUS persis salah satu dari opsi di bawah
- JANGAN jawab selain opsi ini
- Jika tidak yakin, pilih yang paling mendekati

PETUNJUK TINGKAT:
- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat FAKULTAS (BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas
- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa (HIMATESDA, HIMANO), maka == Departemen/Program Studi
- Jika diselenggarakan oleh BEM Universitas, Rektorat, Direktorat Kemahasiswaan, maka == Universitas
- Jika kegiatan berskala nasional, maka == Nasional
- Jika kegiatan berskala internasional, maka == Internasional
- 'UNIVERSITAS AIRLANGGA' adalah institusi induk, BUKAN penentu tingkat

Opsi yang diizinkan:
- Internasional
- Nasional
- Universitas
- Fakultas
- Departemen/Program Studi
- Lainnya

Field yang sudah diketahui (dari pipeline):
- Nama Kegiatan: {nama_kegiatan or "tidak diketahui"}
- Penyelenggara: {penyelenggara or "tidak diketahui"}
- Peran: {raw_role or "tidak diketahui"}

Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):
```

- Prompt: ~200 tokens (heuristics dominate, no raw text)
- Completion: ~5 tokens
- **Total: ~205 tokens/cert**

**Risk:** Hybrid organizer accuracy is only 13.5%. If organizer = "Social Action" (wrong, should be "BEM FEB UNAIR"), LLM can't infer tingkat correctly.

### Variant B — Context + raw text (medium cost)

Same as A, but add `Teks sertifikat: {raw_text}` before the known fields.

- Prompt: ~500 tokens (raw text ~300 + context ~200)
- Completion: ~5 tokens
- **Total: ~505 tokens/cert**

**Tradeoff:** 2.5× tokens vs Variant A. LLM sees full context (helps garbled organizer cases) but at real cost.

### Variant C — Selective (call LLM only on low-confidence organizer)

```
1. Run hybrid+PP
2. Check organizer confidence (penyelenggara_kegiatan.confidence)
3. If confidence >= 0.7 → skip LLM, leave tingkat empty (or rule-based fallback)
4. If confidence < 0.7 → call LLM with Variant A prompt
```

- Easy certs: 0 tokens
- Hard certs: ~205 tokens
- **Expected average: ~50-100 tokens/cert**

**Risk:** Skipping LLM on confident-but-wrong organizers loses accuracy. The threshold needs tuning.

---

## Files to Create

| File | Action | Notes |
|------|--------|-------|
| `docs/handoff_v6.md` | **New** | This document |
| `tests/llm_extractor_v3.py` | **New** | 3 prompt builders + reuse `call_ollama`/validators from `llm_extractor.py` |
| `tests/benchmark_llm_v3.py` | **New** | Benchmark runner: runs hybrid+PP, then per-variant LLM, same output structure as v2 |

### Reuse from existing code

| Import from | Functions |
|-------------|-----------|
| `tests/llm_extractor.py` | `call_ollama`, `validate_tingkat`, `TokenUsage`, `log_call`, `build_token_usage_summary`, `TINGKAT_OPTIONS`, `TINGKAT_GT_MAP` |
| `tests/benchmark_llm.py` | `read_text_file`, `combine_hybrid`, `CSV_PATH`, `TEXTS_DIR`, `RUNS_DIR`, `create_run_dir`, `save_xlsx` |
| `tests/ner_extractor.py` | `load_ner_model`, `extract_entities`, `normalize_for_ner` |
| `tests/ner_to_fields.py` | `map_entities_to_fields` |
| `tests/post_processors.py` | `filter_signer_roles` |
| `tests.evaluation_framework` | `EVAL_FIELDS`, `aggregate_results`, `evaluate_row`, `load_csv`, `print_report` |

### New prompt builder structure

```python
# tests/llm_extractor_v3.py
def build_prompt_tingkat_context(known_fields: dict[str, str]) -> str:
    """Variant A: context-only, no raw text"""
    ...

def build_prompt_tingkat_rawtext(raw_text: str, known_fields: dict[str, str]) -> str:
    """Variant B: context + raw text"""
    ...

def should_call_llm(hybrid_fields: dict, threshold: float = 0.7) -> bool:
    """Variant C: selective gating by organizer confidence"""
    ...
```

### Benchmark runner structure

```python
# tests/benchmark_llm_v3.py
def run_variant(ner_pipe, rows, variant: str) -> dict:
    """Run hybrid+PP, then variant-specific LLM step for tingkat."""
    ...

def main():
    # Load model + GT
    # Run hybrid+PP on all 74 certs (baseline)
    # For each variant A/B/C: run LLM step, evaluate, log tokens
    # Output: results.json + token_usage.json + XLSX per variant
```

---

## Evaluation Metrics

| Metric | How to measure |
|--------|---------------|
| Tingkat exact | Same `evaluate_row` — GT already in CSV (`Tingkat` column, 74 rows) |
| MACRO exact | Same `aggregate_results` — includes tingkat + 5 hybrid fields |
| Tokens per 10K certs | `total_tokens / 74 × 10_000` |
| LLM calls per 10K certs | `total_calls / 74 × 10_000` |
| Latency per cert | Hybrid time + LLM time |
| **Accuracy per token** | `MACRO / total_tokens` — the winner metric |

---

## Execution Order

```
Day 1:
  - Create tests/llm_extractor_v3.py (3 prompt builders)
  - Test variant A on 3 sample certs manually
  - KEY CHECK: can LLM infer tingkat from organizer ALONE?
    - If organizer is clean (e.g., "BEM FKM UNAIR") → LLM says Fakultas?
    - If organizer is garbled (e.g., "APHSABEMFKM") → what happens?

Day 2:
  - Build tests/benchmark_llm_v3.py (3 variants)
  - Run variant A on all 74 certs (cheapest, run first)
  - Record: tingkat accuracy + token usage

Day 3:
  - Run variant B (context + raw text)
  - Compare A vs B: is 2.5× tokens worth the accuracy gain?
  - Run variant C (selective) — tune confidence threshold

Day 4:
  - Pick winner using accuracy-per-token metric
  - Commit results + update this handoff with actual numbers
```

---

## Decision Rules

| Condition | Winner |
|-----------|--------|
| Variant A tingkat ≥ 40% (close to A1's 47.3%) | **A** — cheapest, ship it |
| A < 40% and B ≥ 45% | **B** — 2.5× tokens justified |
| C achieves B's accuracy at < 50% of B's cost | **C** — selective wins |
| All variants < 40% | **Reconsider** — maybe raw text is unavoidable |

---

## What's NOT in Scope

- **jenis_kegiatan, kelompok_kegiatan** — deferred. GT for these columns doesn't exist yet. Can be added later if mentor requests (new GT columns + FORM_OPTIONS already in `master_data.py`).
- **Integration into `extraction_pipeline.py`** — deferred until winner is known.
- **Model comparison** — llama3.1:8b only for this experiment.
- **OCR improvements** — out of scope.

---

## Aturan Main

1. **Commit dulu** sebelum eksperimen. Backup files yang akan diubah.
2. **Mode experiment** — buat file baru (`*_v3.py`), jangan timpa existing.
3. **Gagal?** `git checkout` untuk balik.
4. **Berhasil?** Merge ke production code, run `uv run python -m pytest tests/ -v`.
5. **Run benchmark** setelah merge untuk dokumentasi improvement.
6. **Semua panggilan Ollama harus mencatat `prompt_eval_count` dan `eval_count`** — sama seperti Phase v4.

### Running Tests
```bash
uv run python -m tests.benchmark_llm_v3        # NEW: 3 variants benchmark
uv run python -m tests.benchmark_llm_v2        # Previous winner (A2 v2) reference
uv run python -m tests.benchmark_llm           # A1 reference
```

---

## Referensi

| File | What's there |
|------|--------------|
| `docs/handoff_v5.md` | Full Phase v4 methodology, gotchas, results |
| `docs/phase_v4_methodology.md` | Prompt templates, architecture, lessons |
| `docs/phase_v4_results_summary.xlsx` | Visual comparison of all methods |
| `tests/llm_extractor.py` | Ollama client, validators, token logger (reuse these) |
| `tests/llm_extractor_v2.py` | Full-text prompt (reference for heuristics) |
| `tests/benchmark_llm.py` | Hybrid+PP baseline runner (reference structure) |
| `tests/benchmark_llm_v2.py` | Full-text benchmark (reference structure) |

## Gotchas to remember (from Phase v4)

1. **Model naming:** `llama3.2:8b` doesn't exist → use `llama3.1:8b`.
2. **Ollama server:** needs `nohup ollama serve > /tmp/ollama.log 2>&1 &`.
3. **num_predict:** default 30 truncates long output. Variant B prompt is short → 30 is fine.
4. **EVAL_FIELDS:** patch `ev_fw.EVAL_FIELDS[:]` in-place to add tingkat.
5. **Tingkat heuristics MUST be in prompt** or LLM defaults to "Universitas".
6. **LLM outputs numbered lines** (`1. tingkat: value`) — strip with `re.sub(r'^\d+[\.\)]?\s*', '', key)`.
7. **FORM_OPTIONS tingkat:** use "Lainnya", not "UKM".
8. **benchmark_runs/ is gitignored** — results are local-only.
