from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from scratch_notebook import load_config
from scratch_notebook.auth import ScratchTokenAuthProvider
from scratch_notebook.server import APP_STATE, get_storage, initialize_app, shutdown_app


@pytest.mark.asyncio
async def test_verify_token_matches_registry() -> None:
    provider = ScratchTokenAuthProvider({"tenant-a": "token-123"})
    token = await provider.verify_token("token-123")
    assert token is not None
    assert token.client_id == "tenant-a"
    assert token.claims["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_verify_token_unknown_returns_none() -> None:
    provider = ScratchTokenAuthProvider({"tenant-a": "token-123"})
    token = await provider.verify_token("other")
    assert token is None


def test_get_storage_sets_tenant_from_context(tmp_path) -> None:
    environ = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path),
        "SCRATCH_NOTEBOOK_ENABLE_STDIO": "false",
        "SCRATCH_NOTEBOOK_ENABLE_HTTP": "false",
        "SCRATCH_NOTEBOOK_ENABLE_SSE": "false",
        "SCRATCH_NOTEBOOK_ENABLE_METRICS": "false",
        "SCRATCH_NOTEBOOK_ENABLE_AUTH": "true",
    }
    cfg = load_config(
        argv=["--auth-token", "tenant-a:secret", "--auth-token", "tenant-b:other"],
        environ=environ,
    )

    initialize_app(cfg)
    try:
        # Simulate FastMCP context object exposing client_id
        context = SimpleNamespace(client_id="tenant-b", request_context=None)
        storage = get_storage(context)
        assert storage.tenant_id() == "tenant-b"

        # Fallback to default tenant when context missing principal
        fallback_storage = get_storage(None)
        assert fallback_storage.tenant_id() == "tenant-a"
    finally:
        shutdown_app()
        assert APP_STATE is None
