"""Persistence JSON untuk TingkatKB — prototipe (tests only, produksi = PG).

Snapshot format: {"key_version", "entries": {key_str: {KBEntry fields}}}.
- key_str = "|".join(key) — aman utk v1 (org/role tidak memuat "|").
- key_version di-cek saat load: normalizer berubah → snapshot lama DITOLAK
  (bukan di-silent-mix).
- `save_kb`/`load_kb` dipakai benchmark_kb_seed (KB-002) utk membuktikan KB
  bisa disimpan antar-run dan hasil evaluasi identik dgn in-memory.

Usage:
  uv run python -m tests.kb.store
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from tests.kb.kb import KBEntry, TingkatKB
from tests.kb.key import KEY_VERSION


def _key_to_str(key: tuple[str, str | None, str]) -> str:
    return "|".join(key)


def _key_from_str(s: str) -> tuple[str, str | None, str]:
    parts = s.split("|")
    return (parts[0], parts[1], parts[2])


def save_kb(kb: TingkatKB, path: str) -> None:
    data = {
        "key_version": KEY_VERSION,
        "entries": {
            _key_to_str(k): entry.__dict__ for k, entry in kb.items()
        },
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_kb(path: str) -> TingkatKB:
    with open(path) as f:
        data = json.load(f)
    if data.get("key_version") != KEY_VERSION:
        raise ValueError(
            f"key version mismatch: snapshot {data.get('key_version')!r} != {KEY_VERSION!r} "
            f"— normalizer berubah, snapshot tidak bisa dicampur."
        )
    kb = TingkatKB()
    for key_str, fields in data["entries"].items():
        kb._store[_key_from_str(key_str)] = KBEntry(**fields)
    return kb


def _demo() -> None:
    k1 = ("BEM FTMM Universitas Airlangga", "Peserta", KEY_VERSION)
    kb = TingkatKB()
    kb.write(k1, KBEntry("Fakultas", "human_review", "seed-1"))
    for _ in range(2):
        kb.write(k1, KBEntry("Fakultas", "human_review", "seed-1"))
    kb.write(("BEM FEB UNAIR", "Peserta", KEY_VERSION), KBEntry("Fakultas", "router_rule", "cert-x"))

    path = os.path.join(os.path.dirname(__file__), "_snapshot_demo.json")
    save_kb(kb, path)
    kb2 = load_kb(path)
    assert len(kb) == len(kb2), "round-trip harus identik ukuran"
    for k, e in kb.items():
        e2 = kb2.peek(k)
        assert e2 and e2.tingkat == e.tingkat and e2.confirms == e.confirms \
            and e2.authoritative == e.authoritative and e2.conflicts == e.conflicts, k
    os.remove(path)
    print("ok: kb.store persistence round-trip")


if __name__ == "__main__":
    _demo()
