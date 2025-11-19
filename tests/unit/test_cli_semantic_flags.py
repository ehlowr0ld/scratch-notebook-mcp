from __future__ import annotations

from pathlib import Path

import pytest

from scratch_notebook.config import (
    ConfigError,
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_DEVICE,
    DEFAULT_EMBEDDING_MODEL,
    load_config,
)


def test_semantic_search_defaults_enabled(tmp_path: Path) -> None:
    cfg = load_config(argv=[], environ={"SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path)})

    assert cfg.enable_semantic_search is True
    assert cfg.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert cfg.embedding_device == DEFAULT_EMBEDDING_DEVICE
    assert cfg.embedding_batch_size == DEFAULT_EMBEDDING_BATCH_SIZE


def test_cli_overrides_semantic_search_flags(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    argv = [
        "--storage-dir",
        str(storage_dir),
        "--enable-semantic-search",
        "false",
        "--embedding-model",
        "acme/model",
        "--embedding-device",
        "cuda",
        "--embedding-batch-size",
        "8",
    ]

    cfg = load_config(argv=argv)

    assert cfg.enable_semantic_search is False
    assert cfg.embedding_model == "acme/model"
    assert cfg.embedding_device == "cuda"
    assert cfg.embedding_batch_size == 8


def test_invalid_embedding_batch_size_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(
            argv=[
                "--storage-dir",
                str(tmp_path / "storage"),
                "--embedding-batch-size",
                "not-an-int",
            ]
        )
