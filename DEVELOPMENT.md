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
2. Install test extras as new dependencies are introduced (for example `pytest`, `pytest-asyncio`). `uv pip install -r requirements-dev.txt` works as an alternative when using uv.
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

## Release Checklist

1. Confirm `specs/001-scratch-notebook-mcp/tasks.md` has relevant tasks marked completed.
2. Run the full `pytest` suite.
3. Ensure README configuration snippets reference the latest CLI/environment flags.
4. Verify FastMCP tool descriptions accurately describe parameters and expected behaviour.
5. Update `CHANGELOG.md` (if introduced) and dependency pins as needed.
