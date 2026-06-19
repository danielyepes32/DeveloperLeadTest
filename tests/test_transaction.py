"""Atomicity: a failure mid-operation rolls back the whole DB transaction.

Proves the unit-of-work guarantee — services only flush; if anything raises
before the single commit, get_db rolls the transaction back and nothing persists.
"""
from __future__ import annotations

import pytest

from app.services import negotiation as negmod
from tests.helpers import auth_headers, create_request, make_offer


def test_failed_counter_rolls_back(client, monkeypatch):
    buyer = auth_headers(client, "tx-b@acme.com", "client")
    seller = auth_headers(client, "tx-s@acme.com", "supplier")
    req = create_request(client, buyer)
    neg = make_offer(client, seller, req["id"], 1000)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure after the proposal was staged")

    # Fail AFTER the counter proposal has been added+flushed, before commit.
    monkeypatch.setattr(negmod.audit, "record", boom)
    with pytest.raises(RuntimeError):
        client.post(f"/negotiations/{neg['id']}/counter", headers=buyer, json={"amount": 800})

    # Roll back leaves no trace: still active, only the original offer proposal.
    monkeypatch.undo()
    detail = client.get(f"/negotiations/{neg['id']}", headers=seller).json()
    assert detail["status"] == "active"
    assert [p["kind"] for p in detail["proposals"]] == ["offer"]
