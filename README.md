# Scratch Notebook MCP Server

Scratch Notebook MCP keeps your AI assistant grounded. It offers named scratchpads, typed cells, validation, namespaces, and semantic search so ideas stay organised inside any MCP-enabled workspace.

## What Your Assistant Gains

- **Context that sticks** – Give each scratchpad a friendly title, description, and summary so future prompts surface the right work instantly.
- **Reliable content** – JSON, YAML, Markdown, and popular code snippets are checked automatically, helping your assistant hand back ready-to-use artefacts.
- **Tag-aware organisation** – Namespaces and tags keep related pads together, so your assistant can filter lists or reads to exactly what matters now.
- **Semantic recall** – Vector search highlights past notes that sound like today’s problem, giving your assistant instant inspiration.

## Connect It To Your Agent

1. Ensure [`uv`](https://github.com/astral-sh/uv) is available (Claude Desktop and most MCP runtimes ship with it).
2. Add the server to your MCP client configuration. Here is the canonical Claude Code layout (adjust paths or flags for your setup):

   ```json
   {
     "mcpServers": {
       "scratchpad": {
         "command": "uvx",
         "args": [
           "--from=git+https://github.com/ehlowr0ld/scratch-notebook-mcp",
           "scratch-notebook",
           "--storage-dir",
           "${workspaceFolder}/.scratch-notebook/data"
         ],
         "env": {
           "SCRATCH_NOTEBOOK_ENABLE_STDIO": "true",
           "SCRATCH_NOTEBOOK_ENABLE_HTTP": "false",
           "SCRATCH_NOTEBOOK_ENABLE_SSE": "false"
         }
       }
     }
   }
   ```
3. Reload your assistant and invite it to run tools like `scratch_create`, `scratch_read`, or `scratch_search`. `uvx` installs the package automatically the first time it is needed.

## Tweak The Experience

The defaults favour a single assistant on your local machine over stdio. If you want to share the server with additional assistants or another host, enable HTTP/SSE and secure them with bearer tokens:

- `--enable-http true --enable-sse true` switches on the network transports while stdio stays available.
- Repeat `--auth-token principal:token` to register assistants; each request must send the matching `Authorization: Bearer <token>` header.
- `--auth-token-file <path>` and `--config-file <path>` capture the merged settings on disk so you can drop most CLI flags later.
- `--enable-metrics true` exposes a Prometheus stream at `/metrics` (or `--metrics-path`) on the HTTP listener. Metrics require `--enable-http true`, though SSE can remain on or off.

Other handy switches:

- `--storage-dir <path>` keeps all scratchpad data under a directory you control (defaults to `./scratch-notebook` relative to where you start the server).
- `--max-scratchpads`, `--max-cells-per-pad`, and `--max-cell-bytes` curb runaway sessions.
- Time-based knobs (`--preempt-age`, `--preempt-interval`, `--validation-request-timeout`, `--shutdown-timeout`) accept `15s`/`10m`/`24h` style strings; omit the suffix to fall back to the documented default units.
- Semantic search settings (for example embedder selection or prebuilt indexes) share the same configuration surface; your assistant will honour them automatically.

## Everyday Tool Flow

- **Create and curate** – `scratch_create` opens a new pad (optionally seeding it with a `cells` array that persists atomically), `scratch_delete` removes it, and `scratch_list` shows every pad with lean metadata so assistants can jump to the right one. `scratch_list_cells` peeks at cell summaries without fetching full content, and write responses themselves already stick to structural data (ids/indices/metadata) so you can stay within token budgets—call `scratch_read` whenever you need the full payload.
- **Edit with guardrails** – `scratch_append_cell` and `scratch_replace_cell` extend notebooks cell by cell. Set the `validate` flag when you want the server to run JSON/YAML/code/markdown checks before content is saved; validation is advisory only, your notes are never discarded because of diagnostics. `scratch_replace_cell` also accepts `new_index` so you can reorder a cell while updating it. Write responses mirror `scratch_create` by omitting raw `content`; follow up with `scratch_read` if the assistant needs to re-display the entire cell.
- **Review and filter** – `scratch_read` returns the full pad and lets agents filter by `cell_ids`, tags, or namespaces. Indices are still returned in responses so you can display ordering, but edits and validations always target cells by `cell_id`. `scratch_list_tags` surfaces the tag vocabulary, and `scratch_list_schemas` + `scratch_get_schema` reveal shared schema helpers.
- **Validate on demand** – `scratch_validate` re-checks any subset of cells (supply `cell_ids`, or omit to validate all), returning structured results so assistants can highlight issues without changing stored content. Indices still appear in responses for reference, but selectors must always be `cell_id`s.
- **Search and navigate** – `scratch_search` uses semantic embeddings to find related notes. Namespace helpers (`scratch_namespace_list/create/rename/delete`) keep multi-project work segregated.
- **Schema registry** – `scratch_upsert_schema` lets assistants register JSON Schemas once and reference them from future cells via `scratchpad://schemas/<name>`; missing schemas simply produce validation warnings.

## Need Developer Details?

Contributor notes, architecture decisions, and testing instructions live in `DEVELOPMENT.md`. Agent-facing prompts and workflow guidance live in `AGENTS.md`.

## Release Hygiene

Before tagging a build or publishing a new binary, run the coverage gate and record any lingering gaps:

```bash
python -m coverage run -m pytest
python -m coverage report -m
```

Treat uncovered advisory-validation branches as action items—log them in `specs/001-scratch-notebook-mcp/implementation.md` and schedule new tasks in `specs/001-scratch-notebook-mcp/tasks.md` so future releases stay honest about validation guarantees.

## License

Current release: **v0.1.0** — see `CHANGELOG.md` for the detailed history. This repository remains unpublished; consult the owner before redistributing.
