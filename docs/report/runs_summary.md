# Benchmark Runs Summary

> Registry ringkas dari `tests/benchmark_runs/`. Baca bersama `docs/handoff_v10.md` + `docs/experiments_ledger.md` + codegraph untuk context lengkap sesi eksperimen.
> Regenerate: `uv run python scripts/generate_runs_summary.py`

**Total run terindeks:** 56 (korpus `layout_texts_*` di-skip). Dataset 74 sertifikat.

## Authoritative runs

| Run | Deskripsi | Tingkat | MACRO | Tok/cert | Calls |
|---|---|---|---|---|---|
| `run_20260728_131835` | Baseline corpus produksi (teks RapidOCR+Tesseract, 74 txt) | — | 42.2% | — | — |
| `run_llm_v4_20260804_115212` | v8 f_bias winner lama (GT final fixed_v8) | 82.4% | 55.2% | 214 | 35 |
| `run_llm_v4_20260805_163541` | v9 organizer_v2 + router fix (GT v8) | 83.8% | 58.9% | 176 | 29 |
| `run_llm_v4_20260805_163541 (reval)` | v9 winner re-baseline GT v9 + matcher v2 | 83.8% | 60.2% | — | — |
| `ocr_experiment/baseline_rapid` | OCR baseline: RapidOCR only (host) | — | 42.8% | — | — |
| `ocr_experiment/baseline_rapid_tess` | OCR baseline produksi-equivalent (RapidOCR+Tesseract) | — | 44.3% | — | — |
| `ocr_experiment/trial_a_paddle26` | OCR trial: paddleocr 2.9 + paddle 2.6 (GATE FAIL) | — | 39.8% | — | — |
| `ocr_experiment/trial_a_easyocr` | OCR trial: EasyOCR CPU max-side 960 (GATE FAIL) | — | 34.3% | — | — |
| `ocr_experiment/trial_a_easyocr_gpu` | OCR trial: EasyOCR GPU full-res (GATE FAIL, not adopted) | — | 39.3% | — | — |

## f_bias winner — field exact (run_llm_v4_20260805_163541)

| Field | exact | fuzzy |
|---|---|---|
| nama_kegiatan | 24.3% | 63.5% |
| nomor | 59.6% | 59.6% |
| organizer | 33.8% | 82.4% |
| tanggal_mulai | 81.8% | 81.8% |
| tanggal_selesai | 81.8% | 81.8% |
| tingkat | 83.8% | 86.5% |
| **MACRO** | 58.9% | 76.3% |

## GT v9 + matcher v2 re-baseline — field exact (run_llm_v4_20260805_163541)

> Re-evaluasi extracted_fields vs Ground_Truth_Sertifikat_v9.csv + matcher v2 (handoff v12). Angka GT v8/matcher v1: MACRO exact 58.9%.

| Field | exact | fuzzy |
|---|---|---|
| nama_kegiatan | 25.7% | 52.7% |
| nomor | 59.6% | 59.6% |
| organizer | 39.2% | 79.7% |
| tanggal_mulai | 81.8% | 81.8% |
| tanggal_selesai | 81.8% | 81.8% |
| tingkat | 83.8% | 89.2% |
| **MACRO** | 60.2% | 74.2% |

## OCR experiment (subset scan, field-eval exact)

| Run | Engine | MACRO scan | latency | notes |
|---|---|---|---|---|
| `ocr_experiment/baseline_rapid` | rapid | 42.8% | 3488ms | scan=49 emb=25; scan org 16.3% nomor 54.5% |
| `ocr_experiment/baseline_rapid_tess` | rapid_tess | 44.3% | 8609ms | scan=49 emb=?; scan org 14.3% nomor 57.6% |
| `ocr_experiment/corpus_doctr` | doctr | 43.3% | —ms | scan=49 emb=?; scan org 24.5% nomor 36.4% |
| `ocr_experiment/corpus_nomor_crop` | nomor_crop | 46.3% | 5231ms | scan=49 emb=?; scan org 20.4% nomor 60.6% |
| `ocr_experiment/probe_doctr` | doctr | 40.0% | —ms | scan=None emb=?; scan org 10.0% nomor 14.3% |
| `ocr_experiment/trial_a_easyocr` | easy | 34.3% | —ms | scan=49 emb=?; scan org 20.4% nomor 15.2% |
| `ocr_experiment/trial_a_easyocr_gpu` | easy | 39.3% | 9716ms | scan=49 emb=?; scan org 16.3% nomor 33.3% |
| `ocr_experiment/trial_a_paddle26` | paddle | 39.8% | 10692ms | scan=49 emb=?; scan org 18.4% nomor 39.4% |

## Full run registry

| run_dir | date | kind | variant | tingkat | macro | tok/cert | calls | router | notes |
|---|---|---|---|---|---|---|---|---|---|
| `run_20260728_131835` | 2026-07-28 | baseline_regex |  | — | 42.2% | — | — |  |  |
| `run_fulltext_llm_20260730_201832` | 2026-07-30 | llm_fulltext |  | 23.0% | 47.7% | 614 | 74 |  |  |
| `run_fulltext_llm_20260730_202823` | 2026-07-30 | llm_fulltext |  | 36.5% | 58.3% | 834 | 74 |  |  |
| `run_hybrid_llm_20260730_192808` | 2026-07-30 | other |  | — | 49.4% | 833 | 125 |  |  |
| `run_hybrid_llm_20260730_193007` | 2026-07-30 | other |  | 47.3% | 49.0% | 834 | 125 |  |  |
| `run_hybrid_pp_20260730_182441` | 2026-07-30 | hybrid_pp |  | — | 47.7% | — | — |  |  |
| `run_hybrid_pp_20260730_182639` | 2026-07-30 | hybrid_pp |  | — | 47.7% | — | — |  |  |
| `run_hybrid_pp_20260730_185133` | 2026-07-30 | hybrid_pp |  | — | 47.7% | — | — |  |  |
| `run_llm_v3_20260731_104523` | 2026-07-31 | llm_v3 | b_minimized | 33.8% | 45.3% | 440 | 74 |  |  |
| `run_llm_v3_20260731_112920` | 2026-07-31 | llm_v3 | b_minimized | 31.1% | 44.8% | 589 | 74 |  |  |
| `run_llm_v3_20260731_113156` | 2026-07-31 | llm_v3 | b_minimized | 36.5% | 45.8% | 479 | 74 |  |  |
| `run_llm_v3_20260731_113402` | 2026-07-31 | llm_v3 | b_minimized | 39.2% | 46.4% | 479 | 74 |  |  |
| `run_llm_v3_20260803_095408` | 2026-08-03 | llm_v3 | b_minimized | 70.0% | 55.8% | 66 | 10 |  |  |
| `run_llm_v4_20260803_095133` | 2026-08-03 | llm_v4 | a_context | 66.7% | 66.7% | 16 | 3 |  |  |
| `run_llm_v4_20260803_095223` | 2026-08-03 | llm_v4 | b_minimized | 37.8% | 46.1% | 479 | 74 |  |  |
| `run_llm_v4_20260803_095429` | 2026-08-03 | llm_v4 | b_minimized | 70.0% | 55.8% | 66 | 10 |  |  |
| `run_llm_v4_20260803_095915` | 2026-08-03 | llm_v4 | b_minimized | 40.5% | 47.1% | 488 | 74 |  |  |
| `run_llm_v4_20260803_101153` | 2026-08-03 | llm_v4 | b_minimized | 44.6% | 47.9% | 489 | 74 |  |  |
| `run_llm_v4_20260803_101548` | 2026-08-03 | llm_v4 | a_context | 66.7% | 72.2% | 17 | 3 |  |  |
| `run_llm_v4_20260803_101606` | 2026-08-03 | llm_v4 | b_minimized | 40.5% | 47.1% | 486 | 74 |  |  |
| `run_llm_v4_20260803_103008` | 2026-08-03 | llm_v4 | b_minimized | 44.6% | 47.9% | 489 | 74 | shadow | router 70/74 @97% |
| `run_llm_v4_20260803_103220` | 2026-08-03 | llm_v4 | b_minimized | 44.6% | 47.9% | 489 | 74 | shadow | router 32/74 @100% |
| `run_llm_v4_20260803_103345` | 2026-08-03 | llm_v4 | b_minimized | 71.6% | 53.1% | 270 | 42 | on | router 32/74 @100% |
| `run_llm_v4_20260803_103649` | 2026-08-03 | llm_v4 | b_minimized | 71.6% | 53.1% | 270 | 42 | on | router 32/74 @100% |
| `run_llm_v4_20260803_104611` | 2026-08-03 | llm_v4 | d_mid | 68.9% | 52.6% | 207 | 42 | on | router 32/74 @100% |
| `run_llm_v4_20260803_112440` | 2026-08-03 | llm_v4 | b_minimized | 66.7% | 59.4% | 33 | 5 | on | router 1/74 @100% |
| `run_llm_v4_20260803_112630` | 2026-08-03 | llm_v4 | b_minimized | 74.3% | 53.6% | 249 | 39 | on | router 35/74 @100% |
| `run_llm_v4_20260803_113310` | 2026-08-03 | llm_v4 | e_hybrid | 77.0% | 54.2% | 202 | 39 | on | router 35/74 @100% |
| `run_llm_v4_20260804_093630` | 2026-08-04 | llm_v4 | a_context | 60.0% | 58.6% | 22 | 4 | on | router 1/74 @100% |
| `run_llm_v4_20260804_093737` | 2026-08-04 | llm_v4 | e_hybrid | 77.0% | 54.2% | 202 | 39 | on | router 35/74 @100% |
| `run_llm_v4_20260804_094117` | 2026-08-04 | llm_v4 | e_hybrid | 77.0% | 54.2% | 202 | 39 | on | router 35/74 @100% |
| `run_llm_v4_20260804_094626` | 2026-08-04 | llm_v4 | e_hybrid | 81.1% | 54.9% | 182 | 35 | on | router 39/74 @100% |
| `run_llm_v4_20260804_095054` | 2026-08-04 | llm_v4 | f_bias | 66.7% | 72.2% | 12 | 2 | on | router 1/74 @100% |
| `run_llm_v4_20260804_095127` | 2026-08-04 | llm_v4 | f_bias | 79.7% | 54.7% | 216 | 35 | on | router 39/74 @100% |
| `run_llm_v4_20260804_095412` | 2026-08-04 | llm_v4 | f_bias | 82.4% | 55.2% | 214 | 35 | on | router 39/74 @100% |
| `run_llm_v4_20260804_095713` | 2026-08-04 | llm_v4 | f_bias | 78.4% | 54.4% | 197 | 35 | on | router 39/74 @100% |
| `run_llm_v4_20260804_100137` | 2026-08-04 | llm_v4 | f_bias | 77.0% | 50.8% | 235 | 39 | on | router 35/74 @100% |
| `run_llm_v4_20260804_100410` | 2026-08-04 | llm_v4 | f_bias | 78.4% | 51.3% | 224 | 37 | on | router 37/74 @100% |
| `run_llm_v4_20260804_115212` | 2026-08-04 | llm_v4 | f_bias | 82.4% | 55.2% | 214 | 35 | on | router 39/74 @100% |
| `run_llm_v4_20260805_163541` | 2026-08-05 | llm_v4 | f_bias | 83.8% | 58.9% | 176 | 29 | on | router 45/74 @100% |
| `run_llm_v5_exp5_20260805_211529` | 2026-08-05 | other |  | 66.7% | 77.8% | 14 | 2 |  |  |
| `run_llm_v5_exp5_20260805_211624` | 2026-08-05 | other |  | 83.8% | 60.7% | 195 | 29 |  |  |
| `run_llm_v5_exp5_20260805_225540` | 2026-08-05 | other |  | 60.0% | 65.5% | 19 | 3 |  |  |
| `run_llm_v5_exp5_20260805_225609` | 2026-08-05 | other |  | 81.1% | 60.4% | 185 | 29 |  |  |
| `run_ner_v1_20260728_161014` | 2026-07-28 | ner_v1 |  | — | 12.8% | — | — |  |  |
| `run_ner_v1_20260730_083808` | 2026-07-30 | ner_v1 |  | — | 12.8% | — | — |  |  |
| `run_ner_v1_20260730_084046` | 2026-07-30 | ner_v1 |  | — | 12.8% | — | — |  |  |
| `run_ner_v1_20260730_095336` | 2026-07-30 | ner_v1 |  | — | 12.8% | — | — |  |  |
| `ocr_experiment/baseline_rapid` | 2026-08-04 | ocr_trial |  | — | 42.8% | — | — |  | scan=49 emb=25; scan org 16.3% nomor 54.5% |
| `ocr_experiment/baseline_rapid_tess` | 2026-08-04 | ocr_trial |  | — | 44.3% | — | — |  | scan=49 emb=?; scan org 14.3% nomor 57.6% |
| `ocr_experiment/corpus_doctr` | 2026-08-06 | ocr_trial |  | — | 43.3% | — | — |  | scan=49 emb=?; scan org 24.5% nomor 36.4% |
| `ocr_experiment/corpus_nomor_crop` | 2026-08-06 | ocr_trial |  | — | 46.3% | — | — |  | scan=49 emb=?; scan org 20.4% nomor 60.6% |
| `ocr_experiment/probe_doctr` | 2026-08-06 | ocr_trial |  | — | 40.0% | — | — |  | scan=None emb=?; scan org 10.0% nomor 14.3% |
| `ocr_experiment/trial_a_easyocr` | 2026-08-04 | ocr_trial |  | — | 34.3% | — | — |  | scan=49 emb=?; scan org 20.4% nomor 15.2% |
| `ocr_experiment/trial_a_easyocr_gpu` | 2026-08-04 | ocr_trial |  | — | 39.3% | — | — |  | scan=49 emb=?; scan org 16.3% nomor 33.3% |
| `ocr_experiment/trial_a_paddle26` | 2026-08-04 | ocr_trial |  | — | 39.8% | — | — |  | scan=49 emb=?; scan org 18.4% nomor 39.4% |
