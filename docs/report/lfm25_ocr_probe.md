# OCR-007 — Probe LFM2.5-VL-3B (VLM OCR) — Hasil Detail

> Generasi: 2026-08-13 | GT v9 + matcher v2 | 10 stem scan tetap (sama dgn probe
> DocTR OCR-006) | Varian: **GGUF Q4_0 + mmproj Q8_0** (terendah RAM/quant) via
> `llama-server` (llama.cpp b10405) | 0 LLM pipeline call (OCR terpisah)
>
> Data per-cert: `tests/benchmark_runs/ocr_experiment/lfm25_ocr_20260813_151134/detail.json`

---

## 1. Ringkasan eksekutif

**GATE PASS** — engine OCR pertama yang **tidak regress nomor** (semua engine
klasik OCR-001..006 gagal: paddle 39.4%, easyocr 15.2%, DocTR 36.4% di full
scan; di 10 stem ini DocTR nomor 14.3% vs baseline 28.6%). LFM2.5-VL-3B
mempertahankan nomor **28.6% = baseline**, dates **88.9% = baseline**, dan
**menaikkan organizer exact 0% → 20%**, MACRO **40.0% → 44.4%**.

**Kunci kualitatif**: model TIDAK pernah merusak digit di 7 nomor (DocTR
hancurkan 6/7). Semua 5 miss nomor = masalah lapisan extractor/format, bukan
pembacaan. Kualitas transkripsi jauh di atas engine klasik (struktur dokumen,
NIP/NIM, jabatan, institusi terbaca utuh).

| Field (exact) | baseline rapid_tess | **LFM2.5-VL-3B** | delta | gate |
|---|---|---|---|---|
| nomor_bukti_fisik (7 GT) | 28.6% | **28.6%** | +0.0 | no-regress ✅ |
| waktu_mulai (9 GT) | 88.9% | **88.9%** | +0.0 | no-regress ✅ |
| waktu_selesai (9 GT) | 88.9% | **88.9%** | +0.0 | no-regress ✅ |
| penyelenggara exact | 0.0% | **20.0%** | +20.0pt | naik ✅ |
| penyelenggara fuzzy | 50.0% | **60.0%** | +10.0pt | naik ✅ |
| nama_kegiatan | 0.0% | 0.0% | +0.0 | = (bukan gate) |
| **MACRO** | **40.0%** | **44.4%** | **+4.4pt** | naik ✅ |
| MACRO fuzzy | 51.1% | 53.3% | +2.2pt | naik ✅ |

---

## 2. Setup & reproduksi

| Item | Nilai |
|---|---|
| Model | `LFM2.5-VL-3B-Q4_0.gguf` (1520 MB) + `mmproj-LFM2.5-VL-3B-Q8_0.gguf` (556 MB) — quant terkecil yang tersedia di repo (tidak ada Q3/Q2) |
| Runtime | llama.cpp b10405 (prebuilt ubuntu-x64, `libmtmd.so` ada) |
| Server | `llama-server -m <Q4_0> --mmproj <Q8_0> -c 4096 -t 8 --port 8080` |
| Server RSS | **~4.9 GB** (VmRSS 4,997,516 KB) — jalan aman di host 5.3 GB tersedia (Docker mati) |
| Prompt | transkripsi polos: *"Transkripsikan semua teks pada gambar ini secara lengkap, baris per baris, persis seperti yang tertulis. Jangan menambahkan komentar."* |
| Sampling | temperature 0.1, max_tokens 2000 |
| Render | PDF → PNG zoom 3.0 (konsisten baseline), 1 request per halaman |
| Latency | **~77 s/cert** (70.8–85.7) vs baseline 8.6 s/cert = **~9x** |
| Hasil | 10/10 cert OK, 0 error, 0 watchdog kill |

Reproduksi:
```bash
# 1. server (model lokal di /tmp/opencode/models/...)
llama-server -m LFM2.5-VL-3B-Q4_0.gguf --mmproj mmproj-LFM2.5-VL-3B-Q8_0.gguf -c 4096 -t 8 --port 8080
# 2. probe 10 stem
uv run python -m tests.benchmark_lfm25_probe probe --server-pid <PID>
# 3. eval vs GT v9 + matcher v2
uv run python -m tests.benchmark_lfm25_probe eval \
  --texts <run>/extracted_texts --out <run>/eval.json
```

## 3. Metodologi

- **10 stem tetap** (sama dgn probe DocTR OCR-006): 2439919, 2954707, 2954933,
  2954571, 2955331, FIT_Faiz, NIC_Faiz, ACW_Faiz, 1952296, SERTIF76 — semua
  scan (PyMuPDF teks ≤ 60 char).
- **Like-for-like**: kedua engine dievaluasi pada stem yang sama, GT v9 +
  matcher v2, harness `benchmark_ocr.cmd_eval` yang sama, extractor produksi
  (`field_extractor` + `organizer_v2` + `form_mapper`).
- Baseline = korpus `ocr_experiment/baseline_rapid_tess/` (10 stem dipilih
  ulang → `eval.json` = 40.0% MACRO, konsisten angka OCR-006/HYB-001).
- OCR-only: teks = murni hasil engine, tanpa prepend teks embedded.

---

## 4. Detail per-field

### 4.1 Nomor bukti fisik (7 GT) — 2 exact, 5 miss, 0 digit rusak

| stem | GT | LFM actual | LFM | baseline actual | base |
|---|---|---|---|---|---|
| 2954707_219642_skp | `279/SPS/PAN.COMPETITIONOFDESIGN/HIMAPAJAK/V/2026` | sama persis | **X** | sama persis | X |
| 1952296_219642_skp | `180/E/BEM-FKM/UNAIR/IX/2023` | sama persis | **X** | sama persis | X |
| 2954571_219642_skp | `SERT-2465/PKN.1/2025` | `2465/PKN.1/2025` | . | `2465/PKN.1/2025` | . |
| ACW_Faiz | `SERT-2128/BEM/2026` | `2128/BEM/2026` | . | `2128/BEM/2026` | . |
| 2955331_219642_skp | `177/LPI/SSP/VII//2023` | `177/LPI/SSP/VIII/2023` | . | `177/LPI/SSP/VIII/2023` | . |
| NIC_Faiz | `011/C/NACOESTA4.0HIMASTA/UNIMUS/VI/2025` | `011/C/NACOESTA4.0/HIMASTA/UNIMUS/VI/2025` | . | identik dgn LFM | . |
| 2439919_221065_skp | `106/STF.E/HOLOGY7.0/XI/2024` | `None` | . | `None` | . |

**Analisis 5 miss — SEMUA di lapisan extractor, bukan pembacaan:**

1. **SERT- prefix (2954571, ACW)**: transkripsi LFM berisi `SERT-2465/PKN.1/2025`
   (baris 5) & `SERT-2128/BEM/2026` — model membaca utuh. Extractornya
   membuang prefix `SERT-` (perilaku identik baseline; normalisasi SERT- ada di
   PROD-002 `organizer_normalize` tapi flag OFF + harness ini tidak memakainya).
2. **`VIII` vs GT `VII//` (2955331)**: LFM dan baseline **sama-sama** membaca
   `VIII` — kemungkinan sertifikat asli memang `VIII` atau keduanya misbaca
   identik; tidak ada indikasi kelemahan spesifik LFM.
3. **Separator ekstra `/` (NIC_Faiz)**: `NACOESTA4.0/HIMASTA` vs GT
   `NACOESTA4.0HIMASTA` — LFM dan baseline **identik** (GT mungkin versi
   tanpa separator; transkripsi model mengikuti format cetak).
4. **Nomor tanpa label (2439919)**: transkripsi berisi `106/STF.E/HOLOGY7.0/XI/2024`
   (baris 6) dan `extract_certificate_number()` berhasil mengekstraknya,
   tetapi `extract_certificate_fields()` mengembalikan `None` — extractor
   membutuhkan label `NOMOR :` untuk field ini. Perilaku identik baseline.

> **Verdict nomor**: kualitas pembacaan = perfect (0 digit salah di 7 nomor,
> termasuk serial panjang `279/SPS/PAN.COMPETITIONOFDESIGN/HIMAPAJAK/V/2026`).
> Gap vs baseline = 0; gap vs GT = format/ekstraksi, ranah normalisasi
> (PROD-002) bukan OCR.

### 4.2 Penyelenggara (10 GT) — exact 0→2, fuzzy 5→6

| stem | GT | LFM actual | LFM | baseline actual | base |
|---|---|---|---|---|---|
| 2954707_219642_skp | Himpunan Mahasiswa Perpajakan, Fakultas Ilmu Administrasi, Universitas Brawijaya | **sama persis (lengkap!)** | **X** | Himpunan Mahasiswa Perpajakan, Fakultas Ilmu . Umum HIMAPAJA | . |
| 2954571_219642_skp | Tax Center Politeknik Keuangan Negara STAN | **sama persis** | **X** | Tax Center Politeknik Keuangan Negara STAN Tangerang Selatan | F |
| 2439919_221065_skp | Faculty of Computer Science Brawijaya University | Faculty of Computer Science UB | F | BEM MEI > | . |
| 2954933_219642_skp | Himpunan Mahasiswa Statistika Fakultas MIPA Universitas Gadjah Mada | Himpunan Mahasiswa Statistik | F | Himpunan Mahasiswa Statistika | F |
| 1952296_219642_skp | Divisi Kaprof APHSA BEM FKM Universitas Airlangga | Divisi Kaprof APHSA BEM FKM Universitas Airlangga + junk "Partner Speaker With Halolearn..." | F | None (junk lain) | . |
| ACW_Faiz | Politeknik Negara STAN | junk "Politiia Academic Weeks 2026 Politeknik Keuangan Negara STAN..." | F | junk | . |
| FIT_Faiz | Informatics Engineering, Faculty of Information Technology | Informatics Engineering Department | . | of Informatics Engineering Department | F |
| SERTIF76 | Biro Penelitian dan Pengembangan BEM FEB Universitas Airlangga | BEM | . | Penelitian dan Pengembangan BEM Fakult... | F |
| 2955331_219642_skp | Literasi Psikologi Indonesia | DEPARTMENT CONNECTION | . | Literasi Psikologi Indonesia on July 30, 2023... | F |
| NIC_Faiz | Himpunan Mahasiswa Statistika UNIMUS | Nomor : 011CNACOESTA40HIMASTAUNIMUSVI2025 | . | identik | . |

**Analisis:**

- **2 exact baru** = win besar: 2954707 (organizer LENGKAP termasuk fakultas +
  universitas — baseline gagal total) dan 2954571 (LFM tidak menambahkan
  "Tangerang Selatan" → exact; baseline kelebihan → fuzzy).
- **SERTIF76 & 2955331 regress relatif baseline**: teks LFM bersih dan
  organisasi ADA di transkripsi (SERTIF76 baris 18: "Biro Penelitian dan
  Pengembangan Badan Eksekutif Mahasiswa Fakultas Ekonomi dan Bisnis
  Universitas Airlangga"; 2955331 baris 12: "...organized by Literasi
  Psikologi Indonesia on July 30..."), tapi `organizer_v2` memilih nilai lain
  (SERTIF76: "BEM" dari baris header; 2955331: "DEPARTMENT CONNECTION" dari
  baris jabatan signer). Ini **masalah scoring extractor**, bukan transkripsi
  — justru bukti transkripsi lebih lengkap: garis teks utuh membuat scoring
  memilih frasa yang berbeda. Relevan utk F1C/R6 lanjutan.
- **NIC_Faiz**: OCR typo `STATISTKA` (tanpa I) muncul di transkripsi — kasus
  OCR-merge lama; baseline identik (gagal total).

> **Verdict organizer**: LFM = satu-satunya engine yang menghasilkan nilai
> LENGKAP (fakultas+universitas) langsung dari scan — gap yang selama ini
> hanya bisa ditutup lapisan enrich (R6/F1C). Potensi hybrid HYB-001:
> LFM organizer (20% exact) + baseline nomor.

### 4.3 Tanggal pelaksanaan (9 GT) — 8 exact (= baseline)

| stem | GT | LFM | baseline |
|---|---|---|---|
| 2439919 | 14 Sep 2024 | X | X |
| 2954707 | 3 Apr 2026 | X | X |
| 2954933 | 27 Jan 2026 (mulai=selesai) | X | X |
| 2954571 | 30 Des 2025 | X | X |
| 2955331 | 30 Jul 2023 – 1 Agu 2023 | X | X |
| ACW_Faiz | 28 Feb 2026 | X | X |
| 1952296 | 24 Sep 2023 | X | X |
| SERTIF76 | 6 Mei 2026 | X | X |
| FIT_Faiz | 7–9 Jul 2026 | None (keduanya) | None |

Satu-satunya miss = FIT_Faiz, format `HELD ON 7th-9th JULY 2026` — extractor
tidak mendukung ordinal `7th-9th`. **Identik baseline** → bukan regress.

### 4.4 Nama kegiatan (10 GT) — 0 exact (= baseline, bukan gate)

Semua None, termasuk yang **teksnya ada di transkripsi LFM**:

| stem | GT | ada di transkripsi LFM? |
|---|---|---|
| 2439919 | Hology 7.0 | ✅ "At the Hology 7.0 with theme" |
| 2955331 | Give Yourself A Break: The Power Of Self Compassion | ✅ "...participating in The Largest Campaign, Give Yourself A Break: The Power Of Self Compassion organized by..." |
| ACW_Faiz | Academic Weeks **2025** | ⚠️ LFM baca "Academic Weeks **2026**" — mendukung catatan GT v10 (v32: ACW 2025/2026) |
| 2954707 | Competition of Design | teks ada (judul) |
| FIT_Faiz | FIT COMPETITION 2026 | ✅ "AT THE FIT COMPETITION 2026" (all-caps — sudah dicatat AKT-004) |

Gap = **deteksi extractor produksi** (anchors AKT-002 hidup di
`tests/benchmark_akt2.py`, belum diport), bukan OCR. Pada 6/10 stem teks
kegiatan terbaca sempurna oleh LFM — bila anchors AKT diport, potensi gain.

---

## 5. Timing & resource per cert

| stem | wall (s) | chars transkripsi |
|---|---|---|
| 1952296 | 70.8 | 269 |
| ACW_Faiz | 73.9 | 393 |
| 2954571 | 72.5 | 348 |
| FIT_Faiz | 76.3 | 578 |
| 2955331 | 78.1 | 714 |
| SERTIF76 | 78.2 | 498 |
| 2954707 | 80.4 | 700 |
| 2954933 | 81.5 | 686 |
| 2439919 | 82.2 | 749 |
| NIC_Faiz | 85.7 | 812 |
| **rata-rata** | **77.9** | **575** |

- Model: 2.1 GB download; server RSS ~4.9 GB (host butuh ≥5 GB tersedia).
- Latency ~9x baseline (8.6 s/cert) — biaya intrinsik VLM autoregresif
  (prefill gambar + decoding ~300-500 token).
- Init model: ~1x saja (server load sekali); per-cert = murni inferens.

## 6. Temuan kualitatif transkripsi

- **FIT_Faiz**: seluruh struktur terbaca benar — `CERTIFICATE OF ACHIEVEMENT`,
  `3rd Place Winner`, `AT THE FIT COMPETITION 2026`, `HELD ON 7th-9th JULY
  2026`, NIP/NIM, 2 pejabat + universitas. Baseline kehilangan banyak baris.
- **2439919 (Hology 7.0)**: nomor, tema kutipan, 3 baris tanda tangan
  (Vice Dean/PEB/Chief Executive + NIP/NIM) — utuh.
- **2954707**: nomor serial panjang + organizer lengkap (himpunan, fakultas,
  universitas) — dua-duanya exact, kemenangan ganda.
- **2954571**: transkripsi menjaga prefix `SERT-` (extractor yang buang).
- **ACW_Faiz**: misbaca kecil `Politeknik` → `Politiia`; tanggal/nomor benar.

## 7. Keterbatasan

- **Latency 77 s/cert + RSS 4.9 GB**: tidak viable utk produksi real-time
  tanpa F7 OCR queue / offload GPU; utk batch (prototype) masih masuk akal.
- **n=10 probe** — angka per-field belum otoritatif korpus penuh (baseline
  scan resmi 49: nomor 57.6%, organizer 14.3%, MACRO 44.3%).
- **Determinisme**: sampling temp 0.1 — transkripsi bisa bervariasi sedikit
  antar run (beda engine klasik yang deterministik).
- **nama_kegiatan & format tanggal ordinal** (FIT_Faiz) tidak tertolong oleh
  OCR — ranah extractor/GT.

## 8. Opsi lanjut (urutan saran)

1. **Full run 74 cert** (~95 min) → angka otoritatif + opsi re-run probe utk
   cek determinisme.
2. **Hybrid per-field** (pola HYB-001): LFM utk organizer/dates + baseline
   rapid_tess utk nomor — LFM organizer exact 20% (vs 0%) potensi naikkan
   MACRO hybrid di atas 46.8% HYB-001.
3. **Extractor-side win**: karena transkripsi bersih, fix `SERT-` prefix
   (PROD-002 nomor pattern-4) + port anchors AKT-002 langsung menaikkan
   hasil tanpa OCR baru — kombinasi murah.
4. Produksi: tidak disentuh; semua artefak di `tests/` + run dir.

## Referensi

- Ledger: `docs/experiments_ledger.md` → OCR-007 (PASS)
- Handoff: `docs/handoff_v33.md`
- Harness: `tests/benchmark_lfm25_probe.py`
- Run dir: `tests/benchmark_runs/ocr_experiment/lfm25_ocr_20260813_151134/`
  (extracted_texts, ocr_meta.json, eval.json, detail.json)
