from __future__ import annotations

from pathlib import Path

import pytest

from scratch_notebook import load_config
from scratch_notebook.config import ConfigError


def test_enable_metrics_requires_http(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(
            argv=[
                "--storage-dir",
                str(tmp_path / "storage"),
                "--enable-http",
                "false",
                "--enable-metrics",
                "true",
            ]
        )


def test_enable_metrics_with_http_allowed(tmp_path: Path) -> None:
    cfg = load_config(
        argv=[
            "--storage-dir",
            str(tmp_path / "storage"),
            "--enable-http",
            "true",
            "--enable-metrics",
            "true",
        ]
    )

    assert cfg.enable_http is True
    assert cfg.enable_metrics is True
