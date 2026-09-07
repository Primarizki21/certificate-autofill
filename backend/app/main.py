import sys
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db, init_db
from app.master_data import FORM_OPTIONS
from app.models import Document, ExtractionJob, ExtractedField
from app.schemas import ExtractionResult, FieldResult, OptionsResponse, UploadResponse
from app.services.job_processor import process_document_job
from app.services.retention_cleanup import cleanup_expired_previews_and_documents
from app.services.temporary_upload_store import upload_store

logger = logging.getLogger("certificate-autofill-main")
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

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        cleanup_db = SessionLocal()
        try:
            cleanup_expired_previews_and_documents(cleanup_db)
        finally:
            cleanup_db.close()
        upload_store.reap_orphans()
    except Exception as exc:
        logger.warning("Startup retention cleanup error: %s", exc)


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
    checksum = hashlib.sha256(content).hexdigest()

    # Auto-retrieve: check if identical PDF was already processed with completed fields
    existing = (
        db.query(Document)
        .filter(Document.checksum_sha256 == checksum, Document.status.in_(["completed", "needs_review"]))
        .order_by(Document.created_at.desc())
        .first()
    )
    if existing:
        has_fields = db.query(ExtractedField).filter(ExtractedField.document_id == existing.id).count() > 0
        if has_fields:
            UPLOAD_COUNT.inc()
            UPLOAD_SIZE.observe(len(content))
            return UploadResponse(document_id=existing.id, job_id="cached", status=existing.status)

    try:
        temp_key = upload_store.stage_bytes(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    document_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
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

    has_preview = bool(document.preview_image is not None)
    return ExtractionResult(
        document_id=document_id,
        status=document.status,
        needs_review=needs_review,
        fields=field_dict,
        raw_text_preview=None,
        parser_engine=document.parser_engine,
        has_preview=has_preview,
    )


@app.get("/api/documents/{document_id}/preview")
def get_document_preview(document_id: str, db: Session = Depends(get_db)) -> Response:
    """Return the lightweight compressed JPEG preview of the certificate."""
    REQUEST_COUNT.labels(endpoint="/api/documents/{document_id}/preview").inc()
    try:
        uuid.UUID(str(document_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="ID dokumen tidak valid.")

    document = db.get(Document, document_id)
    if not document or not document.preview_image:
        raise HTTPException(status_code=404, detail="Preview gambar tidak ditemukan untuk dokumen ini.")

    return Response(
        content=document.preview_image,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Disposition": f'inline; filename="preview_{document_id}.jpg"',
        },
    )
