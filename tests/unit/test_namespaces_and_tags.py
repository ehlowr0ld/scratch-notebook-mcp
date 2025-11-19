from __future__ import annotations

import uuid

import pytest

from scratch_notebook import load_config, models
from scratch_notebook.errors import NOT_FOUND, VALIDATION_ERROR, ScratchNotebookError
from scratch_notebook.storage import Storage


def _build_config(tmp_path):
    environ = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
        "SCRATCH_NOTEBOOK_ENABLE_STDIO": "false",
        "SCRATCH_NOTEBOOK_ENABLE_HTTP": "false",
        "SCRATCH_NOTEBOOK_ENABLE_SSE": "false",
        "SCRATCH_NOTEBOOK_ENABLE_METRICS": "false",
        "SCRATCH_NOTEBOOK_ENABLE_AUTH": "false",
        "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
    }
    return load_config(argv=[], environ=environ)


def _make_pad(namespace: str, *, tag: str | None = None) -> models.Scratchpad:
    metadata = {"namespace": namespace}
    if tag:
        metadata["tags"] = [tag]
    return models.Scratchpad(
        scratch_id=str(uuid.uuid4()),
        metadata=metadata,
        cells=[
            models.ScratchCell(
                cell_id=str(uuid.uuid4()),
                index=0,
                language="json",
                content="{}",
                metadata={"tags": [tag]} if tag else {},
            )
        ],
    )


def test_register_namespace_idempotent(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    namespace, created = storage.register_namespace("workspace")
    assert namespace == "workspace"
    assert created is True

    namespace, created = storage.register_namespace("workspace")
    assert namespace == "workspace"
    assert created is False


def test_list_namespaces_includes_counts(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    storage.register_namespace("orphan")
    pad = _make_pad("workspace", tag="alpha")
    storage.create_scratchpad(pad)

    namespaces = storage.list_namespaces()
    assert namespaces == [
        {"namespace": "orphan", "scratchpad_count": 0},
        {"namespace": "workspace", "scratchpad_count": 1},
    ]


def test_rename_namespace_with_migration(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad_one = _make_pad("alpha", tag="one")
    pad_two = _make_pad("alpha", tag="two")
    storage.create_scratchpad(pad_one)
    storage.create_scratchpad(pad_two)

    namespace, migrated = storage.rename_namespace("alpha", "beta")
    assert namespace == "beta"
    assert migrated == 2

    pads = storage.list_scratchpads()
    assert all(entry["namespace"] == "beta" for entry in pads)


def test_rename_namespace_without_migration_fails(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad("alpha")
    storage.create_scratchpad(pad)

    with pytest.raises(ScratchNotebookError) as exc:
        storage.rename_namespace("alpha", "beta", migrate_scratchpads=False)
    assert exc.value.code == VALIDATION_ERROR


def test_delete_namespace_requires_cascade_when_referenced(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad("alpha")
    storage.create_scratchpad(pad)

    with pytest.raises(ScratchNotebookError) as exc:
        storage.delete_namespace("alpha", delete_scratchpads=False)
    assert exc.value.code == VALIDATION_ERROR


def test_delete_namespace_with_cascade_removes_scratchpads(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad("alpha")
    storage.create_scratchpad(pad)

    deleted, removed = storage.delete_namespace("alpha", delete_scratchpads=True)
    assert deleted is True
    assert removed == 1

    with pytest.raises(ScratchNotebookError) as exc:
        storage.read_scratchpad(pad.scratch_id)
    assert exc.value.code == NOT_FOUND

    assert storage.list_namespaces() == []
