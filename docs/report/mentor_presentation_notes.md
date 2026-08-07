# Catatan Presentasi Mentor — Pipeline v9

> Ringkasan siap-pakai untuk sesi mentoring. Angka otoritatif: handoff v17 +
> `docs/report/runs_summary.md` + `docs/experiments_ledger.md`.

## 1. Apa yang diekstrak

Sistem membaca PDF sertifikat kegiatan mahasiswa (Universitas Airlangga, 74
sertifikat) dan mengisi form Kartu Hasil Prestasi (KHP): **nama kegiatan,
tanggal mulai/selesai, penyelenggara, nomor sertifikat, tingkat**. Dievaluasi
terhadap Ground Truth yang diaudit manual (GT v9) dengan matcher v2 (exact +
fuzzy, anti false-positive).

## 2. Sejarah singkat (semua angka terukur)

| Fase | Metode | MACRO exact | LLM calls | Inti |
|---|---|---|---|---|
| v2 | Regex | 42.2% | 0 | regex murni |
| v2 | NER pre-trained | 12.8% | 0 | gagal |
| v3 | Hybrid NER+regex+PP | 48.1% | 0 | gabungan |
| v4 | LLM A1 per-field | 49.0% | 125 | LLM semua field |
| v4 | LLM A2 full-text | 58.3% | 74 | LLM teks utuh |
| v7 | Router rule-based | 54.2% | 39 | **titik balik** |
| v8 | f_bias + router | 55.2% | 35 | prompt + router |
| **v9** | **organizer_v2 + router** | **60.2%** | **29** | **terbaik** |

## 3. Jawaban kunci: LLM atau rule-based router?

**Jawaban: didominasi komponen rule-based. LLM hanya fallback kecil.**

Bukti terukur:

1. **LLM hanya untuk 1 field (`tingkat`), hanya untuk sertifikat yang router
   tidak bisa putuskan.** Router memutuskan 45/74 @ **100% precision** — itu
   tidak pernah menyentuh LLM. LLM hanya melihat 29/74 kasus ambigu.
2. **Kontribusi:** dari 62 keputusan `tingkat` yang benar, router menyuplai
   **45 (72.6%)** tanpa token sama sekali; LLM menyuplai 17/29 (58.6%) pada
   kasus tersisa. LLM = safety net, bukan mesin.
3. **Lompatan v8→v9 berasal dari modul rule-based:** `organizer_v2` (regex +
   normalisasi akronim, tanpa LLM) → organizer exact naik 16.2%→33.8%.
4. **Bukti paling kuat:** akurasi **naik** sementara penggunaan LLM **turun**
   (calls 39→35→29, token 202→214→176). Kalau LLM penyebabnya, memakainya
   lebih sedikit tidak mungkin membuatnya lebih baik. Yang membaik adalah rules.

## 4. Apa peran LLM sebenarnya?

- Model: llama3.1:8b lokal (Ollama), prompt f_bias, temperature 0.
- Memutuskan `tingkat` HANYA untuk kasus yang lolos router (ambigu).
- Dipakai hemat: 176 token efektif/sertifikat, 29 calls untuk 74 sertifikat.
- Produksi bisa berjalan **deterministik tanpa LLM** (flag `ENABLE_LLM_TINGKAT=false`).

## 5. Seberapa robust?

**Robust dalam domain:**
- Router deterministik @100% precision — auditable, zero-cost, reproducible.
- Per-field confidence + flag `needs_review` (threshold <0.80) → human-in-the-loop.
- Metrologi disiplin: GT v9 + matcher v2, no-regress di setiap eksperimen.

**Keterbatasan yang jujur:**
- Dataset kecil (74), satu universitas, template-heavy. 13 rule router
  diturunkan dari korpus ini → **generalization ke kampus/format lain belum
  teruji** (perlu re-validasi rule).
- Bottleneck nyata = **OCR, bukan LLM**: sertifikat scan turun ke MACRO 47.3%
  di produksi vs 60.2% pada teks utuh. `nama_kegiatan` hanya 25.7% exact
  (field tersulit, tidak dipegang LLM).
- Angka 60.2% (benchmark) ≠ angka produksi (deterministik): 60.2% termasuk
  LLM fallback; default produksi lebih murah dan lebih rendah.

## 6. Garis eksperimen yang ditutup (agar mentor tahu ini bukan asal-coba)

- NER pre-trained: gagal (12.8%).
- LLM untuk semua field (A1/A2): token mahal, tingkat jelek → diganti
  tingkat-only hybrid.
- OCR: PaddleOCR/EasyOCR/DocTR gagal baca nomor scan; DocTR layak hanya
  sebagai hybrid per-field; 2-pass nomor (NC-001) +3pt tapi cost +2-10s/cert
  → flag OFF.
- Multi-field LLM (Exp5): melewati gate token → ditutup.

## 7. Artefak presentasi

| File | Isi |
|---|---|
| `results_comparison.xlsx` | Perbandingan semua eksperimen, warna arah delta (accuracy naik=hijau, cost turun=hijau), winner row |
| `raw_vs_pipeline.xlsx` | 74 sertifikat: teks mentah + field pipeline vs GT (EXACT hijau / FUZZY kuning / WRONG merah) |
| `raw_vs_pipeline_examples.docx` | 5 contoh terkurasi + annotasi tahap pipeline (router, LLM fallback, organizer, OCR, field gagal) |
| `pipeline_best.docx` | Deskripsi pipeline v9 lengkap |
