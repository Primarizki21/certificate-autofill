import asyncio
import logging
import sys
from contextlib import suppress
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
import csv
import hashlib
import json
import io
import secrets
import uuid
from datetime import datetime
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
import openpyxl
from openpyxl.utils import get_column_letter
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db, init_db
from app.master_data import FORM_OPTIONS, KHP_MASTER_OPTIONS
from app.models import Document, ExtractionJob, ExtractedField, KHPMasterResolution
from app.schemas import (
    ExtractionResult,
    FieldResult,
    OptionsResponse,
    PublicExtractionResult,
    UploadResponse,
)
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
    if settings.enable_khp_master_staging:
        from app.services.aucc_catalog import warm_aucc_catalog

        warm_aucc_catalog()
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
    options = KHP_MASTER_OPTIONS if settings.enable_khp_master_staging else FORM_OPTIONS
    return OptionsResponse(options=options)


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


@app.get("/api/documents/{document_id}/result", response_model=PublicExtractionResult)
def get_result(document_id: str, db: Session = Depends(get_db)) -> PublicExtractionResult:
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
    master_needs_review = False
    if settings.enable_khp_master_staging:
        resolution_row = (
            db.query(KHPMasterResolution)
            .filter(KHPMasterResolution.document_id == document_id)
            .one_or_none()
        )
        if resolution_row is not None:
            try:
                master_res = json.loads(resolution_row.resolution_json)
                master_needs_review = bool(master_res and master_res.get("status") != "resolved")
            except json.JSONDecodeError:
                master_needs_review = True

    needs_review = (
        any(item.needs_review for item in field_dict.values())
        or document.status == "needs_review"
        or master_needs_review
    )
    return PublicExtractionResult(
        document_id=document_id,
        status=document.status,
        needs_review=needs_review,
        fields=field_dict,
    )

security = HTTPBasic()


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    correct_username = secrets.compare_digest(credentials.username, settings.admin_username)
    correct_password = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Akses ditolak: Kredensial admin tidak valid.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/api/admin/documents/export")
def export_documents(
    format: str = "xlsx",
    admin: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    REQUEST_COUNT.labels(endpoint="/api/admin/documents/export").inc()
    docs = db.query(Document).order_by(Document.created_at.desc()).all()

    doc_ids = [d.id for d in docs]
    all_fields = db.query(ExtractedField).filter(ExtractedField.document_id.in_(doc_ids)).all() if doc_ids else []
    fields_by_doc: dict[str, dict[str, ExtractedField]] = {}
    for f in all_fields:
        fields_by_doc.setdefault(str(f.document_id), {})[f.form_field_name] = f

    headers = [
        ("No", "no"),
        ("ID Dokumen", "id"),
        ("Waktu Upload", "created_at"),
        ("Nama File Asli", "original_file_name"),
        ("Tahun Akademik", "tahun_akademik"),
        ("Bukti Fisik", "bukti_fisik"),
        ("Status", "status"),
        ("Engine Parser", "parser_engine"),
        ("Nama Kegiatan", "nama_kegiatan_sertifikasi"),
        ("Nomor Bukti Fisik / Sertifikat", "nomor_bukti_fisik_nomor_sertifikasi"),
        ("Penyelenggara Kegiatan", "penyelenggara_kegiatan"),
        ("Jenis Penyelenggara", "jenis_penyelenggara"),
        ("Tingkat", "tingkat"),
        ("Prestasi / Partisipasi / Jabatan", "prestasi_partisipasi_jabatan"),
        ("Kelompok Kegiatan", "kelompok_kegiatan"),
        ("Jenis Kegiatan", "jenis_kegiatan"),
        ("Waktu Mulai", "waktu_mulai_pelaksanaan"),
        ("Waktu Selesai", "waktu_selesai_pelaksanaan"),
        ("Avg Confidence", "avg_confidence"),
        ("Perlu Review", "needs_review"),
    ]
    header_labels = [h[0] for h in headers]

    rows = []
    for idx, doc in enumerate(docs, start=1):
        fmap = fields_by_doc.get(str(doc.id), {})

        def _val(fname: str) -> str:
            field = fmap.get(fname)
            if not field:
                return ""
            return field.mapped_value or field.extracted_value or ""

        conf_list = [float(f.confidence) for f in fmap.values() if f.confidence is not None]
        avg_conf = round(sum(conf_list) / len(conf_list), 4) if conf_list else 0.0
        has_review = any(bool(f.needs_review) for f in fmap.values()) or doc.status == "needs_review"

        row_data = {
            "no": idx,
            "id": str(doc.id),
            "created_at": doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "",
            "original_file_name": doc.original_file_name,
            "tahun_akademik": doc.tahun_akademik,
            "bukti_fisik": doc.bukti_fisik,
            "status": doc.status,
            "parser_engine": doc.parser_engine or "-",
            "nama_kegiatan_sertifikasi": _val("nama_kegiatan_sertifikasi"),
            "nomor_bukti_fisik_nomor_sertifikasi": _val("nomor_bukti_fisik_nomor_sertifikasi"),
            "penyelenggara_kegiatan": _val("penyelenggara_kegiatan"),
            "jenis_penyelenggara": _val("jenis_penyelenggara"),
            "tingkat": _val("tingkat"),
            "prestasi_partisipasi_jabatan": _val("prestasi_partisipasi_jabatan"),
            "kelompok_kegiatan": _val("kelompok_kegiatan"),
            "jenis_kegiatan": _val("jenis_kegiatan"),
            "waktu_mulai_pelaksanaan": _val("waktu_mulai_pelaksanaan"),
            "waktu_selesai_pelaksanaan": _val("waktu_selesai_pelaksanaan"),
            "avg_confidence": avg_conf,
            "needs_review": "Ya" if has_review else "Tidak",
        }
        rows.append(row_data)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"riwayat_sertifikat_{timestamp}"

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header_labels)
        for r in rows:
            writer.writerow([r[h[1]] for h in headers])
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )

    # Default XLSX
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Riwayat Sertifikat"
    ws.append(header_labels)

    for cell in ws[1]:
        cell.font = openpyxl.styles.Font(bold=True)

    for r in rows:
        ws.append([r[h[1]] for h in headers])

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 40)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
    )
