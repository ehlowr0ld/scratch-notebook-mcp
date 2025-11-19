from __future__ import annotations

import uuid

import pytest

from scratch_notebook import models
from scratch_notebook.config import load_config
from scratch_notebook.storage import Storage


@pytest.fixture()
def storage(tmp_path):
    config = load_config(
        argv=[],
        environ={
            "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
            "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        },
    )
    return Storage(config)


def _make_pad(
    *,
    scratch_id: str | None = None,
    namespace: str | None = None,
    pad_tags: list[str] | None = None,
    cell_tags: list[list[str]] | None = None,
) -> models.Scratchpad:
    scratch_id = scratch_id or uuid.uuid4().hex
    metadata: dict[str, object] = {}
    if namespace:
        metadata["namespace"] = namespace
    if pad_tags is not None:
        metadata["tags"] = pad_tags
    cells: list[models.ScratchCell] = []
    if cell_tags:
        for index, tags in enumerate(cell_tags):
            cells.append(
                models.ScratchCell(
                    cell_id=uuid.uuid4().hex,
                    index=index,
                    language="json",
                    content="{}",
                    metadata={"tags": tags},
                )
            )
    return models.Scratchpad(scratch_id=scratch_id, cells=cells, metadata=metadata)


def test_list_tags_returns_deduplicated_sets(storage: Storage) -> None:
    pad_one = _make_pad(namespace="alpha", pad_tags=["project", "shared"], cell_tags=[["cell-a"], ["shared"]])
    pad_two = _make_pad(namespace="beta", pad_tags=["shared", "ops"], cell_tags=[["cell-b", "ops"]])
    storage.create_scratchpad(pad_one)
    storage.create_scratchpad(pad_two)

    result = storage.list_tags()

    assert sorted(result["scratchpad_tags"]) == ["cell-a", "cell-b", "ops", "project", "shared"]
    assert sorted(result["cell_tags"]) == ["cell-a", "cell-b", "ops", "shared"]


def test_list_tags_filters_by_namespace(storage: Storage) -> None:
    pad_one = _make_pad(namespace="alpha", pad_tags=["alpha-only"], cell_tags=[["alpha-cell"]])
    pad_two = _make_pad(namespace="beta", pad_tags=["beta-only"], cell_tags=[["beta-cell"]])
    storage.create_scratchpad(pad_one)
    storage.create_scratchpad(pad_two)

    result = storage.list_tags(namespaces=["alpha"])

    assert result["scratchpad_tags"] == sorted(["alpha-cell", "alpha-only"])
    assert result["cell_tags"] == ["alpha-cell"]
