# Laporan Evaluasi & Benchmark Dataset Uji Riil (`certs_test`)

> **Tanggal Evaluasi:** 31 Agustus 2026  
> **Target Evaluasi:** Pipeline Ekstraksi Non-LLM (Baseline Produksi, Combined v2 Staging, Combined v3 Composite Staging)  
> **Ground Truth:** `Ground_Truth_Test_Labeling_Sertifikat_Elzandi_v2.csv` (Kolom `Folder` diabaikan sesuai instruksi)  
> **Dataset Uji:** `certs_test/` (30 sertifikat mahasiswa riil: 29 PDF, 1 JPEG)  
> **Metrologi:** Matcher v2 (`tests/matchers.py`) — Exact Match, Fuzzy Match, Word Error Rate (WER), Character Error Rate (CER).

---

## 1. Ringkasan Eksekutif

Pengujian dilakukan secara ketat dan deterministik menggunakan **pipeline non-LLM (0 LLM calls)** tanpa bias pada 30 berkas sertifikat baru di folder `certs_test/` terhadap anotasi ground truth `Ground_Truth_Test_Labeling_Sertifikat_Elzandi_v2.csv`.

### Tabel Perbandingan Performa Pipeline (30 Sertifikat, 147 Sel Terisi)

| Pipeline Variant | MACRO Exact | MACRO Fuzzy | Tanggal (Mulai/Selesai) | Nomor Sertifikat | Tingkat (Scope) | Nama Kegiatan | Penyelenggara | LLM Calls |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Baseline Regex** | 75/147 (**51.0%**) | 88/147 (**59.9%**) | 15/19 (78.9%) / 17/19 (89.5%) | 11/19 (57.9%) | 22/30 (73.3%) | 3/30 (10.0%) | 7/30 (23.3%) | 0 |
| **Combined v2 Staging** | 84/147 (**57.1%**) | 106/147 (**72.1%**) | 15/19 (78.9%) / 17/19 (89.5%) | 16/19 (84.2%) | 22/30 (73.3%) | 8/30 (26.7%) | 6/30 (20.0%) | 0 |
| **Combined v3 Composite** | **92/147 (62.6%)** | **115/147 (78.2%)** | **19/19 (100.0%)** / **19/19 (100.0%)** | **17/19 (89.5%)** | **23/30 (76.7%)** | **8/30 (26.7%)** | **6/30 (20.0%)** | **0** |

### Temuan Kunci
1. **Tanggal Sempurna (100.0% Exact Match):** Seluruh 19 sertifikat yang memiliki informasi tanggal berhasil diekstraksi dengan **0 kesalahan** (`waktu_mulai_pelaksanaan` dan `waktu_selesai_pelaksanaan` 19/19 exact, WER 0.000). Modul multi-day span dan date normalizer terbukti sangat tangguh pada format tanggal nyata.
2. **Nomor Sertifikat Sangat Akurat (89.5% Exact Match):** Dari 19 sertifikat bernomor, 17 nomor terekstraksi persis (89.5%). 2 ketidakcocokan sisanya murni akibat noise OCR (huruf `O` vs angka `0`) dan pemotongan baris OCR.
3. **Klasifikasi Tingkat Robust (76.7% Exact Match):** 23 dari 30 sertifikat terklasifikasi ke opsi tingkat yang tepat via context router tanpa LLM.
4. **Nama Kegiatan & Penyelenggara:** Menghasilkan Fuzzy Match yang kuat (**66.7%** pada kegiatan dan **56.7%** pada penyelenggara), di mana selisih exact match sebagian besar disebabkan oleh perbedaan batas subtitel / tanda kurung / akronim vs nama panjang universitas.
5. **Kecepatan & Efisiensi:** Rata-rata waktu pemrosesan berkisar 5–8 detik per sertifikat untuk file berbasis scan (OCR penuh) dan <0.02 detik untuk file teks tersemat (Fast Path PyMuPDF).

---

## 2. Metodologi Evaluasi & Pemetaan Data

### Struktur Dataset
- **Total Berkas:** 30 berkas aktif (29 format `.pdf`, 1 format `.jpeg`).
- **Berkas yang tidak masuk Ground Truth:** `02_Sertifikat KARSA.pdf` (berkas ada di direktori tetapi tidak memiliki baris koresponden di CSV anotasi GT). Seluruh 30 baris GT lainnya terpetakan 1-to-1 dengan 30 berkas di `certs_test/`.
- **Sel Terevaluasi (Non-Empty):** 147 sel dari 180 total kemungkinan sel (6 field × 30 sertifikat). Sel dengan nilai `-` pada Ground Truth dilewati dari evaluasi metrik akurasi.

### 6 Field Evaluasi Baku:
1. `tingkat`
2. `nama_kegiatan_sertifikasi`
3. `waktu_mulai_pelaksanaan`
4. `waktu_selesai_pelaksanaan`
5. `penyelenggara_kegiatan`
6. `nomor_bukti_fisik_nomor_sertifikasi`

---

## 3. Rincian Evaluasi Per Field (Combined v3 Composite)

### 3.1. Waktu Mulai & Selesai Pelaksanaan
- **Akurasi:** 19/19 (**100.0% Exact Match**, 100.0% Fuzzy Match)
- **Error Rate:** Mean WER = 0.000, Mean CER = 0.000
- **Catatan:** Format rentang multi-hari (mis. `3 September 2022 - 18 September 2022`, `12 November 2022 - 27 November 2022`, `17-18 September 2025`) ditangani dengan sempurna oleh regex normalizer.

### 3.2. Nomor Bukti Fisik / Nomor Sertifikasi
- **Akurasi:** 17/19 (**89.5% Exact Match**, 89.5% Fuzzy Match)
- **Error Rate:** Mean WER = 0.105, Mean CER = 0.024
- **Daftar Mismatch (2 kasus):**
  1. `15_Data Slayer 1.0 JUARA 2.pdf`:
     - *Expected:* `IT TEL355/MHS-006/KA.PRO-09/I/2024`
     - *Actual:* `006/KA.PRO-09/I/2024`
     - *Penyebab:* OCR memisahkan prefix `IT TEL355/MHS-` pada baris atas terpisah.
  2. `30_Data Mining Gemastik 2025 Juara 3.pdf`:
     - *Expected:* `962/KMH01/KMH/2025`
     - *Actual:* `962/KMHO1/KMH/2025`
     - *Penyebab:* OCR membaca digit `0` sebagai huruf `O` pada token `KMH01`.

### 3.3. Tingkat Kegiatan (Scope)
- **Akurasi:** 23/30 (**76.7% Exact Match**, 76.7% Fuzzy Match)
- **Error Rate:** Mean WER = 0.233, Mean CER = 0.172
- **Daftar Mismatch (7 kasus):**
  1. `00_WEBINAR_E-Sertificate.jpeg` — Exp: *Lainnya*, Act: *Nasional* (Webinar umum tanpa institusi kampus spesifik default ke Nasional).
  2. `03_Sertifikat Binary.pdf` — Exp: *Departemen/Program Studi*, Act: *Fakultas* (Keberadaan teks tanda tangan Dekan/BEM FTMM memicu rule Fakultas).
  3. `04_Panitia Dekan Cup 2022.pdf` — Exp: *Fakultas*, Act: *Nasional* (Teks template memicu rule kompetisi umum).
  4. `07_Panitia PKKMB Unair.pdf` — Exp: *Universitas*, Act: *Fakultas* (Sertifikat ditandatangani oleh pimpinan FTMM).
  5. `11_Indonesia Focus.pdf` — Exp: *Internasional*, Act: *Universitas* (Nama kampus University of Tennessee memicu rule Universitas).
  6. `13_KIM UNAIR JUARA 2.pdf` — Exp: *Universitas*, Act: *Nasional* (Kata "Kompetisi" memicu rule default kompetisi).
  7. `14_FEB Juara.pdf` — Exp: *Fakultas*, Act: *Nasional* (KIM FEB memicu rule kompetisi).

### 3.4. Nama Kegiatan Sertifikasi
- **Akurasi:** 8/30 (**26.7% Exact Match**), 20/30 (**66.7% Fuzzy Match**)
- **Error Rate:** Mean WER = 0.593, Mean CER = 0.565
- **Analisis:**
  - 8 sertifikat exact match.
  - 12 sertifikat fuzzy match (isi inti kegiatan benar, tetapi ground truth memiliki anotasi tambahan seperti subtitel dalam kurung, nomor divisi lomba, atau tahun akademik).
  - 10 sertifikat miss/kosong karena template sertifikat tidak memiliki pola penanda struktural eksplisit (`dalam rangka...`, `sebagai...`).

### 3.5. Penyelenggara Kegiatan
- **Akurasi:** 6/30 (**20.0% Exact Match**), 17/30 (**56.7% Fuzzy Match**)
- **Error Rate:** Mean WER = 0.649, Mean CER = 0.595
- **Analisis:**
  - 6 sertifikat exact match.
  - 11 sertifikat fuzzy match (nama penyelenggara terambil benar tetapi tidak memuat hierarki lengkap seperti `, Fakultas Ilmu Komputer` atau singkatan akronim `BEM FTMM` vs `Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin`).
  - 13 sertifikat miss/noise OCR (mis. spasi rapat pada `UNIVERSITASAIRLANGGA...` atau header OCR yang tercampur baris tanda tangan).

---

## 4. Evaluasi Safety Net & Review Calibration (`needs_review`)

Sesuai arsitektur keselamatan produksi, sistem menetapkan bendera `needs_review = True` apabila terdapat field wajib yang kosong atau memiliki nilai kepercayaan `confidence < 0.80`.

| Metrik Safety Net | Hasil pada `certs_test` (30 Dokumen) |
|---|:---:|
| **Total Dokumen** | 30 |
| **Dokumen dengan Sedikitnya 1 Mismatch** | 28 |
| **Dokumen Prediksi Sempurna (0 Mismatch)** | 2 |
| **Dokumen yang Ter-flag `needs_review = True`** | 18 |
| **True Positives (Bermasalah & Ter-flag)** | 18 |
| **False Positives (Sempurna tapi Ter-flag)** | 0 |
| **Review Precision** | **100.0%** |
| **Review Recall** | **64.3%** |

### Analisis Kalibrasi
- **Zero False Alarm:** Sistem memiliki presisi review 100%, artinya setiap dokumen yang ditandai untuk review oleh sistem memang memiliki ketidaksesuaian ekstraksi nyata.
- **Peluang Optimasi Kalibrasi:** 10 dokumen yang tidak ter-flag review memiliki confidence $\ge 0.80$ dari pola regex yang cocok, namun memiliki variasi string minor (misalnya singkatan BEM FTMM vs nama panjang). Menyesuaikan ambang batas confidence pada field teks panjang (seperti `nama_kegiatan`) dapat meningkatkan recall review mendekati target 95%+.

---

## 5. Ringkasan & Rekomendasi Teknis

1. **Efektivitas Pipeline:** Pipeline Combined v3 Composite tanpa LLM berhasil meningkatkan MACRO exact match dari **51.0% (Baseline)** menjadi **62.6%**, dan MACRO fuzzy match dari **59.9%** menjadi **78.2%**.
2. **Keandalan Modul Tanggal & Nomor:** Komponen ekstraksi tanggal dan nomor sertifikat siap untuk penggunaan produksi penuh dengan tingkat keberhasilan $\ge 89.5\% - 100\%$.
3. **Penyelarasan Nama Kegiatan & Penyelenggara:** Pada implementasi UI form autofill, penggunaan dropdown/autocomplete berbasis data master atau fuzzy suggestions sangat disarankan untuk membantu pengguna mengonfirmasi penyelenggara dan nama kegiatan dengan cepat.
