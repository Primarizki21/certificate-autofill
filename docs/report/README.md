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
| `phase_v4_results_summary.{md,xlsx}` | Ringkasan numerik hasil benchmark + per-file | Tim |

## Konvensi Sinkronisasi

- `.docx`/`.xlsx` adalah **sumber visual**. `.md` adalah **mirror teks** untuk
  agen — bukan dokumen terpisah yang boleh divergen.
- Setiap pembaruan `.docx` harus diikuti regenerasi `.md` pasangannya.
- Validasi: buka ulang `.docx` (bukan hanya patch XML), render ke PDF untuk cek
  tabel/overflow, lalu bandingkan paragraf & tabel dengan `.md`.

## Alur Referensi

- Status eksperimen & langkah berikutnya: `docs/handoff_v8.md`
- Checklist perbaikan: `docs/improvements.md`
- Hasil mentah benchmark: `tests/benchmark_runs/` (gitignored, lokal)
- Ground truth: `Ground_Truth_Sertifikat.csv` (raw) + varian versi di `docs/`/`tests/`
