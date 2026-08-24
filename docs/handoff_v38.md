# Handoff v38 — Revival Cabang OCR: OCR-008 → HYB-002 → NC-003

> Supersedes `docs/handoff_v37.md` **untuk cabang OCR saja**; frontier
> HYB-KB/LLM di v37 tetap valid. Sesi ini mengeksekusi 3 opsi revive dari
> `docs/report/ocr_status.md` sesuai plan `local://ocr-revival-plan.md`:
> LFM full-scan (Opsi 2) → hybrid per-field (Opsi 1) → region murah NC-001
> (Opsi 3). Opsi 4 (integrasi produksi) DILARANG — `backend/**` zero-touch,
> terverifikasi via diff + pytest 64 passed.

---

## Hasil sesi

| Eksperimen | Pertanyaan | Hasil | Verdict |
|---|---|---|---|
| **OCR-008** (`tests/benchmark_lfm25_probe.py --all-scans`, run `ocr_experiment/lfm25_full_20260824_111939` + komposit `composite_lfm_full_20260824_111939`) | Angka otoritatif LFM2.5-VL di seluruh domain scan? | 49/49 ok, 0 err, ~77–95s/cert, RSS ~3.9GB. Scan-49 like-for-like GT v9+matcher v2: nomor 51.5% (−6.1pt), dates 85.7% (=), **organizer exact 40.8% (+14.3pt)**, MACRO **49.75%**. Komposit all-74 (LFM scan + baseline embedded): MACRO **50.65%** vs pembanding resmi 47.3% (**+3.35pt**), fuzzy 60.97% | **PASS (measurement)** — output = input HYB-002 |
| **HYB-002** (`tests/benchmark_hybrid_ocr.py eval --doc-label lfm25`, `eval_hybrid_{10,49}.json`) | Pola HYB-001 dgn LFM sebagai doc-engine: lolos gate? | Semua gate PASS: nomor **57.6% (=** — merge pertahankan baseline), dates 85.7% (=), organizer 26.5→**40.8%**, MACRO 47.26→**50.75%** (+3.95pt atas HYB-001 DocTR 46.8%). Oracle = hybrid. 10-stem repro persis probe OCR-007 | **PASS — winner baru cabang OCR** |
| **NC-003** (`tests/benchmark_nomor_crop.py`: `tess_lines_psm7`, `rapid_tess_psm6`, stage timing, anchor cache) | Region murah bisa pertahankan +3pt NC-001 di ≤2.0s/cert? | vs control 60.6%: lines7 **57.6%** FAIL, rt6 **54.5%** FAIL. Stage timing: anchor full-page = biaya dominan (0.85–3.54s); region cuma 0.55–1.64s. Anchor cache `{stem: bbox}` terbukti (32/32 hits, teks identik) | **FAIL/CLOSED — NC-001 tetap OFF** |
| **HYB-003** (`benchmark_hybrid_ocr.py --doc-label rapid` atas artefak `baseline_rapid/` existing, run `hybrid_rapid_org`) | Gain organizer tanpa biaya LFM? | Organizer 26.5→**34.7% (+8.2pt)**, fuzzy →**77.5%**; nomor/dates no-regress (=); MACRO **47.26→49.2% (+1.94pt)** @ 0 OCR baru — kalahkan HYB-001 DocTR (46.8%), kalah tipis dr HYB-002 (50.75%) dgn gap persis = selisih organizer LFM vs rapid | **PASS — winner non-LFM** |

Detail angka: `docs/experiments_ledger.md` (entri OCR-008/HYB-002/NC-003/HYB-003) +

---

## Keputusan & artefak teknis

1. **Kode eksperimen (tests/, bukan produksi):**
   - `benchmark_lfm25_probe.py`: flag `--all-scans` (transkripsi 49 stem scan),
     perilaku skip-if-exists tidak berubah (resume-able).
   - `benchmark_hybrid_ocr.py`: flag `--doc-label` (JSON/print self-describing);
     `merge_fields` TIDAK disentuh.
   - `ocr_engine.py`: `split_lines_projection()` (proyeksi horizontal piksel
     gelap → strip baris) + `ocr_tess_lines_psm7()` (psm7 per strip — jawaban
     kegagalan psm7 multi-baris NC-002).
   - `benchmark_nomor_crop.py`: 2 engine region baru; `_crop_number_from_pdf`
     return `(text, info)` dgn `info.stages` timing per tahap; `--anchor-json`
     cache (skip full-page RapidOCR saat trial ulang; bbox identik).
2. **Model permanen**: GGUF + llama.cpp b10405 di `~/.cache/lfm25/`
   (`LFM2.5-VL-3B-Q4_0.gguf`, `mmproj-LFM2.5-VL-3B-Q8_0.gguf`,
   `bin/llama-b10405/`). JANGAN simpan di `/tmp` lagi — `/tmp/opencode/`
   ter-wipe OS di tengah sesi dan memaksa re-download ~2.1GB.
3. **Non-determinisme LFM** (temp 0.1): angka antar-run geser tipis; batch ini
   jalan di bawah kontensi CPU proses lain (77→95s/cert) tanpa efek kualitas.

---

## Frontier terbuka (urutan saran)

1. **Keputusan user HYB-002 produksi**: organizer +14.3pt & MACRO 50.75%
   menunggu keputusan porting — tapi LFM batch-only (~77s/cert, RSS ~4GB)
   → realistis hanya dengan F7 OCR queue. Alternatif jalur eksperimen:
   HYB-KB/LLM di atas HYB-002 (frontier v37 masih berlaku).
2. **NC-003 re-try sempit**: 1 trial eksplisit control multi-config rapid_tess
   + anchor cache (proyeksi ≈2.1s/cert, borderline gate ≤2.0s). Kalau lolos
   sekaligus nomor ≥60.6% → baru bicara flip `ENABLE_OCR_NUMBER_2PASS`.
3. **Komposit hybrid all-74**: eval_hybrid_49 baru cover scan; komposit
   hybrid (hybrid scan + baseline embedded) proyeksi ≈51–52% MACRO — satu
   command eval tambahan kalau dibutuhkan angka resmi.
4. DocTR probe korpus penuh & engine lain: tetap CLOSED per ledger.

## Verifikasi sesi

- `pytest tests/ -q` → **64 passed** (zero-regress).
- Meta Phase 1: `ocr_meta.json` stems=49 errors=0; `eval_scan49.json` +
  `eval_all74.json` ada.
- Bukti merge hidup NC-003: `stems_cropped`=2 (lines7) / 5 (rt6) > 0.
- Self-check modul + demo anchor/merge + micro-test line-splitting 2 baris:
  semua ok.
