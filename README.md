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
       "scratch-notebook-mcp": {
         "command": "uvx",
         "args": [
           "--from=https://github.com/ehlowr0ld/scratch-notebook-mcp",
           "scratch-notebook",
           "--storage-dir",
           "/tmp/scratch-notebook-data"
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

- **`scratch_create`** – Open or reset a pad with descriptive metadata so future searches stay meaningful.
- **`scratch_append_cell` / `scratch_replace_cell`** – Grow the notebook cell-by-cell while validation keeps content safe.
- **`scratch_read`** – Revisit work, optionally filtering by cell ids, tags, or namespaces and choosing whether to pull back metadata.
- **`scratch_list` and `scratch_list_cells`** – Browse pads or zoom into cell detail when choosing what to reuse.
- **`scratch_namespace_*` & tagging tools** – Keep projects separated and curated.
- **`scratch_search`** – Find the right snippet even when only a fuzzy memory remains.

## Need Developer Details?

Contributor notes, architecture decisions, and testing instructions live in `DEVELOPMENT.md`. Agent-facing prompts and workflow guidance live in `AGENTS.md`.

## License

This project is currently unpublished; consult the repository owner before redistributing.
