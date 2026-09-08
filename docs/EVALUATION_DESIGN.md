# Standar Desain & Metrik Evaluasi Ekstraksi Sertifikat

Dokumen ini mendefinisikan arsitektur, metrik, formula matematis, dan protokol pembuktian empiris untuk evaluasi sistem ekstraksi data sertifikat mahasiswa pada proyek Certificate Autofill (Kartu Hasil Prestasi - KHP).

> **Sumber Acuan**: Disintesis dari artefak metodologi dan laporan eksperimen utama pada repositori (`old_docs/report/evaluation_methodology.md`, `old_docs/report/benchmark_methods.md`, `old_docs/evaluation_framework_justification.md`, `old_docs/report/stat_validation.md`, `old_docs/report/ood_probe.md`, `old_docs/report/robustness_eval.md`, `old_docs/report/gemini_4layer_empirical_proof.md`, `old_docs/report/runs_summary.md`, `old_docs/handoff_v51.md`, `old_docs/handoff_v52.md`), serta implementasi evaluator aktif (`tests/matchers.py`, `tests/evaluation_framework.py`, `tests/stat_validation.py`, dan `tests/benchmark_production_input_matrix.py`).

---

## 1. Lingkup Evaluasi & Karakteristik Korpus

### 1.1 Objek Evaluasi
Sistem mengekstrak field terstruktur dari dokumen PDF sertifikat untuk mengisi form Kartu Hasil Prestasi (KHP). Evaluasi dilakukan terhadap **6 field baku**:

| Field | Tipe Data | Deskripsi |
|---|---|---|
| `nama_kegiatan_sertifikasi` | Teks Bebas | Nama atau judul kegiatan/event/kompetisi |
| `waktu_mulai_pelaksanaan` | Tanggal | Tanggal mulai pelaksanaan (format baku: `DD/MM/YYYY`) |
| `waktu_selesai_pelaksanaan` | Tanggal | Tanggal selesai pelaksanaan (format baku: `DD/MM/YYYY`) |
| `penyelenggara_kegiatan` | Teks Organisasi | Nama lembaga/organisasi/panitia penyelenggara |
| `nomor_bukti_fisik_nomor_sertifikasi` | Alfanumerik | Nomor resmi sertifikat / surat tugas |
| `tingkat` | Kategorikal | Tingkat kegiatan: *Internasional*, *Nasional*, *Universitas*, *Fakultas*, *Departemen*, *Lainnya* |

### 1.2 Korpus Uji dan Baseline Ground Truth
- **Total Sampel**: 74 berkas sertifikat representatif.
- **Karakteristik Dokumen**:
  - **`Emb-25` (25 dokumen)**: PDF dengan layer teks digital asli (*embedded text*).
  - **`Scan-49` (49 dokumen)**: PDF hasil scan citra raster (murni gambar, wajib melalui OCR).
- **Ground Truth Otoritatif**: `Ground_Truth_Sertifikat_v9.csv` (berstatus *frozen baseline*, hasil audit konsistensi v8 dan v9).

---

## 2. Definisi dan Formula Metrik Lapisan String (`tests/matchers.py`)

Evaluasi pencocokan string menggunakan implementasi evaluator baku pada `tests/matchers.py` (berstatus *frozen*).

### 2.1 Normalisasi Teks
Sebelum dilakukan komparasi, teks dinormalisasi sesuai tipe field:
- **Tanggal**: Dikonversi ke format kanonikal `DD/MM/YYYY` via `tests.date_normalizer.normalize_date`.
- **Nomor Sertifikat**: Menghapus spasi, tanda titik, tanda minus/strip, garis bawah, dan tabulasi via regex `[ .\-\t_]+`.
- **Teks Bebas & Organisasi**: Konversi ke huruf kecil (*lowercase*), menghapus karakter khusus non-alfanumerik kecuali garis miring (`/`), serta merapikan spasi ganda.

### 2.2 Exact Match (EM)
Biner $\{0, 1\}$. Mengukur kesetaraan karakter absolut pasca-normalisasi:
$$\text{exact} = (\text{normalize}(\text{expected}) == \text{normalize}(\text{actual}))$$
*Pengecualian khusus organisasi*: Jika nilai prediksi merupakan akronim/singkatan resmi yang terdaftar dari expected (`abbreviation_match == True`), matcher menetapkan `exact = True` (misalnya `UNAIR` terhadap `Universitas Airlangga`).

### 2.3 Perilaku Fuzzy Match per Tipe Field (`match_field`)
Biner $\{0, 1\}$. Implementasi `match_field()` pada `tests/matchers.py` menerapkan aturan pencocokan berbeda sesuai karakteristik field:
- **Field Tanggal & Nomor** (`waktu_mulai_pelaksanaan`, `waktu_selesai_pelaksanaan`, `nomor_bukti_fisik_nomor_sertifikasi`):
  $$\text{fuzzy} \equiv \text{exact}$$
  Pada field terstruktur ini tidak ada toleransi parsial; nilai `fuzzy` selalu sama dengan nilai `exact`.
- **Field Organisasi & Nama Kegiatan** (`penyelenggara_kegiatan`, `nama_kegiatan_sertifikasi`):
  $$\text{fuzzy} = \text{contains} \lor \text{abbreviation\_match} \lor (\text{token\_overlap} \ge 0.75)$$
  *Threshold Khusus*: Threshold token overlap ditetapkan **$\ge 0.75$** (dinaikkan dari 0.50 guna mengeliminasi false positive antar-organisasi mirip, seperti `BEM FEB UNAIR` vs `BEM FKM UNAIR` yang ber-overlap 0.67).
  *Akronim Mengangkat Exact*: Jika nilai terdeteksi sebagai akronim resmi yang valid (`abbreviation_match == True`), matcher secara otomatis menetapkan `exact = True` dan `fuzzy = True`.
- **Field Lainnya** (misalnya `tingkat`):
  $$\text{fuzzy} = \text{contains} \lor (\text{token\_overlap} \ge 0.50)$$

Sub-komponen logika fuzzy:
1. **Contains (Substring Dua Arah)**:
   $$\text{contains} = (\text{norm}(\text{expected}) \in \text{norm}(\text{actual})) \lor (\text{norm}(\text{actual}) \in \text{norm}(\text{expected}))$$
2. **Token Overlap Score $[0.0, 1.0]$**:
   $$\text{token\_overlap} = \frac{|T_{\text{expected}} \cap T_{\text{actual}}|}{\min(|T_{\text{expected}}|, |T_{\text{actual}}|)}$$
   dengan $T$ adalah himpunan token kata unik dari pemisahan spasi hasil normalisasi (`set(normalize_value(s).split())`). *Catatan*: `token_overlap_score()` tidak melakukan pemfilteran stopword; pemfilteran stopword (`ABBR_STOPWORDS`) hanya berlaku secara eksklusif pada fungsi pengenalan akronim (`is_initialism_of`, `is_portmanteau_of`, `is_abbreviation_of`).
3. **Abbreviation & Portmanteau Match**:
   Pencocokan akronim berbasis huruf depan kata (`is_initialism_of`) dan kamus portmanteau terdaftar (`KNOWN_PORTMANTEAUS` seperti `UNAIR`, `ITS`, `KEMENDIKBUD`, `HIMASADA`, dsb.).

### 2.4 Metrik Jarak Edit Kontinu (Error Rates)
- **Word Error Rate (WER)**:
  $$\text{WER} = \min\left(\frac{\text{Levenshtein}(W_{\text{ref}}, W_{\text{hyp}})}{|W_{\text{ref}}|}, 1.0\right)$$
- **Character Error Rate (CER)**:
  $$\text{CER} = \min\left(\frac{\text{Levenshtein}(C_{\text{ref}}, C_{\text{hyp}})}{|C_{\text{ref}}|}, 1.0\right)$$

---

## 3. Arsitektur Agregasi & Klarifikasi Denominator

### 3.1 Penanganan Denominator Dinamis vs Fixed
- **Jalur Legacy (`tests/evaluation_framework.py`)**:
  Evaluator mengabaikan baris yang pada Ground Truth bernilai kosong atau tanda strip (`-`):
  ```python
  if not expected or expected == "-":
      continue
  ```
  Denominator per field ($N_{\text{field}}$) bersifat dinamis mengikuti total sel yang memiliki label GT valid.
- **Jalur Modern All-Cells (`tests/benchmark_production_input_matrix.py`)**:
  Denominator total sel ditetapkan secara fixed:
  $$\text{total\_all\_cells} = N_{\text{docs}} \times |\text{ALL\_EVAL\_FIELDS}| = 74 \times 6 = 444\text{ sel}$$

### 3.2 Dua Jalur Evaluator Resmi di Repositori

| Parameter | Jalur A: Legacy Framework (`tests/evaluation_framework.py`) | Jalur B: Modern All-Cells (`tests/stat_validation.py` / Input Matrix Runner) |
|---|---|---|
| **Cakupan Field** | 5 Field dasar (tanpa `tingkat`) | 6 Field lengkap (termasuk `tingkat`) |
| **Denominator** | Dinamis ($\approx 370$ sel, minus missing/empty GT) | Fixed $N_{\text{docs}} \times 6 = 444$ sel (pada korpus 74 dokumen) |
| **Sifat Agregasi "Macro"** | **Micro-average pooled over cells**: $\frac{\sum \text{exact\_ok}}{\sum \text{total}}$ | **All-Cells pooled ratio**: $\frac{\sum \text{exact\_all\_cells}}{\text{total\_all\_cells}} \times 100\%$ |
| **Metrik Per-Field** | Dihitung terhadap $N_{\text{field}}$ sel valid | Dihitung terhadap $N_{\text{docs}}$ (74 sampel); macro mean hanya dilaporkan jika runner menghitung rata-rata antar-field eksplisit |
| **Tujuan Penggunaan** | Komparasi historis pipeline ekstraktor regex/NER | Benchmark end-to-end produksi dan model bahasa (LLM) |

*Aturan Pelaporan*: Setiap laporan benchmark wajib mencantumkan secara tegas apakah metrik yang disajikan berbasis **Framework 5-Field** atau **All-Cells 6-Field**. Dilarang mencampuradukkan kedua denominator tersebut.
### 3.3 Pelaporan Subgroup Wajib (`Emb-25` vs `Scan-49`)
Evaluasi wajib menyajikan rincian akurasi terpisah untuk:
1. Subset dokumen teks digital (`Emb-25`).
2. Subset dokumen hasil scan raster (`Scan-49`).
*Prinsip Integritas*: Modul OCR tidak boleh menurunkan akurasi pada dokumen digital murni (gejala visual noise degradation).

---

## 4. Protokol 4 Lapis Pembuktian Empiris (Mandatori Generalisasi & Robustness)

Setiap perubahan pipeline ekstraksi, penambahan rule router, atau integrasi model wajib diuji melalui 4 lapis pembuktian berikut. **Setiap lapis dinilai secara independen dengan status PASS atau FAIL; tidak ada kelulusan otomatis.**

```
┌────────────────────────────────────────────────────────────────────────┐
│               4 LAPIS PEMBUKTIAN EMPIRIS MANDATORI                     │
├────────────────────────────────┬───────────────────────────────────────┤
│ LAPIS 1: Validasi Statistik    │ 5-Fold Stratified CV + Bootstrap CI   │
│ LAPIS 2: Ketahanan OOD         │ Mutasi Entitas (<=2.0pt) + Noise OCR  │
│ LAPIS 3: Anchor Semantik       │ Gramatika Formal (0 hardcoded events) │
│ LAPIS 4: Calibrated Safety Net │ needs_review (<0.85, recall >=95%)    │
└────────────────────────────────┴───────────────────────────────────────┘
```

### 4.1 Lapis 1: Validasi Statistik ($k$-Fold CV & Bootstrap CI)
- **Stratified 5-Fold Cross-Validation**:
  - Membagi 74 dokumen menjadi 5 fold dengan proporsi seimbang antara scan dan digital.
  - Untuk rule router deterministik: Wajib mencapai **Min-Fold Precision 100.0%** pada fold uji yang tidak melihat data latih. Rule dengan frekuensi pemanggilan $< 5$ diklasifikasikan sebagai `LOW-N` dan tidak boleh diklaim robust tanpa guard ketat.
- **Bootstrap 1000x Resampling**:
  - Resampling dengan pengembalian (*with replacement*) sebanyak 1.000 iterasi.
  - Wajib melaporkan estimasi Mean dan **95% Confidence Interval (CI95)** untuk All-Cells Exact, Fuzzy, dan akurasi per field.
- **Gate Lolos**: Min-fold rule precision 100% dan batas bawah CI95 tidak mengalami regresi terhadap baseline.

### 4.2 Lapis 2: Uji Ketahanan Out-of-Distribution (OOD Stress Testing)
- **Template & Entity Mutation**:
  - Menguji kepekaan sistem terhadap perubahan template institusi/fakultas/kegiatan luar domain (misal: `UNAIR` $\to$ `UNS`, `FTMM` $\to$ `FST`, nama event diganti nama generik).
  - **Ambang Batas Toleransi**: Penurunan performa pada field bebas-institusi (tanggal, kegiatan, peranan) dibatasi **$\le 2.0\text{pt}$**.
- **OCR Noise Perturbation**:
  - Injeksi derau kebingungan karakter nyata (`5↔S`, `8↔B`, `0↔O`, `1↔I`, spasi terpotong) pada tingkat 10%, 25%, dan 50%.
  - Sistem wajib mempertahankan kestabilan ekstraksi minimal pada tingkat noise 10%.
- **Catatan Bukti Historis**: Pada pengujian model `gemini-3.1-flash-lite` (`old_docs/report/gemini_4layer_empirical_proof.md`), mutasi entitas menyebabkan penurunan akurasi **16.67pt**, yang melanggar toleransi $\le 2.0\text{pt}$ sehingga berstatus **FAIL**.

### 4.3 Lapis 3: Ekstraksi Berbasis Structural Semantic Anchors (Anti-Hardcoding)
- **Prinsip**: Ekstraksi wajib memanfaatkan relasi sintaksis tata bahasa formal dokumen sertifikat (misal: `diberikan kepada [Nama] sebagai [Peran] dalam kegiatan [Nama Kegiatan] yang diselenggarakan oleh [Penyelenggara]`).
- **Audit Bebas Hardcoding**:
  - Dilarang keras melakukan pencocokan nama event secara leksikal langsung (*string equality matching* terhadap judul event korpus).
  - Dilakukan audit leksikal terhadap 14+ kata kunci event korpus (SPECTA, KARSA, FALCON, BRIEF, AIRNOLOGY, dsb.). Pelanggaran ditemukan wajib = 0.
- **Gate Lolos**: 0 kata kunci event korpus ter-hardcode dalam logika ekstraksi.

### 4.4 Lapis 4: Arsitektur Safety Net Produksi & Calibrated Confidence
- **Mekanisme Peninjauan (`needs_review`)**:
  - Sistem form KHP mengimplementasikan mekanisme pencegahan kesalahan fatal sebelum data disimpan ke database.
  - Ambang batas confidence aktif: Nilai field dengan **confidence $< 0.85$**, nilai kosong (*null*), unrouted, atau format tanggal invalid otomatis menandai `needs_review = True`.
- **Target Review Error Recall**:
  $$\text{Review Recall} = \frac{\text{True Positives (Prediksi Salah & Di-flag)}}{\text{Total Prediksi yang Memiliki Error}} \ge 95.0\%$$
- **Catatan Bukti Historis**: Pada pengujian model `gemini-3.1-flash-lite` (`old_docs/report/gemini_4layer_empirical_proof.md`), mekanisme confidence hanya menghasilkan review recall sebesar **55.88%** (30 kasus salah lolos tanpa peninjauan), sehingga dinyatakan **FAIL**.
- **Koreksi Drift Laporan Lama**: Dokumen lama `technical_report_pipeline_production.md` sempat menuliskan threshold `< 0.80` dan mendefinisikan ulang lapis 2, 3, dan 4 menjadi aspek operasional (leakage, paired delta, pacing/retry). Standar desain ini menegaskan kembali definisi normatif sesuai `AGENTS.md` aktif.

---

## 5. Akuntansi Efisiensi & Biaya Operasional LLM

Untuk setiap pengujian yang melibatkan model bahasa (LLM), pelaporan wajib menyertakan audit konsumsi komputasi dan finansial yang transparan:

1. **Rincian Token Granular**:
   - `prompt_tokens`: Jumlah token prompt input.
   - `candidates_tokens`: Jumlah token teks keluaran model.
   - `cached_tokens`: Jumlah token yang terlayani melalui konteks cache.
   - `thoughts_tokens`: Jumlah token penalaran internal (*reasoning tokens*).
   - `total_tokens`: Total keseluruhan token yang diproses.
2. **Effective Tokens per Document**:
   $$\text{Eff Tokens/Doc} = \frac{\text{Total Tokens across all calls}}{74}$$
   Dokumen yang terselesaikan melalui jalur cepat aturan (*rules/short-circuit*) dihitung berkontribusi 0 token.
3. **Audit Biaya Finansial**:
   - Estimasi biaya riil dalam USD berdasarkan tabel harga resmi penyedia model.
   - Konversi ke IDR menggunakan kurs acuan terverifikasi.
   - Estimasi proyeksi biaya untuk skala operasional 100.000 dokumen sertifikat.
4. **Throughput & Latensi**:
   - Rata-rata waktu proses per dokumen (detik/sertifikat).
   - Pacing jeda antar-request dan penanganan retry (*exponential backoff*).
5. **Grounding & Web Search**:
   - Jumlah query pencarian web yang dipanggil per dokumen (jika alat grounding diaktifkan).

---

## 6. Prosedur Operasional Standar (SOP) Evaluasi Pipeline Baru

Sebelum suatu perubahan pada ekstraktor atau pipeline diklaim berhasil, alur pengujian berikut wajib dipenuhi:

```
1. Persiapan Baseline
   └─ Kunci GT: Ground_Truth_Sertifikat_v9.csv
   └─ Kunci Evaluator: tests/matchers.py (Matcher v2)

2. Eksekusi Benchmark
   ├─ Evaluasi Jalur Legacy 5-Field (Framework Score)
   └─ Evaluasi Jalur Modern 6-Field (All-Cells Score + Emb-25 & Scan-49 split)

3. Uji 4 Lapis Pembuktian Empiris
   ├─ Lapis 1: 5-Fold Stratified CV (Rule Precision 100%) + Bootstrap 1000x CI
   ├─ Lapis 2: OOD Mutasi Entitas (Degradasi <= 2.0pt) + OCR Noise (10%, 25%, 50%)
   ├─ Lapis 3: Audit Relasi Gramatikal (0 event hardcoded)
   └─ Lapis 4: Evaluasi Safety Net needs_review (Threshold < 0.85, Recall >= 95.0%)

4. Verifikasi Zero-Regression
   └─ Pastikan seluruh test lulus: pytest tests/ -v
   └─ Pastikan performa tidak regresi terhadap baseline terdaftar di runs_summary.md

5. Dokumentasi & Pelaporan
   └─ Catat status hasil pengujian (PASS/FAIL) secara independen di experiments_ledger.md
```
