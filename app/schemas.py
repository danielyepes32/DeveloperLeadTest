"""Pydantic v2 request/response schemas — the API contract & validation layer."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import NegotiationStatus, ProposalKind, RequestStatus, Role

# ---------------------------------------------------------------- auth


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    role: Role


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Role


# ---------------------------------------------------------------- product requests


class ProductRequestIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    quantity: int = Field(default=1, ge=1)


class ProductRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    product_name: str
    description: str
    quantity: int
    status: RequestStatus
    created_at: datetime


# ---------------------------------------------------------------- proposals / negotiations


class OfferIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="COP", min_length=3, max_length=3)
    message: str | None = Field(default=None, max_length=500)


class CounterIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    message: str | None = Field(default=None, max_length=500)


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int
    actor_role: Role
    kind: ProposalKind
    amount: Decimal
    currency: str
    message: str | None
    created_at: datetime


class NegotiationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    supplier_id: int
    status: NegotiationStatus
    agreed_amount: Decimal | None
    last_actor_id: int | None = None
    created_at: datetime


class NegotiationDetailOut(NegotiationOut):
    proposals: list[ProposalOut] = []


# ---------------------------------------------------------------- errors


class ErrorOut(BaseModel):
    code: str
    message: str
