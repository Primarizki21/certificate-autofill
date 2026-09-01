# B8 — Composite Candidate: v9 vs v4.2 vs Composite (N=74, 0 LLM)

> Generasi: 2026-09-01 19:21:24 | GT v9 + matcher v2 | korpus teks offline.

## 3-Arah Benchmark

| Metrik | v9 offline | v4.2 staging | **Composite B8** |
|---|---|---|---|
| MACRO exact (all-cells) | 46.17% | 76.13% | **76.13%** |
| MACRO fuzzy (all-cells) | 50.68% | 77.93% | **77.93%** |
| MACRO exact (framework) | 47.74% | 87.42% | **87.42%** |

| Field exact | v9 | v4.2 | Composite |
|---|---|---|---|
| nama_kegiatan_sertifikasi | 5/74 | 59/74 | 59/74 |
| waktu_mulai_pelaksanaan | 45/74 | 53/74 | 53/74 |
| waktu_selesai_pelaksanaan | 45/74 | 53/74 | 53/74 |
| penyelenggara_kegiatan | 21/74 | 58/74 | 58/74 |
| nomor_bukti_fisik_nomor_sertifikasi | 32/74 | 48/74 | 48/74 |
| tingkat | 57/74 | 67/74 | 67/74 |

**Gate all-cells >= 78.0%**: FAIL (76.13%)
**Gate framework >= 89.0%**: FAIL (87.42%)
**Zero regression per field**: PASS

> Komponen B4/B5/B6 adalah pengerasan OOD (0 perubahan nilai di korpus ini —
> kasus audit QA adalah OOD/sintetik). Composite == v4.2 secara numerik;
> gate akurasi plan (>=78.0%) TIDAK tercapai karena target mengasumsikan
> bug korpus-visible yang ternyata tidak ada.

## Tabel 1 — Stratified 5-Fold CV router v7 (B4)

Lihat `docs/report/b4_router_hardening_report.md` — min-fold precision 100%, coverage 64/74.

## Tabel 2 — Kurva OOD Composite (mutation + noise)

| Kondisi | MACRO exact | drop vs baseline |
|---|---|---|
| baseline | 88.0% | — |
| mutation | 72.4% | +15.6pt |
| mutation free-inst | 82.6% | +7.4pt |
| noise 10% | 80.5% | +7.6pt |
| noise 25% | 75.8% | +12.2pt |
| noise 50% | 60.2% | +27.9pt |

## Tabel 3 — Audit Structural Semantic Anchors (B7)

Lihat `docs/report/decorpusing_catalog.md` — Pure Semantic MACRO 79.4% (assist +8.6pt);
nomor 0 assist (literal 270/GIRI dapat dilepas gratis), organizer +31.1pt (alias).

## Tabel 4 — Kalibrasi Review & Safety Net (B3)

Lihat `docs/report/b3_calibrated_confidence_report.md` — cert recall 100%, weak-field
nomor 25% & false alarm 90% (GATE FAIL) → B3 TIDAK dimasukkan ke composite;
flag review tetap dari confidence B6 (0.78 utk nomor repaired).

## HYB-003 (korpus OCR scan-49, report-only)

Organizer rapid-only text merge (0 OCR baru, artefak `hybrid_rapid_org`, HYB-003 ledger):
organizer exact 26.5% → 34.7% (+8.2pt), MACRO scan 47.26% → 49.2%. Berlaku hanya
pada korpus OCR — di korpus teks offline composite tidak menyentuh OCR.
