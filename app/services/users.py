"""User registration and authentication."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import Role
from app.errors import ConflictError
from app.models import User
from app.schemas import RegisterIn
from app.security import hash_password, verify_password
from app.services import audit


def register_user(db: Session, data: RegisterIn) -> User:
    existing = db.scalar(select(User).where(User.email == data.email))
    if existing is not None:
        raise ConflictError("Email already registered")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=Role(data.role).value,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.registered",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        details={"role": user.role},
    )
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
