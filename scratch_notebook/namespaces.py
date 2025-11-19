"""Namespace management helpers for MCP tools."""

from __future__ import annotations

from typing import Any

from .errors import VALIDATION_ERROR, ScratchNotebookError
from .storage import Storage


def list_namespaces(storage: Storage) -> list[dict[str, Any]]:
    """Return namespaces and their scratchpad counts for the active tenant."""

    return storage.list_namespaces()


def create_namespace(storage: Storage, namespace: str) -> tuple[str, bool]:
    """Register a namespace string for the active tenant."""

    return storage.register_namespace(namespace)


def rename_namespace(
    storage: Storage,
    old_namespace: str,
    new_namespace: str,
    *,
    migrate_scratchpads: bool = True,
) -> tuple[str, int]:
    """Rename a namespace, optionally migrating existing scratchpads."""

    migrate = _coerce_bool(migrate_scratchpads, "migrate_scratchpads")
    return storage.rename_namespace(old_namespace, new_namespace, migrate_scratchpads=migrate)


def delete_namespace(
    storage: Storage,
    namespace: str,
    *,
    delete_scratchpads: bool = False,
) -> tuple[bool, int]:
    """Delete a namespace, optionally cascading to scratchpads."""

    cascade = _coerce_bool(delete_scratchpads, "delete_scratchpads")
    return storage.delete_namespace(namespace, delete_scratchpads=cascade)


def _coerce_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None,):
        return False
    raise ScratchNotebookError(VALIDATION_ERROR, f"{field_name} must be a boolean")
