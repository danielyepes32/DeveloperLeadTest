"""SQLAlchemy ORM models.

Status/role values are kept as plain strings (validated by enums in the domain
layer) so the schema stays portable across PostgreSQL and SQLite without native
ENUM types — one less migration footgun.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)  # 'client' | 'supplier'
    full_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProductRequest(Base):
    __tablename__ = "product_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    negotiations: Mapped[list[Negotiation]] = relationship(back_populates="request")


class Negotiation(Base):
    """One negotiation thread per (request, supplier)."""

    __tablename__ = "negotiations"
    __table_args__ = (UniqueConstraint("request_id", "supplier_id", name="uq_request_supplier"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("product_requests.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    agreed_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    request: Mapped[ProductRequest] = relationship(back_populates="negotiations")
    proposals: Mapped[list[Proposal]] = relationship(
        back_populates="negotiation", order_by="Proposal.id"
    )

    @property
    def last_actor_id(self) -> int | None:
        """Actor of the most recent proposal — i.e. whose turn it is NOT."""
        return self.proposals[-1].actor_id if self.proposals else None


class Proposal(Base):
    """Append-only price proposal. The ordered chain IS the negotiation history."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    negotiation_id: Mapped[int] = mapped_column(ForeignKey("negotiations.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))  # 'offer' | 'counter'
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="COP")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    negotiation: Mapped[Negotiation] = relationship(back_populates="proposals")


class AuditLog(Base):
    """Immutable trace of every state transition for traceability/compliance."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)  # correlation id
    actor_id: Mapped[int | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class IdempotencyKey(Base):
    """Stores the response for a given Idempotency-Key so retries are safe."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(255))
    response_status: Mapped[int] = mapped_column()
    response_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
