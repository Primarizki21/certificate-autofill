"""KB-006 — Alias mining data-driven (prototipe, tests only).

Masalah (KB-002): exact-match memecah 1 org logis jadi 2 key (FST DEPT,
"INFORMATION SYSTEMS DEPT" vs "Information System Dept.", 7 cert) → hit turun.
Alias manual (KB-003) hanya 1 baris; data riil butuh otomasi.

Kandidat alias = pasangan plain-key dengan:
- stem-org SAMA (case/punct/plural-collapse, `_stem_org`)
- role SAMA
- tingkat PIPELINE SAMA
→ kedua org label adalah varian format dari organisasi yang sama.

Precision vs GT: kandidat VALID bila semua cert di kedua varian punya GT
tingkat yang sama (GT kosong di-skip). Kandidat INVALID (over-merge) bila ada
dua GT berbeda di dalam group.

Output:
- `mine_alias_candidates(cache)` → daftar kandidat + precision per kandidat
- `make_alias_map(candidates)` → {org_a → org_b} (b = varian terbanyak)

Usage:
  uv run python -m tests.kb.alias
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from app.services.field_extractor import extract_certificate_fields
from tests.kb.key import _stem_org, normalize_organizer, normalize_role
from tests.llm_router_v4 import route_tingkat_trace
from tests.organizer_extractor_v2 import extract_organizer_v2


def build_cache(texts: dict[str, str], gt: dict[str, dict],
                tingkat_pipe: dict[str, str]) -> dict[str, dict]:
    """Satu ekstraksi per cert: {org, role, label, routed, gt}."""
    rows = {}
    for stem in sorted(texts):
        text = texts[stem]
        extracted = extract_certificate_fields(text)
        org_raw = extract_organizer_v2(text)
        rv = extracted.get("raw_role")
        role_raw = rv.value if rv and rv.value else None
        decision, _ = route_tingkat_trace(text, org_raw or "")
        label = decision if decision else tingkat_pipe.get(stem)
        gv = (gt.get(stem) or {}).get("tingkat") or ""
        rows[stem] = {
            "org": normalize_organizer(org_raw, text),
            "role": normalize_role(role_raw),
            "label": label,
            "routed": decision is not None,
            "gt": gv.strip() if gv.strip() and gv.strip() != "-" else None,
        }
    return rows


def mine_alias_candidates(cache: dict[str, dict]) -> list[dict]:
    """Kandidat alias dari group (stem_org, role) dengan >1 org label.

    Kandidat: {org_a, org_b (varian terbanyak), role, tingkat, n_a, n_b,
    valid (GT konsisten di semua cert group)}.
    """
    groups: dict[tuple[str, str], dict[str, int]] = {}
    gt_by_group: dict[tuple[str, str], set] = {}
    for r in cache.values():
        if not r["org"] or not r["role"] or not r["label"]:
            continue
        g = (_stem_org(r["org"]), r["role"])
        counts = groups.setdefault(g, {})  # dua baris: RHS dievaluasi SEBELUM setdefault
        counts[r["org"]] = counts.get(r["org"], 0) + 1
        if r["gt"]:
            gt_by_group.setdefault(g, set()).add(r["gt"])

    out = []
    for (stem_org, role), counts in sorted(groups.items()):
        if len(counts) < 2:
            continue
        org_b = max(counts, key=lambda o: counts[o])
        for org_a, n_a in counts.items():
            if org_a == org_b:
                continue
            n_b = counts[org_b]
            gts = gt_by_group.get((stem_org, role), set())
            valid = len(gts) <= 1  # semua GT konsisten (atau tanpa GT)
            out.append({
                "org_a": org_a, "org_b": org_b, "role": role,
                "n_a": n_a, "n_b": n_b, "total": n_a + n_b,
                "gt_set": sorted(gts), "valid": valid,
            })
    out.sort(key=lambda c: -c["total"])
    return out


def make_alias_map(candidates: list[dict], only_valid: bool = True) -> dict[str, str]:
    """{org_a → org_b} utk make_key(..., aliases=...)."""
    return {c["org_a"]: c["org_b"] for c in candidates if (not only_valid or c["valid"])}


def _demo() -> None:
    # group sintetis: 2 varian format org, GT sama → valid
    cache = {
        "a1": {"org": "BEM FTMM Universitas Airlangga", "role": "Peserta",
               "label": "Fakultas", "gt": "Fakultas"},
        "a2": {"org": "BEM FTMM Universita Airlangga", "role": "Peserta",
               "label": "Fakultas", "gt": "Fakultas"},
        "b1": {"org": "Himastat Universitas Airlangga", "role": "Ketua",
               "label": "Departemen/Program Studi", "gt": "Departemen/Program Studi"},
        "b2": {"org": "HIMASTAT Universitas Airlangga", "role": "Ketua",
               "label": "Departemen/Program Studi", "gt": "Departemen/Program Studi"},
    }
    cands = mine_alias_candidates(cache)
    assert len(cands) == 2, cands
    assert all(c["valid"] for c in cands)
    m = make_alias_map(cands)
    assert m.get("BEM FTMM Universita Airlangga") == "BEM FTMM Universitas Airlangga", m
    # GT tidak konsisten → invalid (over-merge risk)
    cache["a2"]["gt"] = "Nasional"
    cands2 = mine_alias_candidates(cache)
    a = [c for c in cands2 if "Universita" in c["org_a"]][0]
    assert not a["valid"] and a["gt_set"] == ["Fakultas", "Nasional"], a
    assert "Universita" not in make_alias_map(cands2), "kandidat invalid tak boleh dipakai"
    print("ok: kb.alias mining")


if __name__ == "__main__":
    _demo()
