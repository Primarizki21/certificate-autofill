# KB-005 — Event_type utk key: role vs jenis_kegiatan vs kelompok_kegiatan

> Generasi: 2026-08-11 11:06:36 | GT v9 + matcher v2 | pipeline = run v9 + router CURRENT | 0 LLM runtime | seed 42

Pertanyaan desain #1 (kb_design.md): cukup role proxy, atau perlu ekstrak `jenis_kegiatan` beneran? Diukur dari `map_kelompok_dan_jenis` (offline, 0 LLM) — 4 varian normalisasi key × 3 event = 12 kombinasi.

| Varian | Event | Keys | Repeat (cert) | Empty | Collision | Seeds | Hit | Saved | Wrong | Exact KB / Pipe | Shadow hit (3x) | Shadow disagree | Shadow wrong |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plain | role | 55 | 3 (9) | 13 | 0 | 3 | 9 | 0 | 0 | 9/74 (12.2%) / 62/74 (83.8%) | 3 | 0 | 0 |
| plain | jenis | 20 | 2 (4) | 52 | 1 | 2 | 4 | 0 | 1 | 3/74 (4.1%) / 62/74 (83.8%) | 0 | 0 | 0 |
| plain | kelompok | 58 | 5 (14) | 7 | 1 | 5 | 14 | 1 | 2 | 12/74 (16.2%) / 62/74 (83.8%) | 3 | 0 | 0 |
| stem | role | 54 | 2 (9) | 13 | 0 | 2 | 9 | 0 | 0 | 9/74 (12.2%) / 62/74 (83.8%) | 5 | 0 | 0 |
| stem | jenis | 20 | 2 (4) | 52 | 1 | 2 | 4 | 0 | 1 | 3/74 (4.1%) / 62/74 (83.8%) | 0 | 0 | 0 |
| stem | kelompok | 57 | 4 (14) | 7 | 1 | 4 | 14 | 1 | 2 | 12/74 (16.2%) / 62/74 (83.8%) | 5 | 0 | 0 |
| alias | role | 54 | 2 (9) | 13 | 0 | 2 | 9 | 0 | 0 | 9/74 (12.2%) / 62/74 (83.8%) | 5 | 0 | 0 |
| alias | jenis | 20 | 2 (4) | 52 | 1 | 2 | 4 | 0 | 1 | 3/74 (4.1%) / 62/74 (83.8%) | 0 | 0 | 0 |
| alias | kelompok | 57 | 4 (14) | 7 | 1 | 4 | 14 | 1 | 2 | 12/74 (16.2%) / 62/74 (83.8%) | 5 | 0 | 0 |
| both | role | 54 | 2 (9) | 13 | 0 | 2 | 9 | 0 | 0 | 9/74 (12.2%) / 62/74 (83.8%) | 5 | 0 | 0 |
| both | jenis | 20 | 2 (4) | 52 | 1 | 2 | 4 | 0 | 1 | 3/74 (4.1%) / 62/74 (83.8%) | 0 | 0 | 0 |
| both | kelompok | 57 | 4 (14) | 7 | 1 | 4 | 14 | 1 | 2 | 12/74 (16.2%) / 62/74 (83.8%) | 5 | 0 | 0 |

## Interpretasi

- `Empty` = cert yang key-nya mati (event kosong/`--`). `jenis_kegiatan` sering `--` → key mati; `kelompok` selalu non-empty (5 kategori).
- `Collision` = key sama → tingkat pipeline beda (gate 0).
- `Wrong`/`Shadow wrong`/`Shadow disagree` = 0 = aman.
- Keputusan desain: event mana yg menang (repeat keys tinggi, empty rendah, hit tinggi, collision 0). Ini jawaban utk schema produksi KB (kapan pun dipromosikan).