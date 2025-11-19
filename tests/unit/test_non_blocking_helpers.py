from __future__ import annotations

import pytest

from scratch_notebook.validation import run_validation_task


@pytest.mark.asyncio
async def test_validation_helper_uses_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        return func(*args, **kwargs)

    monkeypatch.setattr("scratch_notebook.validation.asyncio.to_thread", fake_to_thread)

    def blocking(x: int) -> int:
        return x * 2

    result = await run_validation_task(blocking, 21)

    assert result == 42
    assert called is True
