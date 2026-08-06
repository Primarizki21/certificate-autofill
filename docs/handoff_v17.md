# Handoff v17 — PROD-001: Promosi v9 + integrasi NC-001 ke produksi

> Supersedes `docs/handoff_v16.md`. Sesi ini EKSEKUSI PRODUKSI (bukan eksperimen):
> - **PROD-001 — promosi v9**: port organizer_v2 (ORG-001) + tingkat_router
>   (ROUTER-002/003) dari `tests/` ke `backend/app/services/`. Terverifikasi:
>   baseline scan organizer 20.4→26.5%, MACRO 45.8→47.3%, no-regress.
> - **NC-001 integrasi produksi**: 2-pass nomor di `ocr_fallback.py` (merge
>   disagreement) via `ENABLE_OCR_NUMBER_2PASS` — **DEFAULT FALSE** (lihat
>   temuan jujur di bawah).
> - Temuan penting yang MENGUBAH rekomendasi: lazy (nomor hilang) = **0/18
>   recovered**; varian penuh mahal (+2-10s/cert).

---

## PROD-001 — Promosi v9 (organizer_v2 + router) — DONE & VERIFIED

### Perubahan
1. `backend/app/services/organizer_v2.py` ← port `tests/organizer_extractor_v2.py`
   (v9/ORG-001): `_normalize_final` (akronim BEM kampus UNAIR, long-form→akronim),
   filter baris nomor (`_NOMOR_RE`/`_SERT_NO_RE`), keyword org & peran EN tambahan.
2. `backend/app/services/tingkat_router.py` ← port `tests/llm_router_v4.py`
   (v9): ROUTER-002 (`bem_no_univ`, `bem+hima`, `sem+univ`) + ROUTER-003
   (dept/luar dari raw_text OR organizer, key `hima_org`).

### Verifikasi (GT v9 + matcher v2, re-eval semua korpus)

| Korpus | MACRO scan (pra→pasca) | nomor | organizer |
|---|---|---|---|
| baseline_rapid_tess | 45.8→**47.3%** | 57.6% | 20.4→**26.5%** |
| baseline_rapid | 45.8→47.3% | 54.5% | 16.3→34.7% |
| corpus_nomor_crop (NC-001) | 46.3→47.8% | **60.6%** | 26.5% |
| corpus_doctr [hybrid_49] | 46.8→**49.2%** | 57.6% | 34.7% |
| corpus_doctr [hybrid_embedded] | →52.3% | 68.4% | no-regress |
| probe_doctr | 40.0% | 14.3% | 10.0% |
| trial_a_easyocr / gpu / paddle26 | 38.3 / 42.3 / 43.3% | — | naik (v9) |

- `pytest tests/` → **31 passed**.
- Smoke pipeline penuh 1 cert: parser pymupdf_fast_path, tingkat=Fakultas
  (router aktif), organizer v9, nomor benar, kelompok/jenis ter-map.
- Trial easy/paddle re-eval naik karena organizer_v2 v9; **ledger OCR-002..004
  tetap angka historis** (diukur pra-promosi) — beda snapshot, bukan inkonsistensi.

## NC-001 integrasi produksi — DONE, FLAG OFF (temuan jujur)

`backend/app/services/ocr_fallback.py`:
- `_find_number_item` (anchor semantik) + `_recover_number_region` (re-render
  clip zoom 6× → re-OCR rapid_tess).
- Trigger **disagreement** (bukan lazy): prepend `NOMOR : <crop>` bila nomor
  crop ≠ nomor baseline (persis eksperimen NC-001 yang PASS).
- Flag `ENABLE_OCR_NUMBER_2PASS` (default **false**).

### Temuan yang mengubah rekomendasi (diukur sesi ini)
- **Lazy (hanya saat nomor hilang) = 0/18 recovered.** 18 scan cert dgn nomor
  baseline kosong; region crop juga gagal baca (2160238 `OOOO3`, dst). GT
  mayoritas memang `-` (tanpa nomor). Cost tetap ~2-9s/cert utk 18 cert.
- **Varian penuh (disagreement)**: +3pt nomor (eksperimen), tapi region OCR
  (rapid + tess 3 PSM) = **+2-10s/cert** — tidak cost-effective sbg default.
- **Coba region-OCR murah (tess psm 7 baris tunggal, ~0.1s) = GAGAL** (region
  multi-baris → output kosong). psm 6/13 belum dicoba.

**Keputusan**: integrasi ada, flag OFF. Aktifkan HANYA bila butuh +3pt nomor
dgn cost tsb. Ini keputusan deploy-time, bukan default.

---

## Rencana EKSEKUSI sesi berikutnya (kalau mau lanjut)

1. **Smoke API penuh** (wajib setelah sentuh produksi):
   `docker compose up` / uvicorn → upload 1-2 PDF scan via frontend/API → cek
   mapping + needs_review. Perhatikan runtime OCR (2-pass off → baseline).
2. **Putuskan `ENABLE_OCR_NUMBER_2PASS`** default (sekarang false). Kalau mau
   gain +3pt nomor dgn cost +2-10s/cert, set true.
3. **Eksperimen berikut (kandidat) — NC-002**: region-OCR MURAH utk varian
   disagreement. Tes tesseract psm 6/13 atau rapid-only pada region;
   target ~1s/cert @ +3pt nomor. Kalau PASS → flip flag jadi default true.
   Gate: nomor scan ≥60.6%, region OCR ≤1.5s/cert, no-regress.
4. **Report**: regenerasi sudah dilakukan sesi ini (report_data + runs_summary
   + docx styling). Kalau ada perubahan angka eksperimen baru → update
   report_data + generate_report + runs_summary + handoff (ikutin B10).
5. **Commit + push** (user push, SSH passphrase).

## Keputusan yang DIBUTUHKAN USER (open)

1. **`ENABLE_OCR_NUMBER_2PASS`** default false (rekomendasi) vs true.
2. **NC-002 (region-OCR murah)** — mau diuji? (target: jadikan NC-001 viable)
3. **Docker/.env** — flag baru perlu diset di `docker-compose` env / `.env`
   produksi bila ingin aktif.

---

## What Was Done (sesi ini)

1. `backend/app/services/organizer_v2.py` ← tests v9 (ORG-001).
2. `backend/app/services/tingkat_router.py` ← tests v9 (ROUTER-002/003).
3. `backend/app/services/ocr_fallback.py` — 2-pass nomor (disagreement) +
   `_self_check`; `backend/app/config.py` + `enable_ocr_number_2pass`;
   `.env.example` + `ENABLE_OCR_NUMBER_2PASS=false`.
4. `tests/benchmark_hybrid_ocr.py` — fix `__main__` (demo→demo+main, CLI eval
   sebelumnya no-op).
5. Re-eval semua korpus OCR + hybrid (49/10/embedded) di bawah produksi baru;
   patch `probe_doctr/ocr_meta.json` scan_count=10.
6. `docs/experiments_ledger.md` +PROD-001, update NC-001 re-try (lazy=0/18);
   frontier → v17.
7. `docs/report/report_data.json` (catatan integrasi/re-eval) + regenerate
   `generate_report.py` + `generate_runs_summary.py`.
8. Handoff v16 → v17.

`pytest tests/` → 31 passed. `python -m app.services.ocr_fallback` self-check
ok. Produksi dipromosikan TANPA regresi; GT & raw CSV tak disentuh.

---

## Key Files

| File | Peran |
|---|---|
| `backend/app/services/organizer_v2.py` | PRODUKSI — v9 (ORG-001) |
| `backend/app/services/tingkat_router.py` | PRODUKSI — v9 (ROUTER-002/003) |
| `backend/app/services/ocr_fallback.py` | PRODUKSI — 2-pass nomor (flag OFF) |
| `backend/app/config.py`, `.env.example` | flag `ENABLE_OCR_NUMBER_2PASS` |
| `tests/benchmark_runs/ocr_experiment/**/eval*.json` | re-eval pasca-promosi (gitignored) |
| `docs/experiments_ledger.md` | +PROD-001 |
| `docs/report/runs_summary.md` + report_data.json | angka pasca-promosi |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Re-run benchmark tanpa GT v9
- Ubah angka eksperimen (ledger/report_data) jadi angka pasca-promosi — itu
  snapshot berbeda; simpan keduanya dgn label jelas
- Aktifkan `ENABLE_OCR_NUMBER_2PASS=true` tanpa smoke API + ukur cost riil
- Sentuh `tests/` yang bukan eksperimen aktif tanpa pytest ulang
