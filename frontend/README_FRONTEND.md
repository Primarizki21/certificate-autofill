# Frontend Prototype Autofill Sertifikat

Frontend ini adalah HTML/CSS/JavaScript murni. Tidak perlu Node.js, tidak perlu npm, dan tidak perlu build.

## Cara menjalankan paling mudah

1. Jalankan backend FastAPI di port 8000.
2. Buka file ini langsung di browser:

```text
frontend/index.html
```

Jika browser memblokir request karena mode file lokal, jalankan static server:

```powershell
cd frontend
python -m http.server 5173
```

Lalu buka:

```text
http://localhost:5173
```

Frontend akan memanggil API backend di:

```text
http://localhost:8000
```

## Endpoint backend yang dipakai

```text
GET  /api/options
POST /api/documents
GET  /api/documents/{document_id}/result
```

## Alur UI

1. Tahun Akademik, Bukti Fisik, dan Upload Bukti tampil di atas.
2. User upload PDF.
3. Preview PDF dan form hasil autofill muncul.
4. Frontend mengirim PDF ke backend.
5. Backend menyimpan PDF ke PostgreSQL dan menjalankan parsing.
6. Frontend polling hasil parsing.
7. Field form otomatis terisi dari JSON hasil extraction.
