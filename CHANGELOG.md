# Changelog

All notable changes to this project will be documented in this file. This project follows semantic versioning once tags are published.

## v0.0.9 - 2025-11-19

### Added
- Initial publication of the Scratch Notebook MCP server with LanceDB-backed storage, UUID-scoped scratchpads, typed cells, and advisory validation across JSON, YAML, code, markdown, and plain text.
- Namespace, tag, and schema-registry tooling plus semantic search, letting assistants organise pads per tenant and rediscover prior work by metadata, tag filters, or embeddings.
- Full transport surface (stdio MCP and HTTP+SSE) with optional bearer-token auth, plus optional Prometheus `/metrics` output and eviction policies (discard/fail/preempt) to keep storage under control.

### Changed
- Established the MCP prompt set, documentation bundle, and SpecKit workflow that the project follows for all future work.

## v0.1.0 - 2025-11-21

### Added
- Introduced explicit `new_index` support on `scratch_replace_cell`, allowing assistants to reorder cells while updating their content.
- Added a project-wide CHANGELOG process so future releases document their changes alongside the README release note.

### Changed
- All edit, read, list, and validation flows now target cells exclusively by `cell_id`, keeping positional indices as presentation metadata only.
- FastMCP prompts, specifications, and documentation now describe validation as advisory guidance and emphasise the id-only contract for every tool.
- Updated tests and LanceDB storage helpers to enforce the id-first addressing model and maintain contiguous indices after reordering.
- Storage startup now materializes a LanceDB scalar index on `tenant_id`, and default-tenant migration uses filtered scans instead of full-table pylist copies, keeping auth enablement fast even with >10k pads.
- Semantic search pushes tenant/namespace predicates down to LanceDB via `where(..., prefilter=True)` before applying limits; new unit tests verify both the migration filter path and prefilter accuracy.
