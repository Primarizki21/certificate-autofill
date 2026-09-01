# EXP-V4-003: v4.x Benchmark — v4.0 (Baseline) vs v4.1 vs v4.2 (Candidate)

- **Date**: 2026-09-01 11:05:17
- **Ground Truth**: `Ground_Truth_Sertifikat_v9.csv`
- **Dataset Size**: 74 certificates (440 evaluation cells)
- **v4.0 MACRO Exact**: **75.68%**
- **v4.1 MACRO Exact**: **76.82%**
- **v4.2 MACRO Exact**: **76.82%** (**+1.14pt vs v4.0**)

## Progression Across v4.x Iterations

| Field / Metric | v4.0 (Baseline) | v4.1 (Minor) | v4.2 (Candidate) | Delta vs v4.0 |
|---|:---:|:---:|:---:|:---:|
| **MACRO Exact** | 75.68% | 76.82% | **76.82%** | **+1.14pt** |
| **MACRO Fuzzy** | 77.95% | 78.64% | **78.64%** | **+0.68pt** |
| `nama_kegiatan_sertifikasi` | 75.7% | 79.7% | **79.7%** | **+4.1pt** |
| `waktu_mulai_pelaksanaan` | 72.6% | 72.6% | **72.6%** | **+0.0pt** |
| `waktu_selesai_pelaksanaan` | 72.6% | 72.6% | **72.6%** | **+0.0pt** |
| `penyelenggara_kegiatan` | 78.4% | 78.4% | **78.4%** | **+0.0pt** |
| `nomor_bukti_fisik_nomor_sertifikasi` | 65.3% | 66.7% | **66.7%** | **+1.4pt** |
| `tingkat` | 89.2% | 90.5% | **90.5%** | **+1.4pt** |

## 3 Pillars Implemented in v4.2

1. **Pillar 1: Structural Semantic Anchors**: Indonesian & English formal certificate grammar patterns (`extract_activity_v8`).
2. **Pillar 2: General OCR Noise Cleaning & Roman Repairs**: Universal Roman numeral month normalization (`normalize_nomor_v5`).
3. **Pillar 3: Calibrated Confidence & Zero-Silent-Error Review Gate**: Review trigger when any field confidence is below 0.85.
4. **High-DPI Region Crop Module**: `app/services/high_dpi_crop.py` provides 6.0x zoom region re-rendering for low-resolution scanned certificates.
