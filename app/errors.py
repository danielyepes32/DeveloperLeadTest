"""Domain errors and their mapping to HTTP responses.

Services raise these provider-agnostic errors; a single exception handler turns
them into consistent JSON. This keeps HTTP concerns out of the domain layer.
"""
from __future__ import annotations


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"


class ConflictError(DomainError):
    """Invalid state transition or business-rule violation."""

    status_code = 409
    code = "conflict"


class ValidationError(DomainError):
    status_code = 422
    code = "validation_error"
