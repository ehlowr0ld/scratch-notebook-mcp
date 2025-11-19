from __future__ import annotations

import threading
from datetime import timedelta
from typing import TYPE_CHECKING

from .logging import get_logger

if TYPE_CHECKING:
    from .storage_lancedb import Storage

LOGGER = get_logger(__name__)


class PreemptiveSweeper:
    """Background worker that applies the preempt eviction policy."""

    def __init__(self, storage: Storage, *, age: timedelta, interval: timedelta) -> None:
        self._storage = storage
        self._age = age
        minimum_interval = max(interval.total_seconds(), 0.1)
        self._interval = timedelta(seconds=minimum_interval)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="scratch-notebook-preempt-sweeper",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=self._interval.total_seconds() + 1)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval.total_seconds()):
            try:
                evicted = self._storage.evict_stale(self._age)
                if evicted:
                    LOGGER.info(
                        "eviction.preempt.sweep",
                        extra={
                            "policy": "preempt",
                            "scratchpad_ids": evicted,
                            "tenant_id": self._storage.tenant_id(),
                        },
                    )
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Preemptive eviction sweep failed")
