from __future__ import annotations

import json

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_read_impl,
    _scratch_validate_impl,
)


@pytest.fixture
def app(tmp_path):
    environ = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
        "SCRATCH_NOTEBOOK_ENABLE_STDIO": "false",
        "SCRATCH_NOTEBOOK_ENABLE_HTTP": "false",
        "SCRATCH_NOTEBOOK_ENABLE_SSE": "false",
        "SCRATCH_NOTEBOOK_ENABLE_METRICS": "false",
        "SCRATCH_NOTEBOOK_ENABLE_AUTH": "false",
        "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
    }
    config = load_config(argv=[], environ=environ)
    initialize_app(config)
    return config


@pytest.mark.asyncio
async def test_scratch_validate_returns_results_for_json_cell(app) -> None:
    create_resp = await _scratch_create_impl(metadata={"title": "validation"})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({"value": 1}),
        },
    )

    initialize_app(app)

    validate_resp = await _scratch_validate_impl(scratch_id)

    assert validate_resp["ok"] is True
    results = validate_resp["results"]
    assert len(results) == 1
    assert results[0]["valid"] is True


@pytest.mark.asyncio
async def test_scratch_validate_with_indices_limits_scope(app) -> None:
    create_resp = await _scratch_create_impl(metadata={})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({"one": 1}),
        },
    )
    await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({"two": 2}),
        },
    )

    validate_resp = await _scratch_validate_impl(scratch_id, indices=[1])

    assert validate_resp["ok"] is True
    results = validate_resp["results"]
    assert len(results) == 1
    assert results[0]["cell_index"] == 1


@pytest.mark.asyncio
async def test_append_with_validate_flag_returns_validation_summary(app) -> None:
    create_resp = await _scratch_create_impl(metadata={})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    append_resp = await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({"value": 5}),
            "validate": True,
        },
    )

    assert append_resp["ok"] is True
    assert "validation" in append_resp
    assert append_resp["validation"][0]["valid"] is True


@pytest.mark.asyncio
async def test_append_with_validate_flag_rejects_invalid_payload(app) -> None:
    create_resp = await _scratch_create_impl(metadata={})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    append_resp = await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": "{broken}",
            "validate": True,
        },
    )

    assert append_resp["ok"] is False
    assert append_resp["error"]["code"] == "VALIDATION_ERROR"

    # Ensure no cells were added on failure
    read_resp = await _scratch_read_impl(scratch_id)
    assert read_resp["scratchpad"]["cells"] == []


@pytest.mark.asyncio
async def test_validate_reports_plain_text_warning(app) -> None:
    create_resp = await _scratch_create_impl(metadata={})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "txt",
            "content": "notes",
        },
    )

    validate_resp = await _scratch_validate_impl(scratch_id)

    assert validate_resp["ok"] is True
    warnings = validate_resp["results"][0]["warnings"]
    assert any("Validation not performed" in warning["message"] for warning in warnings)


@pytest.mark.asyncio
async def test_validate_uses_shared_schema_registry(app) -> None:
    shared_schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
    }
    create_resp = await _scratch_create_impl(metadata={"schemas": {"payload": shared_schema}})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({"value": 7}),
            "json_schema": {"$ref": "scratchpad://schemas/payload"},
        },
    )

    initialize_app(app)

    validate_resp = await _scratch_validate_impl(scratch_id)

    assert validate_resp["ok"] is True
    result = validate_resp["results"][0]
    assert result["valid"] is True
    assert result.get("details", {}).get("schema_ref") == "payload"


@pytest.mark.asyncio
async def test_append_validate_flag_rejects_missing_shared_schema(app) -> None:
    create_resp = await _scratch_create_impl(metadata={"schemas": {}})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    append_resp = await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({"value": 1}),
            "json_schema": "scratchpad://schemas/does-not-exist",
            "validate": True,
        },
    )

    assert append_resp["ok"] is False
    assert append_resp["error"]["code"] == "VALIDATION_ERROR"
