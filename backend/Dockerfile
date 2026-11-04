# Stage 1: Builder
FROM python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893 AS builder
WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1


COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
# rapidocr-onnxruntime pulls the GUI OpenCV build; the headless build provides the
# same cv2 without libGL. Reinstall from scratch so the shared cv2 stays consistent.
RUN pip uninstall -y opencv-python opencv-python-headless \
    && pip install --user --no-cache-dir "opencv-python-headless==5.0.0.93"

# Stage 2: Hardened Runtime
FROM python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893

ARG VCS_REF=unknown
ARG APP_VERSION=dev

LABEL org.opencontainers.image.title="certificate-autofill-backend" \
      org.opencontainers.image.description="Ekstraksi sertifikat mahasiswa dan mapping form KHP" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PYTHONPATH=/app \
    PATH=/home/appuser/.local/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-ind \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root system user for security isolation
RUN useradd -u 10001 -m -s /bin/bash appuser && \
    mkdir -p /tmp/cert_uploads /app/khp /home/appuser/.cache && \
    chown -R appuser:appuser /app /tmp/cert_uploads /home/appuser

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser alembic /app/alembic
COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
# Pre-warm ONNX weights at build time so an air-gapped campus host never downloads
# models at runtime. No `|| true`: a failed download must fail the build.
USER appuser
RUN python -c "from rapidocr_onnxruntime import RapidOCR; RapidOCR()"
RUN python -c "import indra_ocr; indra_ocr.load(threads=2)"

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
