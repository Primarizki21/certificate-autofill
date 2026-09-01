# Stat Validation — Pipeline v9 (N=74)

> Generasi: 2026-09-01 10:04:07 | GT v9 + matcher v2 | router = llm_router_v4 (identik produksi) | bootstrap 1000x, 5-fold seed 42

## Bootstrap CI (per-field exact/fuzzy + MACRO, 95%)

| Metrik | mean | CI95 low | CI95 high |
|---|---|---|---|
| MACRO exact | 60.9% | 56.8% | 65.4% |
| MACRO fuzzy | 74.5% | 70.6% | 78.7% |
| Router precision | 100.0% | 100.0% | 100.0% |
| Router coverage | 61.0% | 50.0% | 71.6% |

| Field | exact mean | exact CI95 | fuzzy mean | fuzzy CI95 |
|---|---|---|---|---|
| nama_kegiatan_sertifikasi | 26.9% | 19.1%-34.9% | 52.6% | 44.0%-60.9% |
| waktu_mulai_pelaksanaan | 81.8% | 74.3%-90.0% | 81.8% | 74.3%-90.0% |
| waktu_selesai_pelaksanaan | 81.9% | 73.5%-90.0% | 81.9% | 73.5%-90.0% |
| penyelenggara_kegiatan | 41.9% | 33.3%-51.1% | 81.1% | 75.0%-88.0% |
| nomor_bukti_fisik_nomor_sertifikasi | 59.5% | 50.0%-70.3% | 59.5% | 50.0%-70.3% |
| tingkat | 83.7% | 77.5%-90.0% | 89.2% | 84.1%-95.6% |

## Router — 5-fold per-rule precision (rule tetap, uji di fold)

Klaim full-sample `100% precision` diuji per fold: rule `stable` = min fold precision ≥95%. Rule `low_n` = fire <5 di full sample (interval lebar, jangan diandalkan untuk klaim robustness).

| Rule | fires | precision | min fold prec | folds (fires, prec) | verdict |
|---|---|---|---|---|---|
| bem+hima | 2 | 100.0% | 100.0% | f1:1(100%), f4:1(100%) | LOW-N |
| bem+sem | 3 | 100.0% | 100.0% | f2:2(100%), f4:1(100%) | LOW-N |
| bem_no_univ | 2 | 100.0% | 100.0% | f2:1(100%), f3:1(100%) | LOW-N |
| dept+fak | 2 | 100.0% | 100.0% | f2:1(100%), f3:1(100%) | LOW-N |
| dept+hima+univ | 2 | 100.0% | 100.0% | f1:1(100%), f3:1(100%) | LOW-N |
| dept+sem | 5 | 100.0% | 100.0% | f0:1(100%), f1:1(100%), f2:2(100%), f4:1(100%) | stable |
| fak+univ | 3 | 100.0% | 100.0% | f0:3(100%) | LOW-N |
| hima+luar | 1 | 100.0% | 100.0% | f2:1(100%) | LOW-N |
| lomba+org | 15 | 100.0% | 100.0% | f0:2(100%), f1:4(100%), f2:3(100%), f3:2(100%), f4:4(100%) | stable |
| lomba_merged+org | 3 | 100.0% | 100.0% | f1:1(100%), f2:1(100%), f4:1(100%) | LOW-N |
| sem+univ | 1 | 100.0% | 100.0% | f4:1(100%) | LOW-N |
| tingkat_nasional | 5 | 100.0% | 100.0% | f0:3(100%), f1:1(100%), f2:1(100%) | stable |
| univ+luar | 1 | 100.0% | 100.0% | f3:1(100%) | LOW-N |

## Fold summary

| Fold | routed | correct | precision |
|---|---|---|---|
| fold0 | 9 | 9 | 100.0% |
| fold1 | 9 | 9 | 100.0% |
| fold2 | 12 | 12 | 100.0% |
| fold3 | 6 | 6 | 100.0% |
| fold4 | 9 | 9 | 100.0% |

## Interpretasi

- Rule dengan `UNSTABLE`/`LOW-N`: klaim precision-nya hanya kebetulan di 74 sample — jangan dipromosikan tanpa validasi data baru (gate Fase 2 roadmap).
- CI MACRO 60.2% baseline: batas bawah interval = target minimum no-regress untuk semua eksperimen berikutnya.