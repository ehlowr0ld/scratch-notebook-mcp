# Research: Scratch Notebook MCP Server

## 1. Goals And Scope

The Scratch Notebook MCP server provides:

- A logical scratchpad abstraction, with each scratchpad identified by a UUID (`scratch_id`), scoped to a tenant, assigned to a namespace string, and containing an ordered list of typed cells that may carry per-cell tags.
- Language-aware validation for JSON, YAML, multiple programming languages, markdown, and plain text via specialized libraries.
- Durable persistence to a LanceDB-backed storage directory with strong deletion and eviction semantics, schema registry support, namespace registry operations, tagging filters, and semantic search via LanceDB vector indices and `sentence-transformers/all-MiniLM-L6-v2` embeddings.
- Multiple transports (stdio MCP, HTTP + SSE) with optional auth and basic observability.

This document captures technical choices that implement those goals while complying with:

- `specs/001-scratch-notebook-mcp/spec.md` (feature spec, precedence in conflicts).
- `specs/scratch-notepad-tool.md` (canonical technical and schema specification, read chronologically).
- `.specify/memory/constitution.md` (project constitution: exploration-first, security-first, non-blocking async, architectural boundaries).

## 2. Language, Runtime, And Packaging

### 2.1 Language And Runtime

- **Language**: Python 3.11+
- **Concurrency model**: `asyncio`
  - All I/O (file operations, network I/O) must be integrated with the event loop.
  - No `time.sleep()` or blocking I/O in async contexts; if blocking libraries are required, they must be isolated behind thread executors or replaced with async-capable alternatives.

### 2.2 MCP Server Framework

- **Framework**: `fastmcp` (per `scratch-notepad-tool.md` dependencies section).
- The server entrypoint will:
  - Construct a `FastMCP` instance with name `scratch-notebook`.
  - Register tools `scratch_create`, `scratch_read`, `scratch_append_cell`, `scratch_replace_cell`, `scratch_delete`, `scratch_list`, and `scratch_validate`, with request/response shapes matching the JSON Schemas defined in `scratch-notepad-tool.md`.
  - Expose a `main()` function so the package can be launched via `python -m scratch_notebook` or a console script.

### 2.3 Python Package Layout

The package `scratch_notebook` will be a normal Python distribution, likely managed via `pyproject.toml` with `tool.poetry` or PEP 621 metadata, and with:

- An importable module for MCP integration.
- A console script entrypoint (`scratch-notebook`) so that `uvx scratch-notebook` works once published.

## 3. Validation Stack

### 3.1 JSON And YAML

- **JSON parsing and schema validation**:
  - Use Python `json` module for syntax parsing.
  - Use `jsonschema` (as pinned in `scratch-notepad-tool.md`) for schema validation with the `referencing` library supplying a registry for shared schemas defined in scratchpad metadata.
  - Behavior:
    - If a cell has `language: "json"`:
      - Parse `content` with `json.loads()`.
      - If `json_schema` is present, validate using `jsonschema.validate(instance=data, schema=schema)`.
      - Errors from `JSONDecodeError` or `ValidationError` are mapped into `ValidationResult.errors`.
    - Shared schemas: scratchpad metadata may expose a `schemas` map; when a cell's `json_schema` contains `{"$ref": "scratchpad://schemas/<name>"}`, the resolver loads the referenced schema from that map before calling `jsonschema.validate()`. Missing references produce a `VALIDATION_ERROR` with a clear diagnostic.

- **YAML parsing and schema validation**:
  - Use `PyYAML` (`yaml.safe_load`) for syntax parsing.
  - If `json_schema` is present and the YAML parses, use `jsonschema.validate()` (with the same `referencing` registry support as JSON) on the resulting object.
  - Errors (syntax or schema) are mapped into `ValidationResult.errors` with code such as `SCHEMA_ERROR` or `SYNTAX_ERROR`.
  - Shared schema references resolve the same way as JSON, using the scratchpad metadata registry and failing validation if unresolved.

### 3.2 Code Languages (Via `syntax-checker`)

- **Library**: `syntax-checker` (version per `scratch-notepad-tool.md`).
- Supported languages: as enumerated in the schemas (for example `py`, `js`, `ts`, `tsx`, `jsx`, `rs`, `c`, `cpp`, `sh`, `css`, `html`, `java`, `go`, `rb`, `toml`, `php`, `cs`, etc.).
- Behavior:
  - For cells with code languages:
    - Call `syntax-checker` with `(language, content)`.
    - Interpret its diagnostics to populate:
      - `errors` (fatal syntax errors, with `line`, `column`, `message`, `code`).
      - `warnings` (non-fatal diagnostics).
      - `details.syntax` summarizing whether syntax was checked and whether it passed.
  - A cell is considered `valid: true` if there are no errors.

### 3.3 Markdown (`markdown-analysis`)

- **Library**: `markdown-analysis` (version per `scratch-notepad-tool.md`).
- Behavior:
  - For cells with `language: "md"`:
    - Run the analysis to collect style issues, structural problems, or link checks where supported.
    - Map non-fatal issues to `warnings` and overall analysis summary into `details.analysis`.
    - Markdown is typically considered `valid: true` unless the library exposes explicit fatal error semantics.

### 3.4 Plain Text

- For `language: "txt"`:
  - No structural validation is performed.
  - Validation always returns `valid: true` with `details.reason` explaining that no validation was performed, matching the behavior described in `scratch-notepad-tool.md`.

### 3.5 Validation Modes

- **Automatic**:
  - Triggered when a cell is appended or replaced and `validate` is set `true`.
  - Implementations may store validation results or return them inline; the canonical detailed results are from `scratch_validate`.

- **Manual (`scratch_validate`)**:
  - Accepts a `scratch_id` and optional `indices`.
  - Validates all or specified cells, returning a `results` array of `ValidationResult` objects, as defined in `scratch-notepad-tool.md`.

## 4. Storage And Persistence

### 4.1 Rationale for LanceDB

- Requirements now include namespace/tag filtering and semantic search with vector similarity. LanceDB provides:
  - Embedded operation (no external service) with Arrow-backed columns and vector indices.
  - ACID-like appends/commits suitable for durability requirements.
  - Filtering expressions (DataFusion SQL) across scalar and nested columns, enabling namespace/tag queries without full in-memory scans.
  - Vector indexing and disk persistence compatible with `sentence-transformers` embeddings.
- Alternatives considered:
  - SQLite + `sqlite-vss`: attractive but requires bundling C extensions and coordinating feature flags; LanceDB offers simpler Python-first API.
  - Chroma/Weaviate: heavier runtime dependencies and background services, violating single-package distribution requirements.

### 4.2 Dataset Layout

- Primary LanceDB dataset (`scratchpads.lance`) with tables:
  - `scratchpads`: columns `scratch_id` (UUID, pk), `tenant_id`, `namespace`, `tags` (list<string>), `metadata` (struct), `cell_tags_cache` (list<string> for denormalized queries), `cells` (struct array), `schemas` (struct array), timestamps.
  - `cells`: optional normalized table for rapid per-cell updates with columns `scratch_id`, `cell_id`, `index`, `language`, `content`, `tags`, `validate`, `metadata`.
  - `namespaces`: stores namespace strings per tenant with creation date for namespaces created before any scratchpad exists.
  - `embeddings`: vector column (for example dimension 384) plus metadata referencing `(scratch_id, cell_id)` and caching namespace/tags for pre-filtering.
- Each table is stored in Lance columnar format; indexes (for example IVF, HNSW) may be created on embeddings for fast similarity search.

### 4.3 Access and Mutation Strategy

- CRUD operations for scratchpads use DataFusion SQL predicates; example: `table.to_table().filter(col("tenant_id") == tenant & col("namespace").isin(namespaces))`.
- Updates apply via `delete + write` semantics within a single committed transaction to maintain atomicity across scratchpad, cell, and embedding tables.
- Namespace create/rename/delete operations update both `namespaces` and `scratchpads` tables, cascading deletes when requested.
- Tag mutations update scratchpad-level `tags` and ensure derived `cell_tags_cache` matches union of cell tags.

### 4.4 Durability

- After every mutation the implementation must call `table.commit()` (or equivalent) to force LanceDB to flush manifests and data files.
- Crash recovery simply reopens the dataset; uncommitted data is rolled back automatically because commit was not invoked.

### 4.5 Unique Constraints

- Primary key uniqueness is enforced by driver logic prior to insert; LanceDB does not yet enforce uniqueness, so the storage layer must query for existing keys and raise `INVALID_ID` if duplicates are detected.
- Namespace uniqueness per tenant is enforced similarly, preventing accidental duplicates from CLI/API calls.

### 4.6 Semantic Search Pipeline

- Embeddings are generated using `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional). The embedding service runs asynchronously and caches model weights on disk inside the storage directory.
- When a scratchpad or cell changes content, the storage layer enqueues re-embedding jobs that update the `embeddings` table transactionally with the scratchpad write.
- The `embeddings` table stores vector data plus scalar metadata (tenant, namespace, tags, language, last_updated) so LanceDB can pre-filter hits before running distance calculations.
- Queries call `table.search(query_vector, filter=...)` with filters derived from namespace/tag parameters. Returned hits are merged with scratchpad metadata to produce response payloads with snippets and similarity scores.

## 5. Capacity, Eviction, And Retention

### 5.1 Capacity Limit

- Configurable `max_scratchpads` (integer; `0` means unlimited; default `1024`).
- Capacity is defined in terms of scratchpad count, not total storage size.
- When creating a new scratchpad and the limit would be exceeded:
  - Behavior is controlled by `eviction_policy`:
    - `discard` (default): evict one or more existing scratchpads to make room.
    - `fail`: reject the new creation without eviction, returning `CAPACITY_LIMIT_REACHED`.
    - `preempt`: background sweeper removes stale scratchpads regardless of instantaneous capacity (see below).

### 5.2 Eviction Ordering (Discard)

- In `discard` mode:
  - Use a least-recently-used policy based on last read/write access timestamp, with ties broken by oldest creation time.
  - When eviction happens, the creation response must indicate that it occurred and which scratchpads were removed.

### 5.3 Preemptive Sweeper (`preempt`)

- When `eviction_policy = "preempt"`:
  - A background sweeper runs at interval `preempt_interval` (default 10 minutes):
    - `preempt_interval` uses the standard time-unit suffix scheme (integer + optional `s`, `m`, `h`), default unit documented per spec.
  - For each scratchpad:
    - If `now - last_access_time` > `preempt_age`, the scratchpad is deleted.
    - `preempt_age` uses the same time suffix format; default unit is hours when no suffix is provided.
  - The sweeper operates regardless of current `max_scratchpads` occupancy; it may delete scratchpads even when under capacity, but must never delete scratchpads more recent than `preempt_age`.

### 5.4 Size Limits

- In addition to `max_scratchpads`, the server should support:
  - `max_cells_per_pad` (0 = unlimited; default around 1024).
  - `max_cell_bytes` (0 = unlimited; default around 1 MiB).
- If an operation would exceed these limits, it fails with a clear error and does not partially apply changes.

## 6. Transports, Auth, And Config

### 6.1 Transports

- **Stdio MCP**:
  - Always supported; can be disabled only by configuration if desired, but default is enabled for local use.

- **HTTP + SSE listener**:
  - Shared listener config with:
    - `http_host` (default `127.0.0.1`).
    - `http_port` (default high, non-reserved port such as 8765).
    - Optional Unix domain socket path (`http_socket_path`).
  - HTTP RPC and SSE share the same listener but different paths:
    - Defaults: `/http` for HTTP RPC and `/sse` for SSE.
    - Config must ensure the paths do not collide; same URIs used across TCP and Unix socket.
  - Transports can be enabled/disabled individually:
    - `enable_stdio`, `enable_http`, `enable_sse`.

### 6.2 Auth And Tenant Isolation

- Default single-user mode:
  - When bound only to `127.0.0.1` and `enable_http`/`enable_sse` are used for local tools, the server may run without explicit auth.
- Multi-tenant / remote mode:
  - HTTP/SSE endpoints should support bearer-token auth:
    - Header: `Authorization: Bearer <token>`.
  - Each scratchpad is associated with an authenticated principal; all operations must enforce that only the owning principal can see or manipulate its scratchpads.
  - The server must not reveal existence of other tenants' scratchpads based on guessed UUIDs alone.

### 6.3 Configuration Sources

- Command-line flags, environment variables, and optional JSON config file:
  - Config file must be valid JSON with a mapping of options; numeric-like strings must be parsed to numeric types, failing on invalid or empty values.
  - On startup, if a config file path is supplied but the file does not exist, create any missing parent directories and write the effective configuration (defaults merged with CLI/env overrides) into that file before proceeding.
  - All time-like settings use a string `integer[unit]` form with well-defined defaults for missing units.
- Auth token registry:
  - CLI supports repeating `--auth-token principal:token` flags; later occurrences override earlier entries, and the final CLI set overlays (not replaces) any entries loaded from the token file.
  - When an auth token file path is configured, load its JSON mapping (token→principal). If the file is missing, create parent directories as needed and write the merged registry (CLI/env entries overriding defaults and file entries on conflicts) into the new file.
  - If no token file path is provided, operate entirely from defaults plus CLI/env overrides without creating files.
- Schema registry:
  - Stored under `scratchpad.metadata.schemas`, keyed by a stable identifier. Each entry contains `id` (UUID), `description` (string), and `schema` (JSON Schema object).
  - New MCP tools will list schemas for a scratchpad, fetch a specific schema by `scratch_id` + `schema_id`, and create/update schema entries. Updates validate payloads before persistence and enforce tenant scoping.
  - All schema definitions (inline on cells or stored in metadata) must parse as JSON objects and pass JSON Schema structural validation prior to acceptance.
- Namespace registry:
  - Namespaces can be created ahead of scratchpads using a dedicated MCP tool; configuration MAY seed default namespaces per tenant.
  - Enabling auth after operating without it triggers a migration that reassigns scratchpads from the implicit default tenant to the first configured tenant; behavior must be logged and documented.
- Cell discovery:
  - `scratch_read` gains optional `cell_ids`, `tags`, and `include_metadata` parameters with intersection semantics when both `cell_ids` and `tags` are supplied.
  - `scratch_list_cells` adds `cell_ids` and `tags` filters so navigation UIs can show only relevant cells without full content payloads.
- Semantic search:
  - Configurable enable flag (`enable_semantic_search`, default `true`), embedding model path (default `sentence-transformers/all-MiniLM-L6-v2`), maximum hits per query, and an optional background re-embedding interval.
- Config evaluation:
  - Per NFR-015, configuration is loaded at startup only.
  - No hot reload is required; config changes take effect after restart.

## 7. Observability, Logging, And Metrics

### 7.1 Logging

- Logging must be:
  - Structured and machine parsable.
  - Emitted to stdout and/or stderr only (the server does not create its own rotating log files).
  - Cover:
    - Errors and exceptions (`code`, `message`, minimal context).
    - Validation failures.
    - Eviction events (discard/preempt).
    - Capacity limit violations, config errors, startup/shutdown events.

- Error codes:
  - Defined centrally in `scratch_notebook.errors` as constants with brief comments.
  - At minimum: `NOT_FOUND`, `INVALID_ID`, `INVALID_INDEX`, `CAPACITY_LIMIT_REACHED`, `VALIDATION_ERROR`, `VALIDATION_TIMEOUT`, `CONFIG_ERROR`, `INTERNAL_ERROR`.
  - All error responses and log records must include a code and message.

### 7.2 Metrics

- Optional `/metrics` endpoint:
  - If enabled, exposed on the HTTP listener at `/metrics`.
  - Prometheus-compatible text exposition format.
  - Includes at least:
    - Total scratch operations by type (create/read/append/replace/delete/list/validate).
    - Total errors.
    - Total evictions (discard vs preempt).
    - Uptime in seconds.
  - This endpoint is not required but recommended for long-running deployments.

## 8. Shutdown Semantics

- **Graceful shutdown**:
  - On shutdown signal:
    - Stop accepting new connections and operations.
    - Return a clear error to new requests (for example an HTTP 503 with a message, or a tool error over MCP).
    - Wait up to `shutdown_timeout` (default 5 seconds, configurable using the standard time-unit format) for in-flight operations to complete.
    - After timeout, abort remaining operations and exit.

- This behaviour is essential to maintain consistency (especially given durability guarantees) while not blocking shutdown indefinitely.

## 9. Open Questions And Implementation Risks

Non-blocking but notable implementation risks:

- **Validation performance for very large cells**:
  - JSON/YAML schema validation or syntax-checker on very large documents may be expensive; the `validation_request_timeout` must be respected, and large inputs may need additional safeguards (for example streaming or size checks).

- **Error surface vs user experience**:
  - The error code taxonomy and messages must be carefully curated so they are useful for debugging but not overwhelming when surfaced to agents.

At this point, all major design questions raised during clarification have been resolved; further clarifications should be handled as incremental amendments rather than blocking implementation.

- Canonical metadata fields (`title`, `description`, optional `summary`) are stored alongside scratchpads and contribute to semantic search snippets. To conserve context tokens, `scratch_list` exposes only `scratch_id`, `title`, `description`, and `cell_count`; agents fetch `summary`, tags, and other metadata via `scratch_read`, which will offer an `include_metadata` toggle for large notebooks. Additional metadata remains opaque.
- A `scratch_list_tags` tool enumerates deduplicated scratchpad-level tags and cell-level tags, optionally filtered by namespace, using LanceDB queries rather than vector indices.
