# KB-SCALE-004 — Konfigurasi KB: confirm 2x vs 3x, key alias

> Generasi: 2026-08-14 15:34:04 | SEED=42 | skew 80/20 | 0 LLM runtime | GT Ground_Truth_Sertifikat_v9.csv | korpus 74 (bukan sintetis)

**Pertanyaan:** 2x confirm aman (wrong no-regress vs 3x)? Dan alias menaikkan hemat di volume menengah (N=500) yang di SCALE-001 cuma 12%?

| Confirm | Key | N | Saved % | Saved | Hit | Wrong |
|---|---|---|---|---|---|---|
| 2x | plain | 500 | 24% | 10 | 407 | 3 |
| 2x | plain | 5000 | 91% | 408 | 4890 | 149 |
| 2x | alias | 500 | 24% | 10 | 409 | 3 |
| 2x | alias | 5000 | 91% | 408 | 4892 | 149 |
| 3x | plain | 500 | 5% | 2 | 382 | 0 |
| 3x | plain | 5000 | 87% | 389 | 4835 | 142 |
| 3x | alias | 500 | 5% | 2 | 385 | 0 |
| 3x | alias | 5000 | 87% | 389 | 4838 | 142 |

## GATE

- Wrong 2x (304) <= Wrong 3x (284) → FAIL
- Hemat N=500 avg 2x (24%) > 3x (5%) → PASS
- **VERDICT: FAIL**

## Interpretasi

- **2x confirm: hemat naik (24% vs 5% @N=500) TAPI wrong ikut naik (304 vs 284, +20)** — error pipeline terkunci lebih cepat dgn confirm lebih sedikit. Konsisten dgn KB-002 (1x = wrong 5). **3x confirm TETAP wajib** — hemat ekstra 2x tidak sebanding dgn salah ekstra.
- Alias (FST pair, KB-003/006): keys 55→54, hit sedikit naik di N=500 (alias 409 vs plain 407 @2x) — efek kecil di korpus ini (pair non-populer); berguna di data riil dgn fragmentasi lebih banyak.
- Angka ini korpus 74 — konfigurasi final produksi tetap diuji di data riil (audit.py) sebelum promosi.