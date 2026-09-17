# Frontend Prototype Autofill Sertifikat

Frontend antarmuka web murni (HTML/CSS/JavaScript vanilla) tanpa dependensi Node.js, npm, atau build tools tambahan.

---

## Cara Menjalankan

1. Pastikan backend FastAPI aktif di port `8000`.
2. Buka berkas berikut langsung di browser:
   ```text
   frontend/index.html
   ```

Jika browser membatasi CORS/request karena mode file lokal (`file://`), jalankan static server sederhana:

```bash
cd frontend
python -m http.server 5173
```

Lalu buka di browser:
```text
http://localhost:5173
```

Frontend akan berkomunikasi dengan API backend di:
```text
http://localhost:8000
```

---

## Endpoint Backend yang Digunakan

```http
GET  /api/options                         # Memuat opsi dropdown (Tahun, Bukti Fisik, Tingkat, Kelompok, Jenis Kegiatan berelasi, Jabatan)
GET  /api/master/activities?search=...    # Katalog pencarian taksonomi kegiatan resmi universitas untuk UI Modal
POST /api/documents                       # Mengunggah PDF sertifikat (multipart/form-data) untuk pemrosesan background
GET  /api/documents/{document_id}/result  # Polling status pemrosesan dan hasil autofill form KHP
```

---

## Fitur Utama Antarmuka Form KHP

### 1. Autofill Terintegrasi 9-Field
Form KHP otomatis terisi dari hasil ekstraksi semantik dan pemetaan taksonomi resmi:
- **6 Data Faktual Sertifikat**: Nama Kegiatan, Nomor Sertifikat, Penyelenggara, Waktu Mulai, Waktu Selesai, Tingkat.
- **3 Dimensi Taksonomi Resmi**: Kelompok Kegiatan, Jenis Kegiatan, dan Prestasi/Partisipasi/Jabatan.

### 2. Cascading Filter Dinamis
Dropdown kegiatan dirancang terhubung secara dinamis:
- Memilih **Kelompok Kegiatan** secara otomatis menyaring opsi **Jenis Kegiatan** yang relevan di bawah kelompok tersebut.
- Memilih **Jenis Kegiatan** secara otomatis mengisi kembali **Kelompok Kegiatan** yang menaunginya.

### 3. Modal Pencarian Master Kegiatan
- Tombol **"MASTER KEGIATAN"** membuka dialog pencarian interaktif.
- Pengguna dapat mengetik kata kunci (contoh: *"lomba"*, *"panitia"*, *"kkn"*, *"forum"*) untuk menemukan kegiatan resmi universitas dan menerapkannya ke form dengan satu klik.

### 4. Notifikasi Status Ramah Pengguna
- Respons backend telah disanitasi penuh untuk konsumsi mahasiswa publik tanpa membocorkan istilah teknis database atau confidence score.
- Jika terdapat ambiguitas data, status menampilkan himbauan:  
  *"Pengisian form selesai otomatis. Silakan periksa kembali isian sebelum menyimpan."*

---

## Alur Kerja UI

1. Mahasiswa memilih **Tahun Akademik** dan **Bukti Fisik**.
2. Mahasiswa memilih file PDF sertifikat dan menekan tombol **"PROSES PDF"**.
3. Frontend mengunggah dokumen sementara ke backend (penyimpanan ephemeral zero-PDF).
4. Pratinjau PDF ditampilkan di layar dan proses polling berjalan otomatis setiap 1,5 detik.
5. Setelah ekstraksi selesai, form KHP 9-field terisi otomatis dan siap diperiksa mahasiswa sebelum disimpan.
