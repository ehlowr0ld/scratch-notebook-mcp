from __future__ import annotations

import json

import pytest

from scratch_notebook import load_config
from scratch_notebook.server import (
    initialize_app,
    _scratch_append_cell_impl,
    _scratch_create_impl,
    _scratch_list_tags_impl,
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


async def _create_scratchpad(metadata: dict[str, object], cell_tags: list[list[str]]) -> str:
    create_resp = await _scratch_create_impl(metadata=metadata)
    assert create_resp["ok"] is True
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    for tags in cell_tags:
        append_resp = await _scratch_append_cell_impl(
            scratch_id,
            {
                "language": "json",
                "content": json.dumps({"tags": tags}),
                "metadata": {"tags": tags},
            },
        )
        assert append_resp["ok"] is True
    return scratch_id


@pytest.mark.asyncio
async def test_list_tags_returns_deduplicated_sets(app) -> None:
    await _create_scratchpad(
        metadata={"namespace": "alpha", "tags": ["project", "shared"]},
        cell_tags=[["cell-a"], ["shared"]],
    )
    await _create_scratchpad(
        metadata={"namespace": "beta", "tags": ["ops", "shared"]},
        cell_tags=[["cell-b"]],
    )

    resp = await _scratch_list_tags_impl()
    assert resp["ok"] is True
    assert resp["scratchpad_tags"] == ["cell-a", "cell-b", "ops", "project", "shared"]
    assert resp["cell_tags"] == ["cell-a", "cell-b", "shared"]


@pytest.mark.asyncio
async def test_list_tags_namespace_filter(app) -> None:
    await _create_scratchpad(
        metadata={"namespace": "alpha", "tags": ["alpha-only"]},
        cell_tags=[["alpha-cell"]],
    )
    await _create_scratchpad(
        metadata={"namespace": "beta", "tags": ["beta-only"]},
        cell_tags=[["beta-cell"]],
    )

    resp = await _scratch_list_tags_impl(namespaces=["alpha"])
    assert resp["ok"] is True
    assert resp["scratchpad_tags"] == ["alpha-cell", "alpha-only"]
    assert resp["cell_tags"] == ["alpha-cell"]
