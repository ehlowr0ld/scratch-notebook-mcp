"""Centralized error codes and helper utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "NOT_FOUND",
    "INVALID_ID",
    "INVALID_INDEX",
    "CAPACITY_LIMIT_REACHED",
    "VALIDATION_ERROR",
    "VALIDATION_TIMEOUT",
    "CONFIG_ERROR",
    "INTERNAL_ERROR",
    "UNAUTHORIZED",
    "ScratchNotebookError",
    "error_payload",
]

NOT_FOUND = "NOT_FOUND"
INVALID_ID = "INVALID_ID"
INVALID_INDEX = "INVALID_INDEX"
CAPACITY_LIMIT_REACHED = "CAPACITY_LIMIT_REACHED"
VALIDATION_ERROR = "VALIDATION_ERROR"
VALIDATION_TIMEOUT = "VALIDATION_TIMEOUT"
CONFIG_ERROR = "CONFIG_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"
UNAUTHORIZED = "UNAUTHORIZED"


@dataclass(slots=True)
class ScratchNotebookError(Exception):
    """Domain-specific exception carrying an error code and message."""

    code: str
    message: str
    details: Mapping[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover - delegation to message
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return error_payload(self.code, self.message, details=self.details)


def error_payload(code: str, message: str, *, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a structured error payload used in tool responses."""

    payload: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details:
        payload["details"] = dict(details)
    return payload
