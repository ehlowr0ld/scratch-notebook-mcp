from __future__ import annotations

import uuid

import pytest

from scratch_notebook import models


def build_cell(**overrides):
    data = {
        "cell_id": str(uuid.uuid4()),
        "index": 0,
        "language": "json",
        "content": "{}",
        "validate": True,
        "json_schema": {"type": "object"},
        "metadata": {"title": "example"},
    }
    data.update(overrides)
    return data


def test_scratch_cell_round_trip() -> None:
    payload = build_cell()

    cell = models.ScratchCell.from_dict(payload)
    assert cell.language == "json"
    assert cell.validate is True
    assert cell.metadata["title"] == "example"

    assert cell.to_dict() == payload


def test_scratchpad_round_trip() -> None:
    pad_data = {
        "scratch_id": str(uuid.uuid4()),
        "metadata": {"title": "notes"},
        "cells": [build_cell(index=0), build_cell(index=1, language="md", content="# heading")],
    }

    pad = models.Scratchpad.from_dict(pad_data)
    assert pad.scratch_id == pad_data["scratch_id"]
    assert len(pad.cells) == 2
    assert pad.cells[1].language == "md"

    payload = pad.to_dict()
    assert payload["scratch_id"] == pad_data["scratch_id"]
    assert payload["title"] == "notes"
    assert payload["metadata"]["title"] == "notes"
    assert payload["cells"] == pad_data["cells"]


def test_scratchpad_to_dict_exposes_namespace_and_tags() -> None:
    cell_payload = build_cell(
        index=0,
        metadata={"tags": ["cell-tag"]},
    )
    pad_data = {
        "scratch_id": str(uuid.uuid4()),
        "metadata": {"namespace": "research", "tags": ["pad-tag"]},
        "cells": [cell_payload],
    }

    pad = models.Scratchpad.from_dict(pad_data)
    payload = pad.to_dict()

    assert payload["namespace"] == "research"
    assert payload["tags"] == ["pad-tag", "cell-tag"]
    assert payload["cell_tags"] == ["cell-tag"]
    assert payload["cells"][0]["tags"] == ["cell-tag"]
    assert payload["metadata"]["tags"] == ["pad-tag", "cell-tag"]
    assert payload["metadata"]["cell_tags"] == ["cell-tag"]


def test_validation_result_helpers() -> None:
    result = models.ValidationResult(cell_index=2, language="py")
    result.add_error("Syntax error", code="SYNTAX")
    result.add_warning("Long line")

    assert result.valid is False
    assert result.errors[0]["code"] == "SYNTAX"
    assert result.warnings[0]["message"] == "Long line"


def test_reject_invalid_language() -> None:
    with pytest.raises(ValueError):
        models.ScratchCell.from_dict(build_cell(language="unsupported"))
