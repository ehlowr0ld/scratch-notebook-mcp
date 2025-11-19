from __future__ import annotations

from scratch_notebook import metrics


def test_metrics_registry_records_and_formats() -> None:
    registry = metrics.MetricsRegistry()
    metrics.install_registry(registry)
    try:
        metrics.record_operation("create")
        metrics.record_operation("list", count=2)
        metrics.record_error("NOT_FOUND")
        metrics.record_eviction("discard", count=3)

        snapshot = registry.snapshot()
        text = metrics.format_prometheus(snapshot, scratchpads_current=5, cells_current=12)

        assert 'scratch_notebook_ops_total{op="create"} 1' in text
        assert 'scratch_notebook_ops_total{op="list"} 2' in text
        assert 'scratch_notebook_ops_total{op="validate"} 0' in text
        assert 'scratch_notebook_errors_total{code="NOT_FOUND"} 1' in text
        assert 'scratch_notebook_evictions_total{policy="discard"} 3' in text
        assert 'scratch_notebook_scratchpads_current 5' in text
        assert 'scratch_notebook_cells_current 12' in text
        assert 'scratch_notebook_uptime_seconds' in text
    finally:
        metrics.install_registry(None)


def test_record_helpers_no_registry() -> None:
    metrics.install_registry(None)
    # Should no-op without raising when registry is not installed.
    metrics.record_operation("create")
    metrics.record_error("NOT_FOUND")
    metrics.record_eviction("discard")
