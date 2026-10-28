# Standar Desain & Metrik Evaluasi Ekstraksi Sertifikat

Dokumen ini mendefinisikan arsitektur, metrik, formula matematis, dan protokol pembuktian empiris untuk evaluasi sistem ekstraksi data sertifikat mahasiswa pada proyek Certificate Autofill (Kartu Hasil Prestasi - KHP).

> **Sumber Acuan**: Disintesis dari artefak metodologi dan laporan eksperimen utama pada repositori (`old_docs/report/evaluation_methodology.md`, `old_docs/report/benchmark_methods.md`, `old_docs/evaluation_framework_justification.md`, `old_docs/report/stat_validation.md`, `old_docs/report/ood_probe.md`, `old_docs/report/robustness_eval.md`, `old_docs/report/gemini_4layer_empirical_proof.md`, `old_docs/report/runs_summary.md`, `old_docs/handoff_v51.md`, `old_docs/handoff_v52.md`), serta implementasi evaluator aktif (`tests/matchers.py`, `tests/evaluation_framework.py`, `tests/stat_validation.py`, dan `tests/benchmark_production_input_matrix.py`).

---

## 1. Lingkup Evaluasi & Karakteristik Korpus

### 1.1 Objek Evaluasi
Sistem mengekstrak field terstruktur dari dokumen PDF sertifikat untuk mengisi form Kartu Hasil Prestasi (KHP). Evaluasi resmi dilakukan terhadap **10 field lengkap**:

| Kategori | Field | Tipe Data | Deskripsi |
|---|---|---|---|
| **6 Field Dasar** | `nama_kegiatan_sertifikasi` | Teks Bebas | Nama atau judul kegiatan/event/kompetisi |
| | `nomor_bukti_fisik_nomor_sertifikasi` | Alfanumerik | Nomor resmi sertifikat / surat tugas |
| | `penyelenggara_kegiatan` | Teks Organisasi | Nama lembaga/organisasi/panitia penyelenggara |
| | `waktu_mulai_pelaksanaan` | Tanggal | Tanggal mulai pelaksanaan (format baku: `DD/MM/YYYY`) |
| | `waktu_selesai_pelaksanaan` | Tanggal | Tanggal selesai pelaksanaan (format baku: `DD/MM/YYYY`) |
| | `tingkat` | Kategorikal | Tingkat kegiatan: *Internasional*, *Nasional*, *Universitas*, *Fakultas*, *Departemen*, *Lainnya* |
| **3 Field AUCC** | `kelompok_kegiatan` | Taksonomi AUCC | Bidang kegiatan (Organisasi, Penalaran, Minat Bakat, dll.) |
| | `jenis_kegiatan` | Taksonomi AUCC | Sub-kegiatan resmi (ID Kegiatan 1 pada `aucc.sql`) |
| | `prestasi_partisipasi_jabatan` | Taksonomi AUCC | Peran/jabatan/prestasi (ID Jabatan pada `aucc.sql`) |
| **Pedoman KHP** | `jenis_penyelenggara` | Kategorikal | 9 Kategori (Internal UNAIR, PTN Lain, PTS, BUMN, dll.) |

### 1.2 Korpus Uji dan Baseline Ground Truth
- **Dataset Acuan Resmi Aktif**: **`Ground_Truth_Unified_AUCC.csv` ($N=104$ sertifikat terpadu)**.
  - Mencakup 74 sertifikat dataset primer + 30 sertifikat holdout.
  - Memuat 13 kolom lengkap termasuk taksonomi master data AUCC dan resolusi tuple `id_kegiatan_2`.
- **Baseline Historis Beku (*Frozen*)**: `Ground_Truth_Sertifikat_v9.csv` ($N=74$ berkas sertifikat) digunakan khusus untuk backward-compatibility dan audit historis terhadap pipeline legacy regex/NER.
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


### 2.5 Arsitektur Metrik Generatif Terpadu (`tests/evaluation_generative_v2.py`)

Guna mengatasi keterbatasan biner *Exact Match* yang kaku dan mengeliminasi risiko *false positive* dari formula pembagi $\min()$ pada *Fuzzy Match* legacy, modul evaluator modern `tests/evaluation_generative_v2.py` mengadopsi standar metrik evaluasi generatif dan Document KIE:

#### 1. Token-level Precision, Recall, dan F1 (SQuAD Multiset Overlap)
Diterapkan pada field teks bebas (`nama_kegiatan_sertifikasi` dan `penyelenggara_kegiatan`):
$$\text{Precision} = \frac{|T_{\text{pred}} \cap T_{\text{gold}}|}{|T_{\text{pred}}|}, \quad \text{Recall} = \frac{|T_{\text{pred}} \cap T_{\text{gold}}|}{|T_{\text{gold}}|}$$
$$F1 = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$
Menggunakan irisan *multiset* kata unik pasca-normalisasi. Presisi menghukum halusinasi/penambahan kata, dan recall menghukum pemotongan teks.

#### 2. Average Normalized Levenshtein Similarity (ANLS - Standar DocVQA)
Toleransi terhadap salah baca 1–2 karakter OCR pada teks bebas dan entitas:
$$\text{NLS}(p, g) = 1.0 - \frac{\text{Levenshtein}(p, g)}{\max(|p|, |g|)}$$
$$\text{ANLS}(p, g) = \begin{cases} \text{NLS}(p, g), & \text{jika } \text{NLS}(p, g) \ge 0.50 \\ 0.0, & \text{lainnya} \end{cases}$$

#### 3. Canonical Date Match & Component-Level Scoring
Diterapkan pada `waktu_mulai_pelaksanaan` dan `waktu_selesai_pelaksanaan`:
- **Exact**: Kesetaraan absolut pasca-konversi format kanonikal ISO `YYYY-MM-DD`.
- **Component-Level Score $[0.0, 1.0]$**: Memberi apresiasi proporsional saat Tahun dan Bulan berhasil diekstrak tepat:
$$\text{Score}_{\text{date}} = \frac{1}{3}\mathbf{1}[\text{Tahun Cocok}] + \frac{1}{3}\mathbf{1}[\text{Bulan Cocok}] + \frac{1}{3}\mathbf{1}[\text{Hari Cocok}]$$

#### 4. Delimiter-Normalized Exact Match & CharSim (Nomor Sertifikat)
Diterapkan pada `nomor_bukti_fisik_nomor_sertifikasi`:
- Normalisasi menghapus spasi dan tanda baca delimiter (`/`, `.`, `-`, `_`, tabulasi).
- Menghitung kesamaan karakter ($\text{CharSim}$) dan *Character Error Rate* (CER):
$$\text{CharSim}(p, g) = 1.0 - \frac{\text{Levenshtein}(p_{\text{norm}}, g_{\text{norm}})}{\max(|p_{\text{norm}}|, |g_{\text{norm}}|)}$$
$$\text{CER}(p, g) = \min\left(\frac{\text{Levenshtein}(p_{\text{norm}}, g_{\text{norm}})}{|g_{\text{norm}}|}, 1.0\right)$$

#### 5. Multiclass Macro-F1 (Tingkat Kegiatan)
Diterapkan pada field kategorikal tertutup `tingkat` (6 kelas resmi KHP):
- Menghitung confusion matrix $6 \times 6$.
- Menghitung rata-rata tanpa bobot (*unweighted macro average*) dari F1 seluruh kelas aktif guna menghilangkan bias akibat ketimpangan jumlah data:
$$\text{Macro-F1}_{\text{tingkat}} = \frac{1}{|C|} \sum_{c \in C} F1_c$$

#### 6. AUCC Triplet Match & Resolution Rate
Diterapkan pada taksonomi master data KHP (`kelompok_kegiatan`, `jenis_kegiatan`, `prestasi_partisipasi_jabatan`):
- **Triplet Match**: Bernilai 1 jika ketiga komponen simultan terpetakan valid sesuai tabel `master_kegiatan_rule`.
- **Resolution Rate**: Persentase sertifikat yang terpetakan sukses ke `id_kegiatan_2` tanpa memicu review manual.

#### 7. Record-Level Exact Match (Zero-Touch Automation Rate)
Metrik operasional riil kampus:
$$\text{Record-EM}_i = \prod_{k \in \text{Fields}} \mathbf{1}[\text{Exact}_{i, k}]$$
Bernilai 1 hanya jika **seluruh field wajib diekstrak benar sempurna**. Mengukur persentase sertifikat mahasiswa yang tidak memerlukan intervensi koreksi manual sama sekali.
---

## 3. Arsitektur Agregasi & Klarifikasi Denominator

### 3.1 Penanganan Denominator Dinamis vs Fixed
- **Jalur Dinamis (Legacy `tests/evaluation_framework.py` & `tests/stat_validation.py`)**:
  Evaluator mengabaikan baris/sel yang pada Ground Truth bernilai kosong atau tanda strip (`-`):
  ```python
  if not expected or expected == "-":
      continue
  ```
  Denominator per field ($N_{\text{field}}$) bersifat dinamis mengikuti total sel yang memiliki label GT valid. Agregasi `macro` pada kedua modul ini dihitung secara **pooled ratio lintas sel valid** ($\sum \text{exact} / \sum \text{total}$), bukan rata-rata dari per-field accuracy.
- **Jalur Fixed All-Cells (`tests/benchmark_production_input_matrix.py`)**:
  Denominator total sel ditetapkan secara fixed:
  $$\text{total\_all\_cells} = N_{\text{docs}} \times |\text{ALL\_EVAL\_FIELDS}| = 74 \times 6 = 444\text{ sel}$$
  Agregasi All-Cells 6F dihitung sebagai pooled ratio:
  $$\text{all\_cells\_exact\_pct} = \frac{\text{exact\_all\_cells}}{\text{total\_all\_cells}} \times 100\%$$

### 3.2 Pemetaan Evaluator Resmi di Repositori

| Parameter | Jalur A: Legacy Framework (`tests/evaluation_framework.py`) | Jalur B: Production Matrix (`tests/benchmark_production_input_matrix.py`) | Jalur C: Evaluator Generatif & AUCC (`tests/evaluation_generative_v2.py`) |
|---|---|---|---|
| **Cakupan Field** | 5 Field dasar (tanpa `tingkat`) | 6 Field lengkap (termasuk `tingkat`) | **10 Field lengkap** (6 dasar + 3 AUCC + jenis penyelenggara) |
| **Denominator** | Dinamis ($\approx 370$ sel valid GT) | Fixed $74 \times 6 = 444$ sel | **Fixed $104$ dokumen ($104 \times 9 = 936$ sel)** |
| **Sifat Agregasi** | Pooled micro-ratio over cells | All-Cells pooled ratio | **Multi-tier**: Record EM, Per-field Token-F1, ANLS, AUCC Triplet, True Macro-F1 |
| **Dataset GT** | `Ground_Truth_Sertifikat_v9.csv` (74) | `Ground_Truth_Sertifikat_v9.csv` (74) | **`Ground_Truth_Unified_AUCC.csv` ($N=104$ terpadu)** |
| **Tujuan Penggunaan** | Komparasi historis regex legacy | Benchmark input matrix model | **Standar Resmi Evaluasi Pipeline Produksi Generatif & AUCC** |

*Aturan Pelaporan*: Setiap laporan benchmark wajib mencantumkan secara tegas apakah metrik yang disajikan berbasis **Jalur Legacy (74 sertifikat)** atau **Jalur Generatif & AUCC Resmi (104 sertifikat)**.

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

---

## 7. Protokol Evaluasi Eksperimen Prompting LLM (Klasifikasi Tingkat)

Untuk eksperimen teknik prompting model bahasa (LLM) pada klasifikasi field `tingkat`, evaluasi wajib mengikuti protokol khusus berikut:

### 7.1 Alur Pipeline End-to-End
```
Dokumen PDF (Digital / Scan)
       ↓
[1] Ekstraksi Teks Mentah (PyMuPDF Fast-path / Tesseract OCR / OCR Marker File)
       ↓
[2] Formulasi Prompt (Zero-Shot / Few-Shot / CoT / Self-Consistency / Iterative)
       ↓
[3] Inferensi LLM (Google Gemini / Ollama / Local Backend)
       ↓
[4] Validasi & Normalisasi Kanonikal (`validate_tingkat` -> 6 opsi resmi KHP)
       ↓
[5] Evaluasi vs Ground Truth & Safety Net Review (`needs_review`)
```

### 7.2 Metrik Spesifik Evaluasi Prompting
1. **Akurasi Klasifikasi Tingkat**:
   $$\text{Akurasi} = \frac{\sum (\text{pred\_tingkat} == \text{gt\_tingkat})}{N_{\text{sampel}}} \times 100\%$$
2. **Matriks Kesalahan Skala (Hierarchical Confusion)**:
   - **Bias `Nasional -> Fakultas`** (False Negative Nasional): Mengukur frekuensi lomba skala nasional salah dipetakan ke tingkat fakultas hanya karena penyelenggaranya adalah BEM/HIMA.
   - **Bias `Fakultas -> Nasional`** (False Positive Nasional): Mengukur frekuensi acara internal fakultas salah dipetakan menjadi skala nasional.
3. **Tingkat Pemicu Peninjauan (Review Trigger Rate)**:
   $$\text{Review Rate} = \frac{\sum (\text{needs\_review} == \text{True})}{N_{\text{sampel}}} \times 100\%$$
   Pemicu wajib: $\text{Confidence} < 0.85$, hasil tie pada sampling voting, atau prediksi bernilai `Lainnya`/`None`.
4. **Akuntansi Token Granular & Biaya Finansial (USD & IDR)**:
   - Input prompt tokens, output candidates tokens, cached tokens, dan reasoning/thoughts tokens dicatat per pemanggilan.
   - Konversi biaya dihitung berdasarkan tarif resmi per model (misal $0.25 / 1M prompt & $1.50 / 1M output untuk `gemini-3.1-flash-lite`) dan kurs resmi acuan IDR/USD.
5. **Wajib Pencatatan Registry Prompt**:
   - Setiap eksperimen prompting wajib menyimpan salinan seluruh template prompt yang digunakan secara terisolasi dalam format Markdown atau teks (`PROMPT_REGISTRY.md` atau `.txt`) untuk menjamin reproduktibilitas tanpa hardcoding.
