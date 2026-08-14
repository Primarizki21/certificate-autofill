# Evaluation Methodology Report

*Certificate Autofill Prototype - Benchmark Metrics, Formulas, and Analysis*

Evaluation Methodology Report

Certificate Autofill Prototype

Benchmark Metrics, Formulas, and Analysis

July 2026

## 1. Introduction

This document describes the evaluation methodology used to assess the accuracy of field extraction from student certificates. The system extracts structured fields (event name, dates, organizer, certification number, activity level) from PDF certificates and maps them to a standardized form.

Scope: 74 ground-truth certificates covering 6 extracted fields, evaluated across multiple extraction methods (regex, NER, hybrid, LLM).

The evaluation framework is implemented in tests/evaluation_framework.py with matching logic in tests/matchers.py.

## 2. Evaluated Fields

The following fields are extracted from each certificate and compared against ground truth:

| Field | Type | Description |
|---|---|---|
| nama_kegiatan_sertifikasi | Text | Event/activity name |
| waktu_mulai_pelaksanaan | Date | Start date |
| waktu_selesai_pelaksanaan | Date | End date |
| penyelenggara_kegiatan | Text | Organizer name |
| nomor_bukti_fisik_nomor_sertifikasi | Structured | Certificate number |
| tingkat | Categorical | Activity level (L1-L6) |

## 3. Metrics Definitions

Each extracted field is evaluated using the following metrics. All string comparisons use normalized values (lowercase, special characters removed).

### 3.1 Exact Match

Formula:

exact = normalize(expected) == normalize(actual)

Binary metric: 1 if normalized strings are identical, 0 otherwise. Normalization lowercases text and strips non-alphanumeric characters (except /). For dates, both sides are first normalized to DD/MM/YYYY format. For certification numbers, whitespace and punctuation are stripped.

Pros:

Simple and interpretable.

Gold standard for structured fields (dates, numbers).

Penalizes minor formatting differences.

Cons:

Sensitive to OCR errors and abbreviations.

Does not capture partial correctness.

Two strings differing by one character score 0.

### 3.2 Fuzzy Match

Formula:

fuzzy = contains OR (token_overlap >= 0.5) OR abbreviation_match

Binary metric: 1 if any of three sub-conditions hold. (a) Contains: expected is a substring of actual or vice versa, after normalization. (b) Token overlap >= 0.5: at least half of the shorter string's tokens appear in the other. (c) Abbreviation match (penyelenggara_kegiatan and nama_kegiatan_sertifikasi only): checks if one string is an acronym of the other (e.g., BEM FEB matches Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis).

Pros:

Tolerates reordering and partial matches.

Captures abbreviations common in organizer names.

More realistic than exact for free-text fields.

Cons:

Threshold (0.5) is a design choice, not theoretically derived.

Abbreviation match can produce false positives on short strings.

Bidirectional contains can over-match on very short expected values.

### 3.3 Token Overlap Score

Formula:

token_overlap = |expected_tokens ∩ actual_tokens| / min(|expected_tokens|, |actual_tokens|)

Continuous metric [0, 1]. Measures the fraction of tokens from the shorter string that appear in the longer string. Uses set intersection (order-insensitive). Tokens are space-delimited after normalization.

Pros:

Captures partial correctness numerically.

Order-insensitive.

Used as input to fuzzy match threshold.

Cons:

Does not penalize extra tokens in actual.

Ignores token ordering.

Can be high for short strings with one matching token.

### 3.4 Word Error Rate (WER)

Formula:

WER = min(Levenshtein(ref_words, hyp_words) / |ref_words|, 1.0)

Continuous metric [0, 1]. Measures the minimum number of word-level edits (insertions, deletions, substitutions) needed to transform the reference into the hypothesis, normalized by reference length. Computed on raw (un-normalized) words for dates, and on normalized words for text fields.

Pros:

Standard metric in speech recognition and NLP.

Captures edit distance at word granularity.

Penalizes both missing and extra words.

Cons:

Sensitive to word boundary differences.

Does not account for semantic similarity.

A perfect substring match with one extra word can still score high.

### 3.5 Character Error Rate (CER)

Formula:

CER = min(Levenshtein(ref_chars, hyp_chars) / |ref|, 1.0)

Continuous metric [0, 1]. Same as WER but at character level. More granular than WER — a single typo in one word increases CER but may not affect WER if word boundaries differ.

Pros:

More granular than WER.

Catches character-level OCR errors.

Useful for short fields (dates, numbers).

Cons:

Can be noisy for long text fields.

Same semantic content with different characterizations scores poorly.

Less interpretable than WER for non-technical audiences.

### 3.6 Contains Match

Formula:

contains = (normalize(expected) in normalize(actual)) OR (normalize(actual) in normalize(expected))

Binary metric: 1 if one normalized string is a substring of the other. Bidirectional — checks both directions. Useful when the extractor returns a superset of the expected value (e.g., full name vs. abbreviation).

Pros:

Simple bidirectional substring check.

Catches partial matches (e.g., organizer name truncated).

Used as input to fuzzy match.

Cons:

Bidirectional can over-match on short strings.

Does not measure degree of overlap.

Sensitive to normalization differences.

### 3.7 Confidence Score

Formula:

confidence = extractor_confidence (range: 0.0 to 1.0)

Not a comparison metric — measures the extractor's self-reported confidence in its output. Used for thresholding in hybrid pipelines (e.g., fields with confidence < 0.7 are sent to LLM for re-extraction). Range and interpretation depend on the extraction method (regex: pattern match quality; NER: model probability; LLM: heuristic-based).

Pros:

Enables selective LLM invocation.

Useful for identifying uncertain extractions.

Method-dependent — not comparable across extractors.

Cons:

Not a ground-truth comparison metric.

Threshold selection is heuristic.

Can be poorly calibrated.

## 4. Aggregation

### 4.1 Per-Field Metrics

For each field, metrics are aggregated across all certificates:

exact_acc(field) = count(exact=1) / count(all)

fuzzy_acc(field) = count(fuzzy=1) / count(all)

avg_wer(field) = mean(WER_i) for all certificates

avg_cer(field) = mean(CER_i) for all certificates

### 4.2 Overall Metrics (macro_avg)

The macro_avg in this codebase is technically a micro-average — it sums correct predictions across all fields and divides by total predictions across all fields:

macro_avg = Σ exact_ok(field) / Σ total(field)

This weights fields with more certificates (e.g., nama_kegiatan with 74 predictions) more heavily than fields with fewer (e.g., tingkat with fewer if some are excluded). A true macro-average would compute the mean of per-field accuracies, giving equal weight to each field regardless of count.

Trade-off: Micro-average is more stable (less variance from small fields) but can mask poor performance on rare fields. For this dataset with 74 certificates and relatively balanced field coverage, the difference is small.

## 5. Evaluation Pipeline

The evaluation follows a 4-step pipeline:

Step 1: Ground Truth Loading

Load Ground_Truth_Sertifikat.csv (74 rows, 8 columns). Each row maps a PDF filename to its expected field values. The TINGKAT_GT_MAP translates old GT labels to canonical form.

Step 2: Field Extraction

Each certificate is processed by one or more extraction methods (regex, NER, LLM). The extractor returns a dict of ExtractedValue objects (value, confidence, source).

Step 3: Matching

evaluate_row() in evaluation_framework.py iterates over EVAL_FIELDS, calling match_field() from matchers.py for each field. match_field() applies field-specific normalization (dates via normalize_date, numbers via normalize_nomor) before computing exact, fuzzy, WER, CER, contains, and token_overlap.

Step 4: Aggregation

aggregate_results() collects per-field counts and computes exact_acc, fuzzy_acc, avg_wer, avg_cer, and the overall micro-average.

## 6. Benchmark Methods

The following extraction methods have been benchmarked:

| Method | Approach | Key Characteristics |
|---|---|---|
| Regex Baseline | PyMuPDF + Docling + OCR + regex patterns | Fast (~0.1s/cert), no ML deps |
| NER v1 | IndoBERT NER (treamyracle/indobert-ner-gold) | ~0.07s/cert, needs GPU |
| Hybrid (NER+regex) | NER for text fields, regex for structured | Combines strengths of both |
| Hybrid+PP | Hybrid + post-processing (filter_signer_roles) | Best non-LLM method |
| LLM A1 (per-field) | Ollama llama3.1:8b, per-field prompts | 834 tok/cert, 47.3% tingkat |
| LLM A2 v2 (full-text) | Ollama llama3.1:8b, full text prompt | 834 tok/cert, 36.5% tingkat |
| LLM v3 Variant A | Context-only prompt, no raw text | 410 tok/cert, 24.3% tingkat |
| LLM v3 Variant B | Context + minimize_text() relevant lines | 479 tok/cert, 39.2% tingkat |

## 7. Results Summary

Latest benchmark results on 74 certificates (llama3.1:8b for LLM variants):

| Method | Tokens/cert | Tingkat | MACRO exact | Acc/token | Latency |
|---|---|---|---|---|---|
| Regex Baseline | 0 | 0% | 38.8% | — | ~0.1s |
| NER v1 | 0 | 0% | 18.4% | — | ~0.07s |
| Hybrid+PP | 0 | 0% | 46.4% | — | ~0.6s |
| LLM A1 | 834 | 47.3% | 49.0% | 0.057 | ~2s |
| LLM A2 v2 | 834 | 36.5% | 58.3% | 0.044 | ~2.5s |
| LLM v3-A | 410 | 24.3% | 43.5% | 0.059 | ~1s |
| LLM v3-B | 479 | 39.2% | 46.4% | 0.082 | ~1s |

## 8. Error Analysis

### 8.1 Error Types

The mismatches.csv output categorizes errors into two types:

null — Extractor returned no value

The field was not extracted at all. Common causes: regex pattern did not match, NER entity not recognized, LLM returned TIDAK_DITEMUKAN or an invalid response.

mismatch — Extractor returned wrong value

A value was extracted but does not match ground truth. Common causes: OCR errors propagated through extraction, incorrect field boundary detection, organizer name abbreviated differently than GT, date format mismatch.

### 8.2 Common Error Patterns

penyelenggara_kegiatan: Most common errors — organizer names vary significantly between extraction and GT (e.g., BEM FEB vs. full name).

nama_kegiatan_sertifikasi: Event names with parenthetical descriptions or subtitles often mismatch.

tingkat: 25 of 74 certificates are Nasional level with no explicit signal in the text (requires external knowledge).

nomor_bukti_fisik: OCR errors in certificate numbers (e.g., 0 vs O, 1 vs I) cause mismatches.

waktu_mulai/selesai: Date format variations (e.g., 29/09/2024 vs 29 September 2024) are mostly handled by normalize_date, but edge cases remain.

## 9. Limitations and Caveats

The micro-average labeled 'macro_avg' in code is not a true macro-average. See Section 4.2.

Tingkat evaluation is limited: 25 of 74 certificates have no text signal for Nasional level, capping maximum achievable accuracy.

Abbreviation matching is heuristic-based and can produce false positives on short strings (< 2 words).

Confidence scores are method-dependent and not comparable across extractors.

The 74-certificate dataset is small and skewed toward specific certificate types (UNAIR events). Results may not generalize.

WER/CER are computed on normalized text, which may not reflect the true edit distance of the original strings.

LLM evaluation uses temperature=0 for determinism, but Ollama's quantized model may produce different results across runs.

## 10. Handoff v7/v8 Evaluation Addendum

### 10.1 Ground Truth Versioning

Starting from v8, evaluation runs state which ground truth they used. Ground_Truth_Sertifikat.csv is the raw historical CSV (unchanged). Ground_Truth_Sertifikat_v8.csv applies 3 audited tingkat corrections: 1966887 Lainnya->Nasional, 1981676 Fakultas->Nasional, 2954283 Fakultas->Internasional. 2030372 stays Nasional (consistent with the identical-template 1981676).

Metrics are reported three ways: (a) raw-GT accuracy, (b) fixed-GT accuracy, (c) ceiling-adjusted accuracy with the disputed certificates excluded, so label noise is separated from method quality.

### 10.2 Tingkat Scale-Evidence Check

verify_ground_truth.py now scans the raw text for scale evidence (TINGKAT NASIONAL, LOMBA, INTERNASIONAL, INTERNATIONAL, foreign-institution hints) and flags ground-truth labels that contradict the text. Pre-v8 this check did not exist, which is why label noise survived.

### 10.3 Router Precision and Call Reduction

| Metric | v7 (P4) | v8 |
|---|---|---|
| Router decisions | 35/74 | 39/74 |
| Router precision | 100% | 100% |
| LLM calls / 74 | 39 | 35 |
| Call reduction vs no-router | 47% | 53% |

v8 adds contains-based BEM/HIMA matching for OCR-merged tokens and the explicit TINGKAT NASIONAL rule. Precision stays at 100% on the fixed ground truth.

### 10.4 Token Accounting

Effective tokens per document = total tokens (prompt + completion) across all LLM calls, amortized over all 74 certificates. Certificates routed by rules contribute 0 tokens. This is reported per variant in token_usage_*.json. v8 final: f_bias = 214 eff tokens/cert (21.4M tokens per 100K requests), slightly above the 200 gate; per the handoff rule, the accuracy floor is preserved first.

### 10.5 Layout Representation Evaluation

Markdown (## title) and annotated ([TITLE]/[BODY]/[SMALL]) representations built from PyMuPDF page.get_text('dict') were compared against the plain-text baseline at matched token budgets. Only 25/74 certificates contain embedded text; the rest are scanned and fall back to OCR text. Both layout variants underperformed the plain baseline (77.0% / 78.4% vs 82.4% tingkat), so layout is rejected. Input quality is bound by OCR, not layout, on this dataset.

### 10.6 Final v8 Ship Gate

| Metric | Target | Actual | Status |
|---|---|---|---|
| Tingkat exact | >= 45% | 82.4% | PASS |
| MACRO exact | >= 50% | 55.2% | PASS |
| Eff. tokens/doc | <= 200 | 214 | MARGINAL |
| 100K-request tokens | <= 20M | 21.4M | MARGINAL |
| LLM call reduction | >= 40% | 53% | PASS |
| Rule precision | >= 95% | 100% | PASS |
| Date / number regression | none | none | PASS |

Caveats: the 74-certificate dataset is small, skewed to UNAIR templates, and not held-out; Ollama quantization adds run-to-run variance of about +/-1-2pp; the macro_avg label is a micro-average (see Section 4.2).

### 10.7 Results Summary (experiments)

| Experiment | Tingkat exact | MACRO exact | Eff tok/cert | LLM calls | Router | GT |
|---|---|---|---|---|---|---|
| LLM A1 (per-field) | 47.3% | 49.0% | 834 | 125 | - | raw |
| LLM A2 v2 (full-text) | 36.5% | 58.3% | 834 | 74 | - | raw |
| LLM v3 Variant B | 39.2% | 46.4% | 479 | 74 | - | raw |
| v7 P3 router rule-based | 71.6% | 53.1% | 191 | 42 | - | raw |
| v7 P4 e_hybrid + router | 77.0% | 54.2% | 202 | 39 | 35/74 @100% | raw |
| v8 f_bias + router | 82.4% | 55.2% | 214 | 35 | 39/74 @100% | fixed_v8 |
| OCR Trial A — PaddleOCR 2.9 (CPU) | n/a | 39.8% | 0 | 0 | - | fixed_v8 |
| OCR Trial A — EasyOCR (CPU, max-side 960) | n/a | 34.3% | 0 | 0 | - | fixed_v8 |
| OCR Trial A — EasyOCR (GPU, full-res) | n/a | 39.3% | 0 | 0 | - | fixed_v8 |
| v9 organizer_v2 + router fix | 83.8% | 58.9% | 176 | 29 | 45/74 @100% | v8 |
| v9 winner re-baseline (GT v9 + matcher v2) | 83.8% | 60.2% | 176 | 29 | 45/74 @100% | v9 |
| NC-001 nomor crop preprocessing (re-render region zoom 6x) | n/a | 46.3% | 0 | 0 | - | v9 |
| OCR-006 DocTR probe (mobilenet CPU, 10 scan) | n/a | 40.0% | 0 | 0 | - | v9 |
| OCR-007 LFM2.5-VL-3B probe (VLM OCR, GGUF Q4_0 + mmproj Q8_0, 10 scan) | n/a | 44.4% | 0 | 0 | - | v9 |
| HYB-001 hybrid OCR per-field (DocTR dates+organizer / baseline nomor) | n/a | 46.8% | 0 | 0 | - | v9 |
| NC-002 region-OCR murah (rapid / tess psm tunggal) utk 2-pass nomor | n/a | 47.3% | 0 | 0 | - | v9 |
| F1 organizer v3 + R6 (0 LLM) | 81.1% | 61.2% | 0 | 0 | - | v9 |
| F1 normalisasi organizer & nomor (0 LLM) | 81.1% | 58.3% | 0 | 0 | - | v9 |
| ORG-004 canonicalisasi format (0 LLM) | 81.1% | 63.5% | 0 | 0 | - | v9 |
| PROD-002 port produksi organizer v3+R3+R6+format + nomor (flag-gated) | 81.1% | 63.0% | 0 | 0 | - | v9 |
| AKT-002 deteksi nama_kegiatan v2 (0 LLM) | 81.1% | 68.8% | 0 | 0 | - | v9 |
| AKT-003 deteksi nama_kegiatan v3: Sebagai Peserta + atthe/inthe (0 LLM) | 81.1% | 71.6% | 0 | 0 | - | v9 |
| AKT-004 deteksi nama_kegiatan v4: Event/lomba/seminar on (0 LLM, gate scope-kecil) | 81.1% | 72.1% | 0 | 0 | - | v9 |
| AKT-005 deteksi nama_kegiatan v5: grup D all-caps/spacing (0 LLM) | 81.1% | 73.7% | 0 | 0 | - | v9 |
