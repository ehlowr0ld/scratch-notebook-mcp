from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator, Tuple

import httpx
import pytest

from scratch_notebook.config import ConfigError, load_config
from scratch_notebook.server import SERVER, initialize_app, shutdown_app
from scratch_notebook.transports.http import HttpTransportConfig, _build_transport_app


def _parse_sse_json(body: str) -> dict[str, object]:
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError(f"No SSE data line found: {body!r}")


@asynccontextmanager
async def _http_matrix_client(
    tmp_path,
    *,
    enable_http: bool,
    enable_sse: bool,
    enable_metrics: bool,
) -> AsyncIterator[Tuple[httpx.AsyncClient, HttpTransportConfig]]:
    storage_dir = tmp_path / "storage"
    argv = [
        "--storage-dir",
        str(storage_dir),
        "--enable-http",
        "true" if enable_http else "false",
        "--enable-sse",
        "true" if enable_sse else "false",
        "--enable-metrics",
        "true" if enable_metrics else "false",
        "--embedding-model",
        "debug-hash",
    ]
    config = load_config(argv=argv)
    initialize_app(config)
    try:
        http_config = HttpTransportConfig(
            host="127.0.0.1",
            port=0,
            http_path=config.http_path,
            sse_path=config.sse_path,
            metrics_path=config.metrics_path,
            enable_metrics=config.enable_metrics,
            enable_http=config.enable_http,
            enable_sse=config.enable_sse,
            socket_path=None,
        )
        app = _build_transport_app(SERVER, http_config)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                yield client, http_config
    finally:
        shutdown_app()


def test_metrics_matrix_requires_http(tmp_path) -> None:
    with pytest.raises(ConfigError):
        load_config(
            argv=[
                "--storage-dir",
                str(tmp_path),
                "--enable-http",
                "false",
                "--enable-sse",
                "true",
                "--enable-metrics",
                "true",
                "--embedding-model",
                "debug-hash",
            ]
        )


@pytest.mark.anyio
async def test_metrics_matrix_metrics_without_sse(tmp_path) -> None:
    async with _http_matrix_client(
        tmp_path,
        enable_http=True,
        enable_sse=False,
        enable_metrics=True,
    ) as (client, config):
        response = await client.get(config.metrics_path)
        assert response.status_code == 200
        body = response.text
        assert "scratch_notebook_ops_total" in body
        assert "scratch_notebook_uptime_seconds" in body


@pytest.mark.anyio
async def test_metrics_matrix_metrics_with_sse(tmp_path) -> None:
    async with _http_matrix_client(
        tmp_path,
        enable_http=True,
        enable_sse=True,
        enable_metrics=True,
    ) as (client, config):
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "matrix-test", "version": "0.0.0"},
            },
        }
        response = await client.post(
            config.http_path,
            json=init_payload,
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert response.status_code == 200
        event = _parse_sse_json(response.text)
        assert event["id"] == 1

        metrics_response = await client.get(config.metrics_path)
        assert metrics_response.status_code == 200
        assert "scratch_notebook_ops_total" in metrics_response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "enable_http, enable_sse",
    [
        (True, False),
        (True, True),
        (False, True),
        (False, False),
    ],
)
async def test_metrics_matrix_metrics_disabled_removes_endpoint(
    tmp_path,
    enable_http: bool,
    enable_sse: bool,
) -> None:
    async with _http_matrix_client(
        tmp_path,
        enable_http=enable_http,
        enable_sse=enable_sse,
        enable_metrics=False,
    ) as (client, config):
        response = await client.get(config.metrics_path)
        assert response.status_code == 404
