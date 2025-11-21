# Contracts: MCP Tools (Scratch Notebook MCP Server)

This document defines the behavioral and structural contracts for the MCP tools exposed by the Scratch Notebook server.
Canonical JSON Schemas for requests and responses are defined in `specs/scratch-notepad-tool.md` ("Tool Request/Response Schemas" section); this document summarizes them and binds them to feature-level requirements.

## 1. Common Conventions

- All tools are exposed via `fastmcp` under the server name `scratch-notebook`.
- All tool responses share the following top-level convention:

```json
{
  "ok": true or false,
  "error": { ... }  // present when ok is false
}
```

Where `error` conforms conceptually to the `ErrorResult` schema:

- `error: string` (message).
- `code: string` (short identifier, for example `NOT_FOUND`, `VALIDATION_ERROR`).
- `details: object` (optional context).

Logical entities used by these tools are documented in `data-model.md`.

## 2. Tool: `scratch_create`

**Purpose**

Create or reset a scratchpad identified by `scratch_id`.

**Request (summary)**

- `scratch_id: string` (required) – Logical identifier for the scratchpad (UUID recommended).
- `metadata: object` (optional) – Scratchpad-level metadata map. Canonical keys inside this object include:
  - `title: string|null` – concise human-facing label (≤60 characters recommended).
  - `description: string|null` – 1–2 sentence description for listings.
  - `summary: string|null` – terse synopsis optimised for semantic search snippets.
  - `namespace: string|null` – Namespace name registered via `scratch_namespace_*`.
  - `tags: string[]` – Scratchpad-level tags.
  - `schemas: object` – Shared schema registry map (per FR-017).
  - Additional keys are stored and returned verbatim; clients may attach arbitrary metadata when useful.
- `cells: object[]` (optional) – List of initial cells to create immediately within the scratchpad. Each element matches the structure used in `scratch_append_cell`:
  - `language: string` (required)
  - `content: string` (required)
  - `validate: boolean` (optional)
  - `json_schema: object|string` (optional)
  - `metadata: object` (optional)
  - `tags: string[]` (optional)

**Response (success)**

- `ok: true`
- `scratchpad: Scratchpad` (see `data-model.md`)
  - `cells` array containing the created cells (including generated `cell_id`s and `index`es).
  - **CRITICAL**: To conserve context window, the response MUST NOT include the `content` of the cells. It MUST returns only structural info (`cell_id`, `index`, `language`, `type`) and metadata/validation status.
  - Canonical fields (`title`, `description`, optional `summary`, `namespace`, `tags`, `cell_tags`) appear both at the top level and within `metadata`.
- `evicted_scratchpads: string[]` (optional) – Present when the `discard` eviction policy removes existing pads to satisfy `max_scratchpads`; lists each evicted scratchpad id.

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code` values: `INVALID_ID`, `CONFIG_ERROR`, `INTERNAL_ERROR`.

**Notes**

- If a scratchpad with `scratch_id` already exists:
  - Behavior must follow `spec.md`: either reset or fail; spec currently assumes "create or reset" semantics.
  - Implementation must be explicit in the docs if this ever changes.
- When eviction policy `discard` deletes one or more pads to honour `max_scratchpads`, the response MUST include `evicted_scratchpads` with the affected ids and emit a structured log entry.

## 3. Tool: `scratch_read`

**Purpose**

Return the full contents of an existing scratchpad.

**Request**

- `scratch_id: string` (required)
- `cell_ids: string[]` (optional) — filters by explicit cell identifiers before the tag filter.
- `tags: string[]` (optional) — when provided, only cells (and metadata summaries) containing at least one requested tag are returned.
- `include_metadata: boolean` (optional, default `true`) — controls whether scratchpad metadata is included in the response.
- `namespaces: string[]` (optional) — when provided, the server MUST verify the scratchpad belongs to one of the listed namespaces, otherwise respond with `CONFLICT` without revealing existence.

**Response (success)**

- `ok: true`
- `scratchpad: Scratchpad`
  - MUST include canonical metadata fields (`title`, `description`, optional `summary`) when they were provided at creation or updated later.

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code`: `NOT_FOUND`, `INVALID_ID`, `UNAUTHORIZED` (in multi-tenant mode).

**Behavioral constraints**

- When `cell_ids` are provided, the server MUST validate they refer to existing cells before applying `tags` filtering. Invalid references result in `INVALID_ID` without mutations.
- When `tags` is supplied, only the subset of cells whose `tags` array intersects the provided set is returned. The response MUST still include scratchpad-level `tags` and the synthesized `cell_tags` array covering all cell tags (even those filtered out) so clients can understand the overall taxonomy.
- When `include_metadata` is `false`, the `metadata` field is omitted from the response while other fields remain unchanged.

## 4. Tool: `scratch_append_cell`

**Purpose**

Append a new cell to the end of a scratchpad.

**Request**

- `scratch_id: string` (required)
- `cell: object` (required)
  - `language: string` (required; must be one of the supported language codes).
  - `content: string` (required).
  - `validate: boolean` (optional; default `false`).
  - `json_schema: object|string` (optional)
    - May be an inline schema or a reference such as `{"$ref": "scratchpad://schemas/<name>"}` pointing to a shared schema stored in `scratchpad.metadata.schemas`.
  - `metadata: object` (optional)
  - `tags: string[]` (optional)
    - Cell-level tags contributing to scratchpad `cell_tags` aggregation and search filters.

**Response (success)**

- `ok: true`
- `scratchpad: Scratchpad` (including the new cell at the last index).
  - **CRITICAL**: The `cells` list in this response MUST be "lightweight" (metadata only). It MUST NOT include `content` for any cell, including the newly appended one.

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code`: `NOT_FOUND`, `INVALID_ID`, `CAPACITY_LIMIT_REACHED`, `VALIDATION_ERROR`, `CONFIG_ERROR`.

**Behavioral constraints**

- If `validate: true`, the server MUST perform validation appropriate to `language` using the validation stack described in `research.md`, but validation is advisory: diagnostics are attached to `ValidationResult` objects and MAY be included in the response, and MUST NOT cause the append operation to fail solely because issues were detected.
- When `json_schema` is a scratchpad reference, the server resolves it to the shared schema prior to validation. If the reference cannot be resolved, the cell is still appended unchanged and the `ValidationResult` MUST contain a warning describing the missing schema reference.
- Storage or configuration errors (for example invalid `scratch_id`, capacity violations) still fail the operation and MUST NOT partially mutate the scratchpad; `ok` is `false` and `error` is populated in those cases.

## 5. Tool: `scratch_replace_cell`

**Purpose**

Replace an existing cell with new content and optionally move it to a new position.

**Request**

- `scratch_id: string` (required)
- `cell_id: string` (required; UUID of the cell to replace).
- `cell: object` (required; same structure as in `scratch_append_cell`).
- `new_index: integer` (optional; zero-based reorder target applied after replacement).

**Response (success)**

- `ok: true`
- `scratchpad: Scratchpad` (with the cell at `index` replaced).
  - **CRITICAL**: The `cells` list in this response MUST be "lightweight" (metadata only). It MUST NOT include `content` for any cell.

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code`: `NOT_FOUND`, `INVALID_ID`, `INVALID_INDEX`, `VALIDATION_ERROR`.

**Behavioral constraints**

- The operation must be atomic with respect to storage: either the new cell is fully written at `index` or the scratchpad is unchanged when a storage/configuration error occurs.
- Validation semantics for `validate: true` are the same as for `scratch_append_cell`: diagnostics are advisory and MUST NOT on their own prevent the replacement from being stored.
- Shared schema references MUST be resolved identically to append operations; unresolved references result in warnings attached to the validation results, not a failed replace.
- When `new_index` is supplied, the server MUST move the targeted cell to that zero-based position after the replacement and shift neighbouring cells to keep indices contiguous.

## 6. Tool: `scratch_delete`

**Purpose**

Delete a scratchpad and all of its cells.

**Request**

- `scratch_id: string` (required)

**Response (success)**

- `ok: true`
- `scratch_id: string`
- `deleted: boolean`
  - `true` if a scratchpad existed and was deleted.
  - `false` if no scratchpad with that id existed (idempotent delete semantics).

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code`: `INVALID_ID`, `UNAUTHORIZED`, `INTERNAL_ERROR`.

**Behavioral constraints**

- Deletion must be explicit; the server may not silently delete scratchpads as a side effect of other operations.
- Durability guarantees apply: once `ok: true` is returned with `deleted: true`, the scratchpad must not reappear after restart.

## 7. Tool: `scratch_list`

**Purpose**

List existing scratchpads to support discovery and navigation.

**Request**

- `namespaces: string[]` (optional) — restricts results to pads in these namespaces.
- `tags: string[]` (optional) — pads with matching scratchpad or cell tags.
- `limit: integer` (optional) — maximum number of entries to return (server MAY enforce a cap).

**Response (success)**

- `ok: true`
- `scratchpads: object[]`
  - Each element:
    - `scratch_id: string`
    - `title: string|null`
    - `description: string|null`
    - `namespace: string|null`
    - `cell_count: integer`

**Response (failure)**

- `ok: false`
- `error: ErrorResult`

**Behavioral constraints**

- Namespace and tag filters SHOULD be evaluated using LanceDB expressions so the server does not fetch all scratchpads into memory. Matching semantics are inclusive (logical OR within each array).
- In multi-tenant mode with auth enabled, the list must be scoped to the authenticated principal.
- The list must be consistent with read/delete behaviors and eviction: deleted or evicted pads MUST disappear once acknowledged.
- Additional metadata such as `summary`, scratchpad `tags`, synthesized `cell_tags`, and schema registries remain available through `scratch_read`; callers rely on that tool (optionally with `include_metadata: false`) when they need more than the lean listing payload.

## 8. Tool: `scratch_list_cells`

**Purpose**

Return a lightweight listing of cells for a scratchpad without full content payloads.

**Request**

- `scratch_id: string` (required)
- `cell_ids: string[]` (optional) — filter to specific cell UUIDs
- `tags: string[]` (optional) — return only cells whose tag set intersects the provided list

**Response (success)**

- `ok: true`
- `scratch_id: string`
- `cells: object[]`
  - Each element: `index`, `cell_id`, `language`, optional `tags`, optional metadata summary (for example `description`), and MAY include a truncated content preview depending on spec constraints.

**Response (failure)**

- `ok: false`
- `error: ErrorResult`

**Behavioral constraints**

- Designed for navigation; returns only lightweight data, not full cell contents.
- Honors tenant scoping and rejects invalid `cell_id` references with `INVALID_ID`.
- When both `cell_ids` and `tags` are provided the result includes only cells present in the intersection.

## 9. Tool: `scratch_validate`

**Purpose**

Validate one or more cells within a scratchpad and return structured results.

**Request**

- `scratch_id: string` (required)
- `cell_ids: string[]` (optional)
  - Preferred mechanism for targeting cells once `cell_id` is known; allows validation to be driven entirely by ids instead of indices.

**Response (success)**

- `ok: true`
- `scratch_id: string`
- `results: ValidationResult[]` (see `data-model.md`)

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code`: `NOT_FOUND`, `INVALID_ID`, `INVALID_INDEX`, `VALIDATION_TIMEOUT`, `CONFIG_ERROR`.

**Behavioral constraints**

- If `validation_request_timeout` is configured and exceeded:
  - The entire request fails with `ok: false` and `code: VALIDATION_TIMEOUT`.
  - No partial results are returned.
- For cells with unsupported validation (for example `txt`):
  - Results must mark them as valid and indicate that no validation was performed.
- For JSON/YAML cells that reference shared schemas:
  - Results MUST indicate which shared schema id was applied when resolved.
  - When the reference cannot be resolved, results MUST include a warning (not a top-level error) describing the missing schema reference; the cell content itself is never discarded as a consequence of validation.

## 11. Tool: `scratch_list_schemas`

**Purpose**

List shared schemas associated with a scratchpad.

**Request**

- `scratch_id: string` (required)

**Response (success)**

- `ok: true`
- `scratch_id: string`
- `schemas: object[]`
  - Each element contains `id` (UUID string), `description` (string), and `schema` (object) metadata.

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code`: `NOT_FOUND`, `UNAUTHORIZED`.

**Behavioral constraints**

- Tenant scoping applies; only schemas owned by the authenticated principal are returned.
- The list is sorted deterministically (for example by description or creation time) so UI clients can present stable results.

## 12. Tool: `scratch_get_schema`

**Purpose**

Fetch a single shared schema definition.

**Request**

- `scratch_id: string` (required)
- `schema_id: string` (required; UUID)

**Response (success)**

- `ok: true`
- `schema: { "id": string, "description": string, "schema": object }`

**Response (failure)**

- `ok: false`
- `error: ErrorResult`
  - Typical `code`: `NOT_FOUND`, `UNAUTHORIZED`.

## 13. Tool: `scratch_upsert_schema`

**Purpose**

Create or update a shared schema entry for a scratchpad.

**Request**

- `scratch_id: string`
