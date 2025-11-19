<!--
Sync Impact Report
- Version change: unversioned draft → 0.1.0 (initial ratified constitution for Scratch Notebook MCP Server)
- Modified principles: none (imported from previous draft `.specify/memory/constitution.md_` without semantic change)
- Added sections: Metadata, Specification Alignment, this Sync Impact Report header
- Removed sections: none
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (Constitution Check section already defers to this file)
  - ✅ .specify/templates/spec-template.md (no constitution-specific assumptions)
  - ✅ .specify/templates/tasks-template.md (no constitution-specific assumptions)
  - ✅ .specify/templates/checklist-template.md (no constitution-specific assumptions)
  - ✅ .specify/templates/review-report-template.md (no constitution-specific assumptions)
  - ⚠ .specify/templates/commands/*.md (directory not present; no command templates to verify)
- Deferred placeholders: none
-->

# Scratch Notebook MCP Server - Project Constitution

## Metadata

- Project: Scratch Notebook MCP Server
- Constitution version: 0.1.0
- Ratification date: 2025-11-16
- Last amended date: 2025-11-16

## Core Principles

### I. Exploration-First Development (NON-NEGOTIABLE)

**Principle**: Systematically explore codebase, dependencies and documentation before implementation. Never assume - always verify.

**Requirements**:
- Read actual source files to verify API interfaces exist
- Map patterns through code analysis to understand component interactions
- Verify imports, method signatures, class hierarchies
- Test basic functionality: imports work, methods exist, execution succeeds
- Proceed with implementation ONLY after verification complete

**Rationale**: Assumptions cause catastrophic failures. This principle prevents building on non-existent interfaces, missing methods, or incorrect architectural understanding. Professional development requires evidence-based decisions.

---

### II. Transparency Over Magic

**Principle**: Every decision must be visible and traceable throughout the system.

**Requirements**:
- No hidden abstractions or "magical" behavior
- Clear, explicit code paths
- Documented decision points
- Visible state transitions
- Traceable execution flow

**Rationale**: Debugging, maintenance, and collaboration require understanding how systems work. Hidden complexity creates technical debt and blocks contribution.

---

### III. Security-First Design (NON-NEGOTIABLE)

**Principle**: Security is not optional and must be architected from the foundation.

**Requirements**:
- Input validation
- Secure process execution
- Safe dynamic code management

**Rationale**: Security violations cannot be patched in later. They must be architectural constraints from day one to prevent data breaches and system compromise.

---

### IV. Non-Blocking Async (NON-NEGOTIABLE)

**Principle**: Use asyncio exclusively - never block the event loop.

**Requirements**:
- Use `await asyncio.sleep()` NEVER `time.sleep()`
- All I/O operations must be async
- CPU-bound work offloaded from event loop
- Proper async/await patterns throughout
- No synchronous blocking calls in async contexts

**Rationale**: Event loop blocking causes system-wide performance degradation, unresponsiveness, and cascading failures. Async discipline is foundational to scalable systems.

---

### V. Self-Contained Components

**Principle**: Components must be independently functional with no global dependencies.

**Requirements**:
- Component-local dependency injection only

**Rationale**: Self-contained components are portable, testable, debuggable, and maintainable.
---

### VI. Infrastructure Invisibility

**Principle**: Plumbing commands and infrastructure operations must be hidden from users.

**Requirements**:
- Users see task-relevant operations only
- Infrastructure commands execute silently
- Clean separation of concerns

**Rationale**: Users care about outcomes, not implementation details. Infrastructure noise creates confusion and poor user experience.

---

### VII. Architectural Boundaries (NON-NEGOTIABLE)

**Principle**: Respect established patterns without creating parallel systems.

**Requirements**:
- Prefer extending existing patterns over introducing new architectures
- Avoid parallel solutions for the same concern
- Keep feature scope local unless the spec explicitly demands shared infrastructure

**Rationale**: Architectural fragmentation creates long-term complexity, brittle integrations, and duplicated effort. Maintaining clear boundaries preserves coherence and keeps the system evolvable.

---

## Specification Alignment

- The technical scope for this project is defined in `specs/scratch-notepad-tool.md`
  (Scratch Notebook MCP Server specification).
- Implementation decisions MUST align with that specification unless an explicit
  amendment is made and recorded through the governance process below.
- Any divergence from the specification MUST document:
  - The reason for divergence
  - The intended migration path
  - The impact on existing tools and clients

---

## Governance

### Constitution Authority

- This constitution supersedes all other practices and guidelines
- Amendments require documentation, approval, and migration plan
- All code reviews must verify compliance
- Complexity must be justified against constitutional principles
- Violations must be documented with rationale and mitigation

### Amendment Procedure

1. Propose change with rationale and impact analysis
2. Document affected systems and required migrations
3. Obtain approval from project maintainers
4. Update constitution with version increment
5. Update all dependent templates and documentation
6. Communicate changes to development team
7. Execute migration plan

### Version Increments

- **MAJOR**: Backward incompatible governance/principle removals or redefinitions
- **MINOR**: New principle/section added or materially expanded guidance
- **PATCH**: Clarifications, wording, typo fixes, non-semantic refinements

### Compliance Review

- All PRs must pass constitutional compliance check
- Architecture decisions documented with constitutional alignment
- Violations require explicit justification and mitigation plan
- Regular audits to ensure ongoing compliance

### Others

- Clean code policy
- Separate code, prompts, and documentation files
- High level of maintainability
- Clear explicit design decisions
- Full documentation compliance for all external dependencies
- Follow best practices for code style, architecture, and documentation
- Follow best practices for logging and packaging
- No tracing infrastructure, no performance monitoring infrastructure
- Targeted testing with coverage targeting 100% for new code, 100% successful execution for all tests


