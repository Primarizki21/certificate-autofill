# OOD Probe — Pipeline v9 di Luar Domain (N=74)

> Generasi: 2026-08-10 08:25:33 | GT v9 + matcher v2 | pipeline offline (no LLM) | seed 42

## Baseline offline (tanpa mutasi/noise)

| MACRO exact | MACRO fuzzy | MACRO exact (field bebas institusi) |
|---|---|---|
| 55.7% | 65.1% | 60.1% |

> Baseline produksi (PROD-001): MACRO 47.3% diukur pada subset scan (49 cert, teks RapidOCR+Tesseract). Offline di sini = seluruh 74 cert (49 scan + 25 embedded) → baseline 55.7% (embedded lebih bersih). Perbandingan drop = within-corpus, sehingga valid untuk mengukur degradasi.

## Sumbu 1 — Template mutation

Mutasi: institusi (Universitas Airlangga→Universitas Negeri Semarang, UNAIR→UNS, AIRLANGGA→SEMARANG), fakultas FTMM→FST, event hardcode (Airnology→InnoFest, Kakiwima→CampusTalks, SPECTA→SPECTRUM, Brief→BRIEFSUM).

| Metrik | baseline | mutated | drop |
|---|---|---|---|
| macro_exact | 55.7% | 46.9% | +8.9% |
| macro_fuzzy | 65.1% | 56.5% | +8.6% |
| MACRO exact (bebas institusi) | 60.1% | 58.9% | -1.2% |

> **Kontaminasi**: drop di `nomor`/`organizer` bukan murni kerapuhan — GT kedua field itu mengikat token institusi (mis. nomor `4813/B/UN3.FTMM/...`, organizer `BEM FTMM Universitas Airlangga`). Saat institusi berubah, jawaban yang benar pun berubah; perbandingan vs GT lama menambah drop artifisial. Ukuran kerapuhan yang jujur = field bebas institusi di atas.

Per-field exact:

| Field | baseline | mutated |
|---|---|---|
| nama_kegiatan_sertifikasi | 6.8% | 6.8% |
| waktu_mulai_pelaksanaan | 81.8% | 81.8% |
| waktu_selesai_pelaksanaan | 81.8% | 81.8% |
| penyelenggara_kegiatan | 37.8% | 21.6% |
| nomor_bukti_fisik_nomor_sertifikasi | 59.6% | 23.1% |
| tingkat | 81.1% | 77.0% |

## Sumbu 2 — OCR noise injection (5↔S, 8↔B, 0↔O, 1↔I + merge kata)

| Noise level | MACRO exact | MACRO fuzzy |
|---|---|---|
| noise_0% | 55.7% | 65.1% |
| noise_10% | 47.1% | 56.5% |
| noise_25% | 39.3% | 48.4% |
| noise_50% | 31.5% | 42.4% |

## Interpretasi

- **Sumbu 1 — kerapuhan lebih rendah dari dugaan**: MACRO exact field bebas-institusi hanya −1.2pt saat template berubah (kegiatan 6.8%→6.8% sudah floor, tanggal 81.8% stabil, tingkat 81.1%→77.0% −4.1pt). Drop −8.9pt di MACRO penuh didominasi organizer (37.8→21.6) & nomor (59.6→23.1) yang **terkontaminasi GT** (token institusi di dalam jawaban — jawaban yang benar memang berubah).
- Sinyal kerapuhan riil sumbu 1 = **tingkat −4.1pt**: router sebagian bergantung pola korpus UNAIR (`univ+luar`, `hima+luar`), bukan murni struktural — kandidat perbaikan Fase 2/3.
- **Sumbu 2 — OCR noise**: MACRO tahan sampai 10% (−8.6pt), drop tajam di 25% (−16.4pt) dan 50% (−24.2pt). Batas praktis noise pipeline v9 ≈ 10-25% karakter rusak.