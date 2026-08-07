# Laporan Eksperimen — Certificate Autofill

Kumpulan laporan eksperimen ekstraksi sertifikat. Format `.docx` adalah sumber
presentasi yang mudah dibaca manusia; setiap `.docx` punya pasangan `.md` yang
disinkronkan agar agen dapat membaca isinya tanpa tool khusus.

## Isi

| File | Konten | Pembaca utama |
|------|--------|---------------|
| `benchmark_methods.{docx,md}` | Deskripsi tiap metode ekstraksi (regex, NER, hybrid, LLM v1–v8) | Tim + agen |
| `evaluation_methodology.{docx,md}` | Metrik, formula, dataset, batasan evaluasi | Tim + agen |
| `phase_v4_methodology.{docx,md}` | Narasi eksperimen fase v4 + addendum v7/v8 | Tim + agen |
| `results_comparison.xlsx` | Perbandingan semua eksperimen (warna arah delta: naik=turun accuracy, cost) + per-file | Tim |
| `raw_vs_pipeline.xlsx` | 74 sertifikat: teks mentah + field pipeline vs GT (hijau/kuning/merah) | Tim |
| `raw_vs_pipeline_examples.docx` | 5 contoh terkurasi + annotasi tahap pipeline | Tim + mentor |
| `mentor_presentation_notes.md` | Catatan presentasi mentor (LLM vs router + robustness) | Tim |
| `runs_summary.{md,csv}` | Registry semua benchmark run + angka otoritatif (auto-generated `scripts/generate_runs_summary.py`) | Agen + tim |

## Konvensi Sinkronisasi

- `.docx`/`.xlsx` adalah **sumber visual**. `.md` adalah **mirror teks** untuk
  agen — bukan dokumen terpisah yang boleh divergen.
- **Semua dokumen dihasilkan ulang penuh oleh generator** (bukan append):
  - Sumber data: `report_data.json` (meta, `experiments[]`, document blocks).
  - `uv run python scripts/generate_report.py` → `benchmark_methods`,
    `evaluation_methodology`, `phase_v4_methodology`, `phase_v4_results_summary`
    (docx + md + xlsx) — docx & md sinkron by construction.
- **Eksperimen baru:** tambah 1 entri ke `experiments[]` di `report_data.json`
  (baca angka dari run dir), lalu jalankan generator. Eksperimen otomatis masuk
  ke seksi/tabel yang benar (comparison, progression, results).
- Validasi: buka ulang `.docx`, render ke PDF untuk cek tabel/overflow.

## Alur Referensi

- Status eksperimen & langkah berikutnya: `docs/handoff_v9.md`
- Checklist perbaikan: `docs/improvements.md`
- Hasil mentah benchmark: `tests/benchmark_runs/` (gitignored, lokal)
- Ground truth: `Ground_Truth_Sertifikat.csv` (raw) + varian versi di `docs/`/`tests/`
