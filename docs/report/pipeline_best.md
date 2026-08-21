# Pipeline HYB-COMBINED

*HYB-COMBINED — Router + AKT-005 + ORG-004 + PROD-002 (best offline, 0 LLM)*

### Overview

| Aspek | Nilai |
|---|---|
| Versi | HYB-COMBINED (supersedes v9) |
| Model LLM | N/A (offline, 0 LLM calls) |
| Dataset | 74 sertifikat mahasiswa (Universitas Airlangga) |
| Ground Truth | Ground_Truth_Sertifikat_v9.csv |
| Matcher evaluasi | v2 (abbr subsequence + rasio kata, anti false-positive) |
| Run benchmark | tests/benchmark_runs/hyb_combined_20260821_134811 |

Pipeline terbaik saat ini: MACRO exact 73.7% / fuzzy 80.2%, tingkat exact 81.1%, 0 tok/cert, 0 LLM calls, router 48/74 @100% precision (router rules only).

### Pipeline Flow

| Stage | Komponen | Modul / Fungsi | Peran |
|---|---|---|---|
| 1 | Text Extraction | pdf_fast_path / docling_parser / ocr_fallback / extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr | Teks PDF: PyMuPDF (embedded), Docling (fallback bila teks < 80 char), OCR RapidOCR+Tesseract (dipaksa bila field tanggal masih kosong). |
| 2 | Field Extraction (regex) | field_extractor.py / extract_certificate_fields | Regex untuk tanggal (dgn alias kesalahan OCR bulan: AGUSTU5 -> AGUSTUS), role, nomor sertifikat. |
| 3 | Organizer v2 + Normalization | organizer_v2.py + organizer_normalize.py / extract_organizer_v2 + normalize_organizer | Ekstraktor penyelenggara (ORG-001/ORG-004): preprocess OCR-merge, kandidat phrase/line, scoring, normalisasi akronim, canonical format (IS DEPT, APHSA BEM FKM, STUDISL, Facultyof+UB). |
| 4 | Activity Detection v5 (AKT-005) | tests/benchmark_akt5.py / extract_activity_v5 | 16+ anchor pattern untuk nama kegiatan: Kepengurusan, Dalam acara/kegiatan, pada ajang, entitled/titled, participation at, the X organized by, winner of, collapse all-caps, repair OCR-merge. 62.2% exact (+55.4pt dari baseline 6.8%). |
| 5 | Form Mapping | form_mapper.py / map_fields_to_form | Mapping ke form KHP: kelompok, jenis, tingkat, jabatan, jenis_penyelenggara + validate_with_needs_review. |
| 6 | Tingkat Router | tingkat_router.py / route_tingkat | 15 rule deterministik berbasis sinyal teks (lomba/hima/dept/univ/luar/nasw/sem/fak/bem/ukm). 48/74 keputusan @100% precision. 26 cert need LLM (tidak dipakai di offline mode). |
| 7 | Persistence | database / models.py / ExtractedField + needs_review | Simpan field + confidence ke PostgreSQL; flag needs_review utk review manusia. |

#### Stage 1 — Text Extraction

Modul: pdf_fast_path / docling_parser / ocr_fallback

Fungsi: extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr

Teks PDF: PyMuPDF (embedded), Docling (fallback bila teks < 80 char), OCR RapidOCR+Tesseract (dipaksa bila field tanggal masih kosong).

#### Stage 2 — Field Extraction (regex)

Modul: field_extractor.py

Fungsi: extract_certificate_fields

Regex untuk tanggal (dgn alias kesalahan OCR bulan: AGUSTU5 -> AGUSTUS), role, nomor sertifikat.

#### Stage 3 — Organizer v2 + Normalization

Modul: organizer_v2.py + organizer_normalize.py

Fungsi: extract_organizer_v2 + normalize_organizer

Ekstraktor penyelenggara (ORG-001/ORG-004): preprocess OCR-merge, kandidat phrase/line, scoring, normalisasi akronim, canonical format (IS DEPT, APHSA BEM FKM, STUDISL, Facultyof+UB).

#### Stage 4 — Activity Detection v5 (AKT-005)

Modul: tests/benchmark_akt5.py

Fungsi: extract_activity_v5

16+ anchor pattern untuk nama kegiatan: Kepengurusan, Dalam acara/kegiatan, pada ajang, entitled/titled, participation at, the X organized by, winner of, collapse all-caps, repair OCR-merge. 62.2% exact (+55.4pt dari baseline 6.8%).

#### Stage 5 — Form Mapping

Modul: form_mapper.py

Fungsi: map_fields_to_form

Mapping ke form KHP: kelompok, jenis, tingkat, jabatan, jenis_penyelenggara + validate_with_needs_review.

#### Stage 6 — Tingkat Router

Modul: tingkat_router.py

Fungsi: route_tingkat

15 rule deterministik berbasis sinyal teks (lomba/hima/dept/univ/luar/nasw/sem/fak/bem/ukm). 48/74 keputusan @100% precision. 26 cert need LLM (tidak dipakai di offline mode).

#### Stage 7 — Persistence

Modul: database / models.py

Fungsi: ExtractedField + needs_review

Simpan field + confidence ke PostgreSQL; flag needs_review utk review manusia.

### Tingkat Router — 15 rules (48/74 @100% precision (router rules only))

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
| ukm_org | organizer UKM tanpa lomba/luar/nasw/sem/fak/dept | Universitas |
| hima_dept | hima_org dan dept | Departemen/Program Studi |

### Metode Penentuan Field (sentence -> field)

NER TIDAK dipakai. Semua field ditentukan oleh regex + rule-based extractor.

| Field | Metode | Mekanisme | Modul |
|---|---|---|---|
| nama_kegiatan_sertifikasi | AKT-005 regex patterns (v5) | 16+ anchor pattern: Kepengurusan, Dalam acara/kegiatan, pada ajang, entitled/titled, participation at, the X organized by, winner of, as a participant at; collapse all-caps (synreaach, ACIC); repair OCR-merge (digit-huruf boundary); stop junk 'untuk kategori'. 62.2% exact. | tests/benchmark_akt5.py (extract_activity_v5) |
| waktu_mulai / waktu_selesai | Regex 5-tier + alias bulan OCR | interval numerik -> English month-first -> tanggal tunggal -> same-month -> token-scan; MONTH_ALIASES (AGUSTU5 -> AGUSTUS) | field_extractor.py (extract_dates) |
| raw_role (jabatan) | Regex + keyword fallback | pola 'as a' / 'sebagai' / 'Atas partisipasinya sebagai'; fallback keyword PANITIA/PESERTA/KETUA | field_extractor.py (extract_role) |
| nomor_bukti_fisik_nomor_sertifikasi | Regex 4 pola + fallback raw text | NO./NOMOR + digit + tahun; pattern SERT- prefix; pattern titik; fallback raw text normalize. 76.9% exact (+17.3pt dari baseline). | field_extractor.py (extract_certificate_number) + ORG-002 |
| penyelenggara_kegiatan | ORG-004 canonical format | organizer_v2 + normalize_organizer: R0 strip trailing HIMA, R2 strip prefix Library Class, R3 strip sampai oleh, R4 strip mulai tanggal, R6 enrich kurang_lengkap (join baris beruntun, Biro-prefix, Himasada fakultas, dept OCR-merge), F1 alias map (IS DEPT, APHSABEMFKM, STUDISL, Facultyof+UB). 63.5% exact. | organizer_v2.py + organizer_normalize.py |
| tingkat | Router 15 rules (offline) | sinyal teks deterministik 48/74 @100% precision. 26 cert need LLM (offline mode: gunakan pipeline default). | tingkat_router.py |
| kelompok / jenis / jabatan form / jenis_penyelenggara | Rule mapper | form_mapper rules + threshold confidence < 0.80 -> needs_review (human-in-the-loop) | form_mapper.py (map_fields_to_form) |

### LLM Tingkat (fallback router)

| Aspek | Nilai |
|---|---|
| Model | N/A (offline mode) |
| Prompt | N/A |
| Temperature / num_predict | 0 / 30 |
| Budget teks (strong/normal/poor_ocr) | 140 / 200 / 300 |
| Context fields | nama_kegiatan_sertifikasi, penyelenggara_kegiatan, raw_role |
| Host | http://127.0.0.1:11434 |

### Results — per-field (Ground_Truth_Sertifikat_v9.csv + matcher v2)

| Field | Exact | Fuzzy |
|---|---|---|
| nama_kegiatan_sertifikasi | 62.2% | 81.1% |
| waktu_mulai_pelaksanaan | 81.8% | 81.8% |
| waktu_selesai_pelaksanaan | 81.8% | 81.8% |
| penyelenggara_kegiatan | 63.5% | 78.4% |
| nomor_bukti_fisik_nomor_sertifikasi | 76.9% | 76.9% |
| tingkat | 81.1% | 81.1% |

MACRO exact 73.7% / fuzzy 80.2%.

### Cost & Efficiency

| Aspek | Nilai |
|---|---|
| Effective tokens/cert | 0 |
| LLM calls (74 cert) | 0 |
| Router coverage | 48/74 @100% precision (router rules only) |
| Tokens per % MACRO | 0.0 |

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
| v10 | HYB-COMBINED (offline, 0 LLM) | 81.1% | 73.7% | 0 | 0 |
| v10 | HYB-LLM (+ LLM 26 cert) | 83.8% | 74.2% | 176 | 26 |

### Production Status

| Aspek | Nilai |
|---|---|
| Dipromosikan ke produksi | backend/app/services/organizer_v2.py, backend/app/services/organizer_normalize.py (flag ENABLE_ORGANIZER_NORMALIZATION), backend/app/services/tingkat_router.py |
| ENABLE_LLM_TINGKAT | false (default) — produksi deterministik |
| ENABLE_OCR_NUMBER_2PASS | false — keputusan deploy-time |
| ENABLE_OCR_FALLBACK | True |
| MACRO scan (produksi, GT v9) | 47.3% |
| Organizer scan (produksi) | 26.5% |

HYB-COMBINED = gabungan semua improvements terbaik (offline). Organizer normalization + AKT-005 activity detection belum di-port ke produksi (keputusan user). Router 48/74 @100% precision.

### Cara Mengganti saat Best Baru

- Update docs/report/pipeline_data.json (version, experiment, results, stages, router_rules, progression).
- Jalankan: uv run python scripts/generate_pipeline_doc.py
- pipeline_best.docx / .xlsx / .md ter-regenerate otomatis. Copy JSON dulu untuk history bila perlu.
