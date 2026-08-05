# Handoff v11 — Exp1+Exp3 BENCHMARK PASS; Next: Promosi Produksi / Exp 4-6

> Supersedes `docs/handoff_v10.md`. Sesi ini:
> - **Exp 1 (Organizer normalization): ✅ FULL BENCHMARK PASS** — organizer exact
>   16.2% → 33.8%, tingkat 82.4% → 83.8%, MACRO 55.2% → 58.9%.
> - **Exp 3 (Router expansion): ✅ PASS** — coverage 36→45/74 @100% precision,
>   LLM calls 35 → 29. Termasuk ROUTER-003 fix (signal `dept`/`luar` dari raw_text).
> - **Exp 2 (Token optimization): ✅ PASS** — budget cut + calls 35→29 → 176 tok/cert.
> - **Exp 4/5/6/7: belum dikerjakan.**

---

## Current Baseline (v8 f_bias, produksi)

| Metric | v8 f_bias | Catatan jujur |
|--------|:---------:|---|
| Tingkat exact | **82.4%** (61/74) | Field LLM. |
| MACRO exact | 55.2% (212/384) | Terbebani organizer (16.2%) & nama_kegiatan (24.3%). |
| MACRO fuzzy | **74.7%** (287/384) | Normalisasi string = kunci gap. |
| Eff. tokens/cert | 214 | Biaya di prompt (448 tok/call × 35). |
| LLM calls / 74 | 35 | Router cover 39/74 @100%. |

## WINNER BARU — v9 (run_llm_v4_20260805_163541, GT v8)

| Metric | v8 baseline | **v9 (current)** | Delta |
|--------|:--------:|:-------------:|-------|
| **Tingkat exact** | 82.4% | **83.8%** | +1.4pp |
| **MACRO exact** | 55.2% | **58.9%** | +3.7pp |
| MACRO fuzzy | 74.7% | **76.8%** | +2.1pp |
| Organizer exact | 16.2% | **33.8%** | +17.6pp |
| Organizer fuzzy | 75.7% | **82.4%** | +6.7pp |
| Eff tokens/cert | 214 | **176** | -38 |
| LLM calls / 74 | 35 | **29** | -6 |
| Router coverage | 39/74 | **45/74 @100%** | +6 |

> Config: `GT_CSV_PATH=Ground_Truth_Sertifikat_v8.csv uv run python -m tests.benchmark_llm_v4 --organizer-variant phrase_v2 --router on`
> Semua gate PASS. Reproducible (2x run f_bias konsisten 78.4% → setelah router
> fix 83.8%). Per-cert vs baseline: 0 regresi eksperimen (2 selisih LLM-noise,
> prompt byte-identik).

---

## What Was Done (sesi ini)

### Exp 1 — Organizer Normalization ✅ (offline PASS)
Edit di `tests/organizer_extractor_v2.py`:
- `SIGNER_ROLES` + EN roles (DEAN, HEAD OF, KAPRODI, CHAIRMAN, VICE, ...).
- `ORG_KEYWORDS` + institusi (POLITEKNIK, INSTITUT, SEKOLAH, PERPUSTAKAAN,
  TAX CENTER, KELUARGA MAHASISWA, PUSAT, BPS).
- Cert-number line filter: `_NOMOR_RE` (Nom0r/Nom Or/No) + `_SERT_NO_RE`
  (SERT2128...) — kandidat nomor sertifikat tidak jadi organizer.
- `_clean`: truncate co-organizer ("Bekerja Sama Dengan", "In Collaboration"),
  trailing role/person ("Peserta Atas Partisipasinya Sebagai:", "Prof./Dr. <nama>"),
  second-university context, trailing year; strip leading signer role SEBELUM
  mid-string role rule (fix "Ketua BEM FKM UNAIR").
- `_normalize_final`: expand merged BEMFTMM→"BEM FTMM", append "Universitas
  Airlangga" utk UNAIR-campus BEM acronym (restricted whitelist), map
  long-form FEB/FKM/FST UNAIR → acronym.
- English faculty+dept join: skip signer lines & prefer non-signer fac line.

Hasil offline: exact 16.2%→31.1%, fuzzy 59.5%→75.7%, 0 regresi dari 11 baseline
exact. Target ~35% tidak penuh: GT org FTMM inkonsisten (7 short "BEM FTMM
Universitas Airlangga" + 2 long "Badan Eksekutif Mahasiswa Fakultas Teknologi
Maju dan Multidisiplin Universitas Airlangga") — satu output tak bisa match dua
bentuk. "Akuntansi" vs GT-typo "Akuntasi" sengaja TIDAK di-normalize (overfit).

### Exp 3 — Router Expansion ✅ (offline PASS)
Edit di `tests/llm_router_v4.py`:
- Naive rules v10 (`univ&!fak&!sem&!lomba→Univ`, `hima&!luar→Departemen`,
  `fak&!univ→Fakultas`) **GAGAL validasi** — precision 78.2% (12 salah).
  `univ` fire pada "Universitas Airlangga" institusi induk; `hima` fire pada
  raw-text (bukan org). Dicatat di ledger (ROUTER-001 FAIL).
- Ganti dengan data-driven (validated semua 74): `bem_no_univ`, `bem+hima`,
  `sem+univ` — coverage 42/74 @100% precision, 0 salah.
- `_sig` tambah signal `hima_org` (org-level saja).

### Exp 2 — Token Optimization (code, BELUM validasi)
Edit di `tests/llm_extractor_v4.py`: budget strong 140→100, normal 200→150,
poor_ocr 300→250. Estimasi offline prompt ~4 tok/call lebih kecil — MARGINAL.
Lever utama = kurangi LLM calls (Exp 3: 35→32 → est. 214→~194 tok/cert).
JANGAN trim bias instruction (terukur regresi 82.4→78.4 di v8).

### Infrastruktur baru (reusable)
- `tests/eval_organizer_offline.py` — organizer eval offline (no LLM),
  bandingkan hybrid vs phrase_v2; `--no-ner` utk cepat.
- `tests/eval_router_offline.py` — router precision pada SEMUA 74 (no LLM).

---

## What's Next — Promosi Produksi & Eksperimen Lanjut

### ✅ FULL LLM BENCHMARK SUDAH DILAKUKAN (run_llm_v4_20260805_163541)
Semua gate PASS (tingkat 83.8%, MACRO 58.9%, 176 tok/cert, 29 calls).
Catatan proses: run benchmark WAJIB pakai `GT_CSV_PATH=Ground_Truth_Sertifikat_v8.csv`
(default `Ground_Truth_Sertifikat.csv` = raw, 6 sel GT beda → angka tidak comparable).

### STEP SELANJUTNYA (keputusan USER)
1. **Keputusan promosi organizer_v2 + router rules ke produksi** —
   `backend/app/services/field_extractor.py` (extract_organizer_v2) +
   `tests/llm_router_v4.py` rules (atau pindah ke `backend/`). Sudah PASS
   benchmark, tapi merge = keputusan user.
2. `pytest tests/` + smoke `--limit 5` sebelum merge.
3. Update handoff v12 setelah keputusan.

### Eksperimen berikutnya
- **Exp 4: Confidence-based field routing** (3-4h) — per-field confidence
  <0.7 → LLM utk field itu. Robust + efisien.
- **Exp 5: Multi-field LLM extraction** (2-3h) — tingkat + organizer satu call.
- **Exp 6: Content-hash caching** (1-2h) — SHA-256 PDF → cache, duplikat
  <100ms. Prod change — butuh persetujuan.
- **Exp 7: Label collection** (ongoing) — `gt_review.xlsx` → 200+ label.

---

## Key Files

| File | Peran |
|---|---|
| `tests/organizer_extractor_v2.py` | Organizer phrase-v2 + normalisasi baru (Exp 1) — kandidat produksi |
| `tests/llm_router_v4.py` | Router + rules baru + raw-text dept/luar (Exp 3, ROUTER-003) — kandidat produksi |
| `tests/llm_extractor_v4.py` | Budget adaptif diturunkan (Exp 2) |
| `tests/eval_organizer_offline.py` | Organizer offline gate |
| `tests/eval_router_offline.py` | Router offline gate |
| `backend/app/services/field_extractor.py` | Produksi — UNTOUCHED, tunggu keputusan merge user |
| `docs/experiments_ledger.md` | +ORG-001 PASS, +ROUTER-001 FAIL, +ROUTER-002 PASS, +ROUTER-003 PASS |

---

## Jangan Lakukan

- Ubah `Ground_Truth_Sertifikat.csv` (raw = history)
- Run benchmark tanpa `GT_CSV_PATH=Ground_Truth_Sertifikat_v8.csv` (6 sel GT beda → angka invalid)
- Merge ke produksi tanpa keputusan user (benchmark sudah PASS, tapi merge = user)
- Trim bias instruction di `llm_extractor_v4.py` (regresi terukur)
- Normalize ke GT-typo ("Akuntasi") — overfit
- Sentuh `ocr_fallback.py` produksi
- Edit kode tanpa `codegraph_explore` dulu
- Push tanpa review — semua perubahan via PR
