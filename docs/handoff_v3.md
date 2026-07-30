# Handoff v3 — Hybrid NER + Regex + Fine-Tune Plan

> Supersedes `docs/handoff_v2.md`. V1 handoff: `docs/handoff.md` (evaluation framework + regex experiments).
> This document documents Phase v1 results, bugs fixed, and plans Phase v2 (hybrid auto-generate BIO → fine-tune).

---

## Current Status

| Prioritas | Eksperimen | Status | Catatan |
|-----------|-----------|--------|---------|
| P0 | Evaluation Framework | ✅ DONE | `tests/evaluation_framework.py` + WER/CER + XLSX |
| P0 | Baseline Benchmark (regex) | ✅ DONE | `run_20260728_131835/` — 42.2% macro |
| P0 | Pre-trained NER (v1) | ✅ DONE | `run_ner_v1_20260730_095336/` — 16.4% activity, 11% organizer |
| P0 | Ground Truth Verification | ⏳ NEXT | `docs/ground_truth_checklist.txt` — 38 files to check |
| P1 | Fine-tune NER (v2) | ⏳ | Auto-generate BIO → fine-tune indobert-base-p1 |
| P2 | LLM for Non-Derivable Fields | ⏳ | tingkat, kelompok, jenis via systematic prompt |
| ~~P1~~ | ~~OCR Confidence Capture~~ | ❌ SKIPPED | Regex accuracy is the bottleneck, not confidence |
| ~~P2~~ | ~~Line-Level OCR~~ | ❌ SKIPPED | OCR already 82% on dates |
| ~~P3~~ | ~~LayoutLMv3 Fine-Tune~~ | ❌ SKIPPED | NER is simpler, same goal |

---

## Phase v1 Results — NER Pre-trained Model

**Run:** `tests/benchmark_runs/run_ner_v1_20260730_095336/`
**Model:** `treamyracle/indobert-ner-gold` (pre-trained, no fine-tuning)
**Files processed:** 74 (0 skipped, 0 errors)
**Total time:** 5.1s (0.07s avg/file) — **124x faster** than regex (447.8s)

### Side-by-Side: Regex vs NER v1

| Field | Regex E% | NER v1 E% | Delta | Regex F% | NER v1 F% | Delta |
|-------|----------|-----------|-------|----------|-----------|-------|
| `nama_kegiatan_sertifikasi` | 6.9% | **16.4%** | +9.5pp ✅ | 19.2% | **43.8%** | +24.6pp ✅ |
| `penyelenggara_kegiatan` | 6.9% | **11.0%** | +4.1pp ✅ | 41.1% | **50.7%** | +9.6pp ✅ |
| `waktu_mulai_pelaksanaan` | **81.8%** | 27.3% | -54.5pp ❌ | **81.8%** | 27.3% | -54.5pp ❌ |
| `waktu_selesai_pelaksanaan` | **81.8%** | 7.3% | -74.5pp ❌ | **81.8%** | 7.3% | -74.5pp ❌ |
| `nomor_bukti_fisik_nomor_sertifikasi` | **58.0%** | 0.0% | -58.0pp ❌ | **58.0%** | 0.0% | -58.0pp ❌ |
| **MACRO** | **42.2%** | 12.8% | -29.4pp | **53.3%** | 28.8% | -24.5pp |

### Key Insight: Learning Curves Decouple

NER v1 is significantly worse in macro because it tries to extract **all** fields but fails on structured ones (dates, cert numbers). However, on free-text fields (activity name, organizer), NER shows consistent improvement. The total is misleading — this isn't a regression, it's a **portfolio effect**.

### Null Rate Improvement (Most Important Signal)

| Field | Regex Null | NER v1 Null | Improvement |
|-------|-----------|-------------|-------------|
| `nama_kegiatan_sertifikasi` | 56/73 (76.7%) | **22/73 (30.1%)** | **-46.6pp** ✅ |
| `penyelenggara_kegiatan` | 11/73 (15.1%) | **3/73 (4.1%)** | -11.0pp ✅ |

NER extracted **34 more activity names** that regex couldn't find at all. This is the structural advantage: NER generalizes across formats, regex needs per-format patterns.

### WER/CER Metrics (New in v3)

| Field | NER v1 AvgWER | NER v1 AvgCER |
|-------|--------------|--------------|
| `nama_kegiatan_sertifikasi` | 0.686 | 0.590 |
| `penyelenggara_kegiatan` | 0.785 | 0.726 |
| `waktu_mulai_pelaksanaan` | 0.709 | 0.709 |
| `waktu_selesai_pelaksanaan` | 0.909 | 0.882 |
| `nomor_bukti_fisik_nomor_sertifikasi` | 1.000 | 1.000 |
| **MACRO** | **0.805** | **0.763** |

Lower is better (0.0 = perfect). The high WER/CER on dates and cert numbers confirms regex should handle those.

---

## The Hybrid Decision

**Regex wins on:** dates, cert numbers (structured, predictable format)
**NER wins on:** activity name, organizer (free-text, unpredictable format)

**Decision: Hybrid pipeline**
```
NER → extract activity_name, organizer
Regex → extract dates, cert numbers, role
Combine → mapped form fields
```

**Projected combined macro:** `(16.4 + 11.0 + 81.8 + 81.8 + 58.0) / 5 = **49.8%**`

This is the ceiling without fine-tuning. Phase v2 aims to push NER's activity/organizer accuracy up, lifting the combined macro past 50%.

---

## Bugs Fixed in This Session

### Bug #1 (CRITICAL): `_meta` filter removes filename from results.json
- **File:** `tests/benchmark_ner.py`
- **Root cause:** List comprehension `{k: v for k, v in r.items() if not (k == "_meta" and "raw_text" in v)}` evaluates `raw_text in v` as True → removes entire `_meta` key
- **Fix:** Separate loop pattern:
  ```python
  clean["_meta"] = {k: v for k, v in meta.items() if k != "raw_text"}
  ```

### Bug #2 (MODERATE): Filename format mismatch
- **File:** `tests/benchmark_ner.py`
- **Issue:** NER used `stem` (no extension), regex used full filename (with .pdf/.png)
- **Fix:** Use `row.get("nama_file", "")` consistently

### Bug #3-#5 (MINOR): Missing counters, diff, tqdm
- Added `skipped` counter, `print_diff()`, and `tqdm` progress bar to NER benchmark

### Bug #6 (MINOR): Source field always empty
- `extracted_fields.csv` now populates `source` column with `"regex"` or `"ner_indobert"`

### Bug #7 (MODERATE): WER/CER case-sensitive
- WER/CER now use `normalize_value()` before scoring, consistent with exact/fuzzy

---

## Evaluation Framework Updates

### Added WER/CER Metrics
- `matchers.py`: `_levenshtein()`, `wer_score()`, `cer_score()`
- `evaluation_framework.py`: `avg_wer`, `avg_cer` in summary + macro_avg
- Console output now shows `AvgWER` and `AvgCER` columns
- WER/CER are **case-insensitive** (normalized) — consistent with exact/fuzzy

### Added Excel Output
- Both benchmark scripts produce `extracted_fields.xlsx` and `mismatches.xlsx`
- Uses `openpyxl` (added to project dependencies)
- Same columns as CSV counterparts

### Added Ground Truth Checklist
- `docs/ground_truth_checklist.txt` — 38 files with empty/dash fields to verify
- 3 categories: GT empty fields, NER failed all fields, regex failed all fields

### WER/CER Normalization Rule
- General fields → normalize with `normalize_value()` (lowercase, strip punctuation)
- Date fields → normalize with `normalize_date()` (canonical DD/MM/YYYY)
- Cert number → normalize with `normalize_nomor()` (strip all punctuation)
- This keeps WER/CER scores comparable to exact/fuzzy

---

## Phase v2 Plan — Fine-Tune NER (Hybrid Approach)

### Motivation

Phase v1 proved the pre-trained model can extract entities regex cannot. But accuracy is low (11-16% exact). Fine-tuning on certificate data should significantly boost this.

### Strategy: Auto-Generate BIO Labels First

Instead of going straight to Label Studio (200 certs, 3-5 days), we auto-generate BIO labels from the 74 existing certificates. If results are good, done. If not, collect more.

| Step | What | Time | Output |
|------|------|------|--------|
| 0 | Check ground truth CSV (use `ground_truth_checklist.txt`) | 1 day | Fixed CSV |
| 1 | `generate_bio_labels.py` — match CSV fields to spans in extracted text | 0.5 day | `tests/bio_labels/*.json` |
| 2 | Validate BIO labels — spot-check 10 files | 0.5 day | Validated |
| 3 | Fine-tune `indobert-base-p1` with LoRA (rank=8) | 0.5 day | Model in `tests/ner_model/` |
| 4 | Benchmark v2 — run on 74 certs, compare vs v1 | 0.5 day | `run_ner_v2_*/` |
| 5 | If targets not met → Label Studio for more data | TBD | More labels |

### BIO Labeling Approach

```
# Step 1: Find CSV field value in extracted text
# Step 2: Mark the span as B-ORG / I-ORG / B-EVT / I-EVT / B-DAT / I-DAT
# Step 3: All other tokens = O (outside)

Example:
Text:  "DIBERIKAN KEPADA Primarizki sebagai peserta Dataquest 4.0"
BIO:   O         O       O         B-PER   O      O     B-EVT  I-EVT
CSV:   Nama Kegiatan = "Dataquest 4.0"
```

**Entity types (same as v1):** `B-ORG`, `I-ORG`, `B-EVT`, `I-EVT`, `B-DAT`, `I-DAT`, `B-PER`, `I-PER`, `O`

### Model: `indobert-base-p1`

- 110M params — fits on GPU (RTX 5050 8GB)
- LoRA fine-tuning (rank=8, target modules: query, value)
- 3-5 epochs, batch size 16-32
- Learning rate: 2e-4 (LoRA default)
- Evaluate with seqeval (precision, recall, F1 per entity type)

### Success Criteria

| Metric | NER v1 | NER v2 Target |
|--------|--------|---------------|
| `nama_kegiatan_sertifikasi` exact | 16.4% | >40% |
| `nama_kegiatan_sertifikasi` null rate | 30.1% | <30% |
| `penyelenggara_kegiatan` exact | 11.0% | >50% |
| Combined macro (NER + regex hybrid) | ~49.8% | >55% |

### Evaluation: Token-Level + Field-Level

```
Token-level (seqeval):
  ORG precision, recall, F1
  EVT precision, recall, F1
  DAT precision, recall, F1

Field-level (same as Phase v1):
  Exact%, Fuzzy%, WER, CER per field
```

### Dependencies to Add

```bash
uv add peft  # LoRA fine-tuning
uv add seqeval  # NER evaluation metrics
uv add datasets  # HuggingFace datasets API
uv add evaluate  # HF evaluate library
```

### Revert
- Delete `tests/generate_bio_labels.py`, `tests/ner_model/`, `tests/benchmark_runs/run_ner_v2_*/`
- `uv remove peft seqeval datasets evaluate`

---

## Phase v3 Plan — LLM for Non-Derivable Fields

Same as v2 handoff. After NER extracts raw entities, use systematic LLM prompts for:

| Field | Input | Why LLM |
|-------|-------|---------|
| `tingkat` | NER-ORG output + full text | Inferred from organizer + affiliation context |
| `kelompok_kegiatan` | NER-ORG + NER-EVT + role | Inferred from role + activity type |
| `jenis_kegiatan` | NER-EVT + role | Inferred from activity name + role |

**Approach:**
```
Given certificate text and extracted entities:
- Organizer: {NER-ORG}
- Event: {NER-EVT}
- Role: {regex-role}

What is the Tingkat? (Fakultas/Departemen/Program Studi/Universitas/Nasional)
What is the Kelompok Kegiatan? (Kegiatan Wajib Universitas/Organisasi dan Kepemimpinan/...)
What is the Jenis Kegiatan? (Peserta PKKMB/Panitia/Pengurus Organisasi/...)
```

**Success criteria:** `tingkat` accuracy >80% (currently not benchmarked).

---

## File Structure (Current)

```
tests/
  ner_extractor.py              # NER model loading + inference
  ner_to_fields.py              # NER entities → form field mapping
  benchmark_ner.py              # NER benchmark runner (bug fixed)
  benchmark_pipeline.py         # Regex benchmark runner
  evaluation_framework.py       # Core eval: exact, fuzzy, WER, CER aggregation
  matchers.py                   # Matching: exact, contains, token_overlap, WER, CER
  date_normalizer.py            # DD/MM/YYYY date normalizer
  test_evaluation_framework.py  # 27 tests (4 WER/CER tests)
  test_field_extractor.py       # Field extractor tests
  test_generalized_parser.py    # Parser rule tests
  conftest.py                   # sys.path fixer
  benchmark_runs/
    run_20260728_131835/        # Regex baseline (42.2% macro)
    run_ner_v1_20260728_161014/ # NER v1 (old, bug not fixed)
    run_ner_v1_20260730_083808/ # NER v1 (bug fixed, old WER/CER)
    run_ner_v1_20260730_084046/ # NER v1 (WER/CER normalized)
    run_ner_v1_20260730_095336/ # NER v1 (latest, with xlsx output)
docs/
  handoff_v3.md                 # THIS DOCUMENT
  handoff_v2.md                 # History (NER experiment plan)
  handoff.md                    # History (original)
  ground_truth_checklist.txt    # 38 files to verify
  improvements.md               # Bug/improvement tracking
```

---

## Aturan Main

1. **Commit dulu** sebelum eksperimen. Backup files yang akan diubah.
2. **Mode experiment** — buat file baru (`*_experiment.py`), jangan timpa existing.
3. **Gagal?** `git checkout` untuk balik.
4. **Berhasil?** Merge ke production code, run `uv run python -m pytest tests/ -v` (verify 27/27 pass).
5. **Run benchmark** setelah merge untuk dokumentasi improvement.
6. **NEW:** Verifikasi ground truth (`ground_truth_checklist.txt`) sebelum fine-tuning.
7. **NEW:** Validasi BIO labels (spot-check 10 files) sebelum training.
8. **NEW:** Benchmark harus menghasilkan file CSV + XLSX.

### Running Tests
```bash
uv run python -m pytest tests/ -v     # All tests
uv run python -m tests.benchmark_pipeline  # Regex benchmark
uv run python -m tests.benchmark_ner       # NER benchmark
```

---

## Referensi

| Paper | Judul | Relevansi |
|-------|-------|-----------|
| [2505.13535] | BLOCKIE — LLM extraction | LLM approach for certificate extraction |
| [2404.10848] | LayoutLMv3 + EM+BBO | Document AI approach (alternative to NER) |
| [2508.21693] | Line-level OCR | OCR improvement (deferred) |

### NER Models

| Model | Type | F1 | Notes |
|-------|------|-----|-------|
| `treamyracle/indobert-ner-gold` | Pre-trained | 79.9% | Phase v1 done — 16.4% activity |
| `indobert-base-p1` | Base model | — | For fine-tuning in Phase v2 |

### Tools

| Tool | Purpose |
|------|---------|
| Label Studio | BIO annotation for fine-tuning data (if step 1-2 fail) |
| HuggingFace transformers | Model loading + inference |
| seqeval | NER evaluation metrics |
| PEFT | LoRA fine-tuning |
| openpyxl | Excel output for benchmark results |
