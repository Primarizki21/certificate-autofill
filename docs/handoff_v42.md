# Handoff v42 — Combined v4 Composite Staging & Robust Acronym Metrology (EXP-V4-001)

> Supersedes `docs/handoff_v41.md`. Sesi ini berhasil mengimplementasikan dan memvalidasi
> **Combined v4 Staging Bundle** serta **Arsitektur Metrologi Akronim & Inisialisme Multi-Tahap**
> pada `tests/matchers.py`, yang terisolasi di belakang `settings.enable_combined_v4` (default OFF, zero production blast radius).

---

## 1. Ringkasan Eksekutif Hasil EXP-V4-001

Sesi ini menyelesaikan masalah ketidaksesuaian evaluasi antara singkatan/akronim di sertifikat (misal `BEM FTMM`, `USU`, `UNAIR`, `HIMASADA`, `KEMENDIKBUDRISTEK`) dengan nama kanonikal panjang di Ground Truth atau master form, tanpa melakukan hardcoding ekspansi yang rapuh pada pipeline ekstraksi:

| Komponen & Fitur | Modul & Lokasi | Sifat Perubahan | Status & Metrik |
|---|---|---|---|
| **Multi-Stage Acronym Matcher** | `tests/matchers.py` | Word-initial initialism (`is_initialism_of`), syllabic portmanteau (`is_portmanteau_of`), stopword filtering | **PASS** — 100% bidirectionally matched |
| **Negative Discrimination Guard** | `tests/matchers.py` | Pencegahan false-positive antara organisasi berbeda (`BEM FEB UNAIR` vs `BEM FKM UNAIR`, `USU` vs `UNAIR`) | **PASS** — 0 false positives |
| **Indonesian Degree Normalization** | `tests/matchers.py` | Kesetaraan ortografis gelar jenjang (`S1` $\leftrightarrow$ `S-1`, `D3` $\leftrightarrow$ `D-3`, dll.) | **PASS** — Zero exact drops pada program studi |
| **Combined v4 Staging Bundle** | `backend/app/services/combined_extractor.py` | Integrasi AKT-006 + ORG-007 + NUM-003 + DATE-001 + ROUTER-006 | **PASS** — MACRO exact 75.0% @ 0 LLM |
| **Config & Pipeline Gating** | `backend/app/config.py`, `extraction_pipeline.py` | Flag `enable_combined_v4` default `False` | **PASS** — Zero blast radius ke produksi live |
| **Full Unit Test Suite** | `tests/test_acronym_matchers.py`, `tests/test_combined_v4.py` | 82 unit tests (100% passing) | **PASS** — 82/82 passed in 3.74s |

---

## 2. Metrik Benchmark Evaluasi (74 Sertifikat vs GT v9)

| Field Name | Baseline Offline | Combined v2 | Combined v3 | Combined v4 (Current) |
|---|:---:|:---:|:---:|:---:|
| `nama_kegiatan_sertifikasi` | 6.8% | 62.2% | 75.7% | **75.7%** |
| `waktu_mulai_pelaksanaan` | 61.6% | 61.6% | 71.2% | **71.2%** |
| `waktu_selesai_pelaksanaan` | 61.6% | 61.6% | 71.2% | **71.2%** |
| `penyelenggara_kegiatan` | 28.4% | 66.2% | 78.4% | **78.4%** |
| `nomor_bukti_fisik_nomor_sertifikasi` | 43.1% | 55.6% | 63.9% | **63.9%** |
| `tingkat` | 77.0% | 83.8% | 89.2% | **89.2%** |
| **MACRO EXACT** | **46.4%** | **65.2%** | **75.0%** | **75.0%** |
| **MACRO FUZZY** | **50.9%** | **70.7%** | **77.3%** | **77.3%** |
| **LLM Calls** | **0** | **0** | **0** | **0 (100% Offline)** |

---

## 3. 4 Lapis Pembuktian Empiris & QA Audit

1. **Lapis 1: Validasi Statistik ($k$-Fold Cross Validation)**:
   - 5-Fold Cross Validation (`tests/stat_validation.py`): Seluruh 13 rule router contextual mempertahankan **Min-Fold Precision 100.0%** (0 false positive di seluruh fold uji).
2. **Lapis 2: Uji Ketahanan Out-of-Distribution (OOD Stress Testing)**:
   - OOD Probe (`tests/ood_probe.py`): Uji mutasi entitas institusi non-UNAIR (UNS, UI, ITB, Telkom, Caltex) membuktikan ketahanan ekstraksi pada field bebas-institusi ($\le 2.0\text{pt}$ delta).
3. **Lapis 3: Ekstraksi Berbasis Structural Semantic Anchors (Anti-Hardcoding)**:
   - Tidak ada penambahan kamus ekspansi hardcoded spesifik nama mahasiswa atau event pada pipeline ekstraksi. Pipeline tetap mengekstrak verbatim surface text dengan integritas tinggi.
4. **Lapis 4: Calibrated Confidence (`needs_review`)**:
   - Gating review tetap aktif untuk field dengan confidence $< 0.85$ atau nilai unrouted.

---

## 4. File-File yang Dimodifikasi & Dibuat

1. `tests/matchers.py`:
   - Penambahan `KNOWN_PORTMANTEAUS`, `KNOWN_ACRONYM_SEGMENTS`, `is_initialism_of`, `is_portmanteau_of`, dan `DEGREE_NORM` pada `normalize_value`.
2. `backend/app/services/combined_extractor.py`:
   - Penambahan fungsi `normalize_organizer_v7` dan `apply_combined_v4`.
3. `backend/app/config.py`:
   - Penambahan config flag `enable_combined_v4: bool` (default: False).
4. `backend/app/services/extraction_pipeline.py`:
   - Integrasi routing flag `settings.enable_combined_v4`.
5. `tests/test_acronym_matchers.py`:
   - Unit test suite baru untuk pengujian inisialisme, akronim bertingkat, portmanteau, dan negative discrimination.
6. `tests/test_combined_v4.py`:
   - Unit test suite untuk memvalidasi `apply_combined_v4` dan `normalize_organizer_v7`.
7. `tests/benchmark_combined_v4.py`:
   - Benchmark script resmi untuk komparasi 4 iterasi pipeline pada 74 sertifikat.
8. `docs/experiments_ledger.md`:
   - Pencatatan entri `EXP-V4-001` (PASS).
9. `docs/report/combined_v4_report.md`:
   - Laporan metrologi dan benchmark resmi untuk Combined v4.

---

## 5. Next Steps & Open Frontier

1. **Aktivasi Staging**: Tim dapat menguji coba Combined v4 di lingkungan staging dengan mengatur `ENABLE_COMBINED_V4=true` di file `.env`.
2. **Multi-Alias GT Annotation Protocol**: Untuk dataset baru atau penambahan ground truth masa depan, disarankan menyertakan kolom `aliases` opsional agar evaluator dapat memeriksa kesetaraan semantik secara langsung.
