import os
import time
import uuid
from pathlib import Path

from app.config import settings


class TemporaryUploadStore:
    """Manages ephemeral PDF files on local storage with zero retention in PostgreSQL.

    Security & Reliability invariants:
    - Files stored with strict permissions (0o600).
    - Keys strictly validated as UUIDs to prevent directory traversal.
    - Atomic writes via .part files and os.replace.
    - Magic bytes (%PDF-) validation before persisting.
    """

    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = Path(root_dir or settings.upload_temp_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root_dir, 0o700)
        except OSError:
            pass

    def _resolve_key(self, file_key: str) -> Path:
        """Validate UUID and resolve full path safely."""
        try:
            parsed_uuid = uuid.UUID(str(file_key))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"Invalid file key (must be UUID): {file_key}") from exc
        target_path = (self.root_dir / f"{parsed_uuid}.pdf").resolve()
        if not str(target_path).startswith(str(self.root_dir)):
            raise ValueError("Path traversal attempt detected.")
        return target_path

    def stage_bytes(self, content: bytes) -> str:
        """Stage PDF content to an ephemeral file atomically.

        Returns the UUID file key.
        """
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"Ukuran file ({len(content)} bytes) melebihi batas {settings.max_upload_size_mb} MB.")

        if not content.startswith(b"%PDF-"):
            raise ValueError("File bukan format PDF valid (magic bytes mismatch).")

        file_key = str(uuid.uuid4())
        part_path = self.root_dir / f"{file_key}.part"
        final_path = self._resolve_key(file_key)

        fd = os.open(str(part_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(part_path), str(final_path))
        except Exception:
            if part_path.exists():
                try:
                    part_path.unlink()
                except OSError:
                    pass
            raise

        return file_key

    def open_bytes(self, file_key: str) -> bytes:
        """Read and return content of an ephemeral file."""
        target_path = self._resolve_key(file_key)
        if not target_path.is_file():
            raise FileNotFoundError(f"File sementara tidak ditemukan: {file_key}")
        return target_path.read_bytes()

    def delete(self, file_key: str) -> bool:
        """Delete an ephemeral file. Safe to call multiple times."""
        try:
            target_path = self._resolve_key(file_key)
            if target_path.is_file():
                target_path.unlink()
                return True
        except (ValueError, FileNotFoundError, OSError):
            return False
        return False

    def reap_orphans(
        self,
        protected_keys: set[str] | None = None,
        max_age_seconds: int | None = None,
    ) -> int:
        """Remove stale files that are not owned by an active job."""
        protected = protected_keys or set()
        cutoff_age = max_age_seconds if max_age_seconds is not None else (settings.temp_file_ttl_hours * 3600)
        now = time.time()
        deleted_count = 0

        for entry in self.root_dir.iterdir():
            if entry.stem in protected or not entry.is_file() or entry.suffix not in {".pdf", ".part"}:
                continue
            try:
                if (now - entry.stat().st_mtime) > cutoff_age:
                    entry.unlink(missing_ok=True)
                    deleted_count += 1
            except OSError:
                pass

        return deleted_count


upload_store = TemporaryUploadStore()
