"""Prometheus metrics for certificate extraction pipeline and MLOps telemetry."""

import logging

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Pipeline execution latency across processing stages
STAGE_DURATION = Histogram(
    "cert_pipeline_stage_duration_seconds",
    "Duration of certificate pipeline extraction stages in seconds",
    ["stage", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
)

# LLM runtime token accounting
LLM_TOKENS = Counter(
    "cert_llm_tokens_total",
    "Total LLM token usage by model and token type",
    ["model", "token_type"],
)

# LLM runtime estimated cost
LLM_COST_USD = Counter(
    "cert_llm_cost_usd_total",
    "Estimated LLM API cost in USD",
    ["model"],
)

# Route distribution (PyMuPDF fast path, Gemini LLM, Offline Combined v4.2 fallback)
EXTRACTION_ROUTE = Counter(
    "cert_extraction_route_total",
    "Total certificates processed by final extraction route",
    ["engine", "status"],
)

# Per-field human review required flags
FIELD_NEEDS_REVIEW = Counter(
    "cert_field_needs_review_total",
    "Total field-level needs_review flags raised",
    ["field"],
)

# Database worker queue depth
QUEUE_JOBS = Gauge(
    "cert_queue_jobs_count",
    "Current number of extraction jobs in database queue by status",
    ["status"],
)
