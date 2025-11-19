from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from scratch_notebook.config import Config
from scratch_notebook.server import SERVER, main as run_main
from scratch_notebook.transports.stdio import run_stdio


class _DummyServer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, *, transport: str, show_banner: bool) -> None:
        self.calls.append({"transport": transport, "show_banner": show_banner})


def _make_config(storage_dir: Path, *, enable_stdio: bool) -> Config:
    return Config(
        storage_dir=storage_dir,
        enable_stdio=enable_stdio,
        enable_http=False,
        enable_sse=False,
        enable_metrics=False,
        enable_auth=False,
        enable_semantic_search=True,
        auth_bearer_token=None,
        auth_token_file=None,
        auth_tokens={},
        http_host="127.0.0.1",
        http_port=8765,
        http_socket_path=None,
        http_path="/http",
        sse_path="/sse",
        metrics_path="/metrics",
        max_scratchpads=0,
        max_cells_per_pad=0,
        max_cell_bytes=0,
        eviction_policy="discard",
        preempt_age=timedelta(hours=24),
        preempt_interval=timedelta(minutes=10),
        validation_request_timeout=timedelta(seconds=10),
        shutdown_timeout=timedelta(seconds=5),
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        embedding_device="cpu",
        embedding_batch_size=16,
        config_file=None,
    )


def test_run_stdio_invokes_fastmcp() -> None:
    dummy = _DummyServer()

    run_stdio(dummy, show_banner=False)

    assert dummy.calls == [{"transport": "stdio", "show_banner": False}]


def test_run_stdio_propagates_keyboard_interrupt() -> None:
    class InterruptingServer:
        def run(self, *, transport: str, show_banner: bool) -> None:  # noqa: D401 - simple stub
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_stdio(InterruptingServer())


def test_main_runs_stdio_when_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _make_config(tmp_path, enable_stdio=True)
    calls: list[tuple[str, Any]] = []

    monkeypatch.setattr("scratch_notebook.server.configure_logging", lambda: None)
    monkeypatch.setattr("scratch_notebook.server.initialize_app", lambda cfg: None)
    monkeypatch.setattr("scratch_notebook.server.shutdown_app", lambda: None)
    monkeypatch.setattr("scratch_notebook.server.run_http", lambda *args, **kwargs: calls.append(("http", args)))
    monkeypatch.setattr("scratch_notebook.server.load_config", lambda argv: config)

    def _capture_stdio(server: Any, *, show_banner: bool = True) -> None:
        calls.append(("stdio", server, show_banner))

    monkeypatch.setattr("scratch_notebook.server.run_stdio", _capture_stdio)

    run_main([])

    assert ("stdio", SERVER, True) in calls
    assert all(call[0] != "http" for call in calls)


def test_main_skips_stdio_when_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _make_config(tmp_path, enable_stdio=False)
    calls: list[tuple[str, Any]] = []

    monkeypatch.setattr("scratch_notebook.server.configure_logging", lambda: None)
    monkeypatch.setattr("scratch_notebook.server.initialize_app", lambda cfg: None)
    monkeypatch.setattr("scratch_notebook.server.shutdown_app", lambda: None)
    monkeypatch.setattr("scratch_notebook.server.run_http", lambda *args, **kwargs: calls.append(("http", args)))
    monkeypatch.setattr("scratch_notebook.server.load_config", lambda argv: config)
    monkeypatch.setattr("scratch_notebook.server.run_stdio", lambda *args, **kwargs: calls.append(("stdio", args)))

    run_main([])

    assert all(call[0] != "stdio" for call in calls)
