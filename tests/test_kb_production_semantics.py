"""KB-PROD-001 — Semantik produksi: servable (source-aware + TTL), resolve,
audit_due. `authoritative` tetap legacy (eksperimen KB-001..006/SCALE memakainya);
produksi wajib cek `servable` (handoff v36).

Catatan: `authoritative` TIDAK berubah — angka eksperimen lama tetap valid.
"""

from tests.kb.kb import KBEntry, TingkatKB


def test_servable_source_aware_llm_needs_more_confirms():
    kb = TingkatKB()
    key = ("HIMA SI UNAIR", "Peserta")
    for _ in range(3):
        kb.write(key, KBEntry("Departemen/Program Studi", "llm", "c"))
    e = kb.lookup(key)
    assert e.authoritative, "legacy: 3x authoritative"
    assert not e.servable(), "produksi: llm 3x belum servable (butuh 5)"
    for _ in range(2):
        kb.write(key, KBEntry("Departemen/Program Studi", "llm", "c"))
    assert kb.lookup(key).servable(), "llm 5x konsisten harus servable"


def test_servable_human_review_immediate_and_ttl():
    kb = TingkatKB()
    key = ("BEM FEB UNAIR", "Peserta")
    resolved = kb.resolve(key, "Fakultas", reviewer="reviewer-1")
    assert resolved.servable(), "human review harus langsung servable"
    stale = ("UKM X", "Peserta")
    for _ in range(3):
        kb.write(stale, KBEntry("Lainnya", "router_rule", "c"))
    stale_entry = kb.lookup(stale)
    stale_entry.last_verified_at = "2020-01-01T00:00:00+00:00"
    assert not stale_entry.servable(ttl_days=365), "basi harus non-servable"
    assert stale_entry.servable(ttl_days=None), "TTL None = tanpa batas"


def test_resolve_unblocks_conflicted_entry():
    kb = TingkatKB()
    key = ("BEM FTMM Universitas Airlangga", "Peserta")
    for _ in range(3):
        kb.write(key, KBEntry("Fakultas", "router_rule", "c1"))
    kb.write(key, KBEntry("Nasional", "llm", "c2"))
    e = kb.lookup(key)
    assert e and not e.authoritative and not e.servable(), "konflik = mati"
    resolved = kb.resolve(key, "Fakultas", reviewer="reviewer-2")
    assert resolved.conflicts == 0 and resolved.source == "human_review"
    assert resolved.servable(), "resolve harus membuka kembali entry"


def test_audit_due_prioritizes_llm_and_conflict():
    kb = TingkatKB()
    kb.write(("A", "Peserta"), KBEntry("Fakultas", "router_rule", "c1"))
    kb.write(("B", "Peserta"), KBEntry("Nasional", "llm", "c2"))
    kb.write(("C", "Peserta"), KBEntry("Fakultas", "router_rule", "c3"))
    kb.write(("C", "Peserta"), KBEntry("Universitas", "llm", "c4"))
    due = kb.audit_due()
    assert all(kv[1].source == "llm" or kv[1].conflicts > 0 for kv in due), due
    keys = {k[0] for k, _ in due}
    assert "B" in keys and "C" in keys and "A" not in keys, keys
