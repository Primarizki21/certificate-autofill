# Laporan Evaluasi: Tesseract-Primary OCR (Scan-49 + Digital-25) + Composite v4.x Suite
> **Tanggal Run:** 2026-09-02 08:09:25  
> **Dataset:** 74 Sertifikat (49 Scan, 25 Digital Embedded)  
> **Ground Truth:** `Ground_Truth_Sertifikat_v9.csv` | **Evaluator:** Matcher v2 (`tests/matchers.py`)  
> **Arsitektur Pipeline:** Tesseract-Primary (Multi-PSM) + Composite v4.x Candidate (`apply_composite_v4_candidate`)  
> **Organizer variant:** `v8` (Tesseract Organizer v8)  
> **Organizer routing:** `v8 on scan and v2 on digital embedded`

---

## 1. Ringkasan Eksekutif

Eksperimen ini mengevaluasi performa Tesseract sebagai engine OCR utama (*primary standalone OCR*) yang dipasangkan dengan suite post-processing modern **Composite v4.x (B8)**:
- **Activity:** Structural semantic grammar anchors & anti-bleed bounds (`extract_activity_v9`)
- **Nomor:** Length-preserving DPKKA cleaner & gated Roman numeral month repairs (`normalize_nomor_v6`)
- **Penyelenggara:** Tesseract Organizer v8
- **Tanggal:** Date extractor v2 multi-day span parser (`extract_dates_v2`)
- **Tingkat:** Hardened contextual router disambiguation (`route_with_disambiguation_v7`)

Hasil run:
- **Framework 5-Field (Scan-49):** MACRO exact **80.60%** (fuzzy **89.05%**).
- **Nomor Sertifikat (Scan-49):** **29/33** exact.
- **Nama Kegiatan (Scan-49):** **36/49** exact.
- **Penyelenggara (Scan-49):** **29/49** exact.
- **All-Cells 6-Field (Scan-49):** MACRO exact **68.71%** (fuzzy **74.83%**).
- **All-Cells 6-Field (All-74):** MACRO exact **68.69%** (fuzzy **73.65%**).
- **Framework 5-Field (All-74):** MACRO exact **78.39%** (fuzzy **85.16%**).

---

## 2. Tabel Komparasi 4 Arah (Scan-49 Subset)

| Metrik (Scan-49) | Baseline Rapid+Tess (v9) | Rapid-Only + v4.x (HYB-003) | **Tesseract-Primary + Tesseract Organizer v8** | Delta vs Baseline |
|---|:---:|:---:|:---:|:---:|
| **MACRO Exact (5-Field)** | 47.26% (95/201) | 50.75% | **80.60%** (162/201) | **+33.34pt** |
| **MACRO Fuzzy (5-Field)** | 57.21% | 63.87% | **89.05%** (179/201) | **+31.84pt** |
| Nama Kegiatan exact | 6.12% (3/49) | 6.12% | **73.47%** (36/49) | **+67.35pt** |
| Nomor Sertifikat exact | 57.58% (19/33) | 57.58% | **87.88%** (29/33) | **+30.30pt** |
| Penyelenggara exact | 26.53% (13/49) | 34.69% | **59.18%** (29/49) | **+32.65pt** |
| Tanggal Mulai exact | 85.71% (30/35) | 85.71% | **97.14%** (34/35) | **+11.43pt** |
| Tanggal Selesai exact | 85.71% (30/35) | 85.71% | **97.14%** (34/35) | **+11.43pt** |
| Tingkat exact (6-Field) | — | — | **81.63%** (40/49) | Baseline baru |

---

## 3. Rincian Metrik Jarak Edit (WER & CER)

| Field | Total Sel | Exact Acc | Fuzzy Acc | Avg WER | Avg CER |
|---|:---:|:---:|:---:|:---:|:---:|
| **Nama Kegiatan** | 49 | 73.47% | 87.76% | 0.1686 | 0.1506 |
| **Nomor Sertifikat** | 33 | 87.88% | 87.88% | 0.1212 | 0.0350 |
| **Penyelenggara** | 49 | 59.18% | 79.59% | 0.3271 | 0.2794 |
| **Tanggal Mulai** | 35 | 97.14% | 97.14% | 0.0286 | 0.0029 |
| **Tanggal Selesai** | 35 | 97.14% | 97.14% | 0.0286 | 0.0029 |
| **Rata-rata Makro** | 201 | **80.60%** | **89.05%** | **0.1507** | **0.1116** |

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
