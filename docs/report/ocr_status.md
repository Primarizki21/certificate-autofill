# Status Cabang Eksperimen OCR

> Konsolidasi semua eksperimen OCR dari `docs/experiments_ledger.md` +
> `docs/report/runs_summary.md`. Dibuat sebagai titik start revive cabang OCR.
> Evaluasi: **GT v9 + matcher v2**, subset scan 49 cert (kecuali disebut lain).
> Field yang jadi penentu gate: **nomor** (baseline resmi scan = 57.6%).

## TL;DR

- **Baseline `RapidOCR+Tesseract` belum terkalahkan di field `nomor`.** Semua
  engine alternatif (Paddle×2, EasyOCR×2, DocTR, LFM2.5 full-scan) regress
  digit — pola konsisten: engine baru lebih baik di organizer/tanggal tapi
  hancur angka NIP/NIM/nomor.
- **Revive 2026-08-24 selesai (OCR-008 / HYB-002 / NC-003):**
  1. **HYB-002 PASS — winner baru cabang OCR**: hybrid LFM(organizer+dates) +
     baseline(nomor/dll) → organizer 26.5→**40.8% (+14.3pt)**, MACRO scan-49
     **50.75%** (> hybrid DocTR HYB-001 46.8%). Produksi = keputusan user
     (LFM batch-only ~77s/cert, RSS ~4GB, butuh F7 OCR queue).
  2. **OCR-008 (measurement)**: LFM full-scan 49 ok/0 err; komposit all-74
     MACRO **50.65%** vs baseline resmi 47.3%; model permanen di
     `~/.cache/lfm25/` (jangan simpan di `/tmp` lagi).
  3. **NC-003 FAIL/CLOSED**: tidak ada engine region murah yg pertahankan
     +3pt nomor (psm7-lines 57.6%, rapid_tess_psm6 54.5% vs control 60.6%);
     stage timing membuktikan floor = anchor full-page (3.5s), BUKAN engine;
     anchor cache JSON terbukti → re-try konkret: control multi-config
     rapid_tess + cache ≈ ~2.1s/cert.

## Daftar eksperimen (urutan kronologis)

| ID | Apa | Hasil kunci | Verdict | Re-try condition |
|---|---|---|---|---|
| OCR-001 | PaddleOCR 3.7 / paddlepaddle 3.3 (PP-OCRv6, CPU) | 3.8GB RSS/cert, ~50s/cert → OOM WSL 8GB | CLOSED — tak viable | GPU (VRAM offload) atau host ≥16GB RAM |
| OCR-002 | paddleocr 2.9 + paddle 2.6 (CPU, stack lama) | 7.1s/cert; organizer 18.4% naik tapi **nomor 39.4%** (regress), MACRO 39.8% | CLOSED — gate FAIL nomor | Field-extractor handle segmentasi paddle |
| OCR-003 | EasyOCR CPU max-side 960 | 12.7s/cert; organizer 20.4% (terbaik saat itu), **nomor 15.2%** (downscale merusak digit) | CLOSED — gate FAIL | Tidak ada di CPU @960 |
| OCR-004 | EasyOCR GPU full-res | 9.7s/cert; nomor 33.3%, MACRO 39.3% | CLOSED — tidak diadopsi | GPU jadi prioritas ATAU baseline nomor regresi |
| OCR-005 | Analisis 3 tool: DocTR / MMOCR / CnOCR | CnOCR redundant (=PP-OCR/RapidOCR); MMOCR stale (2023); **DocTR kandidat terbaik** (model baru, active Feb 2026, varian MobileNet CPU) | Analisis — DocTR dipilih utk probe | Probe terkontrol 5–10 cert scan |
| OCR-006 | DocTR probe (db_mobilenet_v3_large + crnn_mobilenet_v3_small, CPU, RLIMIT 8GB) pada 10 scan | 10/10 ok, RSS ~1.3GB, ~7.5s/cert; dates 88.9% (=), fuzzy organizer 70% vs 60% naik, tapi **nomor 14.3% vs baseline 28.6%** (digit hancur: `106/STF.E/HOLOGY7.0/x1t/2024` → `6/ST : E/ - L G 7. X1/2 o`) | FAIL — gate nomor regresi | Hanya sebagai **hybrid per-field**: DocTR utk dates+organizer, baseline tetap utk nomor. Full replacement ditutup |
| OCR-007 | VLM LFM2.5-VL-3B probe (GGUF Q4_0 + mmproj Q8_0, llama.cpp, transkripsi polos, 10 scan sama) | 10/10 ok, ~77s/cert (≈9× baseline), RSS ~4.9GB; **nomor 28.6% (= baseline — engine pertama yg tak regress)**; dates 88.9% (=); **organizer exact 0→20%** (fuzzy 50→60%); MACRO 40.0→44.4%. Transkripsi bersih | PASS (probe) | (1) Full run 74 cert (~95 menit) utk angka otoritatif; (2) hybrid per-field LFM(organizer/dates)+rapid_tess(nomor) pola HYB-001. Kendala: 77s/cert + RSS 4.9GB (butuh F7 OCR queue utk produksi) |
| HYB-001 | Hybrid per-field: DocTR (dates+organizer) + rapid_tess (nomor/activity/role), merge level extracted-dict, rule prioritas statis | Full 49 scan: organizer 20.4→24.5% exact, nomor 57.6% (=), dates 85.7% (=), **MACRO 45.8→46.8%**. Embedded 25 cert no-regress 50.5%/52.3%. Oracle = hybrid (merge rule sudah optimal) | PASS — semua gate met | Produksi butuh keputusan user (`ocr_fallback.py` = 2 engine + merge ≈ +~8s/cert) |
| NC-001 | Preprocessing nomor: anchor semantik bbox RapidOCR → crop region → re-render PDF zoom 6× → re-OCR multi-config tess, merge voting-disagreement (tanpa hardcode koordinat) | Ver1 upscale digital 3× = 0 gain. **Ver2 re-render PDF zoom 6×: nomor 57.6→60.6% (+3pt)**, dates/organizer =, MACRO 46.3%. Flip nyata: Falcon_Faiz `XI1`→`XII` (=GT). anchor_miss 22/49; crop +5.2s/cert | PASS — gate met | Integrasi produksi sudah ada via `ENABLE_OCR_NUMBER_2PASS` (**default FALSE**) — lihat PROD-001 |
| NC-002 | Ganti OCR region mahal (rapid_tess 5.2s) ke engine tunggal utk bikin NC-001 viable | Tak ada varian ≥60.6%: rapid 54.5%, tess_psm13/psm6 57.6% (=), rapid_tess_psm13 54.5%. Latency floor ~4.3s = anchor full-page + re-render, BUKAN OCR region | FAIL — gate nomor ≥60.6% & latency ≤1.5s tak tercapai | Validasi tesseract psm tunggal (~0.1s) di region multi-barir; kalau +3pt bertahan di ~1s/cert → flip flag |
| PROD-001 | Integrasi produksi: promosi v9 (organizer_v2 + tingkat router) + NC-001 2-pass di `ocr_fallback.py` | Pasca-promosi: baseline scan organizer 20.4→26.5%, MACRO 45.8→47.3%; crop nomor 60.6% bertahan; hybrid 49-stem 46.8→49.2%; pytest hijau | PASS | Flag 2-pass: diukur lazy = 0/18 recovered (cert nomor-hilang mayoritas memang tak ada nomornya di teks); varian penuh +2–10s/cert. Aktifkan hanya bila butuh +3pt dgn cost itu |
| OCR-008 | Revive LFM2.5 full-scan 49 stem (`--all-scans`, GGUF Q4_0+mmproj Q8_0, b10405); korpus komposit all-74 utk pembanding resmi | 49/49 ok, ~77–95s/cert, RSS ~3.9GB. Scan-49: nomor 51.5% (−6.1pt), dates 85.7% (=), **organizer 40.8% (+14.3pt)**, MACRO 49.75%. Komposit all-74: **MACRO 50.65%** vs 47.3% (+3.35pt) | PASS (measurement — input HYB-002) | Model di `~/.cache/lfm25/`; produksi butuh F7 queue |
| HYB-002 | Hybrid per-field LFM(organizer+dates) + baseline(nomor/kegiatan/role), merge rule statis sama HYB-001 (`--doc-label lfm25`) | 49 scan: **semua gate PASS** — nomor 57.6 (=), dates 85.7 (=), organizer 26.5→**40.8%**, MACRO 47.26→**50.75%** (+3.95pt atas HYB-001 DocTR). Oracle = hybrid. 10-stem repro persis OCR-007 | **PASS — winner baru cabang OCR** | Produksi menunggu keputusan user (batch-only LFM) |
| NC-003 | Region murah via line-splitting proyeksi (`tess_lines_psm7`) + kombinasi baru (`rapid_tess_psm6`) + stage timing + anchor cache `{stem: bbox}` | vs control 60.6%: lines7 **57.6%** (FAIL), rt6 **54.5%** (FAIL). Timing: anchor full-page 3.54s dominan, region cuma 0.55–1.64s; cache hits 32/32 identik. Proyeksi control+cache ≈ 2.1s/cert | FAIL/CLOSED — NC-001 tetap OFF | 1 trial eksplisit control rapid_tess + anchor cache kalau mau flip flag |
| HYB-003 | Hybrid organizer TANPA LFM: doc-engine = teks rapid-only (sudah dihitung baseline), rule merge sama; eval offline artefak existing = 0 OCR baru | Organizer 26.5→**34.7% (+8.2pt)**, fuzzy **77.5%** (terbaik); nomor/dates no-regress (=); MACRO **47.26→49.2% (+1.94pt)** @ 0 biaya. Kalah tipis dr HYB-002 (50.75%), kalahkan HYB-001 DocTR (46.8%) | PASS — winner non-LFM | Produksi: merge teks rapid intermediate di `ocr_fallback.py` (zero extra latency) = keputusan user |
| HYB-004 | Angka resmi komposit all-74 utk HYB-003: hybrid rapid di 49 scan + baseline di 25 embedded, evaluasi in-memory harness sama | All-74: MACRO exact **50.32%** (+3.06pt vs baseline), fuzzy 63.87% — **gap ke komposit LFM tinggal 0.33pt @ 0 biaya** | PASS | Angka resmi non-LFM terbaik |
| OCR-009 | Probe ppu-paddle-ocr (ONNX Bun binary, BEDA dr OCR-001/002): v6-tiny/v6-small/v5-en-server × 10 stem, canvas-native + watchdog RSS. ⚠️ Run pertama tanpa guard = OOM WSL → hardening permanen (page-per-page render, RSS watchdog SIGKILL, RLIMIT_AS tidak cocok utk JS/WASM) | Peak RSS: tiny ~1.7GB, small ~2.4GB, **v5-en-server ~3GB → kill 10/10 CLOSED**. Akurasi: nomor tiny/small **14.3%** vs baseline 28.6% (FAIL digit pola PP-OCR); dates small regress 66.7%; organizer-fuzzy tiny **80%** tertinggi | tiny/small FAIL gate; en-server CLOSED | v6-medium butuh RSS >3GB (hanya dgn headroom); ONNX CUDA EP saat GPU path siap |
| HYB-005 | Hybrid organizer ppu-v6-tiny + baseline (organizer-fuzzy ppu 80% tertinggi), like-for-like subset-10 vs HYB-003 | MACRO 42.2% < HYB-003 44.4% pada subset sama; organizer exact 10% vs rapid 20%; biaya +~2.7s/cert tak dibenarkan | FAIL/CLOSED — HYB-003 tetap winner non-LFM | Engine non-LFM yg kalahkan organizer-exact rapid tanpa regress digit |

## Angka pembanding antar-engine (field-level, subset scan)

Sumber: `docs/report/runs_summary.md` §OCR experiment + ledger.

| Engine | Nomor | Organizer | Dates | MACRO | Runtime | Catatan |
|---|:--:|:--:|:--:|:--:|:--:|---|
| **rapid_tess (baseline)** | **57.6%** | 26.5% | 85.7% | 47.3% | ~8.6s | Juara nomor; pasca-promosi v9 |
| rapid only | 54.5% | 34.7% | — | 47.3% | ~3.5s | Organizer lebih baik, nomor turun |
| paddle 2.6 | 39.4% | 32.6% | — | 43.3% | ~10.7s | Gate FAIL nomor |
| easyocr CPU@960 | 15.2% | 36.7% | — | 38.3% | ~12.7s | Downscale bunuh digit |
| easyocr GPU | 33.3% | 28.6% | — | 42.3% | ~9.7s | — |
| DocTR mobile (full 49) | 36.4% | 34.7% | — | 45.8% | ~7.5s | Dates/organizer bagus, nomor hancur |
| LFM2.5-VL-3B (probe 10) | 28.6%* | 20.0%* | 88.9%* | 44.4%* | ~77s | *like-for-like 10 stem; satu-satunya non-baseline yg tak regress nomor |
| LFM2.5-VL-3B (full 49, OCR-008) | 51.5% | **40.8%** | 85.7% | 49.75% | ~77–95s | Organizer exact terbaik semua engine tunggal; nomor regress −6.1pt |
| **Hybrid LFM+baseline (HYB-002)** | **57.6%** | **40.8%** | **85.7%** | **50.75%** | batch-only (~77s LFM) | **Winner cabang OCR** — merge rule statis, oracle=hybrid |
| **Hybrid rapid↔rapid_tess (HYB-003)** | 57.6% | 34.7% | 85.7% | **49.2%** | **~0 tambahan** | Winner non-LFM — organizer dr teks rapid yg memang sudah dihitung pipeline |
| ppu v6-tiny (subset-10, OCR-009) | 14.3% | 10% / fuzzy 80% | 88.9% | 40.0% | ~2.7s, peak 1.7GB | Digit hancur (pola PP-OCR); organizer-fuzzy tertinggi |
| ppu v6-small (subset-10, OCR-009) | 14.3% | 10% / fuzzy 60% | 66.7% | 31.1% | ~3.7s, peak 2.4GB | FAIL — dates & nomor regress |
| ppu v5-en-server (subset-10, OCR-009) | — | — | — | — | kill @~3GB RSS | CLOSED — RSS melebihi budget WSL 8GB (watchdog 10/10) |

## Peta pola yang terbukti (jangan dilupakan saat revive)

1. **Trade-off universal**: engine alternatif menang organizer/dates, kalah
   nomor. Tidak ada engine tunggal yang menang semua field.
2. **Digit adalah titik lemah OCR klasik non-baseline** — contoh nyata DocTR:
   `106/STF.E/HOLOGY7.0/x1t/2024` → `6/ST : E/ - L G 7. X1/2 o`.
3. **Re-render piksel nyata > upscale citra**: zoom 6× langsung dari PDF
   memulihkan numeral yang upscale LANCZOS tidak bisa (NC-001 Ver2).
4. Merge/disagreement per-field (bukan full replacement) = satu-satunya pola
   yang lolos gate berulang kali (HYB-001, NC-001).

## Status opsi revive (sesi 2026-08-24 — semuanya tereksekusi)

1. ~~Full run LFM sebelum hybrid~~ → **DONE (OCR-008)**: 49/49, komposit
   all-74 MACRO 50.65%.
2. ~~Hybrid LFM2.5-VL (pola HYB-001)~~ → **DONE, PASS (HYB-002)**: MACRO
   scan-49 50.75%, organizer +14.3pt, winner baru. Porting produksi menunggu
   keputusan user (LFM = batch-only, RSS ~4GB, butuh F7 OCR queue).
3. ~~NC-001 viable murah~~ → **CLOSED FAIL (NC-003)**: psm7 multi-baris sudah
   bisa (fix NC-002) tapi tak recover digit seperti multi-config;
   stage timing tunjuk anchor sebagai biaya nyata; anchor cache siap pakai →
   re-try tersisa: control rapid_tess + cache ≈ 2.1s/cert (borderline ≤2.0s).
4. **Produksi**: dua kandidat menunggu keputusan user — HYB-002 (LFM hybrid,
   butuh F7 queue) atau NC-001 flip via trial control+cache; `backend/**`
   tidak disentuh sepanjang sesi ini.

> Catatan git: tidak ada artefak OCR yang belum ter-commit saat dokumen ini
> dibuat (untracked = HYB-KB saja). Semua kode OCR eksperimen sudah aman di
> `tests/benchmark_runs/ocr_experiment/` (run dirs) + `tests/`.
