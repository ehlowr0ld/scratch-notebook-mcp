import json
from pathlib import Path

import pytest

from scratch_notebook import Config, load_config
from scratch_notebook.config import ConfigError


def test_package_imports() -> None:
    """Importing the package should expose main APIs."""

    assert callable(load_config)
    assert Config is not None


def test_default_configuration(tmp_path: Path) -> None:
    """Defaults should populate expected values when no overrides provided."""

    storage_dir = tmp_path / "storage"
    environ = {"SCRATCH_NOTEBOOK_STORAGE_DIR": str(storage_dir)}

    cfg = load_config(argv=[], environ=environ)

    assert cfg.storage_dir == storage_dir.resolve()
    assert cfg.enable_stdio is True
    assert cfg.enable_http is True
    assert cfg.http_host == "127.0.0.1"
    assert cfg.http_port == 8765


def test_cli_overrides_take_precedence(tmp_path: Path) -> None:
    """CLI arguments should override defaults and environment values."""

    argv = [
        "--storage-dir",
        str(tmp_path / "storage"),
        "--enable-http",
        "false",
        "--max-scratchpads",
        "2048",
    ]

    cfg = load_config(argv=argv)

    assert cfg.enable_http is False
    assert cfg.max_scratchpads == 2048


def test_env_overrides(tmp_path: Path) -> None:
    """Environment variables should override defaults."""

    environ = {
        "SCRATCH_NOTEBOOK_STORAGE_DIR": str(tmp_path / "data"),
        "SCRATCH_NOTEBOOK_ENABLE_STDIO": "false",
    }

    cfg = load_config(argv=[], environ=environ)

    assert cfg.enable_stdio is False
    assert cfg.storage_dir == (tmp_path / "data").resolve()


def test_json_config_file(tmp_path: Path) -> None:
    """A JSON config file should be merged into the configuration."""

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "storage_dir": str(tmp_path / "configured"),
                "enable_http": False,
                "max_cells_per_pad": 256,
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(argv=["--config-file", str(config_file)])

    assert cfg.storage_dir == (tmp_path / "configured").resolve()
    assert cfg.enable_http is False
    assert cfg.max_cells_per_pad == 256


def test_invalid_numeric_value_raises(tmp_path: Path) -> None:
    """Invalid numeric values should trigger configuration errors."""

    with pytest.raises(ConfigError):
        load_config(argv=["--max-scratchpads", "not-a-number", "--storage-dir", str(tmp_path)])
