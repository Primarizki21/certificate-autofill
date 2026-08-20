"""Add missing experiments from experiments_ledger.md to report_data.json.

Reads the current report_data.json, inserts missing experiments at chronologically
correct positions, and writes back. Idempotent (skips if id already exists).

Usage:
  uv run python scripts/update_report_data.py
"""

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(REPO, "docs", "report", "report_data.json")

# All missing experiments from the ledger, with data from summary files
# and ledger notes. Ordered chronologically.
MISSING_EXPERIMENTS = [
    # --- v8 era: LLM prompt variants ---
    {
        "id": "llm_001_gevidence",
        "phase": "v8",
        "label": "LLM-001 g_evidence prompt (minta bukti sebelum jawaban)",
        "variant": "g_evidence",
        "tingkat": "75.7%",
        "macro": "53.9%",
        "tokens_cert": 194,
        "calls": 35,
        "gt": "fixed_v8",
        "date": "Aug 3",
        "is_winner": False,
        "notes": "CLOSED — GATE FAIL. Tingkat turun (75.7% vs f_bias 82.4%). Prompt meminta LLM memberikan bukti singkat sebelum jawaban, tapi struktur output terlalu longgar.",
    },
    {
        "id": "llm_002_layout",
        "phase": "v8",
        "label": "LLM-002 layout representation (markdown/annotation ke prompt)",
        "variant": "layout_md",
        "tingkat": "77.0%",
        "macro": "50.8%",
        "tokens_cert": 235,
        "calls": 39,
        "gt": "fixed_v8",
        "date": "Aug 3",
        "is_winner": False,
        "notes": "CLOSED — GATE FAIL. Tingkat 77.0% < f_bias 82.4%. OCR-bound: 25/74 cert berteks embedded (tanpa teks diekstrak OCR). Tidak ada gain dari layout info.",
    },
    # --- v9 era: Router expansion ---
    {
        "id": "router_001_naive",
        "phase": "v9",
        "label": "ROUTER-001 naive rule expansion (univ, hima, fak patterns)",
        "variant": "router_naive",
        "tingkat": "-",
        "macro": "54.2%",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "fixed_v8",
        "date": "Aug 3",
        "is_winner": False,
        "notes": "CLOSED — FAIL. Precision turun ke 78.2% (12 salah). Rule naive terlalu agresif: univ fire pada 'Universitas Airlangga' induk, hima fire pada raw-text. Router 32/74 @78.2%.",
    },
    {
        "id": "router_002_datadriven",
        "phase": "v9",
        "label": "ROUTER-002 data-driven rules (bem_no_univ, bem+hima, sem+univ)",
        "variant": "router_v2",
        "tingkat": "83.8%",
        "macro": "58.9%",
        "tokens_cert": 176,
        "calls": 29,
        "router": "42/74 @100%",
        "gt": "fixed_v8",
        "date": "Aug 4",
        "is_winner": False,
        "notes": "PASS. Router coverage 36→42/74 @100% precision (0 salah). Org-level signals: bem_no_univ (2/2), bem+hima (2/2), sem+univ (1/1). 0 extra LLM call.",
    },
    {
        "id": "router_003_dept_luar",
        "phase": "v9",
        "label": "ROUTER-003 dept/luar signal fix (raw_text OR organizer)",
        "variant": "router_v3",
        "tingkat": "83.8%",
        "macro": "58.9%",
        "tokens_cert": 176,
        "calls": 29,
        "router": "45/74 @100%",
        "gt": "fixed_v8",
        "date": "Aug 4",
        "is_winner": False,
        "notes": "PASS. Fix efek samping organizer_v2: dept/luar dari raw_text pull balik 3 cert (Ananda×2 dept+fak, NIC hima+luar). Coverage 42→45/74 @100%. Bagian dari pipeline v9.",
    },
    # --- v9 era: ORG-001 (produksi organizer_v2) ---
    {
        "id": "org_001_v2",
        "phase": "v9",
        "label": "ORG-001 organizer_v2 (abbreviation map, strip, signer EN roles)",
        "variant": "organizer_v2",
        "run_dir": "tests/benchmark_runs/organizer_v2_20260805_162724",
        "tingkat": "83.8%",
        "macro": "58.9%",
        "tokens_cert": 176,
        "calls": 29,
        "router": "45/74 @100%",
        "gt": "v8",
        "date": "Aug 5",
        "is_winner": False,
        "notes": "PASS — full benchmark. Organizer exact 16.2→33.8% (+17.6pt), fuzzy 59.5→82.4% (+22.9pt), tingkat 82.4→83.8%, MACRO 55.2→58.9%. Phrase_v2: 31.1% vs hybrid 16.2% (2x). Sudah dipromosikan ke produksi (PROD-001). Efek samping: organizer_v2 bersih menghilangkan signal router dept/luar → di-fix ROUTER-003.",
    },
    # --- Aug 6: OCR experiments (NC-001, HYB-001 already in report_data) ---
    # --- Aug 10: F3 + KB + OOD + STAT + REVIEW ---
    {
        "id": "f3_001_kb_proto",
        "phase": "v10",
        "label": "F3-001 KB prototype warmup in-memory (opsi B, key=organizer+role)",
        "variant": "kb_warmup",
        "run_dir": "tests/benchmark_runs/kb_warmup_20260810_111952",
        "tingkat": "84.4%",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 29,
        "gt": "v9",
        "date": "Aug 10",
        "is_winner": False,
        "notes": "PASS (prototipe/desain). Warm-up N=10/20/37: LLM calls 31→29 (−2, hit 2 key berulang), tingkat 84.4/81.5/81.1%. Korpus 74 hanya 2 key berulang → gain KB nyata butuh skala 36k. Konfig 1x vs 3x identik di korpus ini. `kb_design.md` = desain final.",
        "per_field_src": "tests/benchmark_runs/kb_warmup_20260810_111952/summary_kb_warmup.json",
    },
    {
        "id": "ood_001",
        "phase": "v10",
        "label": "OOD-001 probe mutation + noise (template & OCR noise injection)",
        "variant": "ood_v1",
        "run_dir": "tests/benchmark_runs/ood_probe_20260810_082401",
        "tingkat": "83.8%",
        "macro": "55.7%",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 10",
        "is_winner": False,
        "notes": "PASS (report-only). Baseline offline 55.7%. Mutation: MACRO -8.9pt tapi field bebas-institusi hanya -1.2pt (tingkat -4.1pt = riil); drop organizer & nomor = kontaminasi GT. Noise: 10% -8.6pt, 25% -16.4pt, 50% -24.2pt → batas praktis 10-25%. v9 lebih robust dari dugaan pada mutation.",
        "per_field_src": "tests/benchmark_runs/ood_probe_20260810_082401/summary.json",
    },
    {
        "id": "stat_001",
        "phase": "v10",
        "label": "STAT-001 validasi statistik 5-fold + bootstrap CI 1000×",
        "variant": "stat_fold",
        "run_dir": "tests/benchmark_runs/stat_validation_20260810_102024",
        "tingkat": "83.8%",
        "macro": "60.1%",
        "tokens_cert": 0,
        "calls": 29,
        "gt": "v9",
        "date": "Aug 10",
        "is_winner": False,
        "notes": "PASS. Router 45/74 @100% precision tervalidasi di fold. Semua 13 rule min-fold-precision 100%. 8/13 rule LOW-N (fire <5) → interval lebar. Bootstrap CI MACRO exact 56.0-64.4% (mean 60.1%), router coverage CI 50.0-71.6%. Temuan: snapshot router_decisions.json pakai organizer lama (6/74 beda).",
        "per_field_src": "tests/benchmark_runs/stat_validation_20260810_102024/summary.json",
    },
    {
        "id": "review_001",
        "phase": "v10",
        "label": "REVIEW-001 needs_review field lemah (confidence berbasis pola)",
        "variant": "needs_review",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 10",
        "is_winner": False,
        "notes": "PASS — recall 98.6% (68/69 wrong-cert ter-flag), FP = 1 cert. Per-field: nama_kegiatan recall 96.7% FP 80%, nomor recall 61.9% FP 0%. 73/74 cert ter-flag butuh review (trade-off: safety net vs biaya review). Keyword hardcode confidence terendah + kandidat KB.",
    },
    # --- Aug 10-11: KB experiments ---
    {
        "id": "kb_001_shadow",
        "phase": "kb",
        "label": "KB-001 shadow replay key v1 (router→KB→LLM)",
        "variant": "kb_shadow",
        "run_dir": "tests/benchmark_runs/kb_shadow_20260811_103552",
        "tingkat": "84.4%",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 29,
        "gt": "v9",
        "date": "Aug 10",
        "is_winner": False,
        "notes": "PASS (3x confirm). Key unik 55, key berulang 3 (9 cert). Hit 3 (semua exact vs GT), saved_llm 0, wrong 0, collision 0. Noise 10/25/50% wrong 0. 1x confirm = GATE FAIL (wrong 5 — error LLM label terkunci). Koreksi: mutasi WARMUP_CONFIRMS via package namespace TIDAK efektif.",
        "per_field_src": "tests/benchmark_runs/kb_shadow_20260811_103552/summary_kb_shadow.json",
    },
    {
        "id": "kb_002_seeded",
        "phase": "kb",
        "label": "KB-002 seeded persistent KB (smoke, ceiling, persistence, noise, fragmentasi)",
        "variant": "kb_seed",
        "run_dir": "tests/benchmark_runs/kb_seed_20260811_103804",
        "tingkat": "83.8%",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 29,
        "gt": "v9",
        "date": "Aug 11",
        "is_winner": False,
        "notes": "PASS. Ceiling seeded: 3 keys/9 cert, hit 9, saved_llm 0, wrong 0. Persistence: mem==persist identik (1x: hits 51/wrong 5, 3x: hits 3/wrong 0). Noise 25% wrong 0. Fragmentasi: 1 org logis terpecah 2 key (7 cert) → exact-match kehilangan hit. 1x confirm dilarang produksi.",
        "per_field_src": "tests/benchmark_runs/kb_seed_20260811_103804/summary_kb_seed.json",
    },
    {
        "id": "kb_003_norm_key",
        "phase": "kb",
        "label": "KB-003 normalisasi key v2 (plain/stem/alias/both)",
        "variant": "kb_norm",
        "run_dir": "tests/benchmark_runs/kb_norm_20260811_105237",
        "tingkat": "83.8%",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 29,
        "gt": "v9",
        "date": "Aug 11",
        "is_winner": False,
        "notes": "PASS. Plain: 55 key, 3 repeat, shadow hit 3. Stem/alias/both: 54 key, 2 repeat (FST pair menyatu), shadow hit 5 (+2), collision 0, wrong 0. Normalisasi key menaikkan hit 3→5 tanpa efek samping.",
        "per_field_src": "tests/benchmark_runs/kb_norm_20260811_105237/summary_kb_norm.json",
    },
    {
        "id": "kb_004_audit",
        "phase": "kb",
        "label": "KB-004 alat audit korpus (tests/kb/audit.py)",
        "variant": "kb_audit",
        "run_dir": "tests/benchmark_runs/kb_audit_20260811_105308",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 11",
        "is_winner": False,
        "notes": "PASS — selfcheck. Dry-run korpus 74: keys 55==55, repeated 3==3. Collision 0, saved_llm proyeksi 0. Alat siap dipakai pada korpus lintas fakultas. --variant stem/alias/both tersedia.",
    },
    {
        "id": "kb_005_event_type",
        "phase": "kb",
        "label": "KB-005 event_type=role terbaik (role/jenis/kelompok × 4 normalisasi)",
        "variant": "kb_event",
        "run_dir": "tests/benchmark_runs/kb_event_20260811_110636",
        "tingkat": "83.8%",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 29,
        "gt": "v9",
        "date": "Aug 11",
        "is_winner": False,
        "notes": "PASS (role). Role: collision 0, empty 13, repeat 3(9), shadow hit 3-5, wrong 0. Jenis: empty 52 (70% key mati!), collision 1, wrong 1 → TIDAK layak. Kelompok: repeat 5(14) TAPI collision 1, wrong 2 → GATE FAIL. Jawaban desain: role = event proxy cukup & paling aman.",
        "per_field_src": "tests/benchmark_runs/kb_event_20260811_110636/summary_kb_event.json",
    },
    {
        "id": "kb_006_alias_mining",
        "phase": "kb",
        "label": "KB-006 alias mining data-driven (auto-alias = manual)",
        "variant": "kb_alias",
        "run_dir": "tests/benchmark_runs/kb_alias_20260811_110930",
        "tingkat": "83.8%",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 29,
        "gt": "v9",
        "date": "Aug 11",
        "is_winner": False,
        "notes": "PASS. Mining menemukan FST pair (2/5 cert, valid=True). Auto-alias: keys 54, seeds 2, shadow hit 5 (= manual), wrong 0, noise 25% wrong 0. Auto-alias = alias manual di korpus ini (terotomasi tanpa kehilangan keamanan).",
        "per_field_src": "tests/benchmark_runs/kb_alias_20260811_110930/summary_kb_alias.json",
    },
    # --- Aug 13: ORG-005 + ACT-001 ---
    {
        "id": "org_005_probe",
        "phase": "v10",
        "label": "ORG-005 probe scoring extractor (sisa 12 kasus)",
        "variant": "org_scoring",
        "tingkat": "-",
        "macro": "63.5%",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 13",
        "is_winner": False,
        "notes": "FAIL (probe). Hanya 1/12 fixable murah (Hitech 'oleh Politeknik Caltex Riau'). Sisa 11 butuh rewrite scoring extractor (blast radius luas) dengan risiko regress (HIMASTA-expand regress 12). Full run TIDAK layak di korpus 74 tanpa GT baru.",
    },
    {
        "id": "akt_001_taxonomy",
        "phase": "v10",
        "label": "AKT-001 taksonomi nama_kegiatan (report-only, 6.8% exact)",
        "variant": "akt_taxonomy",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 13",
        "is_winner": False,
        "notes": "PASS (report-only). Exact 5/74 (6.8%). Taksonomi 69 non-exact: kosong 57 (52 GT muncul di teks → deteksi regex feasible), salah_kegiatan 4, kurang_lengkap 3, kelebihan 3, format_ocr 2. Masalah = DETEKSI, bukan normalisasi.",
    },
    # --- Aug 14: KB-SCALE + KB-PROD ---
    {
        "id": "kb_scale_001",
        "phase": "kb",
        "label": "KB-SCALE-001 simulasi workload skewed (500-5000 req)",
        "variant": "kb_scale_skew",
        "run_dir": "tests/benchmark_runs/kb_scale_20260814_151147",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 14",
        "is_winner": False,
        "notes": "PASS. 80/20 N=5000: saved_llm 87% (391/448 non-routed), hit 97%, wrong 2.8% < pipeline 19%. N=500: saved 12% → FAIL volume kecil (warmup menelan porsi besar). Est. latency saved ~978s/5000 req. 55/55 key authoritative.",
        "per_field_src": "tests/benchmark_runs/kb_scale_20260814_151147/summary_kb_scale.json",
    },
    {
        "id": "kb_scale_002",
        "phase": "kb",
        "label": "KB-SCALE-002 race tulis multi-worker (threading.Lock fix)",
        "variant": "kb_concurrency",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 14",
        "is_winner": False,
        "notes": "PASS. 8 thread × 500 write key sama paralel. Tanpa lock: confirms lost-update. Dengan lock: deterministik, 0 lost update. Test: key sama (8×500) + 20 key acak-deterministik (8×300). Lock global cukup di skala ini.",
    },
    {
        "id": "kb_scale_003",
        "phase": "kb",
        "label": "KB-SCALE-003 peta hemat (5 volume × 5 key space × 3 skew)",
        "variant": "kb_scale_map",
        "run_dir": "tests/benchmark_runs/kb_scale_map_20260814_153304",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 14",
        "is_winner": False,
        "notes": "PASS. 36k@80/20: saved 92% (1k key) / 78% (5k) / 72% (10k), semua ≥50%. Insight: hemat dari key POPULER (top-20% menampung 80% request). 36k/10k = 3.6 req/key rata-rata TAPI tetap 72%.",
        "per_field_src": "tests/benchmark_runs/kb_scale_map_20260814_153304/summary_kb_scale_map.json",
    },
    {
        "id": "kb_scale_004",
        "phase": "kb",
        "label": "KB-SCALE-004 confirm 2x vs 3x (wrong +20 @2x)",
        "variant": "kb_scale_conf",
        "run_dir": "tests/benchmark_runs/kb_scale_conf_20260814_153359",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 14",
        "is_winner": False,
        "notes": "FAIL — 3x confirm TETAP wajib. 2x: wrong 304 vs 3x 284 (+20 — error pipeline terkunci lebih cepat). Hemat N=500 naik (24% vs 5%) TAPI tidak sebanding. Alias: efek kecil.",
        "per_field_src": "tests/benchmark_runs/kb_scale_conf_20260814_153359/summary_kb_scale_conf.json",
    },
    {
        "id": "kb_scale_005",
        "phase": "kb",
        "label": "KB-SCALE-005 akurasi+biaya e2e (hemat 87%, akurasi 99.3%)",
        "variant": "kb_scale_e2e",
        "run_dir": "tests/benchmark_runs/kb_scale_e2e_20260814_153505",
        "tingkat": "-",
        "macro": "99.3%",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 14",
        "is_winner": False,
        "notes": "PASS. 80/20 N=5000: akurasi 96.3→99.3% (KB ≥ tanpa KB), hemat biaya 87% (57 vs 446 calls). KB = cache yang LEBIH akurat dari LLM (serve 97.2% vs fallback 58.6%).",
        "per_field_src": "tests/benchmark_runs/kb_scale_e2e_20260814_153505/summary_kb_scale_e2e.json",
    },
    {
        "id": "kb_prod_001",
        "phase": "kb",
        "label": "KB-PROD-001 semantik produksi (servable/resolve/audit_due)",
        "variant": "kb_prod",
        "tingkat": "-",
        "macro": "-",
        "tokens_cert": 0,
        "calls": 0,
        "gt": "v9",
        "date": "Aug 14",
        "is_winner": False,
        "notes": "PASS. servable() source-aware: AUTHORITATIVE_CONFIRMS={router_rule:3, llm:5, human_review:1} + TTL 365 hari. resolve() human review langsung authoritative. audit_due() prioritasi source=llm+conflicts>0. Pytest 60→64 passed, 0 regress. Gap produksi: PG atomic upsert, hit_count batch, gate data riil.",
    },
]


def main():
    with open(DATA) as f:
        data = json.load(f)

    existing_ids = {e["id"] for e in data["experiments"]}
    added = 0
    skipped = 0

    for exp in MISSING_EXPERIMENTS:
        if exp["id"] in existing_ids:
            skipped += 1
            continue

        # Find correct insertion point (chronological by date + phase)
        insert_idx = len(data["experiments"])
        for i, existing in enumerate(data["experiments"]):
            # Simple: insert KB experiments after all non-KB, before akt
            # Insert v10 experiments before akt_002
            if exp["phase"] == "kb" and existing["phase"] != "kb":
                if i < insert_idx:
                    insert_idx = i
            elif exp["phase"] == "v10" and existing.get("id", "").startswith("akt_"):
                if i < insert_idx:
                    insert_idx = i
            elif exp["phase"] in ("v8", "v9") and existing["phase"] in ("v10", "kb", "ocr"):
                if i < insert_idx:
                    insert_idx = i

        data["experiments"].insert(insert_idx, exp)
        existing_ids.add(exp["id"])
        added += 1
        print(f"  + {exp['id']}: {exp['label']}")

    with open(DATA, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nTotal: {len(data['experiments'])} experiments ({added} added, {skipped} skipped)")
    print(f"Updated: {DATA}")


if __name__ == "__main__":
    main()
