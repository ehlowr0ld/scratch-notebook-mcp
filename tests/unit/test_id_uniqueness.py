from __future__ import annotations

import itertools
import uuid

import pytest

from scratch_notebook import load_config, models
from scratch_notebook.server import generate_unique_scratch_id
from scratch_notebook.storage import Storage


def _build_config(tmp_path, **overrides):
    environ = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
        "SCRATCH_NOTEBOOK_ENABLE_STDIO": "true",
        "SCRATCH_NOTEBOOK_ENABLE_HTTP": "false",
        "SCRATCH_NOTEBOOK_ENABLE_SSE": "false",
        "SCRATCH_NOTEBOOK_ENABLE_METRICS": "false",
        "SCRATCH_NOTEBOOK_ENABLE_AUTH": "false",
        "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
    }
    for key, value in overrides.items():
        environ[f"SCRATCH_NOTEBOOK_{key.upper()}"] = str(value)
    return load_config(argv=[], environ=environ)


def test_generate_unique_id_skips_collisions(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    collision_id = "collision"
    existing_pad = models.Scratchpad(scratch_id=collision_id, cells=[], metadata={})
    storage.create_scratchpad(existing_pad)

    candidates = itertools.chain([uuid.UUID(int=0), uuid.UUID(int=0), uuid.UUID(int=1)])

    def fake_uuid4():
        return next(candidates)

    monkeypatch.setattr(uuid, "uuid4", fake_uuid4)

    new_id = generate_unique_scratch_id(storage)

    assert new_id != collision_id
    assert storage.has_scratchpad(new_id) is False


def test_generate_unique_id_applies_prefix(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    uuid_value = uuid.UUID(int=12345)
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid_value)

    new_id = generate_unique_scratch_id(storage, prefix="scratch")

    assert new_id.startswith("scratch-")
    assert new_id.endswith(uuid_value.hex[:12])
    assert storage.has_scratchpad(new_id) is False
