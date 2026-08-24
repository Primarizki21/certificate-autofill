# HYB-KB-002 — Proyeksi skala ril HYB+KB (~360k request, non-concurrent)

> Generasi: 2026-08-24 10:23:22 | SEED=42 | N=360,000 | horizon 1095 hari | 0 LLM runtime

**Terukur dari HYB-LLM-001:** router 64.9% (48/74 @100%) | LLM benar 57.7% (17/26 unrouted) | 176 tok/call | 1.5 s/call. Hit hanya dari `servable()` (router_rule 3x / llm 5x); TTL dimodelkan harness-side.

## Grid (hemat calls | wrong | akurasi tanpa→dgn KB | LLM calls dgn KB | jam terhemat)

| Key space | Skew | TTL | Hemat | Wrong | Akurasi −KB | Akurasi +KB | Calls +KB | Hemat waktu |
|---|---|---|---|---|---|---|---|---|
| 1,000 | 70% | — | 98.4% | 31,445 | 86.5% | 91.0% | 1,835 | 47 jam |
| 1,000 | 70% | 365 | 98.4% | 31,445 | 86.5% | 91.0% | 1,835 | 47 jam |
| 5,000 | 70% | — | 92.5% | 32,539 | 86.3% | 89.9% | 8,783 | 45 jam |
| 5,000 | 70% | 365 | 92.4% | 32,511 | 86.3% | 89.9% | 8,845 | 45 jam |
| 10,000 | 70% | — | 86.4% | 30,897 | 86.2% | 89.5% | 15,903 | 42 jam |
| 10,000 | 70% | 365 | 86.3% | 30,841 | 86.2% | 89.6% | 16,023 | 42 jam |
| 50,000 | 70% | — | 72.2% | 25,862 | 86.1% | 88.9% | 32,981 | 36 jam |
| 50,000 | 70% | 365 | 72.1% | 25,793 | 86.1% | 88.9% | 33,129 | 36 jam |
| 1,000 | 80% | — | 98.4% | 30,934 | 86.6% | 91.2% | 1,835 | 47 jam |
| 1,000 | 80% | 365 | 98.4% | 30,934 | 86.6% | 91.2% | 1,835 | 47 jam |
| 5,000 | 80% | — | 92.5% | 32,539 | 86.3% | 89.9% | 8,783 | 45 jam |
| 5,000 | 80% | 365 | 92.4% | 32,511 | 86.3% | 89.9% | 8,845 | 45 jam |
| 10,000 | 80% | — | 86.4% | 30,897 | 86.2% | 89.5% | 15,903 | 42 jam |
| 10,000 | 80% | 365 | 86.3% | 30,841 | 86.2% | 89.6% | 16,023 | 42 jam |
| 50,000 | 80% | — | 72.2% | 25,862 | 86.1% | 88.9% | 32,981 | 36 jam |
| 50,000 | 80% | 365 | 72.1% | 25,793 | 86.1% | 88.9% | 33,129 | 36 jam |
| 1,000 | 90% | — | 98.3% | 24,187 | 87.6% | 93.1% | 1,835 | 43 jam |
| 1,000 | 90% | 365 | 98.3% | 24,187 | 87.6% | 93.1% | 1,836 | 43 jam |
| 5,000 | 90% | — | 92.6% | 26,782 | 87.0% | 91.6% | 8,209 | 43 jam |
| 5,000 | 90% | 365 | 92.5% | 26,754 | 87.0% | 91.6% | 8,275 | 43 jam |
| 10,000 | 90% | — | 88.3% | 26,899 | 86.8% | 91.0% | 13,143 | 41 jam |
| 10,000 | 90% | 365 | 88.2% | 26,858 | 86.8% | 91.0% | 13,236 | 41 jam |
| 50,000 | 90% | — | 76.9% | 25,062 | 86.5% | 89.9% | 26,590 | 37 jam |
| 50,000 | 90% | 365 | 76.8% | 25,018 | 86.5% | 89.9% | 26,687 | 37 jam |

## GATE (key space 10k, skew 80/20, tanpa TTL)

- Hemat LLM calls **86.4%** >= 50% → PASS
- Akurasi dgn KB 89.5% >= tanpa KB 86.2% → PASS
- **VERDICT: PASS**

## Interpretasi

- Non-concurrent berarti hemat calls = hemat waktu proses berurutan: tiap call 1.5 s (terukur). Kolom jam = total waktu proses yang dihemat.
- Key space besar menekan hemat (warm-up menyebar); skew adalah penentu utama — konsisten KB-SCALE-003.
- TTL 365 hari menurunkan hemat untuk key jarang (basi → refresh via LLM), key populer tetap segar karena write tiap miss.
- Validasi akhir tetap `tests/kb/audit.py` pada data riil lintas fakultas sebelum port produksi (handoff v36 frontier #1).
