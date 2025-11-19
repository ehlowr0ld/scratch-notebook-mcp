from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from scratch_notebook import load_config
from scratch_notebook.config import ConfigError


def _base_args(tmp_path: Path, *extra: str) -> list[str]:
    storage_dir = tmp_path / "storage"
    return ["--storage-dir", str(storage_dir), *extra]


def test_duration_flags_accept_suffixes(tmp_path: Path) -> None:
    cfg = load_config(
        argv=_base_args(
            tmp_path,
            "--preempt-age",
            "48h",
            "--preempt-interval",
            "90m",
            "--validation-request-timeout",
            "42s",
            "--shutdown-timeout",
            "120s",
        )
    )

    assert cfg.preempt_age == timedelta(hours=48)
    assert cfg.preempt_interval == timedelta(minutes=90)
    assert cfg.validation_request_timeout == timedelta(seconds=42)
    assert cfg.shutdown_timeout == timedelta(seconds=120)


def test_duration_flags_use_default_units_when_missing_suffix(tmp_path: Path) -> None:
    cfg = load_config(
        argv=_base_args(
            tmp_path,
            "--preempt-age",
            "12",
            "--preempt-interval",
            "5",
            "--validation-request-timeout",
            "7",
            "--shutdown-timeout",
            "9",
        )
    )

    assert cfg.preempt_age == timedelta(hours=12)
    assert cfg.preempt_interval == timedelta(minutes=5)
    assert cfg.validation_request_timeout == timedelta(seconds=7)
    assert cfg.shutdown_timeout == timedelta(seconds=9)


@pytest.mark.parametrize("value", ["", "abc", "3x"])
def test_invalid_duration_strings_raise(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError):
        load_config(argv=_base_args(tmp_path, "--preempt-age", value))


def test_invalid_config_file_value_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "storage_dir": str(tmp_path / "data"),
                "enable_http": "definitely",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(argv=["--config-file", str(config_path)])


def test_empty_storage_dir_in_config_file_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"storage_dir": ""}), encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(argv=["--config-file", str(config_path)])
