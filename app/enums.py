"""Domain enumerations (string-valued for portable persistence)."""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    CLIENT = "client"
    SUPPLIER = "supplier"


class RequestStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class NegotiationStatus(StrEnum):
    ACTIVE = "active"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalKind(StrEnum):
    OFFER = "offer"
    COUNTER = "counter"
