# Handoff v5 — Phase v4 LLM Inference via Ollama

> Supersedes `docs/handoff_v4.md`. V4 covered Phase v3 (post-processing) and Phase v4 (LLM inference) as proposals. Phase v3 is now **complete**. This document records actual Phase v3 results and provides the detailed Phase v4 implementation plan.

---

## Current Status

| Prioritas | Eksperimen | Status | Catatan |
|-----------|-----------|--------|---------|
| P0 | Evaluation Framework | ✅ DONE | `tests/evaluation_framework.py` + WER/CER + XLSX |
| P0 | Baseline Benchmark (regex) | ✅ DONE | `run_20260728_131835/` — 42.2% exact macro |
| P0 | Pre-trained NER (v1) | ✅ DONE | `run_ner_v1_20260730_095336/` — 16.4% activity, 11% organizer |
| P0 | Ground Truth Verification | ✅ DONE | `tests/verify_ground_truth.py` — 2 cert numbers fixed |
| P0 | BIO Label Generation | ✅ DONE | `tests/generate_bio_labels.py` — 77% match rate |
| P0 | Hybrid Benchmark | ✅ DONE | NER + regex — **50.3% exact, 64.4% fuzzy** |
| ~~P1~~ | ~~Fine-tune NER (v2)~~ | ❌ FAILED | Catastrophic forgetting, F1=0.15 |
| P1 | Hybrid Post-Processing | ✅ DONE | `66190dd` + `62193fe` — **48.1% exact, 66.1% fuzzy** |
| P2 | LLM Inference (Ollama) | ⏳ NEXT | Unknown fields only, token usage tracked |
| P3 | LLM Benchmark vs Hybrid | ⏳ | Compare methods on same 74 certs |

> **Note:** Hybrid+PP macro (48.1%) is lower than v4's 50.3% because the GT CSV was updated after v4 was written (2 cert numbers added, stricter evaluation). The actual extraction quality improved — NER nama_kegiatan went 16.4% → 24.3%.

---

## Phase v3 — What We Implemented

### Files Changed

| File | Change | Approach |
|------|--------|----------|
| `tests/ner_extractor.py` | Added `normalize_for_ner()` | Splits OCR concatenation at digit↔letter and case boundaries |
| `tests/post_processors.py` | **New file** | Entity scoring (universal properties), signer role detection (NIP/NIM proximity), person-name filtering |
| `tests/ner_to_fields.py` | Scoring-based selection + NOR fallback | Picks best entity by score, NOR as ORG fallback, date range splitting |
| `tests/matchers.py` | Abbreviation matching | First-letter heuristic (50% threshold), bidirectional check |
| `backend/app/services/field_extractor.py` | English patterns | "as a participant in", "participated in", "held by", "organized by", "presented by" |
| `tests/benchmark_hybrid.py` | **New file** | Unified benchmark: NER / Hybrid / Hybrid+PP comparison |

### Actual Results

| Field | Hybrid | Hybrid+PP | Delta |
|-------|--------|-----------|-------|
| nama_kegiatan exact | 24.3% | 24.3% | — |
| nama_kegiatan fuzzy | 63.5% | 63.5% | — |
| penyelenggara exact | 12.2% | 13.5% | **+1.3pp** |
| penyelenggara fuzzy | 47.3% | 50.0% | **+2.7pp** |
| waktu_mulai exact | 81.8% | 81.8% | — |
| waktu_selesai exact | 81.8% | 81.8% | — |
| nomor exact | 59.6% | 59.6% | — |
| **MACRO exact** | 47.7% | **48.1%** | **+0.4pp** |
| **MACRO fuzzy** | 65.5% | **66.1%** | **+0.6pp** |

### What Worked

1. **normalize_for_ner** — splits `24September2023` → `24 September 2023`, enabling NER to tokenize correctly. NER exact improved 12.8% → 18.4%.
2. **Abbreviation matching** — "BEM FTMM" ↔ "Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin" detected via first-letter heuristic. Fuzzy +5.4pp.
3. **NOR fallback** — when NER labels correct organizer as NOR instead of ORG, we try NOR entities. Added +1.3pp penyelenggara exact.
4. **English patterns** — caught "as a participant in" for English certificates. NER nama_kegiatan +1.3pp.

### What Didn't Help Much

1. **Signer role filtering** — correct ORG often not in NER output (labeled as NOR, or missing entirely). Filter removes wrong entities but remaining candidates are often still wrong.
2. **Person name detection** — structural heuristic only catches recipients after "diberikan kepada". Many person names appear elsewhere.
3. **Scoring function** — NER lowercases all entity text, so the title-case bonus was broken (now fixed via position check). Even with the fix, the scoring can't create entities that NER didn't produce.

### Key Learning

**Post-processing can only re-rank existing entities.** If the correct answer isn't in NER's output, no amount of scoring will find it. The remaining 52% of failures need either better OCR or LLM inference.

---

## Root Causes of Remaining Errors (Updated)

| Problem | # certs affected | Post-processing status | Needs |
|--------|------------------|----------------------|-------|
| Garbled OCR text (no spaces, concatenated) | ~39 | Partially fixed by normalize_for_ner | LLM to parse garbled text |
| Regex always picks "UNIVERSITAS AIRLANGGA" over student org | ~18 | NOR fallback helps marginally | LLM context understanding |
| English certificates (no Indonesian patterns) | ~8 | English patterns added | LLM for ambiguous cases |
| Date picked from wrong line | ~4 | Date range split helps | Layout awareness |
| Cert number completely absent from text | ~15 | NER gets 0%, regex gets 59.6% | LLM inference |
| NER labels correct organizer as NOR, not ORG | ~5 | NOR fallback helps | Already partially fixed |

---

## Phase v4 — LLM Inference via Ollama

### Goal

Use local LLM to fill fields that NER+regex cannot extract. Two categories:

1. **Always empty** (never extracted by NER/regex): `tingkat`, `kelompok_kegiatan`, `jenis_kegiatan`
2. **Sometimes empty/wrong**: `nama_kegiatan` (~19 empty), `nomor_bukti` (~34 empty), `penyelenggara` (wrong value in ~61 certs)

### Architecture

```
PDF → NER+regex → known_fields (fast, deterministic)
         ↓
    Check which fields are empty or low-confidence
         ↓
    For each empty/low-confidence field:
    ┌─────────────────────────────────────────┐
    │ Known from certificate:                  │
    │ - Event: Dataquest 4.0                   │
    │ - Organizer: BEM FTMM Universitas Airlangga│
    │ - Role: Panitia                          │
    │ - Dates: 23 Aug - 21 Sep 2025            │
    │                                          │
    │ Question: What is the Tingkat?           │
    │ (Fakultas/Departemen/Prodi/Universitas/Nasional) │
    └─────────────────────────────────────────┘
         ↓
    Ollama → "Fakultas" (~10 tokens output)
         ↓
    Validate response + combine with known_fields
```

**Key difference from handoff_v4:** Also call LLM when NER/regex returns a value but with LOW confidence (< 0.7), as an alternative extraction. LLM can often correct wrong extractions.

### Hardware: RTX 5050 8GB VRAM

| Model | Params | Q4_K_M Size | VRAM | Speed | Quality |
|-------|--------|-------------|------|-------|---------|
| **Llama 3.2 8B** | 8B | 4.9GB | ~6GB | ~42 tok/s | Strong general |
| Qwen 2.5 7B | 7B | 4.4GB | ~5.5GB | ~45 tok/s | Best for structured |
| Phi-4 Mini 3.8B | 3.8B | 2.3GB | ~3GB | ~75 tok/s | Fastest |

**Recommendation:** Start with `llama3.2:8b`. Fits comfortably at Q4_K_M.

### Ollama API — Token Usage Tracking

Ollama API response includes usage metrics that must be logged:

```json
{
  "model": "llama3.2:8b",
  "response": "Fakultas",
  "done": true,
  "total_duration": 174560334,
  "load_duration": 101397084,
  "prompt_eval_count": 156,
  "prompt_eval_duration": 13074791,
  "eval_count": 8,
  "eval_duration": 52479709
}
```

| Metric | Description | How to use |
|--------|-------------|------------|
| `prompt_eval_count` | Input tokens | Cost calculation, prompt optimization |
| `eval_count` | Output tokens | Cost calculation, response length |
| `prompt_eval_duration` | Prompt processing time (ns) | Latency analysis |
| `eval_duration` | Generation time (ns) | Throughput (tokens/s = eval_count / eval_duration × 10^9) |
| `total_duration` | Total time (ns) | End-to-end latency |

### Fields to Infer via LLM

| Field | When to call LLM | Expected calls |
|-------|-----------------|----------------|
| `tingkat` | Always (never extracted by NER/regex) | 74 |
| `kelompok_kegiatan` | Always (never extracted) | 74 |
| `jenis_kegiatan` | Always (never extracted) | 74 |
| `nama_kegiatan` | When NER+regex returns empty OR confidence < 0.7 | ~30 |
| `penyelenggara` | When NER+regex returns empty OR confidence < 0.7 | ~65 |
| `nomor_bukti` | When NER+regex returns empty | ~34 |

**Total LLM calls:** ~351 (74 × 3 + 30 + 65 + 34 + margin)
**Estimated tokens:** ~351 × 200 input + ~351 × 10 output = ~74K tokens
**Estimated cost:** Free (local Ollama)

### Prompt Template

```
Dari sertifikat berikut, tentukan {field_name}.

Teks sertifikat:
{raw_text}

Field yang sudah diketahui:
- Nama Kegiatan: {nama_kegiatan or "tidak diketahui"}
- Penyelenggara: {penyelenggara or "tidak diketahui"}
- Waktu: {waktu_mulai} - {waktu_selesai}
- Nomor: {nomor or "tidak diketahui"}
- Peran: {role or "tidak diketahui"}

Jawaban (hanya satu nilai, tanpa penjelasan):
```

### Validation Rules

| Field | Valid values | Invalid response handling |
|-------|-------------|-------------------------|
| `tingkat` | Fakultas, Departemen, Program Studi, Universitas, Nasional | Leave empty |
| `kelompok_kegiatan` | Must match one of FORM_OPTIONS in `app/master_data.py` | Leave empty |
| `jenis_kegiatan` | Must match one of FORM_OPTIONS in `app/master_data.py` | Leave empty |
| `nama_kegiatan` | Any string 3-100 chars | Leave empty |
| `penyelenggara` | Any string 3-100 chars | Leave empty |
| `nomor_bukti` | Pattern: digits/letters/.../year | Leave empty |

### Step 1: Setup Ollama
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull llama3.2:8b

# Verify
ollama run llama3.2:8b "Hello"
```

### Step 2: Build LLM Extractor
**File:** `backend/app/services/llm_extractor.py` (new)

Functions:
- `infer_unknown_fields(raw_text, known_fields, empty_fields)` → dict of inferred values
- `call_ollama(prompt, model="llama3.2:8b")` → response + token usage
- `validate_response(field, value)` → bool
- `build_prompt(raw_text, known_fields, field)` → str

### Step 3: Integrate with Pipeline
**File:** `backend/app/services/extraction_pipeline.py`

```
1. Run NER+regex → known_fields
2. Check empty_fields = [f for f in ALL_FIELDS if not known_fields.has(f)]
3. If empty_fields:
   a. Build prompt with known_fields + raw_text
   b. Call Ollama once per empty field (or batch in one prompt)
   c. Validate each response
   d. Merge into known_fields
4. Return combined result
```

### Step 4: Benchmark LLM vs Hybrid
**File:** `tests/benchmark_llm.py` (new)

Run on same 74 certs:
1. Hybrid+PP only (baseline: 48.1%)
2. Hybrid+PP + LLM (target: 65%+)
3. Track token usage per file
4. Compare latency, accuracy, cost

### Actual Results (v4 complete)

### Method Comparison

| Method | MACRO exact | MACRO fuzzy | Calls | Total tokens | Tokens per % | Latency/cert | Notes |
|--------|:---------:|:---------:|:----:|:----------:|:----------:|:----------:|-------|
| Baseline (Hybrid+PP) | 38.8% | 53.4% | 0 (no LLM) | 0 | — | ~0.6s | No LLM cost |
| A1 — per-field LLM | 49.0% | 64.6% | 125 | 61,679 | 1,259 | ~2s (4×0.5s) | Calls LLM per empty field |
| **A2 v2 — full-text LLM** | **58.3%** | **74.5%** | **74** | **61,706** | **1,058** | **~2.5s** | **Winner: best accuracy/token** |

### Per-Field Comparison (Best in bold)

| Field | Baseline | A1 (per-field) | A2 v2 (full-text) |
|-------|:------:|:-----------:|:--------------:|
| nama_kegiatan | 24.3% | 25.7% | **43.2%** |
| penyelenggara | 13.5% | 13.5% | **31.1%** |
| waktu_mulai | 81.8% | 81.8% | **94.5%** |
| waktu_selesai | 81.8% | 81.8% | **94.5%** |
| nomor | 59.6% | 65.4% | **73.1%** |
| tingkat | 0.0% | **47.3%** | 36.5% |
| **MACRO** | 38.8% | 49.0% | **58.3%** |

### Key Findings
1. **Approach 2 (full-text) wins on accuracy and token efficiency** — MACRO 58.3% vs 49.0%, same token budget.
2. **Full context helps** — LLM sees all text at once and decides which field each piece belongs to. This helps nama_kegiatan (+13.5pp over A1) and penyelenggara (+17.6pp).
3. **Tingkat heuristics must be in the prompt** — without explicit rules (BEM FTMM → Fakultas), LLM defaults to "Universitas" from the prominent "UNIVERSITAS AIRLANGGA" text.
4. **Same-date post-processing** — copying waktu_mulai → waktu_selesai when selesai is missing recovered +49pp for waktu_selesai (45.5% → 94.5%).
5. **Token tracking per field available** — `calls.json` in benchmark_runs/ directories contain per-call records for cross-method comparison.

### What to Try Next
- **Better OCR (PaddleOCR)** — would reduce garbled text and help both LLM and regex
- **Qwen 2.5 7B** — better at structured output, might improve tingkat past 36.5%
- **Hybrid:** Use A2 v2 for most fields, but if tingkat is still low, add a separate tingkat-focused prompt (approach 1 style) as a second call
- **Integrate into extraction_pipeline.py** — A2 v2 is production-ready: 1 LLM call per cert,~2.5s, 58.3% MACRO

### Time: ~3h total (incl. approach 1 + 2 runs, fixes, analysis)

---

## Benchmark Comparison Plan

### Methods to Compare

| Method | Description | Actual Accuracy | Latency |
|--------|-------------|-----------------|---------|
| Regex only | Baseline | 42.2% | ~0.1s/cert |
| NER v1 only | Pre-trained NER | 18.4% | ~0.07s/cert |
| Hybrid | NER + regex | 47.7% | ~0.5s/cert |
| Hybrid + post-processing | Phase v3 (current) | **48.1%** | ~0.6s/cert |
| Hybrid + LLM | Phase v4 (target) | **65%+** | ~2-5s/cert |

### Metrics to Track per File

| Metric | Source | Purpose |
|--------|--------|---------|
| Exact match | `evaluation_framework.py` | Accuracy |
| Fuzzy match | `evaluation_framework.py` | Near-miss accuracy |
| Input tokens | Ollama API `prompt_eval_count` | Cost/optimization |
| Output tokens | Ollama API `eval_count` | Cost/optimization |
| Latency (ms) | Ollama API `total_duration` | Speed |
| Tokens/sec | Ollama API `eval_count / eval_duration × 10^9` | Throughput |

### Output Files

```
tests/benchmark_runs/
  run_regex_*/           # Regex baseline
  run_ner_v1_*/          # NER v1
  run_hybrid_*/          # Hybrid (current)
  run_hybrid_pp_*/       # Hybrid + post-processing
  run_hybrid_llm_*/      # Hybrid + LLM
    results.json         # Accuracy metrics
    token_usage.json     # Token counts + latency per field
    summary.md           # Human-readable report
```

---

## File Structure (Current + Planned)

```
tests/
  ner_extractor.py              # NER model loading + inference + normalize_for_ner
  ner_to_fields.py              # NER entities → form field mapping (scoring + NOR fallback)
  post_processors.py            # Entity scoring, signer role detection, person-name filter
  benchmark_ner.py              # NER benchmark runner
  benchmark_pipeline.py         # Regex benchmark runner
  benchmark_hybrid.py           # Unified hybrid+PP benchmark
  evaluation_framework.py       # Core eval: exact, fuzzy, WER, CER
  matchers.py                   # Matching functions + abbreviation detection
  generate_bio_labels.py        # BIO label generation
  fine_tune_ner.py              # Fine-tuning script (reference only)
  verify_ground_truth.py        # GT verification
backend/
  app/services/
    llm_extractor.py            # NEW: LLM inference via Ollama
    field_extractor.py          # Regex extraction (English patterns added)
    form_mapper.py              # Rule-based mapping
    extraction_pipeline.py      # Pipeline orchestrator (TO MODIFY for LLM)
```

---

## Execution Order

```
Day 1:
  - Install Ollama on Linux, pull llama3.2:8b
  - Build llm_extractor.py (call_ollama, build_prompt, validate_response)
  - Test Ollama on 3 sample certs manually

Day 2:
  - Integrate llm_extractor.py with extraction_pipeline.py
  - Run benchmark_hybrid.py to confirm baseline unchanged
  - Build benchmark_llm.py

Day 3:
  - Run LLM benchmark on all 74 certs
  - Compare Hybrid+PP vs Hybrid+PP+LLM
  - Tune prompt if accuracy < 60%

Day 4:
  - Commit all results
  - Update benchmark_runs/ with final numbers
```

---

## Aturan Main

1. **Commit dulu** sebelum eksperimen. Backup files yang akan diubah.
2. **Mode experiment** — buat file baru (`*_experiment.py`), jangan timpa existing.
3. **Gagal?** `git checkout` untuk balik.
4. **Berhasil?** Merge ke production code, run `uv run python -m pytest tests/ -v`.
5. **Run benchmark** setelah merge untuk dokumentasi improvement.
6. **Benchmark harus menghasilkan file CSV + XLSX + token usage JSON.**
7. **Semua panggilan Ollama harus mencatat `prompt_eval_count` dan `eval_count`.**

### Running Tests
```bash
uv run python -m pytest tests/ -v     # All tests
uv run python -m tests.benchmark_pipeline  # Regex benchmark
uv run python -m tests.benchmark_ner       # NER benchmark
uv run python -m tests.benchmark_hybrid    # Hybrid + PP benchmark
uv run python -m tests.benchmark_llm       # NEW: Hybrid + LLM benchmark
```

---

## Referensi

| Paper | Judul | Relevansi |
|-------|-------|-----------|
| [2505.13535] | BLOCKIE — LLM extraction | LLM approach for certificate extraction |
| [2404.10848] | LayoutLMv3 + EM+BBO | Document AI approach (alternative) |

### NER Models

| Model | Type | F1 | Notes |
|-------|------|-----|-------|
| `treamyracle/indobert-ner-gold` | Pre-trained | 79.9% | Currently used (NER v1) |
| `indobenchmark/indobert-base-p1` | Base model | — | Fine-tuned failed (59 samples) |

### Tools

| Tool | Purpose |
|------|---------|
| HuggingFace transformers | NER model loading + inference |
| seqeval | NER evaluation metrics |
| openpyxl | Excel output for benchmark results |
| Ollama | Local LLM inference (llama3.2:8b) |

---

## Notes for Next Agent

1. **Phase v3 hit its ceiling.** Post-processing can only re-rank existing entities. The remaining 52% failures need LLM or better OCR. Don't spend more time on post-processing tweaks — the marginal returns are minimal.

2. **LLM doesn't need perfect OCR text.** Even garbled text like `bemfebunair2023socialaction2023` can be parsed by LLM. The LLM's strength is context understanding, not OCR correction.

3. **Token tracking is critical.** The Ollama API returns `prompt_eval_count` and `eval_count` — log these for every call. This data enables the comparison benchmark.

4. **Prompt engineering matters.** The prompt template includes known fields as context. This helps LLM infer unknown fields. Test different prompt versions if accuracy is low.

5. **Validation is essential.** LLM may hallucinate. Always validate responses against FORM_OPTIONS for constrained fields (tingkat, kelompok_kegiatan, jenis_kegiatan). Leave field empty if LLM returns invalid value.

6. **The fine-tuning path is not dead.** If you can get 200+ labeled certs via Label Studio, fine-tuning could work. The BIO label generation script (`generate_bio_labels.py`) is ready.

7. **OCR improvement is deferred.** If LLM doesn't close the gap, consider PaddleOCR (better for Indonesian) or cloud OCR APIs (Google Vision, AWS Textract).
