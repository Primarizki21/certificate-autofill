"""HYB-KB-002 — Proyeksi skala ril HYB+KB: N≈360.000 request non-concurrent.

Lanjutan HYB-KB-001 (korpus 74: mekanisme aman tapi saved=0 karena korpus
pembatas). Eksperimen ini memodelkan workload ril yang disebut user:
~360.000 request KHP, NON-CONCURRENT (berurutan — race multi-worker sudah
ditutup KB-SCALE-002), KB persist antar periode.

Parameter TERUKUR dari artefak HYB-LLM-001 (run 20260821_135619):
- router share 48/74 @100% precision (routed → tanpa LLM)
- LLM benar 17/26 pada unrouted (fallback llama3.1:8b)
- token/call ≈176, latensi ≈1.5 s/call

Semantik produksi: hit hanya saat `servable()` (KB-PROD-001: router_rule 3x,
llm 5x, konflik tidak pernah dilayani). TTL dimodelkan harness-side
(kb.py tak disentuh): entry basi (>TTL hari sejak write terakhir) → miss →
LLM fallback → write menyegarkan last_verified_at — persis perilaku
produksi (lookup tidak merefresh timestamp, write ya).

Grid: key space {1k, 5k, 10k, 50k} x skew {70/30, 80/20, 90/10} x
TTL {tanpa, 365 hari} pada horizon 1095 hari (~3 thn). Key sintetis meng-clone
profil korpus (tingkat/gt/routed) supaya inherited-error realistis.

GATE (N=360k, keys=10k, skew 80/20, TTL tanpa):
- hemat LLM calls >= 50%
- akurasi dgn KB >= tanpa KB

Usage:
  uv run python -m tests.benchmark_hyb_kb_scale            # N=360000
  KB_SCALE_N=50000 uv run python -m tests.benchmark_hyb_kb_scale   # trial cepat
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.benchmark_kb_scale import SEED, TOP_SHARE, alpha_for_skew
from tests.kb.kb import KBEntry, TingkatKB
from tests.matchers import match_field

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PER_CERT = os.path.join(
    REPO, "tests", "benchmark_runs", "hyb_llm_20260821_135619", "per_cert_results.json")
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"hyb_kb_scale_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "hyb_kb_scale.md")

N_REQUESTS = int(os.environ.get("KB_SCALE_N", 360_000))
KEY_SPACES = [1_000, 5_000, 10_000, 50_000]
HORIZON_DAYS = 1095        # ~3 tahun pemakaian
SKEWS = [0.70, 0.80, 0.90]
TTLS = [None, 365]          # hari; None = tanpa kedaluwarsa (batas atas hemat)
TOKENS_CALL = 176           # terukur v9/HYB eff tok/cert
LLM_SECONDS = 1.5           # terukur HYB-LLM-001 (1.5s/cert)
N_GATE = 360_000
KEYS_GATE = 10_000
SKEW_GATE = 0.80


def load_profiles() -> tuple[list[dict], float, float]:
    """Profil (tingkat, gt, routed) per cert dari artefak HYB + angka terukur."""
    with open(PER_CERT) as f:
        per_cert = json.load(f)
    profiles = []
    routed_n = 0
    unrouted_llm_ok = 0
    unrouted_n = 0
    for c in per_cert:
        routed = c["router_decision"] != "unrouted"
        t = c["fields"]["tingkat"]
        label = t["combined"] if routed else t["llm"]
        profiles.append({
            "label": label or "Lainnya",
            "source": "router_rule" if routed else "llm",
            "gt": t["gt"],
            "routed": routed,
        })
        if routed:
            routed_n += 1
        else:
            unrouted_n += 1
            if t["llm_match"] == "exact":
                unrouted_llm_ok += 1
    return profiles, routed_n / len(per_cert), unrouted_llm_ok / unrouted_n


def synthetic_keys(n_keys: int, profiles: list[dict], rng: random.Random) -> tuple[dict, dict]:
    """Key sintetis: nama unik, profil di-clone dari korpus (inherited error riil)."""
    keys, freqs = {}, {}
    for i in range(n_keys):
        p = profiles[rng.randrange(len(profiles))]
        k = (f"Org-{i}", "Peserta")
        keys[k] = {"tingkat": p["label"], "routed": p["routed"], "gt": p["gt"],
                   "source": p["source"]}
        freqs[k] = 1.0 / (i + 1)
    return keys, freqs


def replay(keys: dict, freqs: dict, alpha: float, n: int,
           ttl_days: int | None, llm_acc: float, rng: random.Random) -> dict:
    """Replay non-concurrent ROUTER→KB→LLM dengan semantik servable + TTL harness-side."""
    kb = TingkatKB()
    order = sorted(keys, key=lambda k: -freqs[k])
    weights = [freqs[k] ** alpha for k in order]
    requests = rng.choices(order, weights=weights, k=n)
    write_day: dict = {}
    exact_cache: dict = {}
    routed_total = non_routed_total = saved = wrong = misses = 0
    for i, key in enumerate(requests):
        r = keys[key]
        day = HORIZON_DAYS * i / n
        if r["routed"]:
            routed_total += 1
        else:
            non_routed_total += 1
        # Alur produksi: router SELALU menang (deterministik @100% terukur).
        # KB hanya menggantikan LLM fallback di request unrouted — melayani
        # request routed berarti menimpa jawaban router dgn error turunan KB.
        entry = kb.peek(key) if not r["routed"] else None
        served = False
        if entry is not None and entry.servable(ttl_days=None):
            stale = ttl_days is not None and day - write_day.get(key, day) > ttl_days
            if not stale:
                served = True
                saved += 1
                ck = (r["gt"], entry.tingkat)
                if ck not in exact_cache:
                    exact_cache[ck] = bool(r["gt"]) and not match_field(
                        r["gt"], entry.tingkat, "tingkat")["exact"]
                if exact_cache[ck]:
                    wrong += 1
        if not served:
            if not r["routed"]:
                misses += 1
        kb.write(key, KBEntry(r["tingkat"], r["source"], "workload"))
        write_day[key] = day
    return {
        "n": n,
        "ttl": ttl_days,
        "routed_total": routed_total,
        "non_routed_total": non_routed_total,
        "saved_llm": saved,
        "misses": misses,
        "wrong_hits": wrong,
        "calls_nokb": non_routed_total,
        "calls_kb": misses,
        "saved_pct": saved / non_routed_total if non_routed_total else 0.0,
        "acc_nokb": (routed_total + (non_routed_total) * llm_acc) / n,
        "acc_kb": (routed_total + saved - wrong + misses * llm_acc) / n,
        "hours_saved": saved * LLM_SECONDS / 3600,
        "tokens_saved": saved * TOKENS_CALL,
    }


def main() -> None:
    profiles, routed_share, llm_acc = load_profiles()
    print(f"profil korpus: {len(profiles)} cert | router {routed_share:.1%} | "
          f"LLM benar (unrouted) {llm_acc:.1%} | N={N_REQUESTS}")
    results = {}
    for skew in SKEWS:
        for nk in KEY_SPACES:
            rng = random.Random(SEED)
            keys, freqs = synthetic_keys(nk, profiles, rng)
            alpha = alpha_for_skew(keys, freqs, skew)
            for ttl in TTLS:
                rng2 = random.Random(SEED)
                r = replay(keys, freqs, alpha, N_REQUESTS, ttl, llm_acc, rng2)
                results[(nk, skew, ttl)] = r
                print(f"keys={nk:>6} skew={skew:.0%} ttl={str(ttl):>3}: "
                      f"hemat {r['saved_pct']:.1%} | akurasi "
                      f"{r['acc_nokb']:.3f}->{r['acc_kb']:.3f} | "
                      f"wrong {r['wrong_hits']}")

    g = results[(KEYS_GATE, SKEW_GATE, None)]
    gate1 = g["saved_pct"] >= 0.50
    gate2 = g["acc_kb"] >= g["acc_nokb"]
    verdict = "PASS" if (gate1 and gate2) else "FAIL"
    print(f"GATE (keys={KEYS_GATE}, skew={SKEW_GATE:.0%}, tanpa TTL): "
          f"hemat {g['saved_pct']:.1%} ({'PASS' if gate1 else 'FAIL'}), "
          f"akurasi {g['acc_nokb']:.3f}->{g['acc_kb']:.3f} "
          f"({'PASS' if gate2 else 'FAIL'}) → {verdict}")

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {
        "experiment": "HYB-KB-002",
        "n_requests": N_REQUESTS,
        "horizon_days": HORIZON_DAYS,
        "routed_share_measured": routed_share,
        "llm_acc_measured": llm_acc,
        "tokens_call": TOKENS_CALL,
        "llm_seconds": LLM_SECONDS,
        "results": {
            f"{nk}_{int(s * 100)}_{ttl or 'none'}": r
            for (nk, s, ttl), r in results.items()
        },
        "gate": {
            "config": {"keys": KEYS_GATE, "skew": SKEW_GATE, "ttl": None},
            "saved_pct": g["saved_pct"],
            "gate_saved_ge_50pct": gate1,
            "acc_no_kb": g["acc_nokb"],
            "acc_kb": g["acc_kb"],
            "gate_acc_no_regress": gate2,
            "verdict": verdict,
        },
    }
    with open(os.path.join(OUT_DIR, "summary_hyb_kb_scale.json"), "w") as f:
        json.dump(payload, f, indent=2)
    render_md(payload)
    print(f"wrote {OUT_DIR}/summary_hyb_kb_scale.json")


def render_md(p: dict) -> None:
    def row(nk: int, skew: float, ttl) -> str:
        r = p["results"][f"{nk}_{int(skew * 100)}_{ttl or 'none'}"]
        return (f"| {nk:,} | {skew:.0%} | {'—' if ttl is None else ttl} "
                f"| {r['saved_pct']:.1%} | {r['wrong_hits']:,} "
                f"| {r['acc_nokb']:.1%} | {r['acc_kb']:.1%} "
                f"| {r['calls_kb']:,} | {r['hours_saved']:,.0f} jam |")

    lines = [
        "# HYB-KB-002 — Proyeksi skala ril HYB+KB (~360k request, non-concurrent)",
        "",
        f"> Generasi: {datetime.now():%Y-%m-%d %H:%M:%S} | SEED={SEED} | "
        f"N={p['n_requests']:,} | horizon {p['horizon_days']} hari | 0 LLM runtime",
        "",
        f"**Terukur dari HYB-LLM-001:** router {p['routed_share_measured']:.1%} "
        f"(48/74 @100%) | LLM benar {p['llm_acc_measured']:.1%} (17/26 unrouted) | "
        f"{p['tokens_call']} tok/call | {p['llm_seconds']} s/call. Hit hanya dari "
        "`servable()` (router_rule 3x / llm 5x); TTL dimodelkan harness-side.",
        "",
        "## Grid (hemat calls | wrong | akurasi tanpa→dgn KB | LLM calls dgn KB | jam terhemat)",
        "",
        "| Key space | Skew | TTL | Hemat | Wrong | Akurasi −KB | Akurasi +KB | Calls +KB | Hemat waktu |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for skew in SKEWS:
        for nk in KEY_SPACES:
            for ttl in TTLS:
                lines.append(row(nk, skew, ttl))
    g = p["gate"]
    lines += [
        "",
        "## GATE (key space 10k, skew 80/20, tanpa TTL)",
        "",
        f"- Hemat LLM calls **{g['saved_pct']:.1%}** >= 50% → "
        f"{'PASS' if g['gate_saved_ge_50pct'] else 'FAIL'}",
        f"- Akurasi dgn KB {g['acc_kb']:.1%} >= tanpa KB {g['acc_no_kb']:.1%} → "
        f"{'PASS' if g['gate_acc_no_regress'] else 'FAIL'}",
        f"- **VERDICT: {g['verdict']}**",
        "",
        "## Interpretasi",
        "",
        "- Non-concurrent berarti hemat calls = hemat waktu proses berurutan: "
        "tiap call 1.5 s (terukur). Kolom jam = total waktu proses yang dihemat.",
        "- Key space besar menekan hemat (warm-up menyebar); skew adalah penentu "
        "utama — konsisten KB-SCALE-003.",
        "- TTL 365 hari menurunkan hemat untuk key jarang (basi → refresh via "
        "LLM), key populer tetap segar karena write tiap miss.",
        "- Validasi akhir tetap `tests/kb/audit.py` pada data riil lintas "
        "fakultas sebelum port produksi (handoff v36 frontier #1).",
        "",
    ]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
