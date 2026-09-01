# Handoff v45 — Cabang Eksperimen B1–B8: Penguatan, Validasi Empiris & Kandidat Komposit

> Supersedes `docs/handoff_v44.md`. Sesi ini mengeksekusi plan `CABANG_B1_B8_PLAN.md`
> (8 cabang eksperimen terisolasi di `tests/`, produksi `backend/app/` TIDAK disentuh)
> dengan protokol penuh (B0–B11). Ringkasan verdict per cabang:

| Cabang | Tujuan | Verdict | Inti |
|---|---|---|---|
| B1 | Fast semantic anchor high-DPI crop | **FAIL** (3/3 gate) | Anchor 1.5x regress nomor 54.5% < baseline 60.6%; downscale tidak memangkas RapidOCR (floor ~3-6s) |
| B2 | OOD probe v4.2 | **FAIL raw** (nuanced) | Mutation free-inst +7.4pt (76% kontaminasi GT; real ≈1.9pt); noise 25/50% extra fragility di nomor+kegiatan |
| B3 | Kalibrasi confidence review | **FAIL** | Cert recall 100% tapi false alarm 90% & nomor recall 25% (gate plan saling bertentangan) |
| B4 | Hardening router disambig | **PASS** | 18 adversarial test, 5-fold min-fold precision 100%, coverage 64/74 |
| B5 | Activity structural anchors anti-bleed | **PASS** | 79.7% exact zero-regress, fuzzy 85.1%, 11 unit 0 bleed |
| B6 | Nomor preservasi digit + guard Roman | **PASS** | 92.3% exact zero-regress, 13 unit invariant panjang digit |
| B7 | De-corpusing audit | **PASS** | 18 literal terinventarisasi; Pure Semantic 79.4% (assist +8.6pt; nomor literal gratis) |
| B8 | Composite candidate | **FAIL gate akurasi** | Composite == v4.2 (76.13% all-cells / 87.42% framework, zero-regression); komponen protective |

---

## 1. Ringkasan Eksekutif

Plan B1–B8 mengasumsikan 9 kelemahan konkret hasil audit QA v4.2 yang
"korpus-visible" (bleed, DPKKA corruption, Roman overcorrection, substring
router). Eksekusi membuktikan: **seluruh kelemahan itu nyata di level kode,
TAPI 0 di antaranya mengeksekusi pada korpus 74 saat ini** — kasus audit QA
adalah OOD/sintetik. Konsekuensi:

- B4/B5/B6 **PASS** sebagai pengerasan protective (0 perubahan nilai corpus,
  zero-regression), memperbaiki celah yang akan menggigit di data baru.
- B8 composite **gagal gate akurasi plan** (≥78.0%/≥89.0%) karena komponen
  protective tidak mengubah akurasi corpus; composite == v4.2 secara numerik.
- B1 **refuted empiris**: hipotesis "fast anchor" untuk scan tidak bisa
  dipenuhi oleh downscale OCR; text-search 0% berguna di scan.
- B2/B3 mengungkap trade-off desain yang TIDAK tercakup plan (kontaminasi GT
  di mutation; false alarm vs recall di safety net).

## 2. Tabel Komparasi

| Metrik | v9 offline | v4.2 staging | Composite B8 | B8 gate | Status |
|---|:---:|:---:|:---:|:---:|:---:|
| MACRO exact all-cells (444 sel) | 46.17% | 76.13% | 76.13% | >= 78.0% | FAIL |
| Framework exact (310 sel, sans tingkat) | — | 87.42% | 87.42% | >= 89.0% | FAIL |
| Zero regression per field vs v4.2 | — | — | ✓ | wajib | PASS |
| Pure Semantic MACRO (tanpa literal, B7) | — | — | 79.4% | acuan OOD | — |

Per-field composite == v4.2: kegiatan 59/74, dates 53/55, organizer 58/74,
nomor 48/52, tingkat 67/74.

## 3. File yang Diubah/Dibuat

- `tests/ocr_high_dpi_anchor.py` (B1) — `resolve_number_bbox_fast` (text-search → RapidOCR 1.5x fallback, word-level line grouping).
- `tests/benchmark_b1_high_dpi.py` (B1) — 3+1 varian scan-49, eval resmi harness.
- `tests/ood_probe_v4_2.py` (B2) — probe mutation+noise + diagnosis kontaminasi.
- `tests/calibrated_confidence_v4_2.py` (B3) — kalibrasi confidence per pola.
- `tests/benchmark_review_v4_2.py` (B3) — recall/precision/false-alarm review.
- `tests/router_disambig_v7.py` (B4) — 8 rule hardened + `route_with_disambiguation_v7`.
- `tests/test_router_disambig_hardening.py` (B4) — 18 unit adversarial.
- `tests/stat_validation_disambig.py` (B4) — 5-fold CV per rule.
- `tests/activity_extractor_v9.py` (B5) — structural anchors anti-bleed + anti-bleed cut v7 tier.
- `tests/test_structural_act_robustness.py` (B5) — 11 unit.
- `tests/benchmark_activity_v9.py` (B5) — benchmark + value-diff.
- `tests/nomor_normalizer_v6.py` (B6) — DPKKA length-preserving + guard Roman gated.
- `tests/test_nomor_v6.py` (B6) — 13 unit invariant.
- `tests/benchmark_nomor_v6.py` (B6) — benchmark.
- `tests/decorpusing_audit.py` (B7) — inventarisasi + ablasi Mode A/B.
- `tests/composite_v4_candidate.py` (B8) — `apply_composite_v4_candidate`.
- `tests/benchmark_composite_v4_candidate.py` (B8) — 3 arah + OOD curve + 4 lapis.
- Docs: `docs/report/b1_high_dpi_anchor_report.md` (via eval.json), `b2_ood_v4_2_report.md`, `b3_calibrated_confidence_report.md`, `b4_router_hardening_report.md`, `b5_structural_activity_report.md`, `b6_nomor_normalizer_report.md`, `decorpusing_catalog.md`, `composite_v4_candidate_report.md`, `docs/experiments_ledger.md` (8 entri), `docs/report/runs_summary.md` (regenerated).

## 4. Empat Lapis Pembuktian Empiris (B8)

1. **5-Fold CV** (B4): min-fold precision 100.0% semua rule firing, coverage 64/74, 18 unit adversarial.
2. **OOD Composite**: mutation free-inst drop +7.4pt (16/21 sel = kontaminasi GT), noise 10% +7.6pt / 25% +12.2pt / 50% +27.9pt — identik v4.2 (komponen protective tidak mengubah kurva).
3. **Anti-Hardcoding**: katalog 18 literal (B7); Pure Semantic 79.4%; nomor literal assist 0 (lepas gratis).
4. **Safety Net**: B3 FAIL (cert recall 100% / false alarm 90% / nomor recall 25%) → tidak masuk composite; flag review B6 (0.78 utk nomor repaired) tetap aktif.

## 5. Flaw Plan yang Ditemukan Saat Eksekusi

1. **B1 aritmetika**: gate "60.6% (19/33)" tidak konsisten — 19/33 = 57.6%; 60.6% = 20/33.
2. **B1 premis**: scan = tanpa text layer → `search_for` 0% berguna; downscale 1.5x tidak menurunkan biaya RapidOCR (diukur 4.3–6.7s kedua zoom).
3. **B2 premis salah**: handoff v44 Lapis 2 sudah klaim OOD stabil (via `ood_probe.py` atas v9); probe v4.2 = refinement, bukan pertama kali.
4. **B4/B5/B6 file target tidak ada** di `tests/` (router_disambig_v7/activity_extractor_v9/nomor_normalizer_v6) — harus dibuat sebagai salinan terisolasi; produksi tidak disentuh (sesuai Assumption 3 plan).
5. **B3 gate saling bertentangan**: literal→0.55 menjamin false alarm >20%; error nomor invisible terhadap confidence pola (recall 25% vs gate 88%).
6. **B6 gate zero-regression vs unit invariant konflik**: korpus punya 1 cert (2160238) di mana "1"→"I" benar (DPKKA) — diselesaikan dgn `dpkka_ctx` (konversi di konteks DPKKA, guard di format lain).
7. **B5 anti-bleed cap 120 char merusak nilai sah korpus** ("Kepengurusan Himpunan...Universitas Airlangga" ~135 char) — cap longgar (200) di tier v7, ketat tetap di structural.
8. **B8 gate akurasi tidak achievable**: komponen protective 0 perubahan nilai corpus; target +1.2pt mengasumsikan bug korpus-visible yang tidak ada.

## 6. Open Frontier

1. **Anchor crop yang benar-benar murah**: reuse word-boxes dari primary OCR pass (0 OCR tambahan) — perubahan arsitektur produksi (retain boxes di `ocr_fallback.py`), bukan eksperimen.
2. **De-corpusing organizer** (B7): literal organizer = +31.1pt — butuh pengganti semantic (alias data-driven dari KB/GT) sebelum produksi; nomor literal (270/GIRI) dapat dilepas gratis.
3. **Roman overcorrection produksi**: v3/v5 masih mengubah "1"→"I"; B6 v6 siap dipromosikan (menunggu user).
4. **B3 safety net** (jika direvisi): confidence berbasis OCR disagreement / precision-aware threshold; trade-off recall↔false-alarm perlu keputusan user.
5. **B2 fragility v4.2**: hardcoded event ber-token institusi (KARSA FTMM, SPECTA) rapuh di mutation — target de-corpusing.
6. **Promosi composite**: B4+B5+B6 bundle (0 perubahan corpus, protective) layak staging `ENABLE_COMBINED_V5` bila user setuju — tanpa klaim akurasi tambahan.

## 7. Supersession

Supersedes `docs/handoff_v44.md`. Baseline evaluasi tetap: GT v9 + matcher v2 + Combined v4.2 staging (flag OFF).
