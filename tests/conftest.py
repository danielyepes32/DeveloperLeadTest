"""Test fixtures. Tests run against an in-memory SQLite DB for speed and isolation.

DATABASE_URL is set before importing the app so the engine binds to SQLite. The
StaticPool in app.database keeps the in-memory schema alive across the connection.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
# Disable login rate limiting by default so the many logins across the suite don't
# trip the limiter; the dedicated rate-limit test lowers it explicitly.
os.environ.setdefault("LOGIN_RATE_LIMIT", "100000")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
