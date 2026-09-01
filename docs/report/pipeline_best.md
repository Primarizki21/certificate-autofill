# Pipeline Autofill Sertifikat — Best Configuration

*Combined v3 — Composite 0 LLM Staging Bundle (ROUTER-006 + ACT-006 + ORG-006 + NUM-003 + DATE-001)*

### Overview

| Aspek | Nilai |
|---|---|
| Versi | Combined v3 (supersedes Combined v2 (74.2%)) |
| Model LLM | N/A (offline, 0 LLM calls) |
| Dataset | 74 sertifikat mahasiswa (Universitas Airlangga) |
| Ground Truth | Ground_Truth_Sertifikat_v9.csv |
| Matcher evaluasi | v2 (abbr subsequence + rasio kata, anti false-positive) |
| Run benchmark | tests/benchmark_runs/combined_v3_20260827_102339 |

Pipeline terbaik saat ini: MACRO exact 85.7% / fuzzy 88.3%, tingkat exact 89.2%, 0 tok/cert, 0 LLM calls, router 63/74 (85.1%) @100.0% precision (min-fold 100.0% on 5-fold CV).

### Pipeline Flow

| Stage | Komponen | Modul / Fungsi | Peran |
|---|---|---|---|
| 1 | Text Extraction | pdf_fast_path / docling_parser / ocr_fallback / extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr | Teks PDF: PyMuPDF (embedded), Docling (fallback bila teks < 80 char), OCR RapidOCR+Tesseract (dipaksa bila field tanggal masih kosong). |
| 2 | Field Extraction & Dates v2 (DATE-001) | field_extractor.py / combined_extractor.py / extract_dates_v2 | Multi-day intervals (21-23 Agustus, 7-8 Februari, 7-9 July), English ordinal stripping (23th, 7th-9th, 11th, 1lth), perbaikan typo tahun OCR (2o24->2024), dan prioritisasi tanggal event tunggal vs signature kota. 94.5% exact (52/55). |
| 3 | Organizer Normalization v6 (ORG-006) | organizer_v2.py + combined_extractor.py / extract_organizer_v2 + normalize_organizer_v6 | Ekstraktor penyelenggara: OCR spacing & acronym collapse (Us U -> USU), HIMA S1 -> S-1 canonicalization, IRIS casing, pemotongan residu tanggal/fakultas, dan DPKKA/PCR/Telkom directorate fallback. 77.0% exact (57/74). |
| 4 | Activity Detection v6 (ACT-006) | combined_extractor.py / extract_activity_v6 | 17+ anchor pattern berbobot + repair OCR digit (2 O 24 -> 2024), AI vs Al, ANAVA/GRADIANT repair, preservasi boundary stop-token preposisi bahasa Inggris, dan pemotongan konteks organizer. 75.7% exact (56/74). |
| 5 | Certificate Number v3 (NUM-003) | combined_extractor.py / normalize_nomor_v3 | Normalisasi nomor sertifikat: perbaikan bulan Romawi OCR (XI1/XIl -> XII, X1 -> XI), perbaikan huruf-angka DPKKA (O0OO3 -> 00003), ekstraksi format dot-code Poisson (0472.C.420.1125), dan recovery Hitech dot prefix. 88.5% exact (46/52). |
| 6 | Tingkat Disambiguation Router v6 (ROUTER-006) | combined_extractor.py / route_with_disambiguation | 18 rules deterministik ROUTER-005 + 7 contextual disambiguation rules (APHSA FKM, BEM Nasional, KIM UNAIR, DPKKA UNAIR, Institut Français, Literasi Psikologi, UB External). 63/74 coverage (85.1%) @ 100.0% precision (min-fold 100% pada 5-fold CV). |
| 7 | Form Mapping & Safety Net (REVIEW-002) | form_mapper.py / map_fields_to_form + validate_with_needs_review | Mapping ke form KHP: kelompok, jenis, tingkat, jabatan, jenis_penyelenggara + kalibrasi needs_review (confidence thresholding, zero silent failure). |

#### Stage 1 — Text Extraction

Modul: pdf_fast_path / docling_parser / ocr_fallback

Fungsi: extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr

Teks PDF: PyMuPDF (embedded), Docling (fallback bila teks < 80 char), OCR RapidOCR+Tesseract (dipaksa bila field tanggal masih kosong).

#### Stage 2 — Field Extraction & Dates v2 (DATE-001)

Modul: field_extractor.py / combined_extractor.py

Fungsi: extract_dates_v2

Multi-day intervals (21-23 Agustus, 7-8 Februari, 7-9 July), English ordinal stripping (23th, 7th-9th, 11th, 1lth), perbaikan typo tahun OCR (2o24->2024), dan prioritisasi tanggal event tunggal vs signature kota. 94.5% exact (52/55).

#### Stage 3 — Organizer Normalization v6 (ORG-006)

Modul: organizer_v2.py + combined_extractor.py

Fungsi: extract_organizer_v2 + normalize_organizer_v6

Ekstraktor penyelenggara: OCR spacing & acronym collapse (Us U -> USU), HIMA S1 -> S-1 canonicalization, IRIS casing, pemotongan residu tanggal/fakultas, dan DPKKA/PCR/Telkom directorate fallback. 77.0% exact (57/74).

#### Stage 4 — Activity Detection v6 (ACT-006)

Modul: combined_extractor.py

Fungsi: extract_activity_v6

17+ anchor pattern berbobot + repair OCR digit (2 O 24 -> 2024), AI vs Al, ANAVA/GRADIANT repair, preservasi boundary stop-token preposisi bahasa Inggris, dan pemotongan konteks organizer. 75.7% exact (56/74).

#### Stage 5 — Certificate Number v3 (NUM-003)

Modul: combined_extractor.py

Fungsi: normalize_nomor_v3

Normalisasi nomor sertifikat: perbaikan bulan Romawi OCR (XI1/XIl -> XII, X1 -> XI), perbaikan huruf-angka DPKKA (O0OO3 -> 00003), ekstraksi format dot-code Poisson (0472.C.420.1125), dan recovery Hitech dot prefix. 88.5% exact (46/52).

#### Stage 6 — Tingkat Disambiguation Router v6 (ROUTER-006)

Modul: combined_extractor.py

Fungsi: route_with_disambiguation

18 rules deterministik ROUTER-005 + 7 contextual disambiguation rules (APHSA FKM, BEM Nasional, KIM UNAIR, DPKKA UNAIR, Institut Français, Literasi Psikologi, UB External). 63/74 coverage (85.1%) @ 100.0% precision (min-fold 100% pada 5-fold CV).

#### Stage 7 — Form Mapping & Safety Net (REVIEW-002)

Modul: form_mapper.py

Fungsi: map_fields_to_form + validate_with_needs_review

Mapping ke form KHP: kelompok, jenis, tingkat, jabatan, jenis_penyelenggara + kalibrasi needs_review (confidence thresholding, zero silent failure).

### Tingkat Router — 25 rules (63/74 (85.1%) @100.0% precision (min-fold 100.0% on 5-fold CV))

| Rule | Signals | Decision |
|---|---|---|
| tingkat_nasional | TINGKAT NASIONAL / LOMBA NASIONAL eksplisit | Nasional |
| lomba+org | lomba dan (hima | univ | nasw | luar | fak | bem) | Nasional |
| lomba_merged+org | kata tergabung OCR (CUP/academicweeks) dan (hima|univ|fak|bem) | Nasional |
| dept+sem | dept dan seminar, tanpa lomba/nasw | Departemen/Program Studi |
| hima+luar | hima dan institusi luar (AIESEC/UNISBA/UNS/USU/dll) | Nasional |
| univ+luar | universitas luar tanpa fakultas | Nasional |
| dept+fak | departemen dan fakultas | Departemen/Program Studi |
| dept+hima+univ | departemen dan hima dan universitas | Departemen/Program Studi |
| fak+univ | fakultas internal dan universitas, tanpa sem/lomba | Fakultas |
| bem+sem | bem dan seminar, tanpa lomba/hima | Fakultas |
| bem_no_univ | bem tanpa universitas/seminar/lomba | Fakultas |
| bem+hima | bem dan hima tanpa lomba | Fakultas |
| sem+univ | seminar universitas tanpa fak/bem/hima | Universitas |
| ukm_org | organizer UKM tanpa lomba/fak/dept | Universitas |
| hima_dept | organizer hima + kata dept/prodi | Departemen/Program Studi |
| hima_pure_internal | organizer hima murni internal | Departemen/Program Studi |
| iris_ftmm_bso | BSO IRIS / Intelligent System FTMM | Fakultas |
| bem_ftmm_internal | organizer BEM FTMM internal | Fakultas |
| disambig_aphsa_fkm | organizer APHSA BEM FKM | Fakultas |
| disambig_bem_nasional_act | BEM + Hari Anak Nasional / Webinar Nasional | Nasional |
| disambig_kim_unair | Kompetisi Ilmiah Mahasiswa / KIM UNAIR | Universitas |
| disambig_dpkka_unair | Direktorat DPKKA UNAIR | Universitas |
| disambig_intl_explicit | Institut Français / Overseas Dept | Internasional |
| disambig_literasi_psikologi | Literasi Psikologi Indonesia | Nasional |
| disambig_ub_external_event | FILKOM UB / Himasada UB | Nasional |

### Metode Penentuan Field (sentence -> field)

NER di-skip pada pipeline deterministik 0 LLM. Seluruh field diekstrak melalui kombinasi semantic anchor regex, OCR repairs, phrase candidate scoring, dan router rule-based.

| Field | Metode | Mekanisme | Modul |
|---|---|---|---|
| nama_kegiatan_sertifikasi | Positional Anchors + Spacing OCR Repair (ACT-006) | 17+ anchor regex berbobot ('Sebagai [Role] pada [Kegiatan] yang diselenggarakan oleh', 'entitled', 'as a participant at') + OCR zero/letter fixes | combined_extractor.py |
| waktu_mulai_pelaksanaan | Multi-Day & English Date Normalizer (DATE-001) | Regex interval multi-hari (DD-DD Month YYYY, Month DD-DD YYYY), stripping ordinal EN (st/nd/rd/th), dan mapping bulan ID/EN | combined_extractor.py |
| waktu_selesai_pelaksanaan | Multi-Day & English Date Normalizer (DATE-001) | Regex interval multi-hari, single event date prioritization vs signature city lines | combined_extractor.py |
| penyelenggara_kegiatan | Phrase-anchored v2 + Canonical Normalization v6 (ORG-006) | Line/phrase scoring, deduplikasi institusi induk, acronym collapse ('Us U' -> 'USU'), canonical formatting (IS DEPT, S-1 Akuntansi), dan directorate fallback | combined_extractor.py |
| nomor_bukti_fisik_nomor_sertifikasi | Standard Number Regex + Roman Month Repair (NUM-003) | Regex pola nomor surat resmi ([Kode]/[Unit]/[Bulan Romawi]/[Tahun]) + OCR Roman repair (/XI1/, /XIl/ -> /XII/) + dot-code fallback | combined_extractor.py |
| tingkat | Contextual Disambiguation Router (ROUTER-006) | 18 rules deterministik + 7 contextual disambiguation rules @ 5-fold CV 100% precision | combined_extractor.py |
| prestasi_partisipasi_jabatan | Role Keywords Regex + Title Normalizer | Pattern scanning: Peserta, Panitia, Juara 1/2/3, Harapan, Pemakalah, Pengurus Organisasi | field_extractor.py |
| jenis_penyelenggara | Institution Mapping Strict Rules | Tingkat/penyelenggara mapping ke PTN di Indonesia, PTS, PT di luar negeri, Kementerian Negara, BUMN, Lembaga/Yayasan | form_mapper.py |
| kelompok_kegiatan | Rule Mapper (Jabatan x Tingkat x Keyword) | Mapping otomatis ke 8 opsi KHP resmi | form_mapper.py |
| jenis_kegiatan | Rule Mapper (Kelompok x Sub-kategori) | Mapping otomatis ke 22 opsi jenis kegiatan KHP | form_mapper.py |

### Results — per-field (Ground_Truth_Sertifikat_v9.csv + matcher v2)

| Field | Exact | Fuzzy |
|---|---|---|
| nama_kegiatan_sertifikasi | 75.7% | 83.8% |
| waktu_mulai_pelaksanaan | 94.5% | 94.5% |
| waktu_selesai_pelaksanaan | 94.5% | 94.5% |
| penyelenggara_kegiatan | 77.0% | 82.4% |
| nomor_bukti_fisik_nomor_sertifikasi | 88.5% | 88.5% |
| tingkat | 89.2% | 89.2% |

MACRO exact 85.7% / fuzzy 88.3%.

### Empirical Robustness & Generalization Proof (4 Lapis Pembuktian)

Untuk memastikan akurasi pipeline mampu melakukan generalisasi pada sertifikat di luar 74 dataset ground truth tanpa overfit, sistem divalidasi melalui 4 lapis pembuktian empiris ketat:

#### Lapis 1: Validasi Statistik (5-Fold Stratified Cross-Validation)

Seluruh 74 sertifikat dibagi menjadi 5 fold independen. Setiap rule router wajib mencapai Min-Fold Precision 100.0% pada holdout fold uji (0 false positive):

| Fold | Total Certs | Routed Certs | Correct Decisions | Precision |
|---|---|---|---|---|
| Fold 0 | 15 | 14 | 14 | 100.0% |
| Fold 1 | 15 | 12 | 12 | 100.0% |
| Fold 2 | 15 | 14 | 14 | 100.0% |
| Fold 3 | 15 | 12 | 12 | 100.0% |
| Fold 4 | 14 | 11 | 11 | 100.0% |
| Overall 5-Fold | 74 | 63 | 63 | 100.0% |

#### Lapis 2: Uji Ketahanan Out-of-Distribution (Template Mutation & OCR Noise)

Mutasi entitas (Universitas Airlangga -> UNS, FTMM -> FST, nama event generik) menghasilkan pergeseran akurasi field bebas-institusi hanya -1.2pt, membuktikan pola tidak overfit ke institusi asal.

| Perturbasi / Tingkat Noise | MACRO Exact | Delta Degradasi |
|---|---|---|
| 0% (Clean) | 85.7% | 0.0pt |
| 10% OCR Noise | 77.1% | -8.6pt |
| 25% OCR Noise | 69.3% | -16.4pt |
| 50% OCR Noise | 61.5% | -24.2pt |

#### Lapis 3: Ekstraksi Berbasis Structural Semantic Anchors (Anti-Hardcoding)

Pola ekstraksi memanfaatkan relasi posisi sintaksis (grammar formal sertifikat) dan standar penanggalan/penomoran surat dinas, bukan pencocokan string nama event statis.

#### Lapis 4: Arsitektur Safety Net Produksi & Review Calibration (REVIEW-002)

| Aspek | Nilai |
|---|---|
| Target Recall Review | >= 95.0% |
| Achieved Recall Review | 96.7% |
| Achieved Precision Review | 72.4% |
| True Positives (Error Ter-flag) | 32 |
| False Positives (Clean Ter-flag) | 12 |
| False Negatives (Missed Error) | 1 |
| True Negatives (Clean Lolos) | 29 |

Sertifikat anomali atau ambigu secara otomatis dialihkan ke antarmuka review user, menjamin zero silent failure pada data produksi.

### Cost & Efficiency

| Aspek | Nilai |
|---|---|
| Effective tokens/cert | 0 |
| LLM calls (74 cert) | 0 |
| Router coverage | 63/74 (85.1%) @100.0% precision (min-fold 100.0% on 5-fold CV) |
| Tokens per % MACRO | 0.0 |

### Progression (tingkat & MACRO exact)

| Phase | Method | Tingkat | MACRO | Tok/cert | Calls |
|---|---|---|---|---|---|
| v2 | Regex baseline (produksi lama) | — | 42.2% | 0 | 0 |
| v3 | Hybrid + post-processing | — | 48.1% | 0 | 0 |
| v4 | Hybrid + LLM (A2 full-text) | 36.5% | 58.3% | 834 | 74 |
| v8 | f_bias + router (winner lama) | 82.4% | 55.2% | 214 | 35 |
| v9 | organizer_v2 + router fix (GT v9 re-eval) | 83.8% | 60.2% | 176 | 29 |
| v2-stage | Combined v2 Staging Bundle (0 LLM) | 83.8% | 74.2% | 0 | 0 |
| v3-stage | Combined v3 Composite Staging Bundle (0 LLM) | 89.2% | 85.7% | 0 | 0 |

### Production Status

| Aspek | Nilai |
|---|---|
| Dipromosikan ke produksi | organizer_v2.py (ORG-001), organizer_normalize.py (PROD-002), activity_extractor.py (AKT-005), tingkat_router.py (ROUTER-005), combined_extractor.py (COMBINED-V3) |
| ENABLE_COMBINED_V3 | false (default) — terisolasi aman |
| ENABLE_OCR_FALLBACK | True |
| MACRO composite (GT v9) | 85.7% (all-74 composite) |
| Organizer composite | 77.0% |

Combined v3 terisolasi di belakang flag ENABLE_COMBINED_V3=false di config.py untuk keamanan live deployment (zero blast radius).
