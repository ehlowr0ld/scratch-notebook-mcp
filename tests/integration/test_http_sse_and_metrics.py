from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator, Tuple

import httpx
import pytest

from scratch_notebook import load_config
from scratch_notebook.server import SERVER, initialize_app, shutdown_app
from scratch_notebook.transports.http import HttpTransportConfig, _build_transport_app


def _parse_sse_json(body: str) -> dict[str, object]:
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError(f"No data line found in SSE payload: {body!r}")


@asynccontextmanager
async def _http_test_client(tmp_path) -> AsyncIterator[Tuple[httpx.AsyncClient, HttpTransportConfig]]:
    storage_dir = tmp_path / "storage"
    argv = [
        "--enable-http",
        "true",
        "--enable-sse",
        "true",
        "--enable-metrics",
        "true",
        "--enable-auth",
        "true",
        "--auth-token",
        "tenantA:secret",
        "--storage-dir",
        str(storage_dir),
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


@pytest.mark.anyio
async def test_http_initialize_and_call_tool(tmp_path) -> None:
    async with _http_test_client(tmp_path) as (client, config):
        base_headers = {
            "Authorization": "Bearer secret",
            "Accept": "application/json, text/event-stream",
        }

        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0.0.0"},
            },
        }
        init_response = await client.post(config.http_path, json=init_payload, headers=base_headers)
        assert init_response.status_code == 200
        assert init_response.headers.get("content-type", "").startswith("text/event-stream")
        session_id = init_response.headers["mcp-session-id"]
        init_event = _parse_sse_json(init_response.text)
        assert init_event["id"] == 1

        call_headers = dict(base_headers)
        call_headers.update({
            "Content-Type": "application/json",
            "mcp-session-id": session_id,
        })
        call_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "scratch_list",
                "arguments": {},
            },
        }
        call_response = await client.post(config.http_path, json=call_payload, headers=call_headers)
        assert call_response.status_code == 200
        assert call_response.headers.get("content-type", "").startswith("text/event-stream")
        call_event = _parse_sse_json(call_response.text)
        assert call_event["id"] == 2
        payload = call_event["result"]
        assert isinstance(payload, dict)
        assert payload["structuredContent"] == {"ok": True, "scratchpads": []}


@pytest.mark.anyio
async def test_metrics_endpoint_exposes_prometheus(tmp_path) -> None:
    async with _http_test_client(tmp_path) as (client, config):
        headers = {"Authorization": "Bearer secret"}
        response = await client.get(config.metrics_path, headers=headers)
        assert response.status_code == 200
        body = response.text
        assert "scratch_notebook_ops_total" in body
        assert "scratch_notebook_uptime_seconds" in body


@pytest.mark.anyio
async def test_http_auth_rejects_missing_token(tmp_path) -> None:
    async with _http_test_client(tmp_path) as (client, config):
        response = await client.post(
            config.http_path,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert response.status_code == 401
        problem = response.json()
        assert problem["error"] == "invalid_token"
