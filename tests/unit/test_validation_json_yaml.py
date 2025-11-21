from __future__ import annotations

import json
import uuid

import pytest

from scratch_notebook import models
from scratch_notebook import validation as validation_module
from scratch_notebook.validation import JSON_SCHEMA_SKIPPED_MESSAGE, validate_cell


def _make_cell(language: str, content: str, **kwargs) -> models.ScratchCell:
    return models.ScratchCell(
        cell_id=str(uuid.uuid4()),
        index=0,
        language=language,
        content=content,
        **kwargs,
    )


def test_json_validation_passes_for_well_formed_payload() -> None:
    cell = _make_cell("json", "{\"value\": 1}")

    result = validate_cell(cell)

    assert result.valid is True
    assert result.errors == []


def test_json_validation_reports_syntax_errors() -> None:
    cell = _make_cell("json", "{invalid}")

    result = validate_cell(cell)

    assert result.valid is False
    assert any("Invalid JSON" in error["message"] for error in result.errors)


def test_json_schema_validation_handles_failures() -> None:
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}
    cell = _make_cell("json", "{\"value\": \"oops\"}", json_schema=schema)

    result = validate_cell(cell)

    if result.warnings and any(JSON_SCHEMA_SKIPPED_MESSAGE in warning["message"] for warning in result.warnings):
        pytest.skip("jsonschema not available in runtime")

    assert result.valid is False
    assert any("schema" in error["message"] for error in result.errors)


def test_yaml_validation_reports_parsing_errors() -> None:
    yaml = pytest.importorskip("yaml")

    cell = _make_cell("yaml", "value: [unbalanced")

    result = validate_cell(cell)

    assert result.valid is False
    assert any("Invalid YAML" in error["message"] for error in result.errors)


def test_yaml_schema_validation_respects_json_schema_module() -> None:
    yaml = pytest.importorskip("yaml")
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}}
    content = yaml.safe_dump({"value": "not-int"})

    cell = _make_cell("yaml", content, json_schema=json.dumps(schema))

    result = validate_cell(cell)

    if result.warnings and any(JSON_SCHEMA_SKIPPED_MESSAGE in warning["message"] for warning in result.warnings):
        pytest.skip("jsonschema not available in runtime")

    assert result.valid is False
    assert any("schema" in error["message"] for error in result.errors)


def test_json_schema_reference_resolves_from_metadata() -> None:
    cell = _make_cell(
        "json",
        "{\"value\": 4}",
        json_schema={"$ref": "scratchpad://schemas/payload"},
    )
    schemas = {
        "payload": {
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
        }
    }

    result = validate_cell(cell, schemas=schemas)

    if result.warnings and any(JSON_SCHEMA_SKIPPED_MESSAGE in warning["message"] for warning in result.warnings):
        pytest.skip("jsonschema not available in runtime")

    assert result.valid is True
    assert result.errors == []
    assert result.details.get("schema_applied") is True
    assert result.details.get("schema_ref") == "payload"


def test_json_schema_reference_reports_missing_definition() -> None:
    cell = _make_cell(
        "json",
        "{\"value\": 4}",
        json_schema="scratchpad://schemas/unknown",
    )

    result = validate_cell(cell, schemas={})

    if result.warnings and any(JSON_SCHEMA_SKIPPED_MESSAGE in warning["message"] for warning in result.warnings):
        pytest.skip("jsonschema not available in runtime")

    assert result.valid is True
    assert any("schema reference" in warning["message"] for warning in result.warnings)
    assert result.details.get("schema_ref") == "unknown"


def test_json_schema_references_warn_when_registry_support_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    if validation_module.jsonschema is None:
        pytest.skip("jsonschema not available in runtime")

    cell = _make_cell(
        "json",
        "{\"value\": 5}",
        json_schema={"$ref": "scratchpad://schemas/shared"},
    )
    schemas = {"shared": {"type": "object", "properties": {"value": {"type": "integer"}}}}

    monkeypatch.setattr(validation_module, "Registry", None, raising=False)
    monkeypatch.setattr(validation_module, "Resource", None, raising=False)
    monkeypatch.setattr(validation_module, "_referencing_missing_logged", False, raising=False)

    result = validate_cell(cell, schemas=schemas)

    warning_messages = [warning["message"] for warning in result.warnings]
    assert any(
        validation_module.JSON_SCHEMA_REFERENCE_SKIPPED_MESSAGE in message
        for message in warning_messages
    )
    assert result.errors == []
