from __future__ import annotations

import time

from scratch_notebook import models
from scratch_notebook.config import load_config
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


def _pad(identifier: str) -> models.Scratchpad:
    return models.Scratchpad(scratch_id=identifier, cells=[], metadata={})


def test_discard_policy_evicts_oldest_pad(tmp_path) -> None:
    storage = _make_storage(tmp_path, max_scratchpads=1, eviction_policy="discard")

    storage.create_scratchpad(_pad("pad_a"))
    storage.create_scratchpad(_pad("pad_b"))

    evicted = storage.pop_recent_evictions()
    assert evicted == ["pad_a"]
    assert storage.has_scratchpad("pad_b")
    assert not storage.has_scratchpad("pad_a")


def test_discard_policy_uses_last_access_time(tmp_path) -> None:
    storage = _make_storage(tmp_path, max_scratchpads=2, eviction_policy="discard")

    storage.create_scratchpad(_pad("pad_a"))
    storage.create_scratchpad(_pad("pad_b"))

    # Refresh pad_a so it becomes the most recently accessed scratchpad.
    storage.read_scratchpad("pad_a")
    time.sleep(0.05)

    storage.create_scratchpad(_pad("pad_c"))

    evicted = storage.pop_recent_evictions()
    assert evicted == ["pad_b"]
    assert storage.has_scratchpad("pad_a")
    assert storage.has_scratchpad("pad_c")
    assert not storage.has_scratchpad("pad_b")


def test_pop_recent_evictions_clears_queue(tmp_path) -> None:
    storage = _make_storage(tmp_path, max_scratchpads=1)

    storage.create_scratchpad(_pad("pad_a"))
    storage.create_scratchpad(_pad("pad_b"))
    assert storage.pop_recent_evictions() == ["pad_a"]
    assert storage.pop_recent_evictions() == []
