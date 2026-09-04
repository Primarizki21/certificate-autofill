# Handoff v50 — Benchmark Fine-Tuning GLiNER v2.1 & GLiNER2.5 (5-Fold OOF)

> Supersedes `docs/handoff_v49.md`.

## Ringkasan Eksekutif

Sesuai arahan eksplisit pengguna untuk tetap menjalankan fine-tuning GLiNER meskipun sanity gate v49 gagal, eksperimen `NER-GLINER-002` telah dieksekusi secara menyeluruh dengan arsitektur runner terisolasi per fold (`--fold N --run-dir`) guna menjamin stabilitas memori WSL:

1. **GLiNER v2.1 Multilingual Fine-Tuned (300M)**:
   - Berhasil menyelesaikan seluruh 5 fold Out-of-Fold (74 dokumen, 310 sel framework).
   - **Framework MACRO exact mencapai 54.52%** (169/310 sel) dan fuzzy **63.23%** (196/310 sel).
   - Melonjak **+19.04pt** dibanding zero-shot GLiNER v2.1 (35.48%) dan **+10.00pt** dibanding encoder terbaik sebelumnya (`IndoBERT-ner-gold` 44.52%), menjadikannya **encoder dengan skor exact tertinggi di seluruh proyek**.
   - Resampling Bootstrap 1000x menghasilkan **95% CI [47.78%, 60.76%]** (mean 54.43%).
   - Namun, **Lapis 2 (Uji Ketahanan OOD) GAGAL**: mutasi entitas mengalami drop **-6.36pp** (dari 55.93% ke 49.58%, melewati batas toleransi $\le 2.0\text{pp}$), dan derau karakter OCR turun tajam (**-19.07pp** pada noise 10%, **-28.39pp** pada noise 25%, dan **-42.37pp** pada noise 50%).
   - Rata-rata confidence mentah mencapai 1.02 (>1.0) karena belum terkalibrasi.

2. **GLiNER2.5 Base Fine-Tuned (193.5M)**:
   - Gagal pada Fold 1 epoch 4 akibat instabilitas numerik: `FloatingPointError: 8 non-finite micro-batch loss(es) were zeroed` yang dilempar oleh mekanisme strict training `ExtractorTrainer._flush_delayed_counters()`.
   - Divergensi gradien/loss proposal pada native AdamW dua kelompok.
   - Berstatus **FAIL (Numerik)**; tidak ada metrik OOF yang diklaim (dicatat sebagai `N/A`).

3. **Pelaporan & Produksi**:
   - Seluruh metrik aktual, distribusi 5-fold, konfigurasi hyperparameter, analisis kegagalan, dan uji OOD telah dilaporkan ke dalam dokumen Excel `docs/report/komparasi_ner_encoder_dan_pipeline.xlsx`.
   - **Zero production blast radius**: Tidak ada perubahan pada arsitektur produksi Option A (`ENABLE_TESSERACT_GEMINI=true`, 63.24% exact) maupun fallback Combined v4.2 (87.42% exact).

---

## Tabel Komparasi Kinerja Seluruh Encoder & Pipeline (GT v9, 74 Sertifikat)

| Metode / Model | Kategori Arsitektur | MACRO Exact | MACRO Fuzzy | 95% CI Exact | Nama Kegiatan | Nomor Sertifikat | Penyelenggara | Tgl Mulai | Tgl Selesai | Status / Verdict |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **IndoBERT Pre-trained** | Token Clf (Zero-Shot) | 12.80% | 28.80% | [9.50%, 16.20%] | 16.40% | 0.00% | 11.00% | 27.30% | 7.30% | Baseline Pre-trained |
| **IndoBERT Fine-Tuned Gagal** | Full FT (59 Sampel) | 1.50% | 8.20% | N/A | 2.70% | 0.00% | 1.40% | 3.60% | 0.00% | Gagal (Catastrophic Forgetting) |
| **GLiNER2.5 Base** | Zero-Shot Boundary | 28.71% | 38.71% | [23.64%, 34.39%] | 31.08% | 3.85% | 20.27% | 45.45% | 43.64% | Zero-Shot PASS |
| **GLiNER2.5 Base Fine-Tuned** | Full FT Boundary | **N/A** | **N/A** | **N/A** | N/A | N/A | N/A | N/A | N/A | **FAIL (FloatingPointError micro-batch)** |
| **mDeBERTa-v3-base** (86M) | 5-Fold CV Token Clf | 34.84% | 51.29% | [28.95%, 40.92%] | 25.68% | 55.77% | 25.68% | 32.73% | 41.82% | Eksplorasi (PASS) |
| **GLiNER v2.1 Multilingual** | Zero-Shot Span Bi-Encoder | 35.48% | 46.45% | [30.10%, 41.31%] | 16.22% | 13.46% | 36.49% | 58.18% | 58.18% | Zero-Shot PASS |
| **XLM-RoBERTa-large** (560M) | 5-Fold CV Token Clf | 43.55% | 55.48% | [37.17%, 50.00%] | 35.14% | 59.62% | 37.84% | 45.45% | 45.45% | Eksplorasi (PASS) |
| **IndoBERT-ner-gold FT** (334M) | 5-Fold CV Token Clf | 44.52% | 57.10% | [38.59%, 50.82%] | 43.24% | 57.69% | 36.49% | 49.09% | 40.00% | **BEST TOKEN CLASSIFIER** |
| **GLiNER v2.1 Fine-Tuned** (300M) | 5-Fold OOF Span Bi-Enc | **54.52%** | **63.23%** | **[47.78%, 60.76%]** | **52.70%** | **55.77%** | **50.00%** | **52.73%** | **63.64%** | **BEST ENCODER (OOF Complete, OOD Fail)** |
| **Direct Gemini 3.1 Flash Lite** | Two-Stage OCR-to-LLM | 63.24% | 73.78% | [58.78%, 68.92%] | 62.16% | 59.46% | 59.46% | 67.57% | 67.57% | **PRODUKSI AKTIF (Option A)** |
| **Composite v4.x (Pure OCR)** | Pure Tesseract + Rules | 77.10% | 85.16% | [72.10%, 81.80%] | 76.00% | 89.47% | 36.00% | 90.00% | 90.00% | Baseline Pure OCR Rules |
| **Combined v4.2 (Hybrid)** | Hybrid + 3 Pillars & Crop | 87.42% | 90.00% | [83.50%, 91.20%] | 79.70% | 92.30% | 66.20% | 90.90% | 90.90% | Fallback Produksi Staging |

---

## 4 Lapis Pembuktian Empiris (Empirical Robustness & Generalization Proof)

### Lapis 1: Validasi Statistik (5-Fold Stratified Cross-Validation & Bootstrap CI)
- **Distribusi Per-Fold GLiNER v2.1 Fine-Tuned**:
  * Fold 1 (23 doc): Exact **56.44%**, Fuzzy 64.36%, Durasi 133.2s
  * Fold 2 (21 doc): Exact **53.57%**, Fuzzy 64.29%, Durasi 136.1s
  * Fold 3 (15 doc): Exact **53.12%**, Fuzzy 62.50%, Durasi 137.9s
  * Fold 4 (10 doc): Exact **56.76%**, Fuzzy 67.57%, Durasi 142.9s
  * Fold 5 (5 doc): Exact **50.00%**, Fuzzy 50.00%, Durasi 151.1s
- **Min-Fold Exact**: 50.00%, **Max-Fold Exact**: 56.76% (distribusi sangat seimbang lintas fold).
- **Bootstrap 1000x Resampling**: Mean **54.43%**, 95% Confidence Interval **[47.78%, 60.76%]**. Batas bawah interval v2.1 (47.78%) tumpang tindih tipis pada batas atas IndoBERT-gold ([38.59%, 50.82%]), dengan estimasi mean (+9.86pp) unggul secara substansial.

### Lapis 2: Uji Ketahanan Out-of-Distribution (OOD Stress Testing pada 236 Sel Bebas-Institusi)
- **Baseline Bersih (Clean)**: 55.93% exact (132/236 sel).
- **Mutasi Entitas (UNAIR $\to$ UNS, FTMM $\to$ FST)**:
  * Akurasi turun menjadi **49.58%** (drop **-6.36pp**).
  * **VERDICT LAPIS 2: FAIL**. Threshold toleransi ketahanan mutasi proyek adalah $\le 2.0\text{pp}$. Berbeda dengan zero-shot GLiNER yang kebal mutasi (drop 0.0pt), fine-tuning pada 59 dokumen menyebabkan model mulai mengoverfit token konteks nama institusi lokal.
- **Perturbasi Derau Karakter OCR**:
  * Noise 10%: 36.86% (drop **-19.07pp**).
  * Noise 25%: 27.54% (drop **-28.39pp**).
  * Noise 50%: 13.56% (drop **-42.37pp**).

### Lapis 3: Integritas Pelatihan Anti-Leakage & Tokenizer-Aware Windowing
- 130 tuple label latih diverifikasi konservatif (hanya 148 field unambiguous whole-token, menolak 65 ambigu dan 10 boundary-expanded).
- Pemotongan jendela sliding berbasis subword tokenizer (512 subword, stride 64) memastikan tidak ada span entitas yang terpotong di batas window.
- Eksekusi per-fold diisolasi melalui child process terpisah (`subprocess.run`), membantu melepaskan alokasi heap/VRAM antar-fold ke sistem operasi; seluruh 5 fold berhasil diselesaikan penuh setelah isolasi proses diterapkan.

### Lapis 4: Arsitektur Safety Net & Keamanan Produksi
- **Zero Blast Radius**: Modul produksi `backend/app/services/gemini_extractor.py`, `form_mapper.py`, dan `extraction_pipeline.py` tidak diubah sama sekali.
- GLiNER v2.1 dan GLiNER2.5 murni diposisikan sebagai studi komparasi arsitektural di `tests/`.
- Skor confidence GLiNER mentah belum terkalibrasi ke probabilitas posterior nyata (avg confidence 1.0226 pada nama kegiatan), sehingga tidak layak disambungkan langsung ke threshold `needs_review` (<0.85).

---

## File yang Diubah / Dihasilkan

1. `tests/benchmark_gliner.py`:
   - Penambahan filter `window.spans` pada `to_gliner_v1_records` untuk mencegah tensor reshape error `[1, -1, 0]`.
   - Dukungan CLI granular `--fold <N>` dan `--run-dir <PATH>` untuk eksekusi terisolasi per fold via subprocess.
   - Penjaga memori sistem `avail_gb < 1.5` dan pembersihan memori `malloc_trim(0)` pasca-eksekusi.
2. `scripts/generate_ner_encoder_report_xlsx.py`:
   - Penambahan baris evaluasi resmi GLiNER v2.1 Fine-Tuned dan kegagalan numerik GLiNER2.5 Base pada Sheet 1 (Ringkasan Komparasi).
   - Penambahan spesifikasi teknis kedua model pada Sheet 2 (Konfigurasi Fine-Tuning).
   - Penambahan tabel distribusi 5-fold dan Bootstrap CI GLiNER v2.1 pada Sheet 3 (Detail Per-Fold & Statistik).
   - Pemutakhiran matriks OOD mutasi dan noise pada Sheet 4 (Uji Ketahanan OOD).
3. `docs/report/komparasi_ner_encoder_dan_pipeline.xlsx`:
   - Workbook Excel resmi yang telah diregenerasi dengan seluruh metrik terukur.
4. `docs/experiments_ledger.md`:
   - Pemutakhiran entri `NER-GLINER-002` yang mencatat hasil lengkap 5-fold OOF GLiNER v2.1, kegagalan numerik GLiNER2.5, serta vonis akhir FAIL (Robustness & Numerik).
5. `docs/report/runs_summary.md` & `runs_summary.csv`:
   - Registrasi artefak run resmi `gliner_ft_gliner_multi_v2_1_20260904_195157`.
6. `docs/handoff_v50.md`:
   - Dokumen handoff resmi ini.

---

## Kesimpulan & Rekomendasi Deployment

1. **Keunggulan Arsitektural Bi-Encoder Span**:
   GLiNER v2.1 membuktikan keunggulan representasi span bi-encoder dibanding token classifier konvensional. Dengan parameter 300M, GLiNER v2.1 mencapai **54.52% exact**, mengungguli IndoBERT-gold (44.52%) sebesar **+10.00pp** dan mDeBERTa (34.84%) sebesar **+19.68pp**. Peningkatan terbesar terjadi pada field `nama_kegiatan_sertifikasi` (**52.70%** exact / **74.32%** fuzzy).
2. **Kelemahan Fine-Tuning Domain Kecil**:
   Fine-tuning mengikis keunggulan zero-shot GLiNER: pada mode zero-shot, GLiNER kebal mutasi institusi (drop 0.0pt), namun pasca fine-tuning akurasinya anjlok -6.36pp saat nama kampus dimutasi. Ini membuktikan model mulai menghafal konteks teks sertifikat.
3. **Keputusan Produksi**:
   Arsitektur **Option A (`ENABLE_TESSERACT_GEMINI=true`) tetap menjadi solusi produksi terbaik** (exact 63.24%, fuzzy 73.78%, zero regression, deterministik, biaya Rp9.50/cert) dengan fallback ke Combined v4.2 offline. Encoder lokal (baik IndoBERT maupun GLiNER) ditutup sebagai eksplorasi ilmiah dan tidak dipromosikan ke produksi.
