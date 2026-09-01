# Handoff v41 — Combined v3 Composite Staging (MACRO 85.7% @ 0 LLM) & 5-Branch Execution

> Supersedes `docs/handoff_v40.md`. Sesi ini berhasil mengeksekusi seluruh 5 cabang
> eksperimen lanjutan dari `combined-v2-experiment-branches-plan.md` dan mengintegrasikannya
> ke dalam staging bundle **Combined v3** (`app/services/combined_extractor.py`, gated `ENABLE_COMBINED_V3=False`).

---

## 1. Ringkasan Eksekutif Hasil 5 Cabang & Komposit

Seluruh 5 cabang eksperimen mencapai target gate dan **0 regresi** (zero-regression invariant):

| Branch & ID | Modul & Metode | Baseline | Hasil Baru | Delta | Gate & Verdict |
|---|---|:---:|:---:|:---:|---|
| **Branch 1: ROUTER-006** | Contextual Disambiguation Router (7 rules 5-fold CV precision 100%) | 56/74 (75.7%) | **63/74 (85.1%)** | **+7 certs** | **PASS** — 100.0% precision on all 5 folds |
| **Branch 2: DATE-001** | Multi-day spans, English ordinals, OCR year normalizer | 43/55 (78.2%) | **52/55 (94.5%)** | **+16.4pt** | **PASS** — 9 fixes, 0 regression (gate $\ge 94.5\%$) |
| **Branch 3: ORG-006** | OCR spacing & acronym collapse ('Us U' $\to$ 'USU'), S-1 canonicalization, DPKKA fallback | 46/74 (62.2%) | **56/74 (75.7%)** | **+13.5pt** | **PASS** — 10 fixes, 0 regression (gate $\ge 73.0\%$) |
| **Branch 4: ACT-006** | Spacing & OCR repairs (2 O 24 $\to$ 2024, AI vs Al, ANAVA, GRADIANT), stop-token boundary | 46/74 (62.2%) | **56/74 (75.7%)** | **+13.5pt** | **PASS** — 10 fixes, 0 regression (gate $\ge 74.3\%$) |
| **Branch 5: NUM-003** | Roman numeral month OCR repair (XI1 $\to$ XII, X1 $\to$ XI), Poisson dot-code & Hitech recovery | 40/52 (76.9%) | **46/52 (88.5%)** | **+11.5pt** | **PASS** — 6 fixes, 0 regression (gate $\ge 86.5\%$) |
| **Branch 6: COMBINED-V3** | Composite End-to-End Staging Bundle (`apply_combined_v3`, 0 LLM) | 74.2% (285/384) | **85.7% (329/384)** | **+11.5pt** | **PASS — Milestone $\ge 85.0\%$ Terlampaui (0 LLM)** |

---

## 2. Detail Per-Field Breakdown (All-74 Certificates vs GT v9 + Matcher v2)

| Field Name | Combined v2 Baseline | Combined v3 Composite | Delta | Catatan Perbaikan |
|---|:---:|:---:|:---:|---|
| `nama_kegiatan_sertifikasi` | 46/74 (62.2%) | **56/74 (75.7%)** | **+13.5pt** | ANAVA, GRADIANT, Agentic AI, KARSA, SPECTA, Youth Today |
| `waktu_mulai_pelaksanaan` | 45/55 (81.8%) | **52/55 (94.5%)** | **+12.7pt** | Ordinal 23th, 7th-9th July, 21-23 Agustus, 7-8 Februari |
| `waktu_selesai_pelaksanaan` | 45/55 (81.8%) | **52/55 (94.5%)** | **+12.7pt** | Single event prioritization vs signature line |
| `penyelenggara_kegiatan` | 47/74 (63.5%) | **57/74 (77.0%)** | **+13.5pt** | DPKKA UNAIR, USU spacing, S-1 Akuntansi, IRIS casing |
| `nomor_bukti_fisik_nomor_sertifikasi` | 40/52 (76.9%) | **46/52 (88.5%)** | **+11.5pt** | Roman month repair (XII, XI), Poisson dot code, Hitech |
| `tingkat` | 62/74 (83.8%) | **66/74 (89.2%)** | **+5.4pt** | Contextual router 63/74 @ 100% + mapper fallback |
| **MACRO EXACT** | **285/384 (74.2%)** | **329/384 (85.7%)** | **+11.5pt** | **44 additional cells resolved correctly** |
| **MACRO FUZZY** | **310/384 (80.7%)** | **339/384 (88.3%)** | **+7.6pt** | **High overall semantic alignment** |

---

## 3. Detail Komponen & File Perubahan

### Backend Modules (Production Services)
1. `backend/app/services/combined_extractor.py`:
   - Penambahan `apply_combined_v3(extracted, raw_text)` yang mengorkestrasi komponen v6 (activity, organizer, nomor, dates, disambiguation router).
   - Mempertahankan backward compatibility untuk `apply_combined_v2`.
2. `backend/app/config.py`:
   - Penambahan setting `enable_combined_v3: bool = False` (default OFF, zero blast radius).
3. `backend/app/services/extraction_pipeline.py`:
   - Hooking `apply_combined_v3` di belakang flag `settings.enable_combined_v3` dengan prioritas di atas v2.

### Benchmark & Test Harness
1. `tests/benchmark_router_llm_v5.py`: Evaluasi router contextual disambiguation 5-fold CV.
2. `tests/benchmark_date_v2.py`: Evaluasi date extraction multi-day & ordinals.
3. `tests/benchmark_org_v6.py`: Evaluasi organizer canonicalization.
4. `tests/benchmark_akt6.py`: Evaluasi activity boundary & spacing.
5. `tests/benchmark_nomor_v3.py`: Evaluasi nomor roman repairs.
6. `tests/benchmark_combined_v3.py`: Evaluasi end-to-end composite staging.
7. `tests/test_combined_v3.py`: Unit test suite (75 total unit tests passing).

---

## 4. Status QA & Invarian

- `PYTHONPATH=. uv run pytest tests/ -v` $\to$ **75 passed** in 1.35s.
- `uv run python -m tests.benchmark_combined_v3` $\to$ **GATE PASS** (MACRO exact 85.7%, 0 regression).
- **Staging Invariant**: Flag `ENABLE_COMBINED_V3` default `False` sehingga alur produksi default tidak terganggu sebelum cutover resmi.

---

## 5. Frontier Terbuka Selanjutnya

1. **Aktivasi Produksi**: `ENABLE_COMBINED_V3=true` pada environment staging / produksi setelah persetujuan tim.
2. **Residual 11 Certs Unrouted Tingkat**: 11 sertifikat tersisa dapat diarahkan ke LLM fallback terfokus atau prompt tuning jika ingin mendorong akurasi tingkat menuju 95%+.
3. **Dokumentasi Laporan Resmi**: Memperbarui `report_data.json` dan laporan `.docx`/`.xlsx` bila diperlukan untuk publikasi tim.
