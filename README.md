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

Buka `.env` dan masukkan API Key Google Gemini Anda:
```bash
GOOGLE_API_KEY="AIzaSy..."
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
export GOOGLE_API_KEY="AIzaSy..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Windows (PowerShell):
```powershell
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:ENABLE_TESSERACT_GEMINI="true"
$env:GOOGLE_API_KEY="AIzaSy..."
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

## Hasil Benchmark (Dataset 74 Sertifikat, Evaluator Matcher v2)

| Pipeline / Model | MACRO Exact (6 Field) | MACRO Fuzzy | Rata-rata Biaya / Dokumen | Rata-rata Latensi | Catatan |
|---|:---:|:---:|:---:|:---:|---|
| **Direct Gemini 3.1 Flash-Lite (Produksi Aktif)** | **63.74%** | **72.75%** | **Rp9,50** ($0.0005) | **1.36s** | Cloud LLM terbaik, pemahaman semantik tinggi pada nama kegiatan & penyelenggara |
| Direct Gemini 2.5 Flash-Lite | 58.78% | 66.44% | **Rp3,26** ($0.00018) | 1.32s | Paling murah, tetapi akurasi `tingkat` rendah (43.2%) |
| Direct Gemini 2.5 Flash | 58.56% | 71.40% | Rp38,94 ($0.0022) | 4.62s | Lebih lambat dan biaya 4x lipat tanpa peningkatan akurasi |
| Combined v4.2 (Offline Rules) | 76.82%* | 78.64%* | Rp0 (Lokal) | ~0.15s | 0 LLM, aturan deterministik & High-DPI crop (*all-cells: 76.82%, framework: 87.42%) |
| Multilingual NER (`xlm-roberta-large`) | 43.55% | 55.48% | Rp0 (Lokal) | ~2.5s | 5-Fold OOF token classification, butuh VRAM 7.1GB |
| Regex Baseline Awal (v2) | 42.20% | — | Rp0 (Lokal) | ~0.6s | Baseline historis lama |

---

## Pengujian & Benchmark

Jalankan pengujian unit dan evaluasi komponen dengan:

```bash
# 1. Jalankan seluruh unit test suite
pytest tests/ -v

# 2. Benchmark komparatif Google Gemini pada 74 teks Tesseract
uv run python -m tests.benchmark_gemini_tesseract --models gemini-3.1-flash-lite

# 3. Benchmark pipeline offline Combined v4.2
uv run python -m tests.benchmark_combined_v4_2

# 4. Validasi empiris 4 lapis (5-fold CV, Bootstrap CI, OOD stress test)
uv run python -m tests.validate_gemini_4layer
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
|---------|-----------|
| [AGENTS.md](AGENTS.md) | Konvensi proyek, standar pengujian 4 lapis, dan aturan teknis tim |
| [docs/handoff_v48.md](docs/handoff_v48.md) | Handoff v48: Benchmark & validasi encoder NER mDeBERTa vs XLM-RoBERTa |
| [docs/handoff_v47.md](docs/handoff_v47.md) | Handoff v47: Promosi produksi Direct Tesseract-to-Gemini (Option A) |
| [docs/handoff_v46.md](docs/handoff_v46.md) | Handoff v46: Benchmark komparatif 3 model Gemini (2.5 Flash, 2.5 Flash-Lite, 3.1 Flash-Lite) |
| [docs/report/gemini_tesseract_benchmark_report.md](docs/report/gemini_tesseract_benchmark_report.md) | Laporan detail metrik, token, dan biaya komparasi model Gemini |
| [docs/experiments_ledger.md](docs/experiments_ledger.md) | Rekam jejak seluruh eksperimen tertutup (*closed approaches*) |
