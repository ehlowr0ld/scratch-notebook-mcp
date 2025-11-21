from __future__ import annotations

import uuid

import pytest

from scratch_notebook import load_config, models
from scratch_notebook.search import SearchService
from scratch_notebook.storage import Storage


@pytest.fixture()
def search_dependencies(tmp_path) -> tuple[SearchService, Storage]:
    config = load_config(
        argv=[],
        environ={
            "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
            "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        },
    )
    storage = Storage(config)
    service = SearchService(storage=storage, config=config)
    return service, storage


@pytest.mark.asyncio
async def test_reindex_and_search_returns_hits(search_dependencies: tuple[SearchService, Storage]) -> None:
    search_service, storage = search_dependencies
    pad = models.Scratchpad(
        scratch_id=str(uuid.uuid4()),
        metadata={
            "title": "Greeter",
            "description": "Examples for greeting people",
            "namespace": "examples",
            "tags": ["greetings"],
        },
        cells=[
            models.ScratchCell.from_dict(
                {
                    "cell_id": str(uuid.uuid4()),
                    "index": 0,
                    "language": "md",
                    "content": "Hello world!",
                    "metadata": {"tags": ["intro"]},
                }
            ),
            models.ScratchCell.from_dict(
                {
                    "cell_id": str(uuid.uuid4()),
                    "index": 1,
                    "language": "md",
                    "content": "Goodbye folks",
                    "metadata": {"tags": ["outro"]},
                }
            ),
        ],
    )
    storage.create_scratchpad(pad)
    await search_service.reindex_pad(pad)

    response = await search_service.search("hello", namespaces=["examples"], limit=5)
    assert response["ok"] is True
    hits = response["hits"]
    assert hits, "Expected at least one semantic hit"
    assert any(hit["scratch_id"] == pad.scratch_id for hit in hits)
    assert any("hello" in hit["snippet"].lower() for hit in hits if hit["cell_id"] is not None)
    assert any("greeter" in hit["snippet"].lower() for hit in hits)
    assert any("examples for greeting people" in hit["snippet"].lower() for hit in hits if hit["cell_id"] is not None)

    filtered = await search_service.search("hello", namespaces=["examples"], tags=["intro"], limit=5)
    assert filtered["hits"] and filtered["hits"][0]["cell_id"] == pad.cells[0].cell_id


@pytest.mark.asyncio
async def test_delete_pad_embeddings_removes_entries(search_dependencies: tuple[SearchService, Storage]) -> None:
    search_service, storage = search_dependencies
    pad = models.Scratchpad(
        scratch_id=str(uuid.uuid4()),
        metadata={"title": "Deletion", "namespace": "cleanup"},
        cells=[],
    )
    storage.create_scratchpad(pad)
    await search_service.reindex_pad(pad)

    dimension = storage.get_embedding_dimension()
    assert dimension is not None

    await search_service.delete_pad_embeddings(pad.scratch_id)
    hits = storage.search_embeddings([0.0] * dimension, limit=5)
    assert hits == []


def test_search_embeddings_prefilter_applies_before_limit(monkeypatch, tmp_path) -> None:
    config = load_config(
        argv=[],
        environ={
            "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
            "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        },
    )
    storage = Storage(config)

    class _FakeQuery:
        def __init__(self) -> None:
            self.prefilter_flag = False
            self.where_clause: str | None = None
            self.limit_value: int | None = None

        def metric(self, _metric: str):
            return self

        def where(self, clause: str, prefilter: bool = False):
            self.where_clause = clause
            self.prefilter_flag = prefilter
            return self

        def limit(self, value: int):
            self.limit_value = value
            return self

        def to_list(self):
            if self.prefilter_flag and self.where_clause and "team-b" in self.where_clause:
                return [{"scratch_id": "pad-b", "namespace": "team-b", "tags": []}]
            return [{"scratch_id": "pad-a", "namespace": "team-a", "tags": []}]

    class _FakeEmbeddingTable:
        def __init__(self) -> None:
            self.last_query: _FakeQuery | None = None

        def search(self, *_args, **_kwargs):
            self.last_query = _FakeQuery()
            return self.last_query

    fake_table = _FakeEmbeddingTable()
    storage._embeddings_table = fake_table

    def _fake_ensure(self, dimension=None):  # noqa: ANN001
        return fake_table

    monkeypatch.setattr(Storage, "_ensure_embedding_table", _fake_ensure)

    hits = storage.search_embeddings([0.1, 0.2, 0.3], limit=1, namespaces={"team-b"})

    assert hits and hits[0]["namespace"] == "team-b"
    assert fake_table.last_query is not None
    assert fake_table.last_query.prefilter_flag is True
    assert fake_table.last_query.limit_value == 1
    assert fake_table.last_query.where_clause and "team-b" in fake_table.last_query.where_clause
