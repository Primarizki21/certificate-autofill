# Laporan Evaluasi: Pure 100% Tesseract OCR (All-74) + Composite v4.x Suite
> **Tanggal Run:** 2026-09-01 22:27:59  
> **Dataset:** 74 Sertifikat (49 Scan, 25 Digital Embedded)  
> **Ground Truth:** `Ground_Truth_Sertifikat_v9.csv` | **Evaluator:** Matcher v2 (`tests/matchers.py`)  
> **Arsitektur Pipeline:** Tesseract-Primary (Multi-PSM) + Composite v4.x Candidate (`apply_composite_v4_candidate`)

---

## 1. Ringkasan Eksekutif

Eksperimen ini mengevaluasi performa Tesseract sebagai engine OCR utama (*primary standalone OCR*) yang dipasangkan dengan suite post-processing modern **Composite v4.x (B8)**:
- **Activity:** Structural semantic grammar anchors & anti-bleed bounds (`extract_activity_v9`)
- **Nomor:** Length-preserving DPKKA cleaner & gated Roman numeral month repairs (`normalize_nomor_v6`)
- **Penyelenggara:** Normalizer v7 cleaner (`normalize_organizer_v7`)
- **Tanggal:** Date extractor v2 multi-day span parser (`extract_dates_v2`)
- **Tingkat:** Hardened contextual router disambiguation (`route_with_disambiguation_v7`)

Hasil membuktikan peningkatan masif ketika Tesseract multi-PSM dipadukan dengan post-processing v4.x:
- **Framework 5-Field (Scan-49):** MACRO exact **78.61%** (fuzzy **86.57%**), melesat **+31.35pt** dibandingkan baseline `baseline_rapid_tess` (47.26%).
- **Nomor Sertifikat (Scan-49):** Mencapai **87.88%** (29/33), naik **+30.30pt** (+10 sertifikat pulih vs baseline 57.58%).
- **Nama Kegiatan (Scan-49):** Mencapai **73.47%** (36/49), naik **+67.35pt** (+33 sertifikat pulih vs baseline 6.12%).
- **All-Cells 6-Field (Scan-49):** MACRO exact **67.69%** (fuzzy **73.47%**).
- **All-Cells 6-Field (All-74):** MACRO exact **68.47%** (fuzzy **74.32%**).
- **Framework 5-Field (All-74):** MACRO exact **77.10%** (fuzzy **85.16%**).

---

## 2. Tabel Komparasi 4 Arah (Scan-49 Subset)

| Metrik (Scan-49) | Baseline Rapid+Tess (v9) | Rapid-Only + v4.x (HYB-003) | **Tesseract-Primary + v4.x** (New) | Delta vs Baseline |
|---|:---:|:---:|:---:|:---:|
| **MACRO Exact (5-Field)** | 47.26% (95/201) | 50.75% | **78.61%** (158/201) | **+31.35pt** |
| **MACRO Fuzzy (5-Field)** | 57.21% | 63.87% | **86.57%** (174/201) | **+29.36pt** |
| Nama Kegiatan exact | 6.12% (3/49) | 6.12% | **73.47%** (36/49) | **+67.35pt** |
| Nomor Sertifikat exact | 57.58% (19/33) | 57.58% | **87.88%** (29/33) | **+30.30pt** |
| Penyelenggara exact | 26.53% (13/49) | 34.69% | **51.02%** (25/49) | **+24.49pt** |
| Tanggal Mulai exact | 85.71% (30/35) | 85.71% | **97.14%** (34/35) | **+11.43pt** |
| Tanggal Selesai exact | 85.71% (30/35) | 85.71% | **97.14%** (34/35) | **+11.43pt** |
| Tingkat exact (6-Field) | — | — | **83.67%** (41/49) | Baseline baru |

---

## 3. Uji Ketangguhan: Pure Tesseract OCR vs Layer Teks Digital (25 Sertifikat Digital)

Untuk menguji apakah Tesseract tangguh atau mengalami degradasi saat dipaksa membaca file digital murni yang dirender ke gambar raster:

| Metrik (Subset 25 Digital) | Native Digital Layer (Tanpa OCR) | Pure Tesseract OCR (Gambar Murni) | Delta Degradasi / Perubahan |
|---|:---:|:---:|:---:|
| **MACRO Exact (5-Field)** | 74.31% (81/109) | **74.31% (81/109)** | **0.00pt (Zero Degradation!)** |
| **MACRO Fuzzy (5-Field)** | 77.98% (85/109) | **82.57% (90/109)** | **+4.59pt (Lebih Baik!)** |
| Nama Kegiatan exact | 68.00% (17/25) | **76.00% (19/25)** | **+8.00pt** (Segmentasi baris lebih teratur) |
| Nomor Sertifikat exact | 89.47% (17/19) | **89.47% (17/19)** | **0.00pt (100% Identik)** |
| Tanggal Mulai exact | 80.00% (16/20) | **90.00% (18/20)** | **+10.00pt** (Penyatuan kotak teks tanggal) |
| Tanggal Selesai exact | 80.00% (16/20) | **90.00% (18/20)** | **+10.00pt** (Penyatuan kotak teks tanggal) |
| Penyelenggara exact | 60.00% (15/25) | 36.00% (9/25) | -24.00pt (Interleaving pada layout multi-kolom footer) |

**Temuan Empiris:**
1. **Ketangguhan Tinggi:** Membaca seluruh 74 sertifikat murni dari gambar (tanpa bantuan teks digital sama sekali) menghasilkan framework MACRO exact yang **identik (77.10%)** dengan mode yang memakai teks digital asli.
2. **Zero Degradation Nomor:** Pada nomor sertifikat, Tesseract tidak membuat kesalahan fatal baru: 17/19 nomor digital tetap diekstraksi secara presisi (89.47%).
3. **Penyatuan Layout Positif:** Pada nama kegiatan (+8.0pt) dan tanggal (+10.0pt), rekonstruksi tata letak visual Tesseract multi-PSM justru mengatasi fragmentasi kotak teks internal PDF digital.
4. **Trade-off Penyelenggara:** Pada organizer (-24.0pt), logo dan teks footer pada sertifikat digital berbasis template canva mengalami pemecahan urutan baris saat dibaca secara raster.

---

## 4. Rincian Metrik Jarak Edit (WER & CER pada Scan-49)

| Field | Total Sel | Exact Acc | Fuzzy Acc | Avg WER | Avg CER |
|---|:---:|:---:|:---:|:---:|:---:|
| **Nama Kegiatan** | 49 | 73.47% | 87.76% | 0.1686 | 0.1506 |
| **Nomor Sertifikat** | 33 | 87.88% | 87.88% | 0.1212 | 0.0350 |
| **Penyelenggara** | 49 | 51.02% | 69.39% | 0.4532 | 0.4053 |
| **Tanggal Mulai** | 35 | 97.14% | 97.14% | 0.0286 | 0.0029 |
| **Tanggal Selesai** | 35 | 97.14% | 97.14% | 0.0286 | 0.0029 |
| **Rata-rata Makro** | 201 | **78.61%** | **86.57%** | **0.1814** | **0.1422** |

---

## 4. Analisis Error & Karakteristik Tesseract OCR

### A. Analisis 4 Misses Nomor Sertifikat pada Scan
Dari 33 sertifikat scan yang memiliki nomor di Ground Truth, hanya 4 yang tidak cocok persis:
1. `2160238_221065_skp`:
   - **Pred:** `''` | **GT:** `'00003/DPKKA.S/I/2024'`
   - **Penyebab:** Teks nomor pada scan memiliki resolusi rendah dan font sans-serif tipis, sehingga Tesseract tidak menghasilkan token angka yang cukup untuk trigger regex DPKKA.
2. `2439919_221065_skp`:
   - **Pred:** `'106/STF.E/HOLOGY7.0/x1t/2024'` | **GT:** `'106/STF.E/HOLOGY7.0/XI/2024'`
   - **Penyebab:** OCR confusion pada angka Romawi `XI` terbaca `x1t`. Normalizer Romawi tidak memetakan `x1t` karena karakter `t` di akhir.
3. `2955331_219642_skp`:
   - **Pred:** `'177/LPI/SSP/VIII/2023'` | **GT:** `'177/LPI/SSP/VII//2023'`
   - **Penyebab:** Typo internal pada Ground Truth v9 yang memiliki double slash `//`. Prediksi Tesseract sebenarnya valid secara fisik.
4. `NIC_Faiz`:
   - **Pred:** `'011/C/NACOESTA4.0/HIMASTA/UNIMUS/VI/2025'` | **GT:** `'011/C/NACOESTA4.0HIMASTA/UNIMUS/VI/2025'`
   - **Penyebab:** Tesseract menyisipkan pemisah `/` antara kode versi `4.0` dan nama himpunan `HIMASTA`.

### B. Analisis Layout Tesseract vs RapidOCR
1. **Konsistensi Baris:** Tesseract multi-PSM (`""`, `--psm 6`, `--psm 11`) memberikan cakupan teks vertikal yang lebih stabil daripada RapidOCR, terutama pada blok tanda tangan dan nomor sertifikat yang terpisah jauh di header.
2. **Anti-Bleed Activity:** Jendela batas `extract_activity_v9` berhasil membatasi penangkapan nama kegiatan (73.47% exact), menghindari kontaminasi kata pengantar ("diberikan kepada", "atas partisipasinya").

---

## 5. Profil Latensi & Efisiensi Komputasi

| Engine / Konfigurasi | Avg Latency (Scan-49) | Median Latency | Max Latency | RAM / Resource |
|---|:---:|:---:|:---:|:---:|
| **Tesseract-Primary (Multi-PSM)** | **4.74 s** | **3.72 s** | **23.96 s** | CPU Native, 0 OOM |
| RapidOCR + Tesseract (`baseline_rapid_tess`) | 8.61 s | 7.83 s | 39.78 s | 2x Engine Overhead |
| DocTR Probe (OCR-006) | 7.50 s | — | — | RSS ~1.3 GB |
| LFM-2.5-VL-3B (OCR-008) | 77.00 s | — | — | VRAM ~4.9 GB |

> **Efisiensi:** Tesseract-Primary memangkas latensi scan sebesar **45.0%** (dari 8.61s menjadi 4.74s) dibandingkan baseline ganda `rapid_tess`, sekaligus memberikan akurasi yang jauh melampaui baseline.

---

## 6. Kesimpulan & Rekomendasi
1. **Viabilitas Tinggi:** Tesseract terbukti sangat layak menjadi primary OCR engine pada dokumen sertifikat ketika didukung post-processing v4.x.
2. **Kombinasi Rekomendasi:**
   - Untuk deployment CPU-only ringan, Tesseract-Primary + Composite v4.x merupakan konfigurasi optimal (cepat, stabil, zero GPU dependency).
   - Normalizer Romawi pada `normalize_nomor_v6` dapat diperluas untuk menangani akhiran noise OCR seperti `x1t` -> `XI`.
