# Review Tim — Eksperimen KB (knowledge base)

> Ringkasan internal untuk review tim. Detail teknis: `docs/kb_history.md`
> (naratif + Verdict Final), `docs/experiments_ledger.md` (KB-001..006),
> `docs/report/kb_*.md` (report per eksperimen). Versi .xlsx (mudah dibaca
> user) dibangkitkan dari dokumen ini — regenerasi manual saat isi berubah.
> Semua angka: 74 sertifikat, GT v9 + matcher v2.

---

## TL;DR (3 kalimat)

1. **KB (buku catatan jawaban tingkat) sudah selesai dieksperimenkan dan aman,
   tapi tidak terbukti menghemat AI** — karena data yang ada hanya 74 sertifikat
   dan hanya 3 di antaranya yang berulang; manfaat KB baru terlihat saat ada
   data bervolume besar.
2. **KB bukan alat akurasi** — ia hanya mengganti sumber jawaban (AI → catatan),
   isi jawabannya sama. Exact/fuzzy tidak berubah karena KB.
3. **Kesimpulan: KB ditutup sebagai eksperimen** (Verdict Final, handoff v27),
   alatnya siap dipakai kapan pun data baru tersedia. Jalur akurasi organisasi
   penyelenggara dilanjutkan terpisah (lihat `experiments_ledger.md` ORG-001..005
   + laporan resmi `report_data.json`).

---

## 1. Apa itu KB

Buku catatan yang menyimpan jawaban **tingkat kegiatan** (Internasional /
Nasional / Universitas / Fakultas / Departemen/Program Studi / Lainnya) untuk
kombinasi **(penyelenggara + peran)**. Tujuannya: kalau sertifikat baru sudah
pernah dilihat sebelumnya, jawab langsung dari catatan tanpa bertanya ke AI
(LLM) — hemat biaya dan waktu.

## 2. Hasil 6 eksperimen (semua lulus uji keamanan)

| Eksperimen | Ini ngapain | Apa yang diuji | Hasil | Verdict |
|---|---|---|---|---|
| KB-001 shadow | KB berjalan di samping pipeline (tidak dipakai, hanya dipantau) | Apakah jawaban KB bisa salah/konflik? Aman di noise OCR 10–50%? | 0 salah, 0 konflik, aman | PASS (3x confirm) |
| KB-002 persist | Catatan disimpan ke file (JSON) | Dimuat ulang, hasilnya harus sama persis | Persistence identik; 1x confirm terbukti TIDAK aman (5 salah) → 3x wajib | PASS |
| KB-003 normalisasi key | Penulisan penyelenggara diseragamkan (case, singkatan, stemming) | Kecocokan KB naik? Ada efek samping? | Kecocokan naik 3 → 5 hit, 0 efek samping | PASS |
| KB-004 alat audit | Instrumen mengukur kesiapan produksi (tanpa GT/LLM) | Selfcheck konsisten dengan KB-001? | Selfcheck lulus (55 key, 3 berulang) | PASS |
| KB-005 event type | Jenis kegiatan dipakai sebagai kunci tambahan? | Peran vs jenis kegiatan vs kelompok — mana yang paling aman? | **Tidak perlu** — peran (role) cukup & paling aman (jenis 70% kosong, kelompok over-merge) | PASS (role) |
| KB-006 alias mining | Menemukan penulisan ganda penyelenggara otomatis | Presisi kandidat alias vs daftar manual | 100% presisi, sama persis dengan daftar manual | PASS |

## 3. Kenapa tidak dipakai produksi

- **Penghematan AI tidak terukur**: di 74 sertifikat, semua sertifikat berulang
  kebetulan sudah dijawab aturan internal (router), jadi KB tidak pernah
  menyelamatkan pemanggilan AI (saved = 0). Manfaat KB baru muncul saat data
  besar (puluhan ribu sertifikat) dengan penyelenggara yang berulang.
- **Data tidak mungkin bertambah** (korpus 74 adalah semua yang ada), jadi
  pembuktian ini tidak akan tercapai dalam kondisi sekarang.
- **KB bukan alat akurasi**: ia cache — jawabannya sama dengan pipeline, hanya
  sumbernya yang beda. Terbukti `wrong = 0, disagree = 0` di semua eksperimen.

## 4. Kesimpulan & keputusan tim

**KB selesai sebagai eksperimen, aman, alatnya siap** (`tests/kb/audit.py`,
`tests/kb/alias.py`, `tests/kb/store.py`). Dibuka lagi hanya bila data baru
tersedia (jalankan `uv run python -m tests.kb.audit --dir <dir>` dulu).

Pertanyaan untuk tim:
1. **Setuju KB ditutup** (menunggu data baru) — atau ada jalur data baru yang
   bisa diakses (mis. kerjasama fakultas lain)?
2. **Prioritas sesudah ini** — lanjut jalur akurasi (organizer, sedang naik di
   eksperimen ORG) atau yang lain?

## 5. Cara mengulang eksperimen

```bash
uv run python -m tests.benchmark_kb_shadow   # KB-001
uv run python -m tests.benchmark_kb_seed     # KB-002
uv run python -m tests.benchmark_kb_norm     # KB-003
uv run python -m tests.kb.audit              # KB-004 (dry-run korpus 74)
uv run python -m tests.benchmark_kb_event    # KB-005
uv run python -m tests.benchmark_kb_alias    # KB-006
uv run python -m pytest tests/ -q            # 31 test
```
