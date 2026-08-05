# Handoff v12 — GT v9 + Matcher v2 (Metrologi); Next: Exp 4/5/6

> Supersedes `docs/handoff_v11.md`. Sesi ini **BUKAN eksperimen pipeline** —
> metrologi: perbaikan Ground Truth + redesign matcher evaluasi, supaya angka
> gate valid (no false positive, no false negative). Pipeline LLM TIDAK diubah.
>
> - **GT v9** — `Ground_Truth_Sertifikat_v9.csv` (baru, v8 tetap frozen):
>   5 fix organizer (3 typo + 2 nilai). Tingkat tak tersentuh.
> - **Matcher v2** — `tests/matchers.py` ditulis ulang: akronim = subsequence
>   huruf (bukan inisial-kata buggy), fuzzy organizer threshold 0.5→0.75,
>   tolak parsial kontigu. Nol false positive (FEB≠FKM/UGM/UPNVJT).
> - **Re-baseline** (GT v9 + matcher v2, run v9 winner): MACRO exact
>   **58.9% → 60.2%**, organizer **33.8% → 39.2%**, tingkat stabil **83.8%**.
> - **Exp 4/5/6: belum dikerjakan** (keputusan user di bawah).

---

## Hasil Metrologi

### GT v9 — 5 fix organizer (`docs/report/gt_v9_diff.txt`)

| File | v8 → v9 |
|---|---|
| `AQEEL_Seminar.pdf` | `Kementriann…` → `Kementerian…` (typo) |
| `Piagam HIMA S1-AK 2025-compressed_69.pdf` | `Akuntasi` → `Akuntansi` (typo) |
| `hakim_lomba.png` | `Akuntasi` → `Akuntansi` (typo) |
| `FIT_Faiz.pdf` | `Informatioon` → `Information` (typo) |
| `NIC_Faiz.pdf` | `Himpunan Mahasiswa UNIMUS` → `Himpunan Mahasiswa Statistika UNIMUS` (spesifik) |

Yang **TETAP VALID** (bukan error): `Faculty of Science and Technology
Information System Dept.` (×7) = hasil OCR jelek, bukan GT salah — user
confirm valid, target pipeline (LLM Exp 5). `ITASE 6.0 Dies Natalis…` =
nama acara sekaligus penyelenggara (user confirm). `SERTIF76.png` = OCR gagal.

> **Metodologi audit:** generator `scripts/generate_gt_review_v12.py` AWALNYA
> salah pilih file (heuristic prefix, 20/74 baris konteks salah) → beberapa
> keputusan user sempat didasari konteks keliru. DI-FIX ke mapping stem-exact
> (pola benchmark asli, 74/74 tepat). File `gt_review_v12.xlsx` diregenerasi.

### Matcher v2 — `tests/matchers.py`

Bug matcher v1 yang diperbaiki:
1. `is_abbreviation_of` threshold salah: `i >= len(abbr_clean)*0.5` —
   bandingkan jumlah inisial-kata vs setengah panjang STRING → akronim valid
   (`BEM FTMM Universitas Airlangga` ↔ nama penuh) tak pernah exact, dan
   `BEM FEB UGM` malah match ke "Badan Eksekutif Mahasiswa…Airlangga".
2. Fuzzy organizer `token_overlap ≥ 0.5` — `BEM FEB UNAIR` vs `BEM FKM UNAIR`
   (0.67) & `BEM FEB UGM`/`UPNVJT` dikredit padahal **beda organisasi**.

Matcher v2:
- `is_abbreviation_of`: huruf akronim = subsequence di nama penuh (stopword
  filler skip) + **rasio kata ≥ 0.3** + **rasio huruf ≤ 0.6** + **tolak
  parsial kontigu** (kata abbr = substring berurutan nama penuh → itu
  containment, bukan akronim). Membedakan FEB/FKM/UGM/UPNVJT via isi huruf.
- Fuzzy organizer: threshold 0.5 → **0.75** (0.67 = beda org).
- Test baru di `test_evaluation_framework.py`: `test_match_abbreviation_organizer`
  + `test_match_distinct_organizations_not_credited`.

### Re-baseline (GT v9 + matcher v2, run_llm_v4_20260805_163541)

| Field | v8+m1 | v9+m2 | Catatan |
|---|---|---|---|
| tingkat | 83.8% | **83.8%** | GT v9 tak sentuh tingkat |
| organizer exact | 33.8% | **39.2%** | akronim valid kini dikredit |
| organizer fuzzy | 82.4% | **79.7%** | false-positive FEB/FKM/UGM terhapus |
| nama_kegiatan exact | 24.3% | **25.7%** | parsial/OCR tak lagi exact (ANAVA, IRIS) |
| tanggal | 81.8% | 81.8% | — |
| nomor | 59.6% | 59.6% | — |
| **MACRO exact** | 58.9% | **60.2%** | naik jujur, bukan inflasi |
| **MACRO fuzzy** | 76.8% | **74.2%** | false-positive terhapus |

> Angka tersimpan `tests/benchmark_runs/run_llm_v4_20260805_163541/summary_gt_v9_reval.json`
> (re-eval offline `tests/reval_gt_v9.py`, tanpa re-run LLM — nilai ekstraksi
> sama, GT+matcher beda). `runs_summary.md` + `report_data.json` + docx di-update.

---

## What Was Done

1. `scripts/generate_gt_review_v12.py` (baru) — audit organizer GT v8, mapping
   stem-exact; output `docs/report/gt_review_v12.xlsx` (user-audited).
2. `scripts/apply_gt_review_v12.py` (baru) — terapkan 5 fix → `Ground_Truth_Sertifikat_v9.csv`
   + `docs/report/gt_v9_diff.txt`.
3. `tests/matchers.py` — matcher v2 (subsequence + rasio + tolak parsial).
4. `tests/test_evaluation_framework.py` — +2 test anti-inflasi.
5. `tests/reval_gt_v9.py` (baru) — re-eval offline, tulis `summary_gt_v9_reval.json`.
6. `scripts/generate_runs_summary.py` + `report_data.json` + `scripts/generate_report.py` —
   re-baseline masuk runs_summary + report docx/xlsx.
7. `docs/experiments_ledger.md` — +METRO-001 (matcher v1), +METRO-002 (GT v8 inconsistency).

`pytest tests/` → **31 passed** (0.16s).

---

## Keputusan yang DIBUTUHKAN USER (lanjut dari v11)

1. **Promosi produksi** (organizer_v2 + router rules + matcher?): masih
   menunggu keputusan. Matcher v2 hanya `tests/` — evaluasi, bukan produksi.
2. **Exp 4 (confidence-based field routing)** — sebagian = re-try A1 (LLM-003
   CLOSED). Data organizer low-conf hanya 3/74 → ROI rendah. SKIP disarankan.
3. **Exp 5 (multi-field LLM: tingkat + organizer satu call)** — BUKAN duplikat
   A1 (A1 = per-field terpisah). Target: 7× `Faculty…Information System Dept.`
   (pipeline-gap). Disarankan **variant C**: LLM organizer hanya utk yang
   masih non-exact setelah matcher v2 (set target menyusut → hemat token).
4. **Exp 6 (content-hash caching)** — hanya duplikat byte-identik, TIDAK
   menangkap template-sama-nama-beda. Nilai rendah; user setuju low-value.

---

## Key Files

| File | Peran |
|---|---|
| `Ground_Truth_Sertifikat_v9.csv` | GT baru (5 organizer fixes) — baseline evaluasi |
| `Ground_Truth_Sertifikat_v8.csv` | GT lama — frozen, acuan historis |
| `tests/matchers.py` | Matcher v2 — evaluasi (bukan produksi) |
| `tests/reval_gt_v9.py` | Re-eval offline GT v9 + matcher v2 |
| `scripts/generate_gt_review_v12.py` / `apply_gt_review_v12.py` | Alur audit+apply GT |
| `docs/report/gt_review_v12.xlsx` | Audit user (kolom keputusan) |
| `docs/report/gt_v9_diff.txt` | Diff v8→v9 |
| `tests/benchmark_runs/run_llm_v4_20260805_163541/summary_gt_v9_reval.json` | Angka re-baseline |
| `docs/experiments_ledger.md` | +METRO-001, +METRO-002 |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` (acuan historis) atau raw `Ground_Truth_Sertifikat.csv`
- Run benchmark LLM baru tanpa `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Campur perubahan matcher ke eksperimen pipeline (matcher = metrologi)
- Normalize ekstraktor ke GT-typo (overfit)
- Sentuh `backend/` tanpa keputusan user
- Edit kode tanpa `codegraph_explore` dulu
