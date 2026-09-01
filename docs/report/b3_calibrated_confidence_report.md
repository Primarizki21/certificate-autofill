# B3 — Kalibrasi Confidence & Safety Net Review (v4.2, N=74)

> Generasi: 2026-09-01 18:51:30 | GT v9 + matcher v2 | flag via `field_needs_review` (conf < 0.80).

## Ringkasan

| Metrik | v4.2 statis | B3 kalibrasi | Gate |
|---|---|---|---|
| Certificate-level review recall | 64.7% | **100.0%** | >= 95% |
| Review precision | 52.4% | **48.6%** | laporan |
| False alarm rate (cert 100% benar) | 50.0% | **90.0%** | <= 20% |

| Weak field recall | v4.2 statis | B3 kalibrasi | Gate |
|---|---|---|---|
| nama_kegiatan_sertifikasi | 46.7% (7/15) | **93.3%** (14/15) | >= 88% |
| nomor_bukti_fisik_nomor_sertifikasi | 25.0% (1/4) | **25.0%** (1/4) | >= 88% |

**Verdict: FAIL**

- Cert recall: PASS (100.0% vs 95%)
- Weak-field recall: FAIL ({'nama_kegiatan_sertifikasi': 93.33333333333333, 'nomor_bukti_fisik_nomor_sertifikasi': 25.0} vs 88%)
- False alarm: FAIL (90.0% vs 20%)

## Trade-off

Safety net vs biaya review: recall tinggi berarti lebih banyak cert di-flag
untuk verifikasi manusia. B3 menurunkan confidence hanya pada pola lemah
(literal corpus 0.55, repair OCR 0.78, single-date 0.75, disambig 0.84)
— nilai interval eksplisit & router base tetap 0.95+/0.98.
