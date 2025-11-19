from __future__ import annotations

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_create_impl,
    _scratch_list_impl,
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
    return tmp_path


@pytest.mark.asyncio
async def test_list_response_does_not_leak_paths(app) -> None:
    storage_dir = str(app)

    resp = await _scratch_create_impl(metadata={"title": "Leak test"})
    assert resp["ok"]

    list_resp = await _scratch_list_impl()
    assert list_resp["ok"]

    for entry in list_resp["scratchpads"]:
        metadata_str = str(entry.get("metadata", {}))
        assert storage_dir not in metadata_str
        assert "scratchpads" not in metadata_str
