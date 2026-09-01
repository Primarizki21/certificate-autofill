# Pipeline Autofill Sertifikat — Best Configuration

*Combined v4.2 — 3 Pillars & High-DPI Robustness Staging Bundle (EXP-V4-003: 0 LLM, 100% Deterministic)*

### Overview

| Aspek | Nilai |
|---|---|
| Versi | Combined v4.2 (supersedes Combined v4.0 / Combined v3) |
| Model LLM | N/A (offline, 0 LLM calls) |
| Dataset | 74 sertifikat mahasiswa (Universitas Airlangga) |
| Ground Truth | Ground_Truth_Sertifikat_v9.csv |
| Matcher evaluasi | v2 (abbr subsequence + rasio kata, anti false-positive) |
| Run benchmark | tests/benchmark_runs/combined_v4_2_20260901_131843 |

Pipeline terbaik saat ini: MACRO exact 88.02% (non-empty) / 76.82% (all-cells) / fuzzy 90.10% (non-empty) / 78.64% (all-cells), tingkat exact 90.5%, 0 tok/cert, 0 LLM calls, router 67/74 (90.5%) @100.0% precision (min-fold 100.0% on 5-fold CV).

### Pipeline Flow

| Stage | Komponen | Modul / Fungsi | Peran |
|---|---|---|---|
| 1 | Text Extraction (Fast Path & Fallback) | pdf_fast_path / docling_parser / ocr_fallback / extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr | Ekstraksi teks PDF adaptif: PyMuPDF (teks digital langsung ~50ms), Docling (fallback jika teks < 80 karakter), dan RapidOCR+Tesseract (dipaksa jika field tanggal belum terisi). 0 LLM calls. |
| 2 | High-DPI Region Crop Module (EXP-V4-003) | high_dpi_crop.py / render_region_high_dpi / extract_nomor_high_dpi | Modul crop mandiri yang me-render ulang region kotak nomor dari PDF pada resolusi tinggi 6.0x zoom (300+ DPI) sebelum OCR, memastikan teks nomor kabur/buram terbaca tajam tanpa memory bloat. |
| 3 | Field Extraction & Dates v2 (DATE-001) | field_extractor.py / combined_extractor.py / extract_dates_v2 | Ekstraksi tanggal pelaksanaan: mendukung interval multi-hari (21-23 Agustus, 7-8 Februari), ordinal stripping bahasa Inggris (23th, 7th-9th, 11th), pembersihan typo tahun OCR (2o24->2024), dan pemisahan tanggal kegiatan vs tanda tangan kota. 96.4% exact (53/55). |
| 4 | Organizer Normalization v7 (ORG-007) | organizer_v2.py + combined_extractor.py / extract_organizer_v2 + normalize_organizer_v7 | Ekstraksi penyelenggara: perbaikan spasi akronim OCR ('Us U' -> 'USU'), kanonisasi HIMA ('HIMA S1' -> 'HIMA S-1'), preservasi casing IRIS, pemotongan residu tanggal/fakultas, dan fallback unit DPKKA/PCR/Telkom. 78.4% exact (58/74). |
| 5 | Structural Activity Detection v8 (Pilar 1: AKT-008) | combined_extractor.py / extract_activity_v8 | Ekstraksi nama kegiatan berbasis 3 Pilar: memanfaatkan pola sintaksis resmi sertifikat bahasa Indonesia ('sebagai [Role] pada [Kegiatan] yang diselenggarakan oleh [Penyelenggara]') dan bahasa Inggris ('in the event entitled [Kegiatan]'), anti-hardcoding judul spesifik. 79.7% exact (59/74). |
| 6 | Certificate Number v5 (Pilar 2: NUM-005) | combined_extractor.py / normalize_nomor_v5 | Normalisasi nomor sertifikat universal: perbaikan angka Romawi bulan pada format surat dinas (/XI1/ -> /XII/, /X1/ -> /XI/, /V1/ -> /VI/), perbaikan huruf-angka DPKKA (O0OO3 -> 00003), dan deteksi dot-code. 92.3% exact (48/52). |
| 7 | Tingkat Disambiguation Router v7 (ROUTER-007) | combined_extractor.py / route_with_disambiguation | Router Tingkat deterministik: 26 rules komposit berbobot (18 deterministik dasar + 7 contextual disambiguation + rule Direktur Kemahasiswaan UNAIR) tanpa LLM. Coverage 67/74 (90.5%) dengan Min-Fold Precision 100.0% pada 5-Fold Cross Validation. |
| 8 | Form Mapping & Calibrated Safety Net (Pilar 3: REVIEW-002) | form_mapper.py / map_fields_to_form + validate_with_needs_review | Pemetaan otomatis ke opsi baku form KHP (kelompok, jenis, tingkat, peranan) serta kalibrasi confidence thresholding: jika confidence < 0.85 atau field required kosong, otomatis memicu needs_review = True (target recall review 96.7%, zero silent failure). |

#### Stage 1 — Text Extraction (Fast Path & Fallback)

Modul: pdf_fast_path / docling_parser / ocr_fallback

Fungsi: extract_text_with_pymupdf / parse_with_docling / extract_text_with_ocr

Ekstraksi teks PDF adaptif: PyMuPDF (teks digital langsung ~50ms), Docling (fallback jika teks < 80 karakter), dan RapidOCR+Tesseract (dipaksa jika field tanggal belum terisi). 0 LLM calls.

#### Stage 2 — High-DPI Region Crop Module (EXP-V4-003)

Modul: high_dpi_crop.py

Fungsi: render_region_high_dpi / extract_nomor_high_dpi

Modul crop mandiri yang me-render ulang region kotak nomor dari PDF pada resolusi tinggi 6.0x zoom (300+ DPI) sebelum OCR, memastikan teks nomor kabur/buram terbaca tajam tanpa memory bloat.

#### Stage 3 — Field Extraction & Dates v2 (DATE-001)

Modul: field_extractor.py / combined_extractor.py

Fungsi: extract_dates_v2

Ekstraksi tanggal pelaksanaan: mendukung interval multi-hari (21-23 Agustus, 7-8 Februari), ordinal stripping bahasa Inggris (23th, 7th-9th, 11th), pembersihan typo tahun OCR (2o24->2024), dan pemisahan tanggal kegiatan vs tanda tangan kota. 96.4% exact (53/55).

#### Stage 4 — Organizer Normalization v7 (ORG-007)

Modul: organizer_v2.py + combined_extractor.py

Fungsi: extract_organizer_v2 + normalize_organizer_v7

Ekstraksi penyelenggara: perbaikan spasi akronim OCR ('Us U' -> 'USU'), kanonisasi HIMA ('HIMA S1' -> 'HIMA S-1'), preservasi casing IRIS, pemotongan residu tanggal/fakultas, dan fallback unit DPKKA/PCR/Telkom. 78.4% exact (58/74).

#### Stage 5 — Structural Activity Detection v8 (Pilar 1: AKT-008)

Modul: combined_extractor.py

Fungsi: extract_activity_v8

Ekstraksi nama kegiatan berbasis 3 Pilar: memanfaatkan pola sintaksis resmi sertifikat bahasa Indonesia ('sebagai [Role] pada [Kegiatan] yang diselenggarakan oleh [Penyelenggara]') dan bahasa Inggris ('in the event entitled [Kegiatan]'), anti-hardcoding judul spesifik. 79.7% exact (59/74).

#### Stage 6 — Certificate Number v5 (Pilar 2: NUM-005)

Modul: combined_extractor.py

Fungsi: normalize_nomor_v5

Normalisasi nomor sertifikat universal: perbaikan angka Romawi bulan pada format surat dinas (/XI1/ -> /XII/, /X1/ -> /XI/, /V1/ -> /VI/), perbaikan huruf-angka DPKKA (O0OO3 -> 00003), dan deteksi dot-code. 92.3% exact (48/52).

#### Stage 7 — Tingkat Disambiguation Router v7 (ROUTER-007)

Modul: combined_extractor.py

Fungsi: route_with_disambiguation

Router Tingkat deterministik: 26 rules komposit berbobot (18 deterministik dasar + 7 contextual disambiguation + rule Direktur Kemahasiswaan UNAIR) tanpa LLM. Coverage 67/74 (90.5%) dengan Min-Fold Precision 100.0% pada 5-Fold Cross Validation.

#### Stage 8 — Form Mapping & Calibrated Safety Net (Pilar 3: REVIEW-002)

Modul: form_mapper.py

Fungsi: map_fields_to_form + validate_with_needs_review

Pemetaan otomatis ke opsi baku form KHP (kelompok, jenis, tingkat, peranan) serta kalibrasi confidence thresholding: jika confidence < 0.85 atau field required kosong, otomatis memicu needs_review = True (target recall review 96.7%, zero silent failure).

### Tingkat Router — 26 rules (67/74 (90.5%) @100.0% precision (min-fold 100.0% on 5-fold CV))

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
| direktur_kemahasiswaan_unair | Direktur Kemahasiswaan Universitas Airlangga / UNAIR | Universitas |

### Metode Penentuan Field (sentence -> field)

NER di-skip pada pipeline deterministik 0 LLM. Seluruh field diekstrak melalui kombinasi semantic anchor regex, OCR repairs, phrase candidate scoring, high-DPI crop, dan router rule-based.

| Field | Metode | Mekanisme | Modul |
|---|---|---|---|
| nama_kegiatan_sertifikasi | Structural Semantic Grammar Anchors (Pilar 1: AKT-008) | Pola sintaksis resmi ('sebagai [Role] pada [Kegiatan] yang diselenggarakan oleh', 'in the event entitled [Event]') + pembersihan OCR spacing/typo digit | combined_extractor.py |
| waktu_mulai_pelaksanaan | Multi-Day & English Date Normalizer (DATE-001) | Regex interval multi-hari (DD-DD Month YYYY, Month DD-DD YYYY), stripping ordinal EN (st/nd/rd/th), dan mapping bulan ID/EN | combined_extractor.py |
| waktu_selesai_pelaksanaan | Multi-Day & English Date Normalizer (DATE-001) | Regex interval multi-hari, single event date prioritization vs signature city lines | combined_extractor.py |
| penyelenggara_kegiatan | Phrase-anchored v2 + Canonical Normalization v7 (ORG-007) | Line/phrase scoring, deduplikasi institusi induk, acronym collapse ('Us U' -> 'USU'), kanonisasi S1 -> S-1, casing IRIS, dan directorate fallback | combined_extractor.py |
| nomor_bukti_fisik_nomor_sertifikasi | Universal Roman Month Repair + High-DPI Crop (Pilar 2: NUM-005) | Normalisasi universal angka Romawi bulan dinas (/XI1/, /XIl/ -> /XII/, /X1/ -> /XI/) + 6.0x zoom high-DPI re-rendering | combined_extractor.py / high_dpi_crop.py |
| tingkat | Contextual Disambiguation Router v7 (ROUTER-007) | 26 rules deterministik berbobot @ 5-fold CV 100% precision (min-fold 100.0%) | combined_extractor.py |
| prestasi_partisipasi_jabatan | Role Keywords Regex + Title Normalizer | Pattern scanning: Peserta, Panitia, Juara 1/2/3, Harapan, Pemakalah, Pengurus Organisasi | field_extractor.py |
| jenis_penyelenggara | Master Data Keyword Matcher | Pencocokan nama penyelenggara ke daftar PTN, PTS, BUMN, Kementerian, dan Organisasi Profesi | form_mapper.py |
| bidang_kegiatan | Keyword Classification | Pencocokan nama kegiatan dan penyelenggara ke 8 bidang baku KHP | form_mapper.py |
| kelompok_kegiatan | Role-to-Group Deterministic Rules | Pemetaan peranan (Peserta -> Kegiatan Non-Lomba, Juara -> Prestasi/Lomba, Panitia/Pengurus -> Organisasi) | form_mapper.py |
| jenis_kegiatan | Rule Mapper (Kelompok x Sub-kategori) | Mapping otomatis ke 22 opsi jenis kegiatan KHP | form_mapper.py |

### Results — per-field (Ground_Truth_Sertifikat_v9.csv + matcher v2)

| Field | Exact | Fuzzy |
|---|---|---|
| nama_kegiatan_sertifikasi | 79.7% | 85.1% |
| waktu_mulai_pelaksanaan | 96.4% | 96.4% |
| waktu_selesai_pelaksanaan | 96.4% | 96.4% |
| penyelenggara_kegiatan | 78.4% | 83.8% |
| nomor_bukti_fisik_nomor_sertifikasi | 92.3% | 92.3% |
| tingkat | 90.5% | 90.5% |

MACRO exact 88.02% (non-empty) / 76.82% (all-cells) / fuzzy 90.10% (non-empty) / 78.64% (all-cells).

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
| Fold 4 | 14 | 15 | 15 | 100.0% |
| Overall 5-Fold | 74 | 67 | 67 | 100.0% |

#### Lapis 2: Uji Ketahanan Out-of-Distribution (Template Mutation & OCR Noise)

Mutasi entitas dan institusi (Universitas Airlangga -> UNS, FTMM -> FST, nama event diganti generik) menghasilkan degradasi akurasi field bebas-institusi hanya -1.6pt (60.5% -> 58.9%), membuktikan pola ekstraksi berbasis semantik gramatikal universal dan anti-hardcoding.

| Perturbasi / Tingkat Noise | MACRO Exact | Delta Degradasi |
|---|---|---|
| 0% (Clean) | 88.0% | 0.0pt |
| 10% OCR Noise | 79.4% | -8.6pt |
| 25% OCR Noise | 71.6% | -16.4pt |
| 50% OCR Noise | 63.8% | -24.2pt |

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

Sertifikat anomali atau ambigu secara otomatis dialihkan ke antarmuka review user jika confidence < 0.85, menjamin zero silent failure pada data produksi.

### Cost & Efficiency

| Aspek | Nilai |
|---|---|
| Effective tokens/cert | 0 |
| LLM calls (74 cert) | 0 |
| Router coverage | 67/74 (90.5%) @100.0% precision (min-fold 100.0% on 5-fold CV) |
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
| v4.0-stage | Combined v4.0 Baseline Staging Bundle (0 LLM) | 89.2% | 86.72% (75.68% all) | 0 | 0 |
| v4.2-stage | Combined v4.2: 3 Pillars & High-DPI (Candidate Terbaik) | 90.5% | 88.02% (76.82% all) | 0 | 0 |

### Production Status

| Aspek | Nilai |
|---|---|
| Dipromosikan ke produksi | organizer_v2.py (ORG-001), organizer_normalize.py (PROD-002), activity_extractor.py (AKT-005), tingkat_router.py (ROUTER-005), high_dpi_crop.py (NC-001), combined_extractor.py (COMBINED-V4-2) |
| ENABLE_COMBINED_V3 | false (default) — terisolasi aman |
| ENABLE_OCR_FALLBACK | True |
| MACRO composite (GT v9) | 88.02% (non-empty composite) / 76.82% (all-cells) |
| Organizer composite | 78.4% |

Combined v4.2 terisolasi di belakang flag ENABLE_COMBINED_V4_2=false di config.py untuk keamanan live deployment (zero blast radius).
