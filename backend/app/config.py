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
    # NC-001 (PASS eksperimen): 2-pass nomor — re-OCR region nomor (re-render
    # PDF zoom tinggi), prepend bila beda dari baseline. DEFAULT FALSE: diukur
    # lazy (nomor hilang) = 0/18 gain; varian penuh ~+2-10s/cert utk +3pt.
    enable_ocr_number_2pass: bool = os.getenv("ENABLE_OCR_NUMBER_2PASS", "false").lower() == "true"
    # PROD-002 (port produksi organizer v3+R6+format + nomor, 0 LLM): normalisasi
    # pasca-organizer_v2 (R0/PREFIX_HELD/R2/R6 + F1 alias + F3 BEM FKM + nomor
    # SERT/dot/space). DEFAULT FALSE — eksperimen belum final (handoff v29);
    # aktifkan via ENABLE_ORGANIZER_NORMALIZATION=true setelah re-eval disetujui.
    enable_organizer_normalization: bool = os.getenv("ENABLE_ORGANIZER_NORMALIZATION", "false").lower() == "true"
    # Combined v2 Staging (dummy port 0 LLM bundle: AKT-005 + ORG-004 + PROD-002 + ROUTER-004):
    # DEFAULT FALSE (gated) — aktifkan via ENABLE_COMBINED_V2=true untuk aktivasi staging pipeline.
    enable_combined_v2: bool = os.getenv("ENABLE_COMBINED_V2", "false").lower() == "true"
    # Combined v3 Staging (composite 0 LLM bundle: AKT-006 + ORG-006 + NUM-003 + DATE-002 + ROUTER-006):
    # DEFAULT FALSE (gated) — aktifkan via ENABLE_COMBINED_V3=true untuk aktivasi staging pipeline.
    enable_combined_v3: bool = os.getenv("ENABLE_COMBINED_V3", "false").lower() == "true"
    # Combined v4 Staging (EXP-V4-001: Robust Acronym & Metrology, 0 LLM):
    # DEFAULT FALSE (gated) — aktifkan via ENABLE_COMBINED_V4=true untuk aktivasi staging pipeline.
    enable_combined_v4: bool = os.getenv("ENABLE_COMBINED_V4", "false").lower() == "true"
    # Combined v4.1 Staging (EXP-V4-002: Minor Staging Refinement, 0 LLM):
    # DEFAULT FALSE (gated) — aktifkan via ENABLE_COMBINED_V4_1=true untuk aktivasi staging pipeline.
    enable_combined_v4_1: bool = os.getenv("ENABLE_COMBINED_V4_1", "false").lower() == "true"
    # Combined v4.2 Staging (EXP-V4-003: 3 Pillars & High-DPI Robustness, 0 LLM):
    # DEFAULT FALSE (gated) — aktifkan via ENABLE_COMBINED_V4_2=true untuk aktivasi staging pipeline.
    enable_combined_v4_2: bool = os.getenv("ENABLE_COMBINED_V4_2", "false").lower() == "true"
    max_job_retries: int = int(os.getenv("MAX_JOB_RETRIES", "3"))
    processing_mode: str = os.getenv("PROCESSING_MODE", "background").lower()
    db_worker_poll_seconds: int = int(os.getenv("DB_WORKER_POLL_SECONDS", "2"))
    # v8: LLM tingkat (Ollama) + router. Default LLM off agar produksi tetap
    # deterministik tanpa Ollama; aktifkan via ENABLE_LLM_TINGKAT=true.
    enable_llm_tingkat: bool = os.getenv("ENABLE_LLM_TINGKAT", "false").lower() == "true"
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


settings = Settings()
