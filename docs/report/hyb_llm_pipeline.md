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

Router menentukan tingkat berdasarkan sinyal teks (regex) dan organizer. 15 rules tervalidasi @100% precision di 74 sertifikat.

#### Signal Extraction (_sig function)

Fungsi _sig() mengekstrak sinyal dari teks dan organizer menggunakan regex. Return dict dengan keys: lomba, lomba_merged, hima, hima_org, dept, univ, luar, nasw, nasw_explicit, sem, fak, bem.

Contoh regex untuk deteksi sinyal:

- lomba: r'\bLOMBA\b|\bKOMPETISI\b|\bCOMPETITION\b|\bOLIMPIADE\b|\bCHALLENGE\b|\bTOURNAMENT\b|\bJUARA\b|\bCUP\b|\bCHAMPIONSHIP\b|\bHACKATHON\b'
- lomba_merged: kata tergabung OCR (CUP/academicweeks) tanpa spasi — menangkap 'ACADEMICWEEKS2026', 'INFographicCompetition'
- hima: r'HIMPUNAN|HIMA' di organizer + r'\bHIMA\b|(?<![A-Z])HIMA(?=[A-Z0-9])|HIMPUNAN' di raw_text
- dept: r'\bDEPT\b|DEPARTMENT|STUDY\s*PROGRAM|\bPRODI\b|PROGRAM STUDI' di teks/organizer
- univ: r'UNIVERSITAS|UNIVERSITY|REKTORAT|DIREKTORAT|KEMAHASISWAAN' di organizer
- luar: r'AIESEC|UNIMUS|UNISBA|UNS|UGM|IPB|BRAWIJAYA|BINUS|UNY|UNESA' (daftar kampus eksternal)
- nasw: r'\bNASIONAL\b|\bNATIONAL\b' di teks
- nasw_explicit: r'TINGKAT\s+NASIONAL|LOMBA\s+NASIONAL' — teks eksplisit
- sem: r'\bSEMINAR\b|\bWORKSHOP\b|\bWEBINAR\b|\bGUEST LECTURE\b|\bTALKSHOW\b'
- fak: r'FAKULTAS|FACULTY' di organizer
- bem: r'\bBEM\b' di organizer + r'\bBEM\b|(?<![A-Z])BEM(?=[A-Z0-9])' di raw_text

#### Decision Rules (_decide function)

Rule dipanggil berurutan. Rule pertama yang match = keputusan. None = route ke LLM.

Contoh code decision:

- tingkat_nasional: if s['nasw_explicit'] → 'Nasional'
-   Regex: r'TINGKAT\s+NASIONAL|LOMBA\s+NASIONAL'
- 
- lomba+org: if s['lomba'] and (hima|univ|nasw|luar|fak|bem) → 'Nasional'
-   Regex: r'\bLOMBA\b|\bKOMPETISI\b|\bCOMPETITION\b' AND (hima OR univ OR nasw OR luar OR fak OR bem)
- 
- lomba_merged+org: if s['lomba_merged'] and (hima|univ|fak|bem) → 'Nasional'
-   Untuk kata tergabung OCR: 'ACADEMICWEEKS2026', 'INFographicCompetition'
- 
- dept+sem: if s['dept'] and s['sem'] and not lomba and not nasw → 'Departemen/Program Studi'
-   Regex: r'\bDEPT\b|DEPARTMENT' AND r'\bSEMINAR\b|\bWORKSHOP\b'
- 
- hima+luar: if s['hima'] and s['luar'] → 'Nasional'
-   HIMA dari organizer + kampus eksternal (UGM, BINUS, etc)
- 
- univ+luar: if s['univ'] and s['luar'] and not fak → 'Nasional'
-   Universitas + kampus eksternal, tanpa fakultas
- 
- dept+fak: if s['dept'] and s['fak'] → 'Departemen/Program Studi'
-   Departemen/Prodi + Fakultas = tingkat fakultas
- 
- fak+univ: if s['fak'] and s['univ'] and not sem/nasw/lomba → 'Fakultas'
-   Fakultas + Universitas, tanpa seminar/lomba
- 
- bem+sem: if s['bem'] and s['sem'] and not lomba/hima/nasw → 'Fakultas'
-   BEM + seminar/workshop = tingkat fakultas
- 
- bem_no_univ: if s['bem'] and not univ/sem/lomba/nasw/luar/hima → 'Fakultas'
-   BEM tanpa konteks universitas = tingkat fakultas
- 
- bem+hima: if s['bem'] and s['hima'] and not lomba/nasw/luar → 'Fakultas'
-   BEM + HIMA partnership = tingkat fakultas
- 
- sem+univ: if s['sem'] and s['univ'] and not fak/bem/hima/lomba → 'Universitas'
-   Seminar + Universitas (bukan fakultas) = tingkat universitas

#### Contoh Kasus

Sertifikat: 'LOMBA CIKAL 2024' + Organizer: 'Himpunan Mahasiswa Teknik'

- Signal: lomba=True, hima=True, univ=False, fak=False, bem=False
- Rule: lomba+org (lomba AND hima)
- Decision: Nasional

Sertifikat: 'Guest Lecture by BEM FTMM' + Organizer: 'BEM Fakultas Teknologi Multidisiplin'

- Signal: bem=True, sem=True (guest lecture), lomba=False, hima=False
- Rule: bem+sem (bem AND sem, NOT lomba)
- Decision: Fakultas

Sertifikat: 'Seminar Nasional Data Science' + Organizer: 'Universitas Airlangga'

- Signal: sem=True, nasw=True, univ=True, fak=False, bem=False
- Rule: TIDAK ADA RULE MATCH (sem+univ BUT nasw=True → guard violated)
- Decision: None → route ke LLM

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
