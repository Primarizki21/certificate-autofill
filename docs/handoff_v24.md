# Handoff v24 — OOD-003: re-run OOD probe v3 dengan R6 — R6 KEEP (0 kerapuhan), rekomendasi port final

> Supersedes `docs/handoff_v23.md`. Sesi ini = re-run OOD probe v3 untuk R6
> (frontier #2 v23) atas keputusan user. Verdict probe apa adanya (user setuju
> sebelum eksekusi). Produksi tetap zero-touch; commit saja (user yang push).

---

## Hasil sesi (committed: `84301bc` + commit baru)

| Langkah | Hasil | Verdict |
|---|---|---|
| 1. Edit `tests/ood_probe_v3.py` | `RULE_ORDER` + `"R6"` (ablation & noise survival kini mencakup R6; sumbu 1+2 sudah otomatis via `offline_v3`); referensi benchmark di `render_md`: ORG-003 45.9% → F1C-001 54.1% | DONE |
| 2. Run `ood_probe_v3_20260810_161809` | **R6 = KEEP tanpa catatan GUARD**: fix 6, regress 0, survival 100% di noise 10%, **0 fix mati di semua kondisi**. Mutation: drop organizer v3 21.6% vs v9 16.2% = 100% kontaminasi GT (4 cert). Noise: extra drop vs v9 identik OOD-002 | FAIL (gate drop-relatif) — struktur kerapuhan sama dengan OOD-002, R6 menambah 0 |
| 3. Interpretasi `render_md` diperbarui | Blok hardcoded OOD-002 diganti angka baru + baris R6; run dir 161707 (interpretasi lama) dihapus | DONE |
| 4. Registry | `runs_summary.md` + `.csv`: ood_probe_v3 → 161809 (61.2%), organizer_v3 → 160232 (61.2%) | DONE |
| 5. Pytest + ledger | pytest 31 passed. Ledger: **OOD-003** | DONE |

---

## Temuan penting sesi ini

1. **R6 (F1C-001) = KEEP tanpa GUARD** — kontra-intuitif (teks-bergantung
   ternyata robust): compact-equality baris tahan char-confusion, typo map OCR
   menangani merge, join beruntun tak bergantung spasi. 6 fix-cert ≥ 3 =
   satu-satunya aturan dengan cukup data untuk klaim robust di level korpus.
2. **Extra drop noise vs v9 IDENTIK OOD-002** (10% +1.4 / 25% +1.3 / 50%
   +4.1pt) — semua kerapuhan = aturan lama (R4 sejak 10%, R1 sejak 25%, matcher
   digit S1→SI di 50%). R6 menambah 0 kerapuhan.
3. **Rekomendasi port produksi FINAL** (menunggu keputusan user):
   - KEEP: R0, R2, PREFIX_HELD, **R6**
   - GUARD (wajib needs_review F6): R1, R4
   - HAPUS: R3 (NO_FIX), R5 (DEAD)
4. Gain absolut v3 tetap positif di semua kondisi OOD (noise 50%: organizer
   41.9% vs v9 29.7%).
5. `report_data.json`/xlsx TIDAK disentuh (keputusan user dari v23 tetap).

---

## Frontier berikutnya (urutan saran) — menunggu keputusan user

1. **Port produksi v3+R6** — per-aturan final di atas. **Butuh keputusan user**
   (produksi zero-touch).
2. **Scoring organizer_v2** — 2160238 + `salah_org`/`kosong` (12 kasus; 2160238
   = org spesifik ada di teks tapi kalah skor oleh "Universitas Airlangga").
   Menyentuh produksi. **Butuh keputusan user.**
3. **Matcher v2.1 / normalisasi alias** — bucket `format` (12 kasus). **Butuh
   keputusan user** (a) pipeline-side vs (b) matcher v2.1 + re-baseline.
4. **F3 lanjutan** — sampling data riil unique organizer. **Butuh data baru.**

## Frontier tertunda (sama dengan v23)

- F4 fingerprint dedup, F5 distillation, F7 infra OCR queue (produksi),
  Eksperimen A (LLM per-field — TIDAK, F1 v3+R6 PASS).

---

## Pekerjaan user / jangan lakukan

- `pipeline_best.docx` diedit manual — JANGAN jalankan `generate_pipeline_doc.py`
- Jangan ubah `Ground_Truth_Sertifikat_v8.csv` / raw `Ground_Truth_Sertifikat.csv`
- Benchmark WAJIB `GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv`
- Jangan sentuh `backend/` tanpa keputusan user (eksperimen tetap di `tests/`)
- Jangan push — commit saja; user yang push (SSH passphrase)
- Jangan re-run closed: EXP5-001, OCR-001..006, LLM-001..003, ROUTER-001, NC-001/002
- Pytest: `uv run python -m pytest tests/ -q` (31 passed)
- `results_comparison.xlsx` tidak di-commit — regenerate lokal bila perlu
- `report_data.json` belum berisi F1C/OOD-003 — keputusan user apakah masuk laporan resmi

## Key Files

| File | Peran |
|---|---|
| `tests/ood_probe_v3.py` | OOD probe v3 — kini mencakup **R6** (RULE_ORDER + interpretasi baru) |
| `tests/benchmark_organizer_v3.py` | Lapisan organizer v3 + R6 enrich (R0-R6) |
| `docs/report/ood_probe_v3.md` | Report OOD-003 (verdict FAIL, R6 = KEEP, rekomendasi port final) |
| `docs/report/runs_summary.md` (+`.csv`) | Registry (ood_probe_v3_161809, organizer_v3_160232, keduanya 61.2%) |
| `docs/experiments_ledger.md` | **OOD-003** + F1C-001 + OOD-002 + ORG-003 |
| `docs/handoff_v23.md` | Sesi sebelumnya (F1C-001) |
