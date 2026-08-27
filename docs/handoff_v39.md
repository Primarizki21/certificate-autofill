# Handoff v39 — NC-004 re-try FAIL/CLOSED + C1-001 verifikasi (frontier #2 & #5 v38)

> Supersedes `docs/handoff_v38.md`. Sesi ini = eksekusi dua poin frontier v38
> setelah user memutuskan: **NC re-try sempit** (frontier #2) + **verifikasi C1
> nama_kegiatan** (frontier #5). Fine-tune bobot OCR (TrOCR/GOT/PP-OCR,
> frontier #4) **DITUNDA** — dataset 74 cert terlalu kecil (keputusan user).

---

## Hasil

| Eksperimen | Metode | Hasil | Verdict |
|---|---|---|---|
| **NC-004** | Re-try NC-003: region control rapid_tess multi-config + anchor cache (`corpus_nomor_crop_rt6/anchors.json`, 32/49 hits) — `benchmark_nomor_crop.py run --region-engine rapid_tess --anchor-json ...`, run dir `corpus_nomor_crop_retry_ctrl_cache` | Nomor **57.6% (19/33) = baseline** — gate ≥60.6% FAIL; latency **avg 6.05s/cert** ≫ gate ≤2.0s FAIL | **FAIL/CLOSED — NC-001 tetap OFF** |
| **C1-001** | Verifikasi: extractor AKT-005 di teks OCR branch (`baseline_rapid_tess`, raw OCR 49 scan + 25 embedded) — `tests/verify_c1_akt_scan.py` (baru) | Scan-49: nama_kegiatan exact **6.1% → 59.2% (+53.1pt)**, fuzzy 12.2→83.7%, MACRO 59.60→70.00%; 27 fixes / 1 regress (KARSA suffix) / 0 regress field lain | **PASS (verifikasi) — C1 riset REDUNDAN dgn AKT-002..005** |

## Temuan kunci

### NC-004 — kenapa re-try gagal (dua gate, dua alasan)

1. **Akurasi net 0**: recovery Falcon_Faiz `XI1`→`XII` TEREPRODUKSI (+1), TAPI
   voting-disagreement menimpa nomor benar IRIS (14): crop
   `2902/B/DST//UN3.FTMM/KM./2026` (double-slash) → −1. Gain +3pt NC-001 rapuh:
   bergantung jalur kode/bbox, dan aturan "crop beda = crop menang" bisa
   merusak. Bukti per-stem: 2030335 (=), 2955331 (salah keduanya), ACW (salah
   keduanya), Falcon (+1), NIC (=), IRIS (−1).
2. **Latency**: avg 6.05s/cert (median 5.65). Stages: render 0.58 + anchor
   1.74 (17 miss tanpa cache) + region_render 0.05 + **region 3.79s**. Proyeksi
   ~2.1s di v38 SALAH: timing region 0.55–1.64s (NC-003) itu engine MURAH
   (rapid/tess tunggal), bukan control multi-config rapid_tess (~3.8s). Bahkan
   dgn cache 100% → ~4.4s/cert ≫ 2.0s.

→ `ENABLE_OCR_NUMBER_2PASS` tetap OFF. Re-try hanya relevan jika ada region-OCR
<1s yang mempertahankan 60.6% — belum ada kandidat (NC-002/003 semua FAIL akurasi).

### C1-001 — frontier #5 ditutup (redundan)

- Klaim v38 "nama_kegiatan 6.1% semua varian" = **artefak harness**: eval cabang
  OCR (`benchmark_hybrid_ocr.py`) memakai extractor PRODUKSI untuk
  nama_kegiatan; perbaikan AKT-002..005 (`extract_activity_v5`, 62.2% all-74)
  tidak pernah dipasang di harness itu. Verifikasi ini mereproduksi 6.1% dengan
  offline_prod, lalu +AKT-005 → **59.2%** di teks OCR mentah.
- Korpus AKT asli (`run_20260728_131835`, teks pipeline produksi) TERBUKTI BEDA
  dari `baseline_rapid_tess` (raw OCR) utk stem yang sama — verifikasi ini sah,
  bukan sekadar ulang AKT.
- "Extractor agnostik struktur" (insight OCR-010, GOT prosa) sudah ter-cover:
  anchor AKT memakai `re.search(..., DOTALL|IGNORECASE)` = lintas baris.
- Tindak lanjut yang relevan (bukan riset baru): pasang `extract_activity_v5`
  di harness eval OCR; port produksi = keputusan user (pola PROD-002).

## Keputusan & artefak teknis

1. **Fine-tune bobot OCR ditunda** (TrOCR / GOT `ocr-2` / PP-OCR recognition):
   dataset 74 cert terlalu kecil untuk fine-tune yang mengubah bobot — konsisten
   dgn decision agentmemory "wait for 200-500 labeled certs". Re-try condition
   tetap tercatat di ledger (OCR-010/011).
2. **Kode baru**: `tests/verify_c1_akt_scan.py` (verifikasi C1, reusable) —
   produksi `backend/**` TIDAK disentuh.
3. **Run dir**: `tests/benchmark_runs/ocr_experiment/corpus_nomor_crop_retry_ctrl_cache/`
   (ocr_meta.json + eval.json + anchors.json).
4. **Report**: `docs/report/c1_akt_scan.md` (fix/regress per stem scan-49).
5. Ledger: +C1-001 (PASS), +NC-004 (FAIL/CLOSED); pointer open frontier →
   handoff ini. Entri lama (NC-001..003, AKT-001..005, OCR-*) TIDAK diubah.

---

## Frontier terbuka (urutan saran)

1. **Keputusan produksi (user)**: (a) HYB-003 hybrid rapid↔rapid_tess
   (49.2% scan / komposit **50.32%**, zero latency) — kandidat utama non-LFM;
   (b) AKT-005 extractor nama_kegiatan layak dipakai di eval/pipeline produksi
   (C1-001 membuktikan transfer ke teks OCR mentah, +53.1pt scan-49);
   (c) HYB-002 LFM tetap batch-only.
2. ~~NC re-try~~ → **CLOSED** (NC-004 FAIL dua gate).
3. GPU RTX 5050 tersedia — engine GPU lain tetap layak diprobe; prioritas
   rendah selama HYB-003 + AKT-005 belum di-port.
4. ~~TrOCR fine-tune / GOT ocr-2 / PP-OCR fine-tune~~ → **TUNDA** sampai
   dataset ≥200-500 cert berlabel (keputusan user).
5. ~~C1 riset nama_kegiatan~~ → **CLOSED** (C1-001: redundan dgn AKT-002..005).

## Verifikasi sesi

- `pytest tests/ -q` → hijau (lihat hasil di bawah).
- NC-004: `ocr_meta.json` stems_ok=49, cropped=6, anchor_miss=17, hits=32;
  eval.json nomor 57.6% (19/33), MACRO 47.3% (= baseline).
- C1-001: scan-49 exact 6.1→59.2%, MACRO 59.60→70.00%, 27 fix / 1 regress;
  `docs/report/c1_akt_scan.md` + `summary_c1.json`.
