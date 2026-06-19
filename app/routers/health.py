"""Liveness and readiness probes (Kubernetes/compose health checks)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness — the process is up and serving."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    """Readiness — dependencies (the database) are reachable."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised only on DB outage
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not reachable",
        ) from exc
    return {"status": "ready"}
