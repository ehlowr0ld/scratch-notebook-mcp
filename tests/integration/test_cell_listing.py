from __future__ import annotations

import json

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_list_cells_impl,
    _scratch_list_impl,
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


async def _make_scratchpad_with_cells() -> tuple[str, list[str]]:
    create_resp = await _scratch_create_impl(
        metadata={
            "title": "Integration Listing",
            "description": "Cell listing integration test",
            "tags": ["parent"],
            "namespace": "integration",
        }
    )
    assert create_resp["ok"] is True
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    cell_ids: list[str] = []
    for idx, tag in enumerate(["alpha", "beta", "gamma"]):
        append_resp = await _scratch_append_cell_impl(
            scratch_id,
            {
                "language": "json",
                "content": json.dumps({"index": idx}),
                "metadata": {"tags": [tag]},
            },
        )
        assert append_resp["ok"] is True
        cell_ids = [cell["cell_id"] for cell in append_resp["scratchpad"]["cells"]]

    return scratch_id, cell_ids


@pytest.mark.asyncio
async def test_cell_listing_and_filtered_read_behaviour(app) -> None:
    scratch_id, cell_ids = await _make_scratchpad_with_cells()

    all_cells_resp = await _scratch_list_cells_impl(scratch_id)
    assert all_cells_resp["ok"] is True
    all_cells = all_cells_resp["cells"]
    assert [cell["cell_id"] for cell in all_cells] == cell_ids
    assert all("content" not in cell for cell in all_cells)
    assert all("metadata" in cell for cell in all_cells)
    assert [cell["tags"] for cell in all_cells] == [["alpha"], ["beta"], ["gamma"]]

    tag_filtered = await _scratch_list_cells_impl(scratch_id, tags=["beta"])
    assert tag_filtered["ok"] is True
    tag_cells = tag_filtered["cells"]
    assert len(tag_cells) == 1
    assert tag_cells[0]["cell_id"] == cell_ids[1]
    assert tag_cells[0]["tags"] == ["beta"]

    intersection = await _scratch_list_cells_impl(
        scratch_id,
        cell_ids=[cell_ids[1], cell_ids[2]],
        tags=["beta"],
    )
    assert intersection["ok"] is True
    intersection_cells = intersection["cells"]
    assert [cell["cell_id"] for cell in intersection_cells] == [cell_ids[1]]
    assert intersection_cells[0]["tags"] == ["beta"]

    read_without_metadata = await _scratch_read_impl(
        scratch_id,
        cell_ids=[cell_ids[1]],
        include_metadata=False,
    )
    assert read_without_metadata["ok"] is True
    assert "metadata" not in read_without_metadata["scratchpad"]
    assert read_without_metadata["scratchpad"]["tags"] == ["parent", "alpha", "beta", "gamma"]
    assert read_without_metadata["scratchpad"]["cell_tags"] == ["beta"]
    cells = read_without_metadata["scratchpad"]["cells"]
    assert len(cells) == 1
    assert cells[0]["cell_id"] == cell_ids[1]
    assert cells[0]["tags"] == ["beta"]

    read_with_tags = await _scratch_read_impl(
        scratch_id,
        tags=["gamma"],
    )
    assert read_with_tags["ok"] is True
    tagged_cells = read_with_tags["scratchpad"]["cells"]
    assert len(tagged_cells) == 1
    assert tagged_cells[0]["cell_id"] == cell_ids[2]
    assert "metadata" in read_with_tags["scratchpad"]
    assert "cell_tags" in read_with_tags["scratchpad"]["metadata"]
    assert read_with_tags["scratchpad"]["tags"] == ["parent", "alpha", "beta", "gamma"]
    assert tagged_cells[0]["tags"] == ["gamma"]

    list_filtered = await _scratch_list_impl(tags=["gamma"])
    assert list_filtered["ok"] is True
    assert [entry["scratch_id"] for entry in list_filtered["scratchpads"]] == [scratch_id]

    namespace_match = await _scratch_list_impl(namespaces=["integration"])
    assert [entry["scratch_id"] for entry in namespace_match["scratchpads"]] == [scratch_id]

    namespace_mismatch = await _scratch_list_impl(namespaces=["other"])
    assert namespace_mismatch["scratchpads"] == []
