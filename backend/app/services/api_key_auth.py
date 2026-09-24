import logging
import secrets
from collections.abc import Iterable
from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from app.config import settings

logger = logging.getLogger("certificate-api-auth")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key(prefix: str = "sk-", length: int = 32, encoding: str = "base64url") -> str:
    """Generate a secure API key with a prefix (sk- or sk_) and random string.

    Supports base64url (token_urlsafe) or hex (token_hex).
    """
    clean_prefix = prefix if prefix.startswith(("sk-", "sk_")) else f"sk-{prefix.lstrip('-._')}"
    if encoding == "hex":
        random_part = secrets.token_hex(length // 2 if length >= 2 else 16)
    else:
        random_part = secrets.token_urlsafe(length)
    return f"{clean_prefix}{random_part}"


def is_valid_key_format(key: str | None) -> bool:
    """Verify that an API key follows standard naming conventions (starts with sk- or sk_)."""
    if not key or not isinstance(key, str):
        return False
    stripped = key.strip()
    return (stripped.startswith("sk-") or stripped.startswith("sk_")) and len(stripped) >= 16


def get_allowed_api_keys() -> list[str]:
    """Retrieve allowed API keys from configuration, split by comma or newline."""
    raw = (settings.api_keys or "").strip()
    if not raw:
        return []
    keys: list[str] = []
    for item in raw.replace("\n", ",").split(","):
        cleaned = item.strip()
        if cleaned:
            keys.append(cleaned)
    return keys


def validate_api_key(provided_key: str | None, allowed_keys: Iterable[str] | None = None) -> bool:
    """Constant-time validation of an API key against allowed keys."""
    if not provided_key or not is_valid_key_format(provided_key):
        return False

    targets = list(allowed_keys) if allowed_keys is not None else get_allowed_api_keys()
    if not targets:
        return False

    is_match = False
    for target in targets:
        if secrets.compare_digest(provided_key.strip(), target.strip()):
            is_match = True
    return is_match


def extract_key_from_request(request: Request, header_key: str | None = None) -> str | None:
    """Extract API key from X-API-Key header or Authorization: Bearer <key>."""
    if header_key:
        return header_key.strip()

    x_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
    if x_key:
        return x_key.strip()

    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header:
        parts = auth_header.strip().split()
        if len(parts) == 2 and parts[0].lower() in {"bearer", "token"}:
            return parts[1].strip()

    return None


async def require_api_key(
    request: Request,
    api_key_header: str | None = Security(API_KEY_HEADER),
) -> str | None:
    """FastAPI dependency to enforce API key authentication.

    - If API_KEYS is empty and REQUIRE_API_KEY is False: allows open access (internal mode).
    - If API_KEYS is configured: requires valid X-API-Key or Bearer token with prefix sk-.
    """
    allowed_keys = get_allowed_api_keys()

    if not allowed_keys and not settings.require_api_key:
        return None

    if not allowed_keys and settings.require_api_key:
        logger.error("REQUIRE_API_KEY=true but API_KEYS is empty in settings.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configured to require API Key, but no API_KEYS defined in configuration.",
        )

    provided = extract_key_from_request(request, header_key=api_key_header)
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key wajib disertakan. Gunakan header 'X-API-Key' atau 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not validate_api_key(provided, allowed_keys):
        logger.warning("Rejected invalid API Key access attempt.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key tidak valid atau tidak memiliki izin akses.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return provided
