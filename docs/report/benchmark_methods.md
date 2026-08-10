# Benchmark Methods

*Input, Process, and Output - Certificate Autofill Prototype*

Benchmark Methods

Input, Process, and Output

Certificate Autofill Prototype

July 2026

## 1. Introduction

This document describes six benchmark methods for certificate field extraction.

Each method section has two layers. The first layer explains the workflow in plain language. The second layer (Code Reference) maps each step to the corresponding code.

LLM methods also include a Prompt subsection. This subsection shows the full prompt text that is sent to the language model.

This document is a companion to evaluation_methodology.docx. That document describes how to measure accuracy. This document describes what each method does.

## 2. Pipeline Overview

The diagram below shows how each method builds on the previous one.

Arrows show the data flow from one method to the next.

PDF files (Sertifikat_Ground_Truth/)

|

v

[1] Regex Baseline -----> extracted text files (.txt)

|                       |

|                       v

|                  [2] NER v1 ---------> NER entities

|                       |

v                       v

[3] Hybrid (NER + Regex) ---> combined fields

|

v

[4] Hybrid+PP -----------> cleaned fields (signer removed)

|

v

[5] LLM A1 -----------> hybrid + LLM (per-field, conditional)

[6] LLM v3 -----------> hybrid + LLM (tingkat only)

Each method produces the same output format: a dict of ExtractedValue objects for the five evaluation fields.

## 3. Method 1: Regex Baseline

### 3.1 Overview

The regex baseline extracts text from PDF files with multiple parser engines. It then uses regex patterns to find each field. This method has no machine learning components.

### 3.2 Input

PDF files from Sertifikat_Ground_Truth/<folder>/<filename>.pdf

Ground truth CSV (Ground_Truth_Sertifikat.csv) for evaluation

### 3.3 Process

Extract text from the PDF. The system tries a fast text extractor first. This extractor opens the PDF and reads text from each page. It works on most certificates but produces short results on image-heavy or scanned PDFs.

If the fast extractor produces too little text, a more accurate but slower parser runs. This parser converts the PDF to markdown format, then strips formatting to get plain text. The result replaces or supplements the fast extractor output.

Run regex patterns to extract five fields. Each field has its own extractor function. Dates use multiple date format patterns. The organizer uses direct pattern matching and a list of known organizations. The certificate number uses a structured pattern.

Check if dates were found. If dates are missing or text is very short, run OCR as a last resort. OCR renders each PDF page as a high-resolution image. Two recognition engines process each image in parallel. Unique lines from both engines are merged. The combined text is then processed by the regex extractors again.

Map the extracted fields to form dropdown values. The mapper determines the activity level (tingkat) from organizer and role keywords. It determines the category (kelompok) and type (jenis) from the document structure. All fields are validated to ensure required values exist.

### 3.4 Output

PipelineResult with parser_engine, raw_text, and mapped_fields

Five ExtractedValue objects: nama_kegiatan_sertifikasi, waktu_mulai_pelaksanaan, waktu_selesai_pelaksanaan, penyelenggara_kegiatan, nomor_bukti_fisik_nomor_sertifikasi

Optional: tingkat from rule-based mapping in form_mapper.py

### 3.5 Configuration

| Parameter | Value | Description |
|---|---|---|
| min_text_length | config.py | Threshold to trigger slow parser fallback |
| enable_ocr_fallback | config.py | Enable or disable OCR step |
| zoom | 3.0 | PDF render resolution for OCR |
| tahun_akademik | 2024/2025 | Academic year passed to form mapper |

### 3.6 Strengths

Fast: ~0.1 seconds per certificate

No GPU or external model required

Deterministic: same input produces same output

### 3.7 Limitations

Regex patterns are fragile and hard to maintain

Cannot handle varied certificate layouts

OCR errors propagate through extraction

Tingkat mapping depends on keyword rules, not document understanding

### 3.8 Code Reference

The table below maps each process step to the corresponding code.

| Step | Function | File | What it does |
|---|---|---|---|
| 1 | extract_text_with_pymupdf() | pdf_fast_path.py:11 | Fast text from PDF pages |
| 1 | parse_with_docling() | docling_parser.py:16 | Slow fallback parser (markdown) |
| 2 | extract_certificate_fields() | field_extractor.py:85 | Regex extraction for 5 fields |
| 3 | extract_text_with_ocr() | ocr_fallback.py:8 | RapidOCR + Tesseract OCR |
| 4 | map_fields_to_form() | form_mapper.py:7 | Map fields to form dropdowns |

## 4. Method 2: NER v1

### 4.1 Overview

The NER method uses an IndoBERT model to extract named entities from certificate text. It then maps entity types to form fields. This method handles varied text formats better than regex.

### 4.2 Input

Pre-extracted text files from a previous regex baseline run

Text files have header lines (# Method:, # Time:) which are stripped

Ground truth CSV for evaluation

### 4.3 Process

Load the NER model into memory. The model is a pre-trained Indonesian language model from HuggingFace. It runs on GPU if available, otherwise on CPU. The model is cached globally so it loads only once.

Normalize the text for the NER model. This adds spaces around commas, between camelCase words, and between digits and letters. Normalization helps the model recognize entity boundaries correctly.

Split the text into 512-character chunks. The NER model has a maximum input length. Longer texts are split at sentence boundaries. Each chunk is processed independently by the model.

Run the NER pipeline on each chunk. The model identifies entity types: organizations (ORG), events (EVT), dates (DAT), numbers (NUM), and nominal values (NOR). Non-entity tokens are filtered out.

Merge consecutive entities of the same type. Entities that are close together (within 3 characters) are merged into a single entity. This handles cases where the model splits one entity into multiple tokens.

Map entities to form fields. Organizations become the organizer field. Events become the activity name. Dates become start and end dates. Numbers become the certificate number. Each entity is scored for relevance and the best one is selected.

### 4.4 Output

Dict of ExtractedValue objects for the five evaluation fields

Each value includes the source (which entity type produced it)

No tingkat extraction (NER does not determine activity level)

### 4.5 Configuration

| Parameter | Value | Description |
|---|---|---|
| Model | treamyracle/indobert-ner-gold | Pre-trained Indonesian NER model |
| Chunk size | 512 chars | Max text length per NER call |
| Merge gap | <= 3 chars | Merge consecutive entities within this gap |
| NOR min length | 8 chars | Minimum length for NOR entity fallback |

### 4.6 Strengths

Handles varied text formats better than regex

No rule maintenance needed for new certificate layouts

Fast: ~0.07 seconds per certificate

### 4.7 Limitations

Only extracts 4 of 5 fields (no tingkat)

NER model accuracy depends on training data quality

Struggles with OCR noise and unusual formatting

Requires GPU for acceptable speed

### 4.8 Code Reference

The table below maps each process step to the corresponding code.

| Step | Function | File | What it does |
|---|---|---|---|
| 1 | load_ner_model() | ner_extractor.py:25 | Load IndoBERT NER pipeline |
| 2 | normalize_for_ner() | ner_extractor.py:41 | Normalize text for NER input |
| 3 | extract_entities() | ner_extractor.py:52 | Chunk text, run NER, filter |
| 4 | _merge_consecutive() | ner_to_fields.py:107 | Merge nearby same-type entities |
| 5 | map_entities_to_fields() | ner_to_fields.py:13 | Map ORG/EVT/DAT/NUM to fields |
| 5 | score_entity_for_field() | post_processors.py:11 | Rank entities by relevance |

## 5. Method 3: Hybrid (NER + Regex)

### 5.1 Overview

The hybrid method combines NER and regex extraction. NER handles text fields. Regex handles structured fields. This combines the strengths of both approaches.

### 5.2 Input

Same pre-extracted text files as NER v1

Same ground truth CSV

### 5.3 Process

Run regex extraction. This extracts all five fields using pattern matching. Regex works well for structured data like dates and certificate numbers.

Run NER extraction. This extracts entity-based fields. NER works well for free-text fields like activity names and organizer names.

Combine results using priority rules. Text fields (activity name, organizer) prefer NER results. Structured fields (dates, certificate number) prefer regex results. If the preferred source has no value, the other source is used as fallback.

### 5.4 Output

Dict of ExtractedValue objects for the five evaluation fields

Each field has a source from either NER or regex

### 5.5 Configuration

| Aspect | NER Priority | Regex Priority |
|---|---|---|
| Text fields | nama_kegiatan_sertifikasi, penyelenggara_kegiatan | Fallback only |
| Structured fields | Fallback only | waktu_mulai, waktu_selesai, nomor_bukti_fisik |

### 5.6 Strengths

Best of both approaches

NER handles text fields where regex is weak

Regex handles structured fields where NER is weak

### 5.7 Limitations

Still cannot extract tingkat

Depends on both NER model and regex patterns

No error handling between methods

### 5.8 Code Reference

The table below maps each process step to the corresponding code.

| Step | Function | File | What it does |
|---|---|---|---|
| 1 | extract_certificate_fields() | field_extractor.py:85 | Regex extraction for all fields |
| 2 | extract_entities() + map_entities_to_fields() | ner_extractor.py:52, ner_to_fields.py:13 | NER extraction |
| 3 | combine_hybrid() | benchmark_hybrid.py:63 | Merge with priority rules |

## 6. Method 4: Hybrid + Post-Processing

### 6.1 Overview

The hybrid+PP method adds a post-processing step to the hybrid method. This step filters signer-related entities from the NER results. Signers are common false positives in organizer extraction.

### 6.2 Input

Same pre-extracted text files as NER v1

Raw text passed to the signer filter for context

### 6.3 Process

Run NER extraction. The model identifies all entities in the text, including signer names and organizations.

Filter signer roles. The filter looks for signer patterns. It checks 40 characters before each organization entity for dedication prefixes. It checks 200 characters after for NIP or NIM numbers. It checks if the entity appears in the last 30% of the text.

Filter person names. The filter checks 80 characters before each entity for phrases like 'diberikan kepada' (given to) or 'menghargaan kepada' (awarding to). Entities matching these patterns are removed.

Safety check. If filtering removed all organization entities, the filter reverts to the original list. This prevents data loss from over-aggressive filtering.

Run field mapping and hybrid combination. The cleaned entities are mapped to fields. The results are combined with regex using the same priority rules as the hybrid method.

### 6.4 Output

Dict of ExtractedValue objects for the five evaluation fields

Cleaner organizer values (fewer signer false positives)

### 6.5 Configuration

| Check | Look-behind | Look-ahead | Trigger |
|---|---|---|---|
| Signer role | 40 chars | 200 chars | A.N./ATAS NAMA prefix or NIP/NIM suffix |
| Person name | 80 chars | N/A | diberikan kepada / menghargaan kepada |
| Position | N/A | N/A | Entity past 70% of text length |
| Safety | N/A | N/A | Revert if all ORGs removed |

### 6.6 Strengths

Reduces false positive organizer extractions

Handles common certificate layout patterns

Safety revert prevents data loss

### 6.7 Limitations

Heuristic-based: may incorrectly filter valid organizers

Position thresholds are tuned for this dataset

Does not handle all signer patterns

### 6.8 Code Reference

The table below maps each process step to the corresponding code.

| Step | Function | File | What it does |
|---|---|---|---|
| 2 | filter_signer_roles() | post_processors.py:85 | Remove signer entities from NER output |
| 2 | is_signer_role() | post_processors.py:74 | Check dedication prefix + NIP/NIM |
| 3 | is_likely_person_name() | post_processors.py:46 | Check diberikan kepada phrase |
| 5 | map_entities_to_fields() | ner_to_fields.py:13 | Map filtered entities to fields |
| 5 | combine_hybrid() | benchmark_hybrid.py:63 | Merge with regex results |

## 7. Method 5: LLM A1 (Per-Field)

### 7.1 Overview

The LLM A1 method adds Ollama inference to the hybrid+PP baseline. It calls the language model for tingkat (always) and for other fields when confidence is low. This is the first LLM-based method.

### 7.2 Input

Same pre-extracted text files

Hybrid+PP results as context (known fields)

Full raw text for each certificate

### 7.3 Process

Build the hybrid+PP baseline. This is the same as Method 4. The result is a dict of field values with confidence scores.

Build a context dictionary. This contains the activity name, organizer, and role from the hybrid+PP results. The context helps the language model make better decisions.

Decide which fields need the language model. The tingkat field always triggers a call. Other fields trigger only if the hybrid+PP value is missing or has low confidence (below 0.7).

Build the prompt for tingkat. The prompt contains extraction rules, a list of approved options, and heuristic guidance. It also includes the full certificate text and the known fields from step 2.

Build the prompt for other fields. The prompt asks the model to extract a specific field. It includes the full certificate text and the known fields. The model must return only the field value or TIDAK_DITEMUKAN.

Call the Ollama API. The model runs locally with temperature 0 for deterministic output. Each call uses a 4096-token context window and produces up to 30 tokens. Up to 2 retries are attempted on failure.

Validate the response. For tingkat, the response is checked against the approved options. For other fields, the response is checked for length and rejection patterns.

Merge valid results into the hybrid+PP dict. Valid language model values replace the original field values. Each merged value gets a confidence of 0.85 and source 'llm_ollama'.

### 7.4 Prompt

The prompt tells the language model exactly what to extract. Each prompt contains instructions, rules, heuristic guidance, approved options, the certificate text (or context), and the answer format.

#### Tingkat Prompt

Tentukan TINGKAT KEGIATAN dari sertifikat berikut.

ATURAN WAJIB:

- Jawaban HARUS persis salah satu dari opsi di bawah

- JANGAN jawab selain opsi ini

PETUNJUK TINGKAT:

- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat FAKULTAS

(BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas

- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa

(HIMATESDA, HIMANO), maka == Departemen/Program Studi

- Jika diselenggarakan oleh BEM Universitas, Rektorat,

Direktorat Kemahasiswaan, maka == Universitas

- Jika kegiatan berskala nasional (lomba nasional, webinar nasional),

maka == Nasional

- Jika kegiatan berskala internasional (konferensi internasional),

maka == Internasional

- 'UNIVERSITAS AIRLANGGA' adalah institusi induk, BUKAN penentu tingkat

Opsi yang diizinkan:

- Internasional

- Nasional

- Universitas

- Fakultas

- Departemen/Program Studi

- Lainnya

Teks sertifikat:

<full raw text of certificate>

Field yang sudah diketahui:

- Nama Kegiatan: <extracted activity name>

- Penyelenggara: <extracted organizer>

- Peran: <extracted role>

Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):

#### Free Text Prompt (for other fields)

Ekstrak <field_label> dari sertifikat berikut.

ATURAN:

- Jawaban HANYA nilai field, tanpa penjelasan

- Maksimal 100 karakter

- Jika tidak ditemukan, jawab: TIDAK_DITEMUKAN

Teks sertifikat:

<full raw text of certificate>

Field yang sudah diketahui:

- Nama Kegiatan: <extracted activity name>

- Penyelenggara: <extracted organizer>

- Peran: <extracted role>

Jawaban:

### 7.5 Output

Six ExtractedValue objects (5 from hybrid+PP + tingkat from LLM)

Token usage log (calls.json) with prompt tokens, completion tokens, and latency

Two summaries: hybrid_pp (baseline) and hybrid_llm (with LLM)

### 7.6 Configuration

| Parameter | Value | Description |
|---|---|---|
| Model | llama3.1:8b | Ollama local model |
| max_tokens | 30 | Max completion tokens per call |
| num_ctx | 4096 | Context window size |
| temperature | 0 | Deterministic output |
| CONFIDENCE_THRESHOLD | 0.7 | Trigger LLM if below this |
| LLM confidence | 0.85 | Hardcoded when merging |

### 7.7 Strengths

Adds tingkat extraction (hybrid alone gives 0%)

Conditional LLM calls: only when confidence is low

Full raw text gives LLM maximum context

### 7.8 Limitations

1-4 LLM calls per certificate (slow, ~2 seconds each)

High token usage: ~834 tokens per certificate

Confidence threshold (0.7) is a design choice, not optimal

LLM may hallucinate fields where regex and NER both failed

### 7.9 Code Reference

The table below maps each process step to the corresponding code.

| Step | Function | File | What it does |
|---|---|---|---|
| 2 | needs_llm() | benchmark_llm.py:103 | Check if field needs LLM call |
| 3 | build_prompt_tingkat() | llm_extractor.py:80 | Build tingkat prompt (full text) |
| 3 | build_prompt_free_text() | llm_extractor.py:121 | Build free-text field prompt |
| 4 | call_ollama() | llm_extractor.py:51 | Call Ollama API |
| 5 | validate_tingkat() | llm_extractor.py:149 | Validate tingkat response |
| 5 | validate_free_text() | llm_extractor.py:175 | Validate free-text response |

## 8. Method 6: LLM v3 (Tingkat Only)

### 8.1 Overview

The LLM v3 method calls the language model only for tingkat. It does not re-extract other fields. It has two variants: context-only (A) and context + minimized text (B). This method minimizes token usage.

### 8.2 Input

Same pre-extracted text files

Hybrid+PP results as context

Full raw text (Variant B only, processed by minimize_text())

### 8.3 Process

Build the hybrid+PP baseline. Same as Method 4.

Build the context dictionary. Same as Method 5.

Variant A: Build context-only prompt. The prompt contains extraction rules, approved options, and heuristic guidance. It also includes the known fields. No raw text is included.

Variant B: Select relevant lines. The minimize_text function scores each line of the certificate text. It keeps only lines relevant to tingkat determination. Lines with organizer keywords, scale keywords, or role keywords are kept. Noise and garbled text are removed. The result is capped at 300 characters.

Variant B: Build prompt with minimized text. The prompt is the same as Variant A, but includes the minimized text section. This gives the model some raw text context while keeping token usage low.

Call the Ollama API for each variant. Same settings as Method 5.

Validate and merge. Same as Method 5. Each variant produces its own tingkat result.

### 8.4 Prompt

The prompt tells the language model exactly what to extract. Each prompt contains instructions, rules, heuristic guidance, approved options, the certificate text (or context), and the answer format.

#### Variant A: Context-Only Prompt

Tentukan tingkat kegiatan dari informasi berikut.

ATURAN WAJIB:

- Jawaban HARUS persis salah satu dari opsi di bawah

- JANGAN jawab selain opsi ini

- Jika tidak yakin, pilih yang paling mendekati

PETUNJUK TINGKAT:

- Jika sertifikat menyebut DEPARTMENT/DEPT/STUDY PROGRAM

(bahasa Inggris), maka == Departemen/Program Studi

- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat

FAKULTAS (BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas

- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa

(HIMATESDA, HIMANO), maka == Departemen/Program Studi

- Jika diselenggarakan oleh BEM Universitas, Rektorat,

Direktorat Kemahasiswaan, maka == Universitas

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

- Nama Kegiatan: <extracted activity name>

- Penyelenggara: <extracted organizer>

- Peran: <extracted role>

Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):

#### Variant B: Minimized-Text Prompt

Tentukan tingkat kegiatan dari sertifikat berikut.

ATURAN WAJIB:

- Jawaban HARUS persis salah satu dari opsi di bawah

- JANGAN jawab selain opsi ini

- Jika tidak yakin, pilih yang paling mendekati

PETUNJUK TINGKAT:

- Jika sertifikat menyebut DEPARTMENT/DEPT/STUDY PROGRAM

(bahasa Inggris), maka == Departemen/Program Studi

- Jika diselenggarakan oleh BEM/Badan Eksekutif Mahasiswa tingkat

FAKULTAS (BEM FEB, BEM FKM, BEM FTMM), maka == Fakultas

- Jika diselenggarakan oleh HIMA/Himpunan Mahasiswa

(HIMATESDA, HIMANO), maka == Departemen/Program Studi

- Jika diselenggarakan oleh BEM Universitas, Rektorat,

Direktorat Kemahasiswaan, maka == Universitas

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

Teks sertifikat (bagian yang relevan):

<minimized text, ~300 chars, only tingkat-relevant lines>

Field yang sudah diketahui (dari pipeline):

- Nama Kegiatan: <extracted activity name>

- Penyelenggara: <extracted organizer>

- Peran: <extracted role>

Jawaban (hanya satu opsi dari daftar, tanpa penjelasan):

### 8.5 Output

Six ExtractedValue objects (5 from hybrid+PP + tingkat from LLM)

Per-variant call logs (calls_a_context.json, calls_b_minimized.json)

Minimize stats (minimize_stats.json) with compression ratios

Config dump (config.json) with model and weights

### 8.6 Configuration

| Aspect | Variant A | Variant B |
|---|---|---|
| Raw text in prompt | No | Yes (minimized to ~300 chars) |
| Avg tokens/cert | 410 | 479 |
| Tingkat accuracy | 24.3% | 39.2% |
| Acc/token | 0.059 | 0.082 (best in family) |
| Compression | N/A | 70% (42K -> 12K chars) |

### 8.7 Strengths

Lowest token usage: 479 tokens per certificate (Variant B)

Best accuracy-per-token: 0.082 (highest in the family)

minimize_text() removes OCR noise before the LLM sees it

Single LLM call per certificate (deterministic cost)

### 8.8 Limitations

Only extracts tingkat (other fields stay from hybrid+PP)

Variant A (context-only) has low accuracy: 24.3%

minimize_text() weights are tuned for this dataset

English dept certs still problematic (LLM picks Fakultas over DEPT)

25 Nasional certs have no text signal (unsolvable by any text method)

### 8.9 Code Reference

The table below maps each process step to the corresponding code.

| Step | Function | File | What it does |
|---|---|---|---|
| 4 | minimize_text() | llm_extractor_v3.py:136 | Select relevant lines for tingkat |
| 4 | score_line() | llm_extractor_v3.py:106 | Score a line for tingkat relevance |
| 3 | build_prompt_tingkat_context() | llm_extractor_v3.py:214 | Context-only prompt (Variant A) |
| 5 | build_prompt_tingkat_minimized() | llm_extractor_v3.py:239 | Minimized-text prompt (Variant B) |
| 6 | call_ollama() | llm_extractor.py:51 | Call Ollama API |
| 7 | validate_tingkat() | llm_extractor.py:149 | Validate tingkat response |

## 9. Method 7: Cost-Aware Hybrid Extraction (Handoff v7)

### Overview

Handoff v7 moves from full-text LLM extraction to a cost-aware hybrid that extracts only the tingkat field with an LLM while every other field stays on the deterministic hybrid (NER + regex + post-processing). The goal is the best accuracy/cost Pareto point, not minimum tokens at any cost.

### Input

Same 74 certificates. Ground truth: Ground_Truth_Sertifikat.csv (raw).

### Process

- Run hybrid + post-processing once per certificate (regex + NER + phrase-v2 organizer).
- Run the rule-based tingkat router: high-precision rules decide tingkat at 0 tokens.
- For certificates the router does not decide, call the local LLM with a compact tingkat prompt.
- Validate the LLM answer against the 6 form options; keep the value empty when invalid.

### Configuration

| Key | Value |
|---|---|
| Prompt | v3 minimized / v4 adaptive (variants a-e) |
| Router | rule-based, 35/74 decisions at 100% precision |
| Model | llama3.1:8b (Ollama) |
| Token budget | minimize_text(), ~202 eff tokens/cert |

### Results (v7 P4 e_hybrid)

| Metric | Value |
|---|---|
| Tingkat exact | 77.0% (57/74) |
| MACRO exact | 54.2% |
| Eff. tokens/cert | 202.2 |
| LLM calls | 39 of 74 (router: 35, 100% precision) |
| Run | tests/benchmark_runs/run_llm_v4_20260803_113310/ |

### Strengths

- Router removes ~47% of LLM calls at 0 tokens and 100% precision.
- Best accuracy-per-token in the v4+v6+v7 family (0.082 acc/token).

### Limitations

- Word-boundary router misses OCR-merged tokens (BEMFKM, BEMFEBUNAIR, HIMATESDA).
- Ground truth had un-audited tingkat labels.
- LLM biased English certificate text toward Internasional.

### Code Reference

- tests/benchmark_llm_v4.py, tests/llm_extractor_v3.py, tests/llm_extractor_v4.py
- tests/llm_router_v4.py, tests/organizer_extractor_v2.py, tests/mismatch_taxonomy.py

## 10. Method 8: v8 Router Fix + LLM Bias + Layout (Handoff v8)

### Overview

Handoff v8 repairs the v7 router, audits ground truth, and tests two accuracy levers: a bias-corrected LLM prompt and layout-aware input. Winner: contains-match router + f_bias prompt at 82.4% tingkat exact.

### Input

Same 74 certificates. Versioned ground truth: Ground_Truth_Sertifikat_v8.csv (3 audited tingkat label corrections).

### Process

- GT audit: 1966887->Nasional, 1981676->Nasional, 2954283->Internasional; 2030372 stays Nasional.
- Router contains-match: BEM/HIMA detected in uppercase alnum runs (BEMFKM, SERT2128BEM2026) with a guard.
- New rule: explicit TINGKAT/LOMBA NASIONAL text -> Nasional.
- f_bias prompt: English text is not automatically Internasional; Indonesian-institution context wins.
- Layout experiment (markdown / annotated from PyMuPDF dict) measured and rejected.

### Configuration

| Key | Value |
|---|---|
| Prompt | f_bias (e_hybrid + bias rules) |
| Router | contains-match, 39/74 decisions at 100% precision |
| GT | fixed_v8 (Ground_Truth_Sertifikat_v8.csv) |
| Model | llama3.1:8b (Ollama) |

### Results

| Variant | Tingkat exact | MACRO exact | Eff. tokens/cert |
|---|---|---|---|
| b_minimized | 78.4% | 54.4% | 221 |
| e_hybrid | 79.7% | 54.7% | 182 |
| f_bias (winner) | 82.4% | 55.2% | 214 |
| g_evidence | 75.7% | 53.9% | 194 |
| layout_md (f_bias) | 77.0% | 50.8% | 235 |
| layout_ann (f_bias) | 78.4% | 51.3% | - |

### Strengths

- Contains-match router routes 39/74 at 100% precision (-53% LLM calls).
- f_bias fixes English-name scale bias (data slayer, 2955331, IRIS) without breaking BEM-fakultas.

### Limitations

- g_evidence (FaR-style) regresses accuracy and adds completion tokens -> rejected.
- Layout does not help: only 25/74 PDFs have embedded text, and markers disturb deterministic extractors.
- f_bias is 214 eff tokens/cert, slightly over the 200 gate.

### Code Reference

- tests/llm_router_v4.py, tests/llm_extractor_v4.py, tests/benchmark_llm_v4.py
- tests/layout_repr.py, tests/verify_ground_truth.py
- Production: backend/app/services/{tingkat_router,llm_tingkat,organizer_v2}.py

## 11. Comparison Table

The table below compares all six methods across key dimensions.

| Method | Input | Extraction | LLM calls | Extra fields | Confidence | Speed |
|---|---|---|---|---|---|---|
| Regex | PDF | Regex patterns | 0 | tingkat (rule) | Fixed | ~0.1s |
| NER v1 | Text | IndoBERT NER | 0 | none | NER score | ~0.07s |
| Hybrid | Text | NER + regex | 0 | none | Best of both | ~0.15s |
| Hybrid+PP | Text | NER + regex + PP | 0 | none | Best of both | ~0.6s |
| LLM A1 | Text | Hybrid+PP + LLM | 1-4 | tingkat (LLM) | LLM=0.85 | ~2s |
| LLM v3 | Text | Hybrid+PP + LLM | 1 | tingkat (LLM) | LLM=0.85 | ~1s |

## 12. Appendix: Full Function Index

The table below lists all functions referenced in this document. Functions are listed in the order they appear in the processing pipeline.

| Function | File | Purpose |
|---|---|---|
| extract_text_with_pymupdf() | pdf_fast_path.py:11 | Extract text from PDF pages |
| parse_with_docling() | docling_parser.py:16 | Slow fallback parser (markdown) |
| extract_text_with_ocr() | ocr_fallback.py:8 | RapidOCR + Tesseract OCR |
| extract_certificate_fields() | field_extractor.py:85 | Regex extraction for 5 fields |
| map_fields_to_form() | form_mapper.py:7 | Map fields to form dropdowns |
| run_extraction_pipeline() | extraction_pipeline.py:27 | Full pipeline: PDF to fields |
| load_ner_model() | ner_extractor.py:25 | Load IndoBERT NER pipeline |
| normalize_for_ner() | ner_extractor.py:41 | Normalize text for NER input |
| extract_entities() | ner_extractor.py:52 | Chunk text, run NER, filter |
| _merge_consecutive() | ner_to_fields.py:107 | Merge nearby same-type entities |
| map_entities_to_fields() | ner_to_fields.py:13 | Map ORG/EVT/DAT/NUM to fields |
| score_entity_for_field() | post_processors.py:11 | Rank entities by relevance |
| filter_signer_roles() | post_processors.py:85 | Remove signer entities |
| is_signer_role() | post_processors.py:74 | Check dedication prefix + NIP |
| is_likely_person_name() | post_processors.py:46 | Check diberikan kepada phrase |
| combine_hybrid() | benchmark_hybrid.py:63 | Merge NER and regex results |
| needs_llm() | benchmark_llm.py:103 | Check if field needs LLM call |
| call_ollama() | llm_extractor.py:51 | Call Ollama API |
| build_prompt_tingkat() | llm_extractor.py:80 | Build tingkat prompt (full text) |
| build_prompt_free_text() | llm_extractor.py:121 | Build free-text field prompt |
| validate_tingkat() | llm_extractor.py:149 | Validate tingkat response |
| validate_free_text() | llm_extractor.py:175 | Validate free-text response |
| minimize_text() | llm_extractor_v3.py:136 | Select relevant lines for tingkat |
| score_line() | llm_extractor_v3.py:106 | Score a line for tingkat relevance |
| build_prompt_tingkat_context() | llm_extractor_v3.py:214 | Context-only prompt (A) |
| build_prompt_tingkat_minimized() | llm_extractor_v3.py:239 | Minimized-text prompt (B) |
| evaluate_row() | evaluation_framework.py:47 | Evaluate one certificate vs GT |
| aggregate_results() | evaluation_framework.py:66 | Aggregate per-field metrics |
| save_mismatch_report() | evaluation_framework.py:142 | Generate mismatch CSV/XLSX |

### Comparison Across Experiments

| Experiment | Tingkat | MACRO | Eff tok/cert | LLM calls | Router | GT | Date |
|---|---|---|---|---|---|---|---|
| LLM A1 (per-field) | 47.3% | 49.0% | 834 | 125 | - | raw | Jul 30 |
| LLM A2 v2 (full-text) | 36.5% | 58.3% | 834 | 74 | - | raw | Jul 30 |
| LLM v3 Variant B | 39.2% | 46.4% | 479 | 74 | - | raw | Jul 31 |
| v7 P3 router rule-based | 71.6% | 53.1% | 191 | 42 | - | raw | Aug 3 |
| v7 P4 e_hybrid + router | 77.0% | 54.2% | 202 | 39 | 35/74 @100% | raw | Aug 3 |
| v8 f_bias + router | 82.4% | 55.2% | 214 | 35 | 39/74 @100% | fixed_v8 | Aug 4 |
| OCR Trial A — PaddleOCR 2.9 (CPU) | n/a | 39.8% | 0 | 0 | - | fixed_v8 | Aug 4 |
| OCR Trial A — EasyOCR (CPU, max-side 960) | n/a | 34.3% | 0 | 0 | - | fixed_v8 | Aug 4 |
| OCR Trial A — EasyOCR (GPU, full-res) | n/a | 39.3% | 0 | 0 | - | fixed_v8 | Aug 4 |
| v9 organizer_v2 + router fix | 83.8% | 58.9% | 176 | 29 | 45/74 @100% | v8 | Aug 5 |
| v9 winner re-baseline (GT v9 + matcher v2) | 83.8% | 60.2% | 176 | 29 | 45/74 @100% | v9 | Aug 5 |
| NC-001 nomor crop preprocessing (re-render region zoom 6x) | n/a | 46.3% | 0 | 0 | - | v9 | Aug 6 |
| OCR-006 DocTR probe (mobilenet CPU, 10 scan) | n/a | 40.0% | 0 | 0 | - | v9 | Aug 6 |
| HYB-001 hybrid OCR per-field (DocTR dates+organizer / baseline nomor) | n/a | 46.8% | 0 | 0 | - | v9 | Aug 6 |
| NC-002 region-OCR murah (rapid / tess psm tunggal) utk 2-pass nomor | n/a | 47.3% | 0 | 0 | - | v9 | Aug 6 |
| F1 organizer v3 (R0-R5, 0 LLM) | 81.1% | 59.6% | 0 | 0 | - | v9 | Aug 10 |

| Phase | Method | Tingkat | MACRO |
|---|---|---|---|
| v4 | LLM A1 (per-field) | 47.3% | 49.0% |
| v4 | LLM A2 v2 (full-text) | 36.5% | 58.3% |
| v6 | LLM v3 Variant B | 39.2% | 46.4% |
| v7 | v7 P3 router rule-based | 71.6% | 53.1% |
| v7 | v7 P4 e_hybrid + router | 77.0% | 54.2% |
| v8 | v8 f_bias + router | 82.4% | 55.2% |
| ocr | OCR Trial A — PaddleOCR 2.9 (CPU) | n/a | 39.8% |
| ocr | OCR Trial A — EasyOCR (CPU, max-side 960) | n/a | 34.3% |
| ocr | OCR Trial A — EasyOCR (GPU, full-res) | n/a | 39.3% |
| v9 | v9 organizer_v2 + router fix ** | 83.8% | 58.9% |
| v12 | v9 winner re-baseline (GT v9 + matcher v2) | 83.8% | 60.2% |
| ocr | NC-001 nomor crop preprocessing (re-render region zoom 6x) | n/a | 46.3% |
| ocr | OCR-006 DocTR probe (mobilenet CPU, 10 scan) | n/a | 40.0% |
| ocr | HYB-001 hybrid OCR per-field (DocTR dates+organizer / baseline nomor) | n/a | 46.8% |
| ocr | NC-002 region-OCR murah (rapid / tess psm tunggal) utk 2-pass nomor | n/a | 47.3% |
| v10 | F1 organizer v3 (R0-R5, 0 LLM) | 81.1% | 59.6% |
