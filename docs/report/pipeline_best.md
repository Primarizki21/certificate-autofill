# Pipeline v9

*Pipeline v9 — organizer_v2 + tingkat_router (best current)*

### Overview

| Aspek | Nilai |
|---|---|
| Versi | v9 (supersedes v8) |
| Model LLM | llama3.1:8b (Ollama, Q4_K_M) |
| Dataset | 74 sertifikat mahasiswa (Universitas Airlangga) |
| Ground Truth | Ground_Truth_Sertifikat_v9.csv |
| Matcher evaluasi | v2 (abbr subsequence + rasio kata, anti false-positive) |
| Run benchmark | tests/benchmark_runs/run_llm_v4_20260805_163541 |

Pipeline terbaik saat ini: MACRO exact 60.2% / fuzzy 74.2%, tingkat exact 83.8%, 176 tok/cert, 29 LLM calls, router 45/74 @100% precision.

### Pipeline Flow

| Stage | Komponen | Modul / Fungsi | Peran |
|---|---|---|---|
| 1 | Text Extraction | pdf_fast_path / docling_parser / ocr_fallback / extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr | Teks PDF: PyMuPDF (embedded), Docling (fallback bila teks < 80 char), OCR RapidOCR+Tesseract (dipaksa bila field tanggal masih kosong). 2-pass nomor terintegrasi tapi OFF (flag ENABLE_OCR_NUMBER_2PASS). |
| 2 | Field Extraction (regex) | field_extractor.py / extract_certificate_fields | Regex untuk tanggal (dgn alias kesalahan OCR bulan: AGUSTU5 -> AGUSTUS), role, nama kegiatan, nomor sertifikat, organizer v1. |
| 3 | Organizer v2 | organizer_v2.py / extract_organizer_v2 | Ekstraktor penyelenggara (v9/ORG-001): preprocess perbaikan OCR-merge, kandidat phrase/line, scoring, normalisasi akronim (BEM FTMM -> 'BEM FTMM Universitas Airlangga'). |
| 4 | Form Mapping | form_mapper.py / map_fields_to_form | Mapping ke form KHP: kelompok, jenis, tingkat, jabatan, jenis_penyelenggara + validate_with_needs_review (confidence < 0.80 -> review). |
| 5 | Tingkat Router | tingkat_router.py / route_tingkat | 13 rule deterministik berbasis sinyal teks (lomba/hima/dept/univ/luar/nasw/sem/fak/bem). 45/74 keputusan @100% precision (ROUTER-002/003). |
| 6 | LLM Tingkat (fallback) | llm_tingkat.py / infer_tingkat | Prompt f_bias via Ollama utk cert yang tak ter-rute (29/74). Minimisasi teks per kesulitan (140/200/300 char), context block (nama kegiatan, penyelenggara, peran), temperature 0. |
| 7 | Persistence | database / models.py / ExtractedField + needs_review | Simpan field + confidence ke PostgreSQL; flag needs_review utk review manusia. |

#### Stage 1 — Text Extraction

Modul: pdf_fast_path / docling_parser / ocr_fallback

Fungsi: extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr

Teks PDF: PyMuPDF (embedded), Docling (fallback bila teks < 80 char), OCR RapidOCR+Tesseract (dipaksa bila field tanggal masih kosong). 2-pass nomor terintegrasi tapi OFF (flag ENABLE_OCR_NUMBER_2PASS).

#### Stage 2 — Field Extraction (regex)

Modul: field_extractor.py

Fungsi: extract_certificate_fields

Regex untuk tanggal (dgn alias kesalahan OCR bulan: AGUSTU5 -> AGUSTUS), role, nama kegiatan, nomor sertifikat, organizer v1.

#### Stage 3 — Organizer v2

Modul: organizer_v2.py

Fungsi: extract_organizer_v2

Ekstraktor penyelenggara (v9/ORG-001): preprocess perbaikan OCR-merge, kandidat phrase/line, scoring, normalisasi akronim (BEM FTMM -> 'BEM FTMM Universitas Airlangga').

#### Stage 4 — Form Mapping

Modul: form_mapper.py

Fungsi: map_fields_to_form

Mapping ke form KHP: kelompok, jenis, tingkat, jabatan, jenis_penyelenggara + validate_with_needs_review (confidence < 0.80 -> review).

#### Stage 5 — Tingkat Router

Modul: tingkat_router.py

Fungsi: route_tingkat

13 rule deterministik berbasis sinyal teks (lomba/hima/dept/univ/luar/nasw/sem/fak/bem). 45/74 keputusan @100% precision (ROUTER-002/003).

#### Stage 6 — LLM Tingkat (fallback)

Modul: llm_tingkat.py

Fungsi: infer_tingkat

Prompt f_bias via Ollama utk cert yang tak ter-rute (29/74). Minimisasi teks per kesulitan (140/200/300 char), context block (nama kegiatan, penyelenggara, peran), temperature 0.

#### Stage 7 — Persistence

Modul: database / models.py

Fungsi: ExtractedField + needs_review

Simpan field + confidence ke PostgreSQL; flag needs_review utk review manusia.

### Tingkat Router — 13 rules (45/74 @100% precision)

| Rule | Signals | Decision |
|---|---|---|
| tingkat_nasional | TINGKAT NASIONAL / LOMBA NASIONAL eksplisit | Nasional |
| lomba+org | lomba dan (hima | univ | nasw | luar | fak | bem) | Nasional |
| lomba_merged+org | kata tergabung OCR (CUP/academicweeks) dan (hima|univ|fak|bem) | Nasional |
| dept+sem | dept dan seminar, tanpa lomba/nasw | Departemen/Program Studi |
| hima+luar | hima dan organisasi luar | Nasional |
| univ+luar | univ dan luar, tanpa fak | Nasional |
| dept+fak | dept dan fak | Departemen/Program Studi |
| dept+hima+univ | dept dan hima dan univ | Departemen/Program Studi |
| fak+univ | fak dan univ, tanpa sem/nasw/lomba | Fakultas |
| bem+sem | bem dan sem, tanpa lomba/hima/nasw | Fakultas |
| bem_no_univ | bem tanpa konteks univ/lomba/nasw/luar/hima | Fakultas |
| bem+hima | bem dan hima (panitia internal FTMM) | Fakultas |
| sem+univ | sem dan univ, tanpa fak/bem/hima/lomba | Universitas |

### Metode Penentuan Field (sentence -> field)

NER TIDAK dipakai di v9. NER v1 (pre-trained) = 12.8% MACRO (FAIL, closed di ledger); hybrid NER+regex v3 = 47.7% (superseded). Semua field ditentukan oleh regex + rule-based extractor; LLM hanya fallback utk field tingkat.

| Field | Metode | Mekanisme | Modul |
|---|---|---|---|
| nama_kegiatan_sertifikasi | Regex template + keyword | pola 'seminar X yang diselenggarakan', 'talkshow', PKKMB; fallback keyword AIRNOLOGY/KAKIWIMA/SPECTA/BRIEF | field_extractor.py (extract_activity_name) |
| waktu_mulai / waktu_selesai | Regex 5-tier + alias bulan OCR | interval numerik -> English month-first -> tanggal tunggal -> same-month -> token-scan; MONTH_ALIASES (AGUSTU5 -> AGUSTUS) | field_extractor.py (extract_dates) |
| raw_role (jabatan) | Regex + keyword fallback | pola 'as a' / 'sebagai' / 'Atas partisipasinya sebagai'; fallback keyword PANITIA/PESERTA/KETUA | field_extractor.py (extract_role) |
| nomor_bukti_fisik_nomor_sertifikasi | Regex 3 pola | NO./NOMOR + digit + tahun (mis. 212/E/BEM-FKM/UNAIR/X/2023) | field_extractor.py (extract_certificate_number) |
| penyelenggara_kegiatan | Rule-based organizer_v2 | preprocess perbaikan OCR-merge, kandidat phrase/line, scoring, normalisasi akronim (BEM FTMM -> 'BEM FTMM Universitas Airlangga') | organizer_v2.py (extract_organizer_v2) |
| tingkat | Router 13 rule -> LLM fallback | sinyal teks deterministik 45/74 @100% precision; LLM llama3.1:8b utk 29/74 cert yang tak ter-rute | tingkat_router.py + llm_tingkat.py |
| kelompok / jenis / jabatan form / jenis_penyelenggara | Rule mapper | form_mapper rules + threshold confidence < 0.80 -> needs_review (human-in-the-loop) | form_mapper.py (map_fields_to_form) |

### LLM Tingkat (fallback router)

| Aspek | Nilai |
|---|---|
| Model | llama3.1:8b |
| Prompt | f_bias (v4_bias) — koreksi bias bahasa Inggris |
| Temperature / num_predict | 0 / 30 |
| Budget teks (strong/normal/poor_ocr) | 140 / 200 / 300 |
| Context fields | nama_kegiatan_sertifikasi, penyelenggara_kegiatan, raw_role |
| Host | http://127.0.0.1:11434 |

### Results — per-field (Ground_Truth_Sertifikat_v9.csv + matcher v2)

| Field | Exact | Fuzzy |
|---|---|---|
| nama_kegiatan_sertifikasi | 25.7% | 52.7% |
| waktu_mulai_pelaksanaan | 81.8% | 81.8% |
| waktu_selesai_pelaksanaan | 81.8% | 81.8% |
| penyelenggara_kegiatan | 39.2% | 79.7% |
| nomor_bukti_fisik_nomor_sertifikasi | 59.6% | 59.6% |
| tingkat | 83.8% | 89.2% |

MACRO exact 60.2% / fuzzy 74.2%.

### Cost & Efficiency

| Aspek | Nilai |
|---|---|
| Effective tokens/cert | 176 |
| LLM calls (74 cert) | 29 |
| Router coverage | 45/74 @100% precision |
| Tokens per % MACRO | 2.9 |

### Progression (tingkat & MACRO exact)

| Phase | Method | Tingkat | MACRO | Tok/cert | Calls |
|---|---|---|---|---|---|
| v4 | LLM A1 (per-field) | 47.3% | 49.0% | 834 | 125 |
| v4 | LLM A2 v2 (full-text) | 36.5% | 58.3% | 834 | 74 |
| v6 | LLM v3 Variant B | 39.2% | 46.4% | 479 | 74 |
| v7 | P3 router rule-based | 71.6% | 53.1% | 191 | 42 |
| v7 | P4 e_hybrid + router | 77.0% | 54.2% | 202 | 39 |
| v8 | f_bias + router | 82.4% | 55.2% | 214 | 35 |
| v9 | organizer_v2 + router | 83.8% | 58.9% | 176 | 29 |
| v9 | re-baseline GT v9 + matcher v2 | 83.8% | 60.2% | 176 | 29 |

### Production Status

| Aspek | Nilai |
|---|---|
| Dipromosikan ke produksi | backend/app/services/organizer_v2.py, backend/app/services/tingkat_router.py |
| ENABLE_LLM_TINGKAT | false (default) — produksi deterministik |
| ENABLE_OCR_NUMBER_2PASS | false — keputusan deploy-time |
| ENABLE_OCR_FALLBACK | True |
| MACRO scan (produksi, GT v9) | 47.3% |
| Organizer scan (produksi) | 26.5% |

Produksi deterministik tanpa LLM (ENABLE_LLM_TINGKAT=false default). 2-pass nomor terintegrasi tapi OFF (keputusan deploy-time: gain +3pt nomor dengan cost +2-10s/cert). Re-eval pasca-promosi (GT v9 + matcher v2): scan MACRO 45.8 -> 47.3%, organizer 20.4 -> 26.5%.

### Cara Mengganti saat Best Baru

- Update docs/report/pipeline_data.json (version, experiment, results, stages, router_rules, progression).
- Jalankan: uv run python scripts/generate_pipeline_doc.py
- pipeline_best.docx / .xlsx / .md ter-regenerate otomatis. Copy JSON dulu untuk history bila perlu.
