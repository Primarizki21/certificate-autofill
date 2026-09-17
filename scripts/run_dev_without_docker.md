# Menjalankan Tanpa Docker

Panduan menjalankan backend FastAPI secara lokal tanpa container Docker.

---

## 1. Prasyarat Sistem

1. **Python 3.11+** terpasang.
2. **PostgreSQL 17** aktif di port `5434` (atau sesuaikan port di `.env`) dengan database `certautofill`.
3. **Tesseract OCR** terpasang pada sistem operasi:
   - Linux (Ubuntu/Debian): `sudo apt install tesseract-ocr tesseract-ocr-ind`
   - Windows: Unduh installer Tesseract OCR dan tambahkan ke PATH sistem.

---

## 2. Buat Virtual Environment & Install Dependensi

### Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

---

## 3. Siapkan Environment Variable

Salin template konfigurasi dari root proyek:
```bash
cp .env.example .env
```

Pastikan variabel utama terkonfigurasi pada shell:

### Linux / macOS:
```bash
export APP_ENV=development
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
export PROCESSING_MODE=background
export ENABLE_TESSERACT_GEMINI=true
export ENABLE_KHP_MASTER_STAGING=true
export ENABLE_COMBINED_V4_2=true
export GOOGLE_API_KEY=""  # Isi dengan API key Google AI Studio Anda
```

### Windows (PowerShell):
```powershell
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:ENABLE_TESSERACT_GEMINI="true"
$env:ENABLE_KHP_MASTER_STAGING="true"
$env:ENABLE_COMBINED_V4_2="true"
$env:GOOGLE_API_KEY=""
```

> 💡 Sesuaikan kredensial `DATABASE_URL` jika user dan password PostgreSQL lokal Anda berbeda dari default (`postgres:postgres`).

---

## 4. Jalankan FastAPI

Dari root repositori atau folder `backend/`:

### Linux / macOS:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend
```

### Windows (PowerShell):
```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend
```

Buka di browser:
- Web Form & App: `http://localhost:8000`
- Swagger API Docs: `http://localhost:8000/docs`
- ReDoc API Docs: `http://localhost:8000/redoc`

---

## 5. Mode Alternatif: DB Worker (Opsional)

Secara default, `PROCESSING_MODE=background` menggunakan BackgroundTasks FastAPI sehingga worker terpisah tidak diperlukan.

Jika ingin pemrosesan ekstraksi dijalankan oleh worker independen via polling antrian database:
1. Ubah `PROCESSING_MODE=db_worker` di `.env`.
2. Jalankan worker di terminal kedua:
   ```bash
   python -m app.worker
   ```
   *(Pastikan working directory berada di `backend/` atau tambahkan `PYTHONPATH=backend`).*
