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
