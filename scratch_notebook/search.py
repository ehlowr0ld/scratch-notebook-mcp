from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any, Sequence

from .config import Config
from .errors import CONFIG_ERROR, ScratchNotebookError
from .logging import get_logger
from .models import ScratchCell, Scratchpad, merge_tags, normalize_tags
from .storage_lancedb import ScratchpadSnapshot, Storage

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class EmbeddingDocument:
    text: str
    snippet: str
    namespace: str | None
    tags: list[str]
    cell_id: str | None
    cell_index: int
    title: str | None
    description: str | None
    summary: str | None


class HashingEmbedder:
    name = "debug-hash"
    dimension = 64

    def ensure_loaded(self) -> None:  # pragma: no cover - nothing to load
        return

    def embed(self, texts: Sequence[str], *, batch_size: int, device: str | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8", "ignore")).digest()
            vector: list[float] = []
            for index in range(self.dimension):
                byte = digest[index % len(digest)]
                # map byte (0-255) to [-1, 1]
                vector.append((byte / 127.5) - 1.0)
            vectors.append(vector)
        return vectors


class SentenceTransformerBackend:
    def __init__(self, model_name: str, device: str) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None
        self._dimension: int | None = None

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self.ensure_loaded()
        assert self._dimension is not None
        return self._dimension

    def ensure_loaded(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # lazy import

            self._model = SentenceTransformer(self._model_name, device=self._device)
            self._dimension = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: Sequence[str], *, batch_size: int, device: str | None = None) -> list[list[float]]:
        self.ensure_loaded()
        assert self._model is not None
        vectors = self._model.encode(
            list(texts),
            batch_size=batch_size,
            convert_to_numpy=True,
            device=self._device,
            normalize_embeddings=True,
        )
        return vectors.astype("float32").tolist()


class SearchService:
    def __init__(self, storage: Storage, config: Config) -> None:
        self._storage = storage
        self._config = config
        self._enabled = config.enable_semantic_search
        self._backend: HashingEmbedder | SentenceTransformerBackend | None = None
        self._backend_lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _select_backend(self) -> HashingEmbedder | SentenceTransformerBackend:
        model_name = self._config.embedding_model
        if model_name.strip().lower().startswith("debug"):
            return HashingEmbedder()
        return SentenceTransformerBackend(model_name=model_name, device=self._config.embedding_device)

    async def _get_backend(self) -> HashingEmbedder | SentenceTransformerBackend:
        if self._backend is not None:
            return self._backend
        async with self._backend_lock:
            if self._backend is None:
                backend = self._select_backend()
                backend.ensure_loaded()
                if isinstance(backend, SentenceTransformerBackend):
                    LOGGER.info("Semantic search using %s (dimension=%d)", backend.name, backend.dimension)
                else:
                    LOGGER.info("Semantic search using debug hashing backend (dimension=%d)", backend.dimension)
                self._backend = backend
        return self._backend  # type: ignore[return-value]

    async def reindex_pad(self, pad: Scratchpad) -> None:
        if not self._enabled:
            return
        backend = await self._get_backend()
        documents = self._build_documents(pad)
        if not documents:
            dimension = getattr(backend, "dimension")
            self._storage.replace_embeddings(pad.scratch_id, [], dimension=dimension)
            return
        texts = [doc.text for doc in documents]
        vectors = await asyncio.to_thread(
            backend.embed,
            texts,
            batch_size=self._config.embedding_batch_size,
            device=self._config.embedding_device,
        )
        records: list[dict[str, Any]] = []
        for doc, vector in zip(documents, vectors):
            records.append(
                {
                    "cell_id": doc.cell_id,
                    "cell_index": doc.cell_index,
                    "namespace": doc.namespace or "",
                    "tags": doc.tags,
                    "title": doc.title,
                    "description": doc.description,
                    "summary": doc.summary,
                    "snippet": doc.snippet,
                    "embedding": vector,
                }
            )
        self._storage.replace_embeddings(pad.scratch_id, records, dimension=len(vectors[0]))

    async def delete_pad_embeddings(self, scratch_id: str) -> None:
        if not self._enabled:
            return
        dimension = self._storage.get_embedding_dimension()
        if dimension is None:
            backend = await self._get_backend()
            dimension = backend.dimension
        self._storage.replace_embeddings(scratch_id, [], dimension=dimension)

    async def search(
        self,
        query: str,
        *,
        namespaces: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if not self._enabled:
            raise ScratchNotebookError(CONFIG_ERROR, "Semantic search is disabled")
        backend = await self._get_backend()
        safe_limit = max(1, min(limit, 50))
        [query_vector] = await asyncio.to_thread(
            backend.embed,
            [query],
            batch_size=self._config.embedding_batch_size,
            device=self._config.embedding_device,
        )
        namespace_filter = {ns.strip() for ns in (namespaces or []) if ns and ns.strip()}
        tag_filter = {tag.strip() for tag in (tags or []) if tag and tag.strip()}
        hits = self._storage.search_embeddings(
            query_vector,
            limit=safe_limit,
            namespaces=namespace_filter or None,
            tags=tag_filter or None,
        )
        formatted: list[dict[str, Any]] = []
        for row in hits:
            distance = float(row.get("_distance", 0.0))
            score = max(0.0, min(1.0, 1.0 - distance))
            formatted.append(
                {
                    "scratch_id": row.get("scratch_id"),
                    "cell_id": row.get("cell_id"),
                    "namespace": row.get("namespace"),
                    "tags": row.get("tags") or [],
                    "score": score,
                    "snippet": row.get("snippet") or "",
                }
            )
        backend_name = backend.name if isinstance(backend, SentenceTransformerBackend) else backend.name
        return {"ok": True, "hits": formatted, "embedder": backend_name}

    def _build_documents(self, pad: Scratchpad) -> list[EmbeddingDocument]:
        documents: list[EmbeddingDocument] = []
        namespace = (pad.metadata or {}).get("namespace") if isinstance(pad.metadata, dict) else None
        pad_tags = normalize_tags((pad.metadata or {}).get("tags")) if isinstance(pad.metadata, dict) else []
        title = None
        description = None
        summary = None
        if isinstance(pad.metadata, dict):
            raw_title = pad.metadata.get("title")
            title = raw_title.strip() if isinstance(raw_title, str) else None
            raw_description = pad.metadata.get("description")
            description = raw_description.strip() if isinstance(raw_description, str) else None
            raw_summary = pad.metadata.get("summary")
            summary = raw_summary.strip() if isinstance(raw_summary, str) else None
        pad_text_parts = [part for part in [title, description, summary] if part]
        for cell in pad.cells:
            pad_text_parts.append(cell.content.strip())
        pad_text = "\n".join(filter(None, pad_text_parts))
        pad_snippet = self._build_snippet(pad_text, metadata_parts=[title, description, summary])
        documents.append(
            EmbeddingDocument(
                text=pad_text or "",
                snippet=pad_snippet,
                namespace=namespace,
                tags=pad_tags,
                cell_id=None,
                cell_index=-1,
                title=title,
                description=description,
                summary=summary,
            )
        )
        for cell in pad.cells:
            documents.append(self._build_cell_document(pad, cell, namespace, pad_tags, title, description, summary))
        return documents

    def _build_cell_document(
        self,
        pad: Scratchpad,
        cell: ScratchCell,
        namespace: str | None,
        pad_tags: list[str],
        title: str | None,
        description: str | None,
        summary: str | None,
    ) -> EmbeddingDocument:
        cell_tags = normalize_tags(cell.metadata.get("tags") if cell.metadata else None)
        aggregate_tags = merge_tags(pad_tags, cell_tags)
        cell_text_parts = [cell.content.strip()]
        cell_text = "\n".join(filter(None, cell_text_parts))
        snippet = self._build_snippet(cell_text, metadata_parts=[title, description, summary])
        return EmbeddingDocument(
            text=cell_text or "",
            snippet=snippet,
            namespace=namespace,
            tags=aggregate_tags,
            cell_id=cell.cell_id,
            cell_index=cell.index,
            title=title,
            description=description,
            summary=summary,
        )

    def _build_snippet(self, text: str, *, metadata_parts: Sequence[str] | None = None) -> str:
        parts: list[str] = []
        for value in metadata_parts or []:
            if value:
                parts.append(value.strip())
        trimmed_content = text.strip()
        if trimmed_content:
            parts.append(trimmed_content)
        combined = " ".join(part for part in parts if part)
        if len(combined) <= 240:
            return combined
        return combined[:237] + "..."
