# Certificate Autofill Prototype - Fixed UI, No RabbitMQ

Versi ini sudah memakai frontend yang bentuknya mengikuti form Input Kartu Hasil Prestasi dan tersambung ke backend FastAPI.

## Backend

Jalankan dari PowerShell:

```powershell
cd D:\PUSAKA\certificate_autofill_FIXED_UI\backend
D:\PUSAKA\certificate_autofill_prototype\okeenv\Scripts\activate

$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:1111@127.0.0.1:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:MAX_UPLOAD_SIZE_MB="10"
$env:MIN_TEXT_LENGTH="80"
$env:ENABLE_DOCLING="true"
$env:ENABLE_OCR_FALLBACK="true"
$env:MAX_JOB_RETRIES="3"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Buka frontend dari backend:

```text
http://127.0.0.1:8000
```

## Frontend standalone

Backend tetap harus menyala di port 8000. Buka terminal kedua:

```powershell
cd D:\PUSAKA\certificate_autofill_FIXED_UI\frontend
python -m http.server 5173
```

Buka:

```text
http://127.0.0.1:5173/index.html
```

Jangan jalankan `python -m http.server 5173` dari folder `backend`, karena itu akan menampilkan directory listing.


Catatan V3: panel debug hasil parsing sudah dihapus dari frontend. Jika masih terlihat, lakukan hard refresh browser dengan Ctrl+F5 atau clear cache.

## V7 rule note
This build includes an additional generalized rule for HIMA/Himpunan Mahasiswa/IM/Ikatan Mahasiswa signatures:
- with Universitas Airlangga/Unair/FTMM affiliation context -> Tingkat `Departemen/Program Studi`
- without that affiliation context -> Tingkat `Nasional`
