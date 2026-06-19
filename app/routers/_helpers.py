"""Helpers shared by routers — idempotent response handling."""
from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.deps import Idempotency


def idempotent(
    idem: Idempotency,
    request: Request,
    produce: Callable[[], BaseModel],
    *,
    status_code: int = 201,
) -> JSONResponse:
    """Return a cached response for a repeated Idempotency-Key, else run `produce`.

    `produce` performs the side effect and returns the response model; its JSON is
    persisted against the key so retries are byte-for-byte identical and safe.
    """
    cached = idem.lookup()
    if cached is not None:
        return JSONResponse(status_code=cached.response_status,
                            content=json.loads(cached.response_body))

    model = produce()  # runs the side effect (services only flush, never commit)
    body = model.model_dump_json()
    idem.save(method=request.method, path=request.url.path,
              status_code=status_code, body=body)
    idem.commit()  # single atomic commit: side effect + idempotency key together
    return JSONResponse(status_code=status_code, content=json.loads(body))
