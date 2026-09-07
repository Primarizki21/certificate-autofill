# Certificate Autofill Prototype

Prototype internal — ekstraksi PDF sertifikat mahasiswa dan autofill form Kartu Hasil Prestasi (KHP).

**Stack Utama:**
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL 17
- **Text & OCR:** PyMuPDF (fast text) + Tesseract OCR + RapidOCR
- **Ekstraksi Semantik (Default):** Google Gemini (`gemini-3.1-flash-lite`) via Direct Tesseract-to-Gemini REST API
- **Ekstraksi Offline (Fallback):** Combined v4.2 (Structural Semantic Rules + High-DPI Region Crop)
- **Monitoring:** Prometheus + Grafana + Loki

Lihat [AGENTS.md](AGENTS.md) untuk arsitektur mendalam, konvensi teknis, dan panduan kontribusi tim.

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

### 2. Menjalankan via Docker Compose (Full Stack — Rekomendasi)

Docker Compose akan menjalankan backend FastAPI, PostgreSQL 17, Prometheus, Grafana, dan Loki secara terpadu.

```bash
docker compose up --build
```

Setelah container aktif:
| Service | URL | Keterangan |
|---------|-----|------------|
| **FastAPI Web & Form** | `http://localhost:8000` | Antarmuka web form KHP + Swagger API docs (`/docs`) |
| **PostgreSQL 17** | `localhost:5434` | Database (`certautofill`, user: `postgres`, pass: `postgres`) |
| **Prometheus** | `http://localhost:9090` | Metrik sistem dan performa pipeline |
| **Grafana** | `http://localhost:3000` | Dashboard visualisasi (`admin:admin`) |
| **Loki** | `http://localhost:3100` | Agregator log sistem |

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
export GOOGLE_API_KEY=""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Windows (PowerShell):
```powershell
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:ENABLE_TESSERACT_GEMINI="true"
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
|----------|---------------|-----------|
| `ENABLE_TESSERACT_GEMINI` | `true` | Mengaktifkan ekstraksi langsung teks OCR ke Google Gemini |
| `GOOGLE_API_KEY` | *(kosong)* | Kunci Google AI Studio API Anda |
| `GOOGLE_GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model Gemini yang digunakan (`gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`, `gemini-2.5-flash`) |
| `GEMINI_TIMEOUT_SECONDS` | `30.0` | Batas waktu timeout pemanggilan API Gemini sebelum fallback |
| `PROCESSING_MODE` | `background` | Mode eksekusi job (`background`: FastAPI BackgroundTasks, `sync`: langsung, `db_worker`: polling DB) |
| `ENABLE_COMBINED_V4_2` | `false` | Mengaktifkan pipeline staging offline v4.2 saat Gemini dinonaktifkan |

### Ingin Berjalan 100% Offline Tanpa Cloud API?
Cukup ubah baris berikut di `.env`:
```bash
ENABLE_TESSERACT_GEMINI=false
```
Sistem akan otomatis menggunakan pipeline offline rule-based lokal.

---

## Hasil Evaluasi & Benchmark (Dataset 74 Sertifikat, Evaluator Frozen Matcher v2)

### 1. Pipeline Ekstraksi Utama & Model Cloud LLM
Evaluasi pada 74 teks sertifikat (sumber asli gabungan digital dan pindaian raster):

| Pipeline / Model | MACRO Exact (All-Cells) | Framework Exact (5 Field) | MACRO Fuzzy | Biaya / Dokumen | Rata-rata Latensi | Status / Keterangan |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Production Conditional + Gemini 3.1 Flash-Lite** | **67.57%** | **81.29%** | **75.68%** | **Rp9,50** ($0.0005) | **1.36s** | **Produksi Aktif** (`PROD-INPUT-MATRIX-001` / `PROD-GEMINI-001/002`). Pemenang akurasi semantik. |
| Direct Gemini 2.5 Flash-Lite | 58.78% | 71.05% | 66.44% | **Rp3,26** ($0.00018) | 1.32s | Biaya termurah, akurasi tingkat lebih rendah (43.2%) |
| Direct Gemini 2.5 Flash | 58.56% | 71.38% | 71.40% | Rp38,94 ($0.0022) | 4.62s | Latensi lambat dan biaya 4x lipat tanpa peningkatan akurasi |

### 2. Pipeline Offline Rule-Based Composite v4.x (Staging / Fallback — 0 LLM)
Ekstraksi lokal deterministik tanpa ketergantungan API eksternal (100% offline):

| Pipeline / Versi | MACRO Exact (All-Cells) | Framework Exact (5 Field) | MACRO Fuzzy | LLM Calls | Sifat / Arsitektur |
|---|:---:|:---:|:---:|:---:|---|
| **Combined v4.2 / Composite B8** | **76.13%** | **87.42%** | **78.64%** | **0** | **Best Offline Staging** (`EXP-V4-003` / `B8-COMPOSITE-001`). 3 pilar OOD + High-DPI crop zoom 6.0×. |
| Combined v3 (`COMBINED-V3-001`) | 74.20% | 85.70%* | 88.30% | 0 | 5 branch composite (basis 384 sel non-empty) |
| Combined v2 (`COMBINED-V2-001`) | 74.20% | 80.70% | 80.70% | 0 | Dummy port integrasi rule router v5 |
| Regex Baseline Legacy (v2) | 42.20% | — | — | 0 | Baseline regex awal historis |

### 3. Perbandingan Rekognisi Teks & OCR Engine
Evaluasi pembentukan teks input terhadap 74 dokumen sertifikat (49 pindaian/scan + 25 digital murni):

| Engine / Strategi OCR | MACRO Exact (All-Cells) | Framework Exact | Kinerja Pindaian (Scan-49) | Kinerja Digital (Emb-25) | Status Evaluasi |
|---|:---:|:---:|:---:|:---:|---|
| **Production Conditional (PyMuPDF + RapidOCR)** | **67.57%** | **81.29%** | **65.31%** | **72.00%** | **Pemenang Produksi** (`PROD-INPUT-MATRIX-001`). Mencegah derau OCR pada PDF digital murni. |
| Tesseract Standalone Multi-PSM (`OCR-TESS-V4-001`) | 68.47% | 77.10% | 78.61% (nomor 87.88%) | 74.31% | Alternatif tangguh bila layer teks digital rusak |
| RapidOCR + Tesseract murni | 66.89% | 80.00% | 66.33% | 68.00% | Degradasi -4.0pt pada PDF digital akibat derau OCR |
| Tesseract OCR murni | 65.77% | 78.71% | 64.63% | 68.00% | Stabil pada pindaian, rentan pada font dekoratif digital |
| RapidOCR murni | 63.06% | 75.16% | 61.22% | 66.67% | Kecepatan tinggi namun akurasi nomor lebih rendah |
| PyMuPDF murni (Tanpa OCR) | 27.70% | 33.23% | 9.18% (collapse) | 64.00% | Gagal membaca dokumen scan tanpa layer teks |
| Engine Lain (DocTR, LFM2.5-VL, Docling, PaddleOCR) | Gagal Gate | Gagal Gate | — | — | **Closed** di *ledger* (faktor kegagalan nomor, latensi ekstrem >70s, atau memory overhead) |

### 4. Perbandingan Model Named Entity Recognition (NER)
Evaluasi token classification supervised pada 74 teks korpus OCR Tesseract (310 sel framework non-empty):

| Arsitektur / Model NER | Framework Exact | Framework Fuzzy | Ketahanan OOD Mutasi | Keterangan & Batasan |
|---|:---:|:---:|:---:|---|
| **GLiNER v2.1 Multilingual Fine-Tuned** (`NER-GLINER-002`) | **54.52%** | **63.23%** | **0.00pt drop (Kebal)** | Model encoder/span terbaik; ekstraksi tanggal (63.6%) dan nomor (55.8%) tinggi |
| IndoBERT-ner-gold Fine-Tuned (`NER-ENCODER-002`) | 44.52% | 57.10% | -4.2pt drop | Monolingual Indonesia 334M, 5-Fold Stratified OOF |
| XLM-RoBERTa Large Fine-Tuned (`NER-ENCODER-001`) | 43.55% | 55.48% | -5.8pt drop | Multilingual 560M, kebutuhan VRAM tinggi (7.1 GB) |
| mDeBERTa-v3-base Fine-Tuned (`NER-ENCODER-001`) | 34.84% | 51.29% | -7.1pt drop | Multilingual 86M, representasi entitas Indonesia kurang optimal |
| IndoBERT Pre-trained v1 (Zero-Shot) | 12.80% | 24.50% | — | Baseline tanpa penyesuaian domain sertifikat |

---

### Penjelasan Metrik & Formula Evaluasi

Evaluasi menggunakan standar baku evaluator beku (*frozen matcher v2* di `tests/matchers.py`) pada Ground Truth v9:

1. **MACRO Exact Match**:
   Mengukur persentase prediksi yang cocok persis 100% terhadap Ground Truth setelah normalisasi kanonikal (pembersihan spasi ganda, kapitalisasi, standarisasi format tanggal ISO `YYYY-MM-DD`, dan pembersihan tanda baca nomor sertifikat):
   $$\text{Exact Match} = \frac{1}{N} \sum_{i=1}^{N} \mathbf{1}(\text{Prediksi}_i = \text{GroundTruth}_i)$$

2. **Fuzzy Match (Threshold $\ge 0.75$)**:
   Memberikan toleransi kecocokan semantik untuk:
   - **Portmanteau & Akronim Resmi**: Deteksi ekspansi organisasi yang sah (contoh: `UNAIR` $\leftrightarrow$ `Universitas Airlangga`, `BEM` $\leftrightarrow$ `Badan Eksekutif Mahasiswa`, `HIMA` $\leftrightarrow$ `Himpunan Mahasiswa`).
   - **Substring Relevan**: Kecocokan nama kegiatan yang mencakup nama inti acara sertifikat.

3. **Perbedaan Basis Evaluasi: Framework vs All-Cells**:
   - **Framework (5 Field, 310 Sel)**: Menghitung akurasi hanya pada 5 field inti (*nama kegiatan, nomor sertifikat, penyelenggara, tanggal mulai, tanggal selesai*) yang memiliki target Ground Truth non-kosong. Digunakan sebagai metrik standar perbandingan model NLP/NER.
   - **All-Cells (6 Field, 444 Sel)**: Menghitung akurasi seluruh 6 field form KHP (termasuk *tingkat*) dan memperhitungkan penalti jika sistem mengisi nilai pada field yang seharusnya kosong. Merupakan representasi akurasi end-to-end produksi.

4. **Character Error Rate (CER) & Word Error Rate (WER)**:
   Mengukur jarak edit Levenshtein antara teks prediksi ($P$) dan referensi ($R$):
   $$\text{CER / WER} = \frac{S + D + I}{N}$$
   di mana $S$ adalah jumlah substitusi karakter/kata, $D$ adalah penghapusan (*deletion*), $I$ adalah penyisipan (*insertion*), dan $N$ adalah panjang total karakter/kata pada teks referensi Ground Truth.

---

## Pengujian Sistem

Jalankan pengujian unit dan verifikasi fungsionalitas dengan:

```bash
pytest tests/ -v
```
---

## Endpoint API Utama

```http
POST /api/documents              # Upload dokumen PDF sertifikat → parsing background
GET  /api/documents/{id}/result  # Ambil status job dan hasil ekstraksi form KHP
GET  /api/options                # Opsi dropdown master data KHP (tingkat, jenis kegiatan, dsb.)
GET  /metrics                    # Metrik Prometheus (ekstraksi, latensi, error rate)
GET  /healthz                    # Health check endpoint
```

---

## Dokumen Referensi

| Dokumen | Deskripsi |
|---|---|
| [AGENTS.md](AGENTS.md) | Konvensi proyek, standar pengujian 4 lapis empiris, dan protokol keamanan rahasia |
| [docs/experiments_ledger.md](docs/experiments_ledger.md) | Rekam jejak seluruh eksperimen aktif maupun tertutup (*closed/failed approaches*) |
| [docs/report/runs_summary.md](docs/report/runs_summary.md) | Rekapitulasi metrik numerik seluruh run eksperimen |
| [docs/report/production_input_matrix.md](docs/report/production_input_matrix.md) | Laporan komparasi empiris 6 varian teks input OCR/PyMuPDF (`PROD-INPUT-MATRIX-001`) |
| [docs/report/gemini_tesseract_benchmark_report.md](docs/report/gemini_tesseract_benchmark_report.md) | Laporan evaluasi model Gemini, pencatatan token, dan tarif resmi (`EXP-LLM-002`) |
| [docs/report/composite_v4_candidate_report.md](docs/report/composite_v4_candidate_report.md) | Laporan teknikal pipeline offline Combined v4.2 / Composite B8 |
| [docs/handoff_v52.md](docs/handoff_v52.md) | Handoff v52: Arsitektur Ephemeral Zero-PDF Storage & Input Matrix Produksi |
