"""Structured JSON logging with a per-request correlation id.

Every log line is a single JSON object so it can be ingested by Loki/ELK/Datadog
without parsing. The current request id is carried in a contextvar and injected
into every record, giving end-to-end traceability across the call stack.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_ctx.get(),
            "message": record.getMessage(),
        }
        # Allow structured extras: logger.info("msg", extra={"context": {...}})
        if isinstance(getattr(record, "context", None), dict):
            payload.update(record.context)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Uvicorn access logs are redundant with our request middleware; quiet them.
    logging.getLogger("uvicorn.access").handlers = []


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
