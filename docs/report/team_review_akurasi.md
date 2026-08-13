# Review Tim — KB (knowledge base) & Jalur Akurasi Organizer

> Ringkasan internal. Detail teknis: `docs/experiments_ledger.md` (KB-001..006,
> ORG-004, ORG-005), `docs/kb_history.md` (Verdict Final KB),
> `docs/report/f1_organizer_format.md` (ORG-004). Semua angka: 74 sertifikat,
> GT v9 + matcher v2, tanpa LLM/OCR tambahan.

---

## TL;DR (3 kalimat)

1. **KB (buku catatan jawaban tingkat) sudah selesai dieksperimenkan dan aman,
   tapi tidak terbukti menghemat AI** karena data yang ada hanya 74 sertifikat
   dan hanya 3 di antaranya yang berulang — KB baru terlihat manfaatnya saat
   ada data bervolume besar.
2. **KB bukan alat akurasi** — ia hanya mengganti sumber jawaban (AI → catatan),
   isi jawabannya sama. Jadi exact/fuzzy tidak berubah karena KB.
3. **Kabar baik: jalur akurasi TANPA AI justru mencatat kenaikan terbesar** —
   organisasi penyelenggara naik dari 39.2% → **66.2%** (berkat normalisasi
   nama + perbaikan format), MACRO 58.3% → **63.5%**, biaya AI tetap nol.

---

## 1. Eksperimen KB (sudah selesai — Verdict Final)

**Apa itu KB:** buku catatan yang menyimpan jawaban "tingkat kegiatan"
(Internasional/Nasional/Universitas/Fakultas/Departemen) untuk kombinasi
(penyelenggara + peran). Tujuannya: kalau sertifikat baru sudah pernah dilihat
sebelumnya, jawab langsung dari catatan tanpa tanya AI.

**Hasil 6 eksperimen (semua lulus uji keamanan):**

| Eksperimen | Inti | Hasil |
|---|---|---|
| KB-001 shadow | KB berjalan di samping pipeline, tidak mengubah hasil | 0 salah, 0 konflik, aman diuji noise OCR 10–50% |
| KB-002 persist | Catatan tersimpan ke file, dimuat ulang hasilnya identik | Persistence identik |
| KB-003 normalisasi key | Penamaan penyelenggara diseragamkan | Kecocokan naik 3 → 5 hit |
| KB-004 alat audit | Instrumen untuk mengukur kesiapan produksi | Selfcheck lulus |
| KB-005 event type | Jenis kegiatan dipakai sebagai kunci tambahan? | **Tidak perlu** — peran (role) sudah cukup & paling aman |
| KB-006 alias mining | Menemukan penulisan ganda penyelenggara otomatis | 100% presisi, sama dengan daftar manual |

**Kenapa tidak dipakai produksi:**
- **Penghematan AI tidak terukur**: di 74 sertifikat, semua sertifikat berulang
  kebetulan sudah dijawab aturan internal, jadi KB tidak pernah menyelamatkan
  pemanggilan AI (saved = 0). Manfaat KB baru muncul saat data besar (puluhan
  ribu sertifikat) dengan penyelenggara yang berulang.
- **Data tidak mungkin bertambah** (korpus 74 adalah semua yang ada), jadi
  pembuktian ini tidak akan tercapai dalam kondisi sekarang.

**Kesimpulan tim:** KB selesai sebagai eksperimen, aman, alatnya siap
(`audit.py`, `alias.py`). Dibuka lagi hanya bila data baru tersedia.

## 2. Jalur akurasi TANPA AI (yang sedang naik)

Fokus bergeser ke perbaikan nama penyelenggara (organizer) — field terlemah
pipeline. Semua aturan **umum** (berlaku untuk sertifikat baru), bukan
hardcode per dokumen:

| Langkah | Perbaikan | Organizer exact |
|---|---|---|
| Baseline F1 | Pipeline awal | 39.2% |
| ORG-003 (v3) | Buang sampah prefix/suffix ("Which Held From…", "Library Class", tanggal) | 45.9% |
| F1C-001 (R6) | Lengkapi nama pendek dari konteks teks (Himasada → Himasada, Fakultas Ilmu Komputer) | 54.1% |
| **ORG-004 (format)** | **Perbaiki penulisan/cetak miring OCR (INFORMATION SYSTEMS DEPT → Information System Dept., STUDISL → Studi S1, UB → Brawijaya University, dll)** | **66.2%** |

**ORG-004 detail (eksperimen terbaru, GATE PASS):**
- Organizer exact **54.1% → 66.2%** (+12.1pt, 9 sertifikat diperbaiki).
- Semua field lain tidak turun; MACRO **61.2% → 63.5%**.
- Uji ketahanan (mutasi template + noise OCR 10/25/50%): tidak menambah
  kerapuhan vs lapisan sebelumnya.
- 0 pemanggilan AI.

## 3. Yang TIDAK bisa diperbaiki (dan kenapa)

- **Scoring pemilihan penyelenggara (12 sertifikat tersisa)**: pipeline salah
  menangkap penyelenggara (mis. menangkap fakultas padahal GT ingin BEM).
  Percobaan perbaikan menunjukkan risiko regresi tinggi (1 percobaan merusak
  12 sertifikat lain). Butuh data baru atau keputusan rewrite besar.
- **Inkonsistensi data acuan (GT v9)**: nama "Fakultas Matematika dan Ilmu
  Pengetahuan Alam" kadang ditulis dengan "dan" (2954933) kadang tanpa
  (ACTION); "Himatesda" kadang pendek kadang panjang. Aturan yang mengikuti
  salah satu bentuk akan merusak yang lain — ini harus diperbaiki di data
  acuan (GT v10), bukan di pipeline.

## 4. Pertanyaan keputusan untuk tim

1. **Port produksi?** Lapisan organizer v3+R6+format (66.2%) adalah kandidat
   produksi — perlu keputusan user (sama seperti eksperimen sebelumnya).
2. **Perbaiki GT?** Buat GT v10 yang konsisten (FMIPA "dan", HIMA pendek/panjang)
   — membuka aturan yang sekarang dilarang. GT v9 tetap frozen sebagai acuan.
3. **Fokus selanjutnya?** Jalur akurasi lain (nomor 76.9%, kegiatan 6.8%,
   tanggal 81.8%) atau menunggu data baru untuk scoring/KB?

## 5. Cara mengulang eksperimen

```bash
GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_org_format   # ORG-004
GT_CSV_PATH=Ground_Truth_Sertifikat_v9.csv uv run python -m tests.benchmark_organizer_v3  # v3 baseline
uv run python -m pytest tests/ -q                                                          # 31 test
```
