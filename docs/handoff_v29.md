# Handoff v29 — PROD-002 (port produksi organizer+nomor, GATE PASS) + KOREKSI R3

> Supersedes `docs/handoff_v28.md`. Sesi ini = eksekusi frontier #1 v28:
> port produksi lapisan organizer v3+R6+format + nomor (0 LLM) ke `backend/`,
> di-gerbang flag `ENABLE_ORGANIZER_NORMALIZATION` (default FALSE — produksi
> tak berubah sampai flip manual). Keputusan user: skip R1/R4, port additive.

---

## Hasil sesi

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. `backend/app/services/organizer_normalize.py` — port verbatim `_norm_organizer_v3` (R0/PREFIX_HELD/R2/R3/R6) + `_norm_org_format` (F1/F3) + `_norm_nomor` (D/E) | 1 modul baru, 0 duplikasi logika | DONE |
| 2. Wire di `extraction_pipeline.py` (flag `ENABLE_ORGANIZER_NORMALIZATION`, default FALSE) | Flag OFF = inert (smoke terbukti) | DONE |
| 3. `tests/test_organizer.py` — 27 unit test (fix-case korpus + skip rules + nomor) | 27/27 pass | DONE |
| 4. Re-eval `tests/benchmark_prod_port.py` — jalur produksi flag ON vs replica eksperimen, GT v9 + matcher v2 | **Port fidelity prod==ref: 0 mismatch**; organizer **37.8→63.5%** (47/74), nomor **59.6→76.9%** (40/52), MACRO **55.7→63.0%**, 28 fix / 0 regress, 0 LLM | **GATE PASS** |
| 5. Smoke pipeline PDF nyata (PRIMARIZKI_binary_2025) | flag OFF = value lama; flag ON = R0 strip trailing HIMA → GT exact | PASS |
| 6. QA | pytest **58 passed** (31 lama + 27 baru); diff = 2 file modif (+19 baris) + 4 file baru | DONE |
| 7. Dokumentasi | ledger PROD-002 + `docs/report/prod_organizer_port.md` + report_data `prod_002_port` + generate_report.py + runs_summary | DONE |

---

## Temuan penting sesi ini

1. **KOREKSI spec handoff v28 — R3 bukan dead code.** OOD-002/003 ablation
   "R3 = NO_FIX" diukur pada v3 TANPA lapisan alias (pre-ORG-004). Pada port
   final, R3 (strip prefix sampai "oleh") justru **membuka alias F1 APHSA**
   (`Public Health Career Track2oleh Divisi Kaprof APHSABEMFKM...` → `Divisi
   Kaprof APHSA BEM FKM Universitas Airlangga`) = **2 fix** (1952296, 2030335).
   Handoff v28 "R3 hapus" = salah konteks → R3 di-KEEP.
2. **Port final = 47/74 organizer (63.5%) vs eksperimen penuh 49/74 (66.2%)** —
   selisih persis 2 = R1 (Rasio_Faiz) + R4 (2955331) yang di-skip sesuai
   keputusan user (0 risiko, mekanisme GUARD F6 belum di-port).
3. **Flag-gating = nol disruptif**: `benchmark_pipeline` (baseline regex 42.2%)
   dan `offline_fields` (55.7%) tidak berubah — flag default FALSE, eksperimen
   benchmark memanggil fungsi produksi primitif langsung (bukan
   `run_extraction_pipeline`).
4. **Angka jalur akurasi kumulatif produksi** (GT v9 + matcher v2, 0 LLM,
   flag ON): organizer exact **63.5%** · nomor **76.9%** · MACRO exact **63.0%**
   · fuzzy **68.0%**.
5. Nomor D/E pada raw text: prefix "SERT-" ikut tertangkap (`SERT-2465/...` =
   GT, ternyata benar) dan `0101.17/...` terpotong jadi `17/...` — perilaku
   identik replica eksperimen (ORG-002 76.9% terukur dengan perilaku ini),
   bukan regress port.

---

## Frontier berikutnya (urutan saran)

1. **Flip flag `ENABLE_ORGANIZER_NORMALIZATION=true`** — keputusan user.
   Rekomendasi: aktifkan (semua gate met, 0 regress, 0 LLM); re-eval produksi
   penuh (PDF→text→field) sekali setelah aktif.
2. **Fix GT v9 inkonsistensi** (FMIPA "dan" 2954933 vs ACTION; HIMA
   pendek/panjang) → GT v10 (butuh keputusan user) — membuka F2/HIMASTA yang
   sekarang dilarang.
3. **R1/R4 + GUARD F6**: bila needs_review (REVIEW-001) di-port, R1/R4 bisa
   dibuka kembali (+2 fix → 66.2% = eksperimen penuh).
4. **Scoring organizer_v2**: hanya bila data baru (korpus >74) ATAU keputusan
   user rewrite extractor + re-baseline penuh (ORG-005 FAIL).
5. **KB**: TUTUP (v27 Verdict Final) — dibuka bila data baru (`audit.py`).

### Peta dokumen (agar agent sesi berikutnya tidak salah alamat)

- **KB** (eksperimen KB-001..006 + verdict) → `docs/report/team_review_kb.md`
  (agent) + `team_review_kb.xlsx` (user, lokal — `*.xlsx` di-gitignore).
- **ORG/PROD** (F1/ORG-003/F1C/ORG-004/ORG-005/PROD-002) →
  `docs/experiments_ledger.md` (ledger) + `docs/report/report_data.json`
  (laporan resmi: org_002_f1 + org_003_v3 + org_004_format + prod_002_port)
  → `scripts/generate_report.py` (docx/md/xlsx).
- Port produksi: `backend/app/services/organizer_normalize.py` + flag di
  `backend/app/config.py` + wiring `backend/app/services/extraction_pipeline.py`.

## Frontier tertunda (sama v24-v28)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field), R1/R4 + GUARD F6.

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Eksperimen tetap di `tests/` (port produksi PROD-002 sudah disetujui user)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002, ORG-005
- Pytest: `uv run python -m pytest tests/ -q` (58 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu
- Flag produksi default FALSE — flip = keputusan user

## Key Files

| File | Peran |
|---|---|
| `backend/app/services/organizer_normalize.py` | PROD-002 — normalisasi organizer+nomor (port verbatim) |
| `backend/app/config.py` | Flag `enable_organizer_normalization` (default false) |
| `backend/app/services/extraction_pipeline.py` | Wiring flag-gated |
| `tests/test_organizer.py` | 27 unit test fix-case + skip rules |
| `tests/benchmark_prod_port.py` | Re-eval port (fidelity + no-regress, GATE PASS) |
| `docs/report/prod_organizer_port.md` | Report PROD-002 |
| `docs/experiments_ledger.md` | PROD-002 PASS + KOREKSI R3 |
