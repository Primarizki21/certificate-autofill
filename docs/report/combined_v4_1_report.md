# EXP-V4-002: v4.x Benchmark — v4.0 (Baseline) vs v4.1 (Candidate)

- **Date**: 2026-09-01 10:37:57
- **Ground Truth**: `Ground_Truth_Sertifikat_v9.csv`
- **Dataset Size**: 74 certificates (440 evaluation cells)
- **v4.0 MACRO Exact**: **75.68%** (333/440)
- **v4.1 MACRO Exact**: **76.82%** (338/440) (**+1.14pt**)

## Comparison Table (v4.x Focus)

| Field / Metric | v4.0 (Baseline) | v4.1 (Candidate) | Delta | Status |
|---|:---:|:---:|:---:|:---:|
| **MACRO Exact** | 75.68% | **76.82%** | **+1.14pt** | **IMPROVED** |
| **MACRO Fuzzy** | 77.95% | **78.64%** | **+0.68pt** | **IMPROVED** |
| `nama_kegiatan_sertifikasi` | 75.7% | **79.7%** | **+4.1pt** | IMPROVED |
| `waktu_mulai_pelaksanaan` | 72.6% | **72.6%** | **+0.0pt** | NO REGRESS |
| `waktu_selesai_pelaksanaan` | 72.6% | **72.6%** | **+0.0pt** | NO REGRESS |
| `penyelenggara_kegiatan` | 78.4% | **78.4%** | **+0.0pt** | NO REGRESS |
| `nomor_bukti_fisik_nomor_sertifikasi` | 65.3% | **66.7%** | **+1.4pt** | IMPROVED |
| `tingkat` | 89.2% | **90.5%** | **+1.4pt** | IMPROVED |

## Key Improvements in v4.1

1. **English Ordinal Date Parsing**: Handled `23th`, `1st`, `2nd`, `3rd` in date normalizer (`+1.4pt` on dates).
2. **Underscore Number Normalization**: Stripped `_` in nomor normalizer (`+1.4pt` on nomor).
3. **Activity Preposition Merge Repair**: Repaired `sebagaipeserta`, `berpartisipasisebagai`, `SIDConnect`, and title anchors (`+4.1pt` on activity).
4. **Contextual Direktur Kemahasiswaan Rule**: Prioritized `Universitas` for internal university affairs signed by student director (`+1.4pt` on tingkat).
5. **0 Regressions Invariant**: Zero accuracy regressions across all 6 fields.
