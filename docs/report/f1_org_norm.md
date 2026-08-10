# F1 — Normalisasi Organizer & Nomor Sertifikat (offline, zero LLM)

> Generasi: 2026-08-10 | GT v9 + matcher v2 | pipeline offline (no LLM) |
> run: `tests/benchmark_runs/org_norm_20260810_082848/` | ledger ORG-002

## Hasil

| Metrik | Baseline | Variant | Delta |
|---|---|---|---|
| MACRO exact | 55.7% | 58.3% | **+2.6pt** |
| MACRO fuzzy | 65.1% | 67.5% | +2.4pt |
| organizer exact | 37.8% | 39.2% | **+1.4pt** |
| organizer fuzzy | 75.7% | 75.7% | 0 (no-regress) |
| nomor exact | 59.6% | **76.9%** | **+17.3pt** |
| nama_kegiatan / tanggal / tingkat | — | — | no-regress |

## Nomor: GATE PASS (+17.3pt)

Fix = 2 pattern baru + fallback raw text (9 cert recover):

1. **Pattern ke-4 prefix `SERT-`** (`SERT-2465/PKN.1/2025`, `SERT-2128/BEM/2026`) —
   pattern lama mulai dari digit, prefix hilang → mismatch GT.
2. **Fallback ekstraksi pada raw text (tanpa `normalize_text`)** — `normalize_text`
   memecah `UN27`→`UN 27`, `NACOESTA4.0`→`NACOESTA 4.0` sehingga regex nomor
   gagal (`SSF_Faiz 4330/UN27/...`, `1981676 BINCANG SANTAI`, `hakim_lomba
   GRADIANT 2.0`).
3. **Pattern titik** (`0101.17/STF/PCR/2025`) — belum recover, tapi pattern
   ditambahkan.

Recover: 1981676, 2954571, data slayer, ACW, SSF, binary_2024, hakim_lomba, ML,
2954421, KARSA (10 total di print — 9 nomor + 1 organizer).

## Organizer: GATE FAIL (+1.4pt < target +5pt)

Normalisasi pipeline-side yang diuji:
- **A** strip prefix junk `which held from <date> to <date> by` (residu phrase
  capture) — tidak ada kasus recover di corpus.
- **B** strip trailing `Himpunan Mahasiswa X`/`BEM X` bila value sudah punya
  konteks universitas (duplicate capture) — recover 1: `PRIMARIZKI_panitia_binary_2025`.
- **C** trailing `Universitas` → `Universitas Airlangga` bila raw punya konteks
  UNAIR (GT canonical) — recover 1: `primarizki_panitia_binary_2024`.

**Kenapa target +5pt tidak tercapai:** klasifikasi 46 non-exact organizer:

| Kategori | n | Sifat |
|---|---|---|
| fuzzy (contains/overlap) | 28 | PL benar tapi TIDAK LENGKAP (mis. `Himasada` vs GT `Himasada, Fakultas Ilmu Komputer`; `Biro...` hilang di depan) — masalah **ekstraksi**, bukan format |
| genuine-wrong | 18 | PL beda organisasi (salah capture) |

Gap 39.2→79.7 bukan gap normalisasi — 28 kasus fuzzy adalah ekstraksi parsial
(organizer_v2 `_clean` memotong terlalu agresif / salah candidate terpilih).
Normalisasi evaluator (matcher v2.1, case/whitespace/punct) juga TIDAK akan
menutup gap: fuzzy sudah = contains/overlap, butuh nilai LENGKAP untuk exact.

## Kesimpulan & rekomendasi

- **Nomor**: pattern ke-4 + fallback raw text = quick win nyata (+17.3pt, 0 cost
  LLM) — kandidat kuat untuk F6/dipakai, tapi produksi tetap ditunda (prototipe
  di tests).
- **Organizer**: normalisasi murni sudah habis; sisa gap butuh salah satu dari:
  (1) perbaikan scoring/candidate organizer_v2 (fase terpisah), (2) fallback LLM
  per-field (eksperimen A handoff v18, gate token), (3) KB organizer (Fase 3).
  Rekomendasi: **jangan kejar via matcher** (tidak akan menutup gap).
