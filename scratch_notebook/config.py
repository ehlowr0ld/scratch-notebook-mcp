"""Configuration loading utilities for the Scratch Notebook MCP server."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

ENV_PREFIX = "SCRATCH_NOTEBOOK_"

BOOL_TRUE = {"1", "true", "t", "yes", "y", "on"}
BOOL_FALSE = {"0", "false", "f", "no", "n", "off"}

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765
DEFAULT_HTTP_PATH = "/http"
DEFAULT_SSE_PATH = "/sse"
DEFAULT_METRICS_PATH = "/metrics"
DEFAULT_STORAGE_SUBDIR = "scratch-notebook"


def _default_storage_dir() -> Path:
    """Return the default storage directory under the current working directory."""

    return (Path.cwd() / DEFAULT_STORAGE_SUBDIR).resolve()


DEFAULT_STORAGE_DIR = _default_storage_dir()
DEFAULT_MAX_SCRATCHPADS = 1024
DEFAULT_MAX_CELLS_PER_PAD = 1024
DEFAULT_MAX_CELL_BYTES = 5_242_880
DEFAULT_EVICTION_POLICY = "discard"
DEFAULT_PREEMPT_AGE = "24h"
DEFAULT_PREEMPT_INTERVAL = "10m"
DEFAULT_VALIDATION_TIMEOUT = "10s"
DEFAULT_SHUTDOWN_TIMEOUT = "5s"
DEFAULT_ENABLE_SEMANTIC_SEARCH = True
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DEVICE = "cpu"
DEFAULT_EMBEDDING_BATCH_SIZE = 16

T_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600}

ENV_FIELD_MAP = {
    "config_file": f"{ENV_PREFIX}CONFIG_FILE",
    "storage_dir": f"{ENV_PREFIX}STORAGE_DIR",
    "enable_stdio": f"{ENV_PREFIX}ENABLE_STDIO",
    "enable_http": f"{ENV_PREFIX}ENABLE_HTTP",
    "enable_sse": f"{ENV_PREFIX}ENABLE_SSE",
    "enable_metrics": f"{ENV_PREFIX}ENABLE_METRICS",
    "enable_auth": f"{ENV_PREFIX}ENABLE_AUTH",
    "enable_semantic_search": f"{ENV_PREFIX}ENABLE_SEMANTIC_SEARCH",
    "auth_bearer_token": f"{ENV_PREFIX}AUTH_BEARER_TOKEN",
    "auth_token_file": f"{ENV_PREFIX}AUTH_TOKEN_FILE",
    "http_host": f"{ENV_PREFIX}HTTP_HOST",
    "http_port": f"{ENV_PREFIX}HTTP_PORT",
    "http_socket_path": f"{ENV_PREFIX}HTTP_SOCKET_PATH",
    "http_path": f"{ENV_PREFIX}HTTP_PATH",
    "sse_path": f"{ENV_PREFIX}SSE_PATH",
    "metrics_path": f"{ENV_PREFIX}METRICS_PATH",
    "max_scratchpads": f"{ENV_PREFIX}MAX_SCRATCHPADS",
    "max_cells_per_pad": f"{ENV_PREFIX}MAX_CELLS_PER_PAD",
    "max_cell_bytes": f"{ENV_PREFIX}MAX_CELL_BYTES",
    "eviction_policy": f"{ENV_PREFIX}EVICTION_POLICY",
    "preempt_age": f"{ENV_PREFIX}PREEMPT_AGE",
    "preempt_interval": f"{ENV_PREFIX}PREEMPT_INTERVAL",
    "validation_request_timeout": f"{ENV_PREFIX}VALIDATION_TIMEOUT",
    "shutdown_timeout": f"{ENV_PREFIX}SHUTDOWN_TIMEOUT",
    "embedding_model": f"{ENV_PREFIX}EMBEDDING_MODEL",
    "embedding_device": f"{ENV_PREFIX}EMBEDDING_DEVICE",
    "embedding_batch_size": f"{ENV_PREFIX}EMBEDDING_BATCH_SIZE",
}

DEFAULT_VALUES: dict[str, Any] = {
    "config_file": None,
    "storage_dir": str(DEFAULT_STORAGE_DIR),
    "enable_stdio": True,
    "enable_http": True,
    "enable_sse": True,
    "enable_metrics": False,
    "enable_auth": False,
    "enable_semantic_search": DEFAULT_ENABLE_SEMANTIC_SEARCH,
    "auth_bearer_token": None,
    "auth_token_file": None,
    "auth_tokens": (),
    "http_host": DEFAULT_HTTP_HOST,
    "http_port": DEFAULT_HTTP_PORT,
    "http_socket_path": None,
    "http_path": DEFAULT_HTTP_PATH,
    "sse_path": DEFAULT_SSE_PATH,
    "metrics_path": DEFAULT_METRICS_PATH,
    "max_scratchpads": DEFAULT_MAX_SCRATCHPADS,
    "max_cells_per_pad": DEFAULT_MAX_CELLS_PER_PAD,
    "max_cell_bytes": DEFAULT_MAX_CELL_BYTES,
    "eviction_policy": DEFAULT_EVICTION_POLICY,
    "preempt_age": DEFAULT_PREEMPT_AGE,
    "preempt_interval": DEFAULT_PREEMPT_INTERVAL,
    "validation_request_timeout": DEFAULT_VALIDATION_TIMEOUT,
    "shutdown_timeout": DEFAULT_SHUTDOWN_TIMEOUT,
    "embedding_model": DEFAULT_EMBEDDING_MODEL,
    "embedding_device": DEFAULT_EMBEDDING_DEVICE,
    "embedding_batch_size": DEFAULT_EMBEDDING_BATCH_SIZE,
}


class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


@dataclass(slots=True)
class Config:
    """Configuration model for the Scratch Notebook MCP server."""

    storage_dir: Path
    enable_stdio: bool
    enable_http: bool
    enable_sse: bool
    enable_metrics: bool
    enable_auth: bool
    enable_semantic_search: bool
    auth_bearer_token: str | None
    auth_token_file: Path | None
    auth_tokens: dict[str, str]
    http_host: str
    http_port: int
    http_socket_path: Path | None
    http_path: str
    sse_path: str
    metrics_path: str
    max_scratchpads: int
    max_cells_per_pad: int
    max_cell_bytes: int
    eviction_policy: str
    preempt_age: timedelta
    preempt_interval: timedelta
    validation_request_timeout: timedelta
    shutdown_timeout: timedelta
    embedding_model: str
    embedding_device: str
    embedding_batch_size: int
    config_file: Path | None = None


def load_config(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Config:
    """Load configuration from CLI arguments, environment variables, and optional file."""

    parser = _build_arg_parser()
    parsed = parser.parse_args(argv)
    cli_values = {k: v for k, v in vars(parsed).items() if v is not None}

    env_values = _extract_env_values(environ or os.environ)

    config_path_value = cli_values.get("config_file") or env_values.get("config_file")
    file_values = _load_config_file(config_path_value)

    merged: dict[str, Any] = {}
    _merge_layer(merged, DEFAULT_VALUES)
    _merge_layer(merged, file_values)
    _merge_layer(merged, env_values)
    _merge_layer(merged, cli_values)

    config = _normalize_values(merged, config_path_value)

    _maybe_write_config_file(config)
    _maybe_write_auth_token_file(config)
    return config


def hot_reload_config(*_args: Any, **_kwargs: Any) -> None:
    """Explicitly prevent runtime configuration reloading."""

    raise ConfigError("Configuration can only be loaded during startup. Restart the server to apply changes.")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scratch-notebook",
        description="Scratch Notebook MCP server configuration flags.",
        add_help=False,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-h", "--help", action="help", help="Show this help message and exit.")
    parser.add_argument(
        "--config-file",
        dest="config_file",
        metavar="PATH",
        help="Path to a JSON configuration file. Default: none.",
    )
    parser.add_argument(
        "--storage-dir",
        dest="storage_dir",
        metavar="PATH",
        help=f"Directory for LanceDB storage (default: {DEFAULT_STORAGE_DIR}).",
    )

    parser.add_argument(
        "--enable-stdio",
        dest="enable_stdio",
        metavar="BOOL",
        help="Enable the MCP stdio transport (default: true).",
    )
    parser.add_argument(
        "--enable-http",
        dest="enable_http",
        metavar="BOOL",
        help="Enable the MCP HTTP endpoint (default: true). Disable for stdio-only runs.",
    )
    parser.add_argument(
        "--enable-sse",
        dest="enable_sse",
        metavar="BOOL",
        help="Enable the MCP SSE stream (default: true).",
    )
    parser.add_argument(
        "--enable-metrics",
        dest="enable_metrics",
        metavar="BOOL",
        help="Expose Prometheus metrics at /metrics (requires --enable-http true; default: false).",
    )
    parser.add_argument(
        "--enable-auth",
        dest="enable_auth",
        metavar="BOOL",
        help="Enable bearer-token authentication for HTTP/SSE transports (default: false).",
    )
    parser.add_argument(
        "--enable-semantic-search",
        dest="enable_semantic_search",
        metavar="BOOL",
        help="Toggle semantic search and embeddings (default: true).",
    )
    parser.add_argument(
        "--auth-bearer-token",
        dest="auth_bearer_token",
        metavar="TOKEN",
        help="Register a default bearer token for HTTP/SSE requests.",
    )
    parser.add_argument(
        "--auth-token-file",
        dest="auth_token_file",
        metavar="PATH",
        help="JSON file storing tenant:token mappings (created on first run).",
    )
    parser.add_argument(
        "--auth-token",
        dest="auth_tokens",
        action="append",
        metavar="PRINCIPAL:TOKEN",
        help="Add a bearer token mapping (may be repeated; CLI overrides file entries).",
    )

    parser.add_argument(
        "--http-host",
        dest="http_host",
        metavar="HOST",
        help=f"HTTP listener host (default: {DEFAULT_HTTP_HOST}).",
    )
    parser.add_argument(
        "--http-port",
        dest="http_port",
        metavar="PORT",
        help=f"HTTP listener port (default: {DEFAULT_HTTP_PORT}).",
    )
    parser.add_argument(
        "--http-socket-path",
        dest="http_socket_path",
        metavar="PATH",
        help="Unix domain socket path for the HTTP/SSE listener (optional).",
    )
    parser.add_argument(
        "--http-path",
        dest="http_path",
        metavar="PATH",
        help=f"HTTP RPC path for MCP requests (default: {DEFAULT_HTTP_PATH}).",
    )
    parser.add_argument(
        "--sse-path",
        dest="sse_path",
        metavar="PATH",
        help=f"SSE stream path for MCP events (default: {DEFAULT_SSE_PATH}).",
    )
    parser.add_argument(
        "--metrics-path",
        dest="metrics_path",
        metavar="PATH",
        help=f"Metrics endpoint path (default: {DEFAULT_METRICS_PATH}).",
    )

    parser.add_argument(
        "--max-scratchpads",
        dest="max_scratchpads",
        metavar="INT",
        help=f"Maximum scratchpads (0 for unlimited; default: {DEFAULT_MAX_SCRATCHPADS}).",
    )
    parser.add_argument(
        "--max-cells-per-pad",
        dest="max_cells_per_pad",
        metavar="INT",
        help=f"Maximum cells per scratchpad (0 for unlimited; default: {DEFAULT_MAX_CELLS_PER_PAD}).",
    )
    parser.add_argument(
        "--max-cell-bytes",
        dest="max_cell_bytes",
        metavar="INT",
        help=f"Maximum bytes per cell (0 for unlimited; default: {DEFAULT_MAX_CELL_BYTES}).",
    )
    parser.add_argument(
        "--eviction-policy",
        dest="eviction_policy",
        metavar="MODE",
        help="Eviction policy when at capacity (discard, fail, preempt). Default: discard.",
    )

    parser.add_argument("--preempt-age", dest="preempt_age", metavar="DURATION", help="Age threshold for preempt sweeper (default: 24h).")
    parser.add_argument("--preempt-interval", dest="preempt_interval", metavar="DURATION", help="Interval for preempt sweeper (default: 10m).")
    parser.add_argument(
        "--validation-request-timeout",
        dest="validation_request_timeout",
        metavar="DURATION",
        help="Timeout for scratch-validate requests (default: 10s).",
    )
    parser.add_argument("--shutdown-timeout", dest="shutdown_timeout", metavar="DURATION", help="Graceful shutdown timeout (default: 5s).")
    parser.add_argument("--embedding-model", dest="embedding_model", metavar="NAME", help=f"Embedding model identifier (default: {DEFAULT_EMBEDDING_MODEL}).")
    parser.add_argument("--embedding-device", dest="embedding_device", metavar="DEVICE", help=f"Embedding device (default: {DEFAULT_EMBEDDING_DEVICE}).")
    parser.add_argument(
        "--embedding-batch-size",
        dest="embedding_batch_size",
        metavar="INT",
        help=f"Embedding batch size (default: {DEFAULT_EMBEDDING_BATCH_SIZE}).",
    )

    return parser


def _extract_env_values(env: Mapping[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, env_name in ENV_FIELD_MAP.items():
        if env_name in env:
            values[field] = env[env_name]
    return values


def _load_config_file(path_value: str | Path | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = _parse_path(path_value, field="config_file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigError("Config file must contain a JSON object")
    result: dict[str, Any] = {k: v for k, v in data.items() if k in DEFAULT_VALUES}
    result["config_file"] = str(path)
    return result


def _merge_layer(base: MutableMapping[str, Any], overrides: Mapping[str, Any]) -> None:
    for key, value in overrides.items():
        if value is None:
            continue
        base[key] = value


def _normalize_values(values: Mapping[str, Any], config_path_value: str | Path | None) -> Config:
    storage_dir = _parse_path(values["storage_dir"], field="storage_dir")

    enable_stdio = _parse_bool(values.get("enable_stdio"), default=DEFAULT_VALUES["enable_stdio"])
    enable_http = _parse_bool(values.get("enable_http"), default=DEFAULT_VALUES["enable_http"])
    enable_sse = _parse_bool(values.get("enable_sse"), default=DEFAULT_VALUES["enable_sse"])
    enable_metrics = _parse_bool(values.get("enable_metrics"), default=DEFAULT_VALUES["enable_metrics"])
    enable_auth = _parse_bool(values.get("enable_auth"), default=DEFAULT_VALUES["enable_auth"])
    enable_semantic_search = _parse_bool(values.get("enable_semantic_search"), default=DEFAULT_VALUES["enable_semantic_search"])
    if enable_metrics and not enable_http:
        raise ConfigError("enable_metrics requires enable_http to be true")

    http_host = str(values.get("http_host", DEFAULT_VALUES["http_host"]))
    http_port = _parse_int(values.get("http_port", DEFAULT_VALUES["http_port"]), field="http_port", minimum=0, maximum=65535)

    http_socket_path = _parse_optional_path(values.get("http_socket_path"), field="http_socket_path")

    http_path = str(values.get("http_path", DEFAULT_VALUES["http_path"]))
    sse_path = str(values.get("sse_path", DEFAULT_VALUES["sse_path"]))
    metrics_path = str(values.get("metrics_path", DEFAULT_VALUES["metrics_path"]))

    if http_path == sse_path:
        raise ConfigError("http_path and sse_path must be distinct")

    max_scratchpads = _parse_int(values.get("max_scratchpads", DEFAULT_VALUES["max_scratchpads"]), field="max_scratchpads", minimum=0)
    max_cells_per_pad = _parse_int(values.get("max_cells_per_pad", DEFAULT_VALUES["max_cells_per_pad"]), field="max_cells_per_pad", minimum=0)
    max_cell_bytes = _parse_int(values.get("max_cell_bytes", DEFAULT_VALUES["max_cell_bytes"]), field="max_cell_bytes", minimum=0)

    eviction_policy = str(values.get("eviction_policy", DEFAULT_VALUES["eviction_policy"]).lower())
    if eviction_policy not in {"discard", "fail", "preempt"}:
        raise ConfigError("eviction_policy must be one of: discard, fail, preempt")

    preempt_age = _parse_duration(values.get("preempt_age", DEFAULT_VALUES["preempt_age"]), default_unit="h", field="preempt_age")
    preempt_interval = _parse_duration(values.get("preempt_interval", DEFAULT_VALUES["preempt_interval"]), default_unit="m", field="preempt_interval")
    validation_timeout = _parse_duration(
        values.get("validation_request_timeout", DEFAULT_VALUES["validation_request_timeout"]),
        default_unit="s",
        field="validation_request_timeout",
    )
    shutdown_timeout = _parse_duration(values.get("shutdown_timeout", DEFAULT_VALUES["shutdown_timeout"]), default_unit="s", field="shutdown_timeout")
    embedding_model = str(values.get("embedding_model", DEFAULT_VALUES["embedding_model"]))
    embedding_device = str(values.get("embedding_device", DEFAULT_VALUES["embedding_device"]))
    embedding_batch_size = _parse_int(values.get("embedding_batch_size", DEFAULT_VALUES["embedding_batch_size"]), field="embedding_batch_size", minimum=1)

    auth_bearer_token_value = values.get("auth_bearer_token")
    auth_bearer_token = str(auth_bearer_token_value) if auth_bearer_token_value is not None else None

    auth_token_file = _parse_optional_path(values.get("auth_token_file"), field="auth_token_file")
    persisted_tokens = _load_auth_token_registry(auth_token_file)
    raw_auth_tokens = values.get("auth_tokens")
    merged_tokens = dict(persisted_tokens)
    merged_tokens.update(_coerce_auth_tokens(raw_auth_tokens))
    if auth_bearer_token and "default" not in merged_tokens:
        merged_tokens["default"] = auth_bearer_token

    config_file_path = _parse_optional_path(config_path_value, field="config_file")

    return Config(
        storage_dir=storage_dir,
        enable_stdio=enable_stdio,
        enable_http=enable_http,
        enable_sse=enable_sse,
        enable_metrics=enable_metrics,
        enable_auth=enable_auth,
        enable_semantic_search=enable_semantic_search,
        auth_bearer_token=auth_bearer_token,
        auth_tokens=merged_tokens,
        http_host=http_host,
        http_port=http_port,
        http_socket_path=http_socket_path,
        http_path=http_path,
        sse_path=sse_path,
        metrics_path=metrics_path,
        max_scratchpads=max_scratchpads,
        max_cells_per_pad=max_cells_per_pad,
        max_cell_bytes=max_cell_bytes,
        eviction_policy=eviction_policy,
        preempt_age=preempt_age,
        preempt_interval=preempt_interval,
        validation_request_timeout=validation_timeout,
        shutdown_timeout=shutdown_timeout,
        embedding_model=embedding_model,
        embedding_device=embedding_device,
        embedding_batch_size=embedding_batch_size,
        config_file=config_file_path,
        auth_token_file=auth_token_file,
    )


def _maybe_write_config_file(config: Config) -> None:
    path = config.config_file
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return

    payload = _serialize_config(config)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _maybe_write_auth_token_file(config: Config) -> None:
    path = config.auth_token_file
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return

    payload = _serialize_auth_registry(config)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _serialize_config(config: Config) -> dict[str, Any]:
    return {
        "config_file": str(config.config_file) if config.config_file else None,
        "storage_dir": str(config.storage_dir),
        "enable_stdio": config.enable_stdio,
        "enable_http": config.enable_http,
        "enable_sse": config.enable_sse,
        "enable_metrics": config.enable_metrics,
        "enable_auth": config.enable_auth,
        "enable_semantic_search": config.enable_semantic_search,
        "auth_bearer_token": config.auth_bearer_token,
        "auth_token_file": str(config.auth_token_file) if config.auth_token_file else None,
        "http_host": config.http_host,
        "http_port": config.http_port,
        "http_socket_path": str(config.http_socket_path) if config.http_socket_path else None,
        "http_path": config.http_path,
        "sse_path": config.sse_path,
        "metrics_path": config.metrics_path,
        "max_scratchpads": config.max_scratchpads,
        "max_cells_per_pad": config.max_cells_per_pad,
        "max_cell_bytes": config.max_cell_bytes,
        "eviction_policy": config.eviction_policy,
        "preempt_age": _format_duration(config.preempt_age, preferred_unit="h"),
        "preempt_interval": _format_duration(config.preempt_interval, preferred_unit="m"),
        "validation_request_timeout": _format_duration(config.validation_request_timeout, preferred_unit="s"),
        "shutdown_timeout": _format_duration(config.shutdown_timeout, preferred_unit="s"),
        "embedding_model": config.embedding_model,
        "embedding_device": config.embedding_device,
        "embedding_batch_size": config.embedding_batch_size,
    }


def _serialize_auth_registry(config: Config) -> dict[str, Any]:
    registry: dict[str, str] = {}
    for principal, token in config.auth_tokens.items():
        registry[principal] = token
    if config.auth_bearer_token and "default" not in registry:
        registry["default"] = config.auth_bearer_token
    if registry:
        # deterministic ordering for file output
        registry = {key: registry[key] for key in sorted(registry)}
    return {"tokens": registry}


def _load_auth_token_registry(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Auth token file is not valid JSON: {path}") from exc
    tokens_section = payload.get("tokens")
    if tokens_section is None:
        return {}
    if not isinstance(tokens_section, Mapping):
        raise ConfigError("Auth token file must contain a 'tokens' object")
    registry: dict[str, str] = {}
    for principal, value in tokens_section.items():
        principal_str = str(principal).strip()
        if not principal_str:
            raise ConfigError("Auth token principals must be non-empty strings")
        if not isinstance(value, str):
            raise ConfigError("Auth token values must be strings")
        token_str = value.strip()
        if not token_str:
            raise ConfigError("Auth token values must be non-empty strings")
        registry[principal_str] = token_str
    return registry


def _coerce_auth_tokens(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        registry: dict[str, str] = {}
        for principal, token in raw.items():
            principal_str = str(principal).strip()
            token_str = str(token).strip()
            if not principal_str or not token_str:
                raise ConfigError("Auth token mappings must contain non-empty strings")
            registry[principal_str] = token_str
        return registry
    if isinstance(raw, str):
        principal, token = _parse_auth_token_entry(raw)
        return {principal: token}
    if isinstance(raw, Sequence):
        sequence_registry: dict[str, str] = {}
        for entry in raw:
            if not isinstance(entry, str):
                raise ConfigError("Auth token arguments must be strings")
            principal, token = _parse_auth_token_entry(entry)
            sequence_registry[principal] = token
        return sequence_registry
    raise ConfigError("Auth tokens must be provided as an object or array of strings")


def _parse_auth_token_entry(entry: str) -> tuple[str, str]:
    if ":" not in entry:
        raise ConfigError("Auth token arguments must use 'principal:token' syntax")
    principal, token = entry.split(":", 1)
    principal = principal.strip()
    token = token.strip()
    if not principal or not token:
        raise ConfigError("Auth token arguments must include non-empty principal and token")
    return principal, token


def _format_duration(duration: timedelta, *, preferred_unit: str) -> str:
    total_seconds = int(duration.total_seconds())
    units = {"s": 1, "m": 60, "h": 3600}
    factor = units.get(preferred_unit, 1)
    if factor and total_seconds % factor == 0:
        return f"{total_seconds // factor}{preferred_unit}"
    return f"{total_seconds}s"


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in BOOL_TRUE:
            return True
        if lowered in BOOL_FALSE:
            return False
    raise ConfigError(f"Invalid boolean value: {value!r}")


def _parse_int(value: Any, *, field: str, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        if isinstance(value, (int, float)):
            int_value = int(value)
        else:
            int_value = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid integer for {field}: {value!r}") from exc

    if minimum is not None and int_value < minimum:
        raise ConfigError(f"{field} must be >= {minimum}")
    if maximum is not None and int_value > maximum:
        raise ConfigError(f"{field} must be <= {maximum}")
    return int_value


def _parse_duration(value: Any, *, default_unit: str, field: str) -> timedelta:
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds < 0:
            raise ConfigError(f"{field} must be positive")
        return timedelta(seconds=seconds)
    if not isinstance(value, str):
        raise ConfigError(f"Invalid duration for {field}: {value!r}")

    stripped = value.strip()
    if not stripped:
        raise ConfigError(f"{field} may not be empty")

    unit = default_unit
    suffix = stripped[-1]
    number_part = stripped
    if suffix.lower() in T_DURATION_UNITS:
        unit = suffix.lower()
        number_part = stripped[:-1]
    if not number_part or not number_part.isdigit():
        raise ConfigError(f"{field} must be a positive integer optionally suffixed with s, m, or h")
    amount = int(number_part)
    if amount < 0:
        raise ConfigError(f"{field} must be non-negative")
    seconds = amount * T_DURATION_UNITS[unit]
    return timedelta(seconds=seconds)


def _parse_path(value: Any, *, field: str) -> Path:
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if not isinstance(value, str):
        raise ConfigError(f"Invalid path for {field}: {value!r}")
    stripped = value.strip()
    if not stripped:
        raise ConfigError(f"{field} may not be empty")
    return Path(stripped).expanduser().resolve()


def _parse_optional_path(value: Any, *, field: str) -> Path | None:
    if value in (None, ""):
        return None
    return _parse_path(value, field=field)
