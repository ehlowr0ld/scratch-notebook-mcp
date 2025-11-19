import pytest
import logging

from scratch_notebook import load_config
from scratch_notebook.server import get_storage, initialize_app, _scratch_create_impl


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - simple accessor
        self.records.append(record)


@pytest.mark.asyncio
async def test_default_tenant_migration_logs_and_reassigns(tmp_path):
    storage_dir = tmp_path / "storage"
    environ = {
        "SCRATCH_NOTEBOOK_EMBEDDING_MODEL": "debug-hash",
        "SCRATCH_NOTEBOOK_ENABLE_STDIO": "false",
        "SCRATCH_NOTEBOOK_ENABLE_HTTP": "false",
        "SCRATCH_NOTEBOOK_ENABLE_SSE": "false",
        "SCRATCH_NOTEBOOK_ENABLE_METRICS": "false",
    }

    initial_config = load_config(
        argv=[
            "--storage-dir",
            str(storage_dir),
            "--enable-http",
            "false",
            "--enable-sse",
            "false",
        ],
        environ=environ,
    )
    initialize_app(initial_config)
    create_resp = await _scratch_create_impl(metadata={"title": "Before migration"})
    scratch_id = create_resp["scratchpad"]["scratch_id"]

    auth_config = load_config(
        argv=[
            "--storage-dir",
            str(storage_dir),
            "--enable-auth",
            "true",
            "--auth-token",
            "tenant-auth:secret",
            "--auth-token-file",
            str(tmp_path / "auth" / "tokens.json"),
            "--enable-http",
            "false",
            "--enable-sse",
            "false",
        ],
        environ=environ,
    )
    handler = _RecordingHandler()
    logger = logging.getLogger("scratch_notebook")
    logger.addHandler(handler)
    try:
        initialize_app(auth_config)
    finally:
        logger.removeHandler(handler)

    assert any(record.getMessage() == "tenant.migration.completed" for record in handler.records)

    storage = get_storage()
    assert storage.tenant_id() == "tenant-auth"
    rows = storage._table.to_arrow().to_pylist()  # type: ignore[attr-defined]
    assert all((row.get("tenant_id") or "").strip() == "tenant-auth" for row in rows if row.get("scratch_id") == scratch_id)
