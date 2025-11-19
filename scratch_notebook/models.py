"""Domain models for scratchpads, cells, and validation results."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

_SUPPORTED_LANGUAGES = {
    "json",
    "yaml",
    "yml",
    "md",
    "txt",
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "rs",
    "c",
    "h",
    "cpp",
    "hpp",
    "sh",
    "css",
    "html",
    "htm",
    "java",
    "go",
    "rb",
    "toml",
    "php",
    "cs",
}

logger = logging.getLogger(__name__)

CANONICAL_METADATA_FIELDS: tuple[str, ...] = ("title", "description", "summary")


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        candidate = value.strip() if isinstance(value, str) else value.decode("utf-8", "ignore")
        return [candidate] if candidate else []
    if isinstance(value, Sequence):
        collected: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                candidate = item.strip()
            else:
                candidate = str(item)
            if candidate:
                collected.append(candidate)
        return _dedupe_preserve_order(collected)
    candidate = str(value).strip()
    return [candidate] if candidate else []


def merge_tags(*tag_sets: Iterable[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for tag_set in tag_sets:
        for tag in tag_set:
            if tag not in seen:
                seen.add(tag)
                merged.append(tag)
    return merged


def collect_cell_tags(cells: Iterable["ScratchCell"]) -> list[str]:
    collected: list[str] = []
    for cell in cells:
        collected.extend(normalize_tags(cell.metadata.get("tags")))
    return merge_tags(collected)


def _normalize_cell_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    normalized = dict(metadata)
    tags = normalize_tags(normalized.get("tags"))
    if tags:
        normalized["tags"] = tags
    elif "tags" in normalized:
        normalized.pop("tags")
    return normalized


def _validate_language(language: str) -> None:
    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language '{language}'")


@dataclass(slots=True)
class ScratchCell:
    """Representation of a single cell within a scratchpad."""

    cell_id: str
    index: int
    language: str
    content: str
    validate: bool = False
    json_schema: Mapping[str, Any] | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:  # pragma: no cover - trivial checks
        _validate_language(self.language)
        self.metadata = _normalize_cell_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "cell_id": self.cell_id,
            "index": self.index,
            "language": self.language,
            "content": self.content,
            "validate": self.validate,
        }
        if self.json_schema is not None:
            payload["json_schema"] = self.json_schema
        tags = self.metadata.get("tags")
        if tags:
            payload["tags"] = list(tags)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScratchCell":
        metadata = _normalize_cell_metadata(payload.get("metadata"))
        payload_tags = normalize_tags(payload.get("tags"))
        if payload_tags:
            existing_tags = metadata.get("tags", [])
            metadata["tags"] = merge_tags(existing_tags, payload_tags)
        return cls(
            cell_id=str(payload["cell_id"]),
            index=int(payload["index"]),
            language=str(payload["language"]),
            content=str(payload["content"]),
            validate=bool(payload.get("validate", False)),
            json_schema=payload.get("json_schema"),
            metadata=metadata,
        )


@dataclass(slots=True)
class Scratchpad:
    """Logical scratchpad identified by a UUID."""

    scratch_id: str
    cells: list[ScratchCell] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = _normalize_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scratch_id": self.scratch_id,
            "cells": [cell.to_dict() for cell in self.cells],
        }
        metadata = _normalize_metadata(self.metadata)
        self.metadata = metadata
        scratchpad_tags = normalize_tags(metadata.get("tags"))
        cell_tags = collect_cell_tags(self.cells)
        aggregated_tags = merge_tags(scratchpad_tags, cell_tags)
        if aggregated_tags:
            metadata["tags"] = aggregated_tags
            payload["tags"] = aggregated_tags
        else:
            metadata.pop("tags", None)
        if cell_tags:
            metadata["cell_tags"] = cell_tags
            payload["cell_tags"] = cell_tags
        else:
            metadata.pop("cell_tags", None)
        namespace = metadata.get("namespace")
        if namespace:
            payload["namespace"] = namespace
        for field in CANONICAL_METADATA_FIELDS:
            value = metadata.get(field)
            if value is not None:
                payload[field] = value
        if metadata:
            payload["metadata"] = metadata
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Scratchpad":
        cells = [ScratchCell.from_dict(item) for item in payload.get("cells", [])]
        _ensure_indexes_monotonic(cells)
        metadata = _normalize_metadata(payload.get("metadata"))
        namespace = payload.get("namespace")
        if namespace is not None:
            namespace_value = str(namespace).strip()
            if namespace_value:
                metadata["namespace"] = namespace_value
        tags = normalize_tags(payload.get("tags"))
        if tags:
            metadata["tags"] = tags
        cell_tags = normalize_tags(payload.get("cell_tags"))
        if cell_tags:
            metadata["cell_tags"] = cell_tags
        for field in CANONICAL_METADATA_FIELDS:
            value = payload.get(field)
            if value is None:
                continue
            trimmed = value.strip() if isinstance(value, str) else str(value).strip()
            if trimmed:
                metadata[field] = trimmed
            elif field in metadata:
                metadata.pop(field, None)
        return cls(
            scratch_id=str(payload["scratch_id"]),
            cells=cells,
            metadata=metadata,
        )

    def add_cell(self, cell: ScratchCell) -> None:
        self.cells.append(cell)
        self.cells.sort(key=lambda c: c.index)


def _ensure_indexes_monotonic(cells: Iterable[ScratchCell]) -> None:
    seen: set[int] = set()
    for cell in cells:
        if cell.index in seen:
            raise ValueError(f"Duplicate cell index {cell.index}")
        seen.add(cell.index)


def _normalize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    normalized = dict(metadata)
    normalized.pop("cell_tags", None)
    schemas = normalized.get("schemas")
    registry = normalize_schema_registry_entries(schemas)
    if registry:
        normalized["schemas"] = registry
    elif "schemas" in normalized:
        normalized.pop("schemas")
    tags = normalize_tags(normalized.get("tags"))
    if tags:
        normalized["tags"] = tags
    elif "tags" in normalized:
        normalized.pop("tags")
    namespace = normalized.get("namespace")
    if namespace is not None:
        namespace_value = str(namespace).strip()
        if namespace_value:
            normalized["namespace"] = namespace_value
        else:
            normalized.pop("namespace", None)
    for field in CANONICAL_METADATA_FIELDS:
        value = normalized.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            trimmed = value.strip()
        else:
            trimmed = str(value).strip()
        if trimmed:
            normalized[field] = trimmed
        else:
            normalized.pop(field, None)
    return normalized


def normalize_schema_registry_entries(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return {}

    registry: dict[str, dict[str, Any]] = {}
    for name, value in raw.items():
        if not isinstance(name, str):
            logger.warning("Skipping shared schema with non-string key: %r", name)
            continue
        entry = _normalize_schema_entry(value)
        if entry is not None:
            canonical = dict(entry)
            canonical["name"] = name
            registry[name] = canonical
    return registry


def _normalize_schema_entry(raw: Any) -> dict[str, Any] | None:
    entry_id: str | None = None
    description = ""
    schema_candidate: Any = raw

    if isinstance(raw, Mapping):
        if "schema" in raw:
            schema_candidate = raw.get("schema")
            entry_id = raw.get("id")
            description = raw.get("description", "")
        else:
            schema_candidate = raw
    elif isinstance(raw, str):
        schema_candidate = raw
    else:
        logger.warning("Shared schema entry must be a mapping or JSON string; skipping %r", raw)
        return None

    schema_object = _coerce_schema_object(schema_candidate)
    if schema_object is None:
        return None

    if not entry_id:
        entry_id = uuid4().hex
    else:
        entry_id = str(entry_id)

    if not isinstance(description, str):
        description = "" if description is None else str(description)

    return {"id": entry_id, "description": description, "schema": schema_object}


def _coerce_schema_object(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Shared schema string is not valid JSON (%s); skipping entry", exc.msg)
            return None
        if isinstance(loaded, Mapping):
            return dict(loaded)
        logger.warning("Shared schema string must decode to an object; skipping entry")
        return None
    logger.warning("Shared schema value must be a mapping or JSON string; skipping entry")
    return None


@dataclass(slots=True)
class ValidationResult:
    """Result of validating a single scratchpad cell."""

    cell_index: int
    language: str
    valid: bool = True
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str, *, code: str | None = None, details: Mapping[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"message": message}
        if code:
            payload["code"] = code
        if details:
            payload["details"] = dict(details)
        self.errors.append(payload)
        self.valid = False

    def add_warning(self, message: str, *, code: str | None = None) -> None:
        payload: dict[str, Any] = {"message": message}
        if code:
            payload["code"] = code
        self.warnings.append(payload)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "cell_index": self.cell_index,
            "language": self.language,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload
