"""Audit trail writer — appends an immutable record for every state transition."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.logging_config import get_logger, request_id_ctx
from app.models import AuditLog

logger = get_logger("app.audit")


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None,
    actor_id: int | None,
    details: dict | None = None,
) -> None:
    """Persist an audit entry tagged with the current correlation id.

    Flushed (not committed) so it shares the caller's transaction: if the
    business operation rolls back, its audit entry rolls back with it.
    """
    correlation_id = request_id_ctx.get()
    entry = AuditLog(
        request_id=correlation_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(entry)
    db.flush()
    logger.info(
        "audit",
        extra={"context": {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_id": actor_id,
        }},
    )
