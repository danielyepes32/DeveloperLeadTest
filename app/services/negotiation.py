"""Negotiation domain logic — the turn-based state machine at the core of the system.

Rules enforced here (independent of HTTP/transport):
  * Only the owner client of a request may act on its negotiations as the client.
  * Only the supplier party may act as the supplier.
  * On an ACTIVE negotiation, only the *counterparty of the last proposal* may
    respond — you cannot reply to your own proposal.
  * accept / reject / counter are illegal on a terminal (accepted/rejected) thread.
  * Accepting one offer closes the request and supersedes its sibling negotiations.

Every transition is written to the audit trail (traceability) within the same DB
transaction as the state change (atomicity).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import NegotiationStatus, ProposalKind, RequestStatus, Role
from app.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Negotiation, ProductRequest, Proposal, User
from app.schemas import CounterIn, OfferIn, ProductRequestIn
from app.services import audit

# ---------------------------------------------------------------- requests


def create_request(db: Session, client: User, data: ProductRequestIn) -> ProductRequest:
    req = ProductRequest(
        client_id=client.id,
        product_name=data.product_name,
        description=data.description,
        quantity=data.quantity,
        status=RequestStatus.OPEN.value,
    )
    db.add(req)
    db.flush()
    audit.record(db, action="request.created", entity_type="product_request",
                 entity_id=req.id, actor_id=client.id,
                 details={"product_name": req.product_name, "quantity": req.quantity})
    db.flush()
    return req


def list_requests(
    db: Session, user: User, *, limit: int = 50, offset: int = 0
) -> list[ProductRequest]:
    stmt = select(ProductRequest)
    if user.role == Role.CLIENT:
        stmt = stmt.where(ProductRequest.client_id == user.id)
    else:  # suppliers browse the marketplace of open requests
        stmt = stmt.where(ProductRequest.status == RequestStatus.OPEN.value)
    stmt = stmt.order_by(ProductRequest.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def get_request(db: Session, user: User, request_id: int) -> ProductRequest:
    req = db.get(ProductRequest, request_id)
    if req is None:
        raise NotFoundError("Request not found")
    if user.role == Role.CLIENT and req.client_id != user.id:
        raise PermissionDeniedError("Not your request")
    return req


# ---------------------------------------------------------------- offers / negotiations


def make_offer(db: Session, supplier: User, request_id: int, data: OfferIn) -> Negotiation:
    # Lock the request row so a concurrent accept (which closes the request)
    # cannot race with opening a new negotiation on it.
    req = db.get(ProductRequest, request_id, with_for_update=True)
    if req is None:
        raise NotFoundError("Request not found")
    if req.status != RequestStatus.OPEN.value:
        raise ConflictError("Request is not open for offers")

    existing = db.scalar(
        select(Negotiation).where(
            Negotiation.request_id == request_id,
            Negotiation.supplier_id == supplier.id,
        )
    )
    if existing is not None:
        raise ConflictError("You already have a negotiation on this request")

    neg = Negotiation(
        request_id=request_id,
        supplier_id=supplier.id,
        status=NegotiationStatus.ACTIVE.value,
    )
    db.add(neg)
    db.flush()
    _add_proposal(db, neg, supplier, ProposalKind.OFFER, data.amount, data.currency, data.message)
    audit.record(db, action="offer.created", entity_type="negotiation",
                 entity_id=neg.id, actor_id=supplier.id,
                 details={"amount": str(data.amount), "currency": data.currency})
    db.flush()
    return neg


def list_negotiations(
    db: Session, user: User, *, limit: int = 50, offset: int = 0
) -> list[Negotiation]:
    if user.role == Role.SUPPLIER:
        stmt = select(Negotiation).where(Negotiation.supplier_id == user.id)
    else:
        stmt = (
            select(Negotiation)
            .join(ProductRequest, Negotiation.request_id == ProductRequest.id)
            .where(ProductRequest.client_id == user.id)
        )
    stmt = stmt.order_by(Negotiation.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def get_negotiation(db: Session, user: User, negotiation_id: int) -> Negotiation:
    neg = db.get(Negotiation, negotiation_id)
    if neg is None:
        raise NotFoundError("Negotiation not found")
    _ensure_participant(db, user, neg)
    return neg


# ---------------------------------------------------------------- client/supplier decisions


def accept(db: Session, user: User, negotiation_id: int) -> Negotiation:
    neg = _load_active_for_response(db, user, negotiation_id)
    last = _last_proposal(db, neg)

    neg.status = NegotiationStatus.ACCEPTED.value
    neg.agreed_amount = last.amount
    db.flush()

    # Lock the request row to serialize concurrent accepts on the same request.
    req = db.get(ProductRequest, neg.request_id, with_for_update=True)
    req.status = RequestStatus.CLOSED.value
    _supersede_siblings(db, req, winner_id=neg.id)

    audit.record(db, action="negotiation.accepted", entity_type="negotiation",
                 entity_id=neg.id, actor_id=user.id,
                 details={"agreed_amount": str(last.amount)})
    db.flush()
    return neg


def reject(db: Session, user: User, negotiation_id: int) -> Negotiation:
    neg = _load_active_for_response(db, user, negotiation_id)
    neg.status = NegotiationStatus.REJECTED.value
    db.flush()
    audit.record(db, action="negotiation.rejected", entity_type="negotiation",
                 entity_id=neg.id, actor_id=user.id)
    db.flush()
    return neg


def counter(db: Session, user: User, negotiation_id: int, data: CounterIn) -> Negotiation:
    neg = _load_active_for_response(db, user, negotiation_id)
    currency = _last_proposal(db, neg).currency  # keep negotiating in the same currency
    _add_proposal(db, neg, user, ProposalKind.COUNTER, data.amount, currency, data.message)
    audit.record(db, action="negotiation.countered", entity_type="negotiation",
                 entity_id=neg.id, actor_id=user.id,
                 details={"amount": str(data.amount), "currency": currency})
    db.flush()
    return neg


# ---------------------------------------------------------------- internals


def _add_proposal(db, neg, actor, kind, amount, currency, message) -> Proposal:
    proposal = Proposal(
        negotiation_id=neg.id,
        actor_id=actor.id,
        actor_role=actor.role,
        kind=kind.value,
        amount=amount,
        currency=currency,
        message=message,
    )
    db.add(proposal)
    db.flush()
    return proposal


def _last_proposal(db: Session, neg: Negotiation) -> Proposal:
    proposal = db.scalar(
        select(Proposal)
        .where(Proposal.negotiation_id == neg.id)
        .order_by(Proposal.id.desc())
        .limit(1)
    )
    if proposal is None:  # should never happen — a negotiation is born with a proposal
        raise ConflictError("Negotiation has no proposals")
    return proposal


def _ensure_participant(db: Session, user: User, neg: Negotiation) -> ProductRequest:
    req = db.get(ProductRequest, neg.request_id)
    if user.id not in (req.client_id, neg.supplier_id):
        raise PermissionDeniedError("You are not a participant in this negotiation")
    return req


def _load_active_for_response(db: Session, user: User, negotiation_id: int) -> Negotiation:
    # Pessimistic row lock: prevents lost updates / double-accept when the two
    # parties act concurrently (no-op on SQLite, enforced on PostgreSQL).
    neg = db.get(Negotiation, negotiation_id, with_for_update=True)
    if neg is None:
        raise NotFoundError("Negotiation not found")
    _ensure_participant(db, user, neg)
    if neg.status != NegotiationStatus.ACTIVE.value:
        raise ConflictError(f"Negotiation is already {neg.status}")
    last = _last_proposal(db, neg)
    if last.actor_id == user.id:
        raise ConflictError("Waiting for the counterparty to respond to your proposal")
    return neg


def _supersede_siblings(db: Session, req: ProductRequest, *, winner_id: int) -> None:
    siblings = db.scalars(
        select(Negotiation).where(
            Negotiation.request_id == req.id,
            Negotiation.status == NegotiationStatus.ACTIVE.value,
            Negotiation.id != winner_id,
        )
    )
    for sib in siblings:
        sib.status = NegotiationStatus.REJECTED.value
        audit.record(db, action="negotiation.superseded", entity_type="negotiation",
                     entity_id=sib.id, actor_id=None, details={"winner_id": winner_id})
    db.flush()
