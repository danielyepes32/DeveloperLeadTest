"""Authentication & RBAC tests."""
from __future__ import annotations

from tests.helpers import auth_headers


def test_register_and_login(client):
    headers = auth_headers(client, "client@acme.com", "client")
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "client"


def test_duplicate_email_conflict(client):
    auth_headers(client, "dup@acme.com", "client")
    res = client.post("/auth/register", json={
        "email": "dup@acme.com", "password": "password123",
        "full_name": "Other", "role": "supplier",
    })
    assert res.status_code == 409


def test_login_wrong_password(client):
    auth_headers(client, "u@acme.com", "client")
    res = client.post("/auth/login", json={"email": "u@acme.com", "password": "wrong-pass"})
    assert res.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_short_password_rejected(client):
    res = client.post("/auth/register", json={
        "email": "x@acme.com", "password": "short", "full_name": "X", "role": "client",
    })
    assert res.status_code == 422
