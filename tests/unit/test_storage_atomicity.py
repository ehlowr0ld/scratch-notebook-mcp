from __future__ import annotations

import uuid

import pytest

from scratch_notebook import load_config, models
from scratch_notebook.storage import Storage, StorageError
from scratch_notebook.errors import CAPACITY_LIMIT_REACHED


def _build_config(tmp_path, **overrides):
    environ = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
        "SCRATCH_NOTEBOOK_ENABLE_STDIO": "true",
        "SCRATCH_NOTEBOOK_ENABLE_HTTP": "false",
        "SCRATCH_NOTEBOOK_ENABLE_SSE": "false",
        "SCRATCH_NOTEBOOK_ENABLE_METRICS": "false",
        "SCRATCH_NOTEBOOK_ENABLE_AUTH": "false",
        "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        "SCRATCH_NOTEBOOK_EVICTION_POLICY": "fail",
    }
    for key, value in overrides.items():
        environ[f"SCRATCH_NOTEBOOK_{key.upper()}"] = str(value)
    return load_config(argv=[], environ=environ)


def _make_cell(index: int = 0, content: str = "{}", language: str = "json") -> models.ScratchCell:
    return models.ScratchCell(
        cell_id=str(uuid.uuid4()),
        index=index,
        language=language,
        content=content,
    )


def _make_pad(cell_count: int = 0) -> models.Scratchpad:
    cells = [_make_cell(index=i) for i in range(cell_count)]
    return models.Scratchpad(scratch_id=str(uuid.uuid4()), cells=cells, metadata={})


def test_append_does_not_mutate_on_cell_limit(tmp_path) -> None:
    cfg = _build_config(tmp_path, max_cells_per_pad=1)
    storage = Storage(cfg)

    pad = _make_pad(cell_count=1)
    storage.create_scratchpad(pad)

    with pytest.raises(StorageError) as exc:
        storage.append_cell(pad.scratch_id, _make_cell())

    assert exc.value.code == CAPACITY_LIMIT_REACHED

    reloaded = storage.read_scratchpad(pad.scratch_id)
    assert len(reloaded.cells) == 1


def test_append_respects_cell_size_limit(tmp_path) -> None:
    cfg = _build_config(tmp_path, max_cell_bytes=4)
    storage = Storage(cfg)

    pad = _make_pad(cell_count=0)
    storage.create_scratchpad(pad)

    with pytest.raises(StorageError) as exc:
        storage.append_cell(pad.scratch_id, _make_cell(content="12345"))

    assert exc.value.code == CAPACITY_LIMIT_REACHED
    reloaded = storage.read_scratchpad(pad.scratch_id)
    assert len(reloaded.cells) == 0


def test_capacity_violation_does_not_create_new_pad(tmp_path) -> None:
    cfg = _build_config(tmp_path, max_scratchpads=1)
    storage = Storage(cfg)

    first = _make_pad()
    storage.create_scratchpad(first)

    second = _make_pad()
    with pytest.raises(StorageError) as exc:
        storage.create_scratchpad(second, overwrite=False)

    assert exc.value.code == CAPACITY_LIMIT_REACHED

    pads = storage.list_scratchpads()
    assert len(pads) == 1
    assert pads[0]["scratch_id"] == first.scratch_id
    # ensure second file does not exist
    assert storage.has_scratchpad(second.scratch_id) is False
