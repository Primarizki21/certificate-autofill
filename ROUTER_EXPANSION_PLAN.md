# Plan: Combined v2 Dummy Port (Staging Bundle) & Router Expansion

## Context
Eksperimen offline telah menghasilkan beberapa komponen ekstraksi berkinerja tinggi berbasis rule/regex (0 LLM) yang telah lolos pengujian (PASS):
1. **AKT-005** (`extract_activity_v5`): akurasi nama_kegiatan 62.2% exact (+55.4pt vs baseline produksi).
2. **ORG-004** (`organizer_v4` + R6 context join): akurasi penyelenggara 66.2% exact.
3. **PROD-002** (`normalize_nomor` + `normalize_organizer`): akurasi nomor 76.9% exact.
4. **ROUTER-002..004** (`tingkat_router`): akurasi tingkat 50/74 @ 100% precision (0 LLM).

Komponen-komponen ini belum disatukan secara resmi ke dalam arsitektur backend karena risiko interferensi dan blast radius.
Rencana ini mengeksekusi dua tahap:
1. **Tahap 1 — Combined v2 Staging (Dummy Port)**: Menyatukan seluruh modul PASS di atas ke dalam backend service `app/services/combined_extractor.py` yang digate oleh konfigurasi `ENABLE_COMBINED_V2=False` (default OFF). Dilengkapi suite audit QA & interferensi ketat (74 certs vs GT v9 + matcher v2) untuk membuktikan MACRO offline mencapai $\ge 73.7\%$ (0 LLM) tanpa regresi.
2. **Tahap 2 — Router Expansion Exploration (ROUTER-005)**: Mengeksplorasi penambahan rule router baru untuk 24 sertifikat unrouted dengan memanfaatkan sinyal bersih dari `organizer_v4` dan `activity_v5`, divalidasi dengan 5-fold cross-validation (gate precision 100%, 0 regresi pada 50 cert routed eksisting).

---

## Approach

### Phase 1: Combined v2 Service & Feature Gating

#### Step 1.1: Buat Module Ekstraktor Aktivitas Produksi `backend/app/services/activity_extractor.py`
Port logika AKT-005 (`tests/benchmark_akt5.py`) ke backend service murni (tanpa dependensi ke `tests/`).
- **Function**: `extract_activity(text: str) -> str | None`
- **Fungsi internal**:
  - `_D5_PRE`: perbaikan pra-camel split (split ALL-CAPS kata kunci seperti `DALAM`, `ACARA`, `DEKAN CUP`, `SYNREACH`, `GELAR RASA`, `ACIC`).
  - `_REPAIR4`: camel-split, OCR-alias `Nis C` $\to$ `NISC`, digit-merge.
  - `_D5_POST`: re-split kata kunci `competition` untuk mencegah hilangnya camel-boundary, dan penyisipan sentinel `\n` sebelum `Himpunan` digit-bound.
  - `_ANCHORS5`: 17 anchor pattern termasuk `_GROUP_B_PATTERN` (kutip), `join2` (kutip + bracket sisa), `Dalam rangka`, `Sebagai Peserta`, `Pada ajang`, dll.
- **Handling**: return `None` jika teks kosong atau tidak ada pola yang cocok.

#### Step 1.2: Buat Module Tingkat Router Produksi `backend/app/services/tingkat_router.py`
Port logika `tests/llm_router_v4.py` + rules dari ROUTER-004 (`tests/rule_mining.py`) ke backend service murni.
- **Functions**:
  - `route_tingkat(raw_text: str, organizer: str) -> str | None` (return `"Nasional"`, `"Fakultas"`, `"Departemen/Program Studi"`, `"Universitas"`, atau `None`)
  - `route_tingkat_trace(raw_text: str, organizer: str) -> tuple[str | None, str]` (return `(tingkat, rule_name)`)
- **Signals**: `_sig(raw_text: str, organizer: str) -> dict` mengekstrak `lomba`, `lomba_merged`, `hima`, `hima_org`, `dept`, `univ`, `luar`, `nasw`, `nasw_explicit`, `sem`, `fak`, `bem`.
- **Rules (Total 14 rules validated @100% precision)**:
  1. `tingkat_nasional`: `nasw_explicit`
  2. `lomba+org`: `lomba` and (`hima` or `univ` or `nasw` or `luar` or `fak` or `bem`)
  3. `lomba_merged+org`: `lomba_merged` and (`hima` or `univ` or `fak` or `bem`)
  4. `dept+sem`: `dept` and `sem` and not `lomba` and not `nasw`
  5. `hima+luar`: `hima` and `luar`
  6. `univ+luar`: `univ` and `luar` and not `fak`
  7. `dept+fak`: `dept` and `fak`
  8. `dept+hima+univ`: `dept` and `hima` and `univ`
  9. `fak+univ`: `fak` and `univ` and not `sem` and not `nasw` and not `lomba`
  10. `bem+sem`: `bem` and `sem` and not `lomba` and not `hima` and not `nasw`
  11. `bem_no_univ`: `bem` and not (`univ` or `sem` or `lomba` or `lomba_merged` or `nasw` or `luar` or `hima`)
  12. `bem+hima`: `bem` and `hima` and not (`lomba` or `lomba_merged` or `nasw` or `luar`)
  13. `sem+univ`: `sem` and `univ` and not (`fak` or `bem` or `hima` or `lomba`)
  14. `ukm_org`: `UKM` in organizer and not (`lomba` or `lomba_merged` or `luar` or `nasw` or `sem` or `fak` or `dept`)

#### Step 1.3: Buat Module Staging `backend/app/services/combined_extractor.py` & Konfigurasi
- **Settings update (`backend/app/config.py`)**:
  - Tambah field `enable_combined_v2: bool = os.getenv("ENABLE_COMBINED_V2", "false").lower() == "true"` (default `False`).
- **Module `backend/app/services/combined_extractor.py`**:
  - `apply_combined_v2(extracted: dict[str, ExtractedValue], raw_text: str) -> dict[str, ExtractedValue]`:
    1. Ekstrak `new_act = extract_activity(raw_text)`. Jika ada, set `extracted["nama_kegiatan_sertifikasi"] = ExtractedValue(new_act, 0.88, "activity_v5")`.
    2. Ekstrak `v2_org = extract_organizer_v2(raw_text)` dilanjutkan `norm_org = normalize_organizer(v2_org, raw_text)`. Jika ada, set `extracted["penyelenggara_kegiatan"] = ExtractedValue(norm_org, 0.85, "organizer_v4")`.
    3. Normalisasi nomor `norm_nomor = normalize_nomor(raw_text)`. Jika ada, set `extracted["nomor_sertifikat"] = ExtractedValue(norm_nomor, 0.95, "nomor_v2")`.
    4. Evaluasi router `tingkat, rule = route_tingkat_trace(raw_text, norm_org or "")`. Jika `tingkat`, set `extracted["tingkat"] = ExtractedValue(tingkat, 0.95, f"router:{rule}")`.
- **Integrasi `backend/app/services/extraction_pipeline.py`**:
  - Jika `settings.enable_combined_v2` aktif, panggil `apply_combined_v2(extracted, raw_text)` sebelum `map_fields_to_form`.
  - Jika tidak aktif, alur pipeline eksisting tetap 100% tidak berubah (flag OFF by default).

---

### Phase 2: QA-Audit, Interference & Conflict Check

#### Step 2.1: Buat Benchmark Evaluasi Dummy Port `tests/benchmark_combined_v2.py`
- Menguji fungsi `offline_combined_v2(text: str)` yang mereplikasi persis `apply_combined_v2` di level data offline.
- Melakukan perbandingan per-field terhadap 74 sertifikat vs `Ground_Truth_Sertifikat_v9.csv` menggunakan `tests/matchers.py` (matcher v2).
- **QA Gate Metrics**:
  - `nama_kegiatan`: exact $\ge 62.2\%$ (46/74)
  - `organizer`: exact $\ge 66.2\%$ (49/74)
  - `nomor`: exact $\ge 76.9\%$ (40/52)
  - `tingkat (router only)`: precision $100\%$ (50/74)
  - `MACRO exact`: $\ge 73.7\%$ (0 LLM)
  - Regresi per field vs benchmark terisolasi (AKT-005, ORG-004, PROD-002, ROUTER-004) harus tepat **0 kasus**.
- Cek interferensi teks: memastikan bahwa preprocessing teks di `extract_activity` tidak memutasi teks sumber yang digunakan oleh `organizer_normalize` atau `tingkat_router`.

#### Step 2.2: Buat Unit Test Suite `tests/test_combined_v2.py`
- Test 1: Verifikasi default config `enable_combined_v2 == False`.
- Test 2: Smoke test pipeline saat `enable_combined_v2 == False` (perilaku lama utuh).
- Test 3: Smoke test pipeline saat `enable_combined_v2 == True` (semua field ter-override sesuai rule).
- Test 4: Verifikasi isolasi mutasi string (tidak ada side-effect pada variabel `raw_text`).
- Test 5: Verifikasi 14 rules router unit test.

---

### Phase 3: Router Expansion Exploration (ROUTER-005)

#### Step 3.1: Mining Sinyal pada 24 Sertifikat Unrouted `tests/router_mining_v5.py`
- Ekstrak 24 sertifikat yang tidak ter-cover oleh 14 rules eksisting.
- Untuk setiap cert unrouted, tampilkan:
  - `stem`, `gt_tingkat`, `clean_organizer_v4`, `clean_activity_v5`, `raw_text_snippets`.
- Investigasi pola sinyal spesifik:
  1. **Clean Organizer Sinyal**: apakah ada pola spesifik pada `clean_organizer` (mis. nama departemen/fakultas/institusi spesifik) yang konsisten 100% dengan GT?
  2. **Activity Keyword Sinyal**: apakah `clean_activity` mengandung kata kunci kompetisi/pelatihan tingkat lokal/wilayah/internasional?
  3. **Tanda Tangan / Jabatan Sinyal**: peran signer ("Dekan", "Ketua Departemen", "Rektor", "Presiden BEM") dalam raw text.

#### Step 3.2: Perumusan Kandidat Rule Baru & Validasi 5-Fold
- Formulasi kandidat rule R15, R16, dst. dengan guard ketat.
- Evaluasi pada 5-fold cross-validation (`tests/stat_validation.py` harness):
  - **Gate R1**: Precision pada full-sample 74 certs harus **100.0%** (0 false positive).
  - **Gate R2**: Minimum fold precision pada 5 fold harus **100.0%**.
  - **Gate R3**: Coverage bertambah minimal $\ge 2$ certs (LLM calls berkurang dari 24 menjadi $\le 22$).
  - **Gate R4**: 0 regresi pada 50 certs yang sudah ter-route.
- Jika lolos gate, tambahkan rule ke `tingkat_router.py` dan re-run benchmark full.
- Jika gagal gate (precision $< 100\%$ atau fold unstable), catat sebagai kandidat ditolak di ledger.

#### Step 3.3: Dokumentasi & Ledger
- Buat laporan `docs/report/router_expansion_v5.md`.
- Tambahkan entri di `docs/experiments_ledger.md` (ROUTER-005).
- Perbarui `docs/report/runs_summary.md` dan siapkan handoff v40.

---

## Critical Files & Anchors

1. `backend/app/config.py`: Penambahan parameter `enable_combined_v2: bool = False`.
2. `backend/app/services/activity_extractor.py` (baru): Implementasi `extract_activity(text: str)` (AKT-005).
3. `backend/app/services/tingkat_router.py` (baru): Implementasi `route_tingkat(text, org)` dan `route_tingkat_trace` (14 rules).
4. `backend/app/services/combined_extractor.py` (baru): Orkestrasi combined extraction v2.
5. `backend/app/services/extraction_pipeline.py`: Hooking `apply_combined_v2` di belakang flag `settings.enable_combined_v2`.
6. `tests/benchmark_combined_v2.py` (baru): Evaluasi QA, interferensi, dan benchmark offline all-74 certs.
7. `tests/test_combined_v2.py` (baru): Pytest suite untuk verifikasi backend dummy port.
8. `tests/router_mining_v5.py` (baru): Skrip analisis dan validasi 5-fold untuk router expansion.

---

## Verification

1. **Unit Test Suite**:
   ```bash
   pytest tests/test_combined_v2.py tests/test_organizer.py tests/test_field_extractor.py -v
   ```
   *Expected*: Semua test passed ($100\%$), konfigurasi default tetap `enable_combined_v2 == False`.

2. **Full Regression Check Existing Suite**:
   ```bash
   pytest tests/ -q
   ```
   *Expected*: Semua 31+ unit tests passed, 0 error.

3. **Combined v2 Baseline Benchmark**:
   ```bash
   python -m tests.benchmark_combined_v2
   ```
   *Expected Output*:
   - `nama_kegiatan exact`: $62.2\%$ (46/74)
   - `organizer exact`: $66.2\%$ (49/74)
   - `nomor exact`: $76.9\%$ (40/52)
   - `tingkat (router 14 rules)`: $50/74$ ($67.6\%$ coverage @ $100\%$ precision)
   - `MACRO exact`: $\ge 73.7\%$
   - `0 per-field mismatch` vs benchmark terpisah.

4. **Router Expansion Exploration**:
   ```bash
   python -m tests.router_mining_v5
   ```
   *Expected Output*:
   - Menampilkan detail breakdown 24 certs unrouted.
   - Menghasilkan evaluasi 5-fold precision per kandidat rule baru.
   - Ringkasan perubahan coverage ($50 \to 50+N$).

---

## Assumptions & Contingencies

1. **Default Gating Invariant**: `enable_combined_v2` harus bernilai `False` secara default sehingga sistem produksi live yang berjalan tanpa env var baru tidak terpengaruh sedikitpun.
2. **Deterministic String Invariant**: Semua fungsi ekstraktor menerima string `text` dan mengembalikan string baru tanpa mengubah state global.
3. **Router Strictness**: Jika rule mining untuk 24 cert unrouted tidak menemukan rule baru yang memenuhi $100\%$ precision pada 5-fold CV, router dipertahankan pada 14 rules (50 certs) dan sisa 24 certs tetap dioper ke fallback LLM. Tidak ada toleransi penurunan precision demi menaikkan coverage.
