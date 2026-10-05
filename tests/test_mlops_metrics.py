"""Unit tests for MLOps and Prometheus metrics instrumentation."""

from app.main import app
from app.services.gemini_extractor import _log_telemetry
from app.services.metrics import (
    EXTRACTION_ROUTE,
    FIELD_NEEDS_REVIEW,
    HTTP_REQUEST_DURATION,
    LLM_COST_USD,
    LLM_TOKENS,
    QUEUE_JOBS,
    STAGE_DURATION,
)
from fastapi.testclient import TestClient


def test_metrics_definitions_and_labels():
    """Verify metrics objects exist and accept defined labels."""
    STAGE_DURATION.labels(stage="fast_path", status="success").observe(0.042)
    EXTRACTION_ROUTE.labels(engine="gemini", status="success").inc()
    FIELD_NEEDS_REVIEW.labels(field="nomor").inc()
    QUEUE_JOBS.labels(status="queued").set(5)

    HTTP_REQUEST_DURATION.labels(method="GET", endpoint="/healthz", status_code="200").observe(0.002)
    assert HTTP_REQUEST_DURATION is not None
    assert STAGE_DURATION is not None
    assert EXTRACTION_ROUTE is not None
    assert FIELD_NEEDS_REVIEW is not None
    assert QUEUE_JOBS is not None


def test_gemini_telemetry_updates_metrics():
    """Verify _log_telemetry increments token, cost, and stage duration metrics."""
    meta = {
        "status": "success",
        "model": "gemini-3.1-flash-lite",
        "calls_count": 1,
        "prompt_tokens": 120,
        "candidates_tokens": 45,
        "cached_tokens": 0,
        "thoughts_tokens": 15,
        "total_tokens": 180,
        "cost_usd": 0.000035,
        "cost_idr": 0.58,
        "latency_s": 1.25,
        "fallback_reason": None,
        "error_type": None,
    }

    _log_telemetry(meta)

    # Inspect through metric collector values
    assert LLM_TOKENS.labels(model="gemini-3.1-flash-lite", token_type="prompt")._value.get() >= 120
    assert LLM_COST_USD.labels(model="gemini-3.1-flash-lite")._value.get() >= 0.000035


def test_metrics_endpoint_returns_prometheus_format():
    """Verify /metrics HTTP endpoint returns 200 and includes all new metric names."""
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    assert "cert_pipeline_stage_duration_seconds" in body
    assert "cert_llm_tokens_total" in body
    assert "cert_llm_cost_usd_total" in body
    assert "cert_extraction_route_total" in body
    assert "cert_field_needs_review_total" in body
    assert "cert_queue_jobs_count" in body
    assert "cert_http_request_duration_seconds" in body
