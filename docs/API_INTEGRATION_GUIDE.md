# Panduan Integrasi API Ekstraksi Sertifikat (`/api/v1/extract`) & Pengujian Jarak Jauh

Dokumen teknis ini ditujukan untuk pengembang aplikasi frontend atau sistem eksternal yang ingin mengintegrasikan layanan ekstraksi sertifikat mahasiswa dan pemetaan otomatis ke taksonomi resmi **Kartu Hasil Prestasi (KHP) AUCC Universitas**.

---

## 1. Ringkasan Endpoint

* **URL Path:** `/api/v1/extract`
* **HTTP Method:** `POST`
* **Content-Type:** `multipart/form-data`
* **Format Respons:** `application/json`
* **Karakteristik:** *Stateless & One-Shot* (file diproses langsung di memori dan balikan JSON dikirim seketika tanpa memerlukan polling atau penyimpanan file privat di database, mengutamakan keamanan dan privasi data).

---

## 2. Autentikasi & Format API Key

Endpoint ini dilindungi oleh mekanisme autentikasi **API Key**.

### Spesifikasi Kunci (Key Format)
* API Key diawali dengan awalan (*prefix*) **`sk-`** diikuti token acak alfanumerik aman (minimal 16 karakter).
* Contoh format yang valid (placeholder dokumentasi):
  * `sk-test-sample-key-for-development-01`
  * `sk-prod-sample-key-for-production-01`

### Cara Mengirimkan API Key dari Client
Klien dapat mengirimkan API Key melalui salah satu dari dua cara berikut:

1. **Header Khusus (Rekomendasi):**
   ```http
   X-API-Key: <YOUR_API_KEY>
   ```
2. **Header Standar Bearer Token:**
   ```http
   Authorization: Bearer <YOUR_API_KEY>
   ```

### Konfigurasi di Sisi Server (`.env`)
* **Mode Terproteksi (Produksi):** Isi variabel `API_KEYS` di file `.env`:
  ```env
  API_KEYS="<YOUR_FIRST_API_KEY>,<YOUR_SECOND_API_KEY>"
  REQUIRE_API_KEY=true
  ```
* **Mode Pengembangan Lokal (Development):** Anda dapat menonaktifkan autentikasi sementara untuk pengujian lokal dengan menyetel `REQUIRE_API_KEY=false`. Pastikan menyetel `REQUIRE_API_KEY=true` saat layanan diekspos ke jaringan publik atau staging.

---

## 3. Spesifikasi Parameter Request

Request dikirimkan menggunakan format `multipart/form-data`:

| Nama Parameter | Tipe | Status | Deskripsi |
|---|:---:|:---:|---|
| **`file`** | File Binary | **Wajib** | File dokumen sertifikat. Format yang didukung: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.webp`. Ukuran maksimal default **25 MB**. |
| `tahun_akademik` | String | Opsional | Format tahun akademik pelaporan. Contoh: `"2024/2025 - Genap"`. Default: `"2035/2036 - Genap"`. |
| `bukti_fisik` | String | Opsional | Jenis bukti fisik. Default: `"Sertifikat"`. |

---

## 4. Contoh Kode Pemanggilan (Siap Pakai)

### A. Menggunakan cURL (Terminal / Bash)

```bash
curl -X POST "http://localhost:8000/api/v1/extract" \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -F "file=@/path/ke/sertifikat_mahasiswa.pdf" \
  -F "tahun_akademik=2024/2025 - Genap"
```

### B. Menggunakan JavaScript Modern (Fetch API — Browser / React / Next.js / Vue)

```javascript
async function extractCertificate(fileInput) {
  const file = fileInput.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('tahun_akademik', '2024/2025 - Genap');
  formData.append('bukti_fisik', 'Sertifikat');

  try {
    const response = await fetch('http://localhost:8000/api/v1/extract', {
      method: 'POST',
      headers: {
        'X-API-Key': '<YOUR_API_KEY>',
      },
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || `HTTP Error ${response.status}`);
    }

    const result = await response.json();
    console.log('Status ekstraksi:', result.status);
    console.log('Nama Kegiatan:', result.data.nama_kegiatan_sertifikasi);
    console.log('ID Kelompok Kegiatan:', result.data.kelompok_kegiatan.id);
    console.log('ID Kegiatan 1:', result.data.jenis_kegiatan.id);
    console.log('ID Tingkat:', result.data.tingkat.id);
    console.log('ID Jabatan/Prestasi:', result.data.prestasi_partisipasi_jabatan.id);
    console.log('ID Kegiatan 2 (AUCC PK):', result.data.id_kegiatan_2);

    return result;
  } catch (error) {
    console.error('Gagal mengekstrak sertifikat:', error);
  }
}
```

### C. Menggunakan JavaScript (Axios)

```javascript
import axios from 'axios';

async function extractWithAxios(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await axios.post('http://localhost:8000/api/v1/extract', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
      'X-API-Key': '<YOUR_API_KEY>',
    },
  });

  return response.data;
}
```

### D. Menggunakan Python (`requests`)

```python
import requests

url = "http://localhost:8000/api/v1/extract"
headers = {
    "X-API-Key": "<YOUR_API_KEY>"
}
files = {
    "file": open("sertifikat_contoh.pdf", "rb")
}
data = {
    "tahun_akademik": "2024/2025 - Genap",
    "bukti_fisik": "Sertifikat"
}

response = requests.post(url, headers=headers, files=files, data=data)

if response.status_code == 200:
    res_json = response.json()
    print("Hasil Berhasil:", res_json["data"]["nama_kegiatan_sertifikasi"])
    print("ID Kegiatan 2 AUCC:", res_json["data"]["id_kegiatan_2"])
else:
    print(f"Error {response.status_code}:", response.json())
```

---

## 5. Struktur Output JSON Lengkap

Contoh payload balikan sukses (`200 OK`):

```json
{
  "status": "success",
  "needs_review": false,
  "data": {
    "nama_kegiatan_sertifikasi": "PENGENALAN KEHIDUPAN KAMPUS BAGI MAHASISWA BARU (PKKMB) TAHUN 2024",
    "nomor_bukti_fisik_nomor_sertifikasi": "001/UN3.FTMM/KM/2024",
    "penyelenggara_kegiatan": "Universitas Airlangga",
    "jenis_penyelenggara": "PTN di Indonesia",
    "waktu_mulai_pelaksanaan": "18/08/2024",
    "waktu_selesai_pelaksanaan": "27/08/2024",
    "bukti_fisik": "Sertifikat",
    "tahun_akademik": "2024/2025 - Genap",
    "kelompok_kegiatan": {
      "id": 1,
      "label": "Kegiatan Wajib Universitas"
    },
    "jenis_kegiatan": {
      "id": 41,
      "label": "PKKMB"
    },
    "tingkat": {
      "id": 4,
      "label": "Universitas"
    },
    "prestasi_partisipasi_jabatan": {
      "id": 6,
      "label": "Peserta"
    },
    "id_kegiatan_2": 4098
  },
  "confidence": {
    "nama_kegiatan_sertifikasi": 0.95,
    "nomor_bukti_fisik_nomor_sertifikasi": 0.98,
    "penyelenggara_kegiatan": 0.94,
    "tingkat": 0.90,
    "waktu_mulai_pelaksanaan": 0.90,
    "waktu_selesai_pelaksanaan": 0.90
  },
  "sources": {
    "nama_kegiatan_sertifikasi": "ocr_extraction",
    "kelompok_kegiatan": "khp_master_resolution",
    "jenis_kegiatan": "khp_master_resolution",
    "tingkat": "khp_master_resolution",
    "prestasi_partisipasi_jabatan": "khp_master_resolution"
  },
  "review_reasons": [],
  "parser_engine": "hybrid_ocr_khp_master"
}
```

### Kamus Field Respons
1. **`status`**: `"success"` (seluruh field terisi dengan keyakinan tinggi) atau `"needs_review"` (ada field yang perlu diverifikasi pengguna sebelum disimpan).
2. **`needs_review`**: Boolean (`true`/`false`). Jika `true`, form frontend menandai field terkait agar user memeriksa ulang.
3. **`data.nama_kegiatan_sertifikasi`**: Nama acara / judul sertifikat (text).
4. **`data.nomor_bukti_fisik_nomor_sertifikasi`**: Nomor surat keputusan / nomor registrasi sertifikat (text / null).
5. **`data.penyelenggara_kegiatan`**: Instansi atau organisasi penyelenggara kegiatan (text).
6. **`data.jenis_penyelenggara`**: Kategori penyelenggara standar universitas (misal `"PTN di Indonesia"`, `"BUMN"`, dll).
7. **`data.waktu_mulai_pelaksanaan`** & **`data.waktu_selesai_pelaksanaan`**: Tanggal kegiatan format `dd/mm/yyyy`.
8. **Field Master AUCC KHP (`id` + `label`)**:
   * `kelompok_kegiatan`: Kategori besar kegiatan (misal ID 1: Wajib Universitas).
   * `jenis_kegiatan`: Jenis kegiatan spesifik (Kegiatan 1 AUCC, misal ID 41: PKKMB).
   * `tingkat`: Lingkup tingkat prestasi/kegiatan (misal ID 4: Universitas, ID 3: Nasional).
   * `prestasi_partisipasi_jabatan`: Peranan mahasiswa (misal ID 6: Peserta, ID 1: Juara 1).
9. **`data.id_kegiatan_2`**: ID integer relasi tunggal pada tabel referensi `aucc.kegiatan_2`. Nilai ini adalah kunci utama (*Primary Key*) yang menentukan bobot poin SKP pada database KHP.

---

## 6. Panduan Menjalankan Cloudflare Tunnel (Pengujian Publik Terbatas)

Untuk pengujian jarak jauh oleh rekan penguji tanpa memerlukan konfigurasi public IP atau router port-forwarding, Anda dapat memanfaatkan Cloudflare Tunnel sementara.

> **Peringatan Keamanan:** Selalu pastikan `REQUIRE_API_KEY=true` dan nilai `API_KEYS` telah diisi di `.env` sebelum membuka tunnel publik agar endpoint terlindungi dari akses liar.

### Langkah 1: Unduh Binary Portabel `cloudflared` (Cukup Sekali)
Jalankan perintah ini di terminal WSL / Linux Anda (di folder repositori proyek):

```bash
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared && chmod +x cloudflared
```
*(File binary ini sudah terdaftar di `.gitignore` sehingga aman dan tidak akan masuk ke git).*

### Langkah 2: Nyalakan Terowongan (Tunnel)
Pastikan backend aplikasi sedang menyala di port 8000 (`docker compose up -d` atau uvicorn), lalu jalankan:

```bash
./cloudflared tunnel --url http://localhost:8000
```

Terminal akan menampilkan log koneksi dan tautan publik acak berprotokol HTTPS:
```text
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at:                                          |
|  https://random-assigned-subdomain.trycloudflare.com                                       |
+--------------------------------------------------------------------------------------------+
```

### Langkah 3: Bagikan URL ke Rekan Penguji
Rekan Anda dapat menguji endpoint menggunakan URL publik tersebut dengan menyertakan API Key yang telah Anda tentukan:

```bash
curl -X POST "https://random-assigned-subdomain.trycloudflare.com/api/v1/extract" \
  -H "X-API-Key: <YOUR_API_KEY>" \
  -F "file=@sertifikat_saya.pdf"
```

### Langkah 4: Mematikan Akses Terowongan
Untuk menutup akses publik kapan saja:
* Tekan **`Ctrl + C`** pada jendela terminal yang menjalankan `cloudflared`.
* Seketika itu juga, URL publik dinonaktifkan permanen oleh Cloudflare.

---

## 7. Tabel Kode Status HTTP & Penanganan Kesalahan

| Kode Status | Arti | Penyebab & Solusi |
|:---:|---|---|
| **`200 OK`** | Berhasil | Dokumen berhasil diproses dan JSON dikembalikan. |
| **`400 Bad Request`** | Input Tidak Valid | File kosong, format file bukan dokumen yang didukung (bukan PDF/JPG/PNG/WEBP), atau berkas korup. |
| **`401 Unauthorized`** | Kredensial Salah / Hilang | Header `X-API-Key` atau Bearer token tidak disertakan atau nilai API Key salah. |
| **`413 Payload Too Large`** | Ukuran File Terlalu Besar | Ukuran dokumen melebihi batas (default: 25 MB). Kompresi dokumen sebelum mengunggah jika melebihi batas. |
| **`422 Unprocessable Entity`** | Validasi Skema Gagal | Parameter form wajib (`file`) tidak ditemukan dalam payload request. |
| **`500 Internal Server Error`** | Kesalahan Server | Terjadi kendala internal pada server saat mengekstrak teks. |
