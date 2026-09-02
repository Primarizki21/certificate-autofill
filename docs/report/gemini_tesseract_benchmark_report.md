# Laporan Komparatif: Direct Tesseract-to-Gemini Extraction Benchmark

> Evaluasi komparatif end-to-end ekstraksi 6 field sertifikat KHP langsung dari teks mentah OCR Tesseract
> menggunakan 3 model Google Gemini (`gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`).
> Tanggal evaluasi: `2026-09-02 10:18:22` | Kurs acuan: Rp17,758.00 per USD.

## 1. Tabel Komparasi Utama

| Model | MACRO Exact (6-Field) | MACRO Fuzzy (6-Field) | Framework Exact (5-Field) | Scan-49 Exact | Emb-25 Exact | Avg Tokens/Cert | Avg Cost/Cert (IDR) | Avg Latency |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`gemini-2.5-flash`** | **58.56%** | 71.40% | 57.84% | 59.86% | 56.00% | 1,946.0 | Rp38.94 | 4.62s |
| **`gemini-2.5-flash-lite`** | **58.78%** | 66.44% | 61.89% | 59.18% | 58.00% | 1,369.7 | Rp3.26 | 1.32s |
| **`gemini-3.1-flash-lite`** | **63.74%** | 72.75% | 63.24% | 64.97% | 61.33% | 1,368.9 | Rp9.50 | 1.36s |

## 2. Perbandingan Akurasi per Field (Exact %)

| Model | Nama Kegiatan | Nomor Sertifikat | Penyelenggara | Tanggal Mulai | Tanggal Selesai | Tingkat |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `gemini-2.5-flash` | 46.0% | 54.0% | 54.0% | 67.6% | 67.6% | 62.2% |
| `gemini-2.5-flash-lite` | 58.1% | 56.8% | 60.8% | 66.2% | 67.6% | 43.2% |
| `gemini-3.1-flash-lite` | 62.2% | 59.5% | 59.5% | 67.6% | 67.6% | 66.2% |

## 3. Analisis Biaya dan Efisiensi Token

| Model | Total Tokens | Total Biaya (USD) | Total Biaya (IDR) | Tarif Input / 1M | Tarif Output / 1M |
|---|:---:|:---:|:---:|:---:|:---:|
| `gemini-2.5-flash` | 144,005 | $0.1623 | Rp2,881.90 | $0.30 | $2.50 |
| `gemini-2.5-flash-lite` | 101,359 | $0.0136 | Rp241.17 | $0.10 | $0.40 |
| `gemini-3.1-flash-lite` | 101,298 | $0.0396 | Rp703.27 | $0.25 | $1.50 |

## 4. Kesimpulan dan Model Pemenang

- **Model Pemenang**: `gemini-3.1-flash-lite` dengan MACRO exact **63.74%** (Framework: 63.24%).
- **Efisiensi Finansial**: Biaya rata-rata hanya **Rp9.50 per sertifikat** dengan latensi 1.36s.