# Plan: Tesseract-Primary OCR Benchmark Pipeline with v4.x Post-Processing Suite

## Context
The user requested a dedicated benchmark pipeline that prioritizes Tesseract as the primary OCR engine, combined with the post-processing improvements developed in the v4.x / Composite B8 pipeline (semantic grammar anchors, digit-preserving Roman numeral normalizer, organizer v7 cleaner, date v2 parser, and router v7 disambiguation). The pipeline must regenerate raw OCR texts using Tesseract across the 74 certificate dataset, execute modern v4.x extraction, evaluate against `Ground_Truth_Sertifikat_v9.csv` using frozen matcher v2, and record all benchmark artifacts under `tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/`.

## Approach

### 1. Build Dedicated Standalone Benchmark Script (`tests/benchmark_tesseract_v4.py`)
Create a self-contained runner script supporting `build` (OCR generation) and `eval` (field extraction & scoring) commands:
- **Corpus Target Directory:** `tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/extracted_texts/`
- **Output Artifacts:**
  - `ocr_meta.json` (per-cert latency, character counts, errors)
  - `eval.json` (aggregate & per-field accuracy, scan-49 vs embedded-25 breakdowns)
  - `docs/report/tesseract_primary_v4_report.md` (comprehensive comparative analysis)

### 2. Implement Tesseract OCR Generation (`cmd_build`)
- Load manifest from `tests/layout_manifest.json` (74 certificates: 49 scans, 25 digital PDFs).
- For each certificate:
  - If embedded digital text exists (`embedded_text` from `tests/ocr_engine.py`), capture it.
  - Render PDF pages to PNG at 3.0× zoom via `render_pdf_pages_to_png_bytes` (from `app.services.pdf_fast_path`).
  - Run Tesseract OCR using `ocr_tess` from `tests/ocr_engine.py` (multi-PSM: `""`, `--psm 6`, `--psm 11` with `lang="ind+eng"`).
  - Combine embedded text + Tesseract text: `f"{emb}\n{tess_text}".strip()` to reflect production behavior on hybrid documents, or raw Tesseract for pure scans.
  - Save extracted text to `{target_dir}/{stem}.txt` with header `# Engine: tesseract_primary\n# Seconds: {elapsed}\n\n{text}`.
  - Collect garbage (`gc.collect()`) after each certificate to prevent memory bloat on WSL.

### 3. Implement v4.x Composite Extraction Over Tesseract Corpus (`cmd_eval`)
Process each generated `.txt` file using the latest v4.x post-processing modules instead of the legacy v9 extractor:
- **Activity Name:** `extract_activity_v9(raw_text)` from `tests/activity_extractor_v9.py` (structural semantic grammar anchors, anti-bleed bounds).
- **Organizer:** `extract_organizer_v2(raw_text)` from `app.services.organizer_v2` followed by `normalize_organizer_v7(v2_val, raw_text)` from `app.services.combined_extractor`.
- **Certificate Number:** `normalize_nomor_v6(raw_text)` from `tests/nomor_normalizer_v6.py` (length-preserving DPKKA cleaner, gated Roman numeral month repairs).
- **Dates:** `extract_dates_v2(raw_text)` from `app.services.combined_extractor` (ordinal stripping, multi-day span repairs).
- **Tingkat:** `route_with_disambiguation_v7(raw_text, org, act)` from `tests/router_disambig_v7.py` (8 hardened contextual disambiguation rules).
- **Form Mapping:** `map_fields_to_form(extracted, raw_text, bukti_fisik="Sertifikat")` from `app.services.form_mapper`.

### 4. Evaluate Against Ground Truth v9 & Matcher v2
- Load `Ground_Truth_Sertifikat_v9.csv`.
- Evaluate each certificate row via `evaluate_row(mapped, gt_row)` from `tests/evaluation_framework.py`, utilizing `tests/matchers.py` (matcher v2).
- Compute:
  - All-74 MACRO exact & fuzzy accuracy.
  - Scan-49 subset MACRO exact & fuzzy accuracy.
  - Embedded-25 subset MACRO exact & fuzzy accuracy.
  - Average WER & CER per field.
- Save structured results to `tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/eval.json`.

### 5. Generate Comparative Documentation (`docs/report/tesseract_primary_v4_report.md`)
Compile benchmark metrics into a structured markdown report containing:
- 4-way comparison table:
  1. **Tesseract-Primary + v4.x Composite** (New)
  2. **RapidOCR-Only + v4.x Composite** (HYB-003 scan-49)
  3. **RapidOCR + Tesseract Baseline** (`baseline_rapid_tess`)
  4. **Combined v4.2 / Composite B8 Baseline** (76.13% all-cells / 87.42% framework)
- Per-field accuracy breakdown (kegiatan, tanggal mulai/selesai, penyelenggara, nomor, tingkat).
- Detailed error analysis comparing Tesseract text layout vs RapidOCR text layout.

## Critical files & anchors

1. `tests/ocr_engine.py`: lines 195–213 (`ocr_tess` multi-PSM implementation) & lines 362–392 (`ocr_pdf`, `ocr_path`).
2. `tests/composite_v4_candidate.py`: lines 35–84 (`apply_composite_v4_candidate` orchestrator).
3. `tests/nomor_normalizer_v6.py`: lines 84–165 (`normalize_nomor_v6` Roman & digit length repairs).
4. `tests/activity_extractor_v9.py`: lines 110–195 (`extract_activity_v9` structural anchors).
5. `Ground_Truth_Sertifikat_v9.csv`: frozen baseline evaluation standard.

## Verification

1. **Corpus Generation:**
   ```bash
   uv run python -m tests.benchmark_tesseract_v4 build
   ```
   *Expected:* Successfully processes 74 certificates, outputs 74 `.txt` files in `tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/extracted_texts/`, generates `ocr_meta.json` with 0 unhandled exceptions.

2. **Extraction & Evaluation:**
   ```bash
   uv run python -m tests.benchmark_tesseract_v4 eval
   ```
   *Expected:* Matches 74/74 certificates against GT v9, outputs summary table to stdout, and writes `eval.json`.

3. **Regression Check on Existing Tests:**
   ```bash
   uv run pytest tests/test_combined_v4_2.py tests/test_nomor_v6.py tests/test_structural_act_robustness.py tests/test_router_disambig_hardening.py -q
   ```
   *Expected:* All existing unit tests pass without regression.

## Assumptions & contingencies

- **Assumption:** `tesseract` binary version 5.5.0 with `eng` and `ind` language packs is installed and functional on the host. (Verified: `/usr/bin/tesseract` version 5.5.0 exists with `eng`, `ind`, `osd`).
- **Assumption:** Digital embedded text layers are preserved for the 25 embedded PDF certificates, while Tesseract is the sole OCR engine for the 49 scanned certificates.
  - *Contingency:* If pure OCR on all 74 certificates is desired regardless of digital text layers, `--force-ocr-all` CLI flag is provided.
