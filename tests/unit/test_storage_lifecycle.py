from __future__ import annotations

import uuid

import pytest

from scratch_notebook import models
from scratch_notebook.config import load_config
from scratch_notebook.errors import INVALID_ID, ScratchNotebookError
from scratch_notebook.storage import Storage


def make_pad(cell_count: int = 1) -> models.Scratchpad:
    scratch_id = str(uuid.uuid4())
    cells = [
        models.ScratchCell.from_dict(
            {
                "cell_id": str(uuid.uuid4()),
                "index": i,
                "language": "json",
                "content": "{}",
            }
        )
        for i in range(cell_count)
    ]
    return models.Scratchpad(scratch_id=scratch_id, cells=cells, metadata={"title": f"Pad {scratch_id}"})


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


def test_create_and_read_scratchpad(storage: Storage) -> None:
    pad = make_pad()
    storage.create_scratchpad(pad)

    loaded = storage.read_scratchpad(pad.scratch_id)

    assert loaded.to_dict() == pad.to_dict()


def test_list_scratchpads_returns_metadata(storage: Storage) -> None:
    pads = [make_pad() for _ in range(3)]
    for pad in pads:
        storage.create_scratchpad(pad)

    listing = storage.list_scratchpads()
    listed_ids = {item["scratch_id"] for item in listing}

    assert {pad.scratch_id for pad in pads} == listed_ids


def test_delete_scratchpad(storage: Storage) -> None:
    pad = make_pad()
    storage.create_scratchpad(pad)

    deleted = storage.delete_scratchpad(pad.scratch_id)
    assert deleted is True

    with pytest.raises(ScratchNotebookError):
        storage.read_scratchpad(pad.scratch_id)


def test_delete_missing_scratchpad_is_idempotent(storage: Storage) -> None:
    deleted = storage.delete_scratchpad(str(uuid.uuid4()))
    assert deleted is False


def test_invalid_identifier_rejected(storage: Storage) -> None:
    pad = make_pad()
    pad.scratch_id = "../bad"

    with pytest.raises(ScratchNotebookError) as exc:
        storage.create_scratchpad(pad)

    assert exc.value.code == INVALID_ID
