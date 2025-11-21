# Quickstart: Scratch Notebook MCP Server

This guide explains how to install, configure, and use the Scratch Notebook MCP server as specified in `spec.md` and `scratch-notepad-tool.md`.

## 1. Install And Run

### 1.1 Prerequisites

- Python 3.11+ available on your system.
- A virtual environment for the project (recommended).

Example:

```bash
cd /home/rafael/Workspace/Repos/rafael/scratch-notebook
python -m venv .venv
source .venv/bin/activate
```

### 1.2 Install Dependencies

Once the package metadata (`pyproject.toml` or equivalent) is defined, install the local package in editable mode:

```bash
pip install -e .
```

This will install `scratch-notebook` and its dependencies (`fastmcp`, `jsonschema`, `PyYAML`, `syntax-checker`, `markdown-analysis`, `referencing`, `lancedb`, `sentence-transformers`, etc.).

### 1.3 Start The Server

From the repository root (with the virtual environment active):

```bash
python -m scratch_notebook \
  --storage-dir /tmp/scratch-notebook-data \
  --max-scratchpads 1024
```

The exact CLI flags will be implemented according to the configuration surface described in `contracts/transports-and-config.md`, but minimally:

- `--storage-dir` (required or defaulted): where scratchpads are persisted.
- Optional flags to control transports, capacity, eviction, timeouts, semantic search, and namespace behavior.
- Semantic search defaults can be tuned with `--enable-semantic-search/--disable-semantic-search`, `--embedding-model sentence-transformers/all-MiniLM-L6-v2`, and optional device/batch flags.
- Multiple `--auth-token tenant:secret` flags merge with (and override) entries from `--auth-token-file`. When either file flag is provided, the server materializes the file with the effective configuration before continuing.

On startup, the server will:

- Create the storage directory if it does not exist (or fail fast with a config error).
- Start the stdio MCP server by default.
- Start an HTTP listener on `127.0.0.1:8765` (or configured host/port) with default paths `/http` and `/sse` if HTTP/SSE are enabled.

## 2. Configure Transports

### 2.1 Defaults

By default, the server MUST behave as specified in `spec.md` and `contracts/transports-and-config.md`:

- `enable_stdio = true`
- `enable_http = true`
- `enable_sse = true`
- `http_host = "127.0.0.1"`
- `http_port = 8765` (or another high, non-reserved port)
- `http_path = "/http"`
- `sse_path = "/sse"`
- `enable_metrics = false`
- `metrics_path = "/metrics"` (used only when `enable_metrics` is set to true)
- Metrics require the HTTP listener. If you pass `--enable-metrics true` while `--enable-http false`, config loading fails fast so stdio-only runs stay safe. You can still disable SSE when metrics are on; only HTTP transport is required for `/metrics`.
- Time-based flags such as `--preempt-age`, `--preempt-interval`, `--validation-request-timeout`, and `--shutdown-timeout` accept the standard `integer + suffix` pattern (`30s`, `15m`, `24h`). When you omit a suffix the parser falls back to the spec defaults (seconds for timeouts, minutes or hours for sweepers). Invalid strings raise `CONFIG_ERROR` before startup continues.

### 2.2 Example: HTTP-Only Local Server

```bash
python -m scratch_notebook \
  --storage-dir /tmp/scratch-notebook-data \
  --enable-stdio false \
  --enable-http true \
  --enable-sse true \
  --http-host 127.0.0.1 \
  --http-port 8765 \
  --http-path /http \
  --sse-path /sse
```

### 2.3 Example: Add Unix Domain Socket

```bash
python -m scratch_notebook \
  --storage-dir /tmp/scratch-notebook-data \
  --http-host 127.0.0.1 \
  --http-port 8765 \
  --http-socket-path /tmp/scratch-notebook.sock
```

In this configuration, HTTP and SSE listen on both TCP and the Unix socket; URIs (`/http`, `/sse`, `/metrics`) are shared across interfaces.

### 2.4 First-Time Auth Enablement

If you previously ran the server without auth and now enable bearer tokens, the server automatically reassigns all scratchpads owned by the implicit default tenant to the first tenant defined by CLI flags (or, if none, the first entry in the auth token file). A structured log entry documents the migration; review it and adjust namespace/tag defaults as needed before admitting new tenants.

## 3. Basic Workflow With MCP Tools

### 3.1 Create A Scratchpad

Call the `scratch_create` tool (via MCP client or HTTP wrapper):

```json
{
  "tool": "scratch_create",
  "params": {
    "scratch_id": "2c67d0b4-84e2-4b59-a7f2-2b8b4e75d0c1",
    "metadata": {
      "title": "Experiment",
      "description": "Drafting JSON and markdown snippets",
      "summary": "Experiment scratchpad for config exploration",
      "namespace": "experiments",
      "tags": ["ml", "baseline"],
      "note": "Temporary configuration draft"
    },
    "cells": [
      {
        "language": "json",
        "content": "{ \"seeded\": true }",
        "metadata": { "tags": ["boot"] },
        "validate": true
      }
    ]
  }
}
```

The response includes a normalized metadata block plus a lightweight `cells` array containing ids, indices, language, validation flags, and metadata/tags. Cell `content` is intentionally omitted from write responses to keep tokens low; issue `scratch_read` whenever you need the full notebook payload immediately after creation. Canonical fields (`title`, `description`, optional `summary`) are also surfaced at the top level of the returned scratchpad to support lean listings.

> **Canonical metadata tone**
>
> - `title`: short (≤60 characters), action-oriented (“Experiment deployment plan”).
> - `description`: one or two full sentences giving humans enough context to choose the scratchpad.
> - `summary`: terse synopsis optimised for semantic search snippets (key nouns/verbs, avoid filler).
>
> When agents populate these fields consistently, `scratch_list` stays low-token while `scratch_search` can deliver meaningful snippets.

### 3.2 Append Cells

Append a JSON cell:

```json
{
  "tool": "scratch_append_cell",
  "params": {
    "scratch_id": "2c67d0b4-84e2-4b59-a7f2-2b8b4e75d0c1",
    "cell": {
      "language": "json",
      "content": "{ \"name\": \"example\", \"enabled\": true }",
      "validate": true
    }
  }
}
```

Append a markdown cell:

```json
{
  "tool": "scratch_append_cell",
  "params": {
    "scratch_id": "2c67d0b4-84e2-4b59-a7f2-2b8b4e75d0c1",
    "cell": {
      "language": "md",
      "content": "# Notes\n\n- First idea\n- Second idea",
      "validate": true
    }
  }
}
```

Append/replace responses mirror `scratch_create`: they confirm the updated structure (ids, indices, tags, metadata, validation output) but do not echo the raw cell content.

Need to move a cell? Call `scratch_replace_cell` with the target `cell_id` plus the new content and (optionally) `new_index`. The server updates the cell and shifts neighbours so indices stay contiguous, while `cell_id` remains the only identifier you ever pass to mutations.

### 3.3 Validate Cells

Validate all cells:

```json
{
  "tool": "scratch_validate",
  "params": {
    "scratch_id": "2c67d0b4-84e2-4b59-a7f2-2b8b4e75d0c1"
  }
}
```

Validation results are advisory: the server never discards or rolls back stored cells because of diagnostics. Supply `cell_ids` in `params` when you want to re-check specific cells; indices are returned for reference but are not accepted as selectors.

### 3.6 Manage Namespaces

Create a namespace (idempotent):

```json
{
  "tool": "scratch_namespace_create",
  "params": {
    "namespace": "design"
  }
}
```

List namespaces with scratchpad counts:

```json
{
  "tool": "scratch_namespace_list",
  "params": {}
}
```

Rename a namespace and cascade scratchpads:

```json
{
  "tool": "scratch_namespace_rename",
  "params": {
    "old_namespace": "design",
    "new_namespace": "ux",
    "migrate_scratchpads": true
  }
}
```

Delete a namespace without deleting scratchpads (fails when pads still reference it):

```json
{
  "tool": "scratch_namespace_delete",
  "params": {
    "namespace": "archive",
    "delete_scratchpads": false
  }
}
```

### 3.7 Filter by Tags

Read only cells tagged `model` (metadata omitted):

```json
{
  "tool": "scratch_read",
  "params": {
    "scratch_id": "2c67d0b4-84e2-4b59-a7f2-2b8b4e75d0c1",
    "tags": ["model"],
    "include_metadata": false
  }
}
```

Indices in the response show where each cell sits within the notebook, but you always target cells by `cell_id`. Combine `cell_ids` with the optional `tags` filter when you want an intersection of specific cells and tag categories.

List scratchpads in the `experiments` namespace with `ml` tags:

```json
{
  "tool": "scratch_list",
  "params": {
    "namespaces": ["experiments"],
    "tags": ["ml"]
  }
}
```

The response includes each scratchpad's `scratch_id`, `title`, `description`, and `cell_count`. Fetch richer metadata (including `summary`, tags, namespace context, and schema registry entries) with `scratch_read`; add `"include_metadata": false` when you only need cell payloads.

List cells matching explicit ids and tags:

```json
{
  "tool": "scratch_list_cells",
  "params": {
    "scratch_id": "2c67d0b4-84e2-4b59-a7f2-2b8b4e75d0c1",
    "cell_ids": ["a95fab24-0e4a-4a4d-8ad4-47a46c3cb4ed"],
    "tags": ["baseline"]
  }
}
```

### 3.8 Semantic Search

Search across scratchpads for "deploy configuration" limited to the `release` namespace:

```json
{
  "tool": "scratch_search",
  "params": {
    "query": "deploy configuration",
    "namespaces": ["release"],
    "tags": ["deployment"],
    "limit": 5
  }
}
```

The response contains `hits` with `scratch_id`, optional `cell_id`, similarity `score`, `namespace`, matching `tags`, and a `snippet` preview.

List all tags in use (deduplicated across scratchpads vs cells):

```json
{
  "tool": "scratch_list_tags",
  "params": {}
}
```

Restrict tag listing to specific namespaces:

```json
{
  "tool": "scratch_list_tags",
  "params": {
    "namespaces": ["experiments"]
  }
}
```
