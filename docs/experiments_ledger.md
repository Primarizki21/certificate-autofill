# Experiments Ledger — Closed & Failed Approaches

> **Tujuan:** mencegah agent mengulang pendekatan yang sudah gagal. Cek SEBELUM
> mulai eksperimen (step B0 workflow). Tambahkan entri di SETIAP akhir eksperimen
> (PASS atau FAIL).
>
> **Project goals:** efisien · robust · cepat · hemat token (cost/budget) ·
> scalable ke produksi.
>
> Jika sebuah hipotesis ada di sini, JANGAN dicoba ulang kecuali
> "re-try condition"-nya terpenuhi.

---

## Entries

| ID | Hipotesis | Hasil | Verdict | Re-try condition |
|---|---|---|---|---|
| **OCR-001** | PaddleOCR 3.7 / paddlepaddle 3.3 (PP-OCRv6, CPU) baca nomor lebih baik | 3.8GB RSS/cert, ~50s/cert, >6GB VA saat init → OOM di WSL 8GB. Kualitas teks bagus tapi tak bisa dipakai. | CLOSED — tidak viable | Hanya di GPU (VRAM offload) atau host ≥16GB RAM; revisit kalau produksi pindah dari WSL |
| **OCR-002** | paddleocr 2.9 + paddlepaddle 2.6 (CPU, stack stabil lama) lebih ringan & akurat | Korpus 74/74 ok, 7.1s/cert. Scan: organizer 18.4% (naik) tapi nomor **39.4%** (regresi vs 57.6 baseline), MACRO 39.8%. | CLOSED — gate FAIL (nomor) | Hanya kalau field-extractor diperbaiki menangani segmentasi paddle yang berbeda |
| **OCR-003** | EasyOCR CPU (max-side 960) — downscale biar cepat | 12.7s/cert. Scan: organizer **20.4%** (terbaik) tapi nomor **15.2%** (downscale merusak digit), MACRO 34.3%. | CLOSED — gate FAIL (nomor/dates) | Tidak ada di CPU @960; full-res 53s terlalu lambat |
| **OCR-004** | EasyOCR GPU (full-res) — VRAM offload + cepat | 9.7s/cert. Scan: organizer 16.3%, nomor **33.3%**, MACRO 39.3%. Bukan hasil terbaik. | CLOSED — tidak diadopsi (prioritas user = CPU) | Hanya kalau GPU jadi prioritas ATAU baseline nomor regresi |
| **LLM-001** | Prompt `g_evidence` (minta bukti singkat sebelum jawaban) | Tingkat turun (75.7% vs f_bias 82.4%). | CLOSED — regresi (v8 P3) | Perlu struktur output yang lebih ketat; replay setelah LLM lebih mampu follow structured format |
| **LLM-002** | Layout representation (markdown/annotation) dimasukkan ke prompt | Tingkat 77.0%/78.4% (< f_bias 82.4%); OCR-bound (25/74 berteks embedded). | CLOSED — ditolak (v8 P4) | Hanya kalau OCR kualitas naik drastis |
| **LLM-003** | Per-field LLM (A1) / full-text (A2 v2) untuk semua field | A1: tingkat 47.3%, 834 tok/cert, 125 calls. A2: MACRO 58.3% tapi tingkat 36.5%, 834 tok. | CLOSED — superseded oleh tingkat-only hybrid | Sudah digantikan pipeline v7/v8 (router + tingkat-only); tetap jadi referensi MACRO tinggi |
| **ORG-001** | Organizer normalization di `organizer_extractor_v2.py` (abbreviation map, strip institusi induk, trailing-context, merged tokens, signer EN roles) | Organizer exact **16.2% → 33.8%** (full LLM benchmark v8), fuzzy **59.5% → 82.4%**, tingkat **82.4% → 83.8%**, MACRO **55.2% → 58.9%**, 176 tok/cert, 29 calls. Full benchmark PASS. | **PASS** — semua gate met, no-regress | Sudah dipromosikan ke eksperimen; produksi butuh keputusan user. Efek samping: organizer_v2 bersih bisa menghilangkan signal router (`dept`/`luar`) → di-fix ROUTER-003 |
| **ROUTER-001** | Router expansion: naive `univ&!fak&!sem&!lomba→Univ`, `hima&!luar→Departemen`, `fak&!univ→Fakultas` | Precision turun ke 78.2% (12 salah) — rule naive terlalu agresif, `univ` fire pada "Universitas Airlangga" induk & `hima` fire pada raw-text. | **FAIL** — gate precision ≥95% tidak tercapai | Re-try hanya dengan signal yang diperketat (org-level, exclude BEM/hima-raw) |
| **ROUTER-002** | Router expansion data-driven: `bem_no_univ`, `bem+hima`, `sem+univ` (org-level signals) | Router coverage **36→42/74 @100% precision**, 0 salah. | **PASS** — coverage naik, precision ≥95% terjaga | Bagian dari pipeline v9 (dengan ROUTER-003) |
| **ROUTER-003** | Router `dept`/`luar` signal dari raw_text (OR dengan organizer) — fix efek samping organizer_v2 | Router coverage **42→45/74 @100%**, pull balik 3 cert (Ananda×2 dept+fak, NIC hima+luar) yang hilang signal-nya karena organizer_v2 bersih. Full benchmark: tingkat 83.8%, 29 calls. | **PASS** — coverage +3, precision tetap 100% | Dipertahankan; guard: `luar` dari raw_text terbatas daftar universitas eksternal (tidak menangkap fakultas internal) |
| **METRO-001** | Matcher evaluasi v1 `is_abbreviation_of` (threshold salah: hitung inisial-kata vs 0.5×panjang string) + fuzzy `token_overlap ≥0.5` | False positive ganda: `BEM FEB UNAIR` vs `BEM FKM UNAIR`/`BEM FEB UGM`/`BEM FEB UPNVJT` dikredit exact/fuzzy (0.67) padahal beda org. Organizer exact 33.8% ter-diskon (akronim valid tak pernah exact). | CLOSED — diganti matcher v2 (handoff v12) | Tidak ada — matcher v2 (subsequence huruf + rasio kata ≥0.3 + rasio huruf ≤0.6 + tolak parsial kontigu) |
| **METRO-002** | GT v8 inconsistency (organizer): `Kementriann` typo, `Akuntasi` typo, `FIT_Faiz Informatioon` typo, `NIC_Faiz` kurang spesifik | GT v9 dibuat: 5 organizer fixes (3 typo + NIC lebih spesifik + hakim_lomba Akuntasi). Tingkat tak tersentuh → 83.8% stabil. | CLOSED — GT v9 frozen, v8 tetap acuan historis | Tidak ada — GT v9 + matcher v2 = baseline evaluasi baru |
| **EXP5-001** | Multi-field LLM: tingkat + organizer dalam SATU call (variant C: LLM organizer hanya untuk cert organizer-miss pasca matcher v2, oracle GT = ceiling experiment) | Verbose: tingkat 83.8% ✅, organizer exact 39.2→41.9%, fuzzy 79.7→85.1%, MACRO 60.2→60.7%, 29 calls, tapi **token 195 > gate 176**. Compact: token 185 (masih >176) tapi **tingkat regress 81.1%** (−2.7pt). Gate token tak tercapai — cost intrinsik field kedua +10–19 tok/cert. | **FAIL** — GATE token (≤176) tidak tercapai; compact merusak tingkat | Tidak ada di token ≤176. Multi-field hanya layak bila budget token dilonggarkan (mis. ≤200) ATAU pindah ke model yang hemat prompt (API) |
| **OCR-005** | Analisis 3 OCR tool (saran user): DocTR / MMOCR / CnOCR — mana yang layak diuji sebagai pengganti RapidOCR+Tesseract (OCR sebelumnya ditutup: nomor gagal) | **CnOCR** = keluarga PP-OCR (ONNX) — SAMA dengan RapidOCR yang sudah di pipeline → redundant, tak menambah baru. **MMOCR** = PyPI terakhir Jul 2023 (stale ~3 tahun), butuh mmcv/mmdet stack berat, risiko dependency hell di WSL 8GB. **DocTR** = keluarga model baru (CRNN/SAR/ViTSTR/PARSeq), active (v1.0.1 Feb 2026), English/Latin out-of-box, layout-aware, ada varian MobileNet untuk CPU. | **DocTR = kandidat terbaik** untuk probe; CnOCR skip (redundant), MMOCR skip (stale + berat) | DocTR: probe terkontrol 5–10 cert scan dulu (fokus nomor/ tanggal, gate vs RapidOCR+Tesseract baseline); kalau nomor ≥59.6% baseline baru run penuh |
| **OCR-006** | DocTR probe (handoff v13 → v14): db_mobilenet_v3_large + crnn_mobilenet_v3_small (CPU, via `paddle_probe_safe --engine doctr`, RLIMIT_AS 8GB, watchdog RSS) pada 10 scan cert tetap | 10/10 ok, 0 watchdog kill, RSS ~1.3GB/cert, ~7.5s/cert (init ~3.2s). Like-for-like GT v9 + matcher v2 (10 stem sama): DocTR **nomor 14.3%** (1/7) vs baseline rapid_tess **28.6%** (2/7); dates **88.9%** (= baseline); organizer exact 10%→0% naik, fuzzy **70%** vs 60%. Raw check: `106/STF.E/HOLOGY7.0/x1t/2024` → DocTR `6/ST : E/ - L G 7. X1/2 o` (digit hancur, NIP/NIM juga drop digit). | **FAIL — gate nomor regresi** (14.3% < 28.6% like-for-like; baseline resmi scan 57.6%). Dates & organizer PASS; nomor = pola sama semua engine non-baseline. | Hanya layak sebagai **hybrid per-field**: DocTR utk dates+organizer, baseline RapidOCR+Tesseract tetap utk nomor (mis. merge/2-pass per field). Full replacement DocTR ditutup. |
| **HYB-001** | Hybrid OCR per-field: DocTR (dates+organizer) + baseline rapid_tess (nomor/activity/role), merge di level extracted-dict sebelum mapper, rule prioritas statis | Full 49 scan, GT v9 + matcher v2: baseline organizer 20.4%/61.2% → **hybrid 24.5%/65.3%** (DocTR 24.5%/63.3%); nomor **57.6% (= baseline**, DocTR 36.4%); dates **85.7% (= baseline)**; MACRO 45.8%→**46.8%**. 10-stem: nomor 28.6% (=), dates 88.9% (=), organizer 0/60%→10/70%, MACRO 40.0→42.2%. Embedded 25 (tanpa DocTR, fallback baseline): 50.5%/66.1% no-regress. Oracle = hybrid (rule merge sudah optimal). | **PASS** — semua gate met (nomor/dates no-regress, organizer naik, embedded no-regress), tanpa sentuh produksi | Produksi butuh keputusan user (integrasi `ocr_fallback.py` = 2 engine + merge field; atau tetap pipeline teks tunggal). DocTR runtime ~7.5s/cert + baseline ~8.6s = +~8s/cert tambahan |

---

## Aturan Pengisian

1. **Satu baris per pendekatan tertutup** (engine, prompt variant, strategi).
2. Kolom `Hasil` = angka terukur (jangan opini).
3. Kolom `Re-try condition` = kondisi eksplisit yang membuat pendekatan layak
   dicoba ulang. Jika tidak ada, tulis "tidak ada".
4. Commit bersama kode eksperimen & update `runs_summary.md` (workflow B9-B11).
5. Referensi detail: `docs/handoff_v12.md` + `docs/report/runs_summary.md`.

## Hubungan dengan dokumen lain

- `handoff_v15.md` = **open frontier** (supersedes v14) (baseline + hipotesis terbuka).
- `runs_summary.md` = **angka terukur** (semua run).
- `experiments_ledger.md` (ini) = **closed list** (yang sudah dicoba & ditutup).
