"""KB tingkat in-memory — prototipe opsi B (komposit key).

Key = (normalized_organizer, event_type). entry_level = tingkat terverifikasi.
Storage = dict in-memory (produksi = PostgreSQL, lihat docs/kb_design.md).

Design points (dari handoff v20):
- source enum: router_rule | llm | human_review (llm diaudit lebih sering)
- warm-up: butuh 2-3 konfirmasi konsisten sebelum authoritative
  → `confirms` bertambah tiap hit identik; entry authoritative saat confirms >= WARMUP_CONFIRMS
- hit_count, created_from_cert_id, last_verified_at untuk traceability
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

WARMUP_CONFIRMS = 3


@dataclass
class KBEntry:
    tingkat: str
    source: str  # router_rule | llm | human_review
    created_from_cert_id: str
    confidence: float = 0.8
    hit_count: int = 0
    confirms: int = 1
    conflicts: int = 0  # KB-001: key sama, tingkat beda → non-authoritative
    last_verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def authoritative(self) -> bool:
        # Konflik menurunkan status permanen sampai human review — jangan
        # pernah autofill dari entry yang labelnya pernah bertentangan.
        return self.confirms >= WARMUP_CONFIRMS and self.conflicts == 0


class TingkatKB:
    """Key = (normalized_organizer, event_type). Tidak ada key = (None, ...)."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str | None], KBEntry] = {}
        self._lock = threading.Lock()  # KB-SCALE-002: race multi-worker → lost update confirms

    def lookup(self, key: tuple[str, str | None]) -> KBEntry | None:
        with self._lock:
            entry = self._store.get(key)
            if entry:
                entry.hit_count += 1
            return entry

    def peek(self, key: tuple[str, str | None]) -> KBEntry | None:
        """Baca tanpa mutasi (shadow eval: tidak menghitung hit_count)."""
        with self._lock:
            return self._store.get(key)

    def write(self, key: tuple[str, str | None], entry: KBEntry) -> None:
        with self._lock:
            existing = self._store.get(key)
            if existing:
                if existing.tingkat == entry.tingkat:
                    existing.confirms += 1
                    existing.hit_count += 1
                else:
                    # Konflik: tingkat berbeda utk key sama. JANGAN timpa diam-diam —
                    # entry turun status non-authoritative (sampai human review).
                    existing.conflicts += 1
                existing.last_verified_at = entry.last_verified_at
                return
            self._store[key] = entry

    def __len__(self) -> int:
        return len(self._store)

    def items(self) -> list[tuple[tuple[str, str | None], KBEntry]]:
        """Snapshot view utk persistence (tests/kb/store.py)."""
        return list(self._store.items())


def _demo() -> None:
    kb = TingkatKB()
    key = ("BEM FTMM Universitas Airlangga", "Peserta")
    for _ in range(3):
        kb.write(key, KBEntry("Fakultas", "router_rule", "cert-1"))
    e = kb.lookup(key)
    assert e and e.authoritative, "3 confirm konsisten harus authoritative"
    assert e.tingkat == "Fakultas"
    # konflik: key sama, tingkat beda → non-authoritative, nilai asli dipertahankan
    kb.write(key, KBEntry("Nasional", "llm", "cert-2"))
    e = kb.lookup(key)
    assert e and not e.authoritative, "konflik harus non-authoritative"
    assert e.tingkat == "Fakultas" and e.conflicts == 1, "nilai asli tidak boleh ditimpa"
    # entry berbeda tetap authoritative setelah warm-up cukup
    other = ("BEM FEB UNAIR", "Peserta")
    for _ in range(3):
        kb.write(other, KBEntry("Fakultas", "router_rule", "cert-3"))
    assert kb.lookup(other).authoritative
    print("ok: kb.kb conflict semantics")


if __name__ == "__main__":
    _demo()
