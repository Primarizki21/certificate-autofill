"""Unit tests for CORS security, W3C compliance, and origin validation.

Verifies that:
1. Whitelisted origins (e.g. http://localhost:5173) receive explicit CORS headers with credentials.
2. Malicious or unknown origins (e.g. http://attacker.com) are rejected by CORS policy.
3. Preflight OPTIONS requests return proper allow-methods and allow-headers.
4. Custom origins configured via CORS_ALLOWED_ORIGINS environment variable are respected.
5. When a wildcard '*' origin is present, allow_credentials is automatically False to prevent
   W3C credential leakage violations.
"""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import _get_cors_origins, app


def test_cors_whitelisted_origin_allowed():
    """Whitelisted origin receives Access-Control-Allow-Origin and credentials enabled."""
    client = TestClient(app)
    response = client.get(
        "/healthz",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_malicious_origin_rejected():
    """Untrusted / malicious origin does NOT receive Access-Control-Allow-Origin header."""
    client = TestClient(app)
    response = client.get(
        "/healthz",
        headers={"Origin": "http://evil-attacker.com"},
    )
    assert response.status_code == 200
    # Browser blocks response consumption when access-control-allow-origin is missing
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_options_request():
    """Preflight OPTIONS request from whitelisted origin receives appropriate CORS headers."""
    client = TestClient(app)
    response = client.options(
        "/api/documents",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods or "*" in allow_methods


def test_cors_custom_env_origins(monkeypatch):
    """Custom CORS_ALLOWED_ORIGINS from settings correctly sets allowed domains."""
    mock_settings = Settings(
        cors_allowed_origins="https://khp.unair.ac.id, https://prestasi.unair.ac.id"
    )
    monkeypatch.setattr("app.main.settings", mock_settings)

    origins = _get_cors_origins()
    assert origins == ["https://khp.unair.ac.id", "https://prestasi.unair.ac.id"]
    assert "*" not in origins

    # Test with custom app instance built with these origins
    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/ping")
    def ping():
        return {"pong": True}

    custom_client = TestClient(test_app)

    # Authorized campus origin
    res_campus = custom_client.get("/ping", headers={"Origin": "https://khp.unair.ac.id"})
    assert res_campus.headers.get("access-control-allow-origin") == "https://khp.unair.ac.id"
    assert res_campus.headers.get("access-control-allow-credentials") == "true"

    # Localhost should now be rejected because custom production origins are set
    res_local = custom_client.get("/ping", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in res_local.headers


def test_cors_wildcard_disables_credentials_w3c_compliance(monkeypatch):
    """When wildcard '*' is explicitly specified, allow_credentials MUST be False."""
    mock_settings = Settings(cors_allowed_origins="*")
    monkeypatch.setattr("app.main.settings", mock_settings)

    origins = _get_cors_origins()
    assert origins == ["*"]

    # Verify W3C rule: allow_credentials must be False if '*' in origins
    allow_credentials = "*" not in origins
    assert allow_credentials is False

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/open")
    def open_endpoint():
        return {"open": True}

    client = TestClient(test_app)
    res = client.get("/open", headers={"Origin": "http://any-domain.com"})
    assert res.headers.get("access-control-allow-origin") == "*"
    # access-control-allow-credentials MUST NOT be 'true' when origin is '*'
    assert res.headers.get("access-control-allow-credentials") != "true"
