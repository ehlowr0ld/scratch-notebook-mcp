from __future__ import annotations

import json
import uuid

import pytest

from scratch_notebook import load_config, models
from scratch_notebook.errors import CAPACITY_LIMIT_REACHED, CONFIG_ERROR, INVALID_INDEX, NOT_FOUND, ScratchNotebookError
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


def _make_cell(index: int, *, language: str = "json", content: str = "{}", tags: list[str] | None = None) -> models.ScratchCell:
    metadata = {}
    if tags is not None:
        metadata["tags"] = tags
    return models.ScratchCell(
        cell_id=str(uuid.uuid4()),
        index=index,
        language=language,
        content=content,
        metadata=metadata,
    )


def _make_pad(*, cell_count: int = 0, metadata: dict[str, object] | None = None) -> models.Scratchpad:
    cells = [_make_cell(i) for i in range(cell_count)]
    return models.Scratchpad(scratch_id=str(uuid.uuid4()), cells=cells, metadata=metadata or {})


def test_create_and_read_roundtrip(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    metadata = {
        "title": "Design Notes",
        "description": "Persistent LanceDB payload",
        "summary": "Digest",
        "namespace": "research",
        "tags": ["lancedb", "persistence"],
    }
    pad = models.Scratchpad(
        scratch_id=str(uuid.uuid4()),
        cells=[
            models.ScratchCell(
                cell_id=str(uuid.uuid4()),
                index=0,
                language="json",
                content=json.dumps({"value": 1}),
                metadata={"tags": ["alpha"]},
            )
        ],
        metadata=metadata,
    )

    storage.create_scratchpad(pad)

    reloaded = storage.read_scratchpad(pad.scratch_id)

    assert reloaded.scratch_id == pad.scratch_id
    assert reloaded.metadata["title"] == "Design Notes"
    assert reloaded.metadata["namespace"] == "research"
    payload = reloaded.to_dict()
    assert payload["tags"] == ["lancedb", "persistence", "alpha"]
    assert payload["cell_tags"] == ["alpha"]
    assert payload["cells"][0]["tags"] == ["alpha"]
    assert reloaded.cells[0].metadata["tags"] == ["alpha"]
    payload = reloaded.to_dict()
    assert payload["namespace"] == "research"
    assert payload["tags"] == ["lancedb", "persistence", "alpha"]
    assert payload["cell_tags"] == ["alpha"]
    assert payload["cells"][0]["tags"] == ["alpha"]
    assert reloaded.metadata["cell_tags"] == ["alpha"]


def test_append_and_replace_roundtrip(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad(metadata={"tags": ["base"]})
    storage.create_scratchpad(pad)

    appended = storage.append_cell(pad.scratch_id, _make_cell(0, tags=["beta"]))
    assert len(appended.cells) == 1
    assert appended.cells[0].metadata["tags"] == ["beta"]

    replacement = models.ScratchCell(
        cell_id=appended.cells[0].cell_id,
        index=0,
        language="json",
        content=json.dumps({"value": 2}),
        metadata={"tags": ["gamma"]},
    )
    replaced = storage.replace_cell(pad.scratch_id, appended.cells[0].cell_id, replacement)

    assert replaced.cells[0].content == json.dumps({"value": 2})
    assert replaced.cells[0].metadata["tags"] == ["gamma"]


def test_replace_cell_with_new_index_reorders(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad(cell_count=3)
    storage.create_scratchpad(pad)
    target_id = pad.cells[0].cell_id

    replacement = models.ScratchCell(
        cell_id=target_id,
        index=0,
        language="json",
        content=json.dumps({"moved": True}),
        metadata={"tags": ["moved"]},
    )

    updated = storage.replace_cell(pad.scratch_id, target_id, replacement, new_index=2)

    assert [cell.index for cell in updated.cells] == [0, 1, 2]
    assert updated.cells[2].cell_id == target_id
    assert updated.cells[2].metadata["tags"] == ["moved"]


def test_list_scratchpads_returns_minimal_fields_sorted(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pads = []
    for title in ["delta", "alpha", "charlie"]:
        pad = models.Scratchpad(scratch_id=f"pad-{title}", cells=[], metadata={"title": title, "description": f"desc-{title}"})
        storage.create_scratchpad(pad)
        pads.append(pad)

    listing = storage.list_scratchpads()
    ids = [entry["scratch_id"] for entry in listing]
    assert ids == sorted(ids)
    for entry in listing:
        assert set(entry.keys()) == {"scratch_id", "title", "description", "namespace", "cell_count"}


def test_list_scratchpads_filters_by_namespace(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad_alpha = models.Scratchpad(scratch_id="pad-alpha", metadata={"namespace": "alpha"})
    pad_beta = models.Scratchpad(scratch_id="pad-beta", metadata={"namespace": "beta"})
    storage.create_scratchpad(pad_alpha)
    storage.create_scratchpad(pad_beta)

    filtered = storage.list_scratchpads(namespaces=["alpha"])

    assert [entry["scratch_id"] for entry in filtered] == ["pad-alpha"]


def test_list_scratchpads_filters_by_tags_including_cell_tags(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad_with_cell_tag = models.Scratchpad(
        scratch_id="pad-cell",
        metadata={"namespace": "tags"},
        cells=[
            models.ScratchCell(
                cell_id=str(uuid.uuid4()),
                index=0,
                language="json",
                content="{}",
                metadata={"tags": ["cell-only"]},
            )
        ],
    )
    pad_without_tag = models.Scratchpad(
        scratch_id="pad-plain",
        metadata={"namespace": "tags", "tags": ["plain"]},
    )

    storage.create_scratchpad(pad_with_cell_tag)
    storage.create_scratchpad(pad_without_tag)

    filtered = storage.list_scratchpads(tags=["cell-only"])

    assert [entry["scratch_id"] for entry in filtered] == ["pad-cell"]


def test_list_scratchpads_limit(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    for idx in range(3):
        storage.create_scratchpad(models.Scratchpad(scratch_id=f"pad-{idx}"))

    limited = storage.list_scratchpads(limit=1)

    assert len(limited) == 1


def test_storage_persists_across_reopen(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad(metadata={"title": "Transient"})
    storage.create_scratchpad(pad)

    # simulate process restart by building a new Storage instance
    storage = Storage(cfg)
    reloaded = storage.read_scratchpad(pad.scratch_id)
    assert reloaded.metadata["title"] == "Transient"


def test_schema_registry_roundtrip(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad()
    storage.create_scratchpad(pad)

    entry = storage.upsert_schema(
        pad.scratch_id,
        {
            "name": "payload",
            "description": "Primary payload schema",
            "schema": {"type": "object", "properties": {"value": {"type": "integer"}}},
        },
    )
    assert entry["name"] == "payload"
    assert entry["description"] == "Primary payload schema"
    assert entry["schema"]["type"] == "object"

    fetched = storage.get_schema(pad.scratch_id, entry["id"])
    assert fetched["id"] == entry["id"]

    listing = storage.list_schemas(pad.scratch_id)
    assert listing[0]["name"] == "payload"


def test_append_failure_does_not_mutate_state(tmp_path) -> None:
    cfg = _build_config(tmp_path, max_cell_bytes=4)
    storage = Storage(cfg)

    pad = _make_pad()
    storage.create_scratchpad(pad)

    with pytest.raises(ScratchNotebookError) as exc:
        storage.append_cell(pad.scratch_id, _make_cell(0, content="12345"))

    assert exc.value.code == CAPACITY_LIMIT_REACHED
    reloaded = storage.read_scratchpad(pad.scratch_id)
    assert len(reloaded.cells) == 0


def test_replace_missing_cell_raises(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad()
    storage.create_scratchpad(pad)

    with pytest.raises(ScratchNotebookError) as exc:
        storage.replace_cell(pad.scratch_id, "missing-cell", _make_cell(0))

    assert exc.value.code == NOT_FOUND


def test_get_missing_scratchpad_raises(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    with pytest.raises(ScratchNotebookError) as exc:
        storage.read_scratchpad("unknown")

    assert exc.value.code == NOT_FOUND


def test_schema_upsert_requires_name(tmp_path) -> None:
    cfg = _build_config(tmp_path)
    storage = Storage(cfg)

    pad = _make_pad()
    storage.create_scratchpad(pad)

    with pytest.raises(ScratchNotebookError) as exc:
        storage.upsert_schema(pad.scratch_id, {"schema": {"type": "object"}})

    assert exc.value.code == CONFIG_ERROR
