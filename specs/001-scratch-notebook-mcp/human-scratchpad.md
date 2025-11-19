/speckit.clarify  Scratch Notebook MCP. See the initial specification and trechnical research document at @scratch-notepad-tool.md and do not diverge from the technical specification developed during the brainstormng session documented within that document. Use the document as part of clarification process.

/speckit.tasks Considering Constitution @constitution.md  Keeping documentation in sight: @FastMCP Server Docs @Python JSON Schema Module @PyYAML @Syntax Checker @mrkdwn_analysis . Based onj all other documents we will now create a tasks definition. At the end of this command is the list of phases generated for the impölementation partitioning.

**Proposed implementation phases (slices)**

1. **Phase 1 – Package Skeleton And Configuration Plumbing**
   Create the `scratch_notebook` Python package, wire up `fastmcp` server scaffolding, implement config loading (CLI/env/config file), and honor core NFRs (time-unit parsing, storage_dir validation, basic logging, graceful shutdown hooks) without implementing tools yet.

2. **Phase 2 – Core Domain Model, Storage, And Basic Scratchpad Lifecycle**
   Implement in-memory/domain models (Scratchpad, ScratchCell) plus the storage layer (directory-based persistence, UUID id generation/checking, durability guarantees). Then implement and test `scratch_create`, `scratch_read`, `scratch_delete`, and `scratch_list` end-to-end over MCP/stdio.

3. **Phase 3 – Cell Editing Tools, Concurrency, And Limits**
   Implement `scratch_append_cell` and `scratch_replace_cell` with atomic last-writer-wins semantics, enforce `max_scratchpads`, `max_cells_per_pad`, and `max_cell_bytes`, and implement LRU tracking and discard/fail eviction behavior, including structured errors and logging.

4. **Phase 4 – Validation Pipeline And `scratch_validate`**
   Integrate `jsonschema`, `PyYAML`, `syntax-checker`, and `markdown-analysis` behind a unified validation API; implement automatic per-cell validation and the `scratch_validate` tool with full `ValidationResult` shapes, request-level timeout handling, and validation-related error codes.

5. **Phase 5 – Eviction Sweeper And Preemptive Retention Policy**
   Implement the `preempt` eviction policy and background sweeper using the shared time-unit configuration, integrate with capacity logic, and surface sweeper behavior via logs (and optionally SSE/metrics), ensuring consistency with durability and concurrency rules.

6. **Phase 6 – HTTP/SSE Transports, Auth, And Metrics Endpoint**
   Add the shared HTTP listener with `/http`, `/sse`, and optional `/metrics`; map MCP tools to HTTP RPC, expose SSE events where needed (for example eviction notifications), implement optional bearer-token auth and tenant scoping, and expose Prometheus metrics per the transport contract.

7. **Phase 7 – End-to-End Testing, Hardening, And Documentation Polish**
   Build out unit, integration, and contract tests to cover all tools and transports, validate examples against the canonical JSON Schemas, tune logging and error messages, and align README/quickstart and contracts with the final behavior before moving on to actual implementation tasks in `/speckit.tasks`.
