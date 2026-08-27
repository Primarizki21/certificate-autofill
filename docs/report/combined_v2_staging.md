# Combined v2 Staging Benchmark Report

- **Date**: 2026-08-27 10:05:59
- **Corpus**: 74 certificates (Ground_Truth_Sertifikat_v9.csv + matcher v2)
- **Mode**: 0 LLM (deterministic rules & regex)
- **Verdict**: GATE PASS

## Overall Metrics

| Field | Exact | Fuzzy | Baseline (Prod) | Gain |
|---|---|---|---|---|
| `nama_kegiatan_sertifikasi` | 46/74 (62.2%) | 60/74 (81.1%) | 5/74 (6.8%) | +55.4pt |
| `waktu_mulai_pelaksanaan` | 45/55 (81.8%) | 45/55 (81.8%) | 45/55 (81.8%) | +0.0pt |
| `waktu_selesai_pelaksanaan` | 45/55 (81.8%) | 45/55 (81.8%) | 45/55 (81.8%) | +0.0pt |
| `penyelenggara_kegiatan` | 47/74 (63.5%) | 58/74 (78.4%) | 47/74 (63.5%) | +0.0pt |
| `nomor_bukti_fisik_nomor_sertifikasi` | 40/52 (76.9%) | 40/52 (76.9%) | 40/52 (76.9%) | +0.0pt |
| `tingkat` | 62/74 (83.8%) | 62/74 (83.8%) | 62/74 (83.8%) | +0.0pt |
| **MACRO** | **74.2%** | **80.7%** | 63.5% | **+10.7pt** |

## QA & Fidelity Audit

- Mismatches vs AKT-005 reference: **0** (100% exact match)
- Isolation: Text preprocessing does not mutate source `raw_text`
- Gating: Default config `enable_combined_v2=False` keeps existing production pipeline 100% untouched
