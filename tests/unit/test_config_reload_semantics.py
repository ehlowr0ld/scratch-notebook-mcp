from __future__ import annotations

from pathlib import Path

import pytest

from scratch_notebook.config import ConfigError, hot_reload_config, load_config


def test_config_changes_require_restart(tmp_path: Path) -> None:
    cfg_one = load_config(
        argv=[],
        environ={
            "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path / "one"),
            "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        },
    )
    cfg_two = load_config(
        argv=[],
        environ={
            "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path / "two"),
            "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        },
    )

    assert cfg_one.storage_dir != cfg_two.storage_dir

    with pytest.raises(ConfigError):
        hot_reload_config(cfg_one, environ={"SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path / "three")})
