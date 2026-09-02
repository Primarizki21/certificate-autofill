# Handoff v48 — Benchmark & Validasi Encoder NER: mDeBERTa-v3-base vs XLM-RoBERTa-large (5-Fold Stratified OOF)

> Supersedes `docs/handoff_v47.md`. Sesi ini mengimplementasikan, menstabilkan pelatihan, serta mengevaluasi secara ketat
> dua arsitektur encoder multilingual bertaraf industri (`microsoft/mdeberta-v3-base` dan `facebookai/xlm-roberta-large`)
> untuk ekstraksi entitas form sertifikat mahasiswa pada teks OCR Tesseract menggunakan 5-Fold Stratified Out-of-Fold (OOF)
> cross-validation, evaluasi Matcher v2 (frozen baseline), Bootstrap Confidence Interval 1000x, dan uji ketahanan Out-of-Distribution (OOD).

---

## 1. Ringkasan Eksekutif & Temuan Kunci

1. **Peningkatan Substansial vs Baseline NER v1**:
   - Baseline historis NER v1 (IndoBERT fine-tuning) hanya mencatat akurasi exact **12.8%** (fuzzy 38.2%).
   - Model **`mdeberta-v3-base`** (86M parameter) mencatat framework exact **34.84%** (fuzzy **51.29%**), melonjak **+22.04pt** vs NER v1.
   - Model **`xlm-roberta-large`** (560M parameter) mencatat framework exact **43.55%** (fuzzy **55.48%**), melonjak **+30.75pt** vs NER v1.
   - Pada deteksi `nama_kegiatan_sertifikasi`, fuzzy accuracy kedua encoder mencapai **70.27%** (52/74 dokumen cocok secara substansial).

2. **Diagnosa & Solusi Ketidakstabilan Numerik (Root Cause Optimization)**:
   - **Akar Masalah**: Model DeBERTa-v3 secara default dimuat dalam `torch.float16` dari HuggingFace Hub. Saat dipadukan dengan AdamW standar tanpa mixed-precision scaling, terjadi *numerical overflow* instan pada langkah awal (`logits` & parameter menjadi `NaN`).
   - **Solusi**:
     1. Konversi eksplisit seluruh bobot encoder ke `torch.float32` melalui `model.float()`.
     2. Penggunaan optimizer memory-efficient `adafactor` yang memangkas memori status optimizer dari ~4.5GB menjadi ~50MB, sehingga XLM-RoBERTa-large (560M params) dapat dilatih pada VRAM 8GB RTX 5050 tanpa OOM (puncak VRAM 7.09GB).
     3. Soft-capping pembobotan kelas *square-root inverse frequency* (`min(sqrt(max/count), 10.0)`) untuk mencegah ledakan gradien pada entitas langka.
     4. Sanity overfit set (2 dokumen) berhasil mencapai **100.0% token recall** (25/25 token non-O terprediksi sempurna, finite parameter delta).

3. **Keputusan Arsitektur & Rekomendasi Deployment**:
   - **Verdict**: **PASS (Benchmark Eksplorasi Encoder OOF)**, namun **TIDAK DIPROMOSIKAN KE PRODUKSI**.
   - Meskipun encoder besar melompat tinggi dibanding NER v1, akurasi exact out-of-fold (43.55%) masih berada jauh di bawah pipeline rule-based deterministik Composite v4.x (**77.10%**) maupun direct LLM Gemini-3.1-flash-lite (**63.24%**).
   - Waktu pelatihan dan inferensi encoder lokal (~13 menit untuk 5 fold) tidak memberikan efisiensi yang sebanding dengan biaya sangat murah direct Gemini (<Rp10/sertifikat, 1.36s/sertifikat).
   - Arsitektur produksi tetap dipertahankan pada **Option A (`ENABLE_TESSERACT_GEMINI=true`)** dengan fallback offline Combined v4.2.

---

## 2. Tabel Komparasi Hasil Benchmark (74 Dokumen, 310 Sel Framework)

Evaluasi dilakukan pada 74 korpus teks Tesseract Standalone (`tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/extracted_texts/`) terhadap Ground Truth v9 menggunakan Matcher v2 (frozen baseline).

| Metrik Evaluasi | Baseline NER v1 (IndoBERT) | `mdeberta-v3-base` (86M) | `xlm-roberta-large` (560M) | Direct Gemini 3.1 Flash Lite | Composite v4.x (Pure Rule/OCR) |
|---|:---:|:---:|:---:|:---:|:---:|
| **MACRO Exact (Framework)** | **12.8%** | **34.84%** (+22.04) | **43.55%** (+30.75) | **63.24%** | **77.10%** |
| **MACRO Fuzzy (Framework)** | 38.2% | **51.29%** (+13.09) | **55.48%** (+17.28) | **73.78%** | **85.16%** |
| **Bootstrap 95% CI Exact** | — | [28.95%, 40.92%] | [37.17%, 50.00%] | [58.78%, 68.92%] | [72.10%, 81.80%] |
| **Nama Kegiatan (Exact / Fuzzy)** | — | 25.68% / 70.27% | **35.14% / 70.27%** | 62.16% / 78.38% | 76.00% / 82.00% |
| **Nomor Sertifikat (Exact / Fuzzy)**| — | 55.77% / 55.77% | **59.62% / 59.62%** | 59.46% / 59.46% | 89.47% / 89.47% |
| **Penyelenggara (Exact / Fuzzy)** | — | 25.68% / 50.00% | **37.84% / 52.70%** | 59.46% / 75.68% | 36.00% / 68.00% |
| **Tanggal Mulai (Exact / Fuzzy)** | — | 32.73% / 32.73% | **45.45% / 45.45%** | 67.57% / 67.57% | 90.00% / 90.00% |
| **Tanggal Selesai (Exact / Fuzzy)**| — | 41.82% / 41.82% | **45.45% / 45.45%** | 67.57% / 67.57% | 90.00% / 90.00% |
| **Waktu Training (5-Fold)** | ~4 menit | 12.2 menit (734s) | 13.2 menit (794s) | 0 detik (Inference only) | 0 detik (Rule-based) |
| **VRAM Peak (RTX 5050 8GB)** | ~2.5 GB | 4.08 GB | 7.09 GB (Adafactor+GC) | 0 GB (Cloud API) | 0 GB (CPU/OCR) |

---

## 3. Empat Lapis Pembuktian Empiris (Generalisasi & Robustness)

Sesuai standar evaluasi ketat pada `AGENTS.md`, eksperimen encoder diverifikasi melalui 4 lapis pembuktian:

### Lapis 1: Validasi Statistik (5-Fold Stratified Cross-Validation & Bootstrap CI)
- Pembagian data dilakukan secara *stratified* berdasarkan kelengkapan field pada 74 sertifikat dataset.
- Variasi performa per-fold:
  * `mdeberta-v3-base`: Fold 1 (32.9%), Fold 2 (36.1%), Fold 3 (33.8%), Fold 4 (37.2%), Fold 5 (34.3%).
  * `xlm-roberta-large`: Fold 1 (42.5%), Fold 2 (45.1%), Fold 3 (41.8%), Fold 4 (46.2%), Fold 5 (42.2%).
- Resampling Bootstrap 1000x:
  * `mdeberta-v3-base`: Mean = 34.78%, 95% Confidence Interval = **[28.95%, 40.92%]**.
  * `xlm-roberta-large`: Mean = 43.57%, 95% Confidence Interval = **[37.17%, 50.00%]**.

### Lapis 2: Uji Ketahanan Out-of-Distribution (OOD Stress Testing)
Pengujian dievaluasi pada 236 sel field bebas-institusi (*institution-free fields*: tanggal, nomor, kegiatan) dengan mutasi entitas dan injeksi noise kebingungan karakter OCR (`5↔S`, `8↔B`, `0↔O`, `1↔I`):

| Tingkat Gangguan / Mutasi | `mdeberta-v3-base` Exact (Drop) | `xlm-roberta-large` Exact (Drop) |
|---|:---:|:---:|
| **Clean Baseline** | 37.71% (0.0pt) | 45.34% (0.0pt) |
| **Entity Mutation (UNAIR→UNS dll)** | 30.51% (-7.20pt) | 37.71% (-7.63pt) |
| **OCR Noise 10%** | 25.00% (-12.71pt) | 29.24% (-16.10pt) |
| **OCR Noise 25%** | 20.34% (-17.37pt) | 19.49% (-25.85pt) |
| **OCR Noise 50%** | 10.17% (-27.54pt) | 12.29% (-33.05pt) |

*Catatan*: Penurunan pada uji mutasi entitas sebagian besar disebabkan oleh hilangnya token anchor yang dikenal pada data latih, mengonfirmasi bahwa model encoder 86M–560M membutuhkan volume data latih yang jauh lebih besar agar representasi semantiknya tidak bergantung pada nama institusi tertentu.

### Lapis 3: Pemetaan Token-to-Entity Berbasis Sliding Window
- Implementasi *subword token alignment* menggunakan `fast_tokenizer` offset mapping dan `overflow_to_sample_mapping` (max length 512, stride 64) untuk menangani dokumen sertifikat panjang tanpa memotong teks di akhir halaman.
- Decoding entitas menggunakan skema standard BIO chunking (`B-*` memulai entitas, `I-*` melanjutkan) dengan agregasi confidence per kata untuk menyaring prediksi bernilai rendah.

### Lapis 4: Jaring Pengaman & Zero Blast Radius Produksi
- Kode eksperimen berada mandiri di `tests/benchmark_ner_encoders.py` dan `tests/test_ner_encoder_experiment.py`.
- **Produksi tidak tersentuh**: Layanan produksi `backend/app/services/` tetap menggunakan konfigurasi aktif `ENABLE_TESSERACT_GEMINI=true` (Option A) dengan jaring pengaman fallback otomatis ke pipeline offline.
- Seluruh 169 unit test di `tests/` lulus pengujian tanpa regresi (`169 passed, 0 failed`).

---

## 4. File yang Dibuat & Diubah

1. `tests/benchmark_ner_encoders.py`: Runner benchmark komparatif 5-fold cross-validation untuk encoder multilingual transformer dengan loss terbobot, handling FP32/BF16, Adafactor optimizer, dan integrasi Matcher v2.
2. `tests/test_ner_encoder_experiment.py`: 6 unit test untuk validasi dataset alignment, inverse frequency weighting, decoding entitas, dan finite-check loss trainer.
3. `scripts/generate_runs_summary.py`: Dukungan pengindeksan otomatis untuk direktori run berawalan `ner_encoder_`.
4. `docs/report/runs_summary.md` & `docs/report/runs_summary.csv`: Hasil eksekusi `ner_encoder_facebookai_xlm_roberta_large_20260902_152248` (43.5%) dan `ner_encoder_microsoft_mdeberta_v3_base_20260902_150927` (34.8%) tercatat dalam rekam jejak benchmark proyek.
5. `docs/experiments_ledger.md`: Ditambahkan entri resmi `NER-ENCODER-001`.
6. `docs/handoff_v48.md`: Dokumen handoff ini.

---

## 5. Open Frontier & Rekomendasi Selanjutnya

1. **Jalur Utama Produksi**:
   - Memantau operasional `ENABLE_TESSERACT_GEMINI=true` di lingkungan produksi saat pengguna mengunggah variasi sertifikat baru.
   - Evaluasi kuota dan latensi Google API secara berkala.
2. **Jalur Eksperimen Offline (Jika Dibutuhkan)**:
   - Jika tim menginginkan model offline berukuran kecil yang melampaui rule-based tanpa memanggil cloud API, opsi yang lebih menjanjikan dibanding Token Classification murni adalah:
     * *Prompted Local SLM* (misal Qwen2.5-1.5B-Instruct atau Gemma-2-2B via Ollama / vLLM lokal) yang langsung mengekstrak JSON terstruktur, memanfaatkan penalaran teks utuh daripada klasifikasi token per token.
3. **Penyimpanan Bobot**:
   - Checkpoint per-fold disimpan di `tests/benchmark_runs/ner_encoder_*/fold_*/checkpoint/` dan dapat digunakan bila diperlukan analisis kesalahan token lebih lanjut.

---

## 6. Supersession Note

Supersedes `docs/handoff_v47.md`.
Status pipeline saat ini: **Produksi tetap stabil pada Option A (`ENABLE_TESSERACT_GEMINI=true`), benchmark encoder multilingual selesai dan terdokumentasi lengkap tanpa regresi kode produksi**.
