import json
from pathlib import Path

from scratch_notebook import load_config


def test_config_file_created_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "conf" / "server" / "config.json"
    storage_dir = tmp_path / "storage"

    cfg = load_config(
        argv=[
            "--config-file",
            str(config_path),
            "--storage-dir",
            str(storage_dir),
            "--enable-http",
            "false",
        ]
    )

    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["storage_dir"] == str(storage_dir.resolve())
    assert data["enable_http"] is False
    # ensure stored durations use strings
    assert isinstance(data["preempt_age"], str)
    assert cfg.enable_http is False


def test_config_file_not_overwritten_when_present(tmp_path: Path) -> None:
    config_path = tmp_path / "conf" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    original_content = json.dumps({"storage_dir": "manual"})
    config_path.write_text(original_content, encoding="utf-8")

    cfg = load_config(argv=["--config-file", str(config_path), "--storage-dir", str(tmp_path / "storage")])

    assert config_path.read_text(encoding="utf-8") == original_content
    assert cfg.storage_dir == (tmp_path / "storage").resolve()


def test_auth_token_file_created_with_cli_token(tmp_path: Path) -> None:
    config_path = tmp_path / "conf" / "config.json"
    token_path = tmp_path / "auth" / "tokens.json"

    load_config(
        argv=[
            "--config-file",
            str(config_path),
            "--auth-token-file",
            str(token_path),
            "--auth-token",
            "tenantA:secret-token",
            "--storage-dir",
            str(tmp_path / "storage"),
        ]
    )

    assert token_path.exists()
    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    assert token_data["tokens"]["tenantA"] == "secret-token"


def test_auth_token_file_created_with_bearer_token(tmp_path: Path) -> None:
    token_path = tmp_path / "auth" / "tokens.json"

    load_config(
        argv=[
            "--auth-token-file",
            str(token_path),
            "--auth-bearer-token",
            "fallback-secret",
            "--storage-dir",
            str(tmp_path / "storage"),
        ]
    )

    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    assert token_data["tokens"]["default"] == "fallback-secret"


def test_auth_token_file_empty_when_no_token(tmp_path: Path) -> None:
    token_path = tmp_path / "auth" / "tokens.json"

    load_config(
        argv=[
            "--auth-token-file",
            str(token_path),
            "--storage-dir",
            str(tmp_path / "storage"),
        ]
    )

    assert token_path.exists()
    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    assert token_data == {"tokens": {}}
