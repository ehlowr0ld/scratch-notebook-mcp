from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from scratch_notebook import load_config
from scratch_notebook.errors import CONFIG_ERROR
from scratch_notebook.server import (
    _SHUTDOWN_MANAGER,
    _scratch_list_impl,
    initialize_app,
    shutdown_app,
)


@pytest.mark.asyncio
async def test_requests_rejected_once_shutdown_starts(tmp_path: Path) -> None:
    config = load_config(argv=["--storage-dir", str(tmp_path / "storage")])
    initialize_app(config)
    _SHUTDOWN_MANAGER.request_shutdown(config.shutdown_timeout)
    try:
        response = await _scratch_list_impl()
        assert response["ok"] is False
        assert response["error"]["code"] == CONFIG_ERROR
    finally:
        shutdown_app()


def test_shutdown_waits_for_inflight_requests(tmp_path: Path) -> None:
    config = load_config(
        argv=[
            "--storage-dir",
            str(tmp_path / "storage"),
            "--shutdown-timeout",
            "2s",
        ]
    )
    initialize_app(config)
    release = _SHUTDOWN_MANAGER.try_enter()
    assert release is not None
    released = False

    thread = threading.Thread(target=shutdown_app)
    thread.start()
    try:
        time.sleep(0.05)
        assert thread.is_alive()
        release()
        released = True
        thread.join(timeout=1)
        assert not thread.is_alive()
    finally:
        if not released:
            release()
        thread.join(timeout=1)
