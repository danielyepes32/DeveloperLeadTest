"""Shared FastAPI dependencies: authentication, RBAC and idempotency."""
from __future__ import annotations

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import Role
from app.models import IdempotencyKey, User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise _CREDENTIALS_EXC from exc

    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    return user


def require_role(role: Role):
    """Dependency factory enforcing a single role (RBAC)."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{role}'",
            )
        return user

    return _guard


class Idempotency:
    """Persists POST responses keyed by the client-supplied Idempotency-Key.

    A retry with the same key (same user) returns the stored response instead of
    re-executing the side effect — making offer/decision creation safe to retry.
    """

    def __init__(self, db: Session, user: User, key: str | None):
        self.db = db
        self.user = user
        self.key = key

    def lookup(self) -> IdempotencyKey | None:
        if not self.key:
            return None
        record = self.db.get(IdempotencyKey, self.key)
        if record and record.user_id != self.user.id:
            # Same key reused by a different user — treat as a client error.
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Idempotency-Key already used by another user")
        return record

    def save(self, *, method: str, path: str, status_code: int, body: str) -> None:
        """Stage the idempotency record. Committed by the caller in the SAME
        transaction as the side effect, so key and effect are atomic."""
        if not self.key:
            return
        self.db.add(IdempotencyKey(
            key=self.key,
            user_id=self.user.id,
            method=method,
            path=path,
            response_status=status_code,
            response_body=body,
        ))

    def commit(self) -> None:
        self.db.commit()


def get_idempotency(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Idempotency:
    return Idempotency(db=db, user=user, key=idempotency_key)
