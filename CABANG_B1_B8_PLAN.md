# Plan Eksperimen Cabang B1-B8: Penguatan, Validasi Empiris, dan Kandidat Komposit Pipeline

## Context

Berdasarkan temuan audit QA/QC terhadap pipeline staging v4.2, ditemukan 9 kelemahan konkret (anchor activity bleed, DPKKA digit corruption, Roman overcorrection, substring router landmines, review threshold boundary bug, dan modul High-DPI crop yang belum terhubung di execution path) serta gap pembuktian 4-lapis empiris. Rencana ini menetapkan spesifikasi eksekusi lengkap untuk 8 cabang eksperimen terisolasi (B1 hingga B8) yang dibangun sepenuhnya di dalam direktori `tests/` tanpa memodifikasi kode produksi `backend/app/` maupun mengubah staging bundle v4.2 secara prematur. Setiap cabang dijalankan dengan protokol eksperimen penuh (B0-B11), kriteria gate ketat, pengujian unit mandiri, dan pelaporan metrologi formal (GT v9 + matcher v2).

---

## Approach

### 1. Cabang B1 — Fast Semantic Anchor untuk High-DPI Region Crop (NC-001 Pattern)

Mengintegrasikan modul `backend/app/services/high_dpi_crop.py` ke dalam harness evaluasi eksperimen 2-pass nomor dengan mengganti anchor full-page RapidOCR (penyebab floor latency 3.5s pada NC-003) dengan fast text-search anchor berbasis PyMuPDF.

- **B0 Dedup**: Cek `docs/experiments_ledger.md` untuk NC-001 s/d NC-004. Re-try condition NC-003 terpenuhi karena anchor tidak lagi menggunakan full-page OCR, melainkan penelusuran teks/blok PDF digital.
- **Implementasi Harness Eksperimen**:
  * Buat `tests/ocr_high_dpi_anchor.py` yang mendefinisikan fungsi `resolve_number_bbox_fast(pdf_bytes: bytes) -> fitz.Rect | None`.
  * Fungsi memeriksa `page.search_for()` dengan keyword berurutan: `["NOMOR", "Nomor", "NO.", "No.", "NUMBER", "SERTIFIKAT"]`.
  * Jika keyword ditemukan, validasi apakah blok teks tersebut berdekatan dengan pola angka atau slash dinas (`r"\d{1,5}\s*/"`).
  * Jika tidak ada text layer (PDF murni scan gambar), fallback ke bounding box RapidOCR murah beresolusi standar (downscale 1.5x) hanya untuk mencari koordinat baris nomor.
  * Setelah rect didapatkan, lakukan re-render region pada zoom 6.0x menggunakan `high_dpi_crop.crop_and_ocr_number_region` dan ekstraksi nomor via `extract_certificate_number`.
- **Benchmark & Komparasi**:
  * Buat `tests/benchmark_b1_high_dpi.py`.
  * Evaluasi pada 49 sertifikat scan (`tests/benchmark_runs/ocr_experiment/baseline_rapid_tess`).
  * Bandingkan 3 varian: Baseline (tanpa crop), Control NC-001 (RapidOCR anchor), dan Fast Anchor B1.
- **Kriteria Gate B1**:
  * Akurasi nomor sertifikat pada 49 scan cert >= 60.6% (19/33 certs terisi).
  * Rata-rata waktu resolusi anchor < 0.50s/cert (turun dari 3.54s pada NC-003).
  * Pertambahan latency total pipeline <= 1.80s/cert.
  * Zero regression pada tanggal dan penyelenggara.
- **Dokumentasi & Ledger**:
  * Simpan laporan di `docs/report/b1_high_dpi_anchor_report.md`.
  * Catat entri `B1-HIGH-DPI-001` di `docs/experiments_ledger.md`.
  * Commit otomatis: `feat(ocr): B1 fast semantic anchor for high-DPI number crop`.

---

### 2. Cabang B2 — Uji Ketahanan Out-of-Distribution (OOD Stress Testing) untuk Combined v4.2

Menutup evidence gap paling kritis pada handoff v44 dengan menguji secara langsung fungsi `apply_combined_v4_2` terhadap mutasi entitas dan injeksi noise OCR.

- **B0 Dedup**: Cek OOD-001 s/d OOD-003 pada ledger. Belum ada pengujian OOD untuk staging bundle v4.x.
- **Implementasi Probe**:
  * Buat `tests/ood_probe_v4_2.py` mengadaptasi arsitektur `tests/ood_probe_v3.py`.
  * Definisikan pipeline target: `offline_v4_2(text: str) -> dict[str, str]` yang mengeksekusi `extract_certificate_fields(text)` dilanjutkan `apply_combined_v4_2(extracted, text)` dan pemetaan form.
  * Jalankan 2 sumbu gangguan deterministik (SEED=42):
    1. **Template & Entity Mutation**: UNAIR -> UNS, FTMM -> FST, penggantian nama event spesifik (Airnology, Kakiwima, SPECTA, Brief) dengan string generik ("Kompetisi Sains Nasional", "Seminar Inovasi Teknologi").
    2. **OCR Noise Confusion**: Injeksi substitusi karakter nyata (`5<->S`, `8<->B`, `0<->O`, `1<->I`) dan word-merge pada level 0%, 10%, 25%, dan 50%.
- **Metrik Evaluasi**:
  * Hitung MACRO exact/fuzzy pada seluruh 74 sertifikat dataset.
  * Hitung Free-Institution Macro (rata-rata field bebas institusi: nama_kegiatan, tanggal_mulai, tanggal_selesai, tingkat).
  * Ukur degradation drop v4.2 vs baseline produksi v9 pada setiap level gangguan.
- **Kriteria Gate B2**:
  * Pada mutasi entitas: penurunan Free-Institution Macro <= 2.0pt vs unmutated baseline.
  * Pada noise 10%: penurunan MACRO exact v4.2 <= drop_v9 + 1.5pt.
  * Pada noise 25% dan 50%: penurunan MACRO exact v4.2 <= drop_v9 (zero excess fragility).
- **Dokumentasi & Ledger**:
  * Tulis laporan komprehensif di `docs/report/b2_ood_v4_2_report.md` memuat tabel perbandingan kurva degradasi.
  * Catat entri `B2-OOD-001` di `docs/experiments_ledger.md`.
  * Commit otomatis: `test(ood): B2 empirical OOD stress testing for combined v4.2 bundle`.

---

### 3. Cabang B3 — Kalibrasi Confidence Berbasis Pola & Safety Net Review

Memperbaiki kelemahan Pillar 3 v4.2 di mana confidence di-set tinggi secara statis (0.92–0.98) dan nilai single-date 0.80 lolos dari review threshold.

- **B0 Dedup**: Cek REVIEW-001 di ledger (prototipe F6, recall 98.6%). Cabang B3 mengintegrasikan logika tersebut secara spesifik untuk bundle v4.2.
- **Implementasi Modul Kalibrasi**:
  * Buat `tests/calibrated_confidence_v4_2.py`.
  * Definisikan fungsi `calibrate_v4_2_confidence(fields: dict[str, ExtractedValue], raw_text: str) -> dict[str, ExtractedValue]`.
  * Skema kalibrasi dinamis per pola:
    1. `nama_kegiatan_sertifikasi`:
       - PKKMB fallback -> confidence 0.95 (terbukti akurat 4/4).
       - Structural semantic anchor v8 -> confidence 0.85 (jika lolos validasi batas kata dan tanpa bleed).
       - Quoted event -> confidence 0.82.
       - Hardcoded corpus keywords (SPECTA, KARSA, Falcon, Health Buddies) -> confidence 0.55 (memicu review agar tidak terjadi silent error pada event baru).
       - Base regex fallback -> confidence 0.60.
    2. `nomor_bukti_fisik_nomor_sertifikasi`:
       - Strict official regex tanpa modifikasi -> confidence 0.95.
       - Mengalami perbaikan Roman month (`normalize_nomor_v5`) -> confidence 0.78 (otomatis memicu `needs_review=True` karena < 0.80).
       - Mengalami perbaikan DPKKA -> confidence 0.78.
    3. `waktu_mulai_pelaksanaan` & `waktu_selesai_pelaksanaan`:
       - Interval eksplisit (regex 1-5) -> confidence 0.95.
       - Single numeric date (`\d{1,2}/\d{1,2}/\d{4}`) -> confidence 0.75 (diturunkan dari 0.80 agar memicu review).
       - Date token pair -> confidence 0.88.
    4. `tingkat`:
       - Base router rules (high-frequency >= 5) -> confidence 0.98.
       - Disambiguation rules (LOW-N) -> confidence 0.84 (memicu verifikasi bila field lain meragukan).
- **Benchmark Evaluasi**:
  * Buat `tests/benchmark_review_v4_2.py`.
  * Hitung Certificate-level Review Recall (% sertifikat salah yang ter-flag `needs_review=True`), Review Precision, dan False Alarm Rate pada sertifikat 100% benar.
- **Kriteria Gate B3**:
  * Certificate-level review recall pada sertifikat yang memiliki kesalahan >= 95.0%.
  * Weak field review recall (nama_kegiatan dan nomor) >= 88.0%.
  * False review rate pada sertifikat yang 100% exact match <= 20.0%.
- **Dokumentasi & Ledger**:
  * Simpan laporan di `docs/report/b3_calibrated_confidence_report.md`.
  * Catat entri `B3-CONF-001` di `docs/experiments_ledger.md`.
  * Commit otomatis: `feat(review): B3 pattern-based calibrated confidence for v4.2 safety net`.

---

### 4. Cabang B4 — Pengerasan Router Disambiguasi & Re-validasi Stratified 5-Fold CV

Mengeliminasi false positive akibat substring trigger tanpa word-boundary pada `_DISAMBIG_RULES` dan memvalidasi seluruh 8 rule kontekstual dengan 5-fold CV.

- **B0 Dedup**: Cek ROUTER-001 s/d ROUTER-006 di ledger.
- **Pengerasan Rule di `tests/router_disambig_v7.py`**:
  * `kim_unair`: Ubah dari `"KIM" in a` menjadi `re.search(r"\bKIM\b", a) and not re.search(r"\bKIMIA\b|\bKIMIAWI\b", a, re.I)`.
  * `intl_explicit`: Ubah dari `"OF INFORMATICS ENGINEERING" in u` menjadi mendeteksi institusi internasional eksplisit (misal `INSTITUT FRANÇAIS` atau penyelenggara luar negeri terverifikasi), dan tolak jika didahului `FACULTY OF` / `DEPARTMENT OF` / `FAKULTAS`.
  * `ub_external_event`: Ubah `"UB" in o` menjadi `re.search(r"\bUB\b|\bBRAWIJAYA\b|\bFILKOM\b", o)` (mencegah match pada kata "CLUB" atau "HUBUNGAN").
  * `bem_nasional_act`: Pastikan `"HARI ANAK NASIONAL"` utuh, bukan hanya `"HARI ANAK"`.
  * `direktur_kemahasiswaan_unair`: Integrasikan ke dalam daftar rule formal dengan guard institusi Airlangga eksplisit.
- **Pengujian Unit Negatif & Adversarial**:
  * Buat `tests/test_router_disambig_hardening.py`.
  * Uji kasus kontroversial: `"Olimpiade KIMIA"`, `"Robotics Club Gelar Rasa"`, `"Faculty of Informatics Engineering Seminar"`, `"BEM FKM Hari Anak Kampus"`. Seluruh kasus negatif WAJIB menghasilkan `(None, "")` (tidak ter-route).
- **Validasi Statistik 5-Fold Cross Validation**:
  * Buat `tests/stat_validation_disambig.py`.
  * Bagi 74 sertifikat menjadi 5 stratified holdout folds.
  * Uji presisi setiap rule di fold yang tidak melihat data latih.
- **Kriteria Gate B4**:
  * Min-Fold Precision 100.0% pada seluruh 5 fold untuk semua rule (0 false positive di holdout).
  * 100% lulus pada semua adversarial negative unit tests.
  * Total coverage router pada korpus 74 tidak boleh turun (tetap >= 63/74 routed).
- **Dokumentasi & Ledger**:
  * Simpan laporan di `docs/report/b4_router_hardening_report.md`.
  * Catat entri `B4-ROUTER-001` di `docs/experiments_ledger.md`.
  * Commit otomatis: `fix(router): B4 hardened regex boundaries and 5-fold CV for disambiguation rules`.

---

### 5. Cabang B5 — Perbaikan Anchor Semantik Struktural & Pembatasan Boundary Bleed

Memperbaiki regex `_STRUCTURAL_ACT_ID` dan `_STRUCTURAL_ACT_EN` agar tidak menelan baris penyelenggara atau meluas ke akhir teks saat kata penutup tidak baku.

- **B0 Dedup**: Cek C1-001, ACT-006, dan EXP-V4-003 di ledger.
- **Refactoring Ekstraktor di `tests/activity_extractor_v9.py`**:
  * Tambahkan kata penutup variasi Indonesia ke `_STRUCTURAL_ACT_ID`: `diadakan`, `diadakan oleh`, `bekerja sama dengan`, `yang diadakan`, `yang diselenggarakan oleh`, `bertempat di`.
  * Tambahkan kata penutup variasi Inggris ke `_STRUCTURAL_ACT_EN`: `hosted by`, `presented by`, `in cooperation with`, `in collaboration with`.
  * Hapus fallback `$` tanpa batas dari closing alternation regex. Ganti dengan batas capture ketat: panjang maksimal 120 karakter atau maksimal 18 kata.
  * Tambahkan sanitasi residu: strip tanda petik pembuka/penutup yang tidak sepasang (`"`, `'`, `“`, `”`) dan strip newline di dalam teks kegiatan menjadi satu spasi.
- **Pengujian Unit Robustness**:
  * Buat `tests/test_structural_act_robustness.py`.
  * Uji kasus yang sebelumnya gagal pada audit QA:
    `"sebagai Panitia dalam acara Karya Inovasi Mahasiswa 2026 yang diadakan oleh BEM FTMM pada tanggal 10 Maret 2026"` -> hasil WAJIB bersih `"Karya Inovasi Mahasiswa 2026"`, tanpa menelan kata `"yang diadakan oleh BEM FTMM"`.
- **Benchmark Komparasi**:
  * Buat `tests/benchmark_activity_v9.py`.
  * Evaluasi akurasi nama kegiatan pada 74 sertifikat GT v9.
- **Kriteria Gate B5**:
  * Akurasi exact match nama kegiatan >= 79.7% (zero regression vs v4.2).
  * Fuzzy match nama kegiatan >= 83.8%.
  * 0 kejadian organizer bleeding pada seluruh kasus uji adversarial.
- **Dokumentasi & Ledger**:
  * Simpan laporan di `docs/report/b5_structural_activity_report.md`.
  * Catat entri `B5-ACT-001` di `docs/experiments_ledger.md`.
  * Commit otomatis: `fix(extractor): B5 expanded structural anchors and anti-bleed bounds for activity extraction`.

---

### 6. Cabang B6 — Perbaikan Normalisasi Nomor & Guard Format Surat Dinas

Memperbaiki bug penambahan digit pada DPKKA serta membatasi normalisasi angka Romawi agar tidak merusak format nomor non-dinas.

- **B0 Dedup**: Cek NUM-003 dan EXP-V4-003 di ledger.
- **Refactoring Normalizer di `tests/nomor_normalizer_v6.py`**:
  * Perbaiki DPKKA cleaner: ganti `re.sub(r"^[O0]+", "0000", v)` dengan pemetaan 1-ke-1 berbasis panjang: `v.replace("O", "0")`. Dengan demikian `"OOO4"` tetap 4 digit (`"0004"`), `"O0OO3"` tetap 5 digit (`"00003"`), dan `"0004"` tetap `"0004"`.
  * Perluas toleransi prefix nomor: izinkan `NOMOR:`, `Nomor:`, `NO:`, `No:`, `NO.`, `No.` secara seragam.
  * Tambahkan Guard Format Romawi: perbaikan Romawi (`normalize_nomor_v5`) hanya diterapkan jika nomor memiliki struktur minimal 3 segmen dengan slash (`r"[A-Z0-9.\- ]+/[IVXLCDM1l|]{1,5}/\d{4}$"`). Jika segmen ekor hanya berupa angka `1` tunggal tanpa konteks bulan Romawi, tandai dengan metadata perbaikan dan turunkan confidence menjadi 0.78 agar diverifikasi pengguna.
- **Unit Testing Preservasi Digit**:
  * Buat `tests/test_nomor_v6.py`.
  * Test case invariant digit:
    - `"NO: OOO4/DPKKA/KM/I/2026"` -> `"0004/DPKKA/KM/I/2026"` (4 digit terjaga).
    - `"NO: O0OO3/DPKKA/KM/I/2026"` -> `"00003/DPKKA/KM/I/2026"` (5 digit terjaga).
    - `"NOMOR: 0004/DPKKA/KM/I/2026"` -> `"0004/DPKKA/KM/I/2026"` (prefix NOMOR didukung).
    - `"SERT-123/FTMM/1/2024"` -> nilai diproses tetapi menghasilkan flag review.
- **Benchmark Evaluasi**:
  * Buat `tests/benchmark_nomor_v6.py`.
  * Evaluasi pada 74 sertifikat GT v9.
- **Kriteria Gate B6**:
  * Akurasi nomor exact match >= 66.7% (all-cells) / 88.5% (non-empty).
  * 100% lolos pada unit test invariant panjang digit.
  * Zero regression vs baseline v4.2.
- **Dokumentasi & Ledger**:
  * Simpan laporan di `docs/report/b6_nomor_normalizer_report.md`.
  * Catat entri `B6-NUM-001` di `docs/experiments_ledger.md`.
  * Commit otomatis: `fix(nomor): B6 length-preserving DPKKA cleaner and gated Roman numeral month repairs`.

---

### 7. Cabang B7 — Audit De-Corpusing & Dekopling String Ter-memorasi

Mengidentifikasi, mengukur, dan mendekopel seluruh string hardcode dari basis kode eksperimen ke dalam katalog data transparan guna memastikan kepatuhan pada Lapis 3 (Anti-Hardcoding).

- **B0 Dedup**: Cek ORG-002, ACT-006, NUM-003 di ledger.
- **Audit & Pemetaan Hardcode**:
  * Buat script audit `tests/decorpusing_audit.py`.
  * Scan dan inventarisasi seluruh literal string yang terikat pada sertifikat tertentu:
    1. Nomor spesifik: `"270/A.5/SOCIAL ACTION/BEM FEB UNAIR/IX/2023"`, `"06/001/B/P.GIRI STAT/HMP STATISTIKA/IV/2026"`.
    2. Kegiatan spesifik: `"KARSA FTMM 2024"`, `"SPECTA 2024"`, `"Falcon Project"`, `"Health Buddies"`, `"Digital Campaign 2023"`, `"Give Yourself A Break"`, `"From Discrete Mathematics"`, `"Agentic AI"`.
    3. Penyelenggara spesifik: `"himasta"` -> `"Himpunan Mahasiswa Statistika"`, `"FORKAS"`.
- **Ablasi Pengukuran Dampak**:
  * Jalankan benchmark 74 sertifikat dalam 2 mode:
    - Mode A (Assisted): Dengan string hardcode aktif.
    - Mode B (Pure Semantic): Dengan seluruh string hardcode dinonaktifkan (hanya regex generik dan structural semantic anchors B5/B6).
  * Hitung selisih akurasi (delta assist) per field untuk mengetahui ceiling performa OOD yang murni.
- **Katalog & Dekopling Data**:
  * Buat `docs/report/decorpusing_catalog.md` yang memuat tabel:
    Literal String | File Sumber | Cert Target | Firing Freq | Rekomendasi Generalisasi Semantic
- **Kriteria Gate B7**:
  * 100% literal hardcode terinventarisasi dengan dokumentasi asal-usul sertifikatnya.
  * Terbentuk baseline metrik murni (Pure Semantic Macro) sebagai acuan OOD yang objektif.
- **Dokumentasi & Ledger**:
  * Catat entri `B7-DECORP-001` di `docs/experiments_ledger.md`.
  * Commit otomatis: `docs(audit): B7 decorpusing audit and pure semantic ablation report`.

---

### 8. Cabang B8 — Matriks Keputusan & Kandidat Produksi Komposit (Composite Candidate)

Menyatukan seluruh perbaikan yang terbukti lulus gate dari cabang B1 s/d B7 ditambah integrasi HYB-003 (organizer text-merge rapid-only tanpa LLM, 0 biaya, +8.2pt) ke dalam satu modul kandidat komposit terisolasi.

- **B0 Dedup**: Cek HYB-COMBINED-001 dan EXP-V4-003 di ledger.
- **Perakitan Modul Komposit di `tests/composite_v4_candidate.py`**:
  * Gabungkan komponen-komponen terbaik yang lulus uji:
    1. Fast Semantic Anchor High-DPI Crop dari B1 (untuk nomor resolusi tinggi).
    2. Kalibrasi confidence dinamis dari B3 (safety net review).
    3. Router disambiguasi yang diperkeras dari B4 (min-fold 100%).
    4. Ekstraktor kegiatan struktural v9 dari B5 (anti-bleed).
    5. Normalizer nomor v6 dari B6 (preservasi digit dan guard format).
    6. HYB-003 rapid-only text merge untuk penyelenggara kegiatan.
- **Benchmark Komparasi Komprehensif**:
  * Buat `tests/benchmark_composite_v4_candidate.py`.
  * Jalankan benchmark komparasi 3 arah pada seluruh 74 sertifikat GT v9:
    1. Baseline Produksi Saat Ini (v9 offline, 55.7% macro).
    2. Staging Bundle v4.2 Saat Ini (76.82% all-cells macro).
    3. Composite Candidate B8.
- **Penyusunan Bukti 4-Lapis Lengkap**:
  * Siapkan data untuk 4 tabel pembuktian empiris:
    - Tabel 1: Stratified 5-Fold Cross Validation router precision.
    - Tabel 2: Kurva OOD Stress Test (mutasi entitas & noise 10%, 25%, 50%).
    - Tabel 3: Audit Structural Semantic Anchors (laporan transparansi B7).
    - Tabel 4: Matriks Kalibrasi Review & Confusion Matrix (Safety Net).
- **Kriteria Gate B8**:
  * MACRO exact match (all-cells) >= 78.0% (target peningkatan > 1.2pt vs v4.2).
  * Non-empty framework MACRO exact >= 89.0%.
  * Zero regression pada setiap field individual vs v4.2.
  * Seluruh 4 lapis pembuktian empiris terpenuhi 100%.
- **Dokumentasi & Ledger**:
  * Simpan laporan final di `docs/report/composite_v4_candidate_report.md`.
  * Catat entri `B8-COMPOSITE-001` di `docs/experiments_ledger.md`.
  * Regenerasi summary: `uv run python scripts/generate_runs_summary.py`.
  * Update handoff ke versi berikutnya (`docs/handoff_v45.md`).
  * Commit otomatis: `feat(pipeline): B8 composite production candidate bundle and 4-pillar empirical proof`.

---

## Critical Files & Anchors

1. `backend/app/services/combined_extractor.py`:
   - Referensi kode staging bundle v4.2 (`apply_combined_v4_2`, `extract_activity_v8`, `normalize_nomor_v5`, `_DISAMBIG_RULES`). Dijadikan acuan baseline pembanding untuk seluruh cabang eksperimen di `tests/`.
2. `backend/app/services/high_dpi_crop.py`:
   - Referensi modul crop zoom 6.0x mandiri. Menjadi basis integrasi fast anchor pada Cabang B1.
3. `tests/ood_probe_v3.py`:
   - Template arsitektur pengujian OOD (mutasi entitas & kurva noise OCR). Menjadi dasar pembuatan `tests/ood_probe_v4_2.py` pada Cabang B2.
4. `tests/stat_validation.py`:
   - Template pengujian stratified 5-fold cross validation. Menjadi dasar verifikasi statistik pada Cabang B4.
5. `Ground_Truth_Sertifikat_v9.csv`:
   - Dataset acuan kebenaran evaluasi (74 sertifikat) yang wajib digunakan secara konsisten bersama `tests/matchers.py` (Matcher v2).

---

## Verification

Setiap cabang eksperimen wajib diverifikasi secara independen sebelum beralih ke cabang berikutnya:

1. **Verifikasi B1 (High-DPI Fast Anchor)**:
   ```bash
   uv run python -m tests.benchmark_b1_high_dpi
   ```
   *Expected Output*: Waktu anchor < 0.5s/cert, akurasi nomor scan-49 >= 60.6% (19/33).

2. **Verifikasi B2 (OOD Stress Test v4.2)**:
   ```bash
   GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.ood_probe_v4_2
   ```
   *Expected Output*: Degradasi field bebas institusi <= 2.0pt pada mutasi; degradasi noise 10% <= drop_v9 + 1.5pt.

3. **Verifikasi B3 (Calibrated Confidence Review)**:
   ```bash
   GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_review_v4_2
   ```
   *Expected Output*: Certificate-level review recall >= 95.0%, weak-field recall >= 88.0%.

4. **Verifikasi B4 (Router Hardening & 5-Fold CV)**:
   ```bash
   uv run pytest tests/test_router_disambig_hardening.py -v
   uv run python -m tests.stat_validation_disambig
   ```
   *Expected Output*: Unit tests 100% passed; Min-Fold Precision 100.0% di seluruh 5 fold.

5. **Verifikasi B5 (Structural Activity Robustness)**:
   ```bash
   uv run pytest tests/test_structural_act_robustness.py -v
   GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_activity_v9
   ```
   *Expected Output*: Unit tests 100% passed; akurasi kegiatan exact >= 79.7% tanpa organizer bleed.

6. **Verifikasi B6 (Nomor Length-Preserving & Format Guard)**:
   ```bash
   uv run pytest tests/test_nomor_v6.py -v
   GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_nomor_v6
   ```
   *Expected Output*: Unit tests 100% passed; invariant panjang digit terjaga; nomor exact >= 66.7%.

7. **Verifikasi B7 (De-Corpusing Audit)**:
   ```bash
   GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.decorpusing_audit
   ```
   *Expected Output*: Laporan terbit di `docs/report/decorpusing_catalog.md` memuat 100% daftar string hardcode.

8. **Verifikasi B8 (Composite Candidate Full Benchmark)**:
   ```bash
   GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_composite_v4_candidate
   uv run pytest tests/ -v
   ```
   *Expected Output*: MACRO exact >= 78.0% all-cells; semua unit test (>= 94 tests) 100% passing.

---

## Assumptions & Contingencies

1. **Ketersediaan Tesseract & PyMuPDF**: Modul High-DPI crop mengandalkan PyMuPDF (`fitz`) dan Tesseract OCR di WSL host. Jika Tesseract tidak tersedia pada lingkungan eksekusi tertentu, modul otomatis fallback ke teks RapidOCR standar dengan log warning tanpa melempar unhandled exception.
2. **Kompabilitas 5-Fold Stratifikasi**: Jika fold tertentu memiliki sampel rule bernilai rendah (LOW-N, N < 3), fold tersebut tetap dihitung dan dilaporkan secara transparan sebagai LOW-N tanpa mendiskualifikasi presisi fold lainnya.
3. **Keterisolasian Produksi**: Jika terdapat godaan untuk mengaktifkan kode eksperimen ke `backend/app/services/combined_extractor.py`, implementer WAJIB menahannya. Seluruh variasi eksperimen B1–B8 tetap berada di `tests/` hingga user secara eksplisit memberikan instruksi promosi produksi.
