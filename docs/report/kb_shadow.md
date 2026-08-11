# KB-001 — Shadow replay KB tingkat v1 (alur router → KB → LLM)

> Generasi: 2026-08-11 10:35:53 | GT v9 + matcher v2 | key v1 (organizer v3+R6 + role map_jabatan) | pipeline = run v9 + router CURRENT | 0 LLM runtime call

Shadow: hasil eval tetap dari pipeline; KB dihitung potensinya (hit authoritative pada cert router-miss = LLM call terselamat). `shadow_disagree` = hit yang BERBEDA dari pipeline (regress jika KB diadopsi); `wrong_hits` = hit yang salah vs GT. Gate: disagree 0, wrong 0, konflik tak dipakai.

## Diagnostics korpus (74 cert)

- Key unik: 55 | key berulang: 3 (9 cert) | baseline LLM calls (no-KB): 42

| Key (org, role) | frekuensi |
|---|---|
| Faculty of Science and Technology INFORMATION SYSTEMS DEPT + Peserta | 5 |
| Faculty of Science and Technology Information System Dept. + Peserta | 2 |
| Program Studi S1 Teknologi Sains Data Universitas Airlangga + Panitia | 2 |

| Konfig | Warm N | KB size | Hit | Saved LLM | Disagree | Wrong | Konflik | Tingkat exact pipe | Tingkat exact KB |
|---|---|---|---|---|---|---|---|---|---|
| 1x confirm | 10 | 55 | 51 | 13 | 0 | 5 | 0 | 54/64 (84.4%) | 46/64 (71.9%) |
| 1x confirm | 20 | 55 | 43 | 10 | 0 | 5 | 0 | 44/54 (81.5%) | 38/54 (70.4%) |
| 1x confirm | 37 | 55 | 30 | 9 | 0 | 4 | 0 | 31/37 (83.8%) | 26/37 (70.3%) |
| 3x confirm (default warm-up) | 10 | 55 | 3 | 0 | 0 | 0 | 0 | 54/64 (84.4%) | 3/64 (4.7%) |
| 3x confirm (default warm-up) | 20 | 55 | 3 | 0 | 0 | 0 | 0 | 44/54 (81.5%) | 3/54 (5.6%) |
| 3x confirm (default warm-up) | 37 | 55 | 0 | 0 | 0 | 0 | 0 | 31/37 (83.8%) | 0/37 (0.0%) |

## Safety — OCR noise (wrong_hits harus tetap 0)

| Noise | config | Warm N | Wrong hits | Disagree |
|---|---|---|---|---|
| 10% | 3x confirm (default warm-up) | 20 | 0 | 0 |
| 25% | 3x confirm (default warm-up) | 20 | 0 | 0 |
| 50% | 3x confirm (default warm-up) | 20 | 0 | 0 |

## Interpretasi

- Key berulang naik vs F3 (role mentah) BUKTI normalisasi role bekerja; gain LLM call tetap kecil di 74 cert — ukuran korpus membatasi, bukan desain.
- `shadow_disagree`/`wrong_hits` = 0 di semua konfig = shadow aman: mengadopsi KB tidak mengubah hasil pipeline (syarat no-regress).
- Konflik (key sama, tingkat beda) → entry non-authoritative otomatis (lihat `tests/kb/kb.py`); di korpus ini diukur `collisions`.
- Keputusan produksi TETAP menunggu sampling data riil lintas fakultas (asumsi unique organizer 1.000–10.000 belum tervalidasi).