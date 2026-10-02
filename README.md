# Certificate Autofill Prototype

[![CI](https://github.com/Primarizki21/certificate-autofill/actions/workflows/ci.yml/badge.svg)](https://github.com/Primarizki21/certificate-autofill/actions/workflows/ci.yml)

Prototype sistem ekstraksi multi-format sertifikat mahasiswa (PDF, JPG, JPEG, PNG, WEBP) dan autofill form Kartu Hasil Prestasi (KHP) terintegrasi taksonomi resmi universitas.

**Stack & Arsitektur Utama:**
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL 17
- **Text & OCR Engine:** PyMuPDF (fast text + direct buffer in-memory + resolution clamping) + Tesseract OCR (Single-Pass PSM 6 teroptimasi) + RapidOCR (cgroup CPU thread-aligned)
- **Persepsi Semantik (LLM):** Google Gemini (`gemini-3.1-flash-lite`) untuk ekstraksi fakta teks sertifikat dan penentuan tingkat cakupan
- **Resolver Deterministik KHP:** Modul Python deterministik untuk autofill 9-field KHP yang memetakan hasil ekstraksi ke taksonomi resmi kemahasiswaan universitas secara bilingual (Indonesia & Inggris, mencakup normalisasi tingkat, peran/prestasi, jabatan kepengurusan universal, dan pengelompokan kegiatan resmi)
- **Antarmuka Form KHP:** Vanilla HTML/CSS/JS dengan UI Cascading Filter dinamis dan Modal Pencarian Master Kegiatan
- **Ekstraksi Offline (Fallback):** Combined v4.2 (Sistem aturan struktural lokal tanpa cloud API)
- **Monitoring:** Prometheus + Grafana + Loki
- **Keamanan & Guard Upload:** Inspeksi *defense-in-depth* multi-format (validasi *magic bytes*, sanitasi metadata/EXIF, batas dekompresi 60 MP, pencegahan injeksi skrip PDF) dan *sliding-window rate limiter*

---

## Cara Menjalankan

### 1. Konfigurasi Awal (Environment Variables)

Sebelum menyalakan aplikasi, buat file konfigurasi `.env` dari template:

```bash
cp .env.example .env
```

```bash
GOOGLE_API_KEY=""  # Masukkan kunci Google AI Studio API Anda
```

> 🛡️ **Graceful Fallback (Anti Error 500)**:
> Jika `GOOGLE_API_KEY` dikosongkan, kuota habis (HTTP 429), atau koneksi internet terputus, sistem secara otomatis beralih (*graceful fallback*) ke pipeline offline (Combined v4.2) tanpa memicu crash atau HTTP 500.

---

### 2. Menjalankan via Docker Compose

Perintah default menyalakan backend FastAPI dan PostgreSQL 17:

```bash
docker compose up --build
```

Untuk menyalakan Prometheus, Grafana, dan Loki, gunakan profile `monitoring`:

```bash
docker compose --profile monitoring up --build
```

Setelah container aktif:
| Service | URL | Keterangan |
|---|---|---|
| **FastAPI Web & Form** | `http://localhost:8000` | Antarmuka web form KHP + Swagger API docs (`/docs`) |
| **PostgreSQL 17** | `localhost:5434` | Database (`certautofill`, user: `postgres`, pass: `postgres`) |
| **Worker (DB Polling)** | *(background)* | Service worker (`python -m app.worker`) untuk eksekusi antrean job di database |
| **Prometheus** | `http://localhost:9090` | Aktif dengan profile `monitoring` |
| **Grafana** | `http://localhost:3000` | Aktif dengan profile `monitoring` (`admin:admin`) |
| **Loki** | `http://localhost:3100` | Aktif dengan profile `monitoring` |
> Variabel `GOOGLE_API_KEY` dari file `.env` Anda akan otomatis diteruskan ke container backend oleh Docker Compose.

---

### 3. Menjalankan secara Manual (Tanpa Docker)

#### Prasyarat:
1. PostgreSQL 17 aktif di port `5434` dengan database `certautofill`.
2. Tesseract OCR (`tesseract-ocr` dan `tesseract-ocr-ind`) terpasang di sistem operasi.
3. Jalankan inisialisasi skema dan seed data master KHP universitas (pertama kali):
   ```bash
   python scripts/seed_khp_master.py
   ```
#### Linux / macOS:
```bash
export APP_ENV=development
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
export PROCESSING_MODE=background
export ENABLE_TESSERACT_GEMINI=true
export ENABLE_KHP_MASTER_STAGING=true
export ENABLE_COMBINED_V4_2=true
export GOOGLE_API_KEY=""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Windows (PowerShell):
```powershell
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:ENABLE_TESSERACT_GEMINI="true"
$env:ENABLE_KHP_MASTER_STAGING="true"
$env:ENABLE_COMBINED_V4_2="true"
$env:GOOGLE_API_KEY=""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### 4. Frontend Standalone (Opsional)
Buka `frontend/index.html` langsung di browser, atau gunakan Python HTTP server:
```bash
cd frontend && python -m http.server 5173
```

---

## Konfigurasi Pipeline & Mode Ekstraksi

Pipeline ekstraksi dapat disesuaikan melalui environment variable di file `.env`:

| Variabel | Nilai Default | Deskripsi |
|---|:---:|---|
| `ENABLE_TESSERACT_GEMINI` | `true` | Mengaktifkan ekstraksi langsung teks OCR ke Google Gemini dengan prompt V2 Scope-Aware |
| `GOOGLE_API_KEY` | *(kosong)* | Kunci Google AI Studio API Anda |
| `GOOGLE_GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model Gemini yang digunakan (`gemini-3.1-flash-lite`, `gemini-2.5-flash-lite`, `gemini-2.5-flash`) |
| `GEMINI_TIMEOUT_SECONDS` | `30.0` | Batas waktu timeout pemanggilan API Gemini sebelum fallback |
| `ENABLE_KHP_MASTER_STAGING` | `true` | Mengaktifkan resolusi master data resmi universitas, autofill 9-field KHP, dan UI cascading filter |
| `ENABLE_COMBINED_V4_2` | `true` | Pipeline offline rule-based resmi saat Gemini tidak aktif atau kuota habis |
| `PROCESSING_MODE` | `background` | Mode eksekusi job (`background`: FastAPI BackgroundTasks, `sync`: langsung, `db_worker`: polling DB) |
| `OCR_RAPID_THREADS` | `0` | Thread ONNX Runtime untuk RapidOCR (`0`: otomatis mengikuti kuota CPU container, `-1`: default library, `N`: eksplisit) |
| `UPLOAD_TEMP_DIR` | `/tmp/cert_uploads` | Direktori PDF sementara, izin direktori `0o700` dan file `0o600` |
| `TEMP_FILE_TTL_HOURS` | `1` | Batas umur PDF tanpa job aktif sebelum dihapus |
| `JOB_LEASE_SECONDS` | `900` | Batas kerja eksklusif satu worker untuk satu job |
| `STORAGE_CLEANUP_INTERVAL_SECONDS` | `300` | Jeda cleanup file yatim dan job lease kedaluwarsa |
| `RATE_LIMIT_PER_MINUTE` | `30` | Batas maksimum unggahan per menit per IP address |
| `MAX_PDF_PAGES` | `3` | Batas maksimum jumlah halaman file PDF sertifikat |
| `MAX_IMAGE_PIXELS` | `60000000` | Batas aman piksel gambar (Pillow Decompression Bomb safeguard, 60 MP) |
| `MAX_IMAGE_DIMENSION` | `8000` | Dimensi panjang/lebar piksel maksimum gambar (anti-pixel flood) |
| `MIN_IMAGE_DIMENSION` | `300` | Dimensi piksel minimum gambar sertifikat (anti-troll micro icon) |
| `AUTO_DOWNSCALE_THRESHOLD` | `3500` | Ambang resolusi pindaian tinggi sebelum di-downscale otomatis |
| `AUTO_DOWNSCALE_TARGET` | `2500` | Target resolusi sisi terpanjang gambar setelah downscale proporsional |
| `MAX_PDF_CANVAS_DIMENSION` | `5000` | Batas dimensi kanvas halaman PDF dalam point (anti-canvas bomb) |
| `MAX_UPLOAD_SIZE_MB` | `25` | Batas ukuran berkas maksimum yang diizinkan untuk diunggah (MB) |
| `ADMIN_USERNAME` | `admin` | Username untuk Basic Auth endpoint administratif `/api/admin/*` |
| `ADMIN_PASSWORD` | *(wajib disetel)* | **Wajib diisi dengan kata sandi kuat.** Jangan gunakan password sederhana di server/publik |
| `API_KEYS` | *(kosong)* | Kunci API resmi (prefix `sk-`, dipisahkan koma) untuk integrasi `/api/v1/extract` |
| `REQUIRE_API_KEY` | `false` | Mewajibkan otentikasi API Key pada endpoint `/api/v1/extract` (aktifkan di jaringan publik) |

### Storage Sementara dan Manajemen File
PDF hanya berada sementara di `UPLOAD_TEMP_DIR`; database PostgreSQL hanya menyimpan metadata teks dan hasil ekstraksi form, bukan data bytes PDF atau file OCR mentah.

Untuk pemeliharaan storage atau database lama:
```bash
uv run python scripts/migrate_ephemeral_storage.py
```

### Ingin Berjalan 100% Offline Tanpa Cloud API?
Cukup ubah baris berikut di `.env`:
```bash
ENABLE_TESSERACT_GEMINI=false
```
Sistem akan otomatis menggunakan pipeline offline rule-based lokal.

---

## Proteksi & Keamanan Unggahan Dokumen (Defense-in-Depth)

Sistem menerapkan inspeksi keamanan bertingkat (*defense-in-depth*) sebelum dokumen diproses oleh pipeline OCR/ekstraksi:

1. **Multi-Format & Validasi Magic Bytes (Anti-Spoofing)**:
   - Format yang didukung: **PDF, JPG, JPEG, PNG, dan WEBP**.
   - Integritas file diverifikasi langsung dari *magic bytes* header biner dokumen, bukan sekadar ekstensi nama file atau `Content-Type`. Upaya *MIME spoofing* atau *polyglot file* otomatis ditolak dengan pesan error yang jelas.

2. **Sanitasi Metadata & Privasi Gambar**:
   - Gambar yang diunggah otomatis di-*re-encode* secara aman melalui Pillow untuk membersihkan seluruh metadata EXIF, profil perangkat, dan potensi *active chunk* injeksi.

3. **Mitigasi DoS & Decompression Bomb**:
   - Batas maksimum piksel 60 MP (`MAX_IMAGE_PIXELS = 60000000`) mencegah serangan *decompression bomb* / *pixel flood*.
   - **Smart High-DPI Auto-Downscaling**: Pindaian resolusi tinggi (>3500px, misal scan 600 DPI) secara otomatis diperkecil secara proporsional ke batas aman 2500px menggunakan filter Lanczos agar OCR optimal tanpa risiko *Out-of-Memory* (OOM).
   - Validasi batas dimensi minimum ($\ge 300\times300\text{px}$) dan rasio aspek wajar ($\le 5.0:1$) untuk menangkal file *troll* atau *banner*.

4. **Inspeksi Mendalam Dokumen PDF**:
   - Maksimal 3 halaman (`MAX_PDF_PAGES = 3`) untuk mencegah *page bomb*.
   - Deteksi proteksi kata sandi / enkripsi.
   - Penolakan dokumen yang memuat lampiran biner (*embedded files*).
   - Pindaian objek aktif berbahaya pada tabel *xref* (`/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFiles`, `/RichMedia`).
   - Batas kanvas render maksimal 5000 pt untuk mencegah OOM saat proses rasterisasi.

5. **Rate Limiting (Sliding Window)**:
   - Endpoint upload dilindungi pembatas laju *in-memory* berbasis IP dengan jendela geser (*sliding window*).
   - Default: **30 unggahan per menit per IP** (`RATE_LIMIT_PER_MINUTE = 30`). Jika terlampaui, sistem mengembalikan status HTTP 429 *Too Many Requests* dengan header standar `Retry-After`.
---

## Hasil Evaluasi & Benchmark

### 1. Evaluasi Terpadu Master Data KHP 9-Field (Dataset Terpadu $N=104$)
Evaluasi pipeline terintegrasi (Gemini V2 Scope-Aware + Resolver Deterministik Taksonomi Universitas) pada 104 sertifikat terverifikasi:

| Dimensi Evaluasi | Tahap Awal Staging | Penyempurnaan Bilingual & Universal | Catatan Peningkatan |
|---|:---:|:---:|---|
| **Master 3-Field (Taksonomi Universitas)** | 80.45% (251/312 sel) | **81.73% (255/312 sel)** | **+4 sel (+1.28pt)** berkat pengenalan peran juara & masa bakti bilingual |
| **All-Cells 9-Field (End-to-End KHP)** | 72.97% (683/936 sel) | **73.40% (687/936 sel)** | 6 fakta sertifikat + 3 taksonomi master database (+0.43pt) |
| **Base 6-Field Ekstraksi Faktual** | 69.23% (432/624 sel) | **69.23% (432/624 sel)** | Kestabilan penuh pada field literal sertifikat (zero loss) |
| **Pencocokan Tuple Resmi Database AUCC** | 91.35% (95/104 dokumen) | **93.27% (97/104 dokumen)** | **97 sertifikat (93.27%)** sukses terpetakan otomatis ke ID resmi kegiatan |
| **Safety Net Review Manual** | 8.65% (9/104 dokumen) | **6.73% (7/104 dokumen)** | Terpangkas ke 7 dokumen yang fisiknya tidak memuat deskriptor jenis kegiatan |

*Catatan: Penyempurnaan terbaru mencakup dukungan bilingual (peran pemenang kompetisi, kepengurusan ormawa, dan general leadership roles) serta pembersihan frasa sertifikasi tanpa menyebut atau mencantumkan data privat mahasiswa.*
---

### 2. Riwayat Evaluasi Eksperimen Prompting LLM (Dataset Terpadu $N=104$)
Ringkasan perjalanan eksperimen teknik prompting LLM dari baseline awal hingga arsitektur final:

| Strategi / Arsitektur Prompt | Akurasi Tingkat | All-Cells (Exact) | Token / Doc | Estimasi Biaya / Doc | Status & Temuan Kunci |
|---|:---:|:---:|:---:|:---:|---|
| **V1 Baseline Produksi** | 61.54% | 62.50% | 1.463,5 tok | Rp 9,95 | Baseline awal. Rentan bias hierarki penyelenggara (13 event nasional salah ditebak menjadi fakultas). |
| **V2 Scope-Aware (Pilihan Standar)** | **82.69% (+21.15pt)** | **65.71% (+3.21pt)** | 1.576,2 tok | Rp 10,44 | **Winner Persepsi**. Prinsip eksplisit: *Cakupan Sasaran Peserta > Jenjang Penyelenggara*. Memangkas bias hierarki ke 5 kasus. |
| **V3 Decoupled 2-Stage** | 76.92% | 64.90% | 1.409,7 tok | Rp 9,77 (2 calls) | Pemisahan ekstraksi literal (Stage 1) dan tingkat CoT (Stage 2). Akurasi tingkat berada 5.77pt di bawah V2 dan butuh 2 panggilan API. |
| **V4 In-JSON Scope Signal** | 77.88% (-4.81pt) | 65.22% | 1.650,6 tok | Rp 11,16 | Pembatasan enum sinyal perantara membuat model over-konservatif; 56.73% dokumen jatuh ke internal kampus. |
| **V5 Natural Rationale Buffer** | 80.77% (-1.92pt) | 64.58% | 1.775,5 tok | Rp 12,57 | Menuliskan unit penyelenggara di awal buffer penalaran menginduksi bias atensi berurutan dan mendegradasi salinan teks literal. |
| **Web Search Grounding** | 77.66% (-4.26pt) | N/A | 1.723,2 tok | Rp 197,87 | Web search menimbulkan false positive pada artikel fakultas induk, latensi naik 3×, dan biaya membengkak ~19× lipat. |
| **Injeksi Enum Master ke Prompt** | 52.88% (-29.81pt) | 60.26% | 1.130,0 tok | Rp 8,50 | **Katastropik**. Memaksa LLM memilih 13 enum master resmi merusak penalaran. Keputusan: serahkan taksonomi ke resolver Python. |

---

### 3. Pipeline Ekstraksi Utama & Model Cloud LLM (Dataset Evaluasi $N=74$)
Evaluasi ekstraksi persepsi 6-field pada 74 teks sertifikat:

| Pipeline / Model | MACRO Exact (All-Cells) | Framework Exact (5 Field) | Akurasi Tingkat | Biaya / Dokumen | Rata-rata Latensi | Status / Keterangan |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Production Conditional + Gemini 3.1 Flash-Lite (V2 Scope-Aware)** | **70.27%** | **80.65%** | **83.78%** | **Rp10,91** | **2.23s** | **Arsitektur Persepsi Standar**. Menghilangkan bias hierarki penyelenggara. |
| Production Conditional + Gemini Baseline V1 | 67.12% | 81.29% | 62.16% | Rp10,40 | 1.89s | Baseline awal (terdistraksi bias kepanitiaan fakultas) |
| Direct Gemini 2.5 Flash-Lite | 58.78% | 61.89% | 43.24% | **Rp3,26** | 1.32s | Biaya termurah, akurasi tingkat lebih rendah |
| Direct Gemini 2.5 Flash | 58.56% | 57.84% | 62.16% | Rp38,94 | 4.62s | Latensi lambat dan biaya 4x lipat tanpa peningkatan akurasi |

---

### 4. Pipeline Offline Rule-Based Composite v4.x (Fallback Resmi — 0 LLM)
Ekstraksi lokal deterministik tanpa ketergantungan API eksternal (100% offline):

| Pipeline / Versi | MACRO Exact (All-Cells) | Framework Exact (5 Field) | MACRO Fuzzy | LLM Calls | Sifat / Arsitektur |
|---|:---:|:---:|:---:|:---:|---|
| **Combined v4.2 / Composite B8** | **76.13%** | **87.42%** | **77.93%** | **0** | **Best Offline Fallback**. 3 pilar OOD + High-DPI crop zoom 6.0×. |
| Combined v3 | 74.20% | 85.70%* | 88.30% | 0 | 5 branch composite (basis 384 sel non-empty) |
| Combined v2 | 74.20% | 80.70% | 80.70% | 0 | Port integrasi rule router v5 |
| Regex Baseline Legacy (v2) | 42.20% | — | — | 0 | Baseline regex awal historis |

---

### 5. Perbandingan Rekognisi Teks & OCR Engine
Evaluasi pembentukan teks input terhadap 74 dokumen sertifikat (49 pindaian/scan + 25 digital murni):

| Engine / Strategi OCR | MACRO Exact (All-Cells) | Framework Exact | Kinerja Pindaian (Scan-49) | Kinerja Digital (Emb-25) | Status Evaluasi |
|---|:---:|:---:|:---:|:---:|---|
| **Production Conditional (PyMuPDF + RapidOCR)** | **67.57%** | **81.29%** | **65.31%** | **72.00%** | **Pemenang Produksi**. Mencegah derau OCR pada PDF digital murni. |
| Tesseract Standalone Multi-PSM | 68.47% | 77.10% | 78.61% (nomor 87.88%) | 74.31% | Alternatif tangguh bila layer teks digital rusak |
| RapidOCR + Tesseract murni | 66.89% | 80.00% | 66.33% | 68.00% | Degradasi -4.0pt pada PDF digital akibat derau OCR |
| Tesseract OCR murni | 65.77% | 78.71% | 64.63% | 68.00% | Stabil pada pindaian, rentan pada font dekoratif digital |
| RapidOCR murni | 63.06% | 75.16% | 61.22% | 66.67% | Kecepatan tinggi namun akurasi nomor lebih rendah |
| PyMuPDF murni (Tanpa OCR) | 27.70% | 33.23% | 9.18% (collapse) | 64.00% | Gagal membaca dokumen scan tanpa layer teks |

---

### 6. Optimasi Mode PSM & Skala Resolusi OCR (Dataset Terpadu $N=104$)
Eksperimen `EXP-OCR-PSM-DPI-001` menguji 12 kombinasi skala rendering (*Zoom* 2.0, 3.0, 4.0) dan mode segmentasi halaman Tesseract (*Multi-PSM 3-Pass* vs *Single-Pass PSM 6, PSM 3, PSM 11*):

| Konfigurasi / Varian | Skala Resolusi | Mode Tesseract PSM | Macro Exact | Macro Fuzzy | Waktu Tesseract | Status Evaluasi |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **`z3_psm6` (Pilihan Produksi)** | **Zoom 3.0 (~300 DPI)** | **Single-Pass `--psm 6`** | **67.31% (+0.64pt)** | **73.56%** | **Tercepat** | **PASS — Diadopsi**. Tanpa duplikasi teks, nomor & tanggal 100% terjaga |
| `z3_psm3` | Zoom 3.0 (~300 DPI) | Single-Pass `--psm 3` | 67.47% (+0.80pt) | 73.56% | Cepat | PASS — Menghilangkan 1 nomor sertifikat terformat unik |
| `control_z3_multi` (Baseline) | Zoom 3.0 (~300 DPI) | Multi-Pass (`""` + 6 + 11) | 66.67% | 72.76% | Lambat (3-pass) | CONTROL — Baseline lama (duplikasi teks dan overhead 3×) |
| `z3_psm11` | Zoom 3.0 (~300 DPI) | Single-Pass `--psm 11` | 66.99% (+0.32pt) | 72.92% | Sedang | PASS — Kurang optimal pada blok teks terstruktur |
| `z2_psm6` / `z2_multi` | Zoom 2.0 (~200 DPI) | PSM 6 / Multi-Pass | 65.87% – 66.51% | 72.12% – 72.60% | Sangat Cepat | FAIL — Penurunan akurasi nomor (-1.0pt) & tanggal (-2.0pt) |
| `z4_psm6` / `z4_multi` | Zoom 4.0 (~400 DPI) | PSM 6 / Multi-Pass | 66.03% – 66.19% | 71.79% – 72.44% | Sangat Lambat (4s+) | FAIL — Latensi membengkak ekstrem & risiko OOM tanpa gain akurasi |

**Peningkatan Ketahanan Produksi**:
1. **Single-Pass Tesseract `--psm 6`**: Menggantikan penggabungan 3-pass multi-PSM lama pada `ocr_fallback.py`, memangkas overhead pemanggilan berulang sekaligus membersihkan derau teks duplikat.
2. **Resolution Clamping Guard**: Pembatasan dimensi maksimum rendering PDF (`max_allowed = 2500px` long-edge pada `pdf_fast_path.py`) untuk menjamin dokumen dengan ukuran fisik cetak besar tidak memicu *Out of Memory* (OOM).
---

### 7. Optimasi Alur Buffer Gambar In-Memory & Latensi OCR (Dataset Terpadu $N=104$)
Eksperimen `EXP-OCR-LATENCY-001` mengevaluasi efisiensi alur transmisi buffer gambar di memori (*Direct Buffer Pipeline*) serta alokasi thread CPU terhadap latensi *end-to-end* pada 104 sertifikat terpadu:

| Varian Alur Buffer | Waktu Buffer Prep | Waktu RapidOCR | Waktu Tesseract | Waktu Total / Dokumen | Penghematan | Status Evaluasi |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Direct Buffer In-Memory (`PageImageBuffer`)** | **6.4 ms** | **2.76s** | **1.09s** | **4.03s** | **-257 ms (-6.0%)** | **PASS — Diadopsi**. Zero-loss bit-for-bit, 100% identik dengan kontrol |
| Baseline (PNG Byte Encode/Decode di RAM) | 263.9 ms | 2.76s | 1.09s | 4.28s | Baseline | CONTROL — Terbebani siklus kompresi/dekompresi PNG di memori |
| Direct Buffer + Grayscale Tesseract | 8.7 ms | 2.76s | 0.67s | 3.61s | -680 ms (-15.9%) | FAIL — Ditolak akibat penurunan performa nomor sertifikat (-0.96pt) |

**Keunggulan Produksi Direct Buffer**:
1. **Zero-Copy View**: Matriks piksel mentah PyMuPDF langsung dipetakan ke NumPy array format BGR untuk RapidOCR dan PIL RGB Image untuk Tesseract tanpa proses encode/decode PNG.
2. **Eliminasi Latensi Murni**: Memangkas waktu persiapan gambar sebesar **97.6% (dari 264 ms ke 6.4 ms)** tanpa mengubah satu karakter pun pada hasil ekstraksi teks.

---

### 8. Arsip Eksperimen Model Named Entity Recognition (Tidak Dipakai Pipeline)
Evaluasi token classification supervised pada 74 teks korpus OCR Tesseract (310 sel framework non-empty):

| Arsitektur / Model NER | Framework Exact | Framework Fuzzy | Ketahanan OOD Mutasi | Keterangan & Batasan |
|---|:---:|:---:|:---:|---|
| IndoBERT-ner-gold Fine-Tuned | 44.52% | 57.10% | -4.2pt drop | Monolingual Indonesia 334M, 5-Fold Stratified OOF |
| XLM-RoBERTa Large Fine-Tuned | 43.55% | 55.48% | -5.8pt drop | Multilingual 560M, kebutuhan VRAM tinggi (7.1 GB) |
| mDeBERTa-v3-base Fine-Tuned | 34.84% | 51.29% | -7.1pt drop | Multilingual 86M, representasi entitas Indonesia kurang optimal |
| IndoBERT Pre-trained v1 (Zero-Shot) | 12.80% | 24.50% | — | Baseline tanpa penyesuaian domain sertifikat |

> Eksperimen NER pada bagian ini hanya arsip. Pipeline aktif memakai Tesseract sebagai sumber OCR dan extractor produksi; GLiNER serta model NER tidak dipanggil.

---

### Penjelasan Metrik & Formula Evaluasi

Evaluasi menggunakan formula standar baku:

1. **MACRO Exact Match**:
   Mengukur persentase prediksi yang cocok persis 100% terhadap Ground Truth setelah normalisasi kanonikal:
   $$\text{Exact Match} = \frac{1}{N} \sum_{i=1}^{N} \mathbf{1}(\text{Prediksi}_i = \text{GroundTruth}_i)$$

2. **Fuzzy Match (Threshold $\ge 0.75$)**:
   Memberikan toleransi kecocokan semantik untuk akronim resmi organisasi dan substring relevan nama kegiatan.

3. **Perbedaan Basis Evaluasi: Framework vs All-Cells**:
   - **Framework (5 Field)**: Menghitung akurasi hanya pada 5 field inti (*nama kegiatan, nomor sertifikat, penyelenggara, tanggal mulai, tanggal selesai*) yang memiliki target data non-kosong.
   - **All-Cells (6 Field / 9 Field)**: Menghitung akurasi seluruh field form KHP secara end-to-end (termasuk tingkat dan taksonomi master kegiatan), memperhitungkan penalti jika sistem mengisi nilai pada field yang seharusnya kosong.

---

## Pengujian Sistem

### 1. Pengujian Unit Lokal
Jalankan pengujian unit dan verifikasi fungsionalitas lokal dengan:

```bash
uv run pytest tests/ -v
```

### 2. Otomasi CI/CD (GitHub Actions)
Repositori ini dilengkapi pipeline **Continuous Integration (CI)** otomatis (`.github/workflows/ci.yml`) yang berjalan pada setiap *push* dan *pull request*:
- **Job `security-audit`**: Memindai seluruh berkas untuk mencegah kebocoran file `.env`, kunci API aktif (`AIza...`, Stripe, OpenAI), berkas PDF privat, dan dump database kampus privat (`khp/*`).
- **Job `test`**: Memasang dependensi sistem Tesseract OCR (dengan kamus bahasa Indonesia), kompilasi sintaks Python (`compileall`), dan menjalankan seluruh rangkaian 402 unit tests secara terisolasi.

---

## Endpoint API Utama

```http
# Ekstraksi & Formulir KHP Mahasiswa
POST   /api/v1/extract                 # One-shot ekstraksi sertifikat -> JSON AUCC KHP Master (Auth API Key: sk-)
POST   /api/documents                 # Upload sertifikat (PDF, JPG, PNG, WEBP) dengan security guard & rate limit
GET    /api/documents/{id}/result     # Ambil status job dan hasil ekstraksi 9-field form KHP
GET    /api/options                   # Opsi dropdown master data KHP berelasi untuk cascading filter frontend

# Administrasi & Ekspor Data (Basic Auth: ADMIN_USERNAME & ADMIN_PASSWORD)
GET    /api/admin/documents/export    # Ekspor riwayat dokumen & hasil ekstraksi ke format Excel/CSV (?format=xlsx|csv)
GET    /api/admin/khp/export          # Ekspor tabel master taksonomi universitas ke Excel/CSV (?table=rules&format=xlsx|csv)
GET    /api/admin/khp/rules           # Listing & pencarian aturan master KHP dengan pagination & filter
POST   /api/admin/khp/rules           # Tambah aturan pemetaan master KHP baru
PATCH  /api/admin/khp/rules/{rule_id} # Perbarui aturan master KHP yang ada
DELETE /api/admin/khp/rules/{rule_id} # Hapus aturan master KHP (?hard=true untuk hard delete)

# Sistem & Monitoring
GET    /metrics                       # Metrik Prometheus (ekstraksi, latensi, error rate)
GET    /healthz                       # Health check endpoint
```

---

## Integrasi API Eksternal & Pengujian Jarak Jauh (Cloudflare Tunnel)

Sistem menyediakan endpoint satu-langkah `POST /api/v1/extract` yang dirancang untuk integrasi langsung dengan aplikasi frontend eksternal (React, Vue, mobile) tanpa perlu logika polling:
- **Autentikasi:** API Key berbasis header `X-API-Key: sk-...` atau `Authorization: Bearer sk-...`.
- **Output:** JSON siap pakai berisi teks bersih sertifikat, ID & Label Master AUCC KHP (`id_kelompok_kegiatan`, `id_kegiatan_1`, `id_tingkat`, `id_jabatan_prestasi`), dan Primary Key tabel AUCC (`id_kegiatan_2`).
- **Pengujian Jarak Jauh:** Dapat diuji dari luar jaringan lokal menggunakan Cloudflare Tunnel tanpa perlu konfigurasi server publik.

> 📖 **Panduan Lengkap & Contoh Kode:**
> Silakan baca [Panduan Integrasi API & Cloudflare Tunnel](docs/API_INTEGRATION_GUIDE.md) untuk spesifikasi kamus data lengkap, contoh pemanggilan cURL, JavaScript Fetch/Axios, Python requests, dan cara menjalankan Cloudflare Tunnel.

---
## Visualisasi Arsitektur & Knowledge Graph (Graphify)

Repositori ini mendukung pemetaan dependensi modul dan relasi fungsi menggunakan **Graphify** untuk menghasilkan graf pengetahuan interaktif (*interactive knowledge graph*) dari seluruh fungsi, relasi antar-berkas, dan alur pipeline ekstraksi.

### 1. Menghasilkan Knowledge Graph Lokal
Pastikan `uv` sudah terpasang, lalu jalankan:

```bash
# Jalankan ekstraksi AST & clustering graf lokal
uv tool run graphifyy
```

### 2. Output & Navigasi Graf
Hasil analisis disimpan di folder `graphify-out/` (otomatis terabaikan oleh `.gitignore` sehingga tidak mengotori repositori):

- **`graphify-out/graph.html`**: Visualisasi interaktif graf 2D/3D mandiri yang dapat dibuka langsung di browser (tanpa perlu web server tambahan).
- **`graphify-out/GRAPH_REPORT.md`**: Laporan audit arsitektur lengkap, mencakup *God Nodes* (abstraksi inti), koneksi tak terduga (*surprising connections*), dan metrik kohesi modul.
- **`graphify-out/graph.json`**: Data graf terstruktur untuk kueri traversal dependensi kode.

---

## Dokumentasi Terkait

| Dokumen / Antarmuka | Deskripsi |
|---|---|
| [Swagger API Documentation](/docs) | Dokumentasi interaktif OpenAPI untuk pengujian endpoint upload dan status ekstraksi (`/docs`) |
| [ReDoc API Documentation](/redoc) | Dokumentasi alternatif ReDoc untuk spesifikasi skema data API |
| [Frontend Guide](frontend/README_FRONTEND.md) | Panduan antarmuka web, penanganan cascading dropdown, dan modal pencarian kegiatan |
| [API Integration Guide](docs/API_INTEGRATION_GUIDE.md) | Panduan lengkap integrasi endpoint `/api/v1/extract`, format API Key, contoh cURL/JS/Python, dan setup Cloudflare Tunnel |
| **Knowledge Graph Arsitektur** | Peta interaktif graf dependensi fungsi dan arsitektur pipeline via Graphify (lihat panduan di atas) |
