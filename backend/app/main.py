import asyncio
import logging
import sys
from contextlib import suppress
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import hashlib
import uuid
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db, init_db
from app.master_data import FORM_OPTIONS
from app.models import Document, ExtractionJob, ExtractedField
from app.schemas import ExtractionResult, FieldResult, OptionsResponse, UploadResponse
from app.services.job_processor import cleanup_expired_jobs_and_uploads, process_document_job
from app.services.temporary_upload_store import upload_store

app = FastAPI(title="Certificate Autofill Prototype", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REQUEST_COUNT = Counter("cert_autofill_requests_total", "Total HTTP requests", ["endpoint"])
UPLOAD_COUNT = Counter("cert_autofill_uploads_total", "Total uploaded PDFs")
UPLOAD_SIZE = Histogram("cert_autofill_upload_size_bytes", "PDF upload size in bytes")
logger = logging.getLogger("certificate-main")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


async def _storage_cleanup_loop() -> None:
    cleanup_interval = max(1, settings.storage_cleanup_interval_seconds)
    while True:
        await asyncio.sleep(cleanup_interval)
        try:
            await asyncio.to_thread(cleanup_expired_jobs_and_uploads)
        except Exception:
            logger.exception("Periodic ephemeral-storage cleanup failed.")


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    cleanup_expired_jobs_and_uploads()
    app.state.storage_cleanup_task = asyncio.create_task(_storage_cleanup_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "storage_cleanup_task", None)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    REQUEST_COUNT.labels(endpoint="/").inc()
    return (static_dir / "index.html").read_text(encoding="utf-8")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    REQUEST_COUNT.labels(endpoint="/healthz").inc()
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/options", response_model=OptionsResponse)
def get_options() -> OptionsResponse:
    REQUEST_COUNT.labels(endpoint="/api/options").inc()
    return OptionsResponse(options=FORM_OPTIONS)


@app.post("/api/documents", response_model=UploadResponse)
def upload_document(
    background_tasks: BackgroundTasks,
    tahun_akademik: str = Form(...),
    bukti_fisik: str = Form("Sertifikat"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    REQUEST_COUNT.labels(endpoint="/api/documents").inc()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File wajib PDF.")

    content = file.file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Ukuran PDF maksimal {settings.max_upload_size_mb} MB.")

    try:
        temp_key = upload_store.stage_bytes(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    document_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    checksum = hashlib.sha256(content).hexdigest()

    document = Document(
        id=document_id,
        source_system="prototype_ui",
        tahun_akademik=tahun_akademik,
        bukti_fisik=bukti_fisik,
        original_file_name=file.filename,
        mime_type=file.content_type or "application/pdf",
        file_size=len(content),
        checksum_sha256=checksum,
        status="queued",
    )
    job = ExtractionJob(
        id=job_id,
        document_id=document_id,
        temp_file_key=temp_key,
        status="queued",
        retry_count=0,
    )

    try:
        db.add(document)
        db.add(job)
        db.commit()
    except Exception:
        db.rollback()
        upload_store.delete(temp_key)
        raise
    # No RabbitMQ variant. The extraction job is processed either in the
    # FastAPI background task, synchronously, or by the optional DB-polling worker.
    if settings.processing_mode == "sync":
        process_document_job(job_id=job_id, document_id=document_id)
        db.refresh(document)
        response_status = document.status
    elif settings.processing_mode == "db_worker":
        response_status = "queued"
    else:
        background_tasks.add_task(process_document_job, job_id, document_id)
        response_status = "queued"

    UPLOAD_COUNT.inc()
    UPLOAD_SIZE.observe(len(content))
    return UploadResponse(document_id=document_id, job_id=job_id, status=response_status)


@app.get("/api/documents/{document_id}/result", response_model=ExtractionResult)
def get_result(document_id: str, db: Session = Depends(get_db)) -> ExtractionResult:
    REQUEST_COUNT.labels(endpoint="/api/documents/{document_id}/result").inc()
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan.")

    fields = db.query(ExtractedField).filter(ExtractedField.document_id == document_id).all()

    field_dict = {
        f.form_field_name: FieldResult(
            value=f.mapped_value or f.extracted_value,
            confidence=float(f.confidence),
            source=f.source,
            needs_review=bool(f.needs_review),
        )
        for f in fields
    }
    needs_review = any(item.needs_review for item in field_dict.values()) or document.status == "needs_review"

    return ExtractionResult(
        document_id=document_id,
        status=document.status,
        needs_review=needs_review,
        fields=field_dict,
        raw_text_preview=None,
        parser_engine=document.parser_engine,
    )
