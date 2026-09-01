# EXP-V4-001: Combined v4 Staging & Robust Acronym Metrology Report

- **Date**: 2026-09-01 10:03:57
- **Ground Truth**: `Ground_Truth_Sertifikat_v9.csv`
- **Dataset Size**: 74 certificates (440 evaluation cells)
- **Combined v4 MACRO Exact**: **75.0%** (330/440)
- **Combined v4 MACRO Fuzzy**: **77.3%** (340/440)

## Progression Across Pipeline Iterations

| Metric / Field | Baseline | Combined v2 | Combined v3 | Combined v4 (Current) |
|---|:---:|:---:|:---:|:---:|
| **MACRO Exact** | 46.4% | 65.2% | 75.0% | **75.0%** |
| **MACRO Fuzzy** | 50.9% | 70.7% | 77.3% | **77.3%** |
| `nama_kegiatan_sertifikasi` | 6.8% | 62.2% | 75.7% | **75.7%** |
| `waktu_mulai_pelaksanaan` | 61.6% | 61.6% | 71.2% | **71.2%** |
| `waktu_selesai_pelaksanaan` | 61.6% | 61.6% | 71.2% | **71.2%** |
| `penyelenggara_kegiatan` | 28.4% | 66.2% | 78.4% | **78.4%** |
| `nomor_bukti_fisik_nomor_sertifikasi` | 43.1% | 55.6% | 63.9% | **63.9%** |
| `tingkat` | 77.0% | 83.8% | 89.2% | **89.2%** |

## Zero-Regression & Empirical Robustness Invariant

- **LLM Calls**: 0 (100% offline and deterministic)
- **Config Gate**: `settings.enable_combined_v4` (default: False, zero production blast radius)
- **Metrology Upgrade**: Bidirectional initialism & portmanteau recognition with strict negative discrimination guards.
