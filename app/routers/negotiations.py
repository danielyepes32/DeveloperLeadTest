"""Offer + decision endpoints: the negotiation flow (offer/counter/accept/reject)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Idempotency, get_current_user, get_idempotency, require_role
from app.enums import Role
from app.models import User
from app.routers._helpers import idempotent
from app.schemas import (
    CounterIn,
    NegotiationDetailOut,
    NegotiationOut,
    OfferIn,
)
from app.services import negotiation

# A supplier creates an offer against a request -> opens a negotiation thread.
offers_router = APIRouter(prefix="/requests", tags=["negotiations"])


@offers_router.post(
    "/{request_id}/offers",
    response_model=NegotiationOut,
    status_code=status.HTTP_201_CREATED,
)
def make_offer(
    request_id: int,
    payload: OfferIn,
    request: Request,
    db: Session = Depends(get_db),
    supplier: User = Depends(require_role(Role.SUPPLIER)),
    idem: Idempotency = Depends(get_idempotency),
):
    return idempotent(
        idem, request,
        lambda: NegotiationOut.model_validate(
            negotiation.make_offer(db, supplier, request_id, payload)
        ),
    )


router = APIRouter(prefix="/negotiations", tags=["negotiations"])


@router.get("", response_model=list[NegotiationOut])
def list_negotiations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list:
    return negotiation.list_negotiations(db, user, limit=limit, offset=offset)


@router.get("/{negotiation_id}", response_model=NegotiationDetailOut)
def get_negotiation(
    negotiation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return negotiation.get_negotiation(db, user, negotiation_id)


@router.post("/{negotiation_id}/accept", response_model=NegotiationOut)
def accept(
    negotiation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idem: Idempotency = Depends(get_idempotency),
):
    return idempotent(
        idem, request,
        lambda: NegotiationOut.model_validate(
            negotiation.accept(db, user, negotiation_id)
        ),
        status_code=200,
    )


@router.post("/{negotiation_id}/reject", response_model=NegotiationOut)
def reject(
    negotiation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idem: Idempotency = Depends(get_idempotency),
):
    return idempotent(
        idem, request,
        lambda: NegotiationOut.model_validate(
            negotiation.reject(db, user, negotiation_id)
        ),
        status_code=200,
    )


@router.post("/{negotiation_id}/counter", response_model=NegotiationOut)
def counter(
    negotiation_id: int,
    payload: CounterIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idem: Idempotency = Depends(get_idempotency),
):
    return idempotent(
        idem, request,
        lambda: NegotiationOut.model_validate(
            negotiation.counter(db, user, negotiation_id, payload)
        ),
        status_code=200,
    )
