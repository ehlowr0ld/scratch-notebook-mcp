from __future__ import annotations

import json

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_get_schema_impl,
    _scratch_list_schemas_impl,
    _scratch_upsert_schema_impl,
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
async def test_schema_registry_roundtrip(app) -> None:
    create_resp = await _scratch_create_impl()
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    payload_schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
    }
    payload_upsert = await _scratch_upsert_schema_impl(
        scratch_id,
        {
            "name": "payload",
            "description": "Payload schema",
            "schema": payload_schema,
        },
    )
    assert payload_upsert["ok"] is True
    payload_entry = payload_upsert["schema"]
    payload_id = payload_entry["id"]
    assert payload_entry["name"] == "payload"
    assert payload_entry["description"] == "Payload schema"
    assert payload_entry["schema"]["required"] == ["value"]

    alpha_schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    alpha_upsert = await _scratch_upsert_schema_impl(
        scratch_id,
        {
            "name": "alpha",
            "description": "Alpha schema",
            "schema": alpha_schema,
        },
    )
    assert alpha_upsert["ok"] is True

    list_resp = await _scratch_list_schemas_impl(scratch_id)
    assert list_resp["ok"] is True
    schemas = list_resp["schemas"]
    assert [item["description"] for item in schemas] == ["Alpha schema", "Payload schema"]
    assert {item["name"] for item in schemas} == {"alpha", "payload"}

    get_resp = await _scratch_get_schema_impl(scratch_id, payload_id)
    assert get_resp["ok"] is True
    assert get_resp["schema"]["id"] == payload_id
    assert get_resp["schema"]["description"] == "Payload schema"

    updated_payload_schema = {
        "type": "object",
        "properties": {
            "value": {"type": "integer"},
            "label": {"type": "string"},
        },
        "required": ["value"],
    }
    update_resp = await _scratch_upsert_schema_impl(
        scratch_id,
        {
            "id": payload_id,
            "name": "payload",
            "description": "Updated payload schema",
            "schema": updated_payload_schema,
        },
    )
    assert update_resp["ok"] is True
    assert update_resp["schema"]["id"] == payload_id
    assert update_resp["schema"]["description"] == "Updated payload schema"

    post_update_list = await _scratch_list_schemas_impl(scratch_id)
    assert post_update_list["ok"] is True
    post_update_payload = next(item for item in post_update_list["schemas"] if item["name"] == "payload")
    assert post_update_payload["description"] == "Updated payload schema"
    assert "label" in post_update_payload["schema"]["properties"]


@pytest.mark.asyncio
async def test_upsert_schema_rejects_invalid_schema(app) -> None:
    create_resp = await _scratch_create_impl()
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    invalid_resp = await _scratch_upsert_schema_impl(
        scratch_id,
        {
            "name": "broken",
            "description": "Broken schema",
            "schema": {"type": "invalid"},
        },
    )

    assert invalid_resp["ok"] is False
    assert invalid_resp["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_upserted_schema_integrates_with_validation(app) -> None:
    create_resp = await _scratch_create_impl()
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    schema_resp = await _scratch_upsert_schema_impl(
        scratch_id,
        {
            "name": "payload",
            "description": "Payload schema",
            "schema": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
        },
    )
    assert schema_resp["ok"] is True

    append_resp = await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({"value": 7}),
            "json_schema": {"$ref": "scratchpad://schemas/payload"},
            "validate": True,
        },
    )
    assert append_resp["ok"] is True

    validate_resp = await _scratch_validate_impl(scratch_id)
    assert validate_resp["ok"] is True
    assert validate_resp["results"][0]["valid"] is True
    assert validate_resp["results"][0].get("details", {}).get("schema_ref") == "payload"

    invalid_append = await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": json.dumps({}),
            "json_schema": {"$ref": "scratchpad://schemas/payload"},
            "validate": True,
        },
    )
    assert invalid_append["ok"] is True
    assert invalid_append["validation"][0]["valid"] is False
    assert invalid_append["validation"][0]["errors"]
