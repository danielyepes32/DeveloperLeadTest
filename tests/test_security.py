"""Hardening tests: security headers, login rate limiting, fail-fast secret, pagination."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app import ratelimit
from app.config import Settings
from tests.helpers import auth_headers, create_request


def test_security_headers_present(client):
    res = client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert "x-request-id" in res.headers


def test_login_rate_limit(client, monkeypatch):
    auth_headers(client, "rl@acme.com", "client")
    ratelimit._hits.clear()
    monkeypatch.setattr(ratelimit.settings, "login_rate_limit", 3)

    body = {"email": "rl@acme.com", "password": "password123"}
    codes = [client.post("/auth/login", json=body).status_code for _ in range(4)]

    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_insecure_secret_rejected_in_production():
    with pytest.raises(ValidationError):
        Settings(app_env="production", jwt_secret="short")


def test_strong_secret_accepted_in_production():
    s = Settings(app_env="production", jwt_secret="x" * 40)
    assert s.app_env == "production"


def test_pagination(client):
    buyer = auth_headers(client, "pag@acme.com", "client")
    for i in range(3):
        create_request(client, buyer, product_name=f"Item {i}")

    page1 = client.get("/requests?limit=2&offset=0", headers=buyer).json()
    page2 = client.get("/requests?limit=2&offset=2", headers=buyer).json()
    assert len(page1) == 2
    assert len(page2) == 1


def test_pagination_rejects_out_of_range(client):
    buyer = auth_headers(client, "pag2@acme.com", "client")
    assert client.get("/requests?limit=0", headers=buyer).status_code == 422
    assert client.get("/requests?limit=9999", headers=buyer).status_code == 422
