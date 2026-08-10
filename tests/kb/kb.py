"""KB tingkat in-memory — prototipe opsi B (komposit key).

Key = (normalized_organizer, event_type). entry_level = tingkat terverifikasi.
Storage = dict in-memory (produksi = PostgreSQL, lihat docs/kb_design.md).

Design points (dari handoff v20):
- source enum: router_rule | llm | human_review (llm diaudit lebih sering)
- warm-up: butuh 2-3 konfirmasi konsisten sebelum authoritative
  → `confirms` bertambah tiap hit identik; entry authoritative saat confirms >= WARMUP_CONFIRMS
- hit_count, created_from_cert_id, last_verified_at untuk traceability
"""

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
    last_verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def authoritative(self) -> bool:
        return self.confirms >= WARMUP_CONFIRMS


class TingkatKB:
    """Key = (normalized_organizer, event_type). Tidak ada key = (None, ...)."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str | None], KBEntry] = {}

    def lookup(self, key: tuple[str, str | None]) -> KBEntry | None:
        entry = self._store.get(key)
        if entry:
            entry.hit_count += 1
        return entry

    def write(self, key: tuple[str, str | None], entry: KBEntry) -> None:
        existing = self._store.get(key)
        if existing:
            if existing.tingkat == entry.tingkat:
                existing.confirms += 1
                existing.hit_count += 1
            else:
                existing.tingkat = entry.tingkat
                existing.confirms = 1
                existing.source = entry.source
                existing.created_from_cert_id = entry.created_from_cert_id
            existing.last_verified_at = entry.last_verified_at
            return
        self._store[key] = entry

    def __len__(self) -> int:
        return len(self._store)
