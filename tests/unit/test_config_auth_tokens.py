from __future__ import annotations

import json
from pathlib import Path

import pytest

from scratch_notebook import load_config


def test_cli_auth_tokens_preserve_order(tmp_path: Path) -> None:
    cfg = load_config(
        argv=[
            "--storage-dir",
            str(tmp_path / "storage"),
            "--auth-token",
            "tenantA:alpha",
            "--auth-token",
            "tenantB:beta",
        ]
    )

    assert list(cfg.auth_tokens.items()) == [("tenantA", "alpha"), ("tenantB", "beta")]


def test_cli_tokens_override_file_tokens(tmp_path: Path) -> None:
    token_path = tmp_path / "auth" / "tokens.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps({"tokens": {"tenantA": "older", "tenantC": "gamma"}}), encoding="utf-8")

    cfg = load_config(
        argv=[
            "--storage-dir",
            str(tmp_path / "storage"),
            "--auth-token-file",
            str(token_path),
            "--auth-token",
            "tenantA:newer",
            "--auth-token",
            "tenantB:beta",
        ]
    )

    assert cfg.auth_tokens["tenantA"] == "newer"
    assert cfg.auth_tokens["tenantB"] == "beta"
    assert cfg.auth_tokens["tenantC"] == "gamma"


def test_invalid_auth_token_argument_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_config(argv=["--storage-dir", str(tmp_path / "storage"), "--auth-token", "missingcolon"])
