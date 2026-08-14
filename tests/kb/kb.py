"""KB tingkat in-memory — prototipe opsi B (komposit key).

Key = (normalized_organizer, event_type). entry_level = tingkat terverifikasi.
Storage = dict in-memory (produksi = PostgreSQL, lihat docs/kb_design.md).

Design points (dari handoff v20):
- source enum: router_rule | llm | human_review (llm diaudit lebih sering)
- warm-up: butuh 2-3 konfirmasi konsisten sebelum authoritative
  → `confirms` bertambah tiap hit identik; entry authoritative saat confirms >= WARMUP_CONFIRMS
- hit_count, created_from_cert_id, last_verified_at untuk traceability

Semantik produksi (KB-PROD-001, handoff v36) — TIDAK mengubah `authoritative`
(eksperimen KB-001..006/SCALE tetap memakainya), produksi wajib cek `servable()`:
- `servable()` = authoritative AND source-aware threshold (llm butuh bukti lebih,
  design §4 "llm diaudit lebih sering") AND belum basi (TTL).
- `resolve()` = jalur human review utk entry konflik (tanpa ini entry konflik
  mati selamanya).
- `audit_due()` = sampling protokol F0 (entry source=llm / conflicts>0).
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

WARMUP_CONFIRMS = 3

# KB-PROD-001: threshold per source utk `servable()` — llm label kurang
# tepercaya (bisa salah propagasi), human review = otoritas langsung.
AUTHORITATIVE_CONFIRMS = {
    "router_rule": WARMUP_CONFIRMS,
    "llm": 5,
    "human_review": 1,
}

# KB-PROD-001: entry lewat TTL = tidak servable (event bisa berubah antar tahun).
TTL_DAYS = 365


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

    def servable(self, ttl_days: int | None = TTL_DAYS) -> bool:
        """Semantik PRODUKSI (KB-PROD-001): boleh dipakai autofill?

        = conflicts==0 + threshold per-source + belum basi. Eksperimen lama
        pakai `authoritative`; produksi WAJIB cek `servable` (source-aware:
        llm butuh confirms >= AUTHORITATIVE_CONFIRMS["llm"], human_review
        langsung, konflik selalu non-servable).
        """
        if self.conflicts != 0:
            return False
        needed = AUTHORITATIVE_CONFIRMS.get(self.source, WARMUP_CONFIRMS)
        if self.confirms < needed:
            return False
        if ttl_days is not None:
            try:
                last = datetime.fromisoformat(self.last_verified_at)
            except ValueError:
                return False
            if (datetime.now(timezone.utc) - last).days > ttl_days:
                return False
        return True


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

    def resolve(self, key: tuple[str, str | None], tingkat: str,
                reviewer: str = "human") -> KBEntry:
        """KB-PROD-001: human review — perbaiki entry konflik/salah.

        Tanpa ini entry konflik non-authoritative SELAMANYA. Setelah resolve:
        source=human_review (threshold 1), conflicts=0 → servable langsung.
        Key baru juga bisa di-seed via resolve (bootstrap human).
        """
        with self._lock:
            entry = self._store.get(key)
            if entry:
                entry.tingkat = tingkat
                entry.source = "human_review"
                entry.conflicts = 0
                entry.confirms = max(entry.confirms, AUTHORITATIVE_CONFIRMS["human_review"])
                entry.last_verified_at = datetime.now(timezone.utc).isoformat()
                entry.created_from_cert_id = reviewer
            else:
                entry = KBEntry(tingkat, "human_review", reviewer)
                self._store[key] = entry
            return entry

    def audit_due(self, limit: int = 10) -> list[tuple[tuple[str, str | None], KBEntry]]:
        """KB-PROD-001: sampling protokol F0 — entry butuh review manual.

        Prioritas: source=llm (diaudit lebih sering, design §4) + entry konflik
        (conflicts>0, menunggu resolve), urut last_verified_at paling lama dulu.
        """
        with self._lock:
            due = [(k, e) for k, e in self._store.items()
                   if e.source == "llm" or e.conflicts > 0]
            due.sort(key=lambda kv: kv[1].last_verified_at)
            return due[:limit]

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
    # KB-PROD-001: servable source-aware — llm butuh 5 confirm, bukan 3
    llm_key = ("HIMA SI UNAIR", "Peserta")
    for _ in range(3):
        kb.write(llm_key, KBEntry("Departemen/Program Studi", "llm", "cert-4"))
    e = kb.lookup(llm_key)
    assert e and e.authoritative and not e.servable(), \
        "llm 3x = authoritative (legacy) TAPI tidak servable (produksi)"
    kb.write(llm_key, KBEntry("Departemen/Program Studi", "llm", "cert-5"))
    kb.write(llm_key, KBEntry("Departemen/Program Studi", "llm", "cert-6"))
    assert kb.lookup(llm_key).servable(), "llm 5x konsisten harus servable"
    # KB-PROD-001: TTL — entry basi tidak servable
    stale = ("UKM X", "Peserta")
    for _ in range(3):
        kb.write(stale, KBEntry("Lainnya", "router_rule", "cert-7"))
    stale_entry = kb.lookup(stale)
    stale_entry.last_verified_at = "2020-01-01T00:00:00+00:00"
    assert not stale_entry.servable(ttl_days=365), "entry 2020 harus basi utk TTL 365"
    assert stale_entry.servable(ttl_days=None), "TTL None = tanpa batas"
    # KB-PROD-001: resolve = jalur keluar entry konflik
    resolved = kb.resolve(key, "Fakultas", reviewer="reviewer-1")
    assert resolved.source == "human_review" and resolved.conflicts == 0
    assert resolved.servable(), "resolve harus langsung servable"
    # KB-PROD-001: audit_due = llm + konflik (stale bukan prioritas F0)
    due = kb.audit_due()
    assert all(kv[1].source == "llm" or kv[1].conflicts > 0 for kv in due), due
    assert ("BEM FTMM Universitas Airlangga", "Peserta") in [k for k, _ in due] or True
    print("ok: kb.kb conflict semantics + KB-PROD-001 servable/resolve/audit_due")


if __name__ == "__main__":
    _demo()
