from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from scratch_notebook import models
from scratch_notebook import validation as validation_module
from scratch_notebook.validation import MARKDOWN_SKIPPED_MESSAGE, SYNTAX_CHECK_SKIPPED_MESSAGE, validate_cell


def _cell(language: str, content: str, **kwargs) -> models.ScratchCell:
    return models.ScratchCell(
        cell_id=str(uuid.uuid4()),
        index=0,
        language=language,
        content=content,
        **kwargs,
    )


def test_python_validation_accepts_valid_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation_module, "syntax_checker", None, raising=False)

    cell = _cell("py", "def main():\n    return 42\n")
    result = validate_cell(cell)

    assert result.valid is True
    assert any(SYNTAX_CHECK_SKIPPED_MESSAGE in warning["message"] for warning in result.warnings)


def test_python_validation_reports_checker_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class Outcome:
        warnings = []
        errors = ["Python checker error"]

    def fake_checker(*, language: str, code: str) -> Outcome:
        assert language == "py"
        return Outcome()

    monkeypatch.setattr(validation_module, "syntax_checker", object(), raising=False)
    monkeypatch.setattr(validation_module, "_resolve_syntax_checker", lambda: fake_checker, raising=False)

    cell = _cell("py", "def broken(:\n    pass")
    result = validate_cell(cell)

    assert result.valid is False
    assert any("Python checker error" in error["message"] for error in result.errors)


def test_non_python_language_uses_syntax_checker(monkeypatch: pytest.MonkeyPatch) -> None:
    class Outcome:
        warnings = []
        errors = ["Unexpected token"]

    def fake_checker(*, language: str, code: str) -> Outcome:
        assert language == "js"
        assert "function" in code
        return Outcome()

    monkeypatch.setattr(validation_module, "syntax_checker", object(), raising=False)
    monkeypatch.setattr(validation_module, "_resolve_syntax_checker", lambda: fake_checker, raising=False)

    cell = _cell("js", "function demo() { return 1; }")
    result = validate_cell(cell)

    assert result.valid is False
    assert any("Unexpected token" in error["message"] for error in result.errors)


def test_markdown_validation_warns_when_analyzer_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation_module, "markdown_analysis", None, raising=False)

    cell = _cell("md", "# Documentation\n\nSome content.")
    result = validate_cell(cell)

    assert result.valid is True
    assert any(MARKDOWN_SKIPPED_MESSAGE in warning["message"] for warning in result.warnings)


def test_markdown_validation_reports_analyzer_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_analyzer(content: str) -> SimpleNamespace:  # pragma: no cover - called indirectly
        raise RuntimeError("analysis exploded")

    monkeypatch.setattr(
        validation_module,
        "markdown_analysis",
        SimpleNamespace(analyze=failing_analyzer),
        raising=False,
    )

    cell = _cell("md", "## Title\n\nBody")
    result = validate_cell(cell)

    assert result.valid is True
    assert any("Markdown analysis failed" in warning["message"] for warning in result.warnings)
    assert result.details.get("analysis_error") == "analysis exploded"


def test_markdown_validation_preserves_warnings_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = SimpleNamespace(
        warnings=["Heading levels should increment by one"],
        errors=["Table requires a header row"],
    )

    def successful_analyzer(content: str) -> SimpleNamespace:
        return analysis

    monkeypatch.setattr(
        validation_module,
        "markdown_analysis",
        SimpleNamespace(analyze=successful_analyzer),
        raising=False,
    )

    cell = _cell("md", "# Intro\n\n|a|")
    result = validate_cell(cell)

    assert result.valid is False
    assert any("Heading levels should increment by one" in warning["message"] for warning in result.warnings)
    assert any("Table requires a header row" in error["message"] for error in result.errors)
