# OCR-007 — Probe LFM2.5-VL-3B (VLM OCR, llama.cpp)

> Generasi: 2026-08-13 | GT v9 + matcher v2 | 10 stem scan tetap (sama dgn probe
> DocTR OCR-006) | Varian: **GGUF Q4_0 + mmproj Q8_0** (terendah RAM/quant) via
> `llama-server` (llama.cpp b10405) | 0 LLM pipeline call (OCR terpisah)

## Setup

| Item | Nilai |
|---|---|
| Model | `LFM2.5-VL-3B-Q4_0.gguf` (1520 MB) + `mmproj-LFM2.5-VL-3B-Q8_0.gguf` (556 MB) |
| Runtime | `llama-server -c 4096 -t 8 --port 8080` (mtmd, load sekali) |
| Server RSS | ~4.9 GB (berjalan aman di host 5.3 GB tersedia, Docker mati) |
| Prompt | transkripsi polos: "Transkripsikan semua teks pada gambar ini secara lengkap, baris per baris" |
| Latency | **~77 s/cert** (vs baseline rapid_tess 8.6 s/cert = ~9x) |
| Output | `tests/benchmark_runs/ocr_experiment/lfm25_ocr_20260813_151134/` |

## Hasil (like-for-like, 10 stem sama, GT v9 + matcher v2)

| Field | baseline rapid_tess | **LFM2.5-VL-3B** | delta | gate |
|---|---|---|---|---|
| nomor_bukti_fisik exact | 28.6% | **28.6%** | +0.0% | no-regress ✅ |
| waktu_mulai_pelaksanaan exact | 88.9% | **88.9%** | +0.0% | no-regress ✅ |
| waktu_selesai_pelaksanaan exact | 88.9% | **88.9%** | +0.0% | no-regress ✅ |
| penyelenggara_kegiatan exact | 0.0% | **20.0%** | +20.0pt | naik ✅ |
| penyelenggara_kegiatan fuzzy | 50.0% | **60.0%** | +10.0pt | naik ✅ |
| MACRO exact | 40.0% | **44.4%** | +4.4pt | naik ✅ |

## Verdict

**GATE PASS** — engine OCR pertama yang TIDAK regress nomor (paddle 39.4%,
easyocr 15.2%, DocTR 36.4% di full scan) + organizer exact naik 0% → 20%.
10/10 cert OK, 0 error, 0 watchdog kill.

## Temuan

1. **Nomor bertahan**: 2/7 exact, persis baseline. Transkripsi bersih baca
   format nomor lengkap (`106/STF.E/HOLOGY7.0/XI/2024`) — masalah nomor bukan
   lagi digit hancur (beda DocTR `6/ST:E/-LG7.X1/2o`), tapi konsistensi
   ekstraksi/GT.
2. **Organizer +20pt exact** (2 exact: FIT_Faiz, dll) — VLM baca struktur
   dokumen (nama dekan, jabatan, institusi) lebih utuh dr engine klasik.
3. **Kualitas transkripsi tinggi**: FIT_Faiz (NIP/NIM/dates benar),
   2439919 (Hology 7.0 bersih, tanda tangan 3 pejabat terbaca).
4. **nama_kegiatan 0% (= baseline 0%)** — bukan regress; harness OCR-only
   tanpa embedded; kasus all-caps/acronym (FITCOMPETITION) sudah jadi catatan
   AKT-004 (di luar scope OCR).
5. **Cost**: 77 s/cert ≈ 9x baseline 8.6 s + RSS 4.9 GB + model 2.1 GB
   download. VLM autoregresif mahal utk OCR penuh.

## Rekomendasi

- **Full run 74 cert** (≈ 95 menit) kalau user mau angka otoritatif; atau
- **Hybrid per-field** (pola HYB-001): LFM utk organizer/dates, baseline
  rapid_tess utk nomor — LFM organizer +20pt bisa menaikkan hasil hybrid.
- Produksi TIDAK disentuh (eksperimen murni, `tests/` saja).
