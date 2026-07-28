# Handoff — Eksperimen Pipeline Certificate Autofill

Berdasarkan `docs/rangkuman_findings_v3.docx` (Method Catalog Edition).

## Current Status

| Prioritas | Eksperimen | Status | Commit |
|-----------|-----------|--------|--------|
| P0 | 6. Evaluation Framework | ✅ DONE | `a3d81b5` |
| P1 | 1. OCR Confidence Capture | ⏳ Next | — |
| P1 | 2. Confidence Threshold | ⏳ Next | — |
| P2 | 3. LLM Prototyping | ⏳ | — |
| P2 | 5. Line-Level OCR | ⏳ | — |
| P3 | 7. Conformal Prediction | ⏳ | — |
| P3 | 4. LayoutLMv3 Fine-Tune | ⏳ | — |

---

## Sebelum Memulai Eksperimen: Run Baseline Benchmark

**Jalankan dulu benchmark untuk dapat baseline numbers.** Tanpa ini, eksperimen tidak terukur.

### Setup

1. Install dependencies di **host** (Docker tidak diubah — hanya `backend/app` yang di-copy ke container):
   ```bash
   pip install pymupdf docling rapidocr-onnxruntime pytesseract Pillow
   apt install tesseract-ocr tesseract-ocr-ind
   ```
   Jika `docling` terlalu berat, bisa di-skip dengan `ENABLE_DOCLING=false`.

2. Jalankan dari repo root:
   ```bash
   cd /repo
   python tests/benchmark_pipeline.py
   ```

### Output
- Tabel per-field accuracy (exact + fuzzy)
- File `tests/benchmark_results.json` — disimpan untuk perbandingan nanti.

WARNING: Path benchmark sudah di-set untuk `python tests/benchmark_pipeline.py` dari repo root. Jangan di-run dari dalam `tests/`, jangan di-run dari Docker.

---

## Cara Validasi Eksperimen

```
1. Run benchmark → catat baseline numbers (exact% + fuzzy%)
2. Buat file experiment (*_experiment.py)
3. Run benchmark lagi → catat new numbers
4. Bandingkan: apakah fuzzy accuracy naik? apakah exact accuracy naik?
5. Jika naik → merge experiment ke production code
6. Jika tidak → git checkout, coba pendekatan lain
```

Lihat `docs/evaluation_framework_justification.md` untuk justifikasi tiered matching.

---

## Aturan Main

1. **Commit/backup dulu** sebelum otak-atik. Setiap eksperimen punya daftar file yang harus di-commit duluan.
2. **Kerjakan mode experiment** — buat file baru (misal `*_experiment.py`), jangan timpa yang asli. Kalau berhasil, baru merge.
3. **Gagal?** `git checkout <file>` untuk balik ke backup. Aman.
4. **Berhasil?** Baru deploy dan tunjukkin ke mentor.

---

## ✅ P0: Evaluation Framework (DONE)

**File yang dibuat:**
- `tests/date_normalizer.py` — normalisasi tanggal Indonesia/Inggris ke `DD/MM/YYYY`
- `tests/matchers.py` — 3-tier matching: exact, contains, token overlap ≥50%
- `tests/evaluation_framework.py` — load CSV, compare per field, aggregate, print report
- `tests/benchmark_pipeline.py` — CLI runner: run pipeline on all 74 PDFs, save results
- `tests/test_evaluation_framework.py` — pytest untuk matchers + date normalizer
- `docs/evaluation_framework_justification.md` — academic justification

**Data:**
- `Ground_Truth_Sertifikat.csv` — 74 sertifikat labeled (7 form fields)
- `Sertifikat_Ground_Truth/` — 74 file PDF/PNG (binary, di-`.gitignore`, tidak di-commit)

**Commit:** `a3d81b5`

**Testing matching logic (tanpa backend):**
```bash
cd backend && python -m pytest tests/test_evaluation_framework.py -v
```

---

## P1: Eksperimen 1 — Capture OCR Confidence per-Karakter

**Source V3:** Section 3.3 (Preprocessing & OCR)

**Apa yang dicoba:**
RapidOCR saat ini mengembalikan per-char confidence, tapi kode ini dibuang. Capture dan propagate confidence ini sebagai input feature ke downstream.

**Validasi:** Bandingkan `avg_confidence` di benchmark report sebelum vs sesudah.

**File yang kena:**
- `backend/app/services/ocr_fallback.py`
- `backend/app/services/extraction_pipeline.py`
- `backend/app/services/field_extractor.py`

**Backup:**
```bash
git add backend/app/services/ocr_fallback.py
git commit -m "backup: ocr_fallback before confidence propagation"
```

**Experiment file:**
```bash
cp backend/app/services/ocr_fallback.py backend/app/services/ocr_fallback_experiment.py
```

**Success criteria:**
Output `ExtractedValue` punya `confidence` yang beneran mencerminkan OCR quality, bukan hardcoded.

**Revert:**
```bash
git checkout backend/app/services/ocr_fallback.py
```

---

## P1: Eksperimen 2 — Ganti Hardcoded Confidence dengan Threshold dari Data

**Source V3:** Section 3.5 (Confidence Calibration)

**Apa yang dicoba:**
Sekarang confidence hardcoded (0.80, 0.84, 0.92, dst.). Ganti dengan threshold dari precision-recall curve — hitung pake data riil.

**Validasi:** `needs_review` flag lebih akurat — bandingkan `exact` dan `fuzzy` accuracy di benchmark.

**File yang kena:**
- `backend/app/services/field_extractor.py`
- `backend/app/services/form_mapper.py`

**Backup:**
```bash
git add backend/app/services/field_extractor.py backend/app/services/form_mapper.py
git commit -m "backup: field_extractor + form_mapper before confidence rework"
```

**Cara:**
1. Kumpulin ~100 sertifikat yang sudah di-extract (74 sudah ada dari ground truth).
2. Label manual true/false per field.
3. Hitung precision-recall curve, cari threshold optimal.
4. Ganti const confidence dengan threshold ini.

**Success criteria:**
`needs_review` flag lebih akurat — tidak false positive pada field yang benar, dan tidak false negative pada field yang salah.

**Revert:**
```bash
git checkout backend/app/services/field_extractor.py backend/app/services/form_mapper.py
```

---

## P2: Eksperimen 3 — BLOCKIE-Style Extraction (LLM Prototyping)

**Source V3:** Section 3.2 (Core Extraction — LLM for Prototyping)

**Apa yang dicoba:**
Implementasi BLOCKIE pattern [2505.13535]: decomposisi sertifikat jadi semantic blocks, lalu extract tiap block via LLM. Bikin pipeline prototype yang pake LLM API.

**Validasi:** Bandingkan F1 vs regex pipeline pakai benchmark.

**File baru (jangan timpa existing):**
- `backend/app/services/llm_extractor_experiment.py`

**Backup:** (tidak perlu — file baru semua)

**Minimal dependencies:** `pip install openai` atau pake API apapun yang available.

**Cara:**
1. Baca file PDF/image → convert ke text (via OCR existing).
2. Decompose text ke blocks (header, body, signature).
3. Kirim tiap block ke LLM dengan few-shot prompt.
4. Parse JSON response → map ke field schema.
5. Bandingin akurasi sama regex pipeline.

**Success criteria:**
F1 lebih tinggi dari regex pada field semantik (nama_kegiatan, role, penyelenggara). Wajar lebih lambat — ini prototyping.

**Catatan:**
Ini untuk prototyping saja. Jangan deploy ke production. Kalau berhasil, hasil labelingnya dipakai buat fine-tune LayoutLMv3 (Eksperimen 4).

---

## P2: Eksperimen 5 — Line-Level OCR

**Source V3:** Section 3.3 (Preprocessing & OCR — line-level OCR)

**Apa yang dicoba:**
Ganti word-level OCR dengan line-level OCR. Field sertifikat biasanya satu line — line-level bisa lebih akurat [2508.21693].

**Validasi:** Bandingkan CER atau F1 di benchmark.

**File baru:**
- `backend/app/services/ocr_line_experiment.py`

**Dependencies:**
```bash
pip install kaldilm kraken
```

Atau alternatif: pake `pytesseract` dengan `--psm 6` (treat image as single uniform block of text).

**Cara:**
1. Ambil region teks dari layout detection.
2. Run line-level OCR (Kraken atau Tesseract --psm 6).
3. Compare CER dengan word-level RapidOCR.
4. Kalau lebih baik, integrate ke pipeline.

**Success criteria:**
CER lebih rendah dari RapidOCR pada sertifikat dengan teks rapat. Atau minimal 4x lebih cepat [2508.21693].

---

## P3: Eksperimen 7 — Conformal Prediction untuk Candidate Set

**Source V3:** Section 3.5 (Confidence Calibration — conformal prediction)

**Apa yang dicoba:**
Implementasi conformal prediction [2401.13744]: untuk field dengan banyak kandidat, output candidate set (2-3 nilai) dengan garansi statistik.

**File baru:**
- `backend/app/services/conformal_experiment.py`

**Cara:**
1. Kumpulin calibration set (~50 labeled samples).
2. Hitung conformity scores (kesalahan per field).
3. Tentukan quantile threshold untuk coverage 90%.
4. Di inference: output candidate set kalau confidence > threshold.

**Success criteria:**
90% coverage dengan average set size <3. Artinya: 90% percaya nilai benar ada di dalam 2-3 kandidat.

---

## P3: Eksperimen 4 — Fine-Tune LayoutLMv3 (ML Core)

**Source V3:** Section 3.1 (Core Extraction — ML Approach)

**Apa yang dicoba:**
Fine-tune LayoutLMv3-base dengan LoRA di dataset sertifikat. Ini eksperimen paling besar.

**File baru:**
- `backend/app/services/layoutlm_train_experiment.py` (training script)
- `backend/app/services/layoutlm_infer_experiment.py` (inference script)

**Backup:** (tidak perlu — file baru)

**Dependencies:**
```bash
pip install transformers peft datasets torch evaluate seqeval onnxruntime
```

**Data yang dibutuhkan:**
- 200-500 sertifikat labeled (bisa dari hasil Eksperimen 3)
- Format: text + bounding box + label per field
- Bounding box bisa dari PyMuPDF atau Docling

**Cara:**
1. Prepare dataset: ekstrak token + bounding box + label dari sertifikat.
2. Load LayoutLMv3-base dari HuggingFace.
3. LoRA fine-tune (rank=8, target modules: query, value).
4. Evaluate on held-out test set.
5. Export ke ONNX INT8.

**Success criteria:**
F1 >85% pada field semantik di test set. Inference <500ms per dokumen di CPU (ONNX INT8).

**Revert:**
Hapus file experiment, hasil model ada di folder terpisah (misal `models/layoutlm_certificate/`).

---

## Ringkasan Prioritas

| Prioritas | Eksperimen | Effort | Impact | Risiko |
|-----------|-----------|--------|--------|--------|
| **P0** | **6. Evaluation Framework** | ✅ DONE | ✅ DONE | ✅ DONE |
| P1 | 1. OCR Confidence Capture | Rendah | Sedang | Rendah |
| P1 | 2. Confidence Threshold | Rendah | Sedang | Rendah |
| P2 | 3. LLM Prototyping | Sedang | Tinggi | Rendah |
| P2 | 5. Line-Level OCR | Sedang | Sedang | Rendah |
| P3 | 7. Conformal Prediction | Sedang | Sedang | Rendah |
| P3 | 4. LayoutLMv3 Fine-Tune | Tinggi | Tinggi | Sedang |

**Setelah baseline didapat**, langsung kerjakan P1 — effort rendah, resiko rendah, langsung ngasih angka yang terukur.

---

## Referensi Cepat Paper

| Paper ID | Judul Pendek | Komponen |
|----------|-------------|----------|
| [2505.13535] | BLOCKIE — LLM extraction | Core Extraction (LLM) |
| [2404.10848] | LayoutLMv3 + EM+BBO | Core Extraction (ML) |
| [2508.21693] | Line-level OCR | Preprocessing |
| [2401.13744] | Conformal Prediction | Confidence |
| [2311.12436] | Isotonic Regression | Confidence |
| [2508.14557] | Internal Document Redundancy | Preprocessing |
| [2305.14975] | Just Ask for Calibration | Confidence |
| [2505.20429] | PreP-OCR pipeline | Preprocessing |
