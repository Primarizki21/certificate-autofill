# Menjalankan tanpa Docker dan tanpa RabbitMQ

Tetap dibutuhkan PostgreSQL lokal. Prototype ini tidak lagi membutuhkan RabbitMQ.

## 1. Buat venv dan install dependency

```powershell
cd D:\PUSAKA\certificate_autofill_prototype\backend
..\okeenv\Scripts\activate
pip install -r requirements.txt
```

## 2. Siapkan environment variable

Jika PostgreSQL 17 kamu memakai port 5434 dan password `postgres`:

```powershell
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:DB_WORKER_POLL_SECONDS="2"
$env:MAX_UPLOAD_SIZE_MB="10"
$env:MIN_TEXT_LENGTH="80"
$env:ENABLE_DOCLING="true"
$env:ENABLE_OCR_FALLBACK="true"
$env:MAX_JOB_RETRIES="3"
```

Ganti password pada `DATABASE_URL` jika password PostgreSQL kamu bukan `postgres`.

## 3. Jalankan FastAPI

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Buka:

```text
http://localhost:8000
```

## Mode opsional: DB worker

Default `PROCESSING_MODE=background`, jadi kamu tidak perlu menjalankan worker.

Jika ingin proses parsing dilakukan oleh proses terpisah tanpa RabbitMQ, ubah:

```powershell
$env:PROCESSING_MODE="db_worker"
```

Lalu jalankan terminal kedua:

```powershell
cd D:\PUSAKA\certificate_autofill_prototype\backend
..\okeenv\Scripts\activate
python -m app.worker
```

Worker ini polling job dari PostgreSQL, bukan RabbitMQ.
