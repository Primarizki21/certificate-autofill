# Phase v4 Methodology

> **Experiment:** Comparing LLM extraction methods for certificate autofill
> **Model:** llama3.1:8b (Q4_K_M, ~6GB VRAM, RTX 5050)
> **Dataset:** 74 certificates from Universitas Airlangga
> **Date:** July 30, 2026

---

## 1. Experiment Overview

Goal: find the most token-efficient method for extracting structured fields from Indonesian certificate PDFs. Two LLM-based approaches were tested against a baseline (Hybrid+PP at 38.8% MACRO).

**Winner: Approach 2 v2 (full-text extraction)** — 58.3% MACRO exact at 61,706 tokens (1,058 tokens per % MACRO point).

---

## 2. Baseline (Hybrid+Post-Processing)

Before adding LLM, the pipeline uses:

1. **PyMuPDF** — fast text extraction from PDF
2. **Docling/RapidOCR** — fallback when text is empty
3. **OCR date check** — force OCR if date fields missing
4. **NER (IndoBERT)** — pre-trained entity recognition
5. **Regex** — pattern matching for dates, orgs, roles
6. **Post-processing** — entity scoring, NOR fallback, signer filtering

Baseline MACRO: 38.8% exact (including tingkat at 0%).

---

## 3. Approach 1 — Per-Field LLM

**Architecture:**

```
PDF → NER+regex → known_fields → check empty/low-confidence
                                     ↓
             ┌─────────────────────────────────────┐
             │ For each empty/low-conf field:       │
             │   1. Build single-field prompt       │
             │   2. Call Ollama (1 field per call)  │
             │   3. Validate response               │
             │   4. Log token usage                 │
             └─────────────────────────────────────┘
```

**Calls:** 125 total (74 tingkat + 34 nomor + 16 nama_kegiatan + 1 penyelenggara)

**Tokens:** 61,679 (60,851 prompt + 828 completion)

**Prompt template (tingkat):**
```
Tentukan TINGKAT KEGIATAN dari sertifikat berikut.

ATURAN WAJIB:
- Jawaban HARUS persis salah satu dari opsi di bawah
- JANGAN jawab selain opsi ini

PETUNJUK TINGKAT:
- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat FAKULTAS (BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas
- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa (HIMATESDA, HIMANO), maka == Departemen/Program Studi
- Jika diselenggarakan oleh BEM Universitas, Rektorat, Direktorat Kemahasiswaan, maka == Universitas
- Jika kegiatan berskala nasional (lomba nasional, webinar nasional), maka == Nasional
- Jika kegiatan berskala internasional (konferensi internasional), maka == Internasional
- 'UNIVERSITAS AIRLANGGA' adalah institusi induk, BUKAN penentu tingkat

Opsi yang diizinkan: [Internasional, Nasional, Universitas, Fakultas, Departemen/Program Studi, Lainnya]

Field yang sudah diketahui: [nama_kegiatan, penyelenggara, peran]
Teks sertifikat: {raw_text}
Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):
```

**Result:** MACRO 49.0% (+10.2pp over baseline)

---

## 4. Approach 2 v2 — Full-Text LLM (Winner)

**Architecture:**

```
PDF → raw_text
     ↓
One prompt per cert (all 6 fields)
     ↓
LLM → "tingkat: value\nnama_kegiatan: value\n..."
     ↓
Parse: strip numbered prefix → alias lookup → validate each field
     ↓
Post-process: if waktu_selesai missing, copy from waktu_mulai
```

**Calls:** 74 (1 per cert)

**Tokens:** 61,706 (53,788 prompt + 7,918 completion)

**Prompt template (full-text):**
```
Dari sertifikat berikut, ekstrak semua field yang diperlukan.

ATURAN WAJIB:
- Jawaban HANYA format "field: nilai" (satu field per baris)
- Setiap field harus dijawab
- Jika tidak ditemukan: field: TIDAK_DITEMUKAN
- Jika hanya SATU tanggal, gunakan untuk waktu_mulai DAN waktu_selesai
- Format tanggal: DD/MM/YYYY

PETUNJUK TINGKAT:
- Jika diselenggarakan oleh BEM/BEM tingkat FAKULTAS → Fakultas
- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa → Departemen/Program Studi
- Jika diselenggarakan oleh BEM Universitas/Rektorat → Universitas
- Kegiatan nasional → Nasional, kegiatan internasional → Internasional
- 'UNIVERSITAS AIRLANGGA' adalah institusi induk, BUKAN penentu tingkat

Field yang perlu diekstrak:
1. tingkat: [opsi: Internasional, Nasional, Universitas, Fakultas, Departemen/Program Studi, Lainnya]
2. nama_kegiatan: (nama acara, maks 100 karakter)
3. penyelenggara: (organisasi/panitia penyelenggara, maks 100 karakter)
4. waktu_mulai: (DD/MM/YYYY)
5. waktu_selesai: (DD/MM/YYYY)
6. nomor_bukti: (nomor sertifikat)

Teks sertifikat: {raw_text}
Jawaban:
```

**Parser design:**
- Key:Value split on first colon
- Strip numbered prefixes: `re.sub(r'^\d+[\.\)]?\s*', '', key)`
- Alias lookup: flexible matching for 20+ variations ("nama kegiatan", "activity name", "organizer", etc.)
- Date validation: DD/MM/YYYY or DD-MM-YYYY → normalized
- Nomor: compact remove whitespace

**Post-processing:**
```python
if "waktu_selesai" not in validated and "waktu_mulai" in validated:
    validated["waktu_selesai"] = validated["waktu_mulai"]
```

**Result:** MACRO 58.3% (+19.5pp over baseline)

---

## 5. Comparison by Field

| Field | Baseline | A1 (per-field) | A2 v2 (full-text) | Why A2 v2 wins |
|-------|:--------:|:-------------:|:----------------:|----------------|
| nama_kegiatan | 24.3% | 25.7% | **43.2%** | Full context helps LLM pick the right event name |
| penyelenggara | 13.5% | 13.5% | **31.1%** | LLM sees org names scattered in text; regex misses most |
| waktu_mulai | 81.8% | 81.8% | **94.5%** | LLM handles garbled date strings like "24September2023" |
| waktu_selesai | 81.8% | 81.8% | **94.5%** | Post-process: copy from mulai when only one date found |
| nomor | 59.6% | 65.4% | **73.1%** | LLM finds cert numbers in garbled text |
| tingkat | 0% | **47.3%** | 36.5% | A1 has dedicated prompt with heuristics; A2 has them too but less effective |
| **MACRO** | **38.8%** | **49.0%** | **58.3%** | |

---

## 6. Token Efficiency

| Metric | A1 (per-field) | A2 v2 (full-text) | Savings |
|--------|:-------------:|:----------------:|:-------:|
| Tokens per % MACRO | 1,259 | **1,058** | -16% |
| Prompt tokens | 60,851 | **53,788** | -12% |
| Total calls | 125 | **74** | -41% |

A2 v2 is more token-efficient because the raw text (largest token cost) is sent once instead of 1-5 times.

---

## 7. Gotchas & Lessons Learned

### Ollama & Model
| # | Gotcha | Detail |
|---|--------|--------|
| 1 | **Model naming** | `llama3.2:8b` does NOT exist. Llama 3.2 has 1B/3B/11B only. Use `llama3.1:8b` for 8B. `llama3.2:latest` is the 3B model. |
| 2 | **Server startup** | Ollama server dies when bash session ends. Use `nohup ollama serve > /tmp/ollama.log 2>&1 &` |
| 3 | **num_predict limit** | Default 30 truncates full-text output. Full-text needs `max_tokens=200`. |

### Evaluation
| # | Gotcha | Detail |
|---|--------|--------|
| 4 | **EVAL_FIELDS patching** | `evaluate_row()` uses module-level `EVAL_FIELDS`. Must patch `ev_fw.EVAL_FIELDS[:]` in-place to add fields. |
| 5 | **benchmark_runs/ gitignore** | Results are local-only. Reproduce with `uv run python -m tests.benchmark_llm_v2`. |

### Prompt Engineering
| # | Gotcha | Detail |
|---|--------|--------|
| 6 | **Tingkat heuristics** | Without explicit rules (BEM→Fakultas, HIMA→Prodi), LLM defaults to "Universitas" because "UNIVERSITAS AIRLANGGA" is prominent in text. |
| 7 | **Same-date post-processing** | Copy waktu_mulai→waktu_selesai if selesai missing. Fixes 49% of errors at 0 token cost. |
| 8 | **Numbered output** | LLM outputs `1. tingkat: value`. Parser must strip `^\d+[\.\)]?\s*` from key. |

### Data
| # | Gotcha | Detail |
|---|--------|--------|
| 9 | **FORM_OPTIONS tingkat** | Use "Lainnya" not "UKM". Verified against production form dropdown. |

---

## 8. Files

### New files created in Phase v4

| File | Purpose |
|------|---------|
| `tests/llm_extractor.py` | Ollama client, prompt builders, validators, token logger (approach 1) |
| `tests/benchmark_llm.py` | Benchmark runner for approach 1 (per-field LLM) |
| `tests/llm_extractor_v2.py` | Full-text prompt, multi-field parser, post-processing (approach 2) |
| `tests/benchmark_llm_v2.py` | Benchmark runner for approach 2 (full-text LLM) |
| `docs/phase_v4_results_summary.xlsx` | Visual results with 4 sheets |
| `docs/phase_v4_results_summary.md` | Results in markdown |
| `docs/phase_v4_methodology.md` | This document |
| `docs/phase_v4_methodology.docx` | Methodology in DOCX format |

### Modified files

| File | Change |
|------|--------|
| `backend/app/master_data.py` | FORM_OPTIONS["tingkat"]: "UKM" → "Lainnya" |

---

## 9. Next Steps

- **Integrate A2 v2 into `extraction_pipeline.py`** for production use
- **Try Qwen 2.5 7B** — possibly better at structured output, might improve tingkat
- **Try PaddleOCR** — better text extraction could improve all methods
- **Fine-tune NER with 200+ labeled certs** — if Label Studio data becomes available

---

## 10. Reproducing Results

```bash
# Start Ollama
nohup ollama serve > /tmp/ollama.log 2>&1 &

# Approach 1 (per-field LLM)
uv run python -m tests.benchmark_llm

# Approach 2 v2 (full-text LLM) — winner
uv run python -m tests.benchmark_llm_v2
```
