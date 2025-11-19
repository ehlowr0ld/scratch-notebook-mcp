from __future__ import annotations

from pathlib import Path

import pytest

from scratch_notebook.config import ConfigError, load_config


def test_metrics_help_mentions_requirement(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        load_config(argv=["--help"])
    captured = capsys.readouterr().out
    assert "--enable-metrics" in captured
    assert "requires --enable-http true" in captured


def test_metrics_flags_defaults(tmp_path: Path) -> None:
    cfg = load_config(argv=[], environ={"SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path)})

    assert cfg.enable_http is True
    assert cfg.enable_sse is True
    assert cfg.enable_metrics is False


def test_enable_metrics_requires_http(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(
            argv=[
                "--storage-dir",
                str(tmp_path),
                "--enable-http",
                "false",
                "--enable-metrics",
                "true",
            ]
        )

    assert "enable_metrics requires enable_http to be true" in str(excinfo.value)


def test_enable_metrics_without_sse_is_supported(tmp_path: Path) -> None:
    cfg = load_config(
        argv=[
            "--storage-dir",
            str(tmp_path),
            "--enable-http",
            "true",
            "--enable-sse",
            "false",
            "--enable-metrics",
            "true",
        ]
    )

    assert cfg.enable_http is True
    assert cfg.enable_sse is False
    assert cfg.enable_metrics is True


def test_enable_metrics_with_http_and_sse(tmp_path: Path) -> None:
    cfg = load_config(
        argv=[
            "--storage-dir",
            str(tmp_path),
            "--enable-http",
            "true",
            "--enable-sse",
            "true",
            "--enable-metrics",
            "true",
        ]
    )

    assert cfg.enable_http is True
    assert cfg.enable_sse is True
    assert cfg.enable_metrics is True


