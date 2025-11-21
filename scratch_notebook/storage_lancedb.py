"""LanceDB-backed storage implementation for scratch notebooks."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from dataclasses import dataclass
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone, timedelta
from functools import wraps
from threading import RLock
from typing import Any

import lancedb
import pyarrow as pa

from . import models
from .config import Config
from .errors import (
    CAPACITY_LIMIT_REACHED,
    CONFIG_ERROR,
    INVALID_ID,
    INVALID_INDEX,
    NOT_FOUND,
    VALIDATION_ERROR,
    ScratchNotebookError,
)
from . import metrics
from .logging import get_logger

logger = get_logger(__name__)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SCRATCHPAD_TABLE_NAME = "scratchpads"
_EMBEDDINGS_TABLE_NAME = "embeddings"
_NAMESPACES_TABLE_NAME = "namespaces"
DEFAULT_TENANT_ID = "default"

_SCRATCHPAD_SCHEMA = pa.schema(
    [
        pa.field("scratch_id", pa.string()),
        pa.field("tenant_id", pa.string()),
        pa.field("namespace", pa.string()),
        pa.field("title", pa.string()),
        pa.field("description", pa.string()),
        pa.field("summary", pa.string()),
        pa.field("tags", pa.list_(pa.string())),
        pa.field("cell_tags", pa.list_(pa.string())),
        pa.field("cell_count", pa.int32()),
        pa.field("metadata_json", pa.large_string()),
        pa.field("cells_json", pa.large_string()),
        pa.field("schemas_json", pa.large_string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at", pa.timestamp("us", tz="UTC")),
        pa.field("last_access_at", pa.timestamp("us", tz="UTC")),
    ]
)

_NAMESPACES_SCHEMA = pa.schema(
    [
        pa.field("namespace", pa.string()),
        pa.field("tenant_id", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)


def _build_embedding_schema(dimension: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("scratch_id", pa.string()),
            pa.field("cell_id", pa.string()),
            pa.field("tenant_id", pa.string()),
            pa.field("namespace", pa.string()),
            pa.field("tags", pa.list_(pa.string())),
            pa.field("title", pa.string()),
            pa.field("description", pa.string()),
            pa.field("summary", pa.string()),
            pa.field("snippet", pa.string()),
            pa.field("cell_index", pa.int32()),
            pa.field("embedding", pa.list_(pa.float32(), dimension)),
            pa.field("updated_at", pa.timestamp("us", tz="UTC")),
        ]
    )


@dataclass(slots=True)
class ScratchpadSnapshot:
    row: dict[str, Any]
    embeddings: list[dict[str, Any]]


class StorageError(ScratchNotebookError):
    """Raised when storage operations fail."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_timestamp(value: Any, *, default: datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return default


def _ensure_string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result: list[str] = []
        for item in value:
            if item is None:
                continue
            result.append(str(item))
        return result
    if isinstance(value, (str, bytes)):
        cleaned = value.strip() if isinstance(value, str) else value.decode("utf-8", "ignore")
        return [cleaned] if cleaned else []
    return [str(value)]


def _aggregate_cell_tags(cells: Iterable[models.ScratchCell]) -> list[str]:
    tags: set[str] = set()
    for cell in cells:
        for tag in _ensure_string_list(cell.metadata.get("tags")):
            tags.add(tag)
    return sorted(tags)


def _encode_json(payload: Any, *, context: str) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise StorageError(CONFIG_ERROR, f"Unable to serialize {context}") from exc


def _format_filter(field: str, value: str) -> str:
    escaped = value.replace("'", "\\'")
    return f"{field} = '{escaped}'"


def _quote_literal(value: str) -> str:
    escaped = value.replace("'", "\\'")
    return f"'{escaped}'"


def _normalize_namespace_value(namespace: str) -> str:
    if not isinstance(namespace, str):
        raise ScratchNotebookError(VALIDATION_ERROR, "Namespace must be a string")
    normalized = namespace.strip()
    if not normalized:
        raise ScratchNotebookError(VALIDATION_ERROR, "Namespace must not be empty")
    return normalized


def synchronized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Storage:
    """LanceDB-backed persistence for scratch notebooks."""

    def __init__(self, config: Config, tenant_id: str | None = None) -> None:
        self._config = config
        self._root = config.storage_dir
        self._root.mkdir(parents=True, exist_ok=True)
        tenant_value = (tenant_id or "").strip() if tenant_id else ""
        self._tenant_id = tenant_value or DEFAULT_TENANT_ID
        self._lock = RLock()
        self._last_evicted: list[str] = []
        self._pending_eviction_snapshots: list[ScratchpadSnapshot] = []
        self._eviction_policy = (config.eviction_policy or "").strip().lower() or "discard"

        try:
            self._db = lancedb.connect(str(self._root))
        except Exception as exc:  # pragma: no cover - environment specific
            raise StorageError(CONFIG_ERROR, "Unable to open LanceDB database", details={"path": str(self._root)}) from exc

        self._table = self._ensure_table()
        self._namespaces_table = self._ensure_namespaces_table()
        self._embeddings_table = None
        self._embedding_dimension = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @synchronized
    def validate_identifier(self, scratch_id: str) -> None:
        self._ensure_valid_identifier(scratch_id)

    @synchronized
    def has_scratchpad(self, scratch_id: str) -> bool:
        self._ensure_valid_identifier(scratch_id)
        return self._fetch_row(scratch_id) is not None

    @synchronized
    def set_tenant(self, tenant_id: str | None) -> None:
        tenant_value = (tenant_id or "").strip() if tenant_id else ""
        self._tenant_id = tenant_value or DEFAULT_TENANT_ID

    @synchronized
    def tenant_id(self) -> str:
        return self._tenant_id

    @synchronized
    def migrate_default_tenant(self, target_tenant: str | None) -> list[str]:
        desired = (target_tenant or "").strip() if target_tenant else ""
        if not desired or desired == DEFAULT_TENANT_ID:
            return []

        arrow_table = self._table.to_arrow()
        rows = arrow_table.to_pylist()
        migrated: list[str] = []
        original_tenant = self._tenant_id

        for row in rows:
            tenant_value = (row.get("tenant_id") or "").strip() or DEFAULT_TENANT_ID
            if tenant_value != DEFAULT_TENANT_ID:
                continue
            scratch_id = row.get("scratch_id")
            if not scratch_id:
                continue

            pad = self._pad_from_row(row)
            embeddings_rows = self._capture_embeddings_rows(scratch_id)
            for embedding in embeddings_rows:
                embedding["tenant_id"] = desired

            self._tenant_id = desired
            self._write_pad(pad, existing_row=row, touch_access=False)
            if embeddings_rows:
                self._restore_embeddings_rows(scratch_id, embeddings_rows)
            migrated.append(scratch_id)

        self._tenant_id = desired if migrated else original_tenant
        return migrated

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    @synchronized
    def create_scratchpad(self, pad: models.Scratchpad, *, overwrite: bool = True) -> models.Scratchpad:
        self._ensure_valid_identifier(pad.scratch_id)
        existing = self._fetch_row(pad.scratch_id)

        if existing is not None and not overwrite:
            raise StorageError(INVALID_ID, f"Scratchpad {pad.scratch_id} already exists")

        self._last_evicted.clear()
        if existing is None:
            self._enforce_capacity_limit()
        self._enforce_cell_limits(pad)

        self._write_pad(pad, existing)
        return pad

    @synchronized
    def read_scratchpad(self, scratch_id: str) -> models.Scratchpad:
        self._ensure_valid_identifier(scratch_id)
        row = self._fetch_row(scratch_id)
        if row is None:
            raise StorageError(NOT_FOUND, f"Scratchpad {scratch_id} not found")
        updated_row = self._touch_last_access(row)
        return self._pad_from_row(updated_row)

    @synchronized
    def delete_scratchpad(self, scratch_id: str) -> bool:
        self._ensure_valid_identifier(scratch_id)
        if self._fetch_row(scratch_id) is None:
            return False
        self._delete_row(scratch_id)
        self._restore_embeddings_rows(scratch_id, [])
        return self._fetch_row(scratch_id) is None

    @synchronized
    def register_namespace(self, namespace: str) -> tuple[str, bool]:
        normalized = _normalize_namespace_value(namespace)
        table = self._namespaces_table
        existing = [
            row
            for row in table.to_arrow().to_pylist()
            if (row.get("tenant_id") or "") == self._tenant_id and (row.get("namespace") or "") == normalized
        ]
        if existing:
            return normalized, False
        table.add(
            [
                {
                    "namespace": normalized,
                    "tenant_id": self._tenant_id,
                    "created_at": _now(),
                }
            ]
        )
        return normalized, True

    @synchronized
    def list_namespaces(self) -> list[dict[str, Any]]:
        table_rows = [
            row
            for row in self._namespaces_table.to_arrow().to_pylist()
            if (row.get("tenant_id") or "") == self._tenant_id
        ]
        registry = {str(row.get("namespace") or ""): row for row in table_rows}

        scratchpad_rows = [
            row
            for row in self._table.to_arrow().to_pylist()
            if (row.get("tenant_id") or "") == self._tenant_id
        ]
        counts: Counter[str] = Counter()
        for row in scratchpad_rows:
            namespace_value = (row.get("namespace") or "").strip()
            if namespace_value:
                counts[namespace_value] += 1

        namespaces = set(registry.keys()) | set(counts.keys())
        entries: list[dict[str, Any]] = []
        for name in namespaces:
            if not name:
                continue
            entries.append(
                {
                    "namespace": name,
                    "scratchpad_count": counts.get(name, 0),
                }
            )
        entries.sort(key=lambda item: item["namespace"])
        return entries

    @synchronized
    def rename_namespace(
        self,
        old_namespace: str,
        new_namespace: str,
        *,
        migrate_scratchpads: bool = True,
    ) -> tuple[str, int]:
        source = _normalize_namespace_value(old_namespace)
        target = _normalize_namespace_value(new_namespace)

        if source == target:
            # Ensure namespace exists; create if missing but no migration needed.
            self.register_namespace(target)
            return target, 0

        table_rows = [
            row
            for row in self._namespaces_table.to_arrow().to_pylist()
            if (row.get("tenant_id") or "") == self._tenant_id
        ]
        existing_names = {str(row.get("namespace") or "") for row in table_rows}
        if source not in existing_names:
            raise ScratchNotebookError(NOT_FOUND, f"Namespace '{source}' not found")
        if target in existing_names:
            raise ScratchNotebookError(VALIDATION_ERROR, f"Namespace '{target}' already exists")

        scratchpad_rows = [
            row
            for row in self._table.to_arrow().to_pylist()
            if (row.get("tenant_id") or "") == self._tenant_id and (row.get("namespace") or "") == source
        ]

        if scratchpad_rows and not migrate_scratchpads:
            raise ScratchNotebookError(
                VALIDATION_ERROR,
                f"Namespace '{source}' has {len(scratchpad_rows)} scratchpad(s); set migrate_scratchpads=true to rename.",
            )

        migrated_count = 0
        for row in scratchpad_rows:
            scratch_id = row.get("scratch_id")
            if not scratch_id:
                continue
            pad = self._pad_from_row(row)
            pad.metadata = dict(pad.metadata or {})
            pad.metadata["namespace"] = target
            embeddings_rows = self._capture_embeddings_rows(scratch_id)
            for embedding in embeddings_rows:
                embedding["namespace"] = target
            self._write_pad(pad, existing_row=row)
            if embeddings_rows:
                self._restore_embeddings_rows(scratch_id, embeddings_rows)
            migrated_count += 1

        condition = f"{_format_filter('tenant_id', self._tenant_id)} AND {_format_filter('namespace', source)}"
        self._namespaces_table.delete(where=condition)
        self._namespaces_table.add(
            [
                {
                    "namespace": target,
                    "tenant_id": self._tenant_id,
                    "created_at": _now(),
                }
            ]
        )
        return target, migrated_count

    @synchronized
    def delete_namespace(self, namespace: str, *, delete_scratchpads: bool = False) -> tuple[bool, int]:
        normalized = _normalize_namespace_value(namespace)
        scratchpad_rows = [
            row
            for row in self._table.to_arrow().to_pylist()
            if (row.get("tenant_id") or "") == self._tenant_id and (row.get("namespace") or "") == normalized
        ]
        scratchpad_ids = [str(row.get("scratch_id")) for row in scratchpad_rows if row.get("scratch_id")]

        if scratchpad_ids and not delete_scratchpads:
            raise ScratchNotebookError(
                VALIDATION_ERROR,
                f"Namespace '{normalized}' cannot be deleted while {len(scratchpad_ids)} scratchpad(s) reference it.",
            )

        removed_count = 0
        if scratchpad_ids:
            for scratch_id in scratchpad_ids:
                if self.delete_scratchpad(scratch_id):
                    removed_count += 1

        table_rows = [
            row
            for row in self._namespaces_table.to_arrow().to_pylist()
            if (row.get("tenant_id") or "") == self._tenant_id and (row.get("namespace") or "") == normalized
        ]
        deleted = False
        if table_rows:
            condition = f"{_format_filter('tenant_id', self._tenant_id)} AND {_format_filter('namespace', normalized)}"
            self._namespaces_table.delete(where=condition)
            deleted = True

        if not table_rows and not scratchpad_ids:
            return False, 0

        return deleted, removed_count

    @synchronized
    def list_scratchpads(
        self,
        *,
        namespaces: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        arrow_table = self._table.to_arrow()
        entries: list[dict[str, Any]] = []
        namespace_filter: set[str] | None = None
        if namespaces:
            namespace_filter = {
                (ns.decode("utf-8", "ignore") if isinstance(ns, bytes) else str(ns)).strip()
                for ns in namespaces
                if isinstance(ns, (str, bytes)) and str(ns).strip()
            } or None
        tag_filter: set[str] | None = None
        if tags:
            tag_filter = {
                (tag.decode("utf-8", "ignore") if isinstance(tag, bytes) else str(tag)).strip()
                for tag in tags
                if isinstance(tag, (str, bytes)) and str(tag).strip()
            } or None

        rows = arrow_table.to_pylist()
        if limit is not None and limit >= 0:
            rows = rows[:limit]

        for row in rows:
            namespace_value = row.get("namespace") or ""
            if namespace_filter is not None and namespace_value not in namespace_filter:
                continue
            if tag_filter is not None:
                row_tags = {str(value) for value in (row.get("tags") or [])}
                row_cell_tags = {str(value) for value in (row.get("cell_tags") or [])}
                if not (row_tags | row_cell_tags).intersection(tag_filter):
                    continue
            entries.append(
                {
                    "scratch_id": row.get("scratch_id"),
                    "title": row.get("title"),
                    "description": row.get("description"),
                    "namespace": row.get("namespace"),
                    "cell_count": row.get("cell_count", 0) or 0,
                }
            )
        entries.sort(key=lambda item: item.get("scratch_id") or "")
        return entries

    @synchronized
    def list_tags(self, *, namespaces: Sequence[str] | None = None) -> dict[str, list[str]]:
        arrow_table = self._table.to_arrow()
        namespace_filter: set[str] | None = None
        if namespaces:
            namespace_filter = {
                (ns.decode("utf-8", "ignore") if isinstance(ns, bytes) else str(ns)).strip()
                for ns in namespaces
                if isinstance(ns, (str, bytes)) and str(ns).strip()
            } or None

        scratchpad_tags: list[str] = []
        cell_tags: list[str] = []
        seen_pad: set[str] = set()
        seen_cell: set[str] = set()

        for row in arrow_table.to_pylist():
            namespace_value = row.get("namespace") or ""
            if namespace_filter is not None and namespace_value not in namespace_filter:
                continue

            for value in row.get("tags") or []:
                tag = (value.decode("utf-8", "ignore") if isinstance(value, bytes) else str(value)).strip()
                if tag and tag not in seen_pad:
                    seen_pad.add(tag)
                    scratchpad_tags.append(tag)

            for value in row.get("cell_tags") or []:
                tag = (value.decode("utf-8", "ignore") if isinstance(value, bytes) else str(value)).strip()
                if tag and tag not in seen_cell:
                    seen_cell.add(tag)
                    cell_tags.append(tag)

        scratchpad_tags.sort()
        cell_tags.sort()
        return {"scratchpad_tags": scratchpad_tags, "cell_tags": cell_tags}

    @synchronized
    def list_cells(self, scratch_id: str) -> list[models.ScratchCell]:
        pad = self.read_scratchpad(scratch_id)
        return list(pad.cells)

    @synchronized
    def list_schemas(self, scratch_id: str) -> list[dict[str, Any]]:
        pad = self.read_scratchpad(scratch_id)
        registry = models.normalize_schema_registry_entries(pad.metadata.get("schemas"))
        entries = [dict(value) for value in registry.values()]
        entries.sort(key=lambda item: ((item.get("description") or "").lower(), item.get("name") or ""))
        return entries

    @synchronized
    def get_schema(self, scratch_id: str, schema_id: str) -> dict[str, Any]:
        pad = self.read_scratchpad(scratch_id)
        registry = models.normalize_schema_registry_entries(pad.metadata.get("schemas"))
        normalized = schema_id.lower()
        for value in registry.values():
            entry_id = str(value.get("id", "")).lower()
            if entry_id == normalized:
                return dict(value)
        raise StorageError(NOT_FOUND, "Schema not found", details={"scratch_id": scratch_id, "schema_id": schema_id})

    @synchronized
    def upsert_schema(self, scratch_id: str, entry: Mapping[str, Any]) -> dict[str, Any]:
        pad = self.read_scratchpad(scratch_id)
        registry = models.normalize_schema_registry_entries(pad.metadata.get("schemas"))

        desired_name = str(entry.get("name") or entry.get("id") or "").strip()
        if not desired_name:
            raise StorageError(CONFIG_ERROR, "Schema entry missing name", details={"scratch_id": scratch_id})

        target_name = desired_name
        entry_id = str(entry.get("id", "")).lower()
        for existing_name, existing_entry in list(registry.items()):
            if str(existing_entry.get("id", "")).lower() == entry_id and entry_id:
                target_name = existing_name
                if existing_name != desired_name:
                    registry.pop(existing_name)
                    target_name = desired_name
                break

        registry[target_name] = dict(entry)
        registry[target_name]["name"] = target_name

        canonical_registry = models.normalize_schema_registry_entries(registry)

        pad.metadata = dict(pad.metadata or {})
        pad.metadata["schemas"] = canonical_registry
        self._write_pad(pad)
        return dict(canonical_registry[target_name])

    @synchronized
    def append_cell(self, scratch_id: str, cell: models.ScratchCell) -> models.Scratchpad:
        row = self._fetch_row(scratch_id)
        if row is None:
            raise StorageError(NOT_FOUND, f"Scratchpad {scratch_id} not found")
        pad = self._pad_from_row(row)
        self._enforce_cell_limits(pad, pending_cell=cell)

        cell.index = len(pad.cells)
        pad.cells.append(cell)
        self._write_pad(pad, row)
        return pad

    @synchronized
    def replace_cell(
        self,
        scratch_id: str,
        cell_id: str,
        cell: models.ScratchCell,
        *,
        new_index: int | None = None,
    ) -> models.Scratchpad:
        row = self._fetch_row(scratch_id)
        if row is None:
            raise StorageError(NOT_FOUND, f"Scratchpad {scratch_id} not found")
        pad = self._pad_from_row(row)
        cell_lookup = {existing.cell_id: idx for idx, existing in enumerate(pad.cells)}
        current_index = cell_lookup.get(str(cell_id))
        if current_index is None:
            raise StorageError(NOT_FOUND, f"Cell id {cell_id} not found")

        target_index = current_index if new_index is None else new_index
        if target_index < 0 or target_index >= len(pad.cells):
            raise StorageError(INVALID_INDEX, f"Cell index {target_index} out of range")

        self._enforce_cell_size(cell)
        existing_cell = pad.cells[current_index]
        cell.cell_id = existing_cell.cell_id
        pad.cells[current_index] = cell

        if target_index != current_index:
            moving = pad.cells.pop(current_index)
            insert_position = target_index
            if insert_position > len(pad.cells):
                insert_position = len(pad.cells)
            pad.cells.insert(insert_position, moving)

        for idx, candidate in enumerate(pad.cells):
            candidate.index = idx

        self._write_pad(pad, row)
        return pad

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_table(self):
        table_names = set(self._db.table_names())
        if _SCRATCHPAD_TABLE_NAME in table_names:
            table = self._db.open_table(_SCRATCHPAD_TABLE_NAME)
            missing = [field.name for field in _SCRATCHPAD_SCHEMA if field.name not in table.schema.names]
            if missing:
                raise StorageError(CONFIG_ERROR, "Existing LanceDB table missing required columns", details={"missing": missing})
            return table
        return self._db.create_table(_SCRATCHPAD_TABLE_NAME, schema=_SCRATCHPAD_SCHEMA)

    def _ensure_namespaces_table(self):
        table_names = set(self._db.table_names())
        if _NAMESPACES_TABLE_NAME in table_names:
            table = self._db.open_table(_NAMESPACES_TABLE_NAME)
            missing = [field.name for field in _NAMESPACES_SCHEMA if field.name not in table.schema.names]
            if missing:
                raise StorageError(
                    CONFIG_ERROR,
                    "Existing namespaces table missing required columns",
                    details={"missing": missing},
                )
            return table
        return self._db.create_table(_NAMESPACES_TABLE_NAME, schema=_NAMESPACES_SCHEMA)

    def _ensure_embedding_table(self, dimension: int | None = None):
        if self._embeddings_table is not None:
            table = self._embeddings_table
            embedding_field = table.schema.field("embedding")
            list_type = embedding_field.type
            existing_dim = getattr(list_type, "list_size", None)
            if existing_dim is None:
                raise StorageError(CONFIG_ERROR, "Embedding column is not fixed-size list")
            if dimension is not None and existing_dim != dimension:
                raise StorageError(
                    CONFIG_ERROR,
                    "Embedding dimension mismatch",
                    details={"expected": existing_dim, "provided": dimension},
                )
            self._embedding_dimension = existing_dim
            return table

        table_names = set(self._db.table_names())
        if _EMBEDDINGS_TABLE_NAME in table_names:
            table = self._db.open_table(_EMBEDDINGS_TABLE_NAME)
            try:
                embedding_field = table.schema.field("embedding")
            except KeyError as exc:
                raise StorageError(CONFIG_ERROR, "Embeddings table missing vector column") from exc
            list_type = embedding_field.type
            existing_dim = getattr(list_type, "list_size", None)
            if existing_dim is None:
                raise StorageError(CONFIG_ERROR, "Embedding column must declare fixed dimension")
            if dimension is not None and existing_dim != dimension:
                raise StorageError(
                    CONFIG_ERROR,
                    "Embedding dimension mismatch",
                    details={"expected": existing_dim, "provided": dimension},
                )
            self._embeddings_table = table
            self._embedding_dimension = existing_dim
            return table

        if dimension is None:
            raise StorageError(CONFIG_ERROR, "Embeddings table not initialised and dimension not provided")
        schema = _build_embedding_schema(dimension)
        table = self._db.create_table(_EMBEDDINGS_TABLE_NAME, schema=schema)
        self._embeddings_table = table
        self._embedding_dimension = dimension
        return table

    def _write_pad(
        self,
        pad: models.Scratchpad,
        existing_row: dict[str, Any] | None = None,
        *,
        touch_access: bool = True,
    ) -> None:
        if existing_row is None:
            existing_row = self._fetch_row(pad.scratch_id)
        created_at = existing_row.get("created_at") if existing_row else None
        if touch_access:
            last_access_at = _now()
        else:
            last_access_at = _coerce_timestamp(
                (existing_row or {}).get("last_access_at"),
                default=_now(),
            )
        record = self._serialize_pad(pad, created_at, last_access_at=last_access_at)
        self._delete_row(pad.scratch_id)
        self._table.add([record])
        namespace_value = record.get("namespace")
        if namespace_value:
            try:
                self.register_namespace(str(namespace_value))
            except ScratchNotebookError:
                # Registration failures should not prevent write; log for diagnostics.
                logger.warning("Failed to register namespace '%s'", namespace_value, exc_info=True)

    def _touch_last_access(self, row: Mapping[str, Any]) -> dict[str, Any]:
        scratch_id = row.get("scratch_id")
        if not scratch_id:
            return dict(row)
        updated = dict(row)
        updated["last_access_at"] = _now()
        self._delete_row(str(scratch_id))
        self._table.add([updated])
        return updated

    @synchronized
    def capture_snapshot(self, scratch_id: str) -> ScratchpadSnapshot | None:
        row = self._fetch_row(scratch_id)
        if row is None:
            return None
        embeddings = self._capture_embeddings_rows(scratch_id)
        return ScratchpadSnapshot(row=copy.deepcopy(row), embeddings=copy.deepcopy(embeddings))

    @synchronized
    def restore_snapshot(self, snapshot: ScratchpadSnapshot) -> None:
        scratch_id = snapshot.row.get("scratch_id")
        if scratch_id is None:
            raise StorageError(CONFIG_ERROR, "Snapshot missing scratch_id")
        self._delete_row(scratch_id)
        self._table.add([snapshot.row])
        self._restore_embeddings_rows(scratch_id, snapshot.embeddings)

    @synchronized
    def replace_embeddings(
        self,
        scratch_id: str,
        records: Sequence[Mapping[str, Any]],
        *,
        dimension: int,
    ) -> None:
        if not records:
            table = self._ensure_embedding_table(dimension)
            table.delete(where=_format_filter("scratch_id", scratch_id))
            return

        table = self._ensure_embedding_table(dimension)
        table.delete(where=_format_filter("scratch_id", scratch_id))

        normalized: list[dict[str, Any]] = []
        timestamp = _now()
        for record in records:
            vector = [float(x) for x in record.get("embedding", [])]
            if len(vector) != dimension:
                raise StorageError(
                    CONFIG_ERROR,
                    "Embedding dimension mismatch",
                    details={"expected": dimension, "provided": len(vector)},
                )
            normalized.append(
                {
                    "scratch_id": scratch_id,
                    "cell_id": record.get("cell_id"),
                    "tenant_id": self._tenant_id,
                    "namespace": record.get("namespace"),
                    "tags": list(record.get("tags") or []),
                    "title": record.get("title"),
                    "description": record.get("description"),
                    "summary": record.get("summary"),
                    "snippet": record.get("snippet"),
                    "cell_index": record.get("cell_index", -1),
                    "embedding": vector,
                    "updated_at": timestamp,
                }
            )
        if normalized:
            table.add(normalized)

    @synchronized
    def search_embeddings(
        self,
        query_vector: Sequence[float],
        *,
        limit: int,
        namespaces: set[str] | None = None,
        tags: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self._embeddings_table is None and _EMBEDDINGS_TABLE_NAME not in set(self._db.table_names()):
            return []
        dimension = len(query_vector)
        table = self._ensure_embedding_table(dimension)
        fetch_count = max(limit * 3, limit)
        query = table.search(list(query_vector), vector_column_name="embedding").metric("cosine").limit(fetch_count)
        hits = query.to_list()
        if not namespaces and not tags:
            return hits[:limit]

        filtered: list[dict[str, Any]] = []
        namespace_filter = namespaces or set()
        tag_filter = tags or set()
        for row in hits:
            if namespaces:
                namespace_value = row.get("namespace") or ""
                if namespace_value not in namespace_filter:
                    continue
            if tags:
                row_tags = set(row.get("tags") or [])
                if not row_tags.intersection(tag_filter):
                    continue
            filtered.append(row)
            if len(filtered) >= limit:
                break
        return filtered

    def _capture_embeddings_rows(self, scratch_id: str) -> list[dict[str, Any]]:
        if self._embeddings_table is None and _EMBEDDINGS_TABLE_NAME not in set(self._db.table_names()):
            return []
        table = self._ensure_embedding_table()
        arrow_table = table.to_arrow()
        rows: list[dict[str, Any]] = []
        for row in arrow_table.to_pylist():
            if row.get("scratch_id") == scratch_id:
                rows.append(row)
        return rows

    def _restore_embeddings_rows(self, scratch_id: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            if self._embeddings_table is not None or _EMBEDDINGS_TABLE_NAME in set(self._db.table_names()):
                table = self._ensure_embedding_table()
                table.delete(where=_format_filter("scratch_id", scratch_id))
            return
        sample = rows[0]
        embedding = sample.get("embedding") or []
        dimension = len(embedding)
        table = self._ensure_embedding_table(dimension)
        table.delete(where=_format_filter("scratch_id", scratch_id))
        table.add(list(rows))

    @synchronized
    def get_embedding_dimension(self) -> int | None:
        if self._embedding_dimension is not None:
            return self._embedding_dimension
        if _EMBEDDINGS_TABLE_NAME not in set(self._db.table_names()):
            return None
        table = self._ensure_embedding_table()
        embedding_field = table.schema.field("embedding")
        list_type = embedding_field.type
        dimension = getattr(list_type, "list_size", None)
        if dimension is None:
            raise StorageError(CONFIG_ERROR, "Embedding column missing fixed dimension")
        self._embedding_dimension = dimension
        return dimension

    def _serialize_pad(
        self,
        pad: models.Scratchpad,
        created_at: datetime | None,
        last_access_at: datetime | None = None,
    ) -> dict[str, Any]:
        metadata = dict(pad.metadata or {})
        pad_tags = _ensure_string_list(metadata.get("tags"))
        cell_tags = _aggregate_cell_tags(pad.cells)
        aggregated_tags = models.merge_tags(pad_tags, cell_tags)
        if aggregated_tags:
            metadata["tags"] = aggregated_tags
        elif "tags" in metadata:
            metadata.pop("tags")
        if cell_tags:
            metadata["cell_tags"] = cell_tags
        elif "cell_tags" in metadata:
            metadata.pop("cell_tags")
        namespace = metadata.get("namespace")
        title = metadata.get("title") if isinstance(metadata.get("title"), str) else None
        description = metadata.get("description") if isinstance(metadata.get("description"), str) else None
        summary = metadata.get("summary") if isinstance(metadata.get("summary"), str) else None

        cells_payload = [cell.to_dict() for cell in pad.cells]
        schemas_payload = metadata.get("schemas", {})

        access_timestamp = last_access_at or _now()
        record = {
            "scratch_id": pad.scratch_id,
            "tenant_id": self._tenant_id,
            "namespace": str(namespace) if isinstance(namespace, str) else None,
            "title": title,
            "description": description,
            "summary": summary,
            "tags": aggregated_tags,
            "cell_tags": cell_tags,
            "cell_count": len(pad.cells),
            "metadata_json": _encode_json(metadata, context="metadata"),
            "cells_json": _encode_json(cells_payload, context="cells"),
            "schemas_json": _encode_json(schemas_payload, context="schemas"),
            "created_at": (created_at or _now()),
            "updated_at": _now(),
            "last_access_at": access_timestamp,
        }
        return record

    def _pad_from_row(self, row: Mapping[str, Any]) -> models.Scratchpad:
        metadata_json = row.get("metadata_json")
        cells_json = row.get("cells_json")
        metadata = json.loads(metadata_json) if metadata_json else {}
        cells_payload = json.loads(cells_json) if cells_json else []
        cells = [models.ScratchCell.from_dict(item) for item in cells_payload]
        return models.Scratchpad(scratch_id=str(row.get("scratch_id")), cells=cells, metadata=metadata)

    def _fetch_row(self, scratch_id: str) -> dict[str, Any] | None:
        arrow = self._table.to_arrow()
        for row in arrow.to_pylist():
            if row.get("scratch_id") == scratch_id:
                return row
        return None

    def _delete_row(self, scratch_id: str) -> None:
        filter_expr = _format_filter("scratch_id", scratch_id)
        self._table.delete(where=filter_expr)

    def _ensure_valid_identifier(self, scratch_id: str) -> None:
        if not _ID_PATTERN.match(scratch_id):
            raise StorageError(INVALID_ID, "Scratchpad identifier contains invalid characters", details={"scratch_id": scratch_id})

    def _enforce_capacity_limit(self) -> list[str]:
        max_scratchpads = self._config.max_scratchpads
        if not max_scratchpads or max_scratchpads <= 0:
            return []
        count = self._row_count()
        if count < max_scratchpads:
            return []
        policy = self._eviction_policy
        if policy == "fail":
            raise StorageError(CAPACITY_LIMIT_REACHED, "Maximum scratchpad capacity reached")
        if policy not in {"discard", "preempt"}:
            raise StorageError(CONFIG_ERROR, "Unknown eviction policy", details={"policy": policy})
        victims = self._select_eviction_candidates(1)
        if not victims:
            raise StorageError(CAPACITY_LIMIT_REACHED, "Maximum scratchpad capacity reached")
        self._evict_scratchpads(
            victims,
            reason="capacity",
            record_event=True,
            preserve_snapshots=True,
        )
        return victims

    def _row_count(self) -> int:
        if hasattr(self._table, "count_rows"):
            try:
                return int(self._table.count_rows())
            except Exception:  # pragma: no cover - fallback
                pass
        return int(self._table.to_arrow().num_rows)

    def _select_eviction_candidates(self, count: int) -> list[str]:
        arrow_table = self._table.to_arrow()
        rows = arrow_table.to_pylist()
        candidates: list[tuple[datetime, datetime, str]] = []
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        for row in rows:
            scratch_id = row.get("scratch_id")
            if not scratch_id:
                continue
            last_access = row.get("last_access_at") or row.get("updated_at") or row.get("created_at")
            created_at = row.get("created_at") or epoch
            candidates.append(
                (
                    _coerce_timestamp(last_access, default=epoch),
                    _coerce_timestamp(created_at, default=epoch),
                    str(scratch_id),
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1]))
        return [scratch_id for _, _, scratch_id in candidates[:count]]

    def _evict_scratchpads(
        self,
        scratchpad_ids: Sequence[str],
        *,
        reason: str,
        record_event: bool,
        preserve_snapshots: bool,
    ) -> None:
        if not scratchpad_ids:
            return
        for scratch_id in scratchpad_ids:
            if preserve_snapshots:
                snapshot = self.capture_snapshot(scratch_id)
                if snapshot is not None:
                    self._pending_eviction_snapshots.append(snapshot)
            self._delete_row(scratch_id)
            self._restore_embeddings_rows(scratch_id, [])
        if record_event:
            self._last_evicted = list(scratchpad_ids)
        metrics.record_eviction(self._eviction_policy, count=len(scratchpad_ids))
        logger.info(
            "eviction.%s",
            reason,
            extra={
                "policy": self._eviction_policy,
                "tenant_id": self._tenant_id,
                "scratchpad_ids": list(scratchpad_ids),
            },
        )

    @synchronized
    def evict_stale(self, age: timedelta) -> list[str]:
        threshold = _now() - age
        arrow_table = self._table.to_arrow()
        rows = arrow_table.to_pylist()
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        victims: list[str] = []
        for row in rows:
            scratch_id = row.get("scratch_id")
            if not scratch_id:
                continue
            last_access = row.get("last_access_at") or row.get("updated_at") or row.get("created_at")
            access_time = _coerce_timestamp(last_access, default=epoch)
            if access_time <= threshold:
                victims.append(str(scratch_id))
        if victims:
            self._evict_scratchpads(
                victims,
                reason="preempt",
                record_event=False,
                preserve_snapshots=False,
            )
        return victims

    @synchronized
    def pop_recent_evictions(self) -> list[str]:
        evicted = list(self._last_evicted)
        self._last_evicted.clear()
        self._pending_eviction_snapshots.clear()
        return evicted

    @synchronized
    def peek_recent_evictions(self) -> list[str]:
        return list(self._last_evicted)

    @synchronized
    def restore_evicted_snapshots(self) -> None:
        while self._pending_eviction_snapshots:
            snapshot = self._pending_eviction_snapshots.pop()
            try:
                self.restore_snapshot(snapshot)
            except Exception:
                logger.exception("Failed to restore evicted scratchpad '%s'", snapshot.row.get("scratch_id"))
        self._last_evicted.clear()

    @synchronized
    def snapshot_counts(self) -> dict[str, int]:
        """Return current scratchpad and cell counts for Prometheus gauges."""

        arrow = self._table.to_arrow()
        rows = arrow.to_pylist()
        scratchpads = 0
        cells = 0
        tenant = (self._tenant_id or "").strip() or DEFAULT_TENANT_ID
        for row in rows:
            row_tenant = (row.get("tenant_id") or "").strip() or DEFAULT_TENANT_ID
            if row_tenant != tenant:
                continue
            scratchpads += 1
            cells += int(row.get("cell_count") or 0)
        return {"scratchpads": scratchpads, "cells": cells}

    def _enforce_cell_limits(
        self,
        pad: models.Scratchpad,
        pending_cell: models.ScratchCell | None = None,
    ) -> None:
        cells = list(pad.cells)
        if pending_cell is not None:
            self._enforce_cell_size(pending_cell)
            cells.append(pending_cell)

        max_cells = self._config.max_cells_per_pad
        if max_cells and max_cells > 0 and len(cells) > max_cells:
            raise StorageError(
                CAPACITY_LIMIT_REACHED,
                "Maximum cells per scratchpad exceeded",
                details={"limit": max_cells},
            )

        for cell in cells:
            self._enforce_cell_size(cell)

    def _enforce_cell_size(self, cell: models.ScratchCell) -> None:
        max_bytes = self._config.max_cell_bytes
        if max_bytes and max_bytes > 0:
            content_bytes = cell.content.encode("utf-8")
            if len(content_bytes) > max_bytes:
                raise StorageError(
                    CAPACITY_LIMIT_REACHED,
                    "Cell content exceeds configured byte limit",
                    details={"limit": max_bytes, "size": len(content_bytes)},
                )
