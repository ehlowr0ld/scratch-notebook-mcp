from __future__ import annotations

from pathlib import Path

BLOCKING_PATTERNS = ["time.sleep("]


def test_no_blocking_calls_in_project() -> None:
    """Ensure no obviously blocking calls are introduced inadvertently."""

    project_root = Path(__file__).resolve().parents[2] / "scratch_notebook"
    violations: list[str] = []

    for path in project_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in BLOCKING_PATTERNS:
            if pattern in text:
                violations.append(f"{path.relative_to(project_root)} contains {pattern}")

    assert not violations, "Blocking calls detected:\n" + "\n".join(violations)
