"""End-to-end negotiation flow and state-machine guard tests."""
from __future__ import annotations

from tests.helpers import auth_headers, create_request, make_offer


def test_full_negotiation_offer_counter_accept(client):
    buyer = auth_headers(client, "buyer@acme.com", "client")
    seller = auth_headers(client, "seller@acme.com", "supplier")

    req = create_request(client, buyer)
    neg = make_offer(client, seller, req["id"], 1_500_000)
    assert neg["status"] == "active"

    # Buyer counters lower.
    res = client.post(f"/negotiations/{neg['id']}/counter", headers=buyer,
                      json={"amount": 1_200_000, "message": "muy alto"})
    assert res.status_code == 200

    # Seller accepts the counter.
    res = client.post(f"/negotiations/{neg['id']}/accept", headers=seller)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "accepted"
    assert float(body["agreed_amount"]) == 1_200_000

    # Request is now closed; full proposal history is preserved.
    assert client.get(f"/requests/{req['id']}", headers=buyer).json()["status"] == "closed"
    detail = client.get(f"/negotiations/{neg['id']}", headers=buyer).json()
    assert [p["kind"] for p in detail["proposals"]] == ["offer", "counter"]


def test_supplier_cannot_create_request(client):
    seller = auth_headers(client, "s2@acme.com", "supplier")
    res = client.post("/requests", headers=seller, json={"product_name": "x", "quantity": 1})
    assert res.status_code == 403


def test_client_cannot_make_offer(client):
    buyer = auth_headers(client, "b2@acme.com", "client")
    req = create_request(client, buyer)
    res = client.post(f"/requests/{req['id']}/offers", headers=buyer,
                      json={"amount": 100, "currency": "COP"})
    assert res.status_code == 403


def test_cannot_respond_to_own_proposal(client):
    buyer = auth_headers(client, "b3@acme.com", "client")
    seller = auth_headers(client, "s3@acme.com", "supplier")
    req = create_request(client, buyer)
    neg = make_offer(client, seller, req["id"], 500_000)
    # Seller just proposed; seller trying to accept own offer must fail.
    res = client.post(f"/negotiations/{neg['id']}/accept", headers=seller)
    assert res.status_code == 409


def test_cannot_act_on_terminal_negotiation(client):
    buyer = auth_headers(client, "b4@acme.com", "client")
    seller = auth_headers(client, "s4@acme.com", "supplier")
    req = create_request(client, buyer)
    neg = make_offer(client, seller, req["id"], 500_000)
    client.post(f"/negotiations/{neg['id']}/accept", headers=buyer)
    # Already accepted -> further actions rejected.
    res = client.post(f"/negotiations/{neg['id']}/reject", headers=seller)
    assert res.status_code == 409


def test_non_participant_cannot_view(client):
    buyer = auth_headers(client, "b5@acme.com", "client")
    seller = auth_headers(client, "s5@acme.com", "supplier")
    intruder = auth_headers(client, "s6@acme.com", "supplier")
    req = create_request(client, buyer)
    neg = make_offer(client, seller, req["id"], 500_000)
    res = client.get(f"/negotiations/{neg['id']}", headers=intruder)
    assert res.status_code == 403


def test_accept_supersedes_sibling_negotiations(client):
    buyer = auth_headers(client, "b7@acme.com", "client")
    seller_a = auth_headers(client, "sa@acme.com", "supplier")
    seller_b = auth_headers(client, "sb@acme.com", "supplier")
    req = create_request(client, buyer)
    neg_a = make_offer(client, seller_a, req["id"], 900_000)
    neg_b = make_offer(client, seller_b, req["id"], 950_000)

    client.post(f"/negotiations/{neg_a['id']}/accept", headers=buyer)

    losing = client.get(f"/negotiations/{neg_b['id']}", headers=buyer).json()
    assert losing["status"] == "rejected"
