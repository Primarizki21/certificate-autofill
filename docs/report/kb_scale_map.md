# KB-SCALE-003 — Peta hemat KB (volume x key space x skew)

> Generasi: 2026-08-14 15:33:08 | SEED=42 | confirm 3x | key sintetis freq zipf | routed share 61% (terukur korpus) | 0 LLM runtime

**Pertanyaan:** di ukuran produksi mana KB hemat LLM >= 50%? kb_design.md berasumsi 1.000-10.000 unique organizer utk 36k request — asumsi ini divalidasi/diuji di sini (proyeksi pola, bukan data riil).

**Sel dihitung = saved % dari request non-routed** (miss KB + hit KB).

## Skew 70%

| Volume \ Key space | 55 | 200 | 1000 | 5000 | 10000 |
|---|---|---|---|---|---|
| 500 | 78% | 57% | 44% | 40% | 35% |
| 1000 | 87% | 66% | 51% | 40% | 36% |
| 5000 | 97% | 90% | 71% | 57% | 52% |
| 10000 | 99% | 95% | 80% | 64% | 59% |
| 36000 | 100% | 99% | 92% | 78% | 72% |

## Skew 80%

| Volume \ Key space | 55 | 200 | 1000 | 5000 | 10000 |
|---|---|---|---|---|---|
| 500 | 84% | 66% | 43% | 40% | 35% |
| 1000 | 89% | 75% | 50% | 40% | 36% |
| 5000 | 98% | 91% | 73% | 57% | 52% |
| 10000 | 99% | 95% | 80% | 64% | 59% |
| 36000 | 100% | 99% | 92% | 78% | 72% |

## Skew 90%

| Volume \ Key space | 55 | 200 | 1000 | 5000 | 10000 |
|---|---|---|---|---|---|
| 500 | 90% | 84% | 68% | 49% | 46% |
| 1000 | 93% | 86% | 73% | 55% | 51% |
| 5000 | 98% | 94% | 84% | 71% | 66% |
| 10000 | 99% | 96% | 88% | 77% | 72% |
| 36000 | 100% | 99% | 94% | 85% | 80% |

## GATE (proyeksi produksi: 36k request, 1k-10k key, 80/20)

- Key space 1000: saved **92%** → PASS (>= 50%)
- Key space 5000: saved **78%** → PASS (>= 50%)
- Key space 10000: saved **72%** → PASS (>= 50%)
- **VERDICT: PASS**

## Interpretasi

- Hemat datang dari **key populer**: dgn skew 80/20, top-20% key menampung 80% request → request/key tinggi di sana → warmup terbayar. Key langka tetap miss (LLM), tapi porsinya kecil.
- 36k / 10k key = 3.6 req/key rata-rata TAPI masih hemat 72% — request/key global menyesatkan; yang penting request per key populer.
- Volume kecil + key space besar = hemat rendah (500 req / 10k key = 35%): KB hanya layak di volume besar ATAU persist lintas periode (KB-002: warmup sekali, hemat selamanya) — peta ini = cold-start worst case.