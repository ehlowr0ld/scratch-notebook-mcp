from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Mapping

_DEFAULT_OPERATIONS = ("create", "read", "append", "replace", "delete", "list", "validate")
_DEFAULT_EVICTION_POLICIES = ("discard", "preempt")

_registry_lock = RLock()
_registry: "MetricsRegistry | None" = None


@dataclass(frozen=True)
class MetricsSnapshot:
    """Immutable snapshot of the current metrics state."""

    operations: Mapping[str, int]
    errors: Mapping[str, int]
    evictions: Mapping[str, int]
    uptime_seconds: float


class MetricsRegistry:
    """Thread-safe registry storing counters and gauges for Prometheus export."""

    __slots__ = ("_operations", "_errors", "_evictions", "_lock", "_started_at")

    def __init__(self) -> None:
        self._operations: Counter[str] = Counter()
        self._errors: Counter[str] = Counter()
        self._evictions: Counter[str] = Counter()
        self._lock = RLock()
        self._started_at = monotonic()

    def record_operation(self, name: str, *, count: int = 1) -> None:
        if count <= 0:
            return
        key = name.strip().lower()
        if not key:
            return
        with self._lock:
            self._operations[key] += count

    def record_error(self, code: str, *, count: int = 1) -> None:
        if count <= 0:
            return
        key = code.strip().upper()
        if not key:
            return
        with self._lock:
            self._errors[key] += count

    def record_eviction(self, policy: str, *, count: int = 1) -> None:
        if count <= 0:
            return
        key = policy.strip().lower() or "unknown"
        with self._lock:
            self._evictions[key] += count

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            operations: dict[str, int] = {name: int(self._operations.get(name, 0)) for name in _DEFAULT_OPERATIONS}
            for name, value in self._operations.items():
                if name not in operations:
                    operations[name] = int(value)
            errors = {code: int(value) for code, value in self._errors.items()}
            evictions: dict[str, int] = {policy: int(self._evictions.get(policy, 0)) for policy in _DEFAULT_EVICTION_POLICIES}
            for policy, value in self._evictions.items():
                if policy not in evictions:
                    evictions[policy] = int(value)
            uptime = max(monotonic() - self._started_at, 0.0)
        return MetricsSnapshot(operations=operations, errors=errors, evictions=evictions, uptime_seconds=uptime)

    def reset(self) -> None:
        with self._lock:
            self._operations.clear()
            self._errors.clear()
            self._evictions.clear()
            self._started_at = monotonic()


def install_registry(registry: MetricsRegistry | None) -> None:
    """Install the active metrics registry (or disable metrics when None)."""

    with _registry_lock:
        global _registry
        _registry = registry


def get_registry_optional() -> MetricsRegistry | None:
    with _registry_lock:
        return _registry


def record_operation(name: str, *, count: int = 1) -> None:
    registry = get_registry_optional()
    if registry is not None:
        registry.record_operation(name, count=count)


def record_error(code: str, *, count: int = 1) -> None:
    registry = get_registry_optional()
    if registry is not None:
        registry.record_error(code, count=count)


def record_eviction(policy: str, *, count: int = 1) -> None:
    registry = get_registry_optional()
    if registry is not None:
        registry.record_eviction(policy, count=count)


def format_prometheus(snapshot: MetricsSnapshot, *, scratchpads_current: int, cells_current: int) -> str:
    """Render metrics using Prometheus exposition format (text, version 0.0.4)."""

    lines: list[str] = []

    lines.append("# HELP scratch_notebook_ops_total Total operations executed by type.")
    lines.append("# TYPE scratch_notebook_ops_total counter")
    for name in sorted(snapshot.operations):
        value = snapshot.operations[name]
        lines.append(f'scratch_notebook_ops_total{{op="{name}"}} {value}')

    lines.append("# HELP scratch_notebook_errors_total Total errors returned, grouped by error code.")
    lines.append("# TYPE scratch_notebook_errors_total counter")
    if snapshot.errors:
        for code in sorted(snapshot.errors):
            value = snapshot.errors[code]
            lines.append(f'scratch_notebook_errors_total{{code="{code}"}} {value}')
    else:
        lines.append('scratch_notebook_errors_total{code="none"} 0')

    lines.append("# HELP scratch_notebook_evictions_total Scratchpads evicted by policy.")
    lines.append("# TYPE scratch_notebook_evictions_total counter")
    for policy in sorted(snapshot.evictions):
        value = snapshot.evictions[policy]
        lines.append(f'scratch_notebook_evictions_total{{policy="{policy}"}} {value}')

    lines.append("# HELP scratch_notebook_scratchpads_current Current scratchpad count.")
    lines.append("# TYPE scratch_notebook_scratchpads_current gauge")
    lines.append(f"scratch_notebook_scratchpads_current {scratchpads_current}")

    lines.append("# HELP scratch_notebook_cells_current Current cell count across all scratchpads.")
    lines.append("# TYPE scratch_notebook_cells_current gauge")
    lines.append(f"scratch_notebook_cells_current {cells_current}")

    lines.append("# HELP scratch_notebook_uptime_seconds Server uptime in seconds.")
    lines.append("# TYPE scratch_notebook_uptime_seconds gauge")
    lines.append(f"scratch_notebook_uptime_seconds {snapshot.uptime_seconds:.6f}")

    return "\n".join(lines) + "\n"
