from __future__ import annotations

import json

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_read_impl,
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


async def _create_populated_pad() -> tuple[str, list[str]]:
    create_resp = await _scratch_create_impl(
        metadata={"title": "Notebook", "description": "Filtered read test", "namespace": "primary"}
    )
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    cell_ids: list[str] = []
    for idx in range(3):
        append_resp = await _scratch_append_cell_impl(
            scratch_id,
            {
                "language": "json",
                "content": json.dumps({"index": idx}),
                "metadata": {"tags": [f"tag-{idx}"]},
            },
        )
        assert append_resp["ok"] is True
        cell_ids = [cell["cell_id"] for cell in append_resp["scratchpad"]["cells"]]

    return scratch_id, cell_ids


@pytest.mark.asyncio
async def test_read_filters_by_indices(app) -> None:
    scratch_id, cell_ids = await _create_populated_pad()

    resp = await _scratch_read_impl(scratch_id, indices=[1, 2])

    assert resp["ok"] is True
    cells = resp["scratchpad"]["cells"]
    assert [cell["index"] for cell in cells] == [1, 2]
    assert [cell["cell_id"] for cell in cells] == cell_ids[1:3]
    assert [cell["tags"] for cell in cells] == [["tag-1"], ["tag-2"]]
    assert resp["scratchpad"]["tags"] == ["tag-0", "tag-1", "tag-2"]


@pytest.mark.asyncio
async def test_read_filters_by_cell_ids(app) -> None:
    scratch_id, cell_ids = await _create_populated_pad()

    target_id = cell_ids[1]
    resp = await _scratch_read_impl(scratch_id, cell_ids=[target_id])

    assert resp["ok"] is True
    cells = resp["scratchpad"]["cells"]
    assert len(cells) == 1
    assert cells[0]["cell_id"] == target_id
    assert cells[0]["tags"] == ["tag-1"]
    assert resp["scratchpad"]["tags"] == ["tag-0", "tag-1", "tag-2"]


@pytest.mark.asyncio
async def test_read_filters_by_indices_and_cell_ids_intersection(app) -> None:
    scratch_id, cell_ids = await _create_populated_pad()

    resp = await _scratch_read_impl(scratch_id, indices=[0, 1], cell_ids=[cell_ids[1]])

    assert resp["ok"] is True
    cells = resp["scratchpad"]["cells"]
    assert len(cells) == 1
    assert cells[0]["cell_id"] == cell_ids[1]
    assert cells[0]["tags"] == ["tag-1"]
    assert resp["scratchpad"]["tags"] == ["tag-0", "tag-1", "tag-2"]


@pytest.mark.asyncio
async def test_read_include_metadata_false_omits_metadata(app) -> None:
    scratch_id, _ = await _create_populated_pad()

    resp = await _scratch_read_impl(scratch_id, include_metadata=False)

    assert resp["ok"] is True
    assert "metadata" not in resp["scratchpad"]
    assert resp["scratchpad"]["tags"] == ["tag-0", "tag-1", "tag-2"]
    assert resp["scratchpad"]["cell_tags"] == ["tag-0", "tag-1", "tag-2"]
    assert all(cell["tags"] == [f"tag-{idx}"] for idx, cell in enumerate(resp["scratchpad"]["cells"]))


@pytest.mark.asyncio
async def test_read_with_invalid_index_returns_error(app) -> None:
    scratch_id, _ = await _create_populated_pad()

    resp = await _scratch_read_impl(scratch_id, indices=[42])

    assert resp["ok"] is False
    assert resp["error"]["code"] == "INVALID_INDEX"


@pytest.mark.asyncio
async def test_read_namespace_filter_blocks_mismatch(app) -> None:
    scratch_id, _ = await _create_populated_pad()

    resp = await _scratch_read_impl(scratch_id, namespaces=["other"])

    assert resp["ok"] is False
    assert resp["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_read_namespace_filter_allows_match(app) -> None:
    scratch_id, _ = await _create_populated_pad()

    resp = await _scratch_read_impl(scratch_id, namespaces=["primary"])

    assert resp["ok"] is True
