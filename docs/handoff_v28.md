# Handoff v28 — ORG-004 (canonicalisasi format PASS) + ORG-005 (probe FAIL)

> Supersedes `docs/handoff_v27.md`. Sesi ini = redirect ke jalur akurasi
> (keputusan user: KB = cache, tidak menaikkan akurasi exact/fuzzy — bukti
> `wrong=0/disagree=0` KB-001..006 + Verdict Final v27). Dua eksperimen baru:
> **ORG-004** (bucket `format` organizer, canonicalisasi, GATE PASS) dan
> **ORG-005** (probe scoring organizer_v2, FAIL — tidak layak full run).

---

## Hasil sesi (committed: `64f0bf5` + commit ini)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. Recompute taksonomi pada baseline v3 (54.1%) | format 11, salah_org 8, kelebihan 5, kosong 4, kurang_lengkap 4, format_residu 2 | DONE |
| 2. ORG-004 `tests/benchmark_org_format.py` — canonicalisasi format di atas v3 | Organizer **54.1% → 66.2% (+12.1pt, 9 fix)**, MACRO **61.2% → 63.5%**, 0 regress, 0 LLM | **GATE PASS** |
| 3. OOD ORG-004 (mutation + noise, gate sama OOD-003) | Mutation drop −10.9% vs v3 −10.4% (+0.5pt, toleransi +1pt); noise 10/25/50% IDENTIK v3 | PASS |
| 4. ORG-005 probe scoring (8 salah_org + 4 kosong) | Hanya 1/12 fixable murah (Hitech); HIMASTA-expand regress 12; F4 BEMFTMM regress tingkat 1 | **FAIL (probe)** |
| 5. QA | pytest 31 passed; registry: org_format 63.5% | DONE |

---

## Temuan penting sesi ini

1. **ORG-004 = jalur akurasi tanpa AI yang paling produktif sejauh ini**:
   organizer 39.2% (F1) → 54.1% (v3+R6) → **66.2%** (ORG-004). MACRO
   offline 58.3% → 61.2% → **63.5%**. Semua 0 LLM call, produksi zero-touch.
2. **Bucket `format` habis** (11 → 2): 9 kasus di-canonicalisasi via F1 alias
   map + F3 suffix BEM FKM (mekanisme kamus general, pola sama OCR_ORG_MAP).
3. **GT v9 terbukti inkonsisten — 3 area jangan disentuh pipeline**:
   - FMIPA "dan": GT ACTION tanpa "dan", GT 2954933 dengan "dan" (F2
     menghapus "dan" = regress 2954933).
   - HIMA pendek/panjang: GT Venedict_specta "Himatesda" tapi GT
     Primarizki_hima "Himpunan Mahasiswa Teknologi Sains Data" (HIMASTA
     expand = regress 12 cert).
   - F4 (nilai berakhiran BEMFTMM → BEM FTMM) = +2 fix tapi regress tingkat
     1 cert (organizer mengalir ke router tingkat `map_tingkat_v8`).
4. **ORG-005 scoring = dead end di korpus 74**: sisa 12 kasus butuh rewrite
   `_score_candidate` (blast radius luas — extractor dipakai semua benchmark
   organizer), risiko regress tinggi (terbukti HIMASTA 12, F4 1). Perbaikan
   aman hanya 1/12. Full run TIDAK layak tanpa GT/data baru.
5. **Angka jalur akurasi kumulatif** (semua GT v9 + matcher v2, 0 LLM):
   organizer exact **66.2%** · MACRO exact **63.5%** · fuzzy **68.0%**.

---

## Frontier berikutnya (urutan saran)

1. **Port produksi organizer v3+R6+format** (R0/R2/PREFIX_HELD/R6 + F1 alias
   map + F3 BEM FKM KEEP; R1/R4 GUARD; R3/R5 hapus) — re-eval GT v9 pasca-port.
2. **Fix GT v9 inkonsistensi** (FMIPA "dan" 2954933 vs ACTION; HIMA
   pendek/panjang) → GT v10 (butuh keputusan user) — membuka F2/HIMASTA
   yang sekarang dilarang.
3. **Scoring organizer_v2**: hanya bila data baru (korpus >74) ATAU keputusan
   user rewrite extractor + re-baseline penuh.
4. **KB**: TUTUP (v27 Verdict Final) — dibuka bila data baru (`audit.py`).

## Frontier tertunda (sama v24-v27)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue, Eksperimen A
  (LLM per-field — tidak, F1 v3+R6+format PASS).

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Jangan sentuh `backend/` tanpa keputusan user (eksperimen tetap di `tests/`)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002, ORG-005
- Pytest: `uv run python -m pytest tests/ -q` (31 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu
- `report_data.json` belum berisi F1C/OOD-003/KB/ORG-004 — keputusan user

## Key Files

| File | Peran |
|---|---|
| `tests/benchmark_org_format.py` | ORG-004 — canonicalisasi format (9 fix) |
| `tests/benchmark_organizer_v3.py` | Lapisan v3 (R0-R6) — baseline ORG-004 |
| `docs/report/f1_organizer_format.md` | Report ORG-004 |
| `docs/report/team_review_akurasi.md` | Dokumen review tim (KB + jalur akurasi) |
| `docs/experiments_ledger.md` | ORG-004 PASS + ORG-005 FAIL |
