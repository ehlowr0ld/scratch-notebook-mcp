# Scratch Notebook MCP Agent Guide

This document equips autonomous agents with the full context required to continue development of the Scratch Notebook MCP server. Follow every rule and checklist below before making changes.

## 1. Core Principles
- Read `.specify/memory/constitution.md` first; treat it as the highest authority for non-negotiable rules.
- Uphold Exploration-First Development, Security-First Design, Non-Blocking Async, and Architectural Boundaries.
- Never block the event loop; avoid `time.sleep()` in async code and offload CPU-bound tasks away from the loop.
- Respect existing patterns - extend before modifying, modify before replacing. Avoid broad refactors unless mandated by spec.
- Do not introduce Jupyter notebooks or notebook tooling; use plain text specs and code files only.
- Never edit or delete files via shell commands; use the provided editing tools. Destructive git commands are strictly forbidden.

## 2. Environment Setup
1. Change to the repo root: `cd /home/rafael/Workspace/Repos/rafael/scratch-notebook`.
2. If a virtual environment already exists, activate it immediately:
   ```bash
   if [ -d .venv ]; then
       source .venv/bin/activate
   fi
   ```
3. To create the environment when missing and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
4. Install or upgrade testing extras (`pytest`, `pytest-asyncio`, etc.) as needed. Maintain the dependency pins declared in `pyproject.toml` (`fastmcp`, `jsonschema`, `PyYAML`, `syntax-checker`, `markdown-analysis`, `lancedb`, `sentence-transformers`).
5. Export `PYTHONPATH="/home/rafael/Workspace/Repos/rafael/scratch-notebook"` before running Python modules.

## 3. Execution Safety
- Wrap potentially long-running shell or Python commands with timeouts, e.g. `timeout 60 pytest tests/integration` or another expected max runtime in seconds.
- Use the fastmcp server transports only via project tooling; do not launch ad-hoc processes that could hang without a timeout.
- Clean up temporary directories created during tests.

## 4. Specification Bundle Reading Order
Always refresh context using the feature specification directory `specs/001-scratch-notebook-mcp/` in this order:
1. `implementation.md` – chronological log of completed work and integration notes.
2. `tasks.md` – authoritative backlog; mark items complete via SpecKit workflows only.
3. `spec.md` – functional requirements and non-functional constraints.
4. `plan.md` – architectural decisions, risk mitigations, sequencing guidance.
5. `data-model.md` – canonical schemas for scratchpads, cells, metadata, namespaces.
6. `contracts/mcp-tools.md` – tool signatures, parameter definitions, prompt requirements.
7. `contracts/transports-and-config.md` – transport matrix, CLI expectations, config flags.
8. `research.md` – background studies, alternative evaluations.
9. `quickstart.md` – operator-oriented setup; ensure examples stay accurate after changes.

Supplementary references:
- Repository root `README.md` for enduser instructions and non-technical documentation.
- `DEVELOPMENT.md` for developer workflow specifics.
- `AGENTS.md` for agent workflow specifics. Update this file when agent-specific instructions change or new instructions are needed!

## 5. Project Modules and Responsibilities
- `scratch_notebook/config.py` – CLI/env parsing, metrics/auth flag validation, auth token file materialisation. Keep metrics implying HTTP constraint intact.
- `scratch_notebook/server.py` – FastMCP app wiring, tool registration, authentication hooks, metrics endpoint, tool prompt text.
- `scratch_notebook/storage_lancedb.py` – LanceDB persistence, eviction policies (discard/fail/preempt), tenant scoping, metrics snapshots.
- `scratch_notebook/storage.py` – Facade exporting storage implementations.
- `scratch_notebook/search.py` – Semantic search orchestration, embedding lifecycle tied to LanceDB.
- `scratch_notebook/namespaces.py` – Namespace CRUD and conventions.
- `scratch_notebook/models.py` – Scratchpad, cell, schema, metadata helpers.
- `scratch_notebook/validation.py` – JSON/YAML schema validation, syntax checks.
- `scratch_notebook/auth.py` – Bearer-token auth provider returning tenant-scoped tokens.
- `scratch_notebook/metrics.py` – Metrics registry, Prometheus formatting, helper recorders.
- `scratch_notebook/errors.py` – Domain error catalog consumed across services.
- `scratch_notebook/logging.py` – FastMCP-aware logging configuration.

## 6. Platform Features Summary
- MCP tool suite for creating, reading, updating, deleting scratchpads with typed cells (json/yaml/code/markdown/text).
- Namespace management and canonical metadata (title, description, summary) for multi-tenant separation.
- Semantic search and tag aggregation backed by LanceDB with embeddings.
- Validation pipeline leveraging `jsonschema`, `PyYAML`, `syntax-checker`, and `markdown-analysis`.
- Eviction strategies (`discard`, `fail`, `preempt`) with optional Preemptive Sweeper.
- HTTP POST and Server-Sent Events transports plus stdio fallback; optional bearer-token authentication.
- Prometheus `/metrics` endpoint reporting operations, errors, evictions, counts, uptime.

## 7. Development Workflow
1. Activate venv (or create if missing) and set `PYTHONPATH`.
2. Run `git status --short` to confirm workspace state; never revert unrelated changes.
3. Read the latest entries in `implementation.md`, check `tasks.md` for next items, and align work with planning documents.
4. Before implementing, perform reconnaissance: identify target modules, confirm existing patterns, locate relevant tests.
5. Update tool prompts when behaviour changes; keep namespace guidance consistent for shared default tenant usage.
6. When modifying behaviour, update spec documents as required and append new tasks via the constitution process.
7. Maintain real-time checklist synchronization: mark `tasks.md` items complete immediately after verifying requirements.
8. When the user requests a release or provides a version tag, add/refresh the matching entry in `CHANGELOG.md`, update the README release note to that version, and record the action in `specs/001-scratch-notebook-mcp/implementation.md` before handing the work back.

## 8. Testing Strategy
- Default command: `timeout 60 pytest`.
- Use targeted runs for faster feedback:
  - `timeout 60 pytest tests/unit`
  - `timeout 60 pytest tests/integration`
  - `timeout 60 pytest tests/contract`
- Write tests before or alongside fixes (TDD where feasible) for business logic, transports, and CLI behaviour.
- Integration tests must use FastMCP transports with proper authentication and metrics toggles; prefer in-memory ASGI clients with `httpx.ASGITransport`.
- Never weaken existing tests; adjust implementation to satisfy assertions unless a test is genuinely wrong. Document any necessary test change.

## 9. Writing New Tests
- Mirror existing patterns: async tests should use `pytest.mark.anyio` or `pytest.mark.asyncio` as appropriate.
- For CLI/config parsing, favour unit tests under `tests/unit/` with explicit flag combinations.
- For transport behaviour, place tests under `tests/integration/`, ensuring metrics/auth flags cover required matrices.
- Contract tests (`tests/contract/`) validate MCP tool schemas; update prompt metadata there when instructions change.

## 10. Tips and Secret Sauce
- Start each session with a full SpecKit audit: constitution → spec → plan → tasks → implementation log.
- Use `specs/001-scratch-notebook-mcp/implementation.md` as your scratch timeline; append concise notes after major work to aid future agents.
- For namespace-sensitive features, always call `scratch_namespace_list` in tests/examples to model expected agent behaviour.
- When dealing with eviction logic, leverage `Storage.snapshot_counts()` and metrics helpers to verify gauge values.
- Keep logging consistent by using utilities from `scratch_notebook/logging.py`; avoid bare `print`.
- For semantic search, verify embedding lifecycle in both storage and search modules; reuse helper functions instead of duplicating queries.
- Always include commands within `timeout` to prevent blocking CI or interactive sessions.
- Before finalizing work, re-run full pytest, update documentation snippets, and ensure tool prompts remain self-contained.

Adhering to this guide ensures continuity across autonomous developer sessions and preserves architectural integrity of the Scratch Notebook MCP server.

## 11. Current Status and Expectations

- All tasks in `specs/001-scratch-notebook-mcp/tasks.md` are currently marked `[X]` and the latest implementation log entry (`2025-11-19T07:30Z`) records the final cleanup plus a full `pytest` run (183 tests). Treat the project as feature-complete unless a new specification entry or task is created.
- Before starting new work, run `./.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`, review `implementation.md`, and confirm whether new tasks need to be added via `/speckit.tasks`.
- Every substantive change must finish with an updated implementation log entry, synced checklist items, and a full `timeout 300 pytest` run (or the narrowest failing suite followed by the full run).
- When you update documentation, prompts, or behaviour, synchronize `README.md`, `DEVELOPMENT.md`, `AGENTS.md`, and the specification bundle in the same change set so all three audiences (operators, contributors, agents) stay aligned.
- If you introduce a new phase of work, create fresh tasks/checklists before touching code so future agents inherit an accurate backlog.

## 12. MCP Tool Quick Reference

| Tool | When to use it | Key hints |
| --- | --- | --- |
| `scratch_create` | Start/reset pads with canonical metadata (title, description, summary, namespace, tags). Reuse existing namespace prefixes discovered via `scratch_namespace_list`. |
| `scratch_read` | Pull full pad content. Use `cell_ids`, `tags`, `namespaces`, and `include_metadata=false` when you only need specific cells. Indices are returned for ordering but never accepted as selectors. |
| `scratch_list` | Browse pads quickly. Returns `scratch_id`, canonical metadata, namespace, and `cell_count`. Combine with namespace/tag filters. |
| `scratch_list_cells` | Get a lightweight view of cells (id, index, language, tags) without retrieving the entire pad. Filter by `cell_ids` and tags. |
| `scratch_append_cell` / `scratch_replace_cell` | Add or modify cells. Always supply `cell_id` when replacing. Optional `new_index` lets you move the targeted cell to a new position while replacing it. Set `validate=true` to trigger advisory JSON/YAML/code/markdown checks before the change persists. |
| `scratch_delete` | Remove pads by id. |
| `scratch_list_tags` | Show tag vocabulary (pad + cell tags) optionally filtered by namespace—useful before building tag filters. |
| `scratch_validate` | Re-run validation on any subset of cells (supply `cell_ids`, or omit to validate all). Handy after editing metadata or referencing new schemas. |
| `scratch_search` | Semantic search across pads, filtering by namespaces/tags when you need scoped results. |
| `scratch_list_schemas` / `scratch_get_schema` / `scratch_upsert_schema` | Manage schema registry entries so append/replace/validate can reference `scratchpad://schemas/<name>` ids. |
| `scratch_namespace_list` / `scratch_namespace_create` / `scratch_namespace_rename` / `scratch_namespace_delete` | Keep namespace prefixes organised when multiple projects share the tenant. Avoid creating new namespaces unless necessary, and prefer renaming over deleting when existing pads should migrate. |

Indices in responses are for presentation only. Always target cells via `cell_id`, and pass the optional `new_index` argument to `scratch_replace_cell` when you need to reorder a cell while editing it.

Validation reminders:
- Automatic validation triggers only when you pass `validate=true` on append/replace. Otherwise, call `scratch_validate` explicitly. Validation is advisory: diagnostics never cause a cell to be dropped or a write to be rejected.
- Validation covers JSON/YAML (with schema support), Markdown, and code via `syntax-checker`. Unsupported languages return “not validated” but never crash the flow. Missing shared schemas (for example `scratchpad://schemas/<name>`) are reported as warnings only.
- Timeouts follow `validation_request_timeout`; handle `VALIDATION_TIMEOUT` gracefully and retry with smaller batches if needed. Always use `cell_ids` when selecting specific cells.
