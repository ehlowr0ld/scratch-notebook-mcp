from __future__ import annotations

import uuid

import pytest

from scratch_notebook import models
from scratch_notebook.config import load_config
from scratch_notebook.errors import CONFIG_ERROR, NOT_FOUND, VALIDATION_ERROR, ScratchNotebookError
from scratch_notebook.server import _coerce_schema_request, _normalize_schema_id
from scratch_notebook.storage import Storage, StorageError


@pytest.fixture()
def storage(tmp_path) -> Storage:
    cfg = load_config(
        argv=[],
        environ={
            "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
            "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        },
    )
    return Storage(cfg)


def _empty_pad() -> models.Scratchpad:
    return models.Scratchpad(scratch_id=str(uuid.uuid4()), cells=[], metadata={})


def _create_pad(storage: Storage, metadata: dict[str, object] | None = None) -> models.Scratchpad:
    pad = models.Scratchpad(
        scratch_id=str(uuid.uuid4()),
        cells=[],
        metadata=metadata or {},
    )
    storage.create_scratchpad(pad)
    return pad


def test_list_schemas_normalizes_entries(storage: Storage) -> None:
    schema_metadata = {
        "schemas": {
            "beta": {
                "description": "Beta schema",
                "schema": {"type": "object", "properties": {"value": {"type": "string"}}},
            },
            "alpha": '{"type": "object", "properties": {"flag": {"type": "boolean"}}}',
        }
    }
    pad = _create_pad(storage, metadata=schema_metadata)

    entries = storage.list_schemas(pad.scratch_id)

    assert [entry["name"] for entry in entries] == ["alpha", "beta"]
    for entry in entries:
        assert entry["id"]
        assert entry["name"]
        assert entry["schema"]["type"] == "object"


def test_get_schema_missing_raises_not_found(storage: Storage) -> None:
    pad = _create_pad(storage)

    with pytest.raises(StorageError) as exc:
        storage.get_schema(pad.scratch_id, uuid.uuid4().hex)

    assert exc.value.code == NOT_FOUND


def test_upsert_schema_creates_and_updates(storage: Storage) -> None:
    pad = _create_pad(storage)

    initial_entry = _coerce_schema_request(
        {
            "name": "profile",
            "description": "Initial profile schema",
            "schema": {"type": "object", "properties": {"age": {"type": "integer"}}},
        }
    )
    stored = storage.upsert_schema(pad.scratch_id, initial_entry)

    assert stored["name"] == "profile"
    assert stored["description"] == "Initial profile schema"

    updated_entry = _coerce_schema_request(
        {
            "id": stored["id"],
            "name": "profile",
            "description": "Updated profile schema",
            "schema": {
                "type": "object",
                "properties": {
                    "age": {"type": "integer"},
                    "name": {"type": "string"},
                },
            },
        }
    )
    updated = storage.upsert_schema(pad.scratch_id, updated_entry)

    assert updated["id"] == stored["id"]
    assert updated["description"] == "Updated profile schema"
    schemas = storage.list_schemas(pad.scratch_id)
    assert len(schemas) == 1


def test_upsert_schema_requires_name_or_id(storage: Storage) -> None:
    pad = _create_pad(storage)

    with pytest.raises(StorageError) as exc:
        storage.upsert_schema(pad.scratch_id, {"schema": {"type": "object"}})

    assert exc.value.code == CONFIG_ERROR


def test_coerce_schema_request_requires_schema_field() -> None:
    with pytest.raises(ScratchNotebookError) as exc_info:
        _coerce_schema_request({"name": "missing-schema"})

    assert exc_info.value.code == VALIDATION_ERROR


def test_coerce_schema_request_requires_object() -> None:
    with pytest.raises(ScratchNotebookError) as exc_info:
        _coerce_schema_request("not-a-mapping")  # type: ignore[arg-type]

    assert exc_info.value.code == VALIDATION_ERROR


def test_coerce_schema_request_rejects_invalid_schema_definition() -> None:
    with pytest.raises(ScratchNotebookError) as exc_info:
        _coerce_schema_request(
            {
                "name": "invalid",
                "schema": {"type": 123},
            }
        )

    assert exc_info.value.code == VALIDATION_ERROR


def test_coerce_schema_request_requires_string_description() -> None:
    with pytest.raises(ScratchNotebookError) as exc_info:
        _coerce_schema_request(
            {
                "name": "bad-description",
                "description": 42,
                "schema": {"type": "object"},
            }
        )

    assert exc_info.value.code == VALIDATION_ERROR


def test_normalize_schema_id_rejects_invalid_uuid() -> None:
    with pytest.raises(ScratchNotebookError) as exc_info:
        _normalize_schema_id("not-a-uuid")

    assert exc_info.value.code == VALIDATION_ERROR

    generated = _normalize_schema_id(None)
    assert isinstance(generated, str)
    assert len(generated) == 32
