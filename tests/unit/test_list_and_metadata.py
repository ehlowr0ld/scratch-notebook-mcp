from __future__ import annotations

import uuid

import pytest

from scratch_notebook import models
from scratch_notebook.config import load_config
from scratch_notebook.storage import Storage


@pytest.fixture()
def storage(tmp_path):
    cfg = load_config(
        argv=[],
        environ={
            "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
            "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        },
    )
    return Storage(cfg)


def _make_pad(metadata: dict[str, object] | None = None, cells: int = 0) -> models.Scratchpad:
    base_metadata = {
        "title": "Notebook",
        "description": "Notebook description",
        "summary": "Notebook summary",
        "tags": ["demo"],
    }
    if metadata:
        base_metadata.update(metadata)
    pad = models.Scratchpad(
        scratch_id=str(uuid.uuid4()),
        metadata=base_metadata,
        cells=[
            models.ScratchCell.from_dict(
                {
                    "cell_id": str(uuid.uuid4()),
                    "index": index,
                    "language": "json",
                    "content": "{}",
                    "metadata": {"tags": [f"cell-tag-{index}"]},
                }
            )
            for index in range(cells)
        ],
    )
    return pad


def test_listing_exposes_metadata_and_cell_count(storage: Storage) -> None:
    pad = _make_pad(metadata={"description": "Integration payload"}, cells=2)
    storage.create_scratchpad(pad)

    listing = storage.list_scratchpads()

    assert listing[0]["scratch_id"] == pad.scratch_id
    assert listing[0]["cell_count"] == 2
    assert listing[0]["title"] == "Notebook"
    assert listing[0]["description"] == "Integration payload"
    assert "summary" not in listing[0]
    assert "tags" not in listing[0]
    assert "metadata" not in listing[0]


def test_listing_updates_after_deletion(storage: Storage) -> None:
    pad_one = _make_pad()
    pad_two = _make_pad()
    storage.create_scratchpad(pad_one)
    storage.create_scratchpad(pad_two)

    storage.delete_scratchpad(pad_one.scratch_id)

    listing = storage.list_scratchpads()
    ids = {entry["scratch_id"] for entry in listing}

    assert ids == {pad_two.scratch_id}
    assert all("title" in entry and "description" in entry for entry in listing)
    assert all("summary" not in entry for entry in listing)
    assert all(
        entry["cell_count"] == len(storage.read_scratchpad(entry["scratch_id"]).cells)
        for entry in listing
    )
