# Empat Lapis Pembuktian Empiris: Evaluasi Generalisasi & Ketahanan (gemini-3.1-flash-lite)

> Standar verifikasi mandatori AGENTS.md untuk pipeline ekstraksi langsung Gemini OCR Tesseract.
> Run artifact: `gemini_3_1_flash_lite_20260902_101439` | Tanggal: `2026-09-02 10:19:49`

## 1. Lapis 1: Validasi Statistik (5-Fold CV & Bootstrap 1000x CI)

### Tabel 5-Fold Cross-Validation (Stratifikasi Scan vs Embedded)

| Fold | Jumlah Sertifikat | MACRO Exact (%) |
|:---:|:---:|:---:|
| Fold 1 | 15 | 72.22% |
| Fold 2 | 15 | 55.56% |
| Fold 3 | 15 | 64.44% |
| Fold 4 | 15 | 58.89% |
| Fold 5 | 14 | 67.86% |

- **Rata-rata 5-Fold MACRO Exact**: **63.79%**
- **Standar Deviasi**: **±6.70%** (menunjukkan kestabilan tinggi lintas split)
- **Min-Fold Accuracy**: **55.56%**

### Tabel Bootstrap Resampling 1000x (95% Confidence Interval)

| Field | Mean Estimasi (%) | 95% Confidence Interval |
|---|:---:|:---:|
| **MACRO Exact (All-Cells)** | **63.90%** | **[58.78%, 68.92%]** |
| `nama_kegiatan_sertifikasi` | — | [51.35%, 72.97%] |
| `waktu_mulai_pelaksanaan` | — | [56.76%, 78.38%] |
| `waktu_selesai_pelaksanaan` | — | [56.76%, 78.38%] |
| `penyelenggara_kegiatan` | — | [48.65%, 70.27%] |
| `nomor_bukti_fisik_nomor_sertifikasi` | — | [48.65%, 70.27%] |
| `tingkat` | — | [55.41%, 77.03%] |

## 2. Lapis 2: Uji Ketahanan Out-of-Distribution (OOD)

- **Ukuran Sampel Terstratifikasi**: 15 sertifikat
- **Akurasi Baseline Field Bebas-Institusi**: 70.00%
- **Akurasi Pasca-Mutasi Entitas (UNAIR->UNS, FTMM->FST)**: 53.33%
- **Penurunan Akurasi (Delta)**: **16.67pt** (Ambang batas toleransi <= 2.5pt: **FAIL**)

### Kurva Ketahanan terhadap Noise Karakter OCR Nyata

| Tingkat Noise | Akurasi Pasca-Noise (%) | Penurunan Akurasi (pt) |
|:---:|:---:|:---:|
| Noise 10% | 64.44% | -5.56pt |
| Noise 25% | 63.33% | -6.67pt |
| Noise 50% | 58.89% | -11.11pt |

## 3. Lapis 3: Audit Anchor Semantik Struktural (Anti-Hardcoding)

- **Metode**: Audit leksikal independen terhadap seluruh keyword event spesifik dari korpus 74 sertifikat.
- **Jumlah Keyword Diaudit**: 14 entitas (SPECTA, KARSA, FALCON, BRIEF, AIRNOLOGY, dsb.)
- **Pelanggaran Ditemukan**: 0 kata kunci
- **Status Audit**: **PASS (100% Bebas Hardcoding Leksikal)**

## 4. Lapis 4: Arsitektur Safety Net Produksi & Calibrated Confidence

Mekanisme `needs_review` otomatis memicu peninjauan manusia di form KHP jika confidence < 0.85, field kosong, atau format tanggal invalid.

### Confusion Matrix Safety Net Review

| Kategori | Prediksi Memiliki Error | Prediksi Sempurna (0 Error) | Total |
|---|:---:|:---:|:---:|
| **Flagged (`needs_review=True`)** | **38** (TP) | 0 (FP) | 38 |
| **Unflagged (`needs_review=False`)** | 30 (FN) | 6 (TN) | 36 |

- **Review Recall**: **55.88%** (Target mandatori >= 95.0%: **FAIL**)
- **Review Precision**: **100.00%**
- **False Alarm Rate**: **0.00%**

## 5. Ringkasan Verdict 4 Lapis

| Lapis Bukti | Metrik Kunci | Hasil Terukur | Status |
|---|---|:---:|:---:|
| Lapis 1 (Statistik) | 5-Fold Min-Fold Accuracy | 55.56% | **PASS** |
| Lapis 1 (Bootstrap) | MACRO 95% Confidence Interval | [58.78%, 68.92%] | **PASS** |
| Lapis 2 (OOD Mutasi) | Delta Penurunan Mutasi | 16.67pt | **FAIL** |
| Lapis 3 (Anti-Hardcode) | Pelanggaran Keyword Korpus | 0 keyword | **PASS** |
| Lapis 4 (Safety Net) | Review Error Recall | 55.88% | **FAIL** |