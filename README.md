# Certificate Autofill Prototype

Prototype sistem ekstraksi PDF sertifikat mahasiswa dan autofill form Kartu Hasil Prestasi (KHP) terintegrasi taksonomi resmi universitas.

**Stack & Arsitektur Utama:**
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL 17
- **Text & OCR Engine:** PyMuPDF (fast text) + Tesseract OCR Multi-PSM + RapidOCR
- **Persepsi Semantik (LLM):** Google Gemini (`gemini-3.1-flash-lite`) untuk ekstraksi fakta teks sertifikat dan penentuan tingkat cakupan
- **Resolver Deterministik KHP:** Modul Python deterministik untuk autofill 9-field KHP yang memetakan hasil ekstraksi ke taksonomi resmi kemahasiswaan universitas (normalisasi tingkat, peran/prestasi, dan pengelompokan kegiatan resmi)
- **Antarmuka Form KHP:** Vanilla HTML/CSS/JS dengan UI Cascading Filter dinamis dan Modal Pencarian Master Kegiatan
- **Ekstraksi Offline (Fallback):** Combined v4.2 (Sistem aturan struktural lokal tanpa cloud API)
- **Monitoring:** Prometheus + Grafana + Loki

---

## Cara Menjalankan

### 1. Konfigurasi Awal (Environment Variables)

Sebelum menyalakan aplikasi, buat file konfigurasi `.env` dari template:

```bash
cp .env.example .env
```

```bash
GOOGLE_API_KEY=""  # Masukkan kunci Google AI Studio API Anda
```

> 🛡️ **Graceful Fallback (Anti Error 500)**:
> Jika `GOOGLE_API_KEY` dikosongkan, kuota habis (HTTP 429), atau koneksi internet terputus, sistem secara otomatis beralih (*graceful fallback*) ke pipeline offline (Combined v4.2) tanpa memicu crash atau HTTP 500.

---

### 2. Menjalankan via Docker Compose

Perintah default menyalakan backend FastAPI dan PostgreSQL 17:

```bash
docker compose up --build
```

Untuk menyalakan Prometheus, Grafana, dan Loki, gunakan profile `monitoring`:

```bash
docker compose --profile monitoring up --build
```

Setelah container aktif:
| Service | URL | Keterangan |
|---|---|---|
| **FastAPI Web & Form** | `http://localhost:8000` | Antarmuka web form KHP + Swagger API docs (`/docs`) |
| **PostgreSQL 17** | `localhost:5434` | Database (`certautofill`, user: `postgres`, pass: `postgres`) |
| **Prometheus** | `http://localhost:9090` | Aktif dengan profile `monitoring` |
| **Grafana** | `http://localhost:3000` | Aktif dengan profile `monitoring` (`admin:admin`) |
| **Loki** | `http://localhost:3100` | Aktif dengan profile `monitoring` |

> Variabel `GOOGLE_API_KEY` dari file `.env` Anda akan otomatis diteruskan ke container backend oleh Docker Compose.

---

### 3. Menjalankan secara Manual (Tanpa Docker)

#### Prasyarat:
1. PostgreSQL 17 aktif di port `5434` dengan database `certautofill`.
2. Tesseract OCR (`tesseract-ocr` dan `tesseract-ocr-ind`) terpasang di sistem operasi.

#### Linux / macOS:
```bash
export APP_ENV=development
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
export PROCESSING_MODE=background
export ENABLE_TESSERACT_GEMINI=true
export ENABLE_KHP_MASTER_STAGING=true
export ENABLE_COMBINED_V4_2=true
export GOOGLE_API_KEY=""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Windows (PowerShell):
```powershell
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:ENABLE_TESSERACT_GEMINI="true"
$env:ENABLE_KHP_MASTER_STAGING="true"
$env:ENABLE_COMBINED_V4_2="true"
$env:GOOGLE_API_KEY=""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### 4. Frontend Standalone (Opsional)
Buka `frontend/index.html` langsung di browser, atau gunakan Python HTTP server:
```bash
cd frontend && python -m http.server 5173
```

---

## Konfigurasi Pipeline & Mode Ekstraksi

Pipeline ekstraksi dapat disesuaikan melalui environment variable di file `.env`:

| Variabel | Nilai Default | Deskripsi |
|---|:---:|---|
| `ENABLE_TESSERACT_GEMINI` | `true` | Mengaktifkan ekstraksi langsung teks OCR ke Google Gemini dengan prompt V2 Scope-Aware |
| `GOOGLE_API_KEY` | *(kosong)* | Kunci Google AI Studio API Anda |
| `GOOGLE_GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model Gemini yang digunakan (`gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`, `gemini-2.5-flash`) |
| `GEMINI_TIMEOUT_SECONDS` | `30.0` | Batas waktu timeout pemanggilan API Gemini sebelum fallback |
| `ENABLE_KHP_MASTER_STAGING` | `true` | Mengaktifkan resolusi master data resmi universitas, autofill 9-field KHP, dan UI cascading filter |
| `ENABLE_COMBINED_V4_2` | `true` | Pipeline offline rule-based resmi saat Gemini tidak aktif atau kuota habis |
| `PROCESSING_MODE` | `background` | Mode eksekusi job (`background`: FastAPI BackgroundTasks, `sync`: langsung, `db_worker`: polling DB) |
| `UPLOAD_TEMP_DIR` | `/tmp/cert_uploads` | Direktori PDF sementara, izin direktori `0o700` dan file `0o600` |
| `TEMP_FILE_TTL_HOURS` | `1` | Batas umur PDF tanpa job aktif sebelum dihapus |
| `JOB_LEASE_SECONDS` | `900` | Batas kerja eksklusif satu worker untuk satu job |
| `STORAGE_CLEANUP_INTERVAL_SECONDS` | `300` | Jeda cleanup file yatim dan job lease kedaluwarsa |

### Storage Sementara dan Manajemen File
PDF hanya berada sementara di `UPLOAD_TEMP_DIR`; database PostgreSQL hanya menyimpan metadata teks dan hasil ekstraksi form, bukan data bytes PDF atau file OCR mentah.

Untuk pemeliharaan storage atau database lama:
```bash
uv run python scripts/migrate_ephemeral_storage.py
```

### Ingin Berjalan 100% Offline Tanpa Cloud API?
Cukup ubah baris berikut di `.env`:
```bash
ENABLE_TESSERACT_GEMINI=false
```
Sistem akan otomatis menggunakan pipeline offline rule-based lokal.

---

## Hasil Evaluasi & Benchmark

### 1. Evaluasi Terpadu Master Data KHP 9-Field (Dataset Terpadu $N=104$)
Evaluasi pipeline terintegrasi (Gemini V2 Scope-Aware + Resolver Deterministik Taksonomi Universitas) pada 104 sertifikat terverifikasi:

| Dimensi Evaluasi | Exact Match (%) | Fuzzy / Overlap (%) | Detail Capaian | Status / Keterangan |
|---|:---:|:---:|:---:|---|
| **Master 3-Field (Taksonomi Universitas)** | **80.77%** | **80.77%** | 252/312 sel | **+63 sel bersih (+20.19pt)** vs baseline awal; zero loss |
| **All-Cells 9-Field (End-to-End KHP)** | **73.08%** | **78.42%** | 684/936 sel | 6 fakta sertifikat + 3 taksonomi master database |
| **Base 6-Field Ekstraksi Faktual** | **69.23%** | **77.40%** | 432/624 sel | Kestabilan penuh pada field literal sertifikat |
| **Pencocokan Tuple Resmi Database** | **91.35%** | — | **95 / 104 Dokumen** | 95 sertifikat terpetakan otomatis ke ID resmi kegiatan tanpa review |
| **Safety Net Review Manual** | **8.65%** | — | 9 / 104 Dokumen | Hanya memicu review manual pada noise OCR ekstrem atau kombinasi belum terdaftar |

*Catatan: Resolusi master mencakup penyempurnaan deteksi minat-bakat dan varian kata kunci kompetisi.*

---

### 2. Riwayat Evaluasi Eksperimen Prompting LLM (Dataset Terpadu $N=104$)
Ringkasan perjalanan eksperimen teknik prompting LLM dari baseline awal hingga arsitektur final:

| Strategi / Arsitektur Prompt | Akurasi Tingkat | All-Cells (Exact) | Token / Doc | Estimasi Biaya / Doc | Status & Temuan Kunci |
|---|:---:|:---:|:---:|:---:|---|
| **V1 Baseline Produksi** | 61.54% | 62.50% | 1.463,5 tok | Rp 9,95 | Baseline awal. Rentan bias hierarki penyelenggara (13 event nasional salah ditebak menjadi fakultas). |
| **V2 Scope-Aware (Pilihan Standar)** | **82.69% (+21.15pt)** | **65.71% (+3.21pt)** | 1.576,2 tok | Rp 10,44 | **Winner Persepsi**. Prinsip eksplisit: *Cakupan Sasaran Peserta > Jenjang Penyelenggara*. Memangkas bias hierarki ke 5 kasus. |
| **V3 Decoupled 2-Stage** | 76.92% | 64.90% | 1.409,7 tok | Rp 9,77 (2 calls) | Pemisahan ekstraksi literal (Stage 1) dan tingkat CoT (Stage 2). Akurasi tingkat berada 5.77pt di bawah V2 dan butuh 2 panggilan API. |
| **V4 In-JSON Scope Signal** | 77.88% (-4.81pt) | 65.22% | 1.650,6 tok | Rp 11,16 | Pembatasan enum sinyal perantara membuat model over-konservatif; 56.73% dokumen jatuh ke internal kampus. |
| **V5 Natural Rationale Buffer** | 80.77% (-1.92pt) | 64.58% | 1.775,5 tok | Rp 12,57 | Menuliskan unit penyelenggara di awal buffer penalaran menginduksi bias atensi berurutan dan mendegradasi salinan teks literal. |
| **Web Search Grounding** | 77.66% (-4.26pt) | N/A | 1.723,2 tok | Rp 197,87 | Web search menimbulkan false positive pada artikel fakultas induk, latensi naik 3×, dan biaya membengkak ~19× lipat. |
| **Injeksi Enum Master ke Prompt** | 52.88% (-29.81pt) | 60.26% | 1.130,0 tok | Rp 8,50 | **Katastropik**. Memaksa LLM memilih 13 enum master resmi merusak penalaran. Keputusan: serahkan taksonomi ke resolver Python. |

---

### 3. Pipeline Ekstraksi Utama & Model Cloud LLM (Dataset Evaluasi $N=74$)
Evaluasi ekstraksi persepsi 6-field pada 74 teks sertifikat:

| Pipeline / Model | MACRO Exact (All-Cells) | Framework Exact (5 Field) | Akurasi Tingkat | Biaya / Dokumen | Rata-rata Latensi | Status / Keterangan |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Production Conditional + Gemini 3.1 Flash-Lite (V2 Scope-Aware)** | **70.27%** | **80.65%** | **83.78%** | **Rp10,40** | **1.89s** | **Arsitektur Persepsi Standar**. Menghilangkan bias hierarki penyelenggara. |
| Production Conditional + Gemini Baseline V1 | 67.12% | 81.29% | 62.16% | Rp10,40 | 1.89s | Baseline awal (terdistraksi bias kepanitiaan fakultas) |
| Direct Gemini 2.5 Flash-Lite | 58.78% | 71.05% | 43.20% | **Rp3,26** | 1.32s | Biaya termurah, akurasi tingkat lebih rendah |
| Direct Gemini 2.5 Flash | 58.56% | 71.38% | 51.35% | Rp38,94 | 4.62s | Latensi lambat dan biaya 4x lipat tanpa peningkatan akurasi |

---

### 4. Pipeline Offline Rule-Based Composite v4.x (Fallback Resmi — 0 LLM)
Ekstraksi lokal deterministik tanpa ketergantungan API eksternal (100% offline):

| Pipeline / Versi | MACRO Exact (All-Cells) | Framework Exact (5 Field) | MACRO Fuzzy | LLM Calls | Sifat / Arsitektur |
|---|:---:|:---:|:---:|:---:|---|
| **Combined v4.2 / Composite B8** | **76.13%** | **87.42%** | **78.64%** | **0** | **Best Offline Fallback**. 3 pilar OOD + High-DPI crop zoom 6.0×. |
| Combined v3 | 74.20% | 85.70%* | 88.30% | 0 | 5 branch composite (basis 384 sel non-empty) |
| Combined v2 | 74.20% | 80.70% | 80.70% | 0 | Port integrasi rule router v5 |
| Regex Baseline Legacy (v2) | 42.20% | — | — | 0 | Baseline regex awal historis |

---

### 5. Perbandingan Rekognisi Teks & OCR Engine
Evaluasi pembentukan teks input terhadap 74 dokumen sertifikat (49 pindaian/scan + 25 digital murni):

| Engine / Strategi OCR | MACRO Exact (All-Cells) | Framework Exact | Kinerja Pindaian (Scan-49) | Kinerja Digital (Emb-25) | Status Evaluasi |
|---|:---:|:---:|:---:|:---:|---|
| **Production Conditional (PyMuPDF + RapidOCR)** | **67.57%** | **81.29%** | **65.31%** | **72.00%** | **Pemenang Produksi**. Mencegah derau OCR pada PDF digital murni. |
| Tesseract Standalone Multi-PSM | 68.47% | 77.10% | 78.61% (nomor 87.88%) | 74.31% | Alternatif tangguh bila layer teks digital rusak |
| RapidOCR + Tesseract murni | 66.89% | 80.00% | 66.33% | 68.00% | Degradasi -4.0pt pada PDF digital akibat derau OCR |
| Tesseract OCR murni | 65.77% | 78.71% | 64.63% | 68.00% | Stabil pada pindaian, rentan pada font dekoratif digital |
| RapidOCR murni | 63.06% | 75.16% | 61.22% | 66.67% | Kecepatan tinggi namun akurasi nomor lebih rendah |
| PyMuPDF murni (Tanpa OCR) | 27.70% | 33.23% | 9.18% (collapse) | 64.00% | Gagal membaca dokumen scan tanpa layer teks |

---

### 6. Arsip Eksperimen Model Named Entity Recognition (Tidak Dipakai Pipeline)
Evaluasi token classification supervised pada 74 teks korpus OCR Tesseract (310 sel framework non-empty):

| Arsitektur / Model NER | Framework Exact | Framework Fuzzy | Ketahanan OOD Mutasi | Keterangan & Batasan |
|---|:---:|:---:|:---:|---|
| IndoBERT-ner-gold Fine-Tuned | 44.52% | 57.10% | -4.2pt drop | Monolingual Indonesia 334M, 5-Fold Stratified OOF |
| XLM-RoBERTa Large Fine-Tuned | 43.55% | 55.48% | -5.8pt drop | Multilingual 560M, kebutuhan VRAM tinggi (7.1 GB) |
| mDeBERTa-v3-base Fine-Tuned | 34.84% | 51.29% | -7.1pt drop | Multilingual 86M, representasi entitas Indonesia kurang optimal |
| IndoBERT Pre-trained v1 (Zero-Shot) | 12.80% | 24.50% | — | Baseline tanpa penyesuaian domain sertifikat |

> Eksperimen NER pada bagian ini hanya arsip. Pipeline aktif memakai Tesseract sebagai sumber OCR dan extractor produksi; GLiNER serta model NER tidak dipanggil.

---

### Penjelasan Metrik & Formula Evaluasi

Evaluasi menggunakan formula standar baku:

1. **MACRO Exact Match**:
   Mengukur persentase prediksi yang cocok persis 100% terhadap Ground Truth setelah normalisasi kanonikal:
   $$\text{Exact Match} = \frac{1}{N} \sum_{i=1}^{N} \mathbf{1}(\text{Prediksi}_i = \text{GroundTruth}_i)$$

2. **Fuzzy Match (Threshold $\ge 0.75$)**:
   Memberikan toleransi kecocokan semantik untuk akronim resmi organisasi dan substring relevan nama kegiatan.

3. **Perbedaan Basis Evaluasi: Framework vs All-Cells**:
   - **Framework (5 Field)**: Menghitung akurasi hanya pada 5 field inti (*nama kegiatan, nomor sertifikat, penyelenggara, tanggal mulai, tanggal selesai*) yang memiliki target data non-kosong.
   - **All-Cells (6 Field / 9 Field)**: Menghitung akurasi seluruh field form KHP secara end-to-end (termasuk tingkat dan taksonomi master kegiatan), memperhitungkan penalti jika sistem mengisi nilai pada field yang seharusnya kosong.

---

## Pengujian Sistem

Jalankan pengujian unit dan verifikasi fungsionalitas dengan:

```bash
uv run pytest tests/ -v
```

---

## Endpoint API Utama

```http
POST /api/documents              # Upload dokumen PDF sertifikat → pemrosesan ekstraksi di background
GET  /api/documents/{id}/result  # Ambil status job dan hasil ekstraksi 9-field form KHP
GET  /api/options                # Opsi dropdown master data KHP berelasi (Kelompok Kegiatan berelasi dengan Jenis Kegiatan, Tingkat, Jabatan)
GET  /api/master/activities      # Katalog pencarian taksonomi kegiatan resmi universitas untuk UI Modal
GET  /metrics                    # Metrik Prometheus (ekstraksi, latensi, error rate)
GET  /healthz                    # Health check endpoint
```

---

## Dokumentasi Terkait

| Dokumen / Antarmuka | Deskripsi |
|---|---|
| [Swagger API Documentation](/docs) | Dokumentasi interaktif OpenAPI untuk pengujian endpoint upload dan status ekstraksi (`/docs`) |
| [ReDoc API Documentation](/redoc) | Dokumentasi alternatif ReDoc untuk spesifikasi skema data API |
| [Frontend Guide](frontend/README_FRONTEND.md) | Panduan antarmuka web, penanganan cascading dropdown, dan modal pencarian kegiatan |
