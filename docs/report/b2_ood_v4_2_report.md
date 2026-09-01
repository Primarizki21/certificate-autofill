# B2 — OOD Stress Testing untuk Combined v4.2 (N=74, 0 LLM)

> Generasi: 2026-09-01T18:49:47.861042 | GT v9 + matcher v2 | seed 42 | pipeline offline (no LLM).

## Verdict: **FAIL**

Gate (plan B2):
- Mutation: drop Free-Institution Macro v4.2 **<= 2.0pt** vs unmutated.
- Noise 10%: drop MACRO exact v4.2 **<= drop_v9 + 1.5pt**.
- Noise 25% & 50%: drop MACRO exact v4.2 **<= drop_v9** (zero excess fragility).

## Baseline offline (corpus asli)

| Pipeline | MACRO exact | MACRO fuzzy | Free-Inst exact |
|---|---|---|---|
| v9 | 56.5% | 65.6% | 60.5% |
| v4_2 | 88.0% | 90.1% | 89.9% |

## Sumbu 1 — Template & Entity Mutation

| Metrik | drop v9 | drop v4.2 | gate v4.2 |
|---|---|---|---|
| macro_exact | +9.1pt | +15.6pt | laporan |
| macro_fuzzy | +8.9pt | +10.4pt | laporan |
| free_inst_exact | +1.6pt | +7.4pt | free-inst <= 2.0pt |

**Gate mutation free-inst**: drop +7.4pt (<= 2.0pt) → **FAIL**

## Sumbu 2 — OCR Noise Confusion (drop MACRO exact vs baseline)

| Noise | drop v9 | drop v4.2 | gate |
|---|---|---|---|
| 10% | +8.6pt | +8.1pt | +1.5pt → **PASS** |
| 25% | +16.7pt | +18.2pt | 0pt → **FAIL** |
| 50% | +24.2pt | +27.9pt | 0pt → **FAIL** |

## Diagnosis mutasi — kontaminasi GT vs kerapuhan nyata

Sel field bebas-institusi yang hilang saat mutasi, diklasifikasi: GT memuat token 
institusi (airlangga/unair/ftmm/fst/universitas/fakultas/semarang/brawijaya) = 
**kontaminasi GT** (jawaban benar mengikuti institusi baru, GT lama tak di-update).

| Pipeline | sel hilang | kontaminasi GT | kerapuhan nyata |
|---|---|---|---|
| v9 | 6 | 4 | 2 |
| v4_2 | 21 | 16 | 5 |

Kerapuhan nyata v4.2 = **5 sel** (≈1.9pt free-inst, dalam gate 2.0pt). Rincian:

- `Piagam HIMA S1-AK 2025-compressed_69` [tingkat] GT='Departemen/Program Studi' → 'Nasional'
- `PRIMARIZKI_panitia_dataquest_2025` [nama_kegiatan_sertifikasi] GT='Dataquest 4.0 part of Airnology 4.0' → 'Dataquest 4.0 part of Inno Fest 4.0'
- `Airno_Faiz` [nama_kegiatan_sertifikasi] GT='Dataquest 3.0 part of Airnology 3.0' → 'Dataquest 3.0 part of Inno Fest 3.0'
- `Venedict_panitia_specta` [nama_kegiatan_sertifikasi] GT='SPECTA 2024' → 'SPECTRUM'
- `Venedict_panitia_specta` [tingkat] GT='Departemen/Program Studi' → 'Nasional'

## Diagnosis noise 25%/50% — extra loss per field (vs baseline)

| Field | noise 25% v9 | noise 25% v4.2 | noise 50% v9 | noise 50% v4.2 |
|---|---|---|---|---|
| nama_kegiatan_sertifikasi | 2 | 13 | 3 | 13 |
| waktu_mulai_pelaksanaan | 23 | 13 | 30 | 25 |
| waktu_selesai_pelaksanaan | 22 | 12 | 28 | 18 |
| penyelenggara_kegiatan | 1 | 2 | 6 | 8 |
| nomor_bukti_fisik_nomor_sertifikasi | 19 | 29 | 27 | 43 |
| tingkat | 0 | 1 | 0 | 0 |

Extra fragility v4.2 = **nomor** (Roman-repair pada digit rusak) dan **nama_kegiatan** 
(anchor struktural rusak oleh noise); v4.2 justru lebih tahan di tanggal.

## Interpretasi

- v4.2 memakai input identik dgn v9 (noise di-generate sekali) — drop relatif valid.
- Field bebas institusi (kegiatan + tanggal + tingkat) bebas kontaminasi GT pada sumbu mutation; organizer/nomor sengaja dikecualikan di gate mutation (GT memuat token institusi — drop = artefak perbandingan).
- Per-field absolute bisa dilihat di summary JSON per run.