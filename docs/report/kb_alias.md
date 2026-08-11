# KB-006 — Alias mining data-driven (precision + dampak hit)

> Generasi: 2026-08-11 11:09:31 | GT v9 + matcher v2 | pipeline = run v9 + router CURRENT | 0 LLM runtime

## Kandidat alias (stem-sama + role-sama + tingkat pipeline-sama)

| Org A (varian) | Org B (target) | Role | nA/nB | GT set | Valid |
|---|---|---|---|---|---|
| Faculty of Science and Technology Information System Dept. | Faculty of Science and Technology INFORMATION SYSTEMS DEPT | Peserta | 2/5 | ['Departemen/Program Studi'] | True |

**Precision kandidat vs GT: 1/1 valid (semua konsisten)**

## Dampak pada hit (plain vs auto-alias vs auto+manual)

| Konfig | Keys | Seeds | Ceiling hit | Wrong | Shadow hit (3x) | Shadow saved | Shadow disagree | Shadow wrong |
|---|---|---|---|---|---|---|---|---|
| plain | 55 | 3 | 9 | 0 | 3 | 0 | 0 | 0 |
| auto-alias | 54 | 2 | 9 | 0 | 5 | 0 | 0 | 0 |
| auto+manual | 54 | 2 | 9 | 0 | 5 | 0 | 0 | 0 |

## Safety — noise OCR 25%

| Shadow wrong |
|---|
| 0 |

## Interpretasi

- Semua kandidat valid = mining tidak over-merge di korpus (bisa langsung dipakai, tetap dengan review manusia di produksi).
- Auto-alias = alias manual (KB-003) di korpus ini — mekanisme terotomasi tanpa kehilangan keamanan.