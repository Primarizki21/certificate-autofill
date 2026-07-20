# Certificate Autofill Prototype — No RabbitMQ Variant - V4 DATE FIX

Prototype internal untuk ekstraksi PDF sertifikat mahasiswa dan autofill form Kartu Hasil Prestasi.

Versi ini **tidak memakai RabbitMQ**. Job parsing diproses langsung oleh FastAPI melalui `BackgroundTasks`, atau secara opsional oleh worker yang melakukan polling ke PostgreSQL.

Stack yang dipakai:

- FastAPI untuk internal API dan halaman prototype.
- PostgreSQL untuk menyimpan PDF `BYTEA`, metadata job, hasil parsing, dan hasil mapping.
- Docling sebagai document parser utama.
- PyMuPDF + Regex sebagai fast path.
- RapidOCR/Tesseract sebagai OCR fallback.
- Python job processor untuk menjalankan pipeline ekstraksi.
- Prometheus, Grafana, dan Loki untuk observability awal.

## Alur kerja

```text
PDF dari PostgreSQL
↓
FastAPI Background Task / DB Worker
↓
PyMuPDF fast path
↓
Docling parser jika teks PDF kurang
↓
OCR fallback jika tetap kurang
↓
Field Extractor
↓
Form Mapper
↓
PostgreSQL
↓
Autofill Form
```

Pada prototype ini file PDF disimpan langsung di PostgreSQL pada tabel `document_files.pdf_data`.

## Mode proses parsing

Ada 3 mode:

```text
PROCESSING_MODE=background  # default, tidak perlu worker terpisah
PROCESSING_MODE=sync        # parsing langsung dalam request upload
PROCESSING_MODE=db_worker   # parsing oleh worker polling PostgreSQL
```

Untuk debugging lokal, gunakan default:

```env
PROCESSING_MODE=background
```

## Cara menjalankan tanpa Docker

1. Pastikan PostgreSQL 17 aktif di port 5434.
2. Pastikan database sudah dibuat:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -p 5434 -c "CREATE DATABASE certautofill;"
```

3. Masuk ke backend dan install dependency:

```powershell
cd D:\PUSAKA\certificate_autofill_prototype\backend
..\okeenv\Scripts\activate
pip install -r requirements.txt
```

4. Set environment variable:

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

5. Jalankan API:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. Buka prototype:

```text
http://localhost:8000
```

## Cara menjalankan dengan Docker Compose

Docker Compose pada versi ini juga tidak memakai RabbitMQ.

```bash
docker compose up --build
```

Service yang aktif:

```text
FastAPI  : http://localhost:8000
Postgres : localhost:5434
Prometheus: http://localhost:9090
Grafana  : http://localhost:3000
Loki     : http://localhost:3100
```

## Cara kerja UI

Urutan field dibuat sesuai permintaan:

1. Tahun Akademik
2. Bukti Fisik
3. Upload Bukti
4. Setelah PDF di-upload dan parsing selesai, field lain tampil dan otomatis terisi.

## Rule autofill utama

- Jika teks sertifikat mengandung kata `kegiatan` dan role `panitia`, maka `Jenis Kegiatan` dipetakan menjadi `Panitia Dalam Suatu Kegiatan Kemahasiswaan`.
- Jika ada kata `Dekan`, maka `Tingkat` menjadi `Fakultas`.
- Jika ada kata `Direktur Kemahasiswaan`, maka `Tingkat` menjadi `Universitas`.
- Jika ada `Universitas Airlangga` atau daftar PTN lain, maka `Jenis Penyelenggara` menjadi `PTN di Indonesia`.
- Jika ada universitas swasta dari daftar konfigurasi, maka `Jenis Penyelenggara` menjadi `PTS di Indonesia`.
- Jika ada pola universitas luar negeri, maka `Jenis Penyelenggara` menjadi `PT di luar negeri`.
- Jika ada `Kementerian`, maka `Jenis Penyelenggara` menjadi `Kementerian Negara`.
- Jika ada nama BUMN dalam konfigurasi, maka `Jenis Penyelenggara` menjadi `BUMN`.
- Jika tidak cocok semua, maka `Jenis Penyelenggara` menjadi `Lembaga/Yayasan lain`.
- Jika ditemukan interval tanggal, tanggal awal masuk `Waktu Mulai Pelaksanaan` dan tanggal akhir masuk `Waktu Selesai Pelaksanaan`.
- Jika hanya ditemukan satu tanggal, nilai yang sama masuk ke dua field tanggal.
- Jika ditemukan pola nomor sertifikat berbasis `angka/.../.../tahun`, maka masuk ke `Nomor Bukti Fisik / Nomor Sertifikasi`.

## Endpoint utama

```http
POST /api/documents
GET  /api/documents/{document_id}/result
GET  /api/options
GET  /metrics
GET  /healthz
```

## Catatan production

Versi tanpa RabbitMQ ini lebih mudah dijalankan untuk prototype lokal. Untuk traffic tinggi, mode `background` tidak sekuat queue broker karena semua proses parsing berjalan di proses FastAPI. Jika nanti perlu skala besar, gunakan mode `db_worker` dengan beberapa worker polling PostgreSQL, atau kembalikan message broker seperti RabbitMQ/Kafka.
