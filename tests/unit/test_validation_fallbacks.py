from __future__ import annotations

import uuid

import pytest

from scratch_notebook import models
from scratch_notebook.validation import JSON_SCHEMA_SKIPPED_MESSAGE, NOT_VALIDATED_MESSAGE, validate_cell


def _cell(language: str, content: str, **kwargs) -> models.ScratchCell:
    return models.ScratchCell(
        cell_id=str(uuid.uuid4()),
        index=2,
        language=language,
        content=content,
        **kwargs,
    )


def test_validation_reports_not_performed_for_tsx_language(monkeypatch: pytest.MonkeyPatch) -> None:
    cell = _cell("tsx", "const App = () => <div />;")

    result = validate_cell(cell)

    assert result.valid is True
    assert result.errors == []
    assert any("not available" in warning["message"] for warning in result.warnings)


def test_invalid_schema_string_produces_error() -> None:
    cell = _cell("json", "{\"value\": 1}", json_schema="not-json")

    result = validate_cell(cell)

    assert result.valid is False
    assert any("JSON schema" in error["message"] for error in result.errors)


def test_json_schema_skipped_when_library_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scratch_notebook.validation.jsonschema", None, raising=False)

    cell = _cell("json", "{\"value\": 1}", json_schema={"type": "object"})

    result = validate_cell(cell)

    assert result.valid is True
    assert any(JSON_SCHEMA_SKIPPED_MESSAGE in warning["message"] for warning in result.warnings)


def test_plain_text_validation_includes_reason_detail() -> None:
    cell = _cell("txt", "notes go here")

    result = validate_cell(cell)

    assert result.valid is True
    assert any(NOT_VALIDATED_MESSAGE in warning["message"] for warning in result.warnings)
    assert result.details.get("reason") == "Plain text does not require validation"
