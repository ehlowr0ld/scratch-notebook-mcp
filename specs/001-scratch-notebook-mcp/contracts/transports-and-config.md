# Contracts: Transports, Config, And HTTP/SSE Surface

This document defines the configuration and transport contracts for the Scratch Notebook MCP server, including HTTP/SSE endpoints, configuration keys, and metrics.

## 1. Transports Overview

The server supports the standard MCP transports:

- **Stdio MCP** – primary integration for local tools (MCP over stdio).
- **HTTP + SSE MCP** – the HTTP-based MCP transport, where:
  - HTTP POST is used for MCP requests.
  - SSE is used for the MCP event stream (for example, streaming outputs or MCP-level notifications), not for a separate, custom application-specific event channel.

Each MCP transport can be enabled or disabled via configuration; defaults are chosen to be safe for local use.

## 2. Configuration Surface

Configuration can be provided via:

- Command-line arguments.
- Environment variables.
- Optional JSON config file (`config_file`), which must contain a JSON object mapping option names to values. JSON parsing must respect the required numeric and boolean types (string values must be converted and rejected on invalid input).

Changes to configuration take effect on restart only; no hot reloading is required.

### 2.1 Core Options

**Storage**

- `storage_dir: string`
  - Root directory for LanceDB datasets used by the server.
  - On startup the server creates the directory (including parents) if it is missing; otherwise startup fails with a clear `CONFIG_ERROR`.
  - Scratchpads, schemas, namespaces, and embeddings are persisted exclusively inside LanceDB tables under this directory.

**Capacity And Limits**

- `max_scratchpads: int` (0 = unlimited; default 1024)
- `max_cells_per_pad: int` (0 = unlimited; default ~1024)
- `max_cell_bytes: int` (0 = unlimited; default ~1 MiB)
- `eviction_policy: string`
  - Allowed values: `"discard"`, `"fail"`, `"preempt"` (if implemented).

**Time-Based Settings**

All time-based options use the standard `integer[unit]` string format:

- Unit suffix: `s` (seconds), `m` (minutes), `h` (hours).
- Default unit when omitted:
  - Age-like settings (for example `preempt_age`): hours.
  - Timeout-like settings (for example `validation_request_timeout`, `shutdown_timeout`): seconds.

Time-based options include (non-exhaustive):

- `preempt_age: string` (for example `"24h"`, `"30m"`, `"600s"`)
- `preempt_interval: string` (default `"10m"`)
- `validation_request_timeout: string` (for example `"10s"`)
- `shutdown_timeout: string` (default `"5s"`)

### 2.2 Transport Options

**Transport Enables**

- `enable_stdio: bool` (default `true`)
- `enable_http: bool` (default `true`)
- `enable_sse: bool` (default `true`)

**HTTP/SSE Listener (Shared)**

- `http_host: string` (default `"127.0.0.1"`)
- `http_port: int` (default high, non-reserved port such as `8765`)
- `http_socket_path: string` (optional; Unix domain socket)

**Paths**

- `http_path: string` (default `"/http"`) – HTTP endpoint for MCP requests.
- `sse_path: string` (default `"/sse"`) – SSE endpoint for the MCP event stream.
- `metrics_path: string` (default `"/metrics"`) – Prometheus endpoint, if enabled.

Validation rules:

- `http_path` and `sse_path` must not be equal.
- Paths apply consistently across TCP (`http_host`/`http_port`) and Unix socket (`http_socket_path`).

**Metrics Enable**

- `enable_metrics: bool` (default `false`)
  - When `true`, the `/metrics` endpoint is exposed at `metrics_path`.
  - When `false`, no metrics endpoint is served.

**Semantic Search**

- `enable_semantic_search: bool` (default `true`)
- `embedding_model: string` (default `"sentence-transformers/all-MiniLM-L6-v2"`)
- `embedding_batch_size: int` (optional; defaults to library heuristic)
- `embedding_device: string` (optional; `"cpu"` by default, operators may set to `"cuda"` or similar)
- `semantic_search_limit: int` (optional; server-wide maximum hits per query)

### 2.3 Auth And Security

Auth is optional but recommended for remote use:

- `enable_auth: bool` (default `false` for local-only usage)
- `auth_bearer_token: string` or alternate mechanism (for example token validation callback in code)

Behavioral expectations:

- When `enable_auth` is `false` and listeners are bound only to `127.0.0.1`, the server may operate as a single-user local tool.
- When `enable_auth` is `true`:
  - HTTP/SSE requests must include an `Authorization: Bearer <token>` header (or equivalent).
  - Scratchpads must be associated with a principal derived from auth context; all operations must enforce per-principal isolation.

- First-time auth enablement:
  - When the server detects existing scratchpads without explicit tenants and a new auth configuration is provided, it reassigns those scratchpads to the first tenant defined by CLI or auth file order.
  - A structured log entry is emitted summarizing the migration, and operator docs MUST describe the behavior and recovery steps.

## 3. HTTP API Contract

All HTTP endpoints share:

- JSON request and response bodies matching the MCP tool request/response shapes where applicable.
- Standard HTTP status codes:
  - 200 for success.
  - 4xx for client errors (for example `400`, `401`, `403`, `404`).
  - 5xx for server errors (for example `500`).

### 3.1 HTTP RPC Endpoint (`http_path`)

**Path**: `http_path` (default `/http`)
**Method**: `POST`
**Content-Type**: `application/json`

**Request body (conceptual)**:

```json
{
  "tool": "scratch_create | scratch_read | scratch_append_cell | scratch_replace_cell | scratch_delete | scratch_list | scratch_validate",
  "params": { ... }
}
```

- `tool` must be one of the supported MCP tools.
- `params` must conform to the corresponding tool's request schema.

**Response body**:

```json
{
  "ok": true or false,
  "result": { ... },   // tool-specific data when ok is true
  "error": { ... }     // ErrorResult when ok is false
}
```

- `result` encapsulates the appropriate response object (`scratchpad`, `results`, etc).

This mapping mirrors MCP semantics in a simple HTTP wrapper; precise shape may be refined to match fastmcp conventions if needed (for example `{"tool":"...","data":{...}}`).

### 3.2 SSE Endpoint (`sse_path`)

**Path**: `sse_path` (default `/sse`)
**Method**: `GET`
**Protocol**: Server-Sent Events (MCP HTTP+SSE transport)

The SSE endpoint is part of the MCP HTTP transport and is used to carry MCP protocol messages (for example streaming tool outputs or MCP-level notifications) as defined by the MCP specification and by `fastmcp`. It is **not** a separate, ad hoc application event API; any application-specific signals (such as eviction information) must flow through the MCP protocol (for example as tool results or MCP notifications) rather than through a custom SSE message schema defined here.

## 4. Metrics Endpoint

**Path**: `metrics_path` (default `/metrics`)
**Method**: `GET`
**Content-Type**: `text/plain; version=0.0.4` (Prometheus text format)

**Metrics to expose (minimum)**:

- Counters:
  - `scratch_notebook_ops_total{op="create|read|append|replace|delete|list|validate"}`
  - `scratch_notebook_errors_total{code="..."}`
  - `scratch_notebook_evictions_total{policy="discard|preempt"}`
- Gauges:
  - `scratch_notebook_scratchpads_current`
  - `scratch_notebook_cells_current`
- Uptime:
  - `scratch_notebook_uptime_seconds`

Metrics are optional but must use Prometheus conventions if exposed. Whether the endpoint is exposed is controlled by `enable_metrics`; by default (when `enable_metrics` is not set or is false) no metrics endpoint is served.

## 5. Graceful Shutdown Behavior

When a shutdown signal is received:

1. The server stops accepting new HTTP/SSE connections and MCP requests.
2. New HTTP requests should receive an appropriate 503 or similar status, with a JSON error using `CONFIG_ERROR` or a specific shutdown-related code.
3. In-flight requests are allowed to complete up to `shutdown_timeout` (default 5 seconds; configurable).
4. After `shutdown_timeout`, remaining requests may be interrupted to allow the process to exit.

This behavior must be consistent across stdio and HTTP/SSE transports.

## 6. Error Handling And HTTP Status Mapping

Error codes from the MCP layer must be mapped to HTTP status codes as follows (recommended):

- `NOT_FOUND` → 404
- `INVALID_ID`, `INVALID_INDEX`, `CONFIG_ERROR`, `VALIDATION_ERROR` → 400
- `VALIDATION_TIMEOUT` → 408 or 503 (depending on context; spec should choose one and stick to it)
- `CAPACITY_LIMIT_REACHED` → 409 (Conflict) or 429 (Too Many Requests)
- `UNAUTHORIZED` (if used) → 401 or 403
- `INTERNAL_ERROR` → 500

The HTTP body for errors must still include an `error` object with `code` and `message` so behavior is consistent across transports.

## 7. Alignment With Spec And Technical Document

The transport and config behavior documented here is derived from:

- `specs/001-scratch-notebook-mcp/spec.md` NFR-005, NFR-006, NFR-007, NFR-009, NFR-010, NFR-011, NFR-017 and related clarifications.
- `specs/scratch-notepad-tool.md` sections on tool specification, transport expectations, and "Latest Design Decisions".

Any future changes to:

- Listener addressing (host/port/socket).
- Path conventions (`/http`, `/sse`, `/metrics`).
- Auth requirements.
- Metrics format.

must be updated here and in the relevant parts of `spec.md` and `scratch-notepad-tool.md` to avoid drift.
