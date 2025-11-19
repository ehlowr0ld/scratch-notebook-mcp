from __future__ import annotations

import json

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_list_cells_impl,
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


async def _make_pad_with_cells() -> tuple[str, list[str]]:
    create_resp = await _scratch_create_impl()
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
async def test_list_cells_returns_all_entries(app) -> None:
    scratch_id, cell_ids = await _make_pad_with_cells()

    resp = await _scratch_list_cells_impl(scratch_id)

    assert resp["ok"] is True
    cells = resp["cells"]
    assert len(cells) == 3
    assert [cell["cell_id"] for cell in cells] == cell_ids
    assert all("content" not in cell for cell in cells)
    assert [cell["tags"] for cell in cells] == [["tag-0"], ["tag-1"], ["tag-2"]]


@pytest.mark.asyncio
async def test_list_cells_filters_by_indices(app) -> None:
    scratch_id, cell_ids = await _make_pad_with_cells()

    resp = await _scratch_list_cells_impl(scratch_id, indices=[1, 2])

    assert resp["ok"] is True
    cells = resp["cells"]
    assert [cell["cell_id"] for cell in cells] == cell_ids[1:3]


@pytest.mark.asyncio
async def test_list_cells_filters_by_cell_ids(app) -> None:
    scratch_id, cell_ids = await _make_pad_with_cells()

    target = cell_ids[1]
    resp = await _scratch_list_cells_impl(scratch_id, cell_ids=[target])

    assert resp["ok"] is True
    cells = resp["cells"]
    assert len(cells) == 1
    assert cells[0]["cell_id"] == target


@pytest.mark.asyncio
async def test_list_cells_filters_by_tags(app) -> None:
    scratch_id, cell_ids = await _make_pad_with_cells()

    resp = await _scratch_list_cells_impl(scratch_id, tags=["tag-1"])

    assert resp["ok"] is True
    cells = resp["cells"]
    assert len(cells) == 1
    assert cells[0]["cell_id"] == cell_ids[1]
    assert cells[0]["tags"] == ["tag-1"]


@pytest.mark.asyncio
async def test_list_cells_intersection_of_indices_and_ids(app) -> None:
    scratch_id, cell_ids = await _make_pad_with_cells()

    resp = await _scratch_list_cells_impl(
        scratch_id,
        indices=[0, 1],
        cell_ids=[cell_ids[1], cell_ids[2]],
    )

    assert resp["ok"] is True
    cells = resp["cells"]
    assert len(cells) == 1
    assert cells[0]["cell_id"] == cell_ids[1]


@pytest.mark.asyncio
async def test_list_cells_invalid_index_returns_error(app) -> None:
    scratch_id, _ = await _make_pad_with_cells()

    resp = await _scratch_list_cells_impl(scratch_id, indices=[999])

    assert resp["ok"] is False
    assert resp["error"]["code"] == "INVALID_INDEX"


@pytest.mark.asyncio
async def test_list_cells_invalid_cell_id_returns_error(app) -> None:
    scratch_id, _ = await _make_pad_with_cells()

    resp = await _scratch_list_cells_impl(scratch_id, cell_ids=["missing"])

    assert resp["ok"] is False
    assert resp["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_list_cells_invalid_tags_type_returns_error(app) -> None:
    scratch_id, _ = await _make_pad_with_cells()

    resp = await _scratch_list_cells_impl(scratch_id, tags="invalid")  # type: ignore[arg-type]

    assert resp["ok"] is False
    assert resp["error"]["code"] == "VALIDATION_ERROR"
