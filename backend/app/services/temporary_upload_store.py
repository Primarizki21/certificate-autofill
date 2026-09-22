import os
import time
import uuid
from pathlib import Path

from app.config import settings
from app.services.security_guard import ValidatedDocument

SUPPORTED_STORE_EXTENSIONS = {".pdf", ".jpeg", ".jpg", ".png", ".webp"}


class TemporaryUploadStore:
    """Manages ephemeral documents (PDF and Images) on local storage with zero retention in PostgreSQL.

    Security & Reliability invariants:
    - Files stored with strict permissions (0o600).
    - Keys strictly validated as UUIDs to prevent directory traversal.
    - Atomic writes via .part files and os.replace.
    - Magic bytes validation before persisting.
    """

    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = Path(root_dir or settings.upload_temp_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root_dir, 0o700)
        except OSError:
            pass

    def _resolve_key(self, file_key: str, preferred_ext: str | None = None) -> Path:
        """Validate UUID and resolve full path safely across supported formats."""
        try:
            parsed_uuid = uuid.UUID(str(file_key))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"Invalid file key (must be UUID): {file_key}") from exc

        # 1. If preferred extension is given, check that first
        if preferred_ext:
            candidate = (self.root_dir / f"{parsed_uuid}{preferred_ext}").resolve()
            if not str(candidate).startswith(str(self.root_dir)):
                raise ValueError("Path traversal attempt detected.")
            if candidate.is_file():
                return candidate

        # 2. Check any existing supported extension on disk
        for ext in (".pdf", ".jpeg", ".jpg", ".png", ".webp"):
            candidate = (self.root_dir / f"{parsed_uuid}{ext}").resolve()
            if not str(candidate).startswith(str(self.root_dir)):
                raise ValueError("Path traversal attempt detected.")
            if candidate.is_file():
                return candidate

        # 3. Default fallback path (for initial creation or missing file check)
        fallback = (self.root_dir / f"{parsed_uuid}{preferred_ext or '.pdf'}").resolve()
        if not str(fallback).startswith(str(self.root_dir)):
            raise ValueError("Path traversal attempt detected.")
        return fallback

    def get_file_type(self, file_key: str) -> str:
        """Return the normalized file type ('pdf', 'jpeg', 'png') for a staged key."""
        target_path = self._resolve_key(file_key)
        ext = target_path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            return "jpeg"
        if ext == ".png":
            return "png"
        if ext == ".webp":
            return "webp"
        return "pdf"

    def stage_validated(self, validated: ValidatedDocument) -> str:
        """Stage an already validated and sanitized document to an ephemeral file."""
        file_key = str(uuid.uuid4())
        ext = f".{validated.file_type}"
        part_path = self.root_dir / f"{file_key}.part"
        final_path = self._resolve_key(file_key, preferred_ext=ext)

        fd = os.open(str(part_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(validated.cleaned_bytes)
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

    def stage_bytes(self, content: bytes, filename: str | None = None) -> str:
        """Stage raw content to an ephemeral file atomically after basic magic byte check."""
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"Ukuran file ({len(content)} bytes) melebihi batas {settings.max_upload_size_mb} MB.")

        if content.startswith(b"%PDF-"):
            ext = ".pdf"
        elif content.startswith(b"\xff\xd8\xff"):
            ext = ".jpeg"
        elif content.startswith(b"\x89PNG\r\n\x1a\n"):
            ext = ".png"
        elif len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            ext = ".webp"
        else:
            raise ValueError("File bukan format PDF/gambar valid (magic bytes mismatch).")

        file_key = str(uuid.uuid4())
        part_path = self.root_dir / f"{file_key}.part"
        final_path = self._resolve_key(file_key, preferred_ext=ext)

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
            if entry.stem in protected or not entry.is_file():
                continue
            if entry.suffix not in SUPPORTED_STORE_EXTENSIONS and entry.suffix != ".part":
                continue
            try:
                if (now - entry.stat().st_mtime) > cutoff_age:
                    entry.unlink(missing_ok=True)
                    deleted_count += 1
            except OSError:
                pass

        return deleted_count


upload_store = TemporaryUploadStore()
