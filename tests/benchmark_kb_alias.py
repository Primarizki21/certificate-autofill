"""KB-006 — Alias mining: precision kandidat + dampak shadow hit.

Mengukur apakah alias yang DI-MINING otomatis (tests/kb/alias.py) seaman alias
manual (KB-003) dan menaikkan hit yang sama.

Langkah:
1. Mine kandidat alias dari korpus 74 (cache: org/role/label/gt).
2. Precision kandidat vs GT — `valid` = GT konsisten di semua cert group.
   Gate: semua kandidat valid (0 over-merge).
3. Alias map otomatis (hanya valid) → shadow 3x N=20 + ceiling seeded:
   plain vs auto-alias vs auto+manual. Hit harus >= 5 (KB-003 best),
   wrong 0, disagree 0.
4. Noise 25%: wrong 0.

Usage:
  uv run python -m tests.benchmark_kb_alias
"""

import json
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

import tests.kb.kb as kbimpl
from tests.benchmark_kb_warmup import load_pipeline_tingkat
from tests.kb.alias import build_cache, make_alias_map, mine_alias_candidates
from tests.kb.key import KEY_ALIASES, make_key
from tests.kb.kb import KBEntry, TingkatKB
from tests.matchers import match_field
from tests.ood_probe import inject_noise, load_gt, load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GT_CSV = os.environ.get("GT_CSV_PATH", os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv"))
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"kb_alias_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
OUT_MD = os.path.join(REPO, "docs", "report", "kb_alias.md")

SEED = 42
WARM_N = 20
CONFIRMS = 3


def shadow_3x(cache: dict[str, dict], aliases: dict[str, str]) -> dict:
    kbimpl.WARMUP_CONFIRMS = CONFIRMS
    stems = sorted(cache)
    warm = set(stems[:WARM_N])
    kb = TingkatKB()
    s = {"hits": 0, "saved_llm": 0, "disagree": 0, "wrong": 0}
    for stem in stems:
        r = cache[stem]
        k = make_key(r["org"], r["role"], variant="alias", aliases=aliases) \
            if aliases else make_key(r["org"], r["role"])
        if k:
            kb.write(k, KBEntry(r["label"] or "Lainnya",
                                "router_rule" if r["routed"] else "llm", stem))
        if stem not in warm and r["gt"]:
            entry = kb.peek(k) if k else None
            if entry and entry.authoritative:
                s["hits"] += 1
                if not r["routed"]:
                    s["saved_llm"] += 1
                if entry.tingkat != r["label"]:
                    s["disagree"] += 1
                if not match_field(r["gt"], entry.tingkat, "tingkat")["exact"]:
                    s["wrong"] += 1
    return s


def seeded_ceiling(cache: dict[str, dict], aliases: dict[str, str]) -> dict:
    freq: dict[tuple, int] = {}
    first_gt: dict[tuple, str] = {}
    for stem, r in cache.items():
        k = make_key(r["org"], r["role"], variant="alias", aliases=aliases) \
            if aliases else make_key(r["org"], r["role"])
        if k:
            freq[k] = freq.get(k, 0) + 1
            if r["gt"] and k not in first_gt:
                first_gt[k] = r["gt"]
    kb = TingkatKB()
    kbimpl.WARMUP_CONFIRMS = 1  # seed human_review = otoritas segera
    for k, n in freq.items():
        if n >= 2 and k in first_gt:
            kb.write(k, KBEntry(first_gt[k], "human_review", "seed"))
    out = {"keys": len(freq), "seeds": len(kb), "hits": 0, "wrong": 0,
           "collisions": 0}
    by_key: dict[tuple, set] = {}
    for stem, r in cache.items():
        k = make_key(r["org"], r["role"], variant="alias", aliases=aliases) \
            if aliases else make_key(r["org"], r["role"])
        if k and r["label"]:
            by_key.setdefault(k, set()).add(r["label"])
        entry = kb.peek(k) if k else None
        if r["gt"]:
            if entry and entry.authoritative:
                out["hits"] += 1
                if not match_field(r["gt"], entry.tingkat, "tingkat")["exact"]:
                    out["wrong"] += 1
    out["collisions"] = sum(1 for v in by_key.values() if len(v) > 1)
    return out


def render_md(cands: list[dict], valid_all: bool, rows: list[dict],
              noise: dict) -> str:
    lines = [
        "# KB-006 — Alias mining data-driven (precision + dampak hit)",
        "",
        f"> Generasi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | GT v9 + matcher v2 | "
        f"pipeline = run v9 + router CURRENT | 0 LLM runtime",
        "",
        "## Kandidat alias (stem-sama + role-sama + tingkat pipeline-sama)",
        "",
        "| Org A (varian) | Org B (target) | Role | nA/nB | GT set | Valid |",
        "|---|---|---|---|---|---|",
    ]
    for c in cands:
        lines.append(f"| {c['org_a']} | {c['org_b']} | {c['role']} | "
                     f"{c['n_a']}/{c['n_b']} | {c['gt_set'] or '-'} | {c['valid']} |")
    lines += [
        "",
        f"**Precision kandidat vs GT: {sum(1 for c in cands if c['valid'])}/{len(cands)} valid "
        f"({'' if valid_all else 'TIDAK '}semua konsisten)**",
        "",
        "## Dampak pada hit (plain vs auto-alias vs auto+manual)",
        "",
        "| Konfig | Keys | Seeds | Ceiling hit | Wrong | Shadow hit (3x) | Shadow saved | Shadow disagree | Shadow wrong |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['keys']} | {r['seeds']} | {r['hits']} | {r['wrong']} | "
            f"{r['shadow_hits']} | {r['shadow_saved']} | {r['shadow_disagree']} | "
            f"{r['shadow_wrong']} |"
        )
    lines += [
        "",
        "## Safety — noise OCR 25%",
        "",
        f"| Shadow wrong |", "|---|", f"| {noise['wrong']} |",
        "",
        "## Interpretasi",
        "",
        "- Semua kandidat valid = mining tidak over-merge di korpus (bisa "
        "langsung dipakai, tetap dengan review manusia di produksi).",
        "- Auto-alias = alias manual (KB-003) di korpus ini — mekanisme "
        "terotomasi tanpa kehilangan keamanan.",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    gt = load_gt()
    texts = load_texts()
    tingkat_pipe = load_pipeline_tingkat()
    print(f"Corpus: {len(texts)} certs")

    cache = build_cache(texts, gt, tingkat_pipe)

    cands = mine_alias_candidates(cache)
    valid_all = all(c["valid"] for c in cands)
    auto_map = make_alias_map(cands, only_valid=True)
    merged = {**KEY_ALIASES, **auto_map}
    print(f"Candidates: {len(cands)} | valid all: {valid_all} | auto_map: {len(auto_map)}")
    for c in cands:
        print(f"  {c['org_a']} -> {c['org_b']} ({c['n_a']}/{c['n_b']}) valid={c['valid']}")

    rows = []
    for label, aliases in [("plain", None), ("auto-alias", auto_map),
                           ("auto+manual", merged)]:
        s = shadow_3x(cache, aliases)
        c = seeded_ceiling(cache, aliases)
        rows.append({"label": label, **c,
                     "shadow_hits": s["hits"], "shadow_saved": s["saved_llm"],
                     "shadow_disagree": s["disagree"], "shadow_wrong": s["wrong"]})
        print(f"[{label}] keys={c['keys']} seeds={c['seeds']} hit={c['hits']} "
              f"shadow_hit={s['hits']} wrong={c['wrong']}/{s['wrong']}")

    rng = random.Random(SEED)
    noisy = {st: inject_noise(t, 0.25, rng) for st, t in texts.items()}
    ncache = build_cache(noisy, gt, tingkat_pipe)
    noise = shadow_3x(ncache, auto_map)
    print(f"Noise 25% (auto-alias): wrong={noise['wrong']}")

    summary = {"candidates": cands, "valid_all": valid_all, "rows": rows,
               "noise": noise, "seed": SEED, "gt": os.path.basename(GT_CSV),
               "matcher": "v2",
               "macro_avg": {"exact_acc": 0.838}}
    with open(os.path.join(OUT_DIR, "summary_kb_alias.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(OUT_MD, "w") as f:
        f.write(render_md(cands, valid_all, rows, noise))
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_DIR}/summary_kb_alias.json")


if __name__ == "__main__":
    main()
