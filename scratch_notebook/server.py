"""FastMCP server entrypoint for the Scratch Notebook MCP service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
from uuid import UUID, uuid4
from typing import Any, Mapping, Sequence, Callable

import threading
import time

from fastmcp import Context, FastMCP
from jsonschema import exceptions as jsonschema_exceptions, validators as jsonschema_validators
from mcp.server.auth.middleware.auth_context import (
    AuthenticatedUser,
    auth_context_var,
)
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from . import metrics, namespaces
from .auth import ScratchTokenAuthProvider
from .config import Config, load_config
from .errors import (
    CONFIG_ERROR,
    INTERNAL_ERROR,
    INVALID_ID,
    INVALID_INDEX,
    NOT_FOUND,
    UNAUTHORIZED,
    VALIDATION_ERROR,
    VALIDATION_TIMEOUT,
    ScratchNotebookError,
)
from .eviction import PreemptiveSweeper
from .logging import configure_logging, get_logger
from .models import (
    ScratchCell,
    Scratchpad,
    ValidationResult,
    normalize_schema_registry_entries,
    normalize_tags,
)
from .search import SearchService
from .storage import DEFAULT_TENANT_ID, Storage, StorageError
from .transports import HttpTransportConfig, run_http, run_stdio
from .validation import validate_cells

LOGGER = get_logger(__name__)
SERVER = FastMCP(name="scratch-notebook")


@dataclass(slots=True)
class AppState:
    config: Config
    storage: Storage
    search: SearchService
    sweeper: PreemptiveSweeper | None = None


APP_STATE: AppState | None = None
_METRICS_ROUTE_NAME = "__scratch_notebook_metrics__"


class ShutdownManager:
    """Track active tool requests so shutdown can drain gracefully."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._active_requests = 0
        self._shutdown_requested = False
        self._deadline: float | None = None
        self._timeout = timedelta(seconds=5)

    def configure(self, timeout: timedelta) -> None:
        """Reset state for a new application lifecycle."""

        if timeout.total_seconds() < 0:
            timeout = timedelta(seconds=0)
        with self._condition:
            self._timeout = timeout
            self._active_requests = 0
            self._shutdown_requested = False
            self._deadline = None

    def try_enter(self) -> Callable[[], None] | None:
        """Attempt to register a new request. Returns release callback or None when shutting down."""

        with self._condition:
            if self._shutdown_requested:
                return None
            self._active_requests += 1

        def release() -> None:
            with self._condition:
                if self._active_requests > 0:
                    self._active_requests -= 1
                    self._condition.notify_all()

        return release

    def request_shutdown(self, timeout: timedelta | None = None) -> None:
        """Signal shutdown and start rejecting new requests."""

        with self._condition:
            if self._shutdown_requested:
                return
            effective_timeout = timeout if timeout is not None else self._timeout
            if effective_timeout.total_seconds() < 0:
                effective_timeout = timedelta(seconds=0)
            self._shutdown_requested = True
            self._deadline = time.monotonic() + effective_timeout.total_seconds()
            self._condition.notify_all()

    def wait_for_drain(self) -> bool:
        """Wait for active requests to finish until the shutdown deadline."""

        with self._condition:
            while self._active_requests > 0:
                deadline = self._deadline
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()
            return True

    @property
    def active_requests(self) -> int:
        with self._condition:
            return self._active_requests


_SHUTDOWN_MANAGER = ShutdownManager()


def _resolve_tenant_from_context(context: Context | None) -> str | None:
    if context is not None:
        principal = getattr(context, "client_id", None)
        if principal:
            return str(principal)
        request_context = getattr(context, "request_context", None)
        if request_context and request_context.meta:
            meta_principal = getattr(request_context.meta, "client_id", None)
            if meta_principal:
                return str(meta_principal)
    try:
        user = auth_context_var.get()
    except LookupError:  # pragma: no cover - defensive
        user = None
    if isinstance(user, AuthenticatedUser):
        return str(user.access_token.client_id)
    return None


def _normalise_metrics_path(path: str) -> str:
    if not path:
        return "/metrics"
    normalised = path if path.startswith("/") else f"/{path}"
    if len(normalised) > 1 and normalised.endswith("/"):
        normalised = normalised.rstrip("/")
    return normalised or "/metrics"


def _remove_metrics_route() -> None:
    routes = getattr(SERVER, "_additional_http_routes", None)
    if not routes:
        return
    routes[:] = [route for route in routes if getattr(route, "name", None) != _METRICS_ROUTE_NAME]


def _register_metrics_route(path: str) -> None:
    cleaned = _normalise_metrics_path(path)
    _remove_metrics_route()

    @SERVER.custom_route(cleaned, methods=["GET"], name=_METRICS_ROUTE_NAME, include_in_schema=False)
    async def metrics_endpoint(_request: Request) -> Response:
        registry = metrics.get_registry_optional()
        if registry is None:
            return PlainTextResponse("metrics unavailable\n", status_code=503)
        try:
            storage = get_storage()
        except ScratchNotebookError as exc:  # pragma: no cover - defensive
            metrics.record_error(exc.code)
            return PlainTextResponse("metrics unavailable\n", status_code=503)
        counts = storage.snapshot_counts()
        snapshot = registry.snapshot()
        body = metrics.format_prometheus(
            snapshot,
            scratchpads_current=counts.get("scratchpads", 0),
            cells_current=counts.get("cells", 0),
        )
        return PlainTextResponse(body, media_type="text/plain; version=0.0.4")


def initialize_app(config: Config) -> None:
    """Initialise application state for tool handlers."""

    global APP_STATE
    _SHUTDOWN_MANAGER.configure(config.shutdown_timeout)
    tenant_id = _resolve_active_tenant(config)
    storage = Storage(config, tenant_id=tenant_id)
    migrated: list[str] = []
    if config.enable_auth:
        if config.auth_tokens:
            migrated = storage.migrate_default_tenant(tenant_id)
            if migrated:
                LOGGER.info(
                    "tenant.migration.completed",
                    extra={
                        "tenant": tenant_id,
                        "scratchpad_count": len(migrated),
                        "scratchpad_ids": migrated,
                    },
                )
        else:
            LOGGER.warning("Auth enabled but no tokens configured; tenant migration skipped")
    storage.set_tenant(tenant_id)
    search = SearchService(storage=storage, config=config)
    sweeper: PreemptiveSweeper | None = None
    if config.eviction_policy.strip().lower() == "preempt":
        sweeper = PreemptiveSweeper(
            storage=storage,
            age=config.preempt_age,
            interval=config.preempt_interval,
        )
        sweeper.start()
    metrics.install_registry(metrics.MetricsRegistry())
    if config.enable_auth and config.auth_tokens:
        SERVER.auth = ScratchTokenAuthProvider(config.auth_tokens)
    else:
        SERVER.auth = None
    if config.enable_metrics:
        _register_metrics_route(config.metrics_path)
    else:
        _remove_metrics_route()
    APP_STATE = AppState(config=config, storage=storage, search=search, sweeper=sweeper)


def shutdown_app() -> None:
    """Stop background services and clear application state."""

    global APP_STATE
    if APP_STATE is None:
        return
    config = APP_STATE.config
    _SHUTDOWN_MANAGER.request_shutdown(config.shutdown_timeout)
    drained = _SHUTDOWN_MANAGER.wait_for_drain()
    if not drained:
        LOGGER.warning(
            "shutdown.timeout",
            extra={
                "context": {
                    "active_requests": _SHUTDOWN_MANAGER.active_requests,
                    "timeout_seconds": config.shutdown_timeout.total_seconds(),
                }
            },
        )
    sweeper = APP_STATE.sweeper
    if sweeper:
        sweeper.stop()
    metrics.install_registry(None)
    _remove_metrics_route()
    SERVER.auth = None
    APP_STATE = None


def get_storage(context: Context | None = None) -> Storage:
    if APP_STATE is None:
        raise ScratchNotebookError(CONFIG_ERROR, "Server is not initialised")
    storage = APP_STATE.storage
    tenant = _resolve_tenant_from_context(context)
    active_default = _resolve_active_tenant(APP_STATE.config)
    if tenant is None:
        tenant = active_default
    storage.set_tenant(tenant)
    return storage


def get_search_service(context: Context | None = None) -> SearchService:
    if APP_STATE is None:
        raise ScratchNotebookError(CONFIG_ERROR, "Server is not initialised")
    # Ensure the storage tenant is aligned before performing search operations.
    get_storage(context)
    return APP_STATE.search


def success(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"ok": True, **payload}


def failure(error: ScratchNotebookError) -> dict[str, Any]:
    metrics.record_error(error.code)
    return {"ok": False, "error": error.to_dict()}


def _shutdown_protected(func):
    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            release = _SHUTDOWN_MANAGER.try_enter()
            if release is None:
                return failure(ScratchNotebookError(CONFIG_ERROR, "Server is shutting down"))
            try:
                return await func(*args, **kwargs)
            finally:
                release()

        return async_wrapper

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        release = _SHUTDOWN_MANAGER.try_enter()
        if release is None:
            raise ScratchNotebookError(CONFIG_ERROR, "Server is shutting down")
        try:
            return func(*args, **kwargs)
        finally:
            release()

    return sync_wrapper


def _storage_error_guard(func):
    """Convert StorageError exceptions into structured failure responses."""

    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except StorageError as exc:
                return _handle_storage_error(exc)

        return async_wrapper

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except StorageError as exc:
            return _handle_storage_error(exc)

    return sync_wrapper


def _handle_storage_error(exc: StorageError) -> dict[str, Any]:
    return failure(exc)


def _resolve_active_tenant(config: Config) -> str:
    if config.enable_auth and config.auth_tokens:
        return next(iter(config.auth_tokens.keys()))
    return DEFAULT_TENANT_ID


def _normalize_schema_id(schema_id: str | None) -> str:
    if schema_id is None:
        return uuid4().hex
    try:
        return UUID(str(schema_id)).hex
    except (ValueError, AttributeError) as exc:
        raise ScratchNotebookError(VALIDATION_ERROR, "Schema id must be a UUID string") from exc


def _coerce_schema_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ScratchNotebookError(VALIDATION_ERROR, "Schema request must be an object")

    schema_value = payload.get("schema")
    if not isinstance(schema_value, Mapping):
        raise ScratchNotebookError(VALIDATION_ERROR, "Schema request must include a JSON object under 'schema'")

    schema_dict = dict(schema_value)
    try:
        validator_cls = jsonschema_validators.validator_for(schema_dict)
        validator_cls.check_schema(schema_dict)
    except jsonschema_exceptions.SchemaError as exc:
        raise ScratchNotebookError(VALIDATION_ERROR, "Invalid JSON schema") from exc

    description_value = payload.get("description")
    if description_value is None:
        description = ""
    elif isinstance(description_value, str):
        description = description_value
    else:
        raise ScratchNotebookError(VALIDATION_ERROR, "Schema description must be a string")

    entry: dict[str, Any] = {
        "schema": schema_dict,
        "description": description,
    }

    name_value = payload.get("name")
    if name_value is not None:
        entry["name"] = str(name_value)

    if payload.get("id") is not None:
        entry["id"] = _normalize_schema_id(payload.get("id"))

    return entry


def _extract_schema_registry(metadata: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(metadata, Mapping):
        return {}
    return normalize_schema_registry_entries(metadata.get("schemas"))


async def _ensure_cell_validation(
    cell: ScratchCell,
    *,
    schemas: Mapping[str, Any] | None = None,
) -> list[ValidationResult]:
    timeout_seconds: float | None = None
    if APP_STATE is not None:
        timeout_seconds = APP_STATE.config.validation_request_timeout.total_seconds()
    try:
        results = await validate_cells([cell], timeout=timeout_seconds, schemas=schemas)
    except asyncio.TimeoutError as exc:
        raise ScratchNotebookError(VALIDATION_TIMEOUT, "Validation timed out") from exc
    for result in results:
        if not result.valid:
            raise ScratchNotebookError(
                VALIDATION_ERROR,
                "Cell validation failed",
                details={
                    "errors": list(result.errors),
                    "warnings": list(result.warnings),
                },
            )
    return results


def generate_unique_scratch_id(storage: Storage, *, prefix: str = "scratch") -> str:
    """Generate a unique scratchpad identifier avoiding collisions."""

    import uuid

    attempts = 0
    while True:
        candidate = uuid.uuid4().hex[:12]
        scratch_id = f"{prefix}-{candidate}" if prefix else candidate
        storage.validate_identifier(scratch_id)
        if not storage.has_scratchpad(scratch_id):
            return scratch_id
        attempts += 1
        if attempts > 10_000:
            raise ScratchNotebookError(INTERNAL_ERROR, "Unable to generate unique scratchpad id")


def _validate_scratch_id(storage: Storage, scratch_id: str) -> None:
    storage.validate_identifier(scratch_id)


def _build_cell(payload: Mapping[str, Any], *, index: int | None = None) -> ScratchCell:
    import uuid

    try:
        language = str(payload["language"])
        content = str(payload["content"])
    except KeyError as exc:  # pragma: no cover - defensive
        raise ScratchNotebookError(INVALID_ID, f"Missing required cell field: {exc.args[0]}") from exc

    cell_id = payload.get("cell_id") or uuid.uuid4().hex
    try:
        metadata = dict(payload.get("metadata", {}))
    except Exception as exc:
        raise ScratchNotebookError(VALIDATION_ERROR, "Cell metadata must be a mapping") from exc

    try:
        return ScratchCell(
            cell_id=str(cell_id),
            index=index or 0,
            language=language,
            content=content,
            validate=bool(payload.get("validate", False)),
            json_schema=payload.get("json_schema"),
            metadata=metadata,
        )
    except ValueError as exc:
        raise ScratchNotebookError(VALIDATION_ERROR, str(exc)) from exc


def _build_response_pad(pad: Scratchpad, *, include_metadata: bool = True) -> dict[str, Any]:
    payload = pad.to_dict()
    if not include_metadata:
        payload.pop("metadata", None)
    return {"scratchpad": payload}


def _ensure_string_list(value: Any) -> list[str]:
    return normalize_tags(value)


def _select_cells_by_indices(pad: Scratchpad, indices: Sequence[int]) -> list[ScratchCell]:
    index_map = {cell.index: cell for cell in pad.cells}
    selected: list[ScratchCell] = []
    for index in indices:
        try:
            selected.append(index_map[index])
        except KeyError as exc:
            raise ScratchNotebookError(INVALID_INDEX, f"Cell index {index} out of range") from exc
    return selected


def _select_cells_by_ids(pad: Scratchpad, cell_ids: Sequence[str]) -> list[ScratchCell]:
    id_map = {cell.cell_id: cell for cell in pad.cells}
    selected: list[ScratchCell] = []
    seen: set[str] = set()
    for raw_id in cell_ids:
        cell_id = str(raw_id)
        cell = id_map.get(cell_id)
        if cell is None:
            raise ScratchNotebookError(NOT_FOUND, f"Cell id {cell_id} not found", details={"cell_id": cell_id})
        if cell_id not in seen:
            seen.add(cell_id)
            selected.append(cell)
    return selected


def _normalize_tag_filter(tags: Sequence[str] | None) -> set[str] | None:
    if tags is None:
        return None
    if isinstance(tags, (str, bytes)):
        raise ScratchNotebookError(VALIDATION_ERROR, "Tags filter must be an array of strings")
    if not isinstance(tags, Sequence):
        raise ScratchNotebookError(VALIDATION_ERROR, "Tags filter must be an array of strings")

    normalized: list[str] = []
    for value in tags:
        if isinstance(value, bytes):
            trimmed = value.decode("utf-8", "ignore").strip()
        elif isinstance(value, str):
            trimmed = value.strip()
        else:
            raise ScratchNotebookError(VALIDATION_ERROR, "Tags filter must contain only strings")
        if not trimmed:
            raise ScratchNotebookError(VALIDATION_ERROR, "Tags filter values must not be empty")
        normalized.append(trimmed)

    if not normalized:
        return None
    return set(normalized)


def _normalize_namespace_filter(namespaces: Sequence[str] | None) -> list[str] | None:
    if namespaces is None:
        return None
    if isinstance(namespaces, (str, bytes)):
        raise ScratchNotebookError(VALIDATION_ERROR, "Namespaces filter must be an array of strings")
    if not isinstance(namespaces, Sequence):
        raise ScratchNotebookError(VALIDATION_ERROR, "Namespaces filter must be an array of strings")

    normalized: list[str] = []
    for value in namespaces:
        if isinstance(value, bytes):
            trimmed = value.decode("utf-8", "ignore").strip()
        elif isinstance(value, str):
            trimmed = value.strip()
        else:
            raise ScratchNotebookError(VALIDATION_ERROR, "Namespaces filter must contain only strings")
        if not trimmed:
            raise ScratchNotebookError(VALIDATION_ERROR, "Namespaces filter values must not be empty")
        normalized.append(trimmed)

    return normalized or None


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    try:
        value = int(limit)
    except (TypeError, ValueError):
        raise ScratchNotebookError(VALIDATION_ERROR, "Limit must be an integer")
    if value < 0:
        raise ScratchNotebookError(VALIDATION_ERROR, "Limit must not be negative")
    return value


def _filter_cells(
    pad: Scratchpad,
    *,
    indices: Sequence[int] | None = None,
    cell_ids: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
) -> list[ScratchCell]:
    selected: list[ScratchCell] = list(pad.cells)

    if indices:
        selected = _select_cells_by_indices(pad, indices)

    if cell_ids:
        cells_by_id = _select_cells_by_ids(pad, cell_ids)
        if indices:
            allowed_ids = {cell.cell_id for cell in selected}
            cells_by_id = [cell for cell in cells_by_id if cell.cell_id in allowed_ids]
        selected = cells_by_id

    tag_filter = _normalize_tag_filter(tags)
    if tag_filter:
        selected = [
            cell
            for cell in selected
            if tag_filter.intersection(_ensure_string_list(cell.metadata.get("tags")))
        ]

    return selected


@_storage_error_guard
async def _scratch_read_impl(
    scratch_id: str,
    indices: Sequence[int] | None = None,
    cell_ids: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
    namespaces: Sequence[str] | None = None,
    include_metadata: bool = True,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    try:
        namespace_filter = _normalize_namespace_filter(namespaces)
    except ScratchNotebookError as exc:
        return failure(exc)

    storage = get_storage(context)
    pad = storage.read_scratchpad(scratch_id)

    if namespace_filter:
        allowed_namespaces = set(namespace_filter)
        pad_namespace = ""
        metadata_namespace = pad.metadata.get("namespace") if isinstance(pad.metadata, Mapping) else None
        if isinstance(metadata_namespace, str):
            pad_namespace = metadata_namespace.strip()
        if pad_namespace not in allowed_namespaces:
            return failure(
                ScratchNotebookError(
                    UNAUTHORIZED,
                    "Scratchpad does not belong to an allowed namespace",
                    details={"scratch_id": scratch_id, "namespace": pad_namespace or None},
                )
            )

    try:
        selected_cells = _filter_cells(pad, indices=indices, cell_ids=cell_ids, tags=tags)
    except ScratchNotebookError as exc:
        return failure(exc)

    filtered_pad = Scratchpad(
        scratch_id=pad.scratch_id,
        cells=list(selected_cells),
        metadata=dict(pad.metadata or {}),
    )

    payload = _build_response_pad(filtered_pad, include_metadata=include_metadata)
    response = success(payload)
    metrics.record_operation("read")
    return response


@_storage_error_guard
@_shutdown_protected
async def _scratch_list_cells_impl(
    scratch_id: str,
    indices: Sequence[int] | None = None,
    cell_ids: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    pad = storage.read_scratchpad(scratch_id)

    try:
        cells = _filter_cells(pad, indices=indices, cell_ids=cell_ids, tags=tags)
    except ScratchNotebookError as exc:
        return failure(exc)

    listings: list[dict[str, Any]] = []
    for cell in cells:
        item = {
            "cell_id": cell.cell_id,
            "index": cell.index,
            "language": cell.language,
        }
        tags = cell.metadata.get("tags")
        if tags:
            item["tags"] = list(tags)
        if cell.metadata:
            item["metadata"] = dict(cell.metadata)
        listings.append(item)

    return success({"scratch_id": scratch_id, "cells": listings})


@_storage_error_guard
@_shutdown_protected
async def _scratch_create_impl(
    scratch_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    search = get_search_service(context)

    try:
        if scratch_id is None:
            scratch_id = generate_unique_scratch_id(storage)
        else:
            _validate_scratch_id(storage, scratch_id)
            if storage.has_scratchpad(scratch_id):
                raise ScratchNotebookError(INVALID_ID, f"Scratchpad {scratch_id} already exists")

        try:
            metadata_payload = dict(metadata or {})
        except Exception as exc:  # pragma: no cover - defensive
            raise ScratchNotebookError(VALIDATION_ERROR, "Metadata must be an object") from exc

        pad = Scratchpad(scratch_id=scratch_id, cells=[], metadata=metadata_payload)
        pad = storage.create_scratchpad(pad, overwrite=False)
        try:
            await search.reindex_pad(pad)
        except ScratchNotebookError as exc:
            storage.delete_scratchpad(scratch_id)
            storage.restore_evicted_snapshots()
            await search.delete_pad_embeddings(scratch_id)
            return failure(exc)
        except Exception as exc:  # pragma: no cover - defensive
            storage.delete_scratchpad(scratch_id)
            storage.restore_evicted_snapshots()
            await search.delete_pad_embeddings(scratch_id)
            LOGGER.exception("Failed to index scratchpad %s", scratch_id, exc_info=exc)
            return failure(ScratchNotebookError(INTERNAL_ERROR, "Semantic index failed"))
        payload = _build_response_pad(pad)
        evicted_ids = storage.pop_recent_evictions()
        if evicted_ids:
            for victim in evicted_ids:
                await search.delete_pad_embeddings(victim)
            payload["evicted_scratchpads"] = evicted_ids
        response = success(payload)
        metrics.record_operation("create")
        return response
    except ScratchNotebookError as exc:
        return failure(exc)


@_storage_error_guard
@_shutdown_protected
async def _scratch_delete_impl(scratch_id: str, *, context: Context | None = None) -> dict[str, Any]:
    storage = get_storage(context)
    search = get_search_service(context)
    deleted = storage.delete_scratchpad(scratch_id)
    if deleted:
        await search.delete_pad_embeddings(scratch_id)
    response = success({"scratch_id": scratch_id, "deleted": deleted})
    metrics.record_operation("delete")
    return response


@_storage_error_guard
@_shutdown_protected
async def _scratch_list_schemas_impl(
    scratch_id: str,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    _validate_scratch_id(storage, scratch_id)
    schemas = storage.list_schemas(scratch_id)
    return success({"scratch_id": scratch_id, "schemas": schemas})


@_storage_error_guard
@_shutdown_protected
async def _scratch_get_schema_impl(
    scratch_id: str,
    schema_id: str,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    try:
        _validate_scratch_id(storage, scratch_id)
        normalized_id = _normalize_schema_id(schema_id)
        entry = storage.get_schema(scratch_id, normalized_id)
        return success({"schema": entry})
    except ScratchNotebookError as exc:
        return failure(exc)


@_storage_error_guard
@_shutdown_protected
async def _scratch_upsert_schema_impl(
    scratch_id: str,
    schema: Mapping[str, Any],
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    try:
        _validate_scratch_id(storage, scratch_id)
        entry = _coerce_schema_request(schema)
        stored = storage.upsert_schema(scratch_id, entry)
        return success({"schema": stored})
    except ScratchNotebookError as exc:
        return failure(exc)


@_shutdown_protected
async def _scratch_list_impl(
    namespaces: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
    limit: int | None = None,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    try:
        namespace_filter = _normalize_namespace_filter(namespaces)
        tag_filter = _normalize_tag_filter(tags)
        limit_value = _normalize_limit(limit)
    except ScratchNotebookError as exc:
        return failure(exc)

    storage = get_storage(context)
    listing = storage.list_scratchpads(
        namespaces=namespace_filter,
        tags=sorted(tag_filter) if tag_filter else None,
        limit=limit_value,
    )
    sanitized = [
        {
            "scratch_id": entry.get("scratch_id"),
            "title": entry.get("title"),
            "description": entry.get("description"),
            "namespace": entry.get("namespace"),
            "cell_count": entry.get("cell_count", 0),
        }
        for entry in listing
    ]
    response = success({"scratchpads": sanitized})
    metrics.record_operation("list")
    return response


@_shutdown_protected
async def _scratch_list_tags_impl(
    namespaces: Sequence[str] | None = None,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    try:
        namespace_filter = _normalize_namespace_filter(namespaces)
    except ScratchNotebookError as exc:
        return failure(exc)

    storage = get_storage(context)
    tags = storage.list_tags(namespaces=namespace_filter)
    return success(tags)


@_storage_error_guard
@_shutdown_protected
async def _scratch_append_cell_impl(
    scratch_id: str,
    cell: Mapping[str, Any],
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    search = get_search_service(context)
    validation_results: list[ValidationResult] = []
    snapshot_state = storage.capture_snapshot(scratch_id)
    try:
        new_cell = _build_cell(cell)
        if new_cell.validate:
            existing_pad = storage.read_scratchpad(scratch_id)
            new_cell.index = len(existing_pad.cells)
            registry = _extract_schema_registry(existing_pad.metadata)
            validation_results = await _ensure_cell_validation(new_cell, schemas=registry)
        pad = storage.append_cell(scratch_id, new_cell)
        try:
            await search.reindex_pad(pad)
        except ScratchNotebookError as exc:
            if snapshot_state:
                storage.restore_snapshot(snapshot_state)
            return failure(exc)
        except Exception as exc:  # pragma: no cover - defensive
            if snapshot_state:
                storage.restore_snapshot(snapshot_state)
            LOGGER.exception("Failed to index scratchpad %s", scratch_id, exc_info=exc)
            return failure(ScratchNotebookError(INTERNAL_ERROR, "Semantic index failed"))
        payload = _build_response_pad(pad)
        if validation_results:
            payload["validation"] = [result.to_dict() for result in validation_results]
        response = success(payload)
        metrics.record_operation("append")
        return response
    except ScratchNotebookError as exc:
        return failure(exc)


@_storage_error_guard
@_shutdown_protected
async def _scratch_replace_cell_impl(
    scratch_id: str,
    index: int,
    cell: Mapping[str, Any],
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    search = get_search_service(context)
    validation_results: list[ValidationResult] = []
    snapshot_state = storage.capture_snapshot(scratch_id)
    try:
        current_pad = storage.read_scratchpad(scratch_id)
        if index < 0 or index >= len(current_pad.cells):
            raise ScratchNotebookError(INVALID_INDEX, f"Cell index {index} out of range")
        existing_cell = current_pad.cells[index]
        metadata_supplied = "metadata" in cell
        new_cell = _build_cell(cell, index=index)
        if not metadata_supplied:
            new_cell.metadata = dict(existing_cell.metadata)
        if new_cell.validate:
            registry = _extract_schema_registry(current_pad.metadata)
            validation_results = await _ensure_cell_validation(new_cell, schemas=registry)
        pad = storage.replace_cell(scratch_id, index, new_cell)
        try:
            await search.reindex_pad(pad)
        except ScratchNotebookError as exc:
            if snapshot_state:
                storage.restore_snapshot(snapshot_state)
            return failure(exc)
        except Exception as exc:  # pragma: no cover - defensive
            if snapshot_state:
                storage.restore_snapshot(snapshot_state)
            LOGGER.exception("Failed to index scratchpad %s", scratch_id, exc_info=exc)
            return failure(ScratchNotebookError(INTERNAL_ERROR, "Semantic index failed"))
        payload = _build_response_pad(pad)
        if validation_results:
            payload["validation"] = [result.to_dict() for result in validation_results]
        response = success(payload)
        metrics.record_operation("replace")
        return response
    except ScratchNotebookError as exc:
        return failure(exc)


@_storage_error_guard
@_shutdown_protected
async def _scratch_validate_impl(
    scratch_id: str,
    indices: list[int] | None = None,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    pad = storage.read_scratchpad(scratch_id)

    if indices:
        try:
            target_cells = _select_cells_by_indices(pad, indices)
        except ScratchNotebookError as exc:
            return failure(exc)
    else:
        target_cells = list(pad.cells)

    timeout_seconds: float | None = None
    if APP_STATE is not None:
        timeout_seconds = APP_STATE.config.validation_request_timeout.total_seconds()

    try:
        registry = _extract_schema_registry(pad.metadata)
        results = await validate_cells(target_cells, timeout=timeout_seconds, schemas=registry)
    except asyncio.TimeoutError:
        return failure(ScratchNotebookError(VALIDATION_TIMEOUT, "Validation timed out"))
    response = success(
        {
            "scratch_id": scratch_id,
            "results": [result.to_dict() for result in results],
        }
    )
    metrics.record_operation("validate")
    return response


@_shutdown_protected
async def _scratch_search_impl(
    query: str,
    namespaces: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
    limit: int | None = None,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    search = get_search_service()
    try:
        effective_limit = limit if isinstance(limit, int) else 10
        response = await search.search(query, namespaces=namespaces, tags=tags, limit=effective_limit)
        return response
    except ScratchNotebookError as exc:
        return failure(exc)


scratch_create = SERVER.tool(
    name="scratch_create",
    description=(
        "Create or reset a scratch notebook.\n\n"
        "Parameters:\n"
        "- scratch_id (optional string): supply to reuse a deterministic identifier; omit to auto-generate.\n"
        "- metadata (object): include canonical fields so downstream tools stay informative:\n"
        "    - title: concise (≤60 characters), action-oriented label (e.g. 'Incident response checklist').\n"
        "    - description: one–two sentences summarising intent for humans choosing a pad.\n"
        "    - summary: optional terse, search-friendly synopsis (key nouns/verbs, minimal filler).\n"
        "    - namespace: string namespace registered via scratch_namespace_* (defaults to tenant namespace).\n"
        "    - tags: array of scratchpad-level tags used by list/search filters.\n"
        "  Additional metadata keys are stored verbatim.\n\n"
        "Namespace conventions:\n"
        "- Call scratch_namespace_list before creating a pad to discover existing project prefixes (e.g. 'proj-omega/').\n"
        "- Reuse an existing prefix verbatim; only create a new namespace when you are sure a new project boundary is needed.\n"
        "- Staying consistent keeps multiple assistants sharing the default tenant from stepping on each other's work."
    ),
)(_scratch_create_impl)

scratch_read = SERVER.tool(
    name="scratch_read",
    description=(
        "Read a scratch notebook by id.\n\n"
        "Filters:\n"
        "- indices: restrict to specific zero-based cell indices.\n"
        "- cell_ids: restrict to explicit cell UUIDs (applied before tag filter).\n"
        "- tags: return only cells whose tag set intersects the provided values.\n"
        "- namespaces: assert the pad belongs to one of the listed namespaces.\n"
        "- include_metadata (default true): set to false when only cell payloads are needed; canonical fields remain in the response."
    ),
)(_scratch_read_impl)

scratch_list_cells = SERVER.tool(
    name="scratch_list_cells",
    description="List cells for a scratch notebook",
)(_scratch_list_cells_impl)

scratch_delete = SERVER.tool(
    name="scratch_delete",
    description="Delete a scratch notebook by id",
)(_scratch_delete_impl)

scratch_list = SERVER.tool(
    name="scratch_list",
    description=(
        "List scratchpads with lean metadata suitable for navigation.\n\n"
        "Each entry returns scratch_id, title, description, namespace, and cell_count. Use scratch_read for full metadata or summaries."
    ),
)(_scratch_list_impl)

scratch_list_tags = SERVER.tool(
    name="scratch_list_tags",
    description=(
        "List scratchpad-level and cell-level tags, optionally filtered by namespace."
    ),
)(_scratch_list_tags_impl)

scratch_append_cell = SERVER.tool(
    name="scratch_append_cell",
    description="Append a cell to the specified scratch notebook",
)(_scratch_append_cell_impl)

scratch_replace_cell = SERVER.tool(
    name="scratch_replace_cell",
    description="Replace a cell in the specified scratch notebook",
)(_scratch_replace_cell_impl)

scratch_validate = SERVER.tool(
    name="scratch_validate",
    description="Validate one or more cells within a scratch notebook",
)(_scratch_validate_impl)

scratch_search = SERVER.tool(
    name="scratch_search",
    description="Perform semantic search across scratchpads and cells",
)(_scratch_search_impl)

scratch_list_schemas = SERVER.tool(
    name="scratch_list_schemas",
    description="List shared schemas attached to a scratch notebook",
)(_scratch_list_schemas_impl)

scratch_get_schema = SERVER.tool(
    name="scratch_get_schema",
    description="Fetch a shared schema definition by id",
)(_scratch_get_schema_impl)

scratch_upsert_schema = SERVER.tool(
    name="scratch_upsert_schema",
    description="Create or update a shared schema definition on a scratch notebook",
)(_scratch_upsert_schema_impl)

_SCRATCH_CREATE_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": ["string", "null"],
            "description": "Canonical short label for the scratchpad.",
            "default": None,
        },
        "description": {
            "type": ["string", "null"],
            "description": "Longer human-readable summary presented in listings.",
            "default": None,
        },
        "summary": {
            "type": ["string", "null"],
            "description": "Optional concise synopsis for semantic search snippets.",
            "default": None,
        },
    },
    "additionalProperties": True,
}

scratch_create.parameters = {
    "type": "object",
    "properties": {
        "scratch_id": dict(scratch_create.parameters["properties"]["scratch_id"]),
        "metadata": {
            "anyOf": [
                _SCRATCH_CREATE_METADATA_SCHEMA,
                {"type": "null"},
            ],
            "default": None,
            "description": "Optional metadata payload including canonical fields.",
        },
    },
    "additionalProperties": True,
}

scratch_list.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "namespaces": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional namespace filter; when provided, results include only matching namespaces.",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional tag filter returning scratchpads whose tags or cell tags include any of the supplied values.",
        },
        "limit": {
            "type": "integer",
            "minimum": 0,
            "description": "Optional result cap; when omitted, all matching scratchpads are returned.",
        },
    },
}

scratch_list_tags.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "namespaces": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional namespace filter limiting results to scratchpads in the provided namespaces.",
        },
    },
}

scratch_list.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "scratchpads": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scratch_id": {"type": "string"},
                    "title": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "namespace": {"type": ["string", "null"]},
                    "cell_count": {"type": "integer", "minimum": 0},
                },
                "required": ["scratch_id", "title", "description", "namespace", "cell_count"],
            },
            "description": "Lean listing of scratchpads for navigation.",
        },
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["scratchpads"]},
            "else": {"required": ["error"]},
        }
    ],
}


@_shutdown_protected
async def _scratch_namespace_list_impl(*, context: Context | None = None) -> dict[str, Any]:
    storage = get_storage(context)
    result = namespaces.list_namespaces(storage)
    return success({"namespaces": result})


@_shutdown_protected
async def _scratch_namespace_create_impl(
    namespace: str,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    try:
        value, created = namespaces.create_namespace(storage, namespace)
    except ScratchNotebookError as exc:
        return failure(exc)
    return success({"namespace": value, "created": created})


@_shutdown_protected
async def _scratch_namespace_rename_impl(
    old_namespace: str,
    new_namespace: str,
    migrate_scratchpads: bool | None = True,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    try:
        value, migrated_count = namespaces.rename_namespace(
            storage,
            old_namespace,
            new_namespace,
            migrate_scratchpads=migrate_scratchpads if migrate_scratchpads is not None else True,
        )
    except ScratchNotebookError as exc:
        return failure(exc)
    return success({"namespace": value, "migrated_count": migrated_count})


@_shutdown_protected
async def _scratch_namespace_delete_impl(
    namespace: str,
    delete_scratchpads: bool | None = False,
    *,
    context: Context | None = None,
) -> dict[str, Any]:
    storage = get_storage(context)
    try:
        deleted, removed = namespaces.delete_namespace(
            storage,
            namespace,
            delete_scratchpads=delete_scratchpads if delete_scratchpads is not None else False,
        )
    except ScratchNotebookError as exc:
        return failure(exc)
    return success({"deleted": deleted, "removed_scratchpads": removed})


scratch_namespace_list = SERVER.tool(
    name="scratch_namespace_list",
    description="List namespaces available to the current tenant.",
)(_scratch_namespace_list_impl)

scratch_namespace_list.parameters = {
    "type": "object",
    "additionalProperties": False,
}

scratch_namespace_list.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "namespaces": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "namespace": {"type": "string"},
                    "scratchpad_count": {"type": "integer", "minimum": 0},
                },
                "required": ["namespace", "scratchpad_count"],
            },
        },
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["namespaces"]},
            "else": {"required": ["error"]},
        }
    ],
}

scratch_namespace_create = SERVER.tool(
    name="scratch_namespace_create",
    description="Register a namespace string for the current tenant.",
)(_scratch_namespace_create_impl)

scratch_namespace_create.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "namespace": {
            "type": "string",
            "minLength": 1,
            "description": "Namespace string to register.",
        },
    },
    "required": ["namespace"],
}

scratch_namespace_create.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "namespace": {"type": "string"},
        "created": {"type": "boolean"},
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["namespace", "created"]},
            "else": {"required": ["error"]},
        }
    ],
}

scratch_namespace_rename = SERVER.tool(
    name="scratch_namespace_rename",
    description="Rename an existing namespace.",
)(_scratch_namespace_rename_impl)

scratch_namespace_rename.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "old_namespace": {
            "type": "string",
            "minLength": 1,
            "description": "Existing namespace to rename.",
        },
        "new_namespace": {
            "type": "string",
            "minLength": 1,
            "description": "New namespace value.",
        },
        "migrate_scratchpads": {
            "type": "boolean",
            "default": True,
            "description": "When true (default), migrate scratchpads referencing the old namespace.",
        },
    },
    "required": ["old_namespace", "new_namespace"],
}

scratch_namespace_rename.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "namespace": {"type": "string"},
        "migrated_count": {"type": "integer", "minimum": 0},
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["namespace", "migrated_count"]},
            "else": {"required": ["error"]},
        }
    ],
}

scratch_namespace_delete = SERVER.tool(
    name="scratch_namespace_delete",
    description="Delete a namespace, optionally cascading to scratchpads.",
)(_scratch_namespace_delete_impl)

scratch_namespace_delete.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "namespace": {
            "type": "string",
            "minLength": 1,
            "description": "Namespace to delete.",
        },
        "delete_scratchpads": {
            "type": "boolean",
            "default": False,
            "description": "When true, delete scratchpads referencing the namespace.",
        },
    },
    "required": ["namespace"],
}

scratch_namespace_delete.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "deleted": {"type": "boolean"},
        "removed_scratchpads": {"type": "integer", "minimum": 0},
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["deleted", "removed_scratchpads"]},
            "else": {"required": ["error"]},
        }
    ],
}
scratch_list_tags.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "scratchpad_tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Deduplicated set of tags declared on scratchpad metadata.",
        },
        "cell_tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Deduplicated set of tags discovered on individual cells.",
        },
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["scratchpad_tags", "cell_tags"]},
            "else": {"required": ["error"]},
        }
    ],
}

scratch_read.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scratch_id": {
            "type": "string",
            "minLength": 1,
            "description": "Identifier of the target scratch notebook.",
        },
        "indices": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0},
            "description": "Optional subset of cell indices to return.",
        },
        "cell_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional subset of cell ids to return.",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional tag filter returning cells whose metadata tags intersect the supplied list.",
        },
        "namespaces": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional namespace constraint that must include the scratchpad namespace.",
        },
        "include_metadata": {
            "type": "boolean",
            "description": "When false, omits metadata from the response.",
            "default": True,
        },
    },
    "required": ["scratch_id"],
}

scratch_search.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "description": "Natural language query to search across scratchpads and cells.",
        },
        "namespaces": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional namespace filter applied before ranking.",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional tag filter applied before ranking.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "description": "Maximum number of hits to return.",
        },
    },
    "required": ["query"],
}

scratch_search.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "hits": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scratch_id": {"type": "string"},
                    "cell_id": {"type": ["string", "null"]},
                    "namespace": {"type": ["string", "null"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "score": {"type": "number"},
                    "snippet": {"type": "string"},
                },
                "required": ["scratch_id", "cell_id", "namespace", "tags", "score", "snippet"],
            },
        },
        "embedder": {"type": "string"},
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["hits", "embedder"]},
            "else": {"required": ["error"]},
        }
    ],
}

_LIST_CELL_ENTRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "cell_id": {"type": "string"},
        "index": {"type": "integer", "minimum": 0},
        "language": {"type": "string"},
        "metadata": {"type": "object"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["cell_id", "index", "language"],
}

_LIST_CELLS_SUCCESS_CONSTRAINT = {
    "if": {"properties": {"ok": {"const": True}}},
    "then": {"required": ["scratch_id", "cells"]},
    "else": {"required": ["error"]},
}

scratch_list_cells.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scratch_id": {
            "type": "string",
            "minLength": 1,
            "description": "Identifier of the scratch notebook whose cells should be listed.",
        },
        "indices": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0},
            "description": "Optional subset of cell indices to include.",
        },
        "cell_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional subset of cell ids to include.",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Optional tag filter returning cells that contain any of the supplied tags.",
        },
    },
    "required": ["scratch_id"],
}

scratch_list_cells.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "scratch_id": {"type": "string"},
        "cells": {"type": "array", "items": _LIST_CELL_ENTRY_SCHEMA},
    },
    "required": ["ok"],
    "allOf": [_LIST_CELLS_SUCCESS_CONSTRAINT],
}

_SCHEMA_ENTRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "description": "Canonical schema UUID."},
        "name": {"type": "string", "description": "Logical schema key used within references."},
        "description": {"type": "string", "description": "Human-readable description of the schema."},
        "schema": {"type": "object", "description": "JSON Schema definition describing the payload."},
    },
    "required": ["id", "name", "description", "schema"],
}

_SCHEMA_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {
            "type": "string",
            "description": "Existing schema UUID when updating; omit for new schemas.",
        },
        "name": {
            "type": "string",
            "description": "Optional logical key for referencing; defaults to the schema id when omitted.",
        },
        "description": {
            "type": "string",
            "description": "Human-readable description for the schema.",
            "default": "",
        },
        "schema": {
            "type": "object",
            "description": "JSON Schema object defining the payload structure.",
        },
    },
    "required": ["schema"],
}

_SCHEMA_SUCCESS_CONSTRAINT = {
    "if": {"properties": {"ok": {"const": True}}},
    "then": {"required": ["schema"]},
    "else": {"required": ["error"]},
}

scratch_list_schemas.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scratch_id": {
            "type": "string",
            "minLength": 1,
            "description": "Identifier of the scratch notebook whose shared schemas should be listed.",
        }
    },
    "required": ["scratch_id"],
}

scratch_list_schemas.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "scratch_id": {"type": "string"},
        "schemas": {"type": "array", "items": _SCHEMA_ENTRY_SCHEMA},
    },
    "required": ["ok"],
    "allOf": [
        {
            "if": {"properties": {"ok": {"const": True}}},
            "then": {"required": ["scratch_id", "schemas"]},
            "else": {"required": ["error"]},
        }
    ],
}

scratch_get_schema.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scratch_id": {
            "type": "string",
            "minLength": 1,
            "description": "Identifier of the scratch notebook containing the schema.",
        },
        "schema_id": {
            "type": "string",
            "minLength": 1,
            "description": "UUID of the schema to fetch.",
        },
    },
    "required": ["scratch_id", "schema_id"],
}

scratch_get_schema.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "schema": _SCHEMA_ENTRY_SCHEMA,
    },
    "required": ["ok"],
    "allOf": [_SCHEMA_SUCCESS_CONSTRAINT],
}


scratch_upsert_schema.parameters = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scratch_id": {
            "type": "string",
            "minLength": 1,
            "description": "Identifier of the scratch notebook where the schema should be stored.",
        },
        "schema": _SCHEMA_INPUT_SCHEMA,
    },
    "required": ["scratch_id", "schema"],
}

scratch_upsert_schema.output_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": ["object", "null"]},
        "schema": _SCHEMA_ENTRY_SCHEMA,
    },
    "required": ["ok"],
    "allOf": [_SCHEMA_SUCCESS_CONSTRAINT],
}


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for running the Scratch Notebook server."""

    configure_logging()
    config = load_config(argv)
    LOGGER.info(
        "Configuration loaded",
        extra={
            "context": {
                "storage_dir": str(config.storage_dir),
                "enable_stdio": config.enable_stdio,
                "enable_http": config.enable_http,
                "enable_sse": config.enable_sse,
                "enable_metrics": config.enable_metrics,
            }
        },
    )

    try:
        initialize_app(config)
    except StorageError as exc:
        LOGGER.error(
            "Failed to initialize storage",
            exc_info=exc,
            extra={"context": exc.details or {}},
        )
        raise SystemExit(1) from exc

    try:
        if config.enable_stdio:
            run_stdio(SERVER)
        else:
            LOGGER.info("Stdio transport disabled")

        if config.enable_http or config.enable_sse or config.enable_metrics:
            http_config = HttpTransportConfig(
                host=config.http_host,
                port=config.http_port,
                http_path=config.http_path,
                sse_path=config.sse_path,
                metrics_path=config.metrics_path,
                enable_metrics=config.enable_metrics,
                enable_http=config.enable_http,
                enable_sse=config.enable_sse,
                socket_path=config.http_socket_path,
            )
            run_http(SERVER, http_config)
        else:
            LOGGER.info("HTTP/SSE transports disabled")
    finally:
        shutdown_app()


if __name__ == "__main__":  # pragma: no cover - manual invocation only
    main()
