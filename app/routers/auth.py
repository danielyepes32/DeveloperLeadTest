"""Authentication endpoints: register and login (JWT bearer)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.ratelimit import rate_limit_login
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token
from app.services import users

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> User:
    return users.register_user(db, payload)


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginIn,
    db: Session = Depends(get_db),
    _rate_limited: None = Depends(rate_limit_login),
) -> TokenOut:
    user = users.authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(subject=str(user.id), role=user.role)
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
