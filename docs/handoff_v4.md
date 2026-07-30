# Handoff v4 — Hybrid Post-Processing + LLM Inference (Ollama)

> Supersedes `docs/handoff_v3.md`. V3 covered NER fine-tuning (failed — catastrophic forgetting with 59 samples).
> This document covers Phase v3 (hybrid post-processing) and Phase v4 (LLM inference via Ollama for unknown fields).

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
| P1 | Hybrid Post-Processing | ⏳ NEXT | Entity selection, role filtering, normalization |
| P2 | LLM Inference (Ollama) | ⏳ | Unknown fields only, token usage tracked |
| P3 | LLM Benchmark vs Hybrid | ⏳ | Compare methods on same 74 certs |

---

## Phase v2 Results — What We Learned

### Hybrid Benchmark (50.3% exact, 64.4% fuzzy)

| Field | Regex | NER v1 | Hybrid | Target |
|-------|-------|--------|--------|--------|
| nama_kegiatan (exact) | 6.9% | 16.4% | **17.6%** | >40% |
| nama_kegiatan (fuzzy) | 19.2% | 43.8% | **48.6%** | — |
| penyelenggara (exact) | 6.9% | 11.0% | **10.8%** | >50% |
| penyelenggara (fuzzy) | 41.1% | 50.7% | **50.0%** | — |
| waktu_mulai (exact) | **81.8%** | 27.3% | **81.8%** | — |
| waktu_selesai (exact) | **81.8%** | 7.3% | **81.8%** | — |
| nomor (exact) | **58.0%** | 0.0% | **59.6%** | — |
| **MACRO (exact)** | 42.2% | 12.8% | **50.3%** | >55% |
| **MACRO (fuzzy)** | 53.3% | 28.8% | **64.4%** | — |

### Why Fine-Tuning Failed

- **59 training samples** — too few for full fine-tuning
- **82% class imbalance** — model defaults to "O" (no entity)
- **Catastrophic forgetting** — fine-tuned model (1.5%) worse than pre-trained (12.8%)
- **Verdict:** Fine-tuning needs 200+ labeled certs. Not worth it now.

### Root Causes of Remaining Errors

| Problem | Impact | Fix |
|---------|--------|-----|
| **No layout awareness** | NER picks wrong entity (signer role as organizer) | Context understanding needed |
| **Single-max selection** | Longest entity ≠ right entity | Candidate ranking |
| **Signer roles as ORG** | "Ketua Pelaksana" tagged as organization | Post-processing filter |
| **Garbled OCR tokens** | `2023levelupyourself` passed as one token | Text normalization |
| **No abbreviation normalization** | "BEM FEB UNAIR" vs full name | Dictionary |

**Key insight:** OCR quality is NOT the bottleneck. Clean text exists but NER fails due to lack of context.

---

## Current Hybrid Extraction Rates

| Field | Filled by hybrid | Empty (LLM target) |
|-------|-----------------|-------------------|
| nama_kegiatan | 55/74 (74%) | 19 |
| penyelenggara | 73/74 (99%) | 1 |
| waktu_mulai | 62/74 (84%) | 12 |
| waktu_selesai | 58/74 (78%) | 16 |
| nomor | 40/74 (54%) | 34 |
| tingkat | 0/74 | 74 (always) |
| kelompok | 0/74 | 74 (always) |
| jenis | 0/74 | 74 (always) |

---

## Phase v3 — Hybrid Post-Processing

### Goal
Push hybrid from 50.3% → 55-60% exact through post-processing improvements.

### Step 1: Entity Selection Improvements
**File:** `tests/ner_to_fields.py`

**Current behavior:** Picks the longest entity for each type.
**Problem:** Longest entity is often a tagline or garbled multi-word string.

**Proposed changes:**
1. Instead of `max(merged, key=len)`, use a scoring function:
   - Prefer entities with capital letters (title case)
   - Prefer entities with numbers (e.g., "2024", "4.0")
   - Penalize entities with OCR artifacts (consonant clusters, no spaces)
   - Prefer entities closer to the start of the text (title position)
2. Add entity deduplication — if two EVT entities overlap, keep the better one
3. Add minimum/maximum length constraints (activity name: 3-80 chars)

**Expected gain:** +3-5pp nama_kegiatan

### Step 2: Signer Role Filtering
**File:** `tests/ner_to_fields.py` or new `tests/post_processors.py`

**Problem:** "Ketua Pelaksana", "Dekan", "Direktur" tagged as ORG.

**Proposed changes:**
1. Create a blacklist of signer role patterns:
   ```
   Ketua, Dekan, Direktur, Presiden, Sekretaris, Bendahara,
   Pembina, Kepala, Prof., Dr., NIP, NIM
   ```
2. After NER extraction, filter ORG entities that match role patterns
3. If filtered entity is the only ORG candidate, keep it (might be mislabeled but still relevant)

**Expected gain:** +3-5pp penyelenggara

### Step 3: Text Normalization Pre-Pass
**File:** `tests/ner_extractor.py`

**Problem:** OCR output has concatenated words (`2023levelupyourself`).

**Proposed changes:**
1. Before NER inference, normalize the text:
   - Insert spaces before capital letters: `2023Level` → `2023 Level`
   - Insert spaces between digits and letters: `2023level` → `2023 level`
   - Fix common OCR artifacts: `FTMM` → keep, `fmmas` → might be `FTMM`
2. This is a lightweight regex-based pass, not full OCR correction

**Expected gain:** +2-3pp nama_kegiatan, +1-2pp penyelenggara

### Step 4: Abbreviation Normalization
**File:** `tests/ner_to_fields.py` or `app/services/form_mapper.py`

**Problem:** NER extracts full name, GT expects abbreviation (or vice versa).

**Proposed changes:**
1. Create a dictionary of common abbreviations:
   ```
   BEM FTMM ↔ Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin
   FEB ↔ Fakultas Ekonomi dan Bisnis
   HIMA ↔ Himpunan Mahasiswa
   UNAIR ↔ Universitas Airlangga
   ```
2. After NER extraction, check if the extracted value matches any abbreviation
3. Normalize to the form used in GT (check which form appears more in the CSV)

**Expected gain:** +2-3pp penyelenggara

### Step 5: Benchmark and Validate
- Run hybrid benchmark with all improvements
- Compare vs baseline (50.3%)
- Target: 55-60% exact

### Time Estimate: 1-2 days

---

## Phase v4 — LLM Inference for Unknown Fields (Ollama)

### Goal
Use local LLM (via Ollama) to infer fields that NER+regex cannot extract. LLM receives only known fields + raw text as context and returns just the value — minimal tokens, minimal cost.

### Architecture

```
PDF → NER+regex → known fields (fast, deterministic)
         ↓
    Check which fields are empty
         ↓
    Build prompt with known fields
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
    Validate response + combine with known fields
```

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
| `nama_kegiatan` | When NER+regex returns empty | ~19 |
| `penyelenggara` | When NER+regex returns empty | ~1 |
| `nomor_bukti` | When NER+regex returns empty | ~34 |

**Total LLM calls:** ~276 (74 × 3 + 19 + 1 + 34)
**Estimated tokens:** ~276 × 200 input + ~276 × 10 output = ~58K tokens
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
1. Hybrid only (baseline: 50.3%)
2. Hybrid + LLM (target: 65%+)
3. Track token usage per file
4. Compare latency, accuracy, cost

### Time Estimate: 2-3 days

---

## Benchmark Comparison Plan

### Methods to Compare

| Method | Description | Expected Accuracy | Latency |
|--------|-------------|-------------------|---------|
| Regex only | Current baseline | 42.2% | ~0.1s/cert |
| NER v1 only | Pre-trained NER | 12.8% | ~0.07s/cert |
| Hybrid | NER + regex | 50.3% | ~0.5s/cert |
| Hybrid + post-processing | Phase v3 | 55-60% | ~0.6s/cert |
| Hybrid + LLM | Phase v4 | 65%+ | ~2-5s/cert |

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
  ner_extractor.py              # NER model loading + inference
  ner_to_fields.py              # NER entities → form field mapping (TO MODIFY)
  post_processors.py            # NEW: entity filtering, normalization
  benchmark_ner.py              # NER benchmark runner
  benchmark_pipeline.py         # Regex benchmark runner
  benchmark_hybrid.py           # NEW: unified hybrid+LLM benchmark
  evaluation_framework.py       # Core eval: exact, fuzzy, WER, CER
  matchers.py                   # Matching functions
  generate_bio_labels.py        # BIO label generation
  fine_tune_ner.py              # Fine-tuning script (reference only)
  verify_ground_truth.py        # GT verification
backend/
  app/services/
    llm_extractor.py            # NEW: LLM inference via Ollama
    field_extractor.py          # Regex extraction
    form_mapper.py              # Rule-based mapping
    extraction_pipeline.py      # Pipeline orchestrator (TO MODIFY)
```

---

## Execution Order

```
Day 1:
  - Install Ollama on Linux, pull llama3.2:8b
  - Phase v3 Step 1: Entity selection scoring
  - Phase v3 Step 2: Signer role filtering

Day 2:
  - Phase v3 Step 3: Text normalization pre-pass
  - Phase v3 Step 4: Abbreviation normalization
  - Phase v3 Step 5: Benchmark post-processing → commit

Day 3:
  - Phase v4 Step 1: Build llm_extractor.py + test Ollama
  - Phase v4 Step 2: Integrate with pipeline

Day 4:
  - Phase v4 Step 3: Run LLM benchmark
  - Phase v4 Step 4: Compare results vs hybrid
  - Commit all results
```

---

## Aturan Main

1. **Commit dulu** sebelum eksperimen. Backup files yang akan diubah.
2. **Mode experiment** — buat file baru (`*_experiment.py`), jangan timpa existing.
3. **Gagal?** `git checkout` untuk balik.
4. **Berhasil?** Merge ke production code, run `uv run python -m pytest tests/ -v`.
5. **Run benchmark** setelah merge untuk dokumentasi improvement.
6. **Benchmark harus menghasilkan file CSV + XLSX + token usage JSON.**
7. **NEW:** Semua panggilan Ollama harus mencatat `prompt_eval_count` dan `eval_count`.

### Running Tests
```bash
uv run python -m pytest tests/ -v     # All tests
uv run python -m tests.benchmark_pipeline  # Regex benchmark
uv run python -m tests.benchmark_ner       # NER benchmark
uv run python -m tests.benchmark_hybrid    # NEW: Hybrid + LLM benchmark
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

This handoff is a **proposal, not a prescription.** The phases and steps are based on what we learned, but:

1. **Phase v3 post-processing may not be enough.** If entity selection + role filtering doesn't reach 55%, consider:
   - Using layout information (bounding boxes from PyMuPDF)
   - Adding more ORG/EVT patterns to regex
   - Collecting more training data for fine-tuning

2. **Phase v4 LLM model choice is flexible.** Start with `llama3.2:8b`, but test alternatives:
   - `qwen2.5:7b` — better for structured extraction
   - `phi4-mini:3.8b` — faster, fits in less VRAM

3. **Token tracking is critical.** The Ollama API returns `prompt_eval_count` and `eval_count` — log these for every call. This data enables the comparison benchmark.

4. **The fine-tuning path is not dead.** If you can get 200+ labeled certs via Label Studio, fine-tuning could work. The BIO label generation script (`generate_bio_labels.py`) is ready.

5. **OCR improvement is deferred but not forgotten.** If post-processing and LLM don't close the gap, consider:
   - PaddleOCR (better for Indonesian)
   - Cloud OCR APIs (Google Vision, AWS Textract)
   - Layout-aware models (LayoutLMv3)
