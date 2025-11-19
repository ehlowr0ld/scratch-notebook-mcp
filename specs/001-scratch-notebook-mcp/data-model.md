# Data Model: Scratch Notebook MCP Server

This document consolidates the logical data model for the Scratch Notebook MCP server.
Canonical JSON Schemas are defined in `specs/scratch-notepad-tool.md` (see the "Schemas and definitions" section); this document summarizes their structure and semantics and ties them back to the feature spec.

## 1. Core Entities

### 1.1 Scratch Notebook Entry (`Scratchpad`)

**Concept**

- Represents a logical scratch notebook identified by a UUID `scratch_id`.
- Contains an ordered list of cells and optional metadata.
- Backed by durable storage in the configured storage directory; physical representation is internal.

**Key fields (conceptual)**

- `scratch_id: string`
  - UUID string (for example UUIDv4).
  - Logical identifier; clients never see file paths.
- `tenant_id: string`
  - Internal identifier derived from auth (or the implicit default tenant when auth is disabled).
- `namespace: string`
  - Case-sensitive label grouping scratchpads per tenant; defaults to a configured value (for example `"default"`).
- `tags: string[]`
  - Scratchpad-level labels used for filtering and discovery.
- `cells: ScratchCell[]`
  - Ordered list of cells.
- `metadata: object` (optional)
  - Scratchpad-level metadata; stored and returned but only partially interpreted by the server.
  - Canonical fields (all strings):
    - `title` — short label surfaced in listings and semantic search results.
    - `description` — longer human-readable summary; included in `scratch_list` so agents can choose a pad without issuing a read.
    - `summary` (optional) — machine-oriented synopsis used for semantic search snippets; persisted with the scratchpad and returned by `scratch_read`, but omitted from the default `scratch_list` payload to keep navigation lightweight.
  - MAY contain a `schemas` object keyed by logical schema identifier. Each schema entry MUST be an object containing:
    - `id: string` (UUID)
    - `description: string`
    - `schema: object` (JSON Schema definition)
- `cell_tags: string[]` (synthetic)
  - Union of all cell-level tags synthesized at read time; not persisted to avoid divergence from cell data.
- `last_access_at: datetime`
  - UTC timestamp tracking the most recent read/write access, used for eviction policy ordering and preemptive sweeper decisions.

**Canonical schema**

- See `scratch-notepad-tool.md` section "Scratchpad Notebook (v2)" (`scratchpad-v2.json`), which defines:
  - Required: `scratch_id`, `cells`.
  - Optional: `metadata` with open-ended properties.

### 1.2 Scratch Cell (`ScratchCell`)

**Concept**

- Represents a single unit of content inside a scratchpad.
- Is language-aware and can carry validation instructions and optional JSON Schema for structured data.

**Key fields (conceptual)**

- `index: integer`
  - Zero-based position in the scratchpad.
  - Stable index; used for replace operations and validation targeting.
- `language: string`
  - Determines validation behavior and content interpretation.
  - Supported values (from `scratch-notepad-tool.md`):
    - Code: `py`, `js`, `ts`, `tsx`, `jsx`, `rs`, `c`, `h`, `cpp`, `hpp`, `sh`, `css`, `html`, `htm`, `java`, `go`, `rb`, `toml`, `php`, `cs`.
    - Structured data: `json`, `yaml`, `yml`.
    - Text: `md`, `txt`.
- `content: string`
  - Raw cell content as text.
- `validate: boolean` (optional, default `false`)
  - Whether to automatically validate this cell on add/replace.
- `json_schema: object|string` (optional)
  - JSON Schema for structured data (JSON/YAML/YML).
  - May be provided as a JSON object or a JSON-encoded string; implementation is responsible for parsing.
- `metadata: object` (optional)
  - Cell-level metadata (tags, note, timestamps, etc.), stored and returned but not interpreted by the server.
- `tags: string[]` (optional)
  - Fine-grained labels used for filtering reads and semantic search; duplicates are ignored when computing scratchpad-level `cell_tags`.

**Canonical schema**

- See `scratch-notepad-tool.md` section "Scratchpad Cell (v2)" (`scratch-cell-v2.json`), which defines:
  - Required: `index`, `language`, `content`.
  - Optional: `validate`, `json_schema`, `metadata`.
  - `language` enum list covering all supported formats.

### 1.3 Validation Result (`ValidationResult`)

**Concept**

- Represents the outcome of validating a single cell in a scratchpad.
- Returned by the `scratch_validate` tool and optionally by automatic validation.

**Key fields (conceptual)**

- `cell_index: integer`
  - Index of the validated cell.
- `language: string`
  - Copied from the cell; useful for interpreting diagnostics.
- `valid: boolean`
  - True if there are no fatal errors.
- `errors: ValidationDiagnostic[]`
  - List of errors; each diagnostic includes at least `message`, and optionally `code`, `line`, `column`, and raw `details`.
- `warnings: ValidationDiagnostic[]`
  - List of non-fatal diagnostics (style issues, analysis warnings).
- `details: object`
  - Structured details grouped by aspect:
    - `syntax` (whether syntax was checked and whether it passed).
    - `schema` (whether schema validation was performed; whether it passed; which shared schema name was resolved when applicable).
    - `analysis` (for markdown or other analyzers).

**Canonical schema**

- See `scratch-notepad-tool.md` section "Validation Result" (`validation-result.json`), which defines:
  - Required: `cell_index`, `language`, `valid`, `errors`, `warnings`.
  - Optional structured `details.syntax`, `details.schema`, `details.analysis`.

### 1.4 Error Result (`ErrorResult`)

**Concept**

- Common error envelope used by all tool responses when `ok` is `false`.
- Encapsulates a machine-readable error code and human-readable message.

**Key fields (conceptual)**

- `error: string`
  - Human-readable message.
- `code: string` (optional but strongly recommended)
  - Short identifier (for example `NOT_FOUND`, `VALIDATION_ERROR`).
- `details: object` (optional)
  - Free-form diagnostic context.

**Canonical schema**

- See `scratch-notepad-tool.md` section "Error Result" (`error-result.json`).

### 1.5 Namespace (Logical)

**Concept**

- Namespaces group scratchpads per tenant using a case-sensitive string. They are lightweight labels, not separate persisted documents, but the server maintains a registry so namespaces can exist before scratchpads are created.

**Key attributes**

- `tenant_id: string`
- `namespace: string`
- Optional bookkeeping metadata (creation timestamp) used for ordering.

### 1.6 Semantic Search Result (`SearchHit`)

**Concept**

- Represents a ranked match returned by the `scratch_search` MCP tool.

**Key fields**

- `scratch_id: string`
- `cell_id: string|null` (null when the hit targets scratchpad-level metadata)
- `tenant_id: string`
- `namespace: string`
- `tags: string[]`
- `score: number` (similarity, higher is better)
- `snippet: string` (short excerpt of matched content)
- `embedding_version: string` (identifier of the embedding model used)

**Canonical schema**

- To be defined in `scratch-notepad-tool.md` (`scratch-search-response.json`).

### 1.7 Tag Listing Result (`TagListing`)

**Concept**

- Represents the response body for the `scratch_list_tags` MCP tool.

**Key fields**

- `scratchpad_tags: string[]` — deduplicated list of tags applied directly to scratchpads owned by the tenant.
- `cell_tags: string[]` — deduplicated list of tags that appear on any cell for those scratchpads.
- `namespace_filter: string[]` (optional) — namespaces used when computing the listing (empty or missing means all).

**Canonical schema**

- Defined in `scratch-notepad-tool.md` (`scratch-list-tags-response.json`).

## 2. Tool-Level Data Models

Each MCP tool operates on the core entities above and has corresponding request/response shapes defined as JSON Schemas in `scratch-notepad-tool.md`. Below is a conceptual summary of each.

### 2.1 `scratch_create`

**Request (conceptual)**

- `scratch_id: string`
  - Logical identifier (UUID string); may be caller-chosen or server-generated depending on spec usage.
- `metadata: object` (optional)
  - Initial scratchpad metadata.

**Response (success)**

- `ok: true`
- `scratchpad: Scratchpad`

**Response (failure)**

- `ok: false`
- `error: ErrorResult`

### 2.2 `scratch_read`

**Request**

- `scratch_id: string`
- `namespaces: string[]` (optional; when provided, operation fails with `UNAUTHORIZED`/`CONFLICT` if the scratchpad is outside the supplied set)
- `cell_ids: string[]` (optional; UUIDs of target cells)
- `tags: string[]` (optional; when provided, only cells whose `tags` contain any requested value are returned)
- `include_metadata: boolean` (optional, default `true`)

**Response (success)**

- `ok: true`
- `scratchpad: Scratchpad`

**Response (failure)**

- `ok: false`
- `error: ErrorResult`

### 2.3 `scratch_append_cell`

**Request**

- `scratch_id: string`
- `cell: object`
  - `language: string`
  - `content: string`
  - `validate: boolean` (optional)
  - `json_schema: object|string` (optional)
  - `metadata: object` (optional)
  - Note: `index` is assigned by the server.

**Response (success)**

- `ok: true`
- `scratchpad: Scratchpad`

**Response (failure)**

- `ok: false`
- `error: ErrorResult`

### 2.4 `scratch_replace_cell`

**Request**

- `scratch_id: string`
- `index: integer`
- `cell: object` (as above; replaces content at `index`)

**Response**

- Same pattern as `scratch_append_cell`: `ok + scratchpad` on success, `ok=false + error` on failure.

### 2.5 `scratch_delete`

**Request**

- `scratch_id: string`

**Response**

- `ok: true` plus fields indicating `scratch_id` and `deleted` status, or
- `ok: false` plus `error`.

### 2.6 `scratch_list`

**Request**

- `namespaces: string[]` (optional; limits results to the provided namespace strings)
- `tags: string[]` (optional; matches scratchpads that have any of the supplied tags or whose cells carry those tags)
- `limit: integer` (optional; client hint for pagination)

**Response (success)**

- `ok: true`
- `scratchpads: { scratch_id: string, metadata?: object }[]`

**Response (failure)**

- `ok: false`
- `error: ErrorResult`

### 2.7 `scratch_validate`

**Request**

- `scratch_id: string`
- `indices: integer[]` (optional; if omitted or empty, validate all cells)

**Response (success)**

- `ok: true`
- `scratch_id: string`
- `results: ValidationResult[]`

**Response (failure)**

- `ok: false`
- `error: ErrorResult`

### 2.8 `scratch_namespace_list`

**Request**

- `tenant_scope: string` (implicit via auth; no explicit parameter required)

**Response**

- `ok: true`
- `namespaces: { "namespace": string, "scratchpad_count": integer }[]`

### 2.9 `scratch_namespace_create`

**Request**

- `namespace: string`

**Response**

- `ok: true`
- `namespace: string`
- `created: boolean`

### 2.10 `scratch_namespace_rename`

**Request**

- `old_namespace: string`
- `new_namespace: string`
- `migrate_scratchpads: boolean` (default `true`; when `false`, operation fails if scratchpads reference the old namespace)

**Response**

- `ok: true`
- `namespace: string` (new value)
- `migrated_count: integer`

### 2.11 `scratch_namespace_delete`

**Request**

- `namespace: string`
- `delete_scratchpads: boolean` (default `false`)

**Response**

- `ok: true`
- `deleted: boolean`
- `removed_scratchpads: integer` (0 when `delete_scratchpads` is `false`)

### 2.12 `scratch_search`

**Request**

- `query: string`
- `namespaces: string[]` (optional)
- `tags: string[]` (optional)
- `limit: integer` (optional, default 10)

**Response**

- `ok: true`
- `hits: SearchHit[]`
- `embedder: string` (model identifier)

## 3. Configuration And Time-Unit Encoding

Although configuration surface is primarily documented in contracts and spec, some configuration concepts are tightly coupled to the data model.

### 3.1 Capacity And Limits

- `max_scratchpads: integer`
  - 0 means unlimited; default 1024.
- `max_cells_per_pad: integer`
  - 0 means unlimited; default 1024.
- `max_cell_bytes: integer`
  - 0 means unlimited; default 5_242_880 (5 MiB).

These appear as config, not fields in core entities, but they constrain allowed states and must be reflected in validation and error behavior.

### 3.2 Time-Based Settings

All time-related config options (for example `preempt_age`, `preempt_interval`, `
