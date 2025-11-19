"""Public storage interface backed by LanceDB."""

from .storage_lancedb import DEFAULT_TENANT_ID, Storage, StorageError

__all__ = ["Storage", "StorageError", "DEFAULT_TENANT_ID"]
