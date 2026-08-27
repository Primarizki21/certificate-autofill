# Handoff v40 — Combined v2 Staging (Dummy Port) & Router Expansion v5 (ROUTER-005)

> Supersedes `docs/handoff_v39.md`. Sesi ini menyelesaikan penyatuan seluruh
> modul ekstraksi offline berkinerja tinggi (0 LLM) ke backend staging dan
> mengeksekusi ekspansi router tingkat 5-fold CV (ROUTER-005).

---

## 1. Ringkasan Eksekutif

| Eksperimen | Metode & Lingkup | Hasil Terukur | Verdict |
|---|---|---|---|
| **COMBINED-V2-001** | Penyatuan staging bundle 0 LLM di `app/services/combined_extractor.py` digate `ENABLE_COMBINED_V2=False` (default OFF): AKT-005 (activity), ORG-004 (organizer), PROD-002 (nomor), ROUTER-005 (tingkat). Evaluasi 74 certs vs GT v9 + matcher v2. | **MACRO exact 74.2% (+18.5pt vs prod baseline 55.7%)**, fuzzy 80.7%. nama_kegiatan 62.2%, organizer 63.5%, nomor 76.9%, tingkat 83.8%. QA fidelity 100% (0 mismatch vs ref). | **PASS — Staging bundle siap pakai (0 blast radius)** |
| **ROUTER-005** | Mining 24 unrouted certs dengan sinyal `organizer_v4` + `activity_v5`; validasi 5-fold CV precision 100%. 3 rule baru diterima: `hima_pure_internal` (+2), `iris_ftmm_bso` (+2), `bem_ftmm_internal` (+2). | **Coverage 50 → 56/74 (75.7%) @ 100.0% precision** (56/56 correct, 0 false positive di semua 5 fold). LLM fallback calls 24 → **18 calls (-25.0%)**. | **PASS — Coverage naik +6 certs @ 100% precision** |

---

## 2. Detail Komponen & Perubahan Arsitektur

### Backend Modules (Production Services)
1. `backend/app/services/activity_extractor.py` (baru):
   - Port resmi AKT-005 (`extract_activity(text: str) -> str | None`).
   - 17+ anchor patterns dengan pre/post camel OCR repairs dan context boundaries.
2. `backend/app/services/tingkat_router.py` (diperbarui):
   - Total 18 rules tervalidasi @ 100.0% precision pada 5-fold CV.
   - `route_tingkat(raw_text, organizer) -> str | None` & `route_tingkat_trace(...) -> tuple[str | None, str]`.
3. `backend/app/services/combined_extractor.py` (baru):
   - `apply_combined_v2(extracted, raw_text)` mengorkestrasi pipeline v2.
4. `backend/app/config.py`:
   - Penambahan parameter `enable_combined_v2: bool = False` (default OFF).
5. `backend/app/services/extraction_pipeline.py`:
   - Hooking `apply_combined_v2` di belakang flag `settings.enable_combined_v2`.
6. `backend/app/services/form_mapper.py`:
   - Mempertahankan `extracted["tingkat"]` bila sudah ter-route dengan confidence router.

### Test & Benchmark Suite
1. `tests/benchmark_combined_v2.py` (baru): Offline benchmark lengkap all-74 certs.
2. `tests/test_combined_v2.py` (baru): Unit test suite (config default, string isolation, router rules, form mapper).
3. `tests/router_mining_v5.py` (baru): Mining unrouted certs & 5-fold CV test harness.
4. `docs/report/router_expansion_v5.md` (baru): Laporan resmi per-rule 5-fold CV.

---

## 3. Analisis 18 Sertifikat Sisa Unrouted

18 sertifikat yang tersisa sengaja dioper ke LLM fallback karena memiliki ambiguitas konteks yang tidak aman dipaksa dengan regex:
- **Internasional (2 certs)**: `2954283` (Institut Français D’indonésie) & `FIT_Faiz` (Informatics Engineering Dept).
- **Ambiguous BEM Context (4 certs)**: `2398697` (BEM UNAIR - Job Prep -> Univ) vs `2398703` (BEM UNAIR - Nasional) vs `1952296` (BEM FKM - Fakultas) vs `1930354` (BEM FEB - Nasional).
- **Lomba Tanpa Penyelenggara (3 certs)**: `Primarizki_kim_unair_2024` (KIM internal -> Univ) vs `Data Slayer 2.0` (Nasional) vs `BTF_Faiz` (Nasional).
- **External Partner / Program (9 certs)**: `AIESEC`, `Literasi Psikologi`, `ACIC`, `Hology 7.0`, `Gelar Rasa`, `BINARY`, `hakim_lomba`, `AQEEL_Seminar`, `Sertif_ppkmb_univ_peserta`.

---

## 4. Verifikasi & Status QA

- `PYTHONPATH=. uv run pytest` -> **69 passed** in 0.77s.
- `uv run python -m tests.benchmark_combined_v2` -> **GATE PASS** (MACRO exact 74.2%, 0 mismatch).
- `uv run python -m tests.router_mining_v5` -> **GATE PASS** (56/56 @ 100.0% precision on 5-fold CV).

---

## 5. Frontier Terbuka Selanjutnya

1. **Aktivasi Produksi**: `ENABLE_COMBINED_V2=true` di environment produksi setelah evaluasi staging disetujui.
2. **LLM Fallback untuk 18 Sertifikat Sisa**: Menjalankan evaluasi online / prompt tuning khusus untuk 18 sertifikat ambiguous ini untuk mencapai akurasi MACRO end-to-end >85%.
3. **Eksplorasi Ekstraksi Tanggal**: Meningkatkan akurasi `waktu_mulai_pelaksanaan` / `waktu_selesai_pelaksanaan` (saat ini 81.8% exact).
