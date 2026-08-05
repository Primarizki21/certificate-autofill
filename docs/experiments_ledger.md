# Experiments Ledger — Closed & Failed Approaches

> **Tujuan:** mencegah agent mengulang pendekatan yang sudah gagal. Cek SEBELUM
> mulai eksperimen (step B0 workflow). Tambahkan entri di SETIAP akhir eksperimen
> (PASS atau FAIL).
>
> **Project goals:** efisien · robust · cepat · hemat token (cost/budget) ·
> scalable ke produksi.
>
> Jika sebuah hipotesis ada di sini, JANGAN dicoba ulang kecuali
> "re-try condition"-nya terpenuhi.

---

## Entries

| ID | Hipotesis | Hasil | Verdict | Re-try condition |
|---|---|---|---|---|
| **OCR-001** | PaddleOCR 3.7 / paddlepaddle 3.3 (PP-OCRv6, CPU) baca nomor lebih baik | 3.8GB RSS/cert, ~50s/cert, >6GB VA saat init → OOM di WSL 8GB. Kualitas teks bagus tapi tak bisa dipakai. | CLOSED — tidak viable | Hanya di GPU (VRAM offload) atau host ≥16GB RAM; revisit kalau produksi pindah dari WSL |
| **OCR-002** | paddleocr 2.9 + paddlepaddle 2.6 (CPU, stack stabil lama) lebih ringan & akurat | Korpus 74/74 ok, 7.1s/cert. Scan: organizer 18.4% (naik) tapi nomor **39.4%** (regresi vs 57.6 baseline), MACRO 39.8%. | CLOSED — gate FAIL (nomor) | Hanya kalau field-extractor diperbaiki menangani segmentasi paddle yang berbeda |
| **OCR-003** | EasyOCR CPU (max-side 960) — downscale biar cepat | 12.7s/cert. Scan: organizer **20.4%** (terbaik) tapi nomor **15.2%** (downscale merusak digit), MACRO 34.3%. | CLOSED — gate FAIL (nomor/dates) | Tidak ada di CPU @960; full-res 53s terlalu lambat |
| **OCR-004** | EasyOCR GPU (full-res) — VRAM offload + cepat | 9.7s/cert. Scan: organizer 16.3%, nomor **33.3%**, MACRO 39.3%. Bukan hasil terbaik. | CLOSED — tidak diadopsi (prioritas user = CPU) | Hanya kalau GPU jadi prioritas ATAU baseline nomor regresi |
| **LLM-001** | Prompt `g_evidence` (minta bukti singkat sebelum jawaban) | Tingkat turun (75.7% vs f_bias 82.4%). | CLOSED — regresi (v8 P3) | Perlu struktur output yang lebih ketat; replay setelah LLM lebih mampu follow structured format |
| **LLM-002** | Layout representation (markdown/annotation) dimasukkan ke prompt | Tingkat 77.0%/78.4% (< f_bias 82.4%); OCR-bound (25/74 berteks embedded). | CLOSED — ditolak (v8 P4) | Hanya kalau OCR kualitas naik drastis |
| **LLM-003** | Per-field LLM (A1) / full-text (A2 v2) untuk semua field | A1: tingkat 47.3%, 834 tok/cert, 125 calls. A2: MACRO 58.3% tapi tingkat 36.5%, 834 tok. | CLOSED — superseded oleh tingkat-only hybrid | Sudah digantikan pipeline v7/v8 (router + tingkat-only); tetap jadi referensi MACRO tinggi |

---

## Aturan Pengisian

1. **Satu baris per pendekatan tertutup** (engine, prompt variant, strategi).
2. Kolom `Hasil` = angka terukur (jangan opini).
3. Kolom `Re-try condition` = kondisi eksplisit yang membuat pendekatan layak
   dicoba ulang. Jika tidak ada, tulis "tidak ada".
4. Commit bersama kode eksperimen & update `runs_summary.md` (workflow B9-B11).
5. Referensi detail: `docs/handoff_v10.md` + `docs/report/runs_summary.md`.

## Hubungan dengan dokumen lain

- `handoff_v10.md` = **open frontier** (baseline + hipotesis terbuka).
- `runs_summary.md` = **angka terukur** (semua run).
- `experiments_ledger.md` (ini) = **closed list** (yang sudah dicoba & ditutup).
