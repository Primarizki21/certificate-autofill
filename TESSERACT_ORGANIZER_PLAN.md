# Plan: Tesseract Layout-Resilient Organizer & Rule Normalizer (Branch ORG-TESS-V8)

## Status dan batas eksperimen

Eksperimen ini dijalankan sebagai `ORG-TESS-V8-001` dan hanya menyentuh artefak
staging di `tests/` serta dokumen eksperimen. Kode produksi di `backend/app/`
tidak diubah dan hasilnya tidak dipromosikan ke production tanpa persetujuan
eksplisit.

`tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/` dan
`tesseract_pure_all74_v4/` adalah baseline resmi. Keduanya tidak boleh
ditimpa.

## Hipotesis

Pada raw OCR Tesseract, organizer sering rusak karena:

1. frasa `diselenggarakan oleh` melewati tanggal yang memiliki spasi atau typo
   OCR, misalnya `pada tar ggal`;
2. dua kolom signer tergabung dalam satu baris, misalnya
   `DEKAN ... KETUARIMASADA`;
3. baris nomor sertifikat dengan prefix noise dianggap sebagai kandidat
   organizer;
4. OCR membuat typo satu karakter pada token organisasi.

Hipotesis hanya diterima bila kenaikan organizer terjadi tanpa regresi row-level
pada nomor dan tanggal, bukan hanya bila aggregate macro tetap melewati batas.

## Baseline dan gate

Evaluasi memakai GT v9 + matcher v2, dengan denominator eksplisit berikut:

| Corpus | Metrik | Baseline organizer | Baseline nomor | Baseline tanggal mulai | Baseline tanggal selesai |
|---|---|---:|---:|---:|---:|
| Pure All-74 | framework 5-field | 34/74 (45.95%) | 46/52 (88.46%) | 52/55 (94.55%) | 52/55 (94.55%) |
| Primary Hybrid All-74 | framework 5-field | 40/74 (54.05%) | 46/52 (88.46%) | 50/55 (90.91%) | 50/55 (90.91%) |
| Primary Scan-49 | framework 5-field | 25/49 (51.02%) | 29/33 (87.88%) | 34/35 (97.14%) | 34/35 (97.14%) |

Gate PASS wajib memenuhi seluruh syarat:

1. Pure All-74 organizer minimal **45/74 (60.81%)**.
2. Primary Hybrid All-74 organizer minimal **50/74 (67.57%)**.
3. Untuk setiap corpus, nomor dan kedua tanggal tidak boleh turun dari baseline.
4. Tidak ada row-level regression pada nomor atau tanggal yang sebelumnya exact.
5. Scan-49 tidak boleh mengalami regression pada field framework mana pun.
6. Full suite `uv run pytest tests/ -q` lulus.
7. Semua empat lapis pembuktian empiris selesai dan dilaporkan:
   - 5-fold CV + bootstrap CI;
   - OOD mutation + OCR noise injection;
   - audit semantic anchors dan anti-hardcoding;
   - confidence/safety-net audit.

Target macro 82% dihapus. Dengan scope hanya organizer, tambahan 10 sel dari
239/310 hanya menghasilkan sekitar 80.32% framework macro, sehingga target 82%
tidak konsisten secara matematis.

## Protokol B0–B11

### B0 — Dedup dan checkpoint

Pastikan `ORG-TESS-V8-001` belum ada di `docs/experiments_ledger.md`.
Catat baseline SHA dan status working tree. Working tree tidak harus bersih dari
file user yang tidak terkait; file tersebut tidak boleh disentuh.

### B1 — Gate sebelum coding

Tuliskan hipotesis, gate numerik, corpus, denominator, dan tujuan:
meningkatkan robustness organizer Tesseract dengan biaya OCR tambahan nol.

### B2 — Codegraph dan blast radius

Verifikasi call path:

```text
benchmark_tesseract_v4.cmd_eval
  → composite_v4_candidate.apply_composite_v4_candidate
      → organizer variant
```

Jangan mengasumsikan runner memanggil `extract_organizer_v2` secara langsung.

### B3 — Implementasi terisolasi

Buat `tests/organizer_tess_v8.py` dengan kontrak:

```python
def extract_organizer_v8(text: str) -> str | None:
    ...
```

Aturan wajib:

- boundary tanggal harus berbasis token tanggal valid, bukan `on` secara bebas;
- typo-spasi `pada tar ggal` harus didukung tanpa membuat closer terlalu greedy;
- signer stripping dan de-interleaving harus konservatif karena raw text tidak
  memiliki koordinat word-box;
- fuzzy matching hanya untuk lexicon organisasi yang eksplisit, dengan
  confidence/diagnostic yang membedakan hasil exact dan hasil repair;
- jangan menganggap transformasi semantik seperti `FSTUNAIR → BEM FST UNAIR`
  sebagai Levenshtein satu karakter;
- pembersihan nomor harus memvalidasi konteks baris, bukan menghapus semua
  kandidat yang kebetulan mengandung `angka/`.

Tidak ada engine marker berbasis komentar. Runner sudah membuang baris `#`; jika
engine diperlukan, kirim sebagai parameter eksplisit.

### B4 — Integrasi benchmark

Tambahkan `organizer_variant` pada
`apply_composite_v4_candidate(..., organizer_variant="v2")`.
Runner menambahkan opsi `--use-v8-organizer`, meneruskan varian ke composite,
dan menulis varian tersebut di `eval.json` serta report.

Baseline lama tetap menjadi default.

### B5 — Unit test

Buat `tests/test_organizer_tess_v8.py` dengan raw OCR fixture nyata dan negative
fixture:

- `Gelar Rasa`: signer merge `DEKAN FAK AS LMU KOMPUTER KETUARIMASADA`;
- `VENEDICT_panitia_karsa`: `pada tar ggal` dan footer signer;
- `1981676`: baris `\ 2 | 542/...` tidak menjadi organizer;
- organizer yang mengandung kata `on`, `ketua`, atau `direktur` tetapi tidak
  boleh terpotong;
- nomor line yang valid tidak boleh dibuang sebagai organizer secara keliru.

Uji expected value memakai matcher v2 dan juga assertion bahwa kandidat tidak
mengandung NIM/NIP/nomor.

### B6 — Trial terpisah dan gate

Jangan menimpa baseline. Gunakan output baru:

```bash
uv run python -m tests.benchmark_tesseract_v4 eval \
  --texts tests/benchmark_runs/ocr_experiment/tesseract_pure_all74_v4/extracted_texts \
  --out tests/benchmark_runs/ocr_experiment/tesseract_pure_all74_org_tess_v8 \
  --report docs/report/tesseract_pure_all74_org_tess_v8_report.md \
  --is-pure --use-v8-organizer

uv run python -m tests.benchmark_tesseract_v4 eval \
  --texts tests/benchmark_runs/ocr_experiment/tesseract_primary_v4/extracted_texts \
  --out tests/benchmark_runs/ocr_experiment/tesseract_primary_v4_org_tess_v8 \
  --report docs/report/tesseract_primary_v4_org_tess_v8_report.md \
  --use-v8-organizer
```

Trial memakai raw OCR yang sudah ada; tidak ada OCR tambahan dan tidak
menimpa file `extracted_texts` baseline.

### B7 — Full suite

Jalankan:

```bash
uv run pytest tests/ -q
```

Catat jumlah test yang ditemukan dan hasilnya, bukan angka tetap `136/136`.

### B8 — Empirical robustness

Jalankan validasi terpisah:

1. Stratified 5-fold CV per rule/repair, dengan min-fold precision 100% untuk
   rule yang firing dan bootstrap CI 1000 kali.
2. OOD mutation institusi/event serta noise OCR 10%, 25%, dan 50%.
3. Audit semantic anchors; tidak boleh ada hardcode judul event.
4. Audit `ExtractedValue`, confidence, dan `needs_review`; hasil fuzzy atau
   de-interleave tidak boleh diberi confidence exact.

Rule dengan frekuensi firing kurang dari 5 dilaporkan LOW-N dan tidak boleh
diklaim robust tanpa guard.

### B9 — Ledger dan laporan

Tambahkan `ORG-TESS-V8-001` ke ledger dengan:

- hipotesis dan gate;
- corpus serta denominator;
- per-field dan per-stem diff;
- hasil empat lapis pembuktian;
- latency dan OCR-call delta;
- verdict PASS/FAIL serta retry condition.

Buat report terpisah untuk Pure dan Primary. Jangan mengganti laporan baseline.

### B10 — Summary

Regenerate `docs/report/runs_summary.md` dan
`docs/report/runs_summary.csv`. Pastikan dua run baru muncul sebagai varian
terpisah.

### B11 — Commit dan rollback

Commit semua file eksperimen dan dokumentasi yang memang dibuat pada eksperimen,
baik PASS maupun FAIL, dengan pesan Conventional Commit. Jangan memakai
`git checkout` atau reset seluruh working tree.

Jika FAIL, kode eksperimen boleh tetap sebagai artefak terisolasi dan dicatat
di ledger. Rollback hanya dilakukan pada file eksperimen tersebut, tanpa
menyentuh file user yang tidak terkait.

## File dan kontrak kritis

1. `tests/organizer_tess_v8.py` — extractor baru.
2. `tests/composite_v4_candidate.py` — callsite organizer variant.
3. `tests/benchmark_tesseract_v4.py` — CLI, metadata, dan output evaluator.
4. `tests/test_organizer_tess_v8.py` — fixture dan negative tests.
5. `Ground_Truth_Sertifikat_v9.csv` dan `tests/matchers.py` — frozen evaluator.
6. Baseline `eval.json` Pure/Primary — read-only comparison source.

## Non-goal

Eksperimen ini tidak mengubah `backend/app/services/organizer_v2.py`, tidak
mengubah binary/gambar Tesseract, tidak menambah OCR pass, dan tidak
mempromosikan hasil ke production.
