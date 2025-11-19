"""Validation helpers for scratch notebook cells."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable, Mapping
from typing import Any, Callable, Sequence, TypeVar

from .errors import INTERNAL_ERROR
from .logging import get_logger
from .models import ScratchCell, ValidationResult, normalize_schema_registry_entries

__all__ = [
    "NOT_VALIDATED_MESSAGE",
    "JSON_SCHEMA_SKIPPED_MESSAGE",
    "MARKDOWN_SKIPPED_MESSAGE",
    "SYNTAX_CHECK_SKIPPED_MESSAGE",
    "run_validation_task",
    "validate_cell",
    "validate_cell_async",
    "validate_cells",
]

T = TypeVar("T")

logger = get_logger(__name__)

NOT_VALIDATED_MESSAGE = "Validation not performed"
JSON_SCHEMA_SKIPPED_MESSAGE = "JSON Schema validation skipped because jsonschema is unavailable"
JSON_SCHEMA_REFERENCE_SKIPPED_MESSAGE = "JSON Schema references skipped because referencing library is unavailable"
YAML_VALIDATION_SKIPPED_MESSAGE = "YAML validation skipped because PyYAML is unavailable"
MARKDOWN_SKIPPED_MESSAGE = "Markdown analysis not available"
SYNTAX_CHECK_SKIPPED_MESSAGE = "Syntax checker not available for this language"
SCHEMA_REF_PREFIX = "scratchpad://schemas/"

# Every language that should be validated via the syntax-checker backend.
CODE_LANGUAGES: set[str] = {
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

try:  # pragma: no cover - import availability depends on environment
    import jsonschema  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    jsonschema = None  # type: ignore[assignment]

try:  # pragma: no cover
    from referencing import Registry, Resource  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    Registry = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]

try:  # pragma: no cover
    from referencing.jsonschema import DRAFT202012  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    DRAFT202012 = None  # type: ignore[assignment]

try:  # pragma: no cover
    import yaml  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

try:  # pragma: no cover
    import markdown_analysis  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    markdown_analysis = None  # type: ignore[assignment]

try:  # pragma: no cover
    import syntax_checker  # type: ignore[assignment]
except ImportError:  # pragma: no cover
    syntax_checker = None  # type: ignore[assignment]

_syntax_checker_missing_logged = False
_markdown_missing_logged = False
_yaml_missing_logged = False
_jsonschema_missing_logged = False
_referencing_missing_logged = False


async def run_validation_task(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute a potentially blocking validation helper in a thread pool."""

    return await asyncio.to_thread(func, *args, **kwargs)


def validate_cell(
    cell: ScratchCell,
    *,
    schemas: Mapping[str, Any] | None = None,
) -> ValidationResult:
    """Synchronously validate a single scratch cell."""

    normalized_registry = _normalize_schema_registry(schemas)
    schema_store = _build_schema_store(normalized_registry)

    language = cell.language.lower()
    if language == "json":
        return _validate_json(cell, normalized_registry, schema_store)
    if language in {"yaml", "yml"}:
        return _validate_yaml(cell, normalized_registry, schema_store)
    if language == "md":
        return _validate_markdown(cell)
    if language == "txt":
        return _validate_plain_text(cell)
    if language in CODE_LANGUAGES:
        return _validate_code(cell)
    return _not_validated(cell, NOT_VALIDATED_MESSAGE, code="VALIDATION_SKIPPED")


async def validate_cell_async(
    cell: ScratchCell,
    *,
    schemas: Mapping[str, Any] | None = None,
) -> ValidationResult:
    """Asynchronously validate a cell by offloading to a worker thread."""

    return await run_validation_task(validate_cell, cell, schemas=schemas)


async def validate_cells(
    cells: Sequence[ScratchCell],
    *,
    timeout: float | None = None,
    schemas: Mapping[str, Any] | None = None,
) -> list[ValidationResult]:
    """Validate a sequence of cells, honouring an optional timeout."""

    async def _execute() -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for cell in cells:
            results.append(await validate_cell_async(cell, schemas=schemas))
        return results

    if timeout is None or timeout <= 0:
        return await _execute()
    return await asyncio.wait_for(_execute(), timeout=timeout)


def _validate_json(
    cell: ScratchCell,
    schema_registry: Mapping[str, Mapping[str, Any]],
    schema_store: Mapping[str, Mapping[str, Any]],
) -> ValidationResult:
    result = ValidationResult(cell_index=cell.index, language=cell.language, cell_id=cell.cell_id)
    try:
        parsed = json.loads(cell.content)
    except json.JSONDecodeError as exc:
        result.add_error(
            f"Invalid JSON: {exc.msg}",
            details={"line": exc.lineno, "column": exc.colno},
        )
        return result

    if cell.json_schema is None:
        return result

    if jsonschema is None:
        global _jsonschema_missing_logged
        if not _jsonschema_missing_logged:
            logger.warning("jsonschema library unavailable; JSON schema validation disabled")
            _jsonschema_missing_logged = True
        result.add_warning(JSON_SCHEMA_SKIPPED_MESSAGE, code="VALIDATION_SKIPPED")
        result.details["schema_applied"] = False
        return result

    schema, schema_ref = _coerce_json_schema(cell.json_schema, result, registry=schema_registry)
    if schema is None:
        return result

    _validate_with_jsonschema(parsed, schema, result, schema_store, schema_ref)
    return result


def _validate_yaml(
    cell: ScratchCell,
    schema_registry: Mapping[str, Mapping[str, Any]],
    schema_store: Mapping[str, Mapping[str, Any]],
) -> ValidationResult:
    result = ValidationResult(cell_index=cell.index, language=cell.language, cell_id=cell.cell_id)
    if yaml is None:
        global _yaml_missing_logged
        if not _yaml_missing_logged:
            logger.warning("PyYAML unavailable; YAML validation disabled")
            _yaml_missing_logged = True
        result.add_warning(YAML_VALIDATION_SKIPPED_MESSAGE, code="VALIDATION_SKIPPED")
        return result

    try:
        parsed = yaml.safe_load(cell.content)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - specific error classes vary
        result.add_error(f"Invalid YAML: {exc}")
        return result

    if cell.json_schema is None or parsed is None:
        return result

    if jsonschema is None:
        global _jsonschema_missing_logged
        if not _jsonschema_missing_logged:
            logger.warning("jsonschema library unavailable; JSON schema validation disabled")
            _jsonschema_missing_logged = True
        result.add_warning(JSON_SCHEMA_SKIPPED_MESSAGE, code="VALIDATION_SKIPPED")
        return result

    schema, schema_ref = _coerce_json_schema(cell.json_schema, result, registry=schema_registry)
    if schema is None:
        return result

    _validate_with_jsonschema(parsed, schema, result, schema_store, schema_ref)
    return result


def _validate_markdown(cell: ScratchCell) -> ValidationResult:
    result = ValidationResult(cell_index=cell.index, language=cell.language, cell_id=cell.cell_id)
    analyzer = getattr(markdown_analysis, "analyze", None)
    if analyzer is None:
        global _markdown_missing_logged
        if not _markdown_missing_logged:
            logger.warning("markdown-analysis unavailable; markdown diagnostics disabled")
            _markdown_missing_logged = True
        result.add_warning(MARKDOWN_SKIPPED_MESSAGE, code="VALIDATION_SKIPPED")
        return result

    try:
        analysis = analyzer(cell.content)  # type: ignore[operator]
    except Exception as exc:  # pragma: no cover - dependency specific
        result.add_warning(f"Markdown analysis failed: {exc}")
        result.details["analysis_error"] = str(exc)
        return result

    issues = _extract_analysis_messages(analysis)
    for warning in issues.get("warnings", []):
        result.add_warning(warning)
    for error in issues.get("errors", []):
        result.add_error(error)
    return result


def _validate_plain_text(cell: ScratchCell) -> ValidationResult:
    result = ValidationResult(cell_index=cell.index, language=cell.language, cell_id=cell.cell_id)
    result.add_warning(NOT_VALIDATED_MESSAGE, code="VALIDATION_SKIPPED")
    result.details["reason"] = "Plain text does not require validation"
    return result


def _validate_code(cell: ScratchCell) -> ValidationResult:
    result = ValidationResult(cell_index=cell.index, language=cell.language, cell_id=cell.cell_id)
    checker = _resolve_syntax_checker()
    if checker is None:
        global _syntax_checker_missing_logged
        if not _syntax_checker_missing_logged:
            logger.warning("syntax-checker unavailable; code validation disabled")
            _syntax_checker_missing_logged = True
        result.add_warning(SYNTAX_CHECK_SKIPPED_MESSAGE, code="VALIDATION_SKIPPED")
        result.details["reason"] = SYNTAX_CHECK_SKIPPED_MESSAGE
        return result

    try:
        outcome = checker(language=cell.language.lower(), code=cell.content)
    except Exception as exc:  # pragma: no cover - dependency specific
        result.add_warning(f"Syntax checker failed: {exc}")
        result.details["syntax_error"] = str(exc)
        return result

    _apply_syntax_checker_outcome(outcome, result)
    return result


def _not_validated(cell: ScratchCell, message: str, *, code: str | None = None) -> ValidationResult:
    result = ValidationResult(cell_index=cell.index, language=cell.language, cell_id=cell.cell_id)
    result.add_warning(message, code=code)
    result.details.setdefault("reason", message)
    return result


def _extract_analysis_messages(result: Any) -> dict[str, list[str]]:
    messages: dict[str, list[str]] = {"warnings": [], "errors": []}
    if result is None:
        return messages

    warnings = getattr(result, "warnings", None) or getattr(result, "messages", None)
    errors = getattr(result, "errors", None)

    if isinstance(warnings, Iterable) and not isinstance(warnings, (str, bytes)):
        messages["warnings"] = [str(item) for item in warnings]
    if isinstance(errors, Iterable) and not isinstance(errors, (str, bytes)):
        messages["errors"] = [str(item) for item in errors]
    return messages


def _resolve_syntax_checker() -> Callable[..., Any] | None:
    if syntax_checker is None:
        return None
    if hasattr(syntax_checker, "check"):
        return getattr(syntax_checker, "check")
    if hasattr(syntax_checker, "check_code"):
        return getattr(syntax_checker, "check_code")
    return None


def _apply_syntax_checker_outcome(outcome: Any, result: ValidationResult) -> None:
    if outcome is None:
        return
    errors = getattr(outcome, "errors", None)
    warnings = getattr(outcome, "warnings", None)
    if isinstance(errors, Iterable) and not isinstance(errors, (str, bytes)):
        for error in errors:
            result.add_error(str(error))
    if isinstance(warnings, Iterable) and not isinstance(warnings, (str, bytes)):
        for warning in warnings:
            result.add_warning(str(warning))


def _normalize_schema_registry(schemas: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if schemas is None:
        return {}

    registry_entries = normalize_schema_registry_entries(schemas)
    normalized: dict[str, Mapping[str, Any]] = {}
    for name, entry in registry_entries.items():
        schema = entry.get("schema")
        if isinstance(schema, Mapping):
            normalized[name] = dict(schema)
        else:
            logger.warning("Shared schema '%s' is missing a schema object; ignoring entry", name)
    return normalized


def _build_schema_store(registry: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if not registry:
        return {}
    return {f"{SCHEMA_REF_PREFIX}{name}": schema for name, schema in registry.items()}


def _coerce_json_schema(
    schema: Any,
    result: ValidationResult,
    *,
    registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[Mapping[str, Any] | None, str | None]:
    return _coerce_json_schema_with_registry(schema, result, registry=registry)


def _coerce_json_schema_with_registry(
    schema: Any,
    result: ValidationResult,
    *,
    registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[Mapping[str, Any] | None, str | None]:
    if schema is None:
        return None, None

    schema_ref: str | None = None
    if isinstance(schema, Mapping):
        mapping = dict(schema)
        schema_ref = _extract_direct_schema_ref(mapping)
    elif isinstance(schema, str):
        if schema.startswith(SCHEMA_REF_PREFIX):
            mapping = {"$ref": schema}
            schema_ref = schema[len(SCHEMA_REF_PREFIX) :]
        else:
            try:
                loaded = json.loads(schema)
            except json.JSONDecodeError as exc:
                result.add_error(
                    f"Invalid JSON schema string: {exc.msg}",
                    details={"line": exc.lineno, "column": exc.colno},
                )
                return None, None
            if isinstance(loaded, Mapping):
                mapping = dict(loaded)
                schema_ref = _extract_direct_schema_ref(mapping)
            else:
                result.add_error("JSON schema string must decode to an object")
                return None, None
    else:
        result.add_error("JSON schema must be a mapping or JSON string")
        return None, None

    if schema_ref and (registry is None or schema_ref not in registry):
        result.add_warning(
            f"JSON schema reference '{schema_ref}' not found in scratchpad metadata",
            code="SCHEMA_REFERENCE_MISSING",
        )
        result.details["schema_ref"] = schema_ref
        return None, schema_ref

    return mapping, schema_ref


def _extract_direct_schema_ref(mapping: Mapping[str, Any]) -> str | None:
    ref = mapping.get("$ref")
    if isinstance(ref, str) and ref.startswith(SCHEMA_REF_PREFIX):
        return ref[len(SCHEMA_REF_PREFIX) :]
    return None


def _make_referencing_registry(schema_store: Mapping[str, Mapping[str, Any]]) -> Registry | None:
    if not schema_store:
        return None
    if Registry is None or Resource is None:  # pragma: no cover - guarded by dependency
        global _referencing_missing_logged
        if not _referencing_missing_logged:
            logger.warning("referencing library unavailable; JSON schema references will be skipped")
            _referencing_missing_logged = True
        return None

    registry = Registry()
    for uri, contents in schema_store.items():
        if DRAFT202012 is not None:  # pragma: no cover - dependency provided
            resource = DRAFT202012.create_resource(contents)
        else:
            materialized = dict(contents)
            materialized.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
            resource = Resource.from_contents(materialized)
        registry = registry.with_resource(uri, resource)
    return registry


def _validate_with_jsonschema(
    instance: Any,
    schema: Mapping[str, Any],
    result: ValidationResult,
    schema_store: Mapping[str, Mapping[str, Any]],
    schema_ref: str | None,
) -> None:
    if jsonschema is None:  # pragma: no cover - guarded upstream
        result.add_warning(JSON_SCHEMA_SKIPPED_MESSAGE, code="VALIDATION_SKIPPED")
        return

    try:
        validator_cls = jsonschema.validators.validator_for(schema)  # type: ignore[union-attr]
        validator_cls.check_schema(schema)  # type: ignore[union-attr]
        registry = _make_referencing_registry(schema_store)
        if schema_store and registry is None:
            result.add_warning(JSON_SCHEMA_REFERENCE_SKIPPED_MESSAGE, code="VALIDATION_SKIPPED")
            return

        validator = (
            validator_cls(schema, registry=registry)  # type: ignore[union-attr]
            if registry is not None
            else validator_cls(schema)  # type: ignore[union-attr]
        )
        validator.validate(instance)
        result.details["schema_applied"] = True
        if schema_ref:
            result.details["schema_ref"] = schema_ref
    except jsonschema.ValidationError as exc:  # type: ignore[union-attr]
        result.add_error(
            f"JSON schema validation failed: {exc.message}",
            details={"path": list(exc.path)},
        )
        if schema_ref:
            result.details["schema_ref"] = schema_ref
    except jsonschema.SchemaError as exc:  # type: ignore[union-attr]
        result.add_error(f"Invalid JSON schema: {exc.message}")
    except Exception as exc:  # pragma: no cover - referencing specific errors
        if _handle_referencing_error(exc, result, schema_ref):
            return
        raise


def _handle_referencing_error(exc: Exception, result: ValidationResult, schema_ref: str | None) -> bool:
    try:
        from referencing.exceptions import Unresolvable  # type: ignore[assignment]
    except ImportError:  # pragma: no cover - dependency missing
        Unresolvable = None  # type: ignore[assignment]

    if Unresolvable is not None and isinstance(exc, Unresolvable):
        reference = getattr(exc, "target", None) or getattr(exc, "message", None) or str(exc)
        display_ref = reference
        if isinstance(reference, str) and reference.startswith(SCHEMA_REF_PREFIX):
            display_ref = reference[len(SCHEMA_REF_PREFIX) :]
        result.add_error(
            f"JSON schema reference '{display_ref}' could not be resolved",
            details={"reference": reference},
        )
        if schema_ref:
            result.details["schema_ref"] = schema_ref
        return True
    return False
