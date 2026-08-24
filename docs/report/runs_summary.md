# Benchmark Runs Summary

> Registry ringkas dari `tests/benchmark_runs/`. Baca bersama `docs/handoff_v10.md` + `docs/experiments_ledger.md` + codegraph untuk context lengkap sesi eksperimen.
> Regenerate: `uv run python scripts/generate_runs_summary.py`

**Total run terindeks:** 101 (korpus `layout_texts_*` di-skip). Dataset 74 sertifikat.

## Authoritative runs

| Run | Deskripsi | Tingkat | MACRO | Tok/cert | Calls |
|---|---|---|---|---|---|
| `run_20260728_131835` | Baseline corpus produksi (teks RapidOCR+Tesseract, 74 txt) | — | 42.2% | — | — |
| `run_llm_v4_20260804_115212` | v8 f_bias winner lama (GT final fixed_v8) | 82.4% | 55.2% | 214 | 35 |
| `run_llm_v4_20260805_163541` | v9 organizer_v2 + router fix (GT v8) | 83.8% | 58.9% | 176 | 29 |
| `run_llm_v4_20260805_163541 (reval)` | v9 winner re-baseline GT v9 + matcher v2 | 83.8% | 60.2% | — | — |
| `ocr_experiment/baseline_rapid` | OCR baseline: RapidOCR only (host) | — | 47.3% | — | — |
| `ocr_experiment/baseline_rapid_tess` | OCR baseline produksi-equivalent (RapidOCR+Tesseract) | — | 47.3% | — | — |
| `ocr_experiment/trial_a_paddle26` | OCR trial: paddleocr 2.9 + paddle 2.6 (GATE FAIL) | — | 43.3% | — | — |
| `ocr_experiment/trial_a_easyocr` | OCR trial: EasyOCR CPU max-side 960 (GATE FAIL) | — | 38.3% | — | — |
| `ocr_experiment/trial_a_easyocr_gpu` | OCR trial: EasyOCR GPU full-res (GATE FAIL, not adopted) | — | 42.3% | — | — |
| `ocr_experiment/lfm25_full_20260824_111939` | OCR-008/HYB-002: LFM2.5-VL full-scan 49 + hybrid per-field (organizer +14.3pt, MACRO 50.75%) | — | — | — | — |
| `ocr_experiment/composite_lfm_full_20260824_111939` | OCR-008 komposit all-74: LFM(49 scan) + baseline(25 embedded) — MACRO 50.65% vs baseline 47.3% | — | — | — | — |
| `ocr_experiment/corpus_nomor_crop_lines7` | NC-003 trial: region tess_lines_psm7 (nomor 57.6% FAIL, stage timing anchor 3.5s dominan) | — | 47.3% | — | — |
| `ocr_experiment/corpus_nomor_crop_rt6` | NC-003 trial: region rapid_tess_psm6 + anchor cache hits 32/49 (nomor 54.5% FAIL) | — | 46.8% | — | — |
| `ocr_experiment/hybrid_rapid_org` | HYB-003: hybrid organizer rapid-only tanpa LFM (MACRO 49.2%, organizer +8.2pt, 0 biaya) | — | — | — | — |
| `ocr_experiment/composite_rapid_hybrid` | HYB-004 komposit HYB-003 all-74: MACRO 50.32% — gap ke LFM 0.33pt @ 0 biaya | — | — | — | — |
| `ocr_experiment/probe_ppu` | OCR-009 probe ppu-paddle-ocr (v6-tiny/small FAIL digit, v5-en-server CLOSED RSS ~3GB) + HYB-005 hybrid FAIL | — | — | — | — |

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
| `ocr_experiment/baseline_rapid` | rapid | 47.3% | 3488ms | scan=49 emb=25; scan org 34.7% nomor 54.5% |
| `ocr_experiment/baseline_rapid_tess` | rapid_tess | 47.3% | 8609ms | scan=49 emb=?; scan org 26.5% nomor 57.6% |
| `ocr_experiment/composite_lfm_full_20260824_111939` |  | — | —ms |  |
| `ocr_experiment/composite_rapid_hybrid` |  | — | —ms |  |
| `ocr_experiment/corpus_doctr` | doctr | 45.8% | —ms | scan=49 emb=?; scan org 34.7% nomor 36.4% |
| `ocr_experiment/corpus_doctr [hybrid_10]` | rapid_tess+doctr | 42.2% | —ms | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 10.0% nomor 28.6% |
| `ocr_experiment/corpus_doctr [hybrid_49]` | rapid_tess+doctr | 49.2% | —ms | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 34.7% nomor 57.6% |
| `ocr_experiment/corpus_doctr [hybrid_embedded]` | rapid_tess+doctr | 52.3% | —ms | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 28.0% nomor 68.4% |
| `ocr_experiment/corpus_nomor_cheap_rapid` | nomor_crop | 46.8% | 6320ms | scan=49 emb=0; scan org 26.5% nomor 54.5% |
| `ocr_experiment/corpus_nomor_cheap_rt13` | nomor_crop | 46.8% | 6187ms | scan=49 emb=0; scan org 26.5% nomor 54.5% |
| `ocr_experiment/corpus_nomor_cheap_tess13` | nomor_crop | 47.3% | 4307ms | scan=49 emb=0; scan org 26.5% nomor 57.6% |
| `ocr_experiment/corpus_nomor_cheap_tess6` | nomor_crop | 47.3% | 4267ms | scan=49 emb=0; scan org 26.5% nomor 57.6% |
| `ocr_experiment/corpus_nomor_crop` | nomor_crop | 47.8% | 5231ms | scan=49 emb=?; scan org 26.5% nomor 60.6% |
| `ocr_experiment/corpus_nomor_crop_lines7` | nomor_crop | 47.3% | 4431ms | scan=49 emb=0; scan org 26.5% nomor 57.6% |
| `ocr_experiment/corpus_nomor_crop_rt6` | nomor_crop | 46.8% | 2859ms | scan=49 emb=0; scan org 26.5% nomor 54.5% |
| `ocr_experiment/hybrid_rapid_org` |  | — | —ms |  |
| `ocr_experiment/hybrid_rapid_org [hybrid_49]` | rapid_tess+doctr | 49.2% | —ms | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 34.7% nomor 57.6% |
| `ocr_experiment/lfm25_full_20260824_111939` | lfm25_vl_3b | — | —ms | scan=None emb=? |
| `ocr_experiment/lfm25_full_20260824_111939 [hybrid_10]` | rapid_tess+doctr | 44.4% | —ms | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 20.0% nomor 28.6% |
| `ocr_experiment/lfm25_full_20260824_111939 [hybrid_49]` | rapid_tess+doctr | 50.7% | —ms | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 40.8% nomor 57.6% |
| `ocr_experiment/lfm25_ocr_20260813_151134` | lfm25_vl_3b | 44.4% | —ms | scan=None emb=?; scan org 20.0% nomor 28.6% |
| `ocr_experiment/probe_doctr` | doctr | 40.0% | —ms | scan=10 emb=0; scan org 10.0% nomor 14.3% |
| `ocr_experiment/probe_got` |  | — | —ms |  |
| `ocr_experiment/probe_ppu` |  | — | —ms |  |
| `ocr_experiment/trial_a_easyocr` | easy | 38.3% | —ms | scan=49 emb=?; scan org 36.7% nomor 15.2% |
| `ocr_experiment/trial_a_easyocr_gpu` | easy | 42.3% | 9716ms | scan=49 emb=?; scan org 28.6% nomor 33.3% |
| `ocr_experiment/trial_a_paddle26` | paddle | 43.3% | 10692ms | scan=49 emb=?; scan org 32.6% nomor 39.4% |

## Full run registry

| run_dir | date | kind | variant | tingkat | macro | tok/cert | calls | router | notes |
|---|---|---|---|---|---|---|---|---|---|
| `akt2_20260813_142451` | 2026-08-13 | other |  | — | 68.8% | — | — |  |  |
| `akt3_20260814_135024` | 2026-08-14 | other |  | — | 71.6% | — | — |  |  |
| `akt4_20260814_141802` | 2026-08-14 | other |  | — | 72.1% | — | — |  |  |
| `akt5_20260814_142534` | 2026-08-14 | other |  | — | 73.7% | — | — |  |  |
| `hyb_kb_20260824_094821` | 2026-08-24 | hyb_kb |  | — | — | — | — |  |  |
| `hyb_kb_20260824_095024` | 2026-08-24 | hyb_kb |  | — | — | — | — |  |  |
| `hyb_kb_scale_20260824_101641` | 2026-08-24 | hyb_kb_scale |  | — | — | — | — |  |  |
| `hyb_kb_scale_20260824_102240` | 2026-08-24 | hyb_kb_scale |  | — | — | — | — |  |  |
| `hyb_kb_scale_20260824_102300` | 2026-08-24 | hyb_kb_scale |  | — | — | — | — |  |  |
| `kb_alias_20260811_110930` | 2026-08-11 | other |  | — | 83.8% | — | — |  |  |
| `kb_event_20260811_110636` | 2026-08-11 | other |  | — | 83.8% | — | — |  |  |
| `kb_norm_20260811_105237` | 2026-08-11 | other |  | — | 83.8% | — | — |  |  |
| `kb_scale_20260814_151147` | 2026-08-14 | kb_scale |  | — | — | — | — |  |  |
| `kb_scale_conf_20260814_153359` | 2026-08-14 | kb_scale |  | — | — | — | — |  |  |
| `kb_scale_e2e_20260814_153505` | 2026-08-14 | kb_scale |  | — | — | — | — |  |  |
| `kb_scale_map_20260814_153304` | 2026-08-14 | kb_scale |  | — | — | — | — |  |  |
| `kb_seed_20260811_103804` | 2026-08-11 | other |  | — | 83.8% | — | — |  |  |
| `kb_shadow_20260811_103552` | 2026-08-11 | other |  | — | 84.4% | — | — |  |  |
| `kb_warmup_20260810_111952` | 2026-08-10 | other |  | — | 84.4% | — | — |  |  |
| `ood_probe_v3_20260810_114145` | 2026-08-10 | other |  | — | 59.6% | — | — |  |  |
| `ood_probe_v3_20260810_161809` | 2026-08-10 | other |  | — | 61.2% | — | — |  |  |
| `org_format_20260813_100441` | 2026-08-13 | other |  | — | 63.5% | — | — |  |  |
| `organizer_v3_20260810_135842` | 2026-08-10 | other |  | — | 59.6% | — | — |  |  |
| `organizer_v3_20260810_160232` | 2026-08-10 | other |  | — | 61.2% | — | — |  |  |
| `organizer_v3_20260813_095301` | 2026-08-13 | other |  | — | 61.2% | — | — |  |  |
| `prod_port_20260813_135019` | 2026-08-13 | other |  | — | 63.0% | — | — |  |  |
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
| `ocr_experiment/baseline_rapid` | 2026-08-04 | ocr_trial |  | — | 47.3% | — | — |  | scan=49 emb=25; scan org 34.7% nomor 54.5% |
| `ocr_experiment/baseline_rapid_tess` | 2026-08-04 | ocr_trial |  | — | 47.3% | — | — |  | scan=49 emb=?; scan org 26.5% nomor 57.6% |
| `ocr_experiment/composite_lfm_full_20260824_111939` |  | ocr_trial |  | — | — | — | — |  |  |
| `ocr_experiment/composite_rapid_hybrid` |  | ocr_trial |  | — | — | — | — |  |  |
| `ocr_experiment/corpus_doctr` | 2026-08-06 | ocr_trial |  | — | 45.8% | — | — |  | scan=49 emb=?; scan org 34.7% nomor 36.4% |
| `ocr_experiment/corpus_doctr [hybrid_10]` | 2026-08-06 | ocr_trial |  | — | 42.2% | — | — |  | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 10.0% nomor 28.6% |
| `ocr_experiment/corpus_doctr [hybrid_49]` | 2026-08-06 | ocr_trial |  | — | 49.2% | — | — |  | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 34.7% nomor 57.6% |
| `ocr_experiment/corpus_doctr [hybrid_embedded]` | 2026-08-06 | ocr_trial |  | — | 52.3% | — | — |  | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 28.0% nomor 68.4% |
| `ocr_experiment/corpus_nomor_cheap_rapid` | 2026-08-06 | ocr_trial |  | — | 46.8% | — | — |  | scan=49 emb=0; scan org 26.5% nomor 54.5% |
| `ocr_experiment/corpus_nomor_cheap_rt13` | 2026-08-06 | ocr_trial |  | — | 46.8% | — | — |  | scan=49 emb=0; scan org 26.5% nomor 54.5% |
| `ocr_experiment/corpus_nomor_cheap_tess13` | 2026-08-06 | ocr_trial |  | — | 47.3% | — | — |  | scan=49 emb=0; scan org 26.5% nomor 57.6% |
| `ocr_experiment/corpus_nomor_cheap_tess6` | 2026-08-06 | ocr_trial |  | — | 47.3% | — | — |  | scan=49 emb=0; scan org 26.5% nomor 57.6% |
| `ocr_experiment/corpus_nomor_crop` | 2026-08-06 | ocr_trial |  | — | 47.8% | — | — |  | scan=49 emb=?; scan org 26.5% nomor 60.6% |
| `ocr_experiment/corpus_nomor_crop_lines7` | 2026-08-24 | ocr_trial |  | — | 47.3% | — | — |  | scan=49 emb=0; scan org 26.5% nomor 57.6% |
| `ocr_experiment/corpus_nomor_crop_rt6` | 2026-08-24 | ocr_trial |  | — | 46.8% | — | — |  | scan=49 emb=0; scan org 26.5% nomor 54.5% |
| `ocr_experiment/hybrid_rapid_org` |  | ocr_trial |  | — | — | — | — |  |  |
| `ocr_experiment/hybrid_rapid_org [hybrid_49]` |  | ocr_trial |  | — | 49.2% | — | — |  | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 34.7% nomor 57.6% |
| `ocr_experiment/lfm25_full_20260824_111939` | 2026-08-24 | ocr_trial |  | — | — | — | — |  | scan=None emb=? |
| `ocr_experiment/lfm25_full_20260824_111939 [hybrid_10]` | 2026-08-24 | ocr_trial |  | — | 44.4% | — | — |  | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 20.0% nomor 28.6% |
| `ocr_experiment/lfm25_full_20260824_111939 [hybrid_49]` | 2026-08-24 | ocr_trial |  | — | 50.7% | — | — |  | HYB-001 hybrid (DocTR dates+organizer / baseline nomor); org 40.8% nomor 57.6% |
| `ocr_experiment/lfm25_ocr_20260813_151134` | 2026-08-13 | ocr_trial |  | — | 44.4% | — | — |  | scan=None emb=?; scan org 20.0% nomor 28.6% |
| `ocr_experiment/probe_doctr` | 2026-08-06 | ocr_trial |  | — | 40.0% | — | — |  | scan=10 emb=0; scan org 10.0% nomor 14.3% |
| `ocr_experiment/probe_got` |  | ocr_trial |  | — | — | — | — |  |  |
| `ocr_experiment/probe_ppu` |  | ocr_trial |  | — | — | — | — |  |  |
| `ocr_experiment/trial_a_easyocr` | 2026-08-04 | ocr_trial |  | — | 38.3% | — | — |  | scan=49 emb=?; scan org 36.7% nomor 15.2% |
| `ocr_experiment/trial_a_easyocr_gpu` | 2026-08-04 | ocr_trial |  | — | 42.3% | — | — |  | scan=49 emb=?; scan org 28.6% nomor 33.3% |
| `ocr_experiment/trial_a_paddle26` | 2026-08-04 | ocr_trial |  | — | 43.3% | — | — |  | scan=49 emb=?; scan org 32.6% nomor 39.4% |
