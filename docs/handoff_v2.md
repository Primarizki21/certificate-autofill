# Handoff v2 — NER Experiment

> V1 handoff: `docs/handoff.md` (evaluation framework + regex experiments)
> This document supersedes P1/P2/P3 experiments from v1 with NER-first approach.

---

## Current Status

| Prioritas | Eksperimen | Status | Catatan |
|-----------|-----------|--------|---------|
| P0 | Evaluation Framework | ✅ DONE | `tests/evaluation_framework.py` |
| P0 | Baseline Benchmark | ✅ DONE | `tests/benchmark_runs/run_20260728_131835/` |
| P0 | Benchmark Pipeline Optimization | ✅ DONE | Folder output, CSVs, extracted texts |
| P1 | Pre-trained NER (v1) | ⏳ NEXT | Run `indobert-ner-gold` on 74 certs |
| P1 | Fine-tune NER (v2) | ⏳ | If v1 promising, label + train |
| P2 | LLM for Non-Derivable Fields | ⏳ | tingkat, kelompok, jenis via systematic prompt |
| ~~P1~~ | ~~OCR Confidence Capture~~ | ❌ SKIPPED | Regex accuracy is the bottleneck, not confidence |
| ~~P1~~ | ~~Confidence Threshold~~ | ❌ SKIPPED | Same reason |
| ~~P2~~ | ~~Line-Level OCR~~ | ❌ SKIPPED | OCR already 82% on dates |
| ~~P3~~ | ~~Conformal Prediction~~ | ❌ SKIPPED | Premature without better extraction |
| ~~P3~~ | ~~LayoutLMv3 Fine-Tune~~ | ❌ SKIPPED | NER is simpler, same goal |

---

## Baseline Benchmark Results

**Run:** `tests/benchmark_runs/run_20260728_131835/`
**Date:** 2026-07-28
**Files processed:** 74 (0 skipped, 0 errors)
**Total time:** 447.8s (6.05s avg/file)
**Parser distribution:** 60 pymupdf+ocr, 14 pymupdf only

### Per-Field Accuracy

| Field | Total | Exact% | Fuzzy% | Avg Conf | Status |
|-------|-------|--------|--------|----------|--------|
| `waktu_mulai_pelaksanaan` | 55 | **81.8%** | 81.8% | 0.76 | Good — keep regex |
| `waktu_selesai_pelaksanaan` | 55 | **81.8%** | 81.8% | 0.76 | Good — keep regex |
| `nomor_bukti_fisik_nomor_sertifikasi` | 50 | **58.0%** | 58.0% | 0.70 | OK — improve regex |
| `penyelenggara_kegiatan` | 73 | **6.9%** | 41.1% | 0.71 | Bad — switch to NER |
| `nama_kegiatan_sertifikasi` | 73 | **6.9%** | 19.2% | 0.20 | Bad — switch to NER |
| **MACRO** | 306 | **42.2%** | 53.3% | — | — |

### Error Analysis Summary

| Problem | Count | Root Cause | Fix |
|---------|-------|-----------|-----|
| `nama_kegiatan_sertifikasi` null | 57/73 | Regex patterns don't match most certificate formats | NER |
| `penyelenggara_kegiatan` wrong entity | ~30 | Regex falls back to generic `known_orgs` list | NER |
| `penyelenggara_kegiatan` expanded vs abbreviation | ~12 | No normalizer for "Badan Eksekutif Mahasiswa" → "BEM" | String normalizer |
| `penyelenggara_kegiatan` OCR garbage | ~8 | Poor OCR on image-based PDFs | Better OCR preprocessing |
| Date mismatches | 3 | OCR misread year/date | Not fixable by extraction logic |

---

## Why NER Over More Regex

The regex approach has a structural problem: every new certificate format requires a new pattern. With 73 certificates from ~30 different institutions, we'd need 50+ regex patterns and constant maintenance.

NER generalizes from examples — one trained model handles all institutions, all formats, all phrasings. The 57 null activity names are the killer evidence: regex can't find "Dataquest 4.0" or "GAMMAFEST 2025" because there's no surrounding context phrase to anchor on. NER doesn't need anchors — it learns what event names look like.

---

## NER Experiment Plan

### Phase v1: Pre-trained NER (No Training)

**Model:** `treamyracle/indobert-ner-gold` (Indonesian BERT, 19 entity types)
**Effort:** ~1 day. No labeling, no training.
**Input:** `tests/benchmark_runs/run_20260728_131835/extracted_texts/*.txt`

**What it does:**
1. Load pre-trained NER model from HuggingFace
2. Run inference on each certificate's extracted text
3. Extract entity spans: ORG (organization), DAT (date), EVT (event), LOC (location), NUM (number)
4. Map entities to form fields:
   - ORG spans → `penyelenggara_kegiatan`
   - EVT/title spans → `nama_kegiatan_sertifikasi`
   - DAT spans → `waktu_mulai/waktu_selesai` (validation only — regex already 82%)
   - NUM spans → `nomor_bukti_fisik` (fallback only — regex already 58%)

**Files to create:**
- `tests/ner_extractor.py` — load model, run inference, return entities
- `tests/ner_to_fields.py` — map NER entities → form field values
- `tests/benchmark_ner.py` — run on all 74 certs, compare vs ground truth

**Dependencies:**
```bash
uv add transformers torch sentencepiece
```

**Success criteria:**
| Metric | Regex Baseline | NER v1 Target |
|--------|---------------|---------------|
| `penyelenggara_kegiatan` exact | 6.9% | >25% |
| `nama_kegiatan_sertifikasi` exact | 6.9% | >20% |
| `nama_kegiatan_sertifikasi` null rate | 78% | <50% |
| Overall macro exact | 42.2% | >50% |

**Revert:** Delete `tests/ner_*.py` files. Regex pipeline unchanged.

---

### Phase v2: Fine-tune NER (If v1 Promising)

**When:** Only if v1 shows NER can extract some entities correctly.
**Effort:** ~3-5 days (labeling is bottleneck).

**Data needs:**
- ~200 certificates labeled in BIO format
- 74 already have extracted text in `extracted_texts/*.txt`
- Label with custom entity types: `B-ORG`, `I-ORG`, `B-EVT`, `I-EVT`, `B-DAT`, `I-DAT`, `B-NUM`, `I-NUM`, `O`
- Use [Label Studio](https://labelstud.io/) for annotation

**Model:** Fine-tune `indobert-base-p1` (110M params, runs on CPU)
**Training:** LoRA (rank=8), seqeval metric, 3-5 epochs

**Success criteria:**
| Metric | NER v1 | NER v2 Target |
|--------|--------|---------------|
| `penyelenggara_kegiatan` exact | >25% | >50% |
| `nama_kegiatan_sertifikasi` exact | >20% | >40% |
| `nama_kegiatan_sertifikasi` null rate | <50% | <30% |

**Revert:** Delete fine-tuned model + experiment files. Pre-trained model untouched.

---

### Phase v3: LLM for Non-Derivable Fields

**When:** After NER extracts the raw entities from the certificate.
**Effort:** ~1 day (prompt engineering only).

**Fields that need LLM:**
| Field | Why LLM | Input to LLM |
|-------|---------|--------------|
| `tingkat` | Inferred from organizer + affiliation context | NER-ORG output + full text |
| `kelompok_kegiatan` | Inferred from role + activity type | NER-ORG + NER-EVT + role |
| `jenis_kegiatan` | Inferred from activity name + role | NER-EVT + role |

**Approach:** Systematic prompt with entity context:
```
Given this certificate text and extracted entities:
- Organizer: {NER-ORG}
- Event: {NER-EVT}
- Role: {regex-role}

What is the Tingkat? (Fakultas/Departemen/Program Studi/Universitas/Nasional)
What is the Kelompok Kegiatan?
What is the Jenis Kegiatan?
```

**Success criteria:** `tingkat` accuracy >80% (currently not evaluated — inferred field).

---

## Evaluation Methodology

### How NER Entities Map to Form Fields

```
NER Output (entity spans):
  ["Badan", "Eksekutif", "Mahasiswa", "Fakultas", "Teknologi", "Maju"]  →  type: ORG
  ["29", "September", "2024"]  →  type: DAT
  ["Dataquest", "4.0"]  →  type: EVT

Concatenate spans of same type:
  ORG → "Badan Eksekutif Mahasiswa Fakultas Teknologi Maju"
  DAT → "29 September 2024"
  EVT → "Dataquest 4.0"

Map to form fields:
  ORG → penyelenggara_kegiatan
  EVT → nama_kegiatan_sertifikasi
  DAT → waktu_mulai_pelaksanaan (validation)
```

### How to Compare NER vs Regex

1. Run NER on all 74 extracted_texts
2. Map entities → form fields
3. Compare using existing `matchers.py` (exact, contains, token overlap)
4. Generate same output structure: `mismatches.csv`, `summary.md`
5. Diff against regex baseline run

### Metrics

- **Primary:** Exact match % per field (same as regex baseline)
- **Secondary:** Null reduction (how many of the 57 null activity names does NER fill?)
- **Tertiary:** Fuzzy match % (partial correctness)

---

## Aturan Main

1. **Commit dulu** sebelum eksperimen. Backup files yang akan diubah.
2. **Mode experiment** — buat file baru (`*_experiment.py`), jangan timpa existing.
3. **Gagal?** `git checkout` untuk balik.
4. **Berhasil?** Merge ke production code, run `uv run python -m pytest tests/ -v` (verify 22/22 pass).
5. **Run benchmark** setelah merge untuk dokumentasi improvement.

---

## File Structure After NER Experiments

```
tests/
  ner_extractor.py          # NER model loading + inference
  ner_to_fields.py          # NER entities → form field mapping
  benchmark_ner.py          # NER benchmark runner
  ner_experiment.py         # Main experiment script
  extracted_texts/          # Already exists from benchmark
  benchmark_runs/           # Already exists, NER runs go here too
```

---

## Referensi

| Paper | Judul | Relevansi |
|-------|-------|-----------|
| [2505.13535] | BLOCKIE — LLM extraction | LLM approach for certificate extraction |
| [2404.10848] | LayoutLMv3 + EM+BBO | Document AI approach (alternative to NER) |
| [2508.21693] | Line-level OCR | OCR improvement (deferred) |

### NER Models

| Model | Type | Entities | F1 |
|-------|------|----------|-----|
| `treamyracle/indobert-ner-gold` | Pre-trained | 19 (PER, ORG, LOC, DAT, etc.) | 79.9% on NER_UI |
| `nahiar/BERT-NER` | Pre-trained | PER, ORG, LOC | Indonesian NER |
| `cahya/NusaBert-ner-v1.3` | Pre-trained | 18 | Previous SOTA |

### Tools

| Tool | Purpose |
|------|---------|
| [Label Studio](https://labelstud.io/) | BIO annotation for fine-tuning data |
| [HuggingFace transformers](https://huggingface.co/docs/transformers) | Model loading + inference |
| [seqeval](https://github.com/chakki-works/seqeval) | NER evaluation metrics |
