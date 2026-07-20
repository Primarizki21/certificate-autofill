import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:changeme@127.0.0.1:5434/certautofill",
    )
    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    min_text_length: int = int(os.getenv("MIN_TEXT_LENGTH", "80"))
    enable_docling: bool = os.getenv("ENABLE_DOCLING", "true").lower() == "true"
    enable_ocr_fallback: bool = os.getenv("ENABLE_OCR_FALLBACK", "true").lower() == "true"
    max_job_retries: int = int(os.getenv("MAX_JOB_RETRIES", "3"))
    processing_mode: str = os.getenv("PROCESSING_MODE", "background").lower()
    db_worker_poll_seconds: int = int(os.getenv("DB_WORKER_POLL_SECONDS", "2"))


settings = Settings()
