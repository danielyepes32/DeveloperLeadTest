"""Small helpers to keep tests readable."""
from __future__ import annotations


def auth_headers(client, email, role, password="password123", full_name="Test User") -> dict:
    client.post("/auth/register", json={
        "email": email, "password": password, "full_name": full_name, "role": role,
    })
    res = client.post("/auth/login", json={"email": email, "password": password})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_request(client, headers, product_name="Laptops", quantity=10) -> dict:
    res = client.post("/requests", headers=headers, json={
        "product_name": product_name, "quantity": quantity, "description": "test",
    })
    assert res.status_code == 201, res.text
    return res.json()


def make_offer(client, headers, request_id, amount, message="oferta") -> dict:
    res = client.post(f"/requests/{request_id}/offers", headers=headers, json={
        "amount": amount, "currency": "COP", "message": message,
    })
    assert res.status_code == 201, res.text
    return res.json()
