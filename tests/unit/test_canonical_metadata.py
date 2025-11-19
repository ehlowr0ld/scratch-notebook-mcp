from __future__ import annotations

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_create_impl,
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


@pytest.mark.asyncio
async def test_create_returns_trimmed_canonical_fields(app) -> None:
    resp = await _scratch_create_impl(
        metadata={"title": "  Title  ", "description": " Description ", "summary": "  Summary  "}
    )

    assert resp["ok"] is True
    pad = resp["scratchpad"]
    assert pad["title"] == "Title"
    assert pad["description"] == "Description"
    assert pad["summary"] == "Summary"
    assert pad["metadata"]["title"] == "Title"
    assert pad["metadata"]["description"] == "Description"
    assert pad["metadata"]["summary"] == "Summary"


@pytest.mark.asyncio
async def test_read_persists_canonical_fields_across_restart(app) -> None:
    create_resp = await _scratch_create_impl(
        metadata={"title": "Notebook", "description": "Primary notebook", "summary": "Key notes"}
    )
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    initialize_app(app)

    read_resp = await _scratch_read_impl(scratch_id)
    assert read_resp["ok"] is True
    pad = read_resp["scratchpad"]
    assert pad["title"] == "Notebook"
    assert pad["description"] == "Primary notebook"
    assert pad["summary"] == "Key notes"
    assert pad["metadata"]["title"] == "Notebook"
    assert pad["metadata"]["description"] == "Primary notebook"
    assert pad["metadata"]["summary"] == "Key notes"


@pytest.mark.asyncio
async def test_list_returns_null_when_canonical_metadata_missing(app) -> None:
    first = await _scratch_create_impl()
    second = await _scratch_create_impl(metadata={"title": "Other pad", "description": "Other description"})

    list_resp = await _scratch_list_impl()
    assert list_resp["ok"] is True
    entries = {entry["scratch_id"]: entry for entry in list_resp["scratchpads"]}

    first_entry = entries[first["scratchpad"]["scratch_id"]]
    assert first_entry["title"] is None
    assert first_entry["description"] is None
    assert "summary" not in first_entry

    second_entry = entries[second["scratchpad"]["scratch_id"]]
    assert second_entry["title"] == "Other pad"
    assert second_entry["description"] == "Other description"
