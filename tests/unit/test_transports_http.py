from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastmcp import FastMCP

from scratch_notebook.transports.http import HttpTransportConfig, describe_routes, run_http


def test_describe_routes_respects_toggles() -> None:
    config = HttpTransportConfig(
        host="127.0.0.1",
        port=1234,
        http_path="/http",
        sse_path="/sse",
        metrics_path="/metrics",
        enable_metrics=True,
        enable_http=False,
        enable_sse=True,
        socket_path=None,
    )

    routes = describe_routes(config)

    assert "http" not in routes
    assert routes["sse"] == "/sse"
    assert routes["metrics"] == "/metrics"


@pytest.mark.parametrize("socket_path", [None, Path("/tmp/mock.sock")])
def test_run_http_invokes_uvicorn(monkeypatch: pytest.MonkeyPatch, socket_path: Path | None) -> None:
    captured: dict[str, Any] = {}

    class DummyConfig:  # mimics uvicorn.Config signature
        def __init__(self, app, host, port, **kwargs):
            captured["app"] = app
            captured["host"] = host
            captured["port"] = port
            captured["kwargs"] = kwargs
            self.app = app

    class DummyServer:
        def __init__(self, config):
            captured["config"] = config

        async def serve(self) -> None:
            captured["served"] = True

    monkeypatch.setattr("scratch_notebook.transports.http.uvicorn.Config", DummyConfig)
    monkeypatch.setattr("scratch_notebook.transports.http.uvicorn.Server", DummyServer)

    server = FastMCP(name="test-http")
    config = HttpTransportConfig(
        host="127.0.0.1",
        port=0,
        http_path="/http",
        sse_path="/sse",
        metrics_path="/metrics",
        enable_metrics=False,
        enable_http=True,
        enable_sse=False,
        socket_path=socket_path,
    )

    run_http(server, config)

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 0
    if socket_path is None:
        assert "uds" not in captured["kwargs"]
    else:
        assert captured["kwargs"]["uds"] == str(socket_path)
    assert captured["served"] is True
    assert getattr(captured["app"].state, "fastmcp_server") is server
    assert captured["app"].state.path == "/http"
