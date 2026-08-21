# HYB-LLM Pipeline

*Certificate Autofill Prototype — Best Pipeline with LLM*

## HYB-LLM Pipeline

Hybrid pipeline dengan LLM fallback untuk 26 cert unrouted. Gabungan terbaik dari semua improvements: router rules (tingkat), AKT-005 (nama kegiatan), ORG-004 (organizer), PROD-002 (nomor).

### Overview

| Aspek | Nilai |
|---|---|
| Versi | HYB-LLM (supersedes HYB-COMBINED) |
| Model LLM | llama3.1:8b (Ollama, Q4_K_M) |
| Dataset | 74 sertifikat mahasiswa (Universitas Airlangga) |
| Ground Truth | Ground_Truth_Sertifikat_v9.csv |
| Matcher evaluasi | v2 (abbr subsequence + rasio kata, anti false-positive) |
| Run benchmark | tests/benchmark_runs/hyb_llm_20260821_135619 |

### Results — per-field

| Field | Exact | Fuzzy |
|---|---|---|
| nama_kegiatan_sertifikasi | 62.2% | 81.1% |
| waktu_mulai_pelaksanaan | 81.8% | 81.8% |
| waktu_selesai_pelaksanaan | 81.8% | 81.8% |
| penyelenggara_kegiatan | 63.5% | 78.4% |
| nomor_bukti_fisik_nomor_sertifikasi | 76.9% | 76.9% |
| tingkat | 83.8% | 83.8% |
| MACRO | 74.2% | 80.7% |

### Router + LLM Stats

| Metrik | Nilai |
|---|---|
| Router coverage | 48/74 @100% precision |
| Unrouted (need LLM) | 26 |
| LLM correct | 17/26 (65.4%) |
| LLM wrong | 9 |
| LLM time | 38.2s total, 1.5s/cert |
| Tokens/cert | ~176 (untuk 26 cert unrouted) |
| Total LLM calls | 26 |

### Comparison with Previous Pipelines

| Pipeline | MACRO | Tingkat | LLM Calls | Status |
|---|---|---|---|---|
| v9 (baseline) | 60.2% | 83.8% | 29 | Old winner |
| HYB-COMBINED (offline) | 73.7% | 81.1% | 0 | Best offline |
| HYB-LLM (this) | 74.2% | 83.8% | 26 | NEW WINNER |

### Pipeline Flow

| Stage | Komponen | Peran |
|---|---|---|
| 1 | Text Extraction | PyMuPDF + Docling + OCR (RapidOCR+Tesseract) |
| 2 | Field Extraction | Regex: tanggal, role, nomor |
| 3 | Organizer v2 + Normalization | ORG-001 + ORG-004 canonical format |
| 4 | Activity Detection v5 | AKT-005: 16+ anchor patterns (62.2% exact) |
| 5 | Form Mapping | Mapping ke form KHP + needs_review |
| 6 | Tingkat Router | 15 rules (48/74 @100% precision) |
| 7 | LLM Tingkat (fallback) | Ollama llama3.1:8b untuk 26 cert unrouted |
| 8 | Persistence | PostgreSQL + needs_review flag |

### Router Rules (15 rules, 48/74 @100%)

| Rule | Signals | Decision |
|---|---|---|
| tingkat_nasional | TINGKAT NASIONAL / LOMBA NASIONAL eksplisit | Nasional |
| lomba+org | lomba dan (hima | univ | nasw | luar | fak | bem) | Nasional |
| lomba_merged+org | kata tergabung OCR (CUP/academicweeks) | Nasional |
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

### Field Extraction Methods

| Field | Method | Akurasi |
|---|---|---|
| nama_kegiatan | AKT-005: 16+ anchor patterns, collapse all-caps, repair OCR-merge | 62.2% |
| tanggal_mulai/selesai | Regex 5-tier + alias bulan OCR | 81.8% |
| penyelenggara | ORG-004: organizer_v2 + normalize + canonical format | 63.5% |
| nomor | Regex 4 pola + fallback raw text (ORG-002) | 76.9% |
| tingkat | Router 15 rules + LLM fallback (llama3.1:8b) | 83.8% |

### LLM Configuration

| Parameter | Nilai |
|---|---|
| Model | llama3.1:8b |
| Prompt | Tentukan TINGKAT KEGIATAN (dengan aturan BEM/HIMA/UNIV/Nasional) |
| Temperature | 0 |
| Num predict | 30 |
| Budget teks | 140/200/300 char (strong/normal/poor OCR) |
| Context fields | nama_kegiatan, penyelenggara, peran |
| Host | http://127.0.0.1:11434 |

### Production Status

| Aspek | Status |
|---|---|
| Dipromosikan | organizer_v2.py, tingkat_router.py |
| Belum dipromosikan | AKT-005 activity detection, ORG-004 normalization |
| ENABLE_LLM_TINGKAT | false (default) — produksi deterministik |
| ENABLE_ORGANIZER_NORMALIZATION | false (keputusan user) |

HYB-LLM = pipeline terbaik saat ini (MACRO 74.2%). Offline mode (HYB-COMBINED, 73.7%) sudah sangat bagus tanpa LLM. LLM hanya menambah +0.5pp dengan 26 calls.
