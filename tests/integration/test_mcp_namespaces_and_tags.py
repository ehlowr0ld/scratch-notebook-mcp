from __future__ import annotations

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    _scratch_create_impl,
    _scratch_namespace_create_impl,
    _scratch_namespace_delete_impl,
    _scratch_namespace_list_impl,
    _scratch_namespace_rename_impl,
    _scratch_read_impl,
    initialize_app,
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
async def test_namespace_lifecycle(app) -> None:
    list_resp = await _scratch_namespace_list_impl()
    assert list_resp["ok"] is True
    assert list_resp["namespaces"] == []

    create_resp = await _scratch_namespace_create_impl(namespace="research")
    assert create_resp["ok"] is True
    assert create_resp["created"] is True

    list_resp = await _scratch_namespace_list_impl()
    assert list_resp["ok"] is True
    assert list_resp["namespaces"] == [{"namespace": "research", "scratchpad_count": 0}]

    create_pad = await _scratch_create_impl(metadata={"namespace": "research"})
    assert create_pad["ok"] is True
    scratch_id = create_pad["scratchpad"]["scratch_id"]

    list_resp = await _scratch_namespace_list_impl()
    assert list_resp["namespaces"] == [{"namespace": "research", "scratchpad_count": 1}]

    rename_resp = await _scratch_namespace_rename_impl(
        old_namespace="research",
        new_namespace="laboratory",
    )
    assert rename_resp["ok"] is True
    assert rename_resp["namespace"] == "laboratory"
    assert rename_resp["migrated_count"] == 1

    read_resp = await _scratch_read_impl(scratch_id)
    assert read_resp["ok"] is True
    assert read_resp["scratchpad"]["namespace"] == "laboratory"

    list_resp = await _scratch_namespace_list_impl()
    assert list_resp["namespaces"] == [{"namespace": "laboratory", "scratchpad_count": 1}]

    delete_block = await _scratch_namespace_delete_impl(namespace="laboratory")
    assert delete_block["ok"] is False
    assert delete_block["error"]["code"] == "VALIDATION_ERROR"

    delete_resp = await _scratch_namespace_delete_impl(namespace="laboratory", delete_scratchpads=True)
    assert delete_resp["ok"] is True
    assert delete_resp["deleted"] is True
    assert delete_resp["removed_scratchpads"] == 1

    list_resp = await _scratch_namespace_list_impl()
    assert list_resp["namespaces"] == []
