---
description: "Implementation tasks for Scratch Notebook MCP (001-scratch-notebook-mcp)"
---

# Task List: Scratch Notebook MCP

**Feature**: `001-scratch-notebook-mcp`
**Spec**: `specs/001-scratch-notebook-mcp/spec.md`
**Technical Reference**: `specs/scratch-notepad-tool.md`
**Constitution**: `.specify/memory/constitution.md`

All tasks below follow the required format:

- `- [ ] TNNN [P?] [USx?] Description with file path`

Where:

- `[P]` - task can safely be executed in parallel (different files, no ordering dependency).
- `[US1]`, `[US2]`, `[US3]` - tasks mapped to User Stories from `spec.md`.
- Paths are relative to the repository root.

Path conventions for this project (per `plan.md`):

- Package root: `scratch_notebook/`
- Tests: `tests/unit/`, `tests/integration/`, `tests/contract/`
- Docs: `specs/001-scratch-notebook-mcp/*.md`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, package skeleton, and base tooling.

- [X] T000 Initialize local Python development environment from the repository root:
  - Create a virtual environment in `.venv` using `uv venv .venv --python=3.12 --seed` (or equivalent, consistent with the project constitution).
  - Add a `requirements-dev.txt` (and/or `requirements.txt`) that mirrors the runtime dependencies from `pyproject.toml` (`fastmcp`, `jsonschema`, `PyYAML`, `syntax-checker`, `markdown-analysis`, etc.) plus test and lint tooling (for example `pytest`, `ruff`, `mypy` as needed).
  - Install dependencies into `.venv` (for example via `uv pip install -e .[dev]` or `pip install -e .` followed by `pip install -r requirements-dev.txt`) so that editors, linters, and tests can resolve imports without spurious errors.
- [X] T001 Create Python package skeleton with minimal modules in `scratch_notebook/__init__.py`, `scratch_notebook/server.py`, and `scratch_notebook/config.py` as per `plan.md` structure.
- [X] T002 Create `pyproject.toml` with project metadata, `scratch-notebook` package definition, dependencies (`fastmcp`, `jsonschema`, `PyYAML`, `syntax-checker`, `markdown-analysis`), and console script entrypoint `scratch-notebook`.
- [X] T003 [P] Create test layout directories and placeholder files in `tests/unit/`, `tests/integration/`, and `tests/contract/` (for example empty `__init__.py` and a smoke test file).
- [X] T004 [P] Add basic `pytest` configuration (for example in `pyproject.toml` or `pytest.ini`) and a smoke test `tests/unit/test_imports_and_config_smoke.py` that imports `scratch_notebook` and runs a trivial config parse.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before user story implementation.

**⚠️ CRITICAL**: No user story work should begin until this phase is complete.

- [X] T005 Implement configuration model and loader in `scratch_notebook/config.py` to merge command-line args, environment variables, and optional JSON config file, including:
  - `storage_dir`, transport flags (`enable_stdio`, `enable_http`, `enable_sse`), capacity/eviction settings, timeouts, and time-unit parsing per NFR-003 and NFR-017.
- [X] T005A [P] Extend configuration loader to materialize missing config/auth directories and files when paths are provided, writing the effective configuration/token registry (defaults merged with CLI/env overrides) on first run.
- [X] T005B [P] Add unit tests in `tests/unit/test_config_file_generation.py` covering file/directory creation, precedence of CLI/env over persisted files, and no-op behavior when paths are omitted.
- [X] T006 [P] Implement structured logging helpers in `scratch_notebook/logging.py` that emit machine-parsable records (with at least `level`, `code`, `message`, and context) to stdout/stderr only.
- [X] T007 [P] Implement central error code taxonomy in `scratch_notebook/errors.py` defining constants (for example `NOT_FOUND`, `INVALID_ID`, `INVALID_INDEX`, `CAPACITY_LIMIT_REACHED`, `VALIDATION_ERROR`, `VALIDATION_TIMEOUT`, `CONFIG_ERROR`, `INTERNAL_ERROR`) and helper functions to build error payloads.
- [X] T008 Wire up a minimal FastMCP server entrypoint in `scratch_notebook/server.py`:
  - Create `FastMCP(name="scratch-notebook")`.
  - Register placeholder tools `scratch_create`, `scratch_read`, `scratch_append_cell`, `scratch_replace_cell`, `scratch_delete`, `scratch_list`, `scratch_validate` with stub implementations.
  - Provide `main()` and a `if __name__ == "__main__": main()` block.
- [X] T009 [P] Implement storage interface skeleton in `scratch_notebook/storage.py`:
  - Resolve and validate `storage_dir` (create if missing, or raise `CONFIG_ERROR`).
  - Provide helpers for resolving per-scratchpad paths and a lightweight index structure, without full CRUD behavior yet.
- [X] T010 [P] Implement transport scaffolding in `scratch_notebook/transports/__init__.py`, `scratch_notebook/transports/stdio.py`, and `scratch_notebook/transports/http.py`:
  - Stdio: wrapper to run FastMCP over stdio.
  - HTTP: shared listener config (host, port, optional Unix socket) and stub request routing for `/http` and `/sse`.
- [X] T011 Add a basic configuration and imports test in `tests/unit/test_config_and_imports.py` to assert that:
  - `scratch_notebook` imports cleanly.
  - `Config` (or equivalent) parses minimal CLI/env/config combinations and honors failure on invalid numeric values.
- [X] T059 Add an early non-blocking guardrail in `tests/unit/test_async_blocking_guard.py` that scans the codebase for `time.sleep(` and other known blocking calls inside async paths, wiring the check into CI so violations fail immediately.
- [X] T060 [P] Introduce runtime helpers in `scratch_notebook/storage.py` and `scratch_notebook/validation.py` that offload blocking work to executors, and add smoke tests proving Phase 2 components never block the event loop.
- [X] T061 Document and test startup-only configuration semantics in `tests/unit/test_config_reload_semantics.py`, ensuring changes to flags/environment variables take effect only after restart and that hot reload attempts raise `CONFIG_ERROR`.

**Checkpoint**: Foundation ready - model, storage, transports, logging, and error taxonomy are in place for user story implementation.

---

## Phase 3: User Story 1 - Capture Structured Scratch Notes (Priority: P1) 🎯 MVP

**Goal**: Provide core scratchpad lifecycle (create, read, delete, list) and multi-cell editing so agents can maintain structured scratch notebooks without touching real project files.

**Independent Test** (from `spec.md`): Create a scratch notebook, append multiple cells of different languages, replace a cell, and verify that reads return expected content and that non-scratch files remain untouched.

### Tests for User Story 1

- [X] T012 [P] [US1] Implement unit tests for `Scratchpad` and `ScratchCell` domain models in `tests/unit/test_models.py` reflecting the fields and semantics from `data-model.md`.
- [X] T013 [P] [US1] Implement unit tests for storage create/read/delete/list behavior in `tests/unit/test_storage_lifecycle.py`, including:
  - Creation of new scratchpads.
  - Idempotent reads.
  - Correct deletion semantics.
  - No cross-scratchpad interference.
- [X] T062 [P] [US1] Add failure-mode unit tests in `tests/unit/test_storage_atomicity.py` that simulate invalid IDs, capacity violations, and validation failures to confirm no partial mutations ever reach disk.
- [X] T063 [P] [US1] Add UUID uniqueness tests in `tests/unit/test_id_uniqueness.py`, including simulated collisions to ensure duplicate IDs are rejected before persistence.
- [X] T064 [P] [US1] Extend contract coverage in `tests/contract/test_api_path_leakage.py` to assert that MCP tool responses and logs never include filesystem paths or internal storage details.

### Implementation for User Story 1

- [X] T014 [P] [US1] Implement domain models in `scratch_notebook/models.py`:
  - `Scratchpad`, `ScratchCell`, and a skeletal `ValidationResult` type consistent with `data-model.md` and `scratch-notepad-tool.md`.
- [X] T015 [US1] Implement durable storage CRUD for scratchpads in `scratch_notebook/storage.py`:
  - `create_scratchpad`, `read_scratchpad`, `delete_scratchpad`, `list_scratchpads`.
  - Use JSON files under `<storage_dir>/scratchpads/` plus an index for listing.
- [X] T016 [US1] Implement `scratch_create` tool in `scratch_notebook/server.py`:
  - Support caller-provided or server-generated UUID `scratch_id`.
  - Persist new scratchpad with optional metadata.
  - Return a `Scratchpad` object on success or `CONFIG_ERROR`/`INTERNAL_ERROR` if storage fails.
- [X] T017 [US1] Implement `scratch_read` tool in `scratch_notebook/server.py` to load a scratchpad by id, returning `NOT_FOUND` if it does not exist.
- [X] T018 [US1] Implement `scratch_delete` tool in `scratch_notebook/server.py` with explicit deletion semantics:
  - Remove only the targeted scratchpad.
  - Return a clear result indicating whether an entry existed and was deleted.
- [X] T019 [US1] Implement `scratch_list` tool in `scratch_notebook/server.py`:
  - Return `scratch_id` and metadata fields required for visual identification.
  - Ensure the listing matches data stored in `storage.py`.
- [X] T020 [P] [US1] Implement integration tests for scratchpad lifecycle via FastMCP stdio in `tests/integration/test_mcp_scratch_lifecycle.py`:
  - Cover `scratch_create`, `scratch_read`, `scratch_delete`, `scratch_list` end-to-end.
- [X] T065 [US1] Harden storage transactions in `scratch_notebook/storage.py` so create/append/replace paths either fully apply or roll back, and return `INVALID_ID`/`VALIDATION_ERROR` without persisting partial state.
- [X] T066 [US1] Add explicit UUID generation/collision handling in `scratch_notebook/server.py`, including storage-level checks before persistence and clear `INVALID_ID` errors when duplicates are detected.
- [X] T067 [US1] Sanitize server responses and structured logging so only logical IDs/metadata are emitted, never filesystem paths; update serialization helpers accordingly.

- [X] T049 [US1] Implement `scratch_append_cell` tool in `scratch_notebook/server.py` and supporting logic in `scratch_notebook/storage.py`:
  - Append a new `ScratchCell` at the end of the notebook, assigning a stable `index` and, where applicable, a `cell_id` UUID.
  - Respect `max_cells_per_pad` and `max_cell_bytes` limits and return appropriate error codes when limits are exceeded.
  - Optionally trigger automatic validation when `validate` is true on the new cell.

- [X] T050 [US1] Implement `scratch_replace_cell` tool in `scratch_notebook/server.py` and supporting logic in `scratch_notebook/storage.py`:
  - Replace the cell at a given `index` with new content while preserving ordering and other cells.
  - Validate `index` bounds and return `INVALID_INDEX` without mutation when out of range.
  - Optionally trigger automatic validation when `validate` is true on the replacement cell.

**Checkpoint**: User Story 1 fully functional and independently testable via MCP stdio.

---

## Phase 4: User Story 2 - Validate Scratch Content Early (Priority: P2)

**Goal**: Enable validation of JSON, YAML, code, markdown, and plain text cells so users can catch issues before promoting content into real configs or code.

**Independent Test**: Create scratchpads with JSON/YAML/code/markdown cells, run `scratch_validate`, and verify valid cells pass while invalid cells report clear, structured errors without crashing the server.

### Tests for User Story 2

- [X] T021 [P] [US2] Implement unit tests for JSON/YAML validation in `tests/unit/test_validation_json_yaml.py`:
  - Valid vs invalid JSON and YAML.
  - JSON Schema validation success and failure paths.
- [X] T022 [P] [US2] Implement unit tests for code and markdown validation in `tests/unit/test_validation_code_markdown.py`:
  - Syntax errors vs clean code using `syntax-checker`.
  - Markdown analysis warnings and valid markdown behavior.
- [X] T023 [P] [US2] Implement unit tests for plain-text validation behavior in `tests/unit/test_validation_plain_text.py` (no structural validation, always valid with explanatory details).
- [X] T068 [P] [US2] Add fallback coverage in `tests/unit/test_validation_fallbacks.py` for unsupported languages and temporarily unavailable analyzers, asserting the server reports “validation not performed” without crashing.

### Implementation for User Story 2

- [X] T024 [P] [US2] Implement validation backend in `scratch_notebook/validation.py`:
  - Integrate `jsonschema` and `PyYAML` for JSON/YAML syntax and schema validation.
  - Integrate `syntax-checker` for supported code languages.
  - Integrate `markdown-analysis` for markdown cells.
  - Map diagnostics into `ValidationResult` structures consistent with `data-model.md` and `scratch-notepad-tool.md`.
- [X] T025 [US2] Implement `scratch_validate` tool in `scratch_notebook/server.py`:
  - Accept `scratch_id` and optional `indices` list.
  - Honor `validation_request_timeout` from config.
  - Return a `results` array of `ValidationResult` objects or `VALIDATION_TIMEOUT`/`VALIDATION_ERROR` on failure.
- [X] T026 [US2] Integrate automatic validation on append/replace operations:
  - When `validate` flag is true on a cell, invoke validation pipeline and propagate summary into the response.
  - Ensure failures do not corrupt stored content.
- [X] T069 [US2] Implement graceful fallback logic in `scratch_notebook/validation.py` so unsupported languages or missing analyzers yield structured “not validated” results while keeping storage untouched.
- [X] T027 [P] [US2] Implement integration tests for `scratch_validate` in `tests/integration/test_mcp_scratch_validate.py`:
  - Cover JSON/YAML/code/markdown/plain text cases including schema validation and timeout handling.
- [X] T027A [US2] Add unit and integration coverage for shared schema references (for example storing schemas in scratchpad metadata and referencing them via `$ref`) in `tests/unit/test_validation_json_yaml.py` and `tests/integration/test_mcp_scratch_validate.py`.
- [X] T027B [US2] Extend `scratch_notebook/validation.py` and server tooling to resolve `scratchpad://schemas/<name>` references against scratchpad metadata (including error handling for unresolved names) while preserving inline schema support.
- [X] T027C [US2] Update data models and serialization (`scratch_notebook/models.py`, storage metadata handling) to persist schema registry entries with `id`, `description`, and `schema` fields and ensure UUID generation when absent.
- [X] T027D [US2] Implement MCP tools `scratch_list_schemas`, `scratch_get_schema`, and `scratch_upsert_schema` in `scratch_notebook/server.py` (plus any supporting modules) to manage schemas per scratchpad, including JSON Schema validation of payloads.
- [X] T027E [US2] Add unit tests covering schema registry CRUD (`tests/unit/test_schema_registry.py`) focusing on storage semantics, validation failures, and tenant scoping hooks.
- [X] T027F [US2] Add integration tests in `tests/integration/test_schema_registry.py` exercising list/get/upsert flows end-to-end and verifying interaction with cell validation.
- [X] T027G [US2] Extend `scratch_read` to support `indices` and `include_metadata` parameters, including unit tests in `tests/unit/test_read_filters.py`.
- [X] T027H [US2] Implement the `scratch_list_cells` tool in `scratch_notebook/server.py` with supporting storage helpers, plus unit coverage in `tests/unit/test_list_cells.py`.
- [X] T027I [US2] Add integration tests in `tests/integration/test_cell_listing.py` validating filtered read, metadata toggles, and lightweight cell listing responses.

**Checkpoint**: User Story 2 fully functional and independently testable.

---

## Phase 5: User Story 3 - Discover And Navigate Scratch Notebooks (Priority: P3) + Limits/Eviction

**Goal**: Support discovery, navigation, and controlled cleanup of scratchpads, including capacity limits, LRU eviction, and preemptive retention.

**Independent Test**: Create multiple notebooks with metadata, list and inspect them, delete selected ones, and verify capacity/eviction behavior and navigation results.

### Tests for User Story 3

- [X] T028 [P] [US3] Implement unit tests for list/index behavior and metadata in `tests/unit/test_list_and_metadata.py`:
  - Ensure listing returns ids and descriptive metadata.
  - Ensure deletes are reflected in listings.
- [X] T029 [P] [US3] Implement unit tests for capacity and size limits in `tests/unit/test_limits.py`:
  - `max_scratchpads`, `max_cells_per_pad`, `max_cell_bytes`.
  - Operations exceeding limits must fail with correct error codes.
- [X] T030 [P] [US3] Implement unit tests for eviction policies (discard/fail) and LRU ordering in `tests/unit/test_eviction_policies.py`.
- [X] T031 [P] [US3] Implement unit tests for preemptive sweeper behavior and time-based retention in `tests/unit/test_eviction_preempt_sweeper.py`.
- [X] T070 [P] [US3] Add contract/integration tests in `tests/integration/test_eviction_notifications.py` asserting that creation responses include the IDs of any scratchpads evicted under the discard policy.

### Implementation for User Story 3 and Limits/Eviction

- [X] T032 [P] [US3] Extend `scratch_notebook/storage.py` to maintain listing index and per-scratchpad metadata required for discovery (title, description, tags) while keeping storage representation internal.
- [X] T033 [US3] Implement `max_scratchpads`, `max_cells_per_pad`, and `max_cell_bytes` enforcement in `scratch_notebook/storage.py` and/or `scratch_notebook/server.py`:
  - Reject operations that would exceed limits with appropriate error codes.
- [X] T034 [US3] Implement `scratch_notebook/eviction.py` with capacity-based eviction logic:
  - `eviction_policy` with at least `discard` (default) and `fail`.
  - LRU tracking based on last read/write access time, with ties broken by creation time.
  - Hook into scratchpad creation to evict or fail as per policy.
- [X] T035 [US3] Implement preemptive sweeper in `scratch_notebook/eviction.py`:
  - Use `preempt_age` and `preempt_interval` configuration (time strings with `s`/`m`/`h` suffixes, default units per NFR-010/NFR-017).
  - Operate independently of instantaneous capacity but never delete scratchpads newer than `preempt_age`.
- [X] T036 [US3] Integrate sweeper lifecycle into `scratch_notebook/server.py`:
  - Start sweeper on server startup.
  - Ensure graceful shutdown respects `shutdown_timeout` and stops sweeper safely.
- [X] T037 [P] [US3] Implement integration tests for navigation and limits in `tests/integration/test_mcp_scratch_discovery_and_eviction.py`:
  - Cover listing, deletion, capacity limit reached, discard/fail behavior, and preempt sweeper effects.
- [X] T071 [US3] Extend `scratch_notebook/eviction.py` and server responses to collect and surface the exact scratchpad IDs evicted during a discard event, ensuring the data is logged and returned to clients per spec.

**Checkpoint**: User Story 3, capacity, eviction, and retention semantics are fully functional and independently testable.

---

## Phase 6: HTTP/SSE Transports, Auth, And Metrics Endpoint (Cross-Cutting)

**Purpose**: Expose the MCP tools over stdio and the MCP HTTP+SSE transport, support optional auth, and provide an optional Prometheus metrics endpoint.

- [X] T038 Implement stdio transport wiring in `scratch_notebook/transports/stdio.py`:
  - Provide a function that runs the FastMCP server over stdio for MCP clients.
  - Integrate with `main()` and CLI options (enable/disable stdio).
- [X] T039 [P] Implement HTTP+SSE MCP transport in `scratch_notebook/transports/http.py`:
  - Shared listener configuration (host, port, optional Unix socket) from `scratch_notebook/config.py`.
  - Route `/http` to MCP HTTP requests that proxy to the same tools as stdio, following MCP/FastMCP semantics.
  - Route `/sse` to the MCP SSE event stream as defined by MCP/FastMCP (for example streaming tool outputs or MCP-level notifications), not as a separate ad hoc application event API.
  - Enforce non-colliding paths and consistent behavior across TCP and Unix socket.
- [X] T040 [P] Implement optional metrics endpoint in `scratch_notebook/metrics.py`:
  - Expose `/metrics` on the HTTP listener when enabled.
  - Emit Prometheus-compatible metrics (counters for operations, errors, validations, evictions, and uptime).
- [X] T041 [P] Implement bearer-token auth (optional) in `scratch_notebook/auth.py`:
  - Parse `Authorization: Bearer <token>` header for HTTP/SSE requests.
  - Map token to a principal identifier and attach it to request context.
  - Integrate with storage and listing so scratchpads are scoped to the authenticated principal.
- [X] T041A [P] Support repeated CLI auth-token arguments (`principal:token` syntax) that merge with the token registry loaded from the auth file, and ensure the merged registry is written back when the auth file is generated.
- [X] T042 [P] Wire config and startup for HTTP/SSE/auth/metrics in `scratch_notebook/server.py`:
  - Use config flags to enable/disable stdio, HTTP, SSE, metrics.
  - Start HTTP server and metrics endpoint when configured.
  - Ensure that default configuration matches spec (localhost, high port, `/http`, `/sse`, optional `/metrics`).
- [X] T043 [P] Implement integration tests for HTTP/SSE and metrics in `tests/integration/test_http_sse_and_metrics.py`:
  - Call tools over the HTTP `/http` endpoint using the MCP HTTP mapping.
  - Verify SSE behavior for at least one MCP-level streaming scenario over `/sse` (for example streaming tool output via the MCP HTTP+SSE transport), without introducing a custom SSE event schema.
  - Verify `/metrics` output format and basic counters when `enable_metrics` is true and HTTP/SSE are both enabled.
  - Verify that when `enable_metrics` is false the `/metrics` path is not served (for example returns 404 or equivalent) while SSE streams remain unaffected.
  - Verify auth behavior (authorized vs unauthorized requests).
- [X] T058 [P] Add a transport/metrics matrix test in `tests/integration/test_metrics_matrix.py` that exercises every documented combination of `enable_http`, `enable_sse`, and `enable_metrics`, ensuring:
  - Enabling metrics with HTTP disabled raises `CONFIG_ERROR`.
  - Enabling metrics with HTTP enabled but SSE disabled still serves `/metrics`.
  - Enabling metrics with both HTTP and SSE enabled serves `/metrics` while SSE streams remain healthy.
  - Disabling metrics always removes `/metrics` regardless of SSE/stdio state.
- [X] T072 [P] Add CLI regression tests in `tests/unit/test_cli_metrics_flags.py` that cover help text, defaults, and error messages for every metrics/transport permutation so the UX clearly documents valid combinations.
- [X] T073 [P] Add stdio-only and HTTP-disabled integration tests in `tests/integration/test_metrics_cli_failures.py` that confirm enabling metrics without an HTTP listener fails fast and that disabling metrics while HTTP is enabled never affects stdio workflows.

**Checkpoint**: Transports, auth, and metrics are available and behave consistently with MCP stdio tools and contracts.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, documentation, and final validation across all stories and transports.

- [X] T044 [P] Update documentation in `specs/001-scratch-notebook-mcp/quickstart.md` and top-level `README.md` to reflect final CLI options, transports, auth behavior, and metrics endpoint, ensuring examples match actual behavior.
- [X] T045 [P] Add unit tests for time-unit parsing and config error handling in `tests/unit/test_time_and_config_parsing.py`, covering:
  - Valid/invalid time strings.
  - Default units for each time-related config.
  - Behavior on invalid config file values and missing required settings.
- [X] T046 [P] Add unit tests for graceful shutdown semantics in `tests/unit/test_shutdown_behavior.py`, verifying:
  - New requests rejected during shutdown.
  - In-flight operations honored up to `shutdown_timeout`.
- [X] T047 Run full `pytest` suite (unit, integration, contract) and fix any remaining issues, ensuring:
  - All MCP tools conform to schemas from `specs/scratch-notepad-tool.md`.
  - All transports (stdio/HTTP/SSE) behave consistently and respect auth, limits, and durability requirements.
- [X] T048 Perform final code cleanup and refactoring in `scratch_notebook/`

---

## Phase 4B: Namespaces, Tagging, and Semantic Search (Priority: P2)

**Goal**: Transition storage to LanceDB, surface namespace/tag management, and deliver semantic search capabilities that respect tenant isolation.

### Storage Migration and Core Infrastructure

- [X] T074 [US4] Replace JSON-based persistence with LanceDB-backed storage in `scratch_notebook/storage.py`, ensuring scratchpad CRUD, schema registry, and listing APIs operate on LanceDB tables.
- [X] T075 [P] [US4] Add unit tests in `tests/unit/test_lancedb_storage.py` covering create/read/update/delete flows, namespace assignment, tag persistence, and transactional guarantees.
- [X] T076 [US4] Update existing integration tests (`tests/integration/test_mcp_scratch_lifecycle.py`, `tests/integration/test_mcp_scratch_validate.py`) to run against the LanceDB backend and assert durability across restarts.

### Namespace and Tag Features

- [X] T077 [US4] Extend `scratch_notebook/models.py` and server serialization helpers to include `namespace`, scratchpad `tags`, synthesized `cell_tags`, and per-cell `tags` in responses.
- [X] T078 [US4] Enhance `scratch_notebook/server.py` list/read/cell tooling to accept `namespaces`, `tags`, and `cell_ids` filters with intersection semantics, including LanceDB query expressions.
- [X] T079 [P] [US4] Implement namespace MCP tools (`scratch_namespace_list`, `scratch_namespace_create`, `scratch_namespace_rename`, `scratch_namespace_delete`) in a new `scratch_notebook/namespaces.py` module with transactional cascade behavior.
- [X] T080 [P] [US4] Add unit tests for namespaces and tag filtering in `tests/unit/test_namespaces_and_tags.py`, covering lifecycle operations, conflict cases, and tag aggregation logic.
- [X] T081 [US4] Add integration tests in `tests/integration/test_mcp_namespaces_and_tags.py` verifying namespace CRUD, filtered listings, filtered reads, and cell tag intersections end-to-end.

### Semantic Search

- [X] T082 [US4] Implement semantic search orchestration in `scratch_notebook/search.py`, wiring `sentence-transformers/all-MiniLM-L6-v2` embeddings, LanceDB vector indices, and the new `scratch_search` tool.
- [X] T083 [P] [US4] Add unit tests in `tests/unit/test_semantic_search.py` covering embedding generation, filter application, and ranking logic (using deterministic fixtures).
- [X] T084 [US4] Add integration tests in `tests/integration/test_mcp_semantic_search.py` exercising namespace/tag filtered searches, result structure, and similarity ordering.

### Configuration, Auth Migration, and Docs

- [X] T085 [P] [US4] Extend CLI/config handling for semantic search (`enable_semantic_search`, `embedding_model`, device/batch flags) with regression tests in `tests/unit/test_cli_semantic_flags.py`.
- [X] T086 [US4] Implement default-tenant migration logic triggered on first auth enablement, with contract tests in `tests/contract/test_default_tenant_migration.py` validating log output and reassignment behavior.
- [X] T087 [P] [US4] Update documentation (`specs/001-scratch-notebook-mcp/quickstart.md`, top-level README) to cover namespaces, tagging, semantic search, and auth migration, ensuring examples match implemented behavior.

**Checkpoint**: Namespaces, tags, LanceDB storage, and semantic search are fully functional with comprehensive test coverage.

---

- [X] T088 [US4] Add canonical metadata handling (`title`, `description`, `summary`) to `scratch_notebook/server.py` and serialization helpers, ensuring values flow through create/read/list endpoints and are persisted in LanceDB.
- [X] T089 [P] [US4] Add unit tests in `tests/unit/test_canonical_metadata.py` verifying create/read/list behaviors for the canonical metadata fields, including absence/presence cases and persistence across restarts.
- [X] T090 [US4] Update MCP tool schemas (`specs/scratch-notepad-tool.md`) and prompt documentation so `scratch_create`, `scratch_read`, and `scratch_list` explicitly expose canonical metadata parameters, and refresh developer docs/quickstart accordingly.
- [X] T091 [US4] Implement the `scratch_list_tags` MCP tool in `scratch_notebook/server.py`, including LanceDB-backed aggregation logic and namespace filtering support.
- [X] T092 [P] [US4] Add unit and integration coverage for `scratch_list_tags` (`tests/unit/test_tag_listing.py`, `tests/integration/test_mcp_tag_listing.py`) asserting deduplication, ordering, namespace filtering, and tenant scoping.

- [X] T087A [US4] Update existing unit/integration tests to assert canonical metadata fields and new tag listing requirements, intentionally introducing failing expectations that reflect the updated spec before implementation changes.
- [X] T087B [US4] Update contract tests/tool schema fixtures so prompts expose `title`, `description`, `summary`, and ensure absence of the new fields causes failures pending implementation.
- [X] T087C [US4] Update existing semantic search tests to require snippets to reference canonical metadata where applicable, causing failures until the new behavior is implemented.

- [X] T093 [US4] Update MCP prompt/documentation to define expected tone and detail for `title`, `description`, and `summary`, ensuring agents know how to populate these fields during `scratch_create`.
- [X] T094 [US4] Ensure `README.md` reflects operator-facing guidance only, includes the canonical MCP client configuration example, and removes references to internal schemas.
- [X] T095 [US4] Author `DEVELOPMENT.md` consolidating contributor-focused build, test, and architecture notes.
- [X] T096 [US4] Relocate agent-facing instructions (including canonical metadata tone) into FastMCP tool prompts so clients receive self-contained guidance.
- [X] T097 [US4] Update FastMCP tool prompts (notably `scratch_create`) to instruct assistants to reuse project-specific namespace prefixes discovered via `scratch_namespace_list`, ensuring consistent naming when multiple projects share the default tenant.
- [X] T098 [US4] Add contract or unit coverage that exercises the updated prompts/documentation to confirm the namespace reuse guidance remains present and accurate.

---

## Phase 8: Validation UX & Id-First Addressing (Post-Stabilisation)

**Goal**: Evolve validation and addressing semantics so scratchpads behave like advisory workspaces (not compilers) and entities are always addressed by stable ids instead of positional indices.

- [X] T099 [P] Update validation semantics in `specs/001-scratch-notebook-mcp/spec.md`, `data-model.md`, `contracts/mcp-tools.md`, `quickstart.md`, `research.md`, `README.md`, `DEVELOPMENT.md`, and `AGENTS.md` so that:
  - All validation diagnostics (JSON/YAML/code/markdown) are advisory and never block create/append/replace operations.
  - Missing JSON/YAML schema references (for example `scratchpad://schemas/<name>` that are not present) produce warnings and store the cell unchanged.
  - The `ValidationResult` model clearly represents warnings vs informational messages and is framed as guidance, not hard errors.
- [X] T100 [P] Shift `scratch_append_cell` / `scratch_replace_cell` / `scratch_validate` implementations in `scratch_notebook/server.py` and `scratch_notebook/validation.py` to the new advisory model:
  - `VALIDATION_ERROR` has now a warning character instead of a hard error, it no longer aborts operation - it only gets logged as advisory to correct the errors presented as clear comprehensive detail context in the warning message.
  - Automatic validation on `validate=true` must always persist the cell and return structured diagnostics without raising `VALIDATION_ERROR`.
  - `scratch_validate` must accept explicit cell id lists and re-validate those cells even when their `validate` flag is false.
  - Response formats and error codes must remain consistent with the updated contracts while eliminating index-only addressing wherever ids exist.
- [X] T101 [P] Refine id-first addressing across tools and docs:
  - Prefer `cell_id` and `scratch_id` filters over raw indices in MCP contracts and prompts.
  - Where positional indices are currently the only option, add id-based alternatives and mark index usage as legacy in `spec.md` and `contracts/mcp-tools.md`.
  - Update tests in `tests/unit/` and `tests/integration/` to exercise id-based flows as the primary path.
- [X] T102 [P] Make tool prompts in `scratch_notebook/server.py` fully explicit about validation and addressing semantics:
  - Describe exactly when automatic validation runs, what happens on validation diagnostics, and how to interpret `results` arrays.
  - Document that manual `scratch_validate` calls treat validation as advisory and can be targeted by cell ids.
  - Ensure prompts remain self-contained so agents understand parameters, behaviours, and response shapes without reading this repository.
- [X] T103 [P] Remove index-based addressing from edit operations and keep indices only as ordering metadata:
  - Update `spec.md`, `data-model.md`, `contracts/mcp-tools.md`, `scratch-notepad-tool.md`, `research.md`, `quickstart.md`, `README.md`, `DEVELOPMENT.md`, and `AGENTS.md` so editing tools (`scratch_replace_cell`, `scratch_validate`, `scratch_read`, `scratch_list_cells`) describe `cell_id` as the sole identifier for mutations; indices are documented purely as order indicators.
  - Extend `scratch_replace_cell` contract with an optional `new_index` parameter (or equivalent) that lets clients reorder cells without relying on positional addressing.
  - Add a new server-level task covering prompt updates so FastMCP instructions fully describe the id-only editing and reorder semantics.
- [X] T104 [P] Implement the id-only editing model:
  - Update server/storage code so `_scratch_replace_cell_impl`, `_scratch_validate_impl`, `_scratch_read_impl`, `_scratch_list_cells_impl`, and related helpers accept only `cell_id` for targeting cells (indices removed except for the reorder parameter).
  - Teach storage to handle reorder requests by shifting neighbouring cells when `new_index` (or the chosen reorder parameter) is provided, ensuring indexes remain contiguous.
  - Adjust prompt text, tests (unit, integration, contract), and schemas to align with the new parameter set; remove index-based addressing tests and add reorder coverage.
  - Run full pytest and document the change in `implementation.md`.
