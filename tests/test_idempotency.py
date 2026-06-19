"""Idempotency-Key guarantees: retries must not create duplicate side effects."""
from __future__ import annotations

from tests.helpers import auth_headers, create_request


def test_create_request_is_idempotent(client):
    buyer = auth_headers(client, "idem@acme.com", "client")
    headers = {**buyer, "Idempotency-Key": "fixed-key-123"}
    payload = {"product_name": "Monitors", "quantity": 5}

    first = client.post("/requests", headers=headers, json=payload)
    second = client.post("/requests", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]  # same resource, not a duplicate

    # Exactly one request exists for this client.
    assert len(client.get("/requests", headers=buyer).json()) == 1


def test_offer_is_idempotent(client):
    buyer = auth_headers(client, "ib@acme.com", "client")
    seller = auth_headers(client, "is@acme.com", "supplier")
    req = create_request(client, buyer)
    headers = {**seller, "Idempotency-Key": "offer-key-1"}
    body = {"amount": 700_000, "currency": "COP"}

    first = client.post(f"/requests/{req['id']}/offers", headers=headers, json=body)
    second = client.post(f"/requests/{req['id']}/offers", headers=headers, json=body)

    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/negotiations", headers=seller).json()) == 1
