from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from scratch_notebook import models
from scratch_notebook.config import load_config
from scratch_notebook.eviction import PreemptiveSweeper
from scratch_notebook.storage import Storage


def _make_storage(tmp_path, **overrides: int | str) -> Storage:
    environ: dict[str, str] = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
        "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        "SCRATCH_NOTEBOOK_EVICTION_POLICY": "preempt",
        "SCRATCH_NOTEBOOK_PREEMPT_AGE": "10s",
        "SCRATCH_NOTEBOOK_PREEMPT_INTERVAL": "10s",
    }
    for key, value in overrides.items():
        environ[f"SCRATCH_NOTEBOOK_{key.upper()}"] = str(value)
    config = load_config(argv=[], environ=environ)
    return Storage(config)


def _pad(identifier: str) -> models.Scratchpad:
    return models.Scratchpad(scratch_id=identifier, cells=[], metadata={})


def _set_last_access(storage: Storage, scratch_id: str, when: datetime) -> None:
    with storage._lock:  # type: ignore[attr-defined]
        row = storage._fetch_row(scratch_id)  # type: ignore[attr-defined]
        assert row is not None
        storage._delete_row(scratch_id)  # type: ignore[attr-defined]
        row["last_access_at"] = when
        row["updated_at"] = when
        storage._table.add([row])  # type: ignore[attr-defined]


def test_evict_stale_respects_threshold(tmp_path) -> None:
    storage = _make_storage(tmp_path)

    storage.create_scratchpad(_pad("pad_old"))
    storage.create_scratchpad(_pad("pad_fresh"))

    now = datetime.now(timezone.utc)
    _set_last_access(storage, "pad_old", now - timedelta(minutes=5))
    _set_last_access(storage, "pad_fresh", now)

    evicted = storage.evict_stale(timedelta(minutes=1))

    assert evicted == ["pad_old"]
    assert not storage.has_scratchpad("pad_old")
    assert storage.has_scratchpad("pad_fresh")


def test_preemptive_sweeper_removes_stale_entries(tmp_path) -> None:
    storage = _make_storage(tmp_path)

    storage.create_scratchpad(_pad("pad_old"))
    now = datetime.now(timezone.utc)
    _set_last_access(storage, "pad_old", now - timedelta(minutes=5))

    sweeper = PreemptiveSweeper(storage, age=timedelta(seconds=1), interval=timedelta(seconds=0.1))
    sweeper.start()

    try:
        deadline = time.time() + 2.0
        while storage.has_scratchpad("pad_old") and time.time() < deadline:
            time.sleep(0.05)
    finally:
        sweeper.stop()

    assert not storage.has_scratchpad("pad_old")
