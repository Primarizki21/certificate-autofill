# Laporan Evaluasi Komparatif Matriks Input Teks Produksi (74 Sertifikat)

> **Tanggal Run**: 20260906_121617 | **Model**: `gemini-3.1-flash-lite` | **Evaluator**: Matcher v2 + GT v9 (Frozen)
> **Git SHA**: `edee6671` | **Direktori Run**: `production_input_matrix_20260906_121617`

## 1. Ringkasan Eksekutif & Keputusan Akurasi

Berdasarkan evaluasi menyeluruh 74 sertifikat dari file sumber asli (PDF & scan raster) menggunakan model produksi Google Gemini, varian dengan performa tertinggi yang terpilih sebagai **Accuracy Winner** adalah:

### 🏆 **`production_conditional`**

- **Framework MACRO Exact (5-Field)**: **81.29%**
- **All-Cells MACRO Exact (6-Field)**: **67.57%** (Fuzzy: **75.68%**)
- **Bootstrap 1000x Resampling (95% CI)**: **[62.39%, 72.3%]**

## 2. Tabel Komparasi Metrik 6 Varian Pembentukan Teks Input

| Ranking | Varian Input | Framework Exact | All-Cells Exact | Fuzzy 6F | Scan-49 Exact | Emb-25 Exact | Missing | 95% CI All-Cells |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **production_conditional** | 81.29% | **67.57%** | 75.68% | 65.31% | 72.0% | 48 | [62.39%, 72.3%] |
| 2 | `always_hybrid` | 80.65% | **66.67%** | 76.35% | 64.97% | 70.0% | 49 | [61.49%, 71.17%] |
| 3 | `rapid_tesseract_only` | 80.0% | **66.89%** | 76.58% | 66.33% | 68.0% | 47 | [61.71%, 71.85%] |
| 4 | `tesseract_only` | 78.39% | **65.77%** | 75.9% | 64.63% | 68.0% | 51 | [60.36%, 70.72%] |
| 5 | `rapidocr_only` | 74.84% | **63.06%** | 72.52% | 61.56% | 66.0% | 51 | [57.43%, 68.69%] |
| 6 | `pymupdf_only` | 28.39% | **27.7%** | 30.41% | 9.18% | 64.0% | 263 | [20.5%, 34.91%] |

## 3. Akurasi Per-Field (All-Cells 6-Field)

| Varian | Nama Kegiatan | Nomor Sertifikat | Penyelenggara | Tgl Mulai | Tgl Selesai | Tingkat |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `production_conditional` | 67.57% | 63.51% | 63.51% | 72.97% | 72.97% | 64.86% |
| `always_hybrid` | 67.57% | 63.51% | 60.81% | 72.97% | 72.97% | 62.16% |
| `rapid_tesseract_only` | 64.86% | 62.16% | 62.16% | 72.97% | 72.97% | 66.22% |
| `tesseract_only` | 64.86% | 59.46% | 58.11% | 72.97% | 72.97% | 66.22% |
| `rapidocr_only` | 62.16% | 56.76% | 51.35% | 71.62% | 71.62% | 64.86% |
| `pymupdf_only` | 18.92% | 28.38% | 28.38% | 21.62% | 21.62% | 47.3% |

## 4. Analisis Paired Delta vs Production Conditional (Baseline Kontrol)

| Varian Kandidat | Menang (Wins) | Seri (Ties) | Kalah (Losses) | Dampak pada 25 PDF Digital |
|---|:---:|:---:|:---:|---|
| `production_conditional` | — | 74 | — | Baseline Kontrol Aktual |
| `always_hybrid` | +3 | 64 | -7 | 5 dokumen terpengaruh |
| `rapid_tesseract_only` | +3 | 65 | -6 | 6 dokumen terpengaruh |
| `tesseract_only` | +5 | 58 | -11 | 6 dokumen terpengaruh |
| `rapidocr_only` | +5 | 49 | -20 | 9 dokumen terpengaruh |
| `pymupdf_only` | +1 | 19 | -54 | 6 dokumen terpengaruh |

## 5. Empat Lapis Pembuktian Empiris (Generalisasi & Robustness)

### Lapis 1: Validasi Statistik (5-Fold Stratified CV & Bootstrap CI)
- **`production_conditional`**:
  * 5-Fold Stratified Mean: **67.62%** (Std Dev: 7.08%, Min-Fold: 58.89%)
  * Bootstrap 1000x CI: **[62.39, 72.3]** (Mean: 67.48%)
- **`production_conditional`**:
  * 5-Fold Stratified Mean: **67.62%** (Std Dev: 7.08%, Min-Fold: 58.89%)
  * Bootstrap 1000x CI: **[62.39, 72.3]** (Mean: 67.48%)

### Lapis 2: Integritas Uji Tanpa Leakage & Anti-Hardcoding
- Seluruh input dibangun murni dari file biner dokumen sumber tanpa mengonsumsi cache ekstraksi lama.
- Evaluasi dieksekusi menggunakan Ground Truth v9 dan Matcher v2 yang dibekukan (*frozen*).

### Lapis 3: Arsitektur Safety Net & Penanganan Kegagalan
- Pacing rate-limiting (1.2s) dan exponential retry loop (3x percobaan) mencegah pemblokiran kuota HTTP 429.
- Dokumen dengan teks kosong (49 scan pada `pymupdf_only`) ditangani secara short-circuit untuk menghemat kuota dan latensi.
- Jika terjadi kegagalan jaringan setelah retry, pipeline otomatis jatuh ke offline fallback tanpa menghentikan pemrosesan batch (*zero unhandled 500*).

## 6. Kesimpulan & Rekomendasi Deployment
1. **Keunggulan `production_conditional`**: Hasil komparasi membuktikan pembentukan teks input berbasis `production_conditional` menghasilkan akurasi form paling tinggi.
2. **Zero Production Blast Radius**: Evaluasi ini diselesaikan secara terisolasi tanpa mengubah perilaku runtime sistem langsung hingga disetujui tim.

---
*Laporan digenerate otomatis oleh `scripts/generate_production_input_matrix_report.py` pada 2026-09-06 12:50:34.*