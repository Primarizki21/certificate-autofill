"""HYB-KB-001 — Efek KB pada pipeline HYB-LLM-001 (korpus 74, replay online).

Pertanyaan user (post-handoff v36): apakah KB harus masuk produksi dulu
sebelum dicampur HYB? TIDAK — eksperimen ini zero-touch produksi, sama
dengan KB-001..006/SCALE/PROD-001.

Alur diuji: ROUTER → KB → LLM (KB disisipkan antara router dan LLM fallback).
Label per cert = artefak HYB-LLM-001 (run 20260821_135619) — 0 LLM runtime:
- routed (48 cert)  → tingkat = combined (router rule), source=router_rule
- unrouted (26 cert) → tingkat = llm, source=llm

Replay ONLINE berurutan (non-concurrent): tiap cert cek KB dulu (servable(),
semantik produksi KB-PROD-001 — bukan `authoritative` legacy), miss → pakai
label pipeline + write ke KB. Warm-up alami, tanpa split tetap.

GATE:
- G1: tingkat exact dgn KB >= baseline HYB-LLM tanpa KB (no-regress).
- G2: wrong dari serve KB = 0 (KB tidak menambah salah).
Ekspektasi jujur: saved_llm = 0 — korpus hanya punya 3 key berulang
(≤3 kemunculan; servable butuh confirms>=3 SEBELUM hit → butuh ≥4 kemunculan
utk 1 hemat; label source=llm bahkan butuh 5). Nilai KB terlihat di skala —
ukur HYB-KB-002 (benchmark_hyb_kb_scale.py).

Usage:
  uv run python -m tests.benchmark_hyb_kb
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.kb.audit import pipeline_label
from tests.kb.kb import KBEntry, TingkatKB
from tests.matchers import match_field
from tests.ood_probe import load_texts

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PER_CERT = os.path.join(
    REPO, "tests", "benchmark_runs", "hyb_llm_20260821_135619", "per_cert_results.json")
OUT_DIR = os.path.join(REPO, "tests", "benchmark_runs", f"hyb_kb_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

KEY_VARIANT = "plain"  # konsisten KB-SCALE-001..005 (banding antar-eksperimen)


def load_hyb_certs(texts: dict[str, str]) -> list[dict]:
    """Satu record per cert: key, routed, label pipeline, source, gt."""
    with open(PER_CERT) as f:
        per_cert = {r["stem"]: r for r in json.load(f)}
    certs = []
    missing_key_count = 0
    for stem in sorted(per_cert):
        if stem not in texts:
            continue
        c = per_cert[stem]
        text = texts[stem]
        routed = c["router_decision"] != "unrouted"
        t = c["fields"]["tingkat"]
        label = t["combined"] if routed else t["llm"]
        gt = t["gt"]
        key = pipeline_label(stem, text, KEY_VARIANT)[0]
        if key is None:
            missing_key_count += 1
        certs.append({
            "stem": stem,
            "key": key,
            "routed": routed,
            "label": label or "Lainnya",
            "source": "router_rule" if routed else "llm",
            "gt": gt,
        })
    return certs, missing_key_count


def exact_tingkat(gt: str | None, value: str | None, cache: dict) -> bool:
    k = (gt, value)
    if k not in cache:
        cache[k] = bool(gt) and match_field(gt, value or "", "tingkat")["exact"]
    return cache[k]


def replay(certs: list[dict], use_kb: bool) -> dict:
    kb = TingkatKB()
    cache: dict = {}
    hits = saved = wrong = llm_calls = 0
    exact = 0
    for c in certs:
        final = None
        if use_kb and not c["routed"] and c["key"] is not None:
            # Alur produksi: router dulu (deterministik @100%); KB hanya
            # menggantikan LLM fallback di cert unrouted.
            entry = kb.peek(c["key"])
            if entry is not None and entry.servable(ttl_days=None):
                final = entry.tingkat
                hits += 1
                saved += 1
                if c["gt"] and not match_field(c["gt"], entry.tingkat, "tingkat")["exact"]:
                    wrong += 1
        if final is None:
            final = c["label"]
            if not c["routed"]:
                llm_calls += 1
            if use_kb and c["key"] is not None:
                kb.write(c["key"], KBEntry(c["label"], c["source"], c["stem"]))
        if exact_tingkat(c["gt"], final, cache):
            exact += 1
    return {
        "exact": exact,
        "n": len(certs),
        "hits": hits,
        "saved_llm": saved,
        "wrong_from_kb": wrong,
        "llm_calls": llm_calls,
        "kb_size": len(kb),
    }


def main() -> None:
    texts = load_texts()
    certs, missing_keys = load_hyb_certs(texts)
    base = replay(certs, use_kb=False)
    kbres = replay(certs, use_kb=True)

    g1 = kbres["exact"] >= base["exact"]
    g2 = kbres["wrong_from_kb"] == 0
    verdict = "PASS" if (g1 and g2) else "FAIL"

    print(f"certs={len(certs)} (key None: {missing_keys})")
    print(f"baseline tanpa KB : exact {base['exact']}/{base['n']} "
          f"({base['exact'] / base['n']:.1%}), llm_calls {base['llm_calls']}")
    print(f"dengan KB (servable): exact {kbres['exact']}/{kbres['n']} "
          f"({kbres['exact'] / kbres['n']:.1%}), hits {kbres['hits']}, "
          f"saved {kbres['saved_llm']}, wrong {kbres['wrong_from_kb']}, "
          f"llm_calls {kbres['llm_calls']}, kb_size {kbres['kb_size']}")
    print(f"G1 no-regress exact : {'PASS' if g1 else 'FAIL'}")
    print(f"G2 wrong dari KB = 0: {'PASS' if g2 else 'FAIL'}")
    print(f"VERDICT: {verdict}")

    os.makedirs(OUT_DIR, exist_ok=True)
    summary = {
        "experiment": "HYB-KB-001",
        "per_cert_artifact": PER_CERT,
        "key_variant": KEY_VARIANT,
        "certs": len(certs),
        "keys_missing": missing_keys,
        "baseline": base,
        "with_kb": kbres,
        "gate": {"g1_no_regress": g1, "g2_wrong_zero": g2, "verdict": verdict},
        "note": "servable() KB-PROD-001 (router_rule 3x / llm 5x); korpus hanya "
                "3 key berulang <=3 kemunculan → saved=0 adalah hasil yang "
                "diharapkan; efek KB diukur di skala (HYB-KB-002).",
    }
    with open(os.path.join(OUT_DIR, "summary_hyb_kb.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"wrote {OUT_DIR}/summary_hyb_kb.json")


if __name__ == "__main__":
    main()
