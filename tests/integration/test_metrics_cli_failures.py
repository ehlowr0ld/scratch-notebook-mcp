from __future__ import annotations

import pytest

from scratch_notebook import load_config
from scratch_notebook.config import ConfigError
from scratch_notebook.server import (
    _scratch_create_impl,
    initialize_app,
    shutdown_app,
)


def test_metrics_requires_http_integration(tmp_path) -> None:
    with pytest.raises(ConfigError):
        load_config(
            argv=[
                "--storage-dir",
                str(tmp_path),
                "--enable-stdio",
                "true",
                "--enable-http",
                "false",
                "--enable-sse",
                "false",
                "--enable-metrics",
                "true",
                "--embedding-model",
                "debug-hash",
            ]
        )


@pytest.mark.asyncio
async def test_metrics_disabled_preserves_stdio_workflows(tmp_path) -> None:
    config = load_config(
        argv=[
            "--storage-dir",
            str(tmp_path),
            "--enable-stdio",
            "true",
            "--enable-http",
            "true",
            "--enable-sse",
            "false",
            "--enable-metrics",
            "false",
            "--embedding-model",
            "debug-hash",
        ]
    )
    initialize_app(config)
    try:
        result = await _scratch_create_impl(metadata={"title": "stdio ok"})
        assert result["ok"] is True
        assert result["scratchpad"]["metadata"]["title"] == "stdio ok"
    finally:
        shutdown_app()


