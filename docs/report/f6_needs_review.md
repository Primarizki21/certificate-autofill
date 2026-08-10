# F6 — Extend needs_review ke Field Lemah (prototipe tests-only)

> Generasi: 2026-08-10 08:35:19 | GT v9 + matcher v2 | pipeline offline (no LLM) | threshold confidence < 0.80

## Masalah

`field_needs_review` produksi: `confidence < 0.80`. Tapi confidence regex di-set tinggi begitu value ada (nama_kegiatan 0.86, nomor 0.95) → field lemah (25.7% / 59.6% exact) hampir tak pernah ter-flag walau sering salah.

## Prototipe — confidence berbasis pola (bukan keberadaan value)

| Field | Sumber value | Confidence baru | Bukti corpus |
|---|---|---|---|
| nama_kegiatan | PKKMB fallback | 0.95 | 4/4 exact/fuzzy |
| nama_kegiatan | pola struktural | 0.60 | kegiatan 2/5 exact |
| nama_kegiatan | keyword hardcode | 0.50 | SPECTA 0/2 exact |
| nama_kegiatan | None | 0.00 | — |
| nomor | value ada | 0.95 | F1 fix 76.9% |
| nomor | None | 0.00 | — |

## Hasil

| Field | wrong | recall (wrong→flagged) | exact | FP (exact→flagged) |
|---|---|---|---|---|
| nama_kegiatan_sertifikasi | 61 | 59/61 (97% jika >0) | 5 | 4/5 (80% jika >0) |
| nomor_bukti_fisik_nomor_sertifikasi | 21 | 13/21 (62% jika >0) | 31 | 0/31 (0% jika >0) |

## Level cert (keputusan user: review dokumen ini?)

- Cert exact semua field: 1 | ter-flag (FP): 1
- Cert dengan ≥1 field wrong: 69 | ter-flag (recall): 68/69
- Total cert ter-flag butuh review: 73/74

## Interpretasi

- **nama_kegiatan**: recall tinggi = FP tinggi (25.7% akurat → hampir semua yang benar pun ke-flag). Ini trade-off wajib safety net: di skala 360k, silent-wrong lebih mahal daripada review ulang. Keyword hardcode diberi confidence terendah (terbukti template-specific, tidak general).
- **nomor**: recall/FP didominasi F1 fix; sisa salah (23%) tidak terdeteksi tanpa GT — butuh sinyal tambahan (mis. format tidak umum) atau LLM.
- Rekomendasi: aktifkan prototipe ini sebagai **default-on** di produksi (produksi ditunda dulu), karena biayanya = human review, bukan error.