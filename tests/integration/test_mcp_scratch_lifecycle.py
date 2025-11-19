from __future__ import annotations

import uuid

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_delete_impl,
    _scratch_list_impl,
    _scratch_read_impl,
    _scratch_replace_cell_impl,
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
async def test_full_scratchpad_lifecycle(app) -> None:
    create_resp = await _scratch_create_impl(
        metadata={
            "title": "Lifecycle Notebook",
            "description": "Lifecycle notebook description",
            "summary": "Lifecycle notebook summary",
            "tags": ["alpha"],
            "namespace": "research",
        }
    )
    assert create_resp["ok"] is True
    scratchpad = create_resp["scratchpad"]
    scratch_id = scratchpad["scratch_id"]
    assert scratchpad["cells"] == []
    assert scratchpad["metadata"]["title"] == "Lifecycle Notebook"
    assert scratchpad["metadata"]["description"] == "Lifecycle notebook description"
    assert scratchpad["metadata"]["summary"] == "Lifecycle notebook summary"
    assert scratchpad["metadata"]["tags"] == ["alpha"]
    assert scratchpad["metadata"].get("cell_tags", []) == []
    assert scratchpad["namespace"] == "research"
    assert scratchpad.get("tags") == ["alpha"]
    assert "cell_tags" not in scratchpad

    append_resp = await _scratch_append_cell_impl(
        scratch_id,
        {
            "language": "json",
            "content": "{}",
            "metadata": {"note": "initial", "tags": ["payload"]},
        },
    )
    assert append_resp["ok"] is True
    cells = append_resp["scratchpad"]["cells"]
    assert len(cells) == 1
    assert cells[0]["index"] == 0
    assert cells[0]["language"] == "json"
    assert cells[0]["metadata"]["tags"] == ["payload"]
    assert cells[0]["tags"] == ["payload"]
    assert append_resp["scratchpad"]["tags"] == ["alpha", "payload"]
    assert append_resp["scratchpad"]["cell_tags"] == ["payload"]

    replace_resp = await _scratch_replace_cell_impl(
        scratch_id,
        0,
        {
            "language": "json",
            "content": "{\"updated\": true}",
        },
    )
    assert replace_resp["ok"] is True
    replaced_cell = replace_resp["scratchpad"]["cells"][0]
    assert replaced_cell["content"] == "{\"updated\": true}"
    assert "cell_tags" in replace_resp["scratchpad"]["metadata"]
    assert replace_resp["scratchpad"]["tags"] == ["alpha", "payload"]
    assert replace_resp["scratchpad"]["cells"][0]["tags"] == ["payload"]

    initialize_app(app)

    read_resp = await _scratch_read_impl(scratch_id)
    assert read_resp["ok"] is True
    assert read_resp["scratchpad"]["scratch_id"] == scratch_id
    assert read_resp["scratchpad"]["namespace"] == "research"
    assert set(read_resp["scratchpad"]["metadata"]["tags"]) == {"alpha", "payload"}
    assert read_resp["scratchpad"]["metadata"]["cell_tags"] == ["payload"]
    assert read_resp["scratchpad"]["tags"] == ["alpha", "payload"]
    assert read_resp["scratchpad"]["cell_tags"] == ["payload"]
    assert read_resp["scratchpad"]["cells"][0]["tags"] == ["payload"]

    list_resp = await _scratch_list_impl()
    assert list_resp["ok"] is True
    listing = list_resp["scratchpads"]
    assert any(entry["scratch_id"] == scratch_id for entry in listing)
    target_entry = next(entry for entry in listing if entry["scratch_id"] == scratch_id)
    assert target_entry["title"] == "Lifecycle Notebook"
    assert target_entry["description"] == "Lifecycle notebook description"
    assert "summary" not in target_entry
    assert "metadata" not in target_entry
    assert "tags" not in target_entry

    delete_resp = await _scratch_delete_impl(scratch_id)
    assert delete_resp["ok"] is True
    assert delete_resp["deleted"] is True

    missing_resp = await _scratch_read_impl(scratch_id)
    assert missing_resp["ok"] is False
    assert missing_resp["error"]["code"] == "NOT_FOUND"
