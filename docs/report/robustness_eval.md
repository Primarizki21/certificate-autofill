# Robustness Eval — Pipeline v9 (k-fold + bootstrap CI + OOD)

> Generasi: 2026-08-10 10:20:26 | GT v9 + matcher v2 |
> pipeline offline (no LLM) | gabungan `stat_validation` + `ood_probe`.

## 1. Stat Validation (5-fold router + bootstrap CI)

- Corpus: 74 cert, bootstrap 1000x seed 42, 5-fold.
- MACRO exact: mean **60.1%** (CI95 56.0%–64.4%)
- MACRO fuzzy: mean **74.2%** (CI95 70.3%–78.3%)
- Router precision: mean **100.0%** (CI95 100.0%–100.0%)
- Router coverage: mean **61.0%** (CI95 50.0%–71.6%)

| Field exact | mean | CI95 |
|---|---|---|
| nama_kegiatan_sertifikasi | 25.5% | 17.8%-33.3% |
| waktu_mulai_pelaksanaan | 81.8% | 74.3%-90.0% |
| waktu_selesai_pelaksanaan | 81.9% | 73.5%-90.0% |
| penyelenggara_kegiatan | 39.1% | 30.6%-47.9% |
| nomor_bukti_fisik_nomor_sertifikasi | 59.5% | 50.0%-70.3% |
| tingkat | 83.7% | 77.5%-90.0% |
| Rule UNSTABLE (min fold prec <95%): — |
| Rule LOW-N (fire <5, jangan klaim robust): bem+hima, bem+sem, bem_no_univ, dept+fak, dept+hima+univ, fak+univ, hima+luar, lomba_merged+org, sem+univ, univ+luar |

## 2. OOD Probe (template mutation + OCR noise)

| Skenario | MACRO exact | Delta vs baseline |
|---|---|---|
| Baseline offline | 55.7% | — |
| Template mutation | 46.9% | -8.9% |
| Noise 10% | 47.1% | -8.6% |
| Noise 25% | 39.3% | -16.4% |
| Noise 50% | 31.5% | -24.2% |

## 3. Gate untuk eksperimen berikutnya (sintesis)

- **No-regress**: MACRO exact eksperimen baru wajib ≥ CI95 low baseline
  **56.0%** (bukan hanya ≥ mean 60.1%).
- **Rule router baru**: wajib k-fold; rule LOW-N (`bem+hima, bem+sem, bem_no_univ, dept+fak, dept+hima+univ, fak+univ, hima+luar, lomba_merged+org, sem+univ, univ+luar`) jangan
  diklaim robust; jangan dipromosikan tanpa data baru.
- **Noise**: batas praktis 10–25% karakter rusak — eksperimen yang menyentuh
  OCR/normalisasi teks wajib no-regress di level noise 10%.
- **Kerapuhan riil**: tingkat (−4.1pt saat mutation) = kandidat perbaikan
  router/KB; drop organizer/nomor saat mutation = artefak GT, bukan regresi.

## Sumber

- Detail k-fold + bootstrap: `docs/report/stat_validation.md` (run dir
  `tests/benchmark_runs/stat_validation_*`)
- Detail OOD: `docs/report/ood_probe.md` (run dir `tests/benchmark_runs/ood_probe_*`)
