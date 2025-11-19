from __future__ import annotations

import uuid

import pytest

from scratch_notebook import models
from scratch_notebook.config import load_config
from scratch_notebook.errors import CAPACITY_LIMIT_REACHED, ScratchNotebookError
from scratch_notebook.storage import Storage


def _make_storage(tmp_path, **overrides: int | str) -> Storage:
    environ: dict[str, str] = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
        "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
    }
    for key, value in overrides.items():
        environ[f"SCRATCH_NOTEBOOK_{key.upper()}"] = str(value)
    config = load_config(argv=[], environ=environ)
    return Storage(config)


def _empty_pad(identifier: str) -> models.Scratchpad:
    return models.Scratchpad(scratch_id=identifier, cells=[], metadata={})


def _make_cell(content: str = "{}") -> models.ScratchCell:
    return models.ScratchCell(
        cell_id=str(uuid.uuid4()),
        index=0,
        language="json",
        content=content,
    )


def test_max_scratchpads_limit_fail_policy(tmp_path) -> None:
    storage = _make_storage(tmp_path, max_scratchpads=1, eviction_policy="fail")

    storage.create_scratchpad(_empty_pad("pad_a"))

    with pytest.raises(ScratchNotebookError) as exc:
        storage.create_scratchpad(_empty_pad("pad_b"), overwrite=False)

    assert exc.value.code == CAPACITY_LIMIT_REACHED


def test_max_cells_per_pad_limit(tmp_path) -> None:
    storage = _make_storage(tmp_path, max_cells_per_pad=1)
    scratch_id = "pad_cells"
    storage.create_scratchpad(_empty_pad(scratch_id))

    storage.append_cell(scratch_id, _make_cell())

    with pytest.raises(ScratchNotebookError) as exc:
        storage.append_cell(scratch_id, _make_cell())

    assert exc.value.code == CAPACITY_LIMIT_REACHED


def test_max_cell_bytes_limit(tmp_path) -> None:
    storage = _make_storage(tmp_path, max_cell_bytes=8)
    scratch_id = "pad_bytes"
    storage.create_scratchpad(_empty_pad(scratch_id))

    storage.append_cell(scratch_id, _make_cell("{}"))

    with pytest.raises(ScratchNotebookError) as exc:
        storage.append_cell(scratch_id, _make_cell("{" + "x" * 20 + "}"))

    assert exc.value.code == CAPACITY_LIMIT_REACHED
