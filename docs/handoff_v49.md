# Handoff v49 — Preflight Fine-Tuning GLiNER: Sanity Gate FAIL

> Supersedes `docs/handoff_v48.md`.

## Ringkasan Eksekutif

`NER-GLINER-002` berhenti sebelum benchmark 5-fold OOF. GLiNER v2.1 gagal gate sanity 20 epoch: training finite, tetapi exact span recall hanya 6/8 (75.0%); syaratnya 8/8. GLiNER2.5 tidak dijalankan karena plan menetapkan kegagalan sanity menghentikan OOF penuh.

Tidak ada perubahan pipeline produksi, model deployment, maupun flag.

## Audit Plan dan Koreksi

| Temuan | Koreksi tervalidasi |
|---|---|
| `find_token_span` end-exclusive dan first-hit lintas token | Konverter v1 menulis `end - 1`; enumerator whole-token lokal menolak label ambigu/boundary-expanded. |
| Audit awal memperlakukan tanda baca batas sebagai occurrence lain | Kanonisasi batas token kosong menghasilkan 213 whole-token field: 148 unambiguous, 65 ambiguous, 10 boundary-unmatched, 130 label tuple. |
| `InputExample.validate()` tidak melempar error | Error list non-kosong sekarang menjadi `ValueError`; `sanitize()` tidak dipakai. |
| `GLiNER2.from_pretrained()` span-only | Runner fine-tune memakai `AutoExtractor` dan assert arsitektur `boundary`. |
| GLiNER2 long API memakai window kata | Runner memakai window tokenizer-aware 512 subword / stride 64 dan inferensi per-window. |
| GLiNER v1 `max_width` diubah sesudah load | Runner memakai load-time override `max_length=512, max_width=64` dan assert head nested width 64. |

## Hasil Terukur

| Kondisi | Hasil | Verdict |
|---|---:|---|
| Alignment GT v9 | 310 field; 223 kandidat; 87 unmatched awal | Pass preflight |
| Label train konservatif | 130 tuple usable; 65 ambiguous + 10 boundary ditolak | Pass preflight |
| Zero-shot regression v2.1 | 35.48% exact framework (110/310) | Stabil |
| Zero-shot regression v2.5 | 28.71% exact framework (89/310) | Stabil |
| GLiNER v2.1 sanity | loss 0.9251 finite; exact span 6/8 | **FAIL** |
| GLiNER2.5 sanity / OOF | Tidak dijalankan | Diblokir gate |

Span yang tidak berhasil di-recall: `Webinar mengenai Global Warming` dan `28 Oktober 2023` pada dua dokumen sanity berlabel terbanyak.

## Empirical Robustness & Generalization Proof

1. **Lapis 1 — statistik:** 5-fold OOF, Bootstrap CI, dan metrik per-field tidak dijalankan karena gate pra-latih gagal. Tidak ada angka OOF yang diklaim.
2. **Lapis 2 — OOD:** mutation dan noise 10/25/50% tidak dijalankan untuk fine-tuned model. Zero-shot yang diulang tetap mencatat baseline resmi.
3. **Lapis 3 — anti-leakage:** split belum dibuat model; audit whole-token menolak 75 field tidak layak (65 ambiguous, 10 boundary). Semua 130 label train dapat ditelusuri ke satu span whole-token unik.
4. **Lapis 4 — safety net:** `needs_review` tidak berlaku karena mapper produksi tidak dipanggil. Zero blast radius dibuktikan: hanya `tests/`, generator report, plan, dan dokumen eksperimen berubah.

## File Diubah

- `GLINER_FINE_TUNING_PLAN.md` — audit preflight mengikat dan koreksi API.
- `tests/benchmark_gliner.py` — runner fine-tune OOF, alignment konservatif, window tokenizer-aware, strict finite/OOM gate, sanity gate.
- `tests/test_gliner_experiment.py` — 8 test kontrak tanpa unduhan model.
- `docs/experiments_ledger.md` — `NER-GLINER-002` FAIL.
- `scripts/generate_runs_summary.py` — CSV konsisten LF, tanpa trailing CR.
- `docs/report/runs_summary.md`, `docs/report/runs_summary.csv` — registry zero-shot dan artefak sanity diregenerasi.
- `docs/handoff_v49.md` — dokumen ini.

Artefak gagal lokal: `tests/benchmark_runs/gliner_sanity_gliner_multi_v2.1_20260903_214108/`.

## Open Frontier

1. Diagnosis parity train/inferensi untuk dua span yang hilang dengan konfigurasi sama persis; jangan mengubah threshold, LoRA, atau hyperparameter.
2. Hanya bila sanity mencapai 8/8 exact span: jalankan GLiNER v2.1 dan GLiNER2.5 OOF serial, lalu OOD, XLSX, dan laporan komparasi.
3. Production tetap Option A `ENABLE_TESSERACT_GEMINI=true`; Combined v4.2 tetap fallback staging sesuai status sebelumnya.
