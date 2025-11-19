from __future__ import annotations

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_search_impl,
)


@pytest.fixture()
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
async def test_scratch_search_returns_ranked_hits(app) -> None:
    create_resp = await _scratch_create_impl(
        metadata={
            "title": "Test notebook",
            "description": "Collection of greetings",
            "namespace": "semantic",
            "tags": ["examples"],
        }
    )
    assert create_resp["ok"]
    scratchpad = create_resp["scratchpad"]
    scratch_id = scratchpad["scratch_id"]

    await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "md",
            "content": "Hello semantic search",
            "metadata": {"tags": ["hello"]},
        },
    )

    await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "md",
            "content": "Farewell semantic search",
            "metadata": {"tags": ["goodbye"]},
        },
    )

    search_resp = await _scratch_search_impl("hello semantic", namespaces=["semantic"], limit=5)
    assert search_resp["ok"] is True
    assert search_resp["hits"], "Expected at least one search hit"
    hits = search_resp["hits"]
    cell_hit = next((hit for hit in hits if hit["cell_id"] is not None), None)
    assert cell_hit is not None
    assert cell_hit["scratch_id"] == scratch_id
    assert "hello" in cell_hit["snippet"].lower()
    assert "test notebook" in cell_hit["snippet"].lower()
    assert "collection of greetings" in cell_hit["snippet"].lower()

    filtered_resp = await _scratch_search_impl("semantic", namespaces=["semantic"], tags=["goodbye"], limit=5)
    assert filtered_resp["ok"] is True
    assert len(filtered_resp["hits"]) == 1
    filtered_tags = filtered_resp["hits"][0]["tags"]
    assert "examples" in filtered_tags
    assert "goodbye" in filtered_tags
