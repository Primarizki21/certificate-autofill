# Phase v4 Results Summary

*Certificate Autofill Prototype - Numerical Results*

## Phase v4 Results Summary

### Method Comparison (Exact Accuracy)

| Field | Regex | NER v1 | Hybrid | Hybrid+PP | A1 (per-field) | A2 v2 (full-text) | Best |
|---|---|---|---|---|---|---|---|
| nama_kegiatan | 6.9% | 16.4% | 24.3% | 24.3% | 25.7% | **43.2%** | A2 v2 |
| penyelenggara | 6.9% | 11.0% | 12.2% | 13.5% | 13.5% | **31.1%** | A2 v2 |
| waktu_mulai | 81.8% | 27.3% | 81.8% | 81.8% | 81.8% | **94.5%** | A2 v2 |
| waktu_selesai | 81.8% | 7.3% | 81.8% | 81.8% | 81.8% | **94.5%** | A2 v2 |
| nomor | 58.0% | 0.0% | 59.6% | 59.6% | 65.4% | **73.1%** | A2 v2 |
| tingkat | — | — | — | — | **47.3%** | 36.5% | A1 |
| **MACRO** | 42.2% | 12.8% | 47.7% | 48.1% | 49.0% | **58.3%** | A2 v2 |

### Method Comparison (Fuzzy Accuracy)

| Field | Regex | NER v1 | Hybrid | Hybrid+PP | A1 (per-field) | A2 v2 (full-text) |
|---|---|---|---|---|---|---|
| nama_kegiatan | 19.2% | 43.8% | 63.5% | 63.5% | 70.3% | **85.1%** |
| penyelenggara | 41.1% | 50.7% | 47.3% | 50.0% | 50.0% | **73.0%** |
| waktu_mulai | 81.8% | 27.3% | 81.8% | 81.8% | 81.8% | **94.5%** |
| waktu_selesai | 81.8% | 7.3% | 81.8% | 81.8% | 81.8% | **94.5%** |
| nomor | 58.0% | 0.0% | 59.6% | 59.6% | 65.4% | **73.1%** |
| tingkat | — | — | — | — | 47.3% | 36.5% |
| **MACRO** | 53.3% | 28.8% | 65.5% | 66.1% | 64.6% | **74.5%** |

### Token Efficiency

| Metric | A1 (per-field) | A2 v2 (full-text) | Winner |
|---|---|---|---|
| MACRO exact | 49.0% | **58.3%** | A2 v2 |
| Total tokens | 61,679 | 61,706 | ~tied |
| Tokens per % MACRO | 1,259 | **1,058** | A2 v2 |
| LLM calls | 125 | **74** | A2 v2 |
| Prompt tokens | 60,851 | **53,788** | A2 v2 |
| Completion tokens | **828** | 7,918 | A1 |
| Avg latency/cert | **503ms** | 2,573ms | A1 |
| Avg tok/s | **63.0** | 54.9 | A1 |

### Progression

| Phase | Date | Method | MACRO | Delta | Cumulative |
|---|---|---|---|---|---|
| v2 | Jul 28 | Regex baseline | 42.2% | — | 42.2% |
| v2 | Jul 28 | NER v1 (pre-trained) | 12.8% | -29.4pp | 12.8% |
| v2 | Jul 30 | Hybrid (NER+regex) | 47.7% | +5.5pp | 47.7% |
| v3 | Jul 30 | Hybrid+PP | 48.1% | +0.4pp | 48.1% |
| v4 A1 | Jul 30 | Per-field LLM | 49.0% | +0.9pp | 49.0% |
| v4 A2 | Jul 30 | Full-text LLM (v1) | 47.7% | — | 47.7% |
| **v4 A2v2** | **Jul 30** | **Full-text LLM (v2)** | **58.3%** | **+10.2pp** | **58.3%** |

### Per-File Results

See `results_comparison.xlsx` → Sheet "Per-File tingkat" for per-certificate comparison of tingkat across methods.

### Key Takeaways

1. **Winner: A2 v2 (full-text)** — 58.3% MACRO exact, 61,706 tokens.

2. **Token efficiency** — 1,058 tokens per % MACRO (vs 1,259 for A1). Same token budget, +9.3pp accuracy.

3. **Biggest improvements** — waktu_mulai 81.8%→94.5%, waktu_selesai 81.8%→94.5%, nomor 59.6%→73.1%.

4. **Approach 1 still better at tingkat** — per-field prompt with heuristics (47.3% vs 36.5%).

5. **Full context helps** — LLM extracts nama_kegiatan (43.2%) and penyelenggara (31.1%) much better when it sees the whole text.

## Handoff v7 Results - Cost-Aware Hybrid (Tingkat-Only)

| Variant | Tingkat exact | MACRO exact | Eff. tok/cert | LLM calls |
|---|---|---|---|---|
| Hybrid+PP (no LLM) | 0% | 39.3% | 0 | 0 |
| b_minimized | 74.3% | 53.6% | 249 | 39 |
| c_adaptive | 68.9% | 52.6% | 167 | 39 |
| d_mid | 71.6% | 53.1% | 191 | 39 |
| e_hybrid | 77.0% | 54.2% | 202 | 39 |

Router: 35/74 decisions at 100% precision. Baseline run: tests/benchmark_runs/run_llm_v4_20260803_113310/ (GT raw).

## Handoff v8 Results - Router Fix + LLM Bias + Layout

Fixed GT: Ground_Truth_Sertifikat_v8.csv (3 audited tingkat corrections). Best run: tests/benchmark_runs/run_llm_v4_20260804_115212/.

| Variant | Tingkat exact | MACRO exact | Eff. tok/cert | LLM calls |
|---|---|---|---|---|
| a_context | 71.6% | 53.1% | 196 | 35 |
| b_minimized | 78.4% | 54.4% | 221 | 35 |
| c_adaptive | 71.6% | 53.1% | 149 | 35 |
| d_mid | 75.7% | 53.9% | 169 | 35 |
| e_hybrid | 79.7% | 54.7% | 182 | 35 |
| f_bias (winner) | 82.4% | 55.2% | 214 | 35 |
| g_evidence | 75.7% | 53.9% | 194 | 35 |

### Layout experiments (f_bias prompt)

| Input | Tingkat exact | MACRO exact |
|---|---|---|
| plain text (baseline) | 82.4% | 55.2% |
| layout markdown | 77.0% | 50.8% |
| layout annotated | 78.4% | 51.3% |

Layout rejected - only 25/74 PDFs have embedded text; markers disturb the deterministic extractors.

### GT audit effect (e_hybrid, router on)

| GT | Tingkat exact | MACRO exact | Ceiling-adjusted |
|---|---|---|---|
| raw | 57/74 (77.0%) | 54.2% | 56/71 (78.9%) |
| fixed_v8 | 57/74 (77.0%) | 54.2% | 56/71 (78.9%) |

Net-zero on raw count because 1981676 went correct->wrong while 2954283 went wrong->correct; the label corrections make the evaluation honest, not higher.

### Ship gate check

| Metric | Target | Actual | Status |
|---|---|---|---|
| Tingkat exact | >= 45% | 82.4% | PASS |
| MACRO exact | >= 50% | 55.2% | PASS |
| Eff. tokens/doc | <= 200 | 214 | MARGINAL |
| 100K-request tokens | <= 20M | 21.4M | MARGINAL |
| LLM call reduction | >= 40% | 53% | PASS |
| Rule precision | >= 95% | 100% | PASS |
| Date / number regression | none | none | PASS |

### Progression (tingkat exact, router on)

## Handoff v9–v17 Addendum — Production Promotion & OCR Line

### v9 winner: organizer_v2 + router (ORG-001, ROUTER-002/003)

| Metric | v8 f_bias | v9 organizer_v2 + router | v9 re-baseline (GT v9 + matcher v2) |
|---|---|---|---|
| Tingkat exact | 82.4% | 83.8% | 83.8% |
| MACRO exact | 55.2% | 58.9% | 60.2% |
| Eff tok/cert | 214 | 176 | 176 |
| LLM calls | 35 | 29 | 29 |
| Router coverage @100% precision | 39/74 | 45/74 | 45/74 |
| Organizer exact | 33.8% | 33.8% | 39.2% |

v9 (handoff v13): organizer_v2 + data-driven router ROUTER-002/003. Re-baseline GT v9 + matcher v2 (handoff v12) adalah metrologi jujur — MACRO 58.9% → 60.2%, organizer 33.8% → 39.2%.

### Production promotion — PROD-001 (v9 ke backend/app/services/)

organizer_v2.py + tingkat_router.py di-port dari tests/ ke produksi. Re-eval semua korpus di bawah konteks produksi (GT v9 + matcher v2): baseline rapid_tess scan MACRO 45.8 → 47.3%, organizer 20.4 → 26.5%, nomor 57.6% no-regress. pytest 31 passed; smoke pipeline 1 cert ok. Trial OCR lain (easy/paddle) ikut naik karena organizer_v2 — angka historis di ledger tetap.

### OCR exploration — bottleneck nomor sertifikat (line ditutup)

| Experiment | Approach | Nomor scan (GT v9) | Verdict |
|---|---|---|---|
| OCR-005 | Analisis 3 tool: DocTR / MMOCR / CnOCR | — | DocTR = kandidat (CnOCR redundant PP-OCR, MMOCR stale 2023) |
| OCR-006 | DocTR probe (mobilenet CPU, 10 scan) | 14.3% (like-for-like 28.6%) | FAIL — digit nomor hancur |
| HYB-001 | Hybrid per-field DocTR(dates+org) / baseline(nomor) | 57.6% (= baseline) | PASS — organizer +4.1pt, cost +7.5s/cert; tidak diintegrasikan |
| NC-001 | Re-render region zoom 6x + re-OCR rapid_tess (disagreement) | 60.6% (+3.0pt) | PASS — cost +5.2s/cert; flag OFF |
| NC-002 | Region-OCR murah (rapid / tess psm6/13 tunggal) | max 57.6% (= baseline) | FAIL — recovery melekat ke multi-config tess |

### Current production status

ENABLE_OCR_NUMBER_2PASS default FALSE — 2-pass nomor terintegrasi di ocr_fallback.py tapi keputusan deploy-time (gain +3pt nomor dengan cost +2-10s/cert). No-regress di produksi. Garis penggantian engine OCR untuk nomor ditutup (PaddleOCR, EasyOCR, DocTR, region-OCR murah).

| Phase | Method | Tingkat | MACRO |
|---|---|---|---|
| v4 | LLM A1 (per-field) | 47.3% | 49.0% |
| v4 | LLM A2 v2 (full-text) | 36.5% | 58.3% |
| v6 | LLM v3 Variant B | 39.2% | 46.4% |
| v7 | v7 P3 router rule-based | 71.6% | 53.1% |
| v7 | v7 P4 e_hybrid + router | 77.0% | 54.2% |
| v8 | LLM-001 g_evidence prompt (minta bukti sebelum jawaban) | 75.7% | 53.9% |
| v8 | LLM-002 layout representation (markdown/annotation ke prompt) | 77.0% | 50.8% |
| v9 | ROUTER-001 naive rule expansion (univ, hima, fak patterns) | 82.4% | 54.2% |
| v8 | v8 f_bias + router | 82.4% | 55.2% |
| v9 | ROUTER-002 data-driven rules (bem_no_univ, bem+hima, sem+univ) | 83.8% | 58.9% |
| v9 | ROUTER-003 dept/luar signal fix (raw_text OR organizer) | 83.8% | 58.9% |
| ocr | OCR Trial A — EasyOCR (CPU, max-side 960) | n/a | 34.3% |
| ocr | OCR Trial A — EasyOCR (GPU, full-res) | n/a | 39.3% |
| ocr | OCR Trial A — PaddleOCR 2.9 (CPU) | n/a | 39.8% |
| v9 | ORG-001 organizer_v2 (abbreviation map, strip, signer EN roles) | 83.8% | 58.9% |
| v9 | v9 organizer_v2 + router fix | 83.8% | 58.9% |
| v12 | v9 winner re-baseline (GT v9 + matcher v2) | 83.8% | 60.2% |
| ocr | HYB-001 hybrid OCR per-field (DocTR dates+organizer / baseline nomor) | n/a | 46.8% |
| ocr | NC-001 nomor crop preprocessing (re-render region zoom 6x) | n/a | 46.3% |
| ocr | NC-002 region-OCR murah (rapid / tess psm tunggal) utk 2-pass nomor | n/a | 47.3% |
| ocr | OCR-006 DocTR probe (mobilenet CPU, 10 scan) | n/a | 40.0% |
| v10 | F3-001 KB prototype warmup in-memory (opsi B, key=organizer+role) | 84.4% | - |
| v10 | OOD-001 probe mutation + noise (template & OCR noise injection) | 83.8% | 55.7% |
| v10 | F1 normalisasi organizer & nomor (0 LLM) | 81.1% | 58.3% |
| v10 | F1 organizer v3 + R6 (0 LLM) | 81.1% | 61.2% |
| v10 | REVIEW-001 needs_review field lemah (confidence berbasis pola) | - | - |
| v10 | STAT-001 validasi statistik 5-fold + bootstrap CI 1000× | 83.8% | 60.1% |
| kb | KB-001 shadow replay key v1 (router→KB→LLM) | 84.4% | - |
| kb | KB-002 seeded persistent KB (smoke, ceiling, persistence, noise, fragmentasi) | 83.8% | - |
| kb | KB-003 normalisasi key v2 (plain/stem/alias/both) | 83.8% | - |
| kb | KB-004 alat audit korpus (tests/kb/audit.py) | - | - |
| kb | KB-005 event_type=role terbaik (role/jenis/kelompok × 4 normalisasi) | 83.8% | - |
| kb | KB-006 alias mining data-driven (auto-alias = manual) | 83.8% | - |
| ocr | OCR-007 LFM2.5-VL-3B probe (VLM OCR, GGUF Q4_0 + mmproj Q8_0, 10 scan) | n/a | 44.4% |
| v10 | AKT-001 taksonomi nama_kegiatan (report-only, 6.8% exact) | - | - |
| v10 | AKT-002 deteksi nama_kegiatan v2 (0 LLM) | 81.1% | 68.8% |
| v10 | AKT-003 deteksi nama_kegiatan v3: Sebagai Peserta + atthe/inthe (0 LLM) | 81.1% | 71.6% |
| v10 | ORG-004 canonicalisasi format (0 LLM) | 81.1% | 63.5% |
| v10 | ORG-005 probe scoring extractor (sisa 12 kasus) | 81.1% | 63.5% |
| v10 | PROD-002 port produksi organizer v3+R3+R6+format + nomor (flag-gated) | 81.1% | 63.0% |
| v10 | AKT-004 deteksi nama_kegiatan v4: Event/lomba/seminar on (0 LLM, gate scope-kecil) | 81.1% | 72.1% |
| v10 | AKT-005 deteksi nama_kegiatan v5: grup D all-caps/spacing (0 LLM) | 81.1% | 73.7% |
| kb | KB-PROD-001 semantik produksi (servable/resolve/audit_due) | - | - |
| kb | KB-SCALE-001 simulasi workload skewed (500-5000 req) | - | - |
| kb | KB-SCALE-002 race tulis multi-worker (threading.Lock fix) | - | - |
| kb | KB-SCALE-003 peta hemat (5 volume × 5 key space × 3 skew) | - | - |
| kb | KB-SCALE-004 confirm 2x vs 3x (wrong +20 @2x) | - | - |
| kb | KB-SCALE-005 akurasi+biaya e2e (hemat 87%, akurasi 99.3%) | - | 99.3% |
| v10 | HYB-COMBINED gabungan terbaik (router + AKT-005 + ORG-004, 0 LLM) | 81.1% | 73.7% |
| v10 | HYB-LLM hybrid + LLM tingkat (26 cert unrouted, llama3.1:8b) ** | 83.8% | 74.2% |

## Handoff v18–v21 Addendum — F1 Organizer v3 (0 LLM) & Robustness OOD Probe

### F1 lanjutan organizer v3 (ORG-003)

Lapisan post-processing organizer tanpa AI (tests-only, produksi tak disentuh): R0 fix bug rule B, R1 strip suffix ', Faculty/Department' (Inggris saja), R2 strip prefix 'Library Class', R3 strip prefix sampai 'oleh', R4 strip suffix mulai tanggal, R5 normalisasi dash 'S-1'→'S1', fix regex 'Which [was] Held From <tgl> to <tgl> by'. Hasil (GT v9 + matcher v2, 0 LLM): organizer exact 39.2% → 45.9% (+6.7pt, GATE PASS), MACRO 58.3% → 59.6% no-regress. 5 fix per-cert: PRIMARIZKI (rule B), Rasio_Faiz (R1), 2955331 (R4 tanggal), Venedict ORM (R2), Venedict_specta (prefix held).

### F1C-001: enrich kurang_lengkap organizer (R6)

Lanjutan ORG-003: lengkapi organizer pendek dari konteks teks (0 LLM): join baris beruntun berkata-kunci org (2954933: camel-split + typo OCR 'llmu'->'ilmu'), Biro-prefix (SERTIF76), Himasada + baris 'DEKAN FAKUETASILMU KOMPUTER', IRIS: baris org tepat di atas baris fakultas, dept OCR-merge 'INFORMATIONSYSTEMSSTUDYPROGRAM' (Ananda Agentic AI + E-certificate (1)). Guard keras: v tanpa penanda fakultas/kampus, baris lanjutan beruntun max 2, dedup != v. Hasil: organizer exact 45.9% -> 54.1% (+6.2pt, 6 fix), MACRO 59.6% -> 61.2% no-regress, 0 regress, 0 LLM. Kasus tak fixable dari teks (skip): 2160238 (masalah scoring), NIC_Faiz & SDC Unisba (OCR rusak).

### Robustness OOD probe lapisan v3 (OOD-002)

Uji kerapuhan aturan v3 saat varian sertifikat baru: template mutation (institusi/event diganti) + OCR noise 10/25/50% + ablation per aturan + noise survival fix-cert. Verdict: FAIL gate drop-relatif — tapi mutation 0 kerapuhan aturan nyata (extra drop = 100% kontaminasi GT, nilai v3 justru mengikuti institusi baru); noise: R4 rapuh sejak 10% (digit tanggal rusak 'July 30'→'July 3O') & R1 sejak 25% (kata merge 'Facultyof'); R0/R2/PREFIX_HELD bertahan s.d. 50%. R3 = NO_FIX & R5 = DEAD (tanpa manfaat terukur, kandidat hapus). Gain absolut v3 tetap positif di semua kondisi (noise 10%: organizer 44.5% vs v9 37.8%).

Re-run OOD probe dengan R6 (RULE_ORDER + 'R6'). Verdict: FAIL gate drop-relatif (struktur kerapuhan SAMA dengan OOD-002) tapi R6 menambah 0 kerapuhan: fix 6, regress 0, survival 100% di noise 10%, 0 fix mati di noise 25/50% & mutation non-kontaminasi — lebih robust dari R1/R4 (compact-equality tahan char-confusion, typo map OCR menangani merge). Mutation: drop organizer v3 21.6% vs v9 16.2% = 100% kontaminasi GT (4 cert). Noise: extra drop identik OOD-002 (10% +1.4 / 25% +1.3 / 50% +4.1pt) — R4 sejak 10%, R1 sejak 25%, 50% = matcher digit S1->SI (bukan aturan strip). Gain absolut v3 tetap positif (noise 50%: 41.9% vs v9 29.7%).

### Rekomendasi port produksi (menunggu keputusan user)

- R0, R2, PREFIX_HELD, R6: KEEP — aman dipromosikan.
- R1, R4: GUARD — rapuh di noise OCR, wajib ditemani needs_review (F6) sebagai jaring pengaman.
- R3, R5: hapus — tanpa manfaat terukur di korpus.
- R6 = satu-satunya aturan dengan >=3 fix-cert (6) — klaim robust valid di level korpus; validasi data baru tetap wajib untuk generalisasi (cert non-UNAIR/FTMM).
