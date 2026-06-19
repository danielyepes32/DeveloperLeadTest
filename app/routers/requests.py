"""Product request endpoints (client creates; supplier browses)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Idempotency, get_current_user, get_idempotency, require_role
from app.enums import Role
from app.models import User
from app.routers._helpers import idempotent
from app.schemas import ProductRequestIn, ProductRequestOut
from app.services import negotiation

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=ProductRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: ProductRequestIn,
    request: Request,
    db: Session = Depends(get_db),
    client: User = Depends(require_role(Role.CLIENT)),
    idem: Idempotency = Depends(get_idempotency),
):
    return idempotent(
        idem, request,
        lambda: ProductRequestOut.model_validate(
            negotiation.create_request(db, client, payload)
        ),
    )


@router.get("", response_model=list[ProductRequestOut])
def list_requests(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list:
    return negotiation.list_requests(db, user, limit=limit, offset=offset)


@router.get("/{request_id}", response_model=ProductRequestOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return negotiation.get_request(db, user, request_id)
