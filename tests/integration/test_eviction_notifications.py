from __future__ import annotations

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    _scratch_create_impl,
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
        "SCRATCH_NOTEBOOK_MAX_SCRATCHPADS": "1",
        "SCRATCH_NOTEBOOK_EVICTION_POLICY": "discard",
    }
    config = load_config(argv=[], environ=environ)
    initialize_app(config)
    return config


@pytest.mark.asyncio
async def test_scratch_create_returns_evicted_ids(app) -> None:
    first_resp = await _scratch_create_impl(metadata={"title": "first"})
    assert first_resp["ok"] is True
    assert "evicted_scratchpads" not in first_resp
    first_id = first_resp["scratchpad"]["scratch_id"]

    second_resp = await _scratch_create_impl(metadata={"title": "second"})
    assert second_resp["ok"] is True
    assert second_resp["evicted_scratchpads"] == [first_id]
    second_id = second_resp["scratchpad"]["scratch_id"]

    missing_first = await _scratch_read_impl(first_id)
    assert missing_first["ok"] is False
    assert missing_first["error"]["code"] == "NOT_FOUND"

    present_second = await _scratch_read_impl(second_id)
    assert present_second["ok"] is True
    assert present_second["scratchpad"]["scratch_id"] == second_id
