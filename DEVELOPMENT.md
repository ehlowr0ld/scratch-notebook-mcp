# Development Guide

This document targets contributors extending or maintaining the Scratch Notebook MCP server. Operator-facing instructions live in `README.md`; agent-facing prompts reside in the FastMCP tool definitions inside `scratch_notebook/server.py`.

## Project Layout

```
scratch_notebook/
  __init__.py
  config.py              # CLI/env parsing and materialisation of config/auth files
  errors.py              # Domain error codes
  logging.py             # FastMCP-aware logging helpers
  models.py              # Scratchpad, cell, schema, and metadata helpers
  namespaces.py          # Namespace orchestration (list/create/rename/delete)
  search.py              # Semantic search orchestration and embedding management
  server.py              # FastMCP server + tool registrations (agent prompts live here)
  storage.py             # Public facade re-exporting the LanceDB storage backend
  storage_lancedb.py     # LanceDB-backed persistence, tag aggregation, tenant migration
  validation.py          # Structured validation utilities
specs/001-scratch-notebook-mcp/  # Specification bundle (requirements, plan, research, data model, quickstart)
tests/                         # Unit, integration, and contract suites
```

## Environment Setup

1. Create a virtual environment and install dependencies in editable mode:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
2. Install test extras as new dependencies are introduced (for example `pytest`, `pytest-asyncio`, `coverage`). Running `pip install -e .[dev]` (or `uv pip install -e .[dev]`) ensures the dev extra installs the full toolchain in one step.
3. Export `PYTHONPATH="/home/rafael/Workspace/Repos/rafael/scratch-notebook"` before invoking project modules or pytest so imports resolve in editors and scripts.
4. Maintain the dependency pins declared in `pyproject.toml` (notably `fastmcp`, `jsonschema`, `syntax-checker`, `markdown-analysis`, `lancedb`, and `sentence-transformers`).

## Local Testing

Run the full suite before submitting changes:
```bash
timeout 300 pytest
```
Component-specific targets:
- `pytest tests/unit` – fast feedback for data model, storage, and config helpers.
- `pytest tests/integration` – MCP lifecycle, namespaces/tags, validation, and semantic search.
- `pytest tests/contract` – Tool schema compliance and transport/auth expectations.
Usage examples:
- `timeout 120 pytest tests/unit`
- `timeout 180 pytest tests/integration`
- `timeout 120 pytest tests/contract`

Large refactors should run the targeted suite first and then the full suite to ensure no regressions slip past.

### Coverage Workflow

Every release-quality change should capture coverage results so we can spot regressions in `scratch_notebook/validation.py` and other complex modules:

```bash
python -m coverage run -m pytest
python -m coverage report -m
```

Because `coverage` ships in the `dev` extra, `pip install -e .[dev]` or `uv pip install -e .[dev]` guarantees the command is available without manual installs. Record notable gaps (for example uncovered advisory-validation branches) in `specs/001-scratch-notebook-mcp/implementation.md` and schedule new tasks when thresholds slip.

## SpecKit Workflow

- Use `./.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` at the start of every `/speckit.*` run to capture the feature directory and available docs.
- Treat `specs/001-scratch-notebook-mcp/tasks.md` as the canonical backlog. Only mark a task `[X]` after the implementation has been verified.
- `specs/001-scratch-notebook-mcp/implementation.md` is the running changelog. Append a dated entry for every meaningful change or blocker investigation.
- Keep the checklists under `specs/001-scratch-notebook-mcp/checklists/` synchronized. Re-run them whenever the specification changes.
- When behaviour or prompts evolve, update the specification bundle (spec, plan, data-model, research, quickstart, contracts) alongside the code so tests and docs stay aligned.

## Coding Guidelines

- Follow the architecture described in `specs/001-scratch-notebook-mcp/spec.md` and `plan.md` before modifying server APIs.
- Keep namespaces, tags, and semantic search logic confined to the LanceDB storage layer (`storage_lancedb.py`) and search services (`search.py`).
- Use FastMCP logging (`logging.py`) to ensure transport-aware routing (stderr vs telemetry).
- Reuse `_shutdown_protected` and `_storage_error_guard` for new FastMCP tools so shutdown semantics and StorageError conversion remain consistent.
- Honour NFR-017A: validation is advisory. Automatic and manual validation MUST never roll back or reject writes solely because diagnostics were reported; unresolved schema references are surfaced as warnings, not top-level errors.
- Treat indices as presentation metadata only. Target cells via `cell_id` for reads, listings, validations, and replacements, and rely on the optional `new_index` parameter when reordering through `scratch_replace_cell`.
- When adding features that affect tool semantics, update:
  - Specification documents (spec, plan, data-model, research, quickstart) to reflect behaviour.
  - Tool prompts in `server.py` so agents receive complete, self-contained guidance.
  - README (operator view) and this file (developer view) if public documentation changes.
- Do **not** introduce Jupyter notebooks or notebook editing tooling; use plain-text specs and code.

## Documentation Responsibilities

- **Operator docs** (`README.md`, `specs/001-scratch-notebook-mcp/quickstart.md`) must stay concise and configuration focused.
- **Contributor docs** (this file plus the specification bundle) should capture architectural rationale, migration steps, and testing requirements.
- **Agent instructions** (canonical metadata tone, parameter annotations, usage notes) must live inside the FastMCP tool prompts (`server.py`) and be mirrored in `AGENTS.md`. When prompts change, update related specification sections and add/complete tasks in `specs/001-scratch-notebook-mcp/tasks.md`.
- Every documentation change should be paired with an entry in `specs/001-scratch-notebook-mcp/implementation.md` so future agents can trace why it happened.

## MCP Tool Reference (Developer View)

All tools are declared in `scratch_notebook/server.py` near the bottom of the file, immediately after their handler implementations. Each tool wraps a `_scratch_*` function that already includes `_shutdown_protected` and `_storage_error_guard`.

| Tool | Handler | Purpose / Notes |
| --- | --- | --- |
| `scratch_create` | `_scratch_create_impl` | Create/reset pads, accepts optional `scratch_id`, metadata (title/description/summary/namespace/tags), and a `cells` array for one-shot creation. Responses return structural summaries (ids/indices/metadata/tags/validation) without raw content—call `scratch_read` for the full payload. |
| `scratch_read` | `_scratch_read_impl` | Read pads with filters for `cell_ids`, tags, namespaces, and optional metadata omission; indices are returned for ordering but never accepted as identifiers. |
| `scratch_list_cells` | `_scratch_list_cells_impl` | Lightweight cell listings (id, index, language, tags, metadata). Filters accept `cell_ids` + tags only. |
| `scratch_delete` | `_scratch_delete_impl` | Delete pads and clean up embeddings. |
| `scratch_list` | `_scratch_list_impl` | List pads with `scratch_id`, canonical metadata, namespace, and `cell_count`. Supports namespace/tag filters and limits. |
| `scratch_list_tags` | `_scratch_list_tags_impl` | Aggregate pad-level and cell-level tags, optionally filtered by namespace. |
| `scratch_append_cell` | `_scratch_append_cell_impl` | Append cells, honoring `validate` flag, schema registry lookups, and eviction handling. Responses mirror `scratch_create` and omit raw content. |
| `scratch_replace_cell` | `_scratch_replace_cell_impl` | Replace cells by `cell_id`, optionally moving them via `new_index`; copies metadata when not supplied and supports validation. Responses also omit content—use `scratch_read` to inspect the updated cell body. |
| `scratch_validate` | `_scratch_validate_impl` | Run validation over all cells or a supplied `cell_ids` subset; respects `validation_request_timeout`. |
| `scratch_search` | `_scratch_search_impl` | Semantic search via `SearchService`; accepts namespace/tag filters and limit. |
| `scratch_list_schemas` | `_scratch_list_schemas_impl` | List stored schemas per pad. |
| `scratch_get_schema` | `_scratch_get_schema_impl` | Retrieve a schema entry by id. |
| `scratch_upsert_schema` | `_scratch_upsert_schema_impl` | Create/update schema entries (validates schema payload before storing). |
| `scratch_namespace_list` | `_scratch_namespace_list_impl` | List namespaces for the active tenant. |
| `scratch_namespace_create` | `_scratch_namespace_create_impl` | Register namespaces. |
| `scratch_namespace_rename` | `_scratch_namespace_rename_impl` | Rename namespaces, optionally migrating pads. |
| `scratch_namespace_delete` | `_scratch_namespace_delete_impl` | Delete namespaces, optionally cascading to pads. |

Refer to the surrounding parameter and output schema definitions in `server.py` when adjusting behaviours or updating contracts.

## Release Checklist

1. Confirm `specs/001-scratch-notebook-mcp/tasks.md` has relevant tasks marked completed.
2. Run the full `pytest` suite.
3. Capture coverage results with:
   ```bash
   python -m coverage run -m pytest
   python -m coverage report -m
   ```
   Record notable coverage gaps (especially around advisory validation semantics) in `specs/001-scratch-notebook-mcp/implementation.md` and open tasks when thresholds regress.
4. Ensure README configuration snippets reference the latest CLI/environment flags.
5. Verify FastMCP tool descriptions accurately describe parameters and expected behaviour.
6. Whenever the user asks for a release/tag, add the new entry to `CHANGELOG.md`, refresh the README release note to the provided version, and update dependency pins if the release requires it.
