"""KB-SCALE-002 — Race tulis multi-worker (produksi = beberapa worker).

Tanpa lock: 2+ thread tulis key sama → lost update pada `confirms` → entry
tidak pernah authoritative walau sudah 3x, atau conflict palsu. Produksi
multi-worker (api + db_worker) butuh write aman.

Fix: threading.Lock per TingkatKB di tests/kb/kb.py.
"""

import threading

from tests.kb.kb import KBEntry, TingkatKB

THREADS = 8
WRITES_PER_THREAD = 500


def _hammer(kb: TingkatKB, key: tuple, n: int, barrier: threading.Barrier) -> None:
    barrier.wait()
    for _ in range(n):
        kb.write(key, KBEntry("Fakultas", "router_rule", "t"))


def test_race_same_key_no_lost_update():
    kb = TingkatKB()
    key = ("BEM FTMM Universitas Airlangga", "Peserta")
    barrier = threading.Barrier(THREADS)
    threads = [threading.Thread(target=_hammer, args=(kb, key, WRITES_PER_THREAD, barrier))
               for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    e = kb.lookup(key)
    assert e is not None
    assert e.confirms == THREADS * WRITES_PER_THREAD, (
        f"lost update: confirms={e.confirms}, expected {THREADS * WRITES_PER_THREAD}")
    assert e.authoritative


def test_race_many_keys_deterministic():
    keys = [("Org-%d" % i, "Peserta") for i in range(20)]
    kb = TingkatKB()
    barrier = threading.Barrier(THREADS)
    errors: list[BaseException] = []

    def hammer():
        try:
            barrier.wait()
            for _ in range(300):
                for k in keys:
                    kb.write(k, KBEntry("Fakultas", "router_rule", "t"))
        except BaseException as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=hammer) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    expected = {k: THREADS * 300 for k in keys}
    got = {k: e.confirms for k, e in kb.items()}
    assert got == expected, f"lost update: {got} != {expected}"
