# Stage 1: Builder
FROM python:3.11-slim AS builder
WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Hardened Runtime
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PYTHONPATH=/app \
    PATH=/home/appuser/.local/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
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

# Pre-warm RapidOCR ONNX model weights in build layer (ensures offline campus operation)
USER appuser
RUN python -c "from rapidocr_onnxruntime import RapidOCR; RapidOCR()" || true

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
