# KB-SCALE-001 — Simulasi workload produksi skewed (efisiensi saat scale)

> Generasi: 2026-08-14 15:11:50 | SEED=42 | confirm 3x | 0 LLM runtime (label pipeline offline) | GT Ground_Truth_Sertifikat_v9.csv | dua volume: kecil (500 req) vs produksi (5000 req)

**Pertanyaan:** KB hemat LLM saat produksi besar (request skewed)? Korpus 74 seragam tidak membuktikan (saved=0, v27 Verdict Final). Simulasi memproyeksikan pola produksi: 20% organizer terpopuler menampung 70-90% request.

## Hasil — volume produksi (N=5000 request sintetis, deterministik)

| Skew (top-20% key) | Alpha | Non-routed (LLM tanpa KB) | KB hit | Saved LLM | Saved % | Wrong |
|---|---|---|---|---|---|---|
| asli (freq korpus) | 1.00 | 1556 | 4835 | 1499 | 96% | 542 |
| 70/30 | 2.73 | 653 | 4835 | 596 | 91% | 223 |
| 80/20 | 3.12 | 448 | 4835 | 391 | 87% | 136 |
| 90/10 | 3.66 | 205 | 4835 | 148 | 72% | 50 |

## Hasil — volume kecil (N=500, sensitivitas)

| Skew (top-20% key) | Alpha | Non-routed (LLM tanpa KB) | KB hit | Saved LLM | Saved % | Wrong |
|---|---|---|---|---|---|---|
| asli (freq korpus) | 1.00 | 142 | 338 | 88 | 62% | 27 |
| 70/30 | 2.73 | 70 | 358 | 21 | 30% | 11 |
| 80/20 | 3.12 | 42 | 394 | 5 | 12% | 1 |
| 90/10 | 3.66 | 25 | 432 | 1 | 4% | 1 |

## GATE (skew 80/20, N=5000)

- Saved LLM >= 50% non-routed: **87%** → PASS
- Hit rate >= 60%: **97%** → PASS
- Wrong < 5% hit: **136 (2.8%)** → PASS
- **VERDICT: PASS**

## Interpretasi

- Est. latency saved di 80/20: ~978s per 5000 request (asumsi 2.5s/call benchmark v4 — ESTIMASI, bukan ukuran).
- Warmup cost: 57 request tetap tanya LLM (3x confirm per key baru) — relatif kecil di workload besar.
- 55/55 key authoritative setelah workload.
- **Volume kecil (500 req) → saved % rendah**: warmup 3x menelan porsi besar request non-routed. Hemat LLM proporsional request per key (volume besar = warmup terbayar). Produksi 36k request / 1-10k key (kb_design.md) berada di tengah — gate 80/20 N=500: saved ~12% (FAIL), N=5000: ~87% (PASS).
- Wrong = hit yg labelnya ≠ GT. Sumber: key yg label pipeline offline-nya salah (bukan kesalahan KB — KB mewarisi pipeline). Key populer cenderung benar → error serve KB (2.8%) lebih rendah dari error pipeline offline (tingkat ~19%).
- Sifat: **proyeksi pola**, bukan bukti distribusi riil. Sebelum produksi: `uv run python -m tests.kb.audit` di data lintas fakultas.