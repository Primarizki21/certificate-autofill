# Handoff v33 — OCR-007: Probe LFM2.5-VL-3B (VLM OCR) GATE PASS

> Supersedes `docs/handoff_v32.md`. Sesi ini = eksekusi ide user: coba
> **LFM2.5-VL-3B** (VLM LiquidAI, klaim "Better OCR", support Bahasa Indonesia)
> sebagai engine OCR. Varian terendah RAM/quant dipilih: **GGUF Q4_0 + mmproj
> Q8_0** via llama.cpp `llama-server` (b10405), transkripsi polos.
> Hasil: probe 10 scan cert **GATE PASS** — engine OCR pertama yang tidak
> regress nomor, organizer exact 0→20%.

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. Setup runtime: llama.cpp b10405 + Q4_0 (1520MB) + mmproj Q8_0 (556MB) | Server RSS ~4.9GB di host 5.3GB tersedia (Docker mati) — aman | DONE |
| 2. Smoke test 1 PNG | Transkripsi bersih (Primarizki_kim: NIP/SKP benar), 72.4s | DONE |
| 3. `tests/benchmark_lfm25_probe.py` (mirror doctr probe) + probe 10 stem scan | 10/10 ok, 0 error, ~77s/cert | DONE |
| 4. Eval like-for-like GT v9 + matcher v2 vs baseline rapid_tess (10 stem sama) | nomor 28.6% (=), dates 88.9% (=), **organizer 0→20%** (fuzzy 50→60%), MACRO 40.0→44.4% | **GATE PASS** |
| 5. QA | pytest 58 passed; diff = 1 file tests/ baru; run dir gitignored | DONE |

---

## Temuan penting

1. **Nomor TIDAK regress** — pertama kalinya di semua eksperimen OCR
   (paddle 39.4%, easyocr 15.2%, DocTR 36.4% di full scan; OCR-001..006
   ditutup karena nomor). Transkripsi baca format nomor utuh
   (`106/STF.E/HOLOGY7.0/XI/2024`) — masalah nomor LFM = konsistensi
   ekstraksi/GT, bukan digit hancur.
2. **Organizer +20pt exact** — VLM baca struktur dokumen (jabatan/institusi)
   lebih utuh dr engine klasik.
3. **Cost tinggi**: ~77s/cert (≈9x baseline 8.6s) + server RSS 4.9GB +
   model 2.1GB. VLM autoregresif mahal utk OCR penuh — kendala produksi
   (relevan utk F7 OCR queue).
4. **nama_kegiatan 0% = baseline 0%** (harness OCR-only, tanpa embedded) —
   bukan regress. Kasus all-caps (FITCOMPETITION) = ranah AKT-004.
5. Output tersimpan di `tests/benchmark_runs/ocr_experiment/lfm25_ocr_20260813_151134/`
   (extracted_texts + ocr_meta.json + eval.json).

---

## Frontier berikutnya (urutan saran)

1. **OCR-007 lanjutan** (keputusan user):
   - **Full run 74 cert** (~95 min) → angka otoritatif vs baseline scan
     (nomor 57.6%, organizer 14.3%, MACRO 44.3%);
   - atau **hybrid per-field** (pola HYB-001): LFM utk organizer/dates +
     rapid_tess utk nomor — LFM organizer +20pt = potensi naikkan hybrid.
2. **AKT-003** — rencana v32 masih terbuka (grup A+B+C, target +8–12pt
   nama_kegiatan; baseline offline_prod).
3. **AKT-004** — grup D+E+F+G (termasuk all-caps yang muncul di FIT_Faiz).
4. GT v10, R1/R4 + GUARD F6, scoring organizer_v2 (data >74).

### Peta dokumen

- **OCR** → `docs/experiments_ledger.md` (OCR-007 PASS) +
  `docs/report/lfm25_ocr_probe.md` + report_data `ocr_007_lfm25` +
  runs_summary (78 runs). Harness: `tests/benchmark_lfm25_probe.py`
  (probe/eval, server di `/tmp/opencode/llama-cpp/llama-b10405/`,
  model di `/tmp/opencode/models/LFM2.5-VL-3B-GGUF/` — lokal, bukan repo).
- **AKT** → v32 tidak berubah (rencana utuh).

## Frontier tertunda (sama v24-v32)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6, HYB-001 OCR hybrid (integrasi produksi),
  AKT-003/004.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Eksperimen tetap di `tests/` (produksi: PROD-002 flag default OFF)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001,
  NC-001/002, ORG-005 (OCR-007 = PASS, bukan closed)
- Pytest: `uv run python -m pytest tests/ -q` (58 passed)

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_lfm25_probe.py` | OCR-007 — harness probe/eval LFM2.5-VL-3B (llama-server) |
| `docs/report/lfm25_ocr_probe.md` | Report OCR-007 (hasil + rekomendasi) |
| `docs/experiments_ledger.md` | OCR-007 PASS (baru) |
| `tests/benchmark_runs/ocr_experiment/lfm25_ocr_20260813_151134/` | Hasil probe (gitignored) |
| `docs/handoff_v32.md` | Rencana AKT-003/004 (masih terbuka) |
