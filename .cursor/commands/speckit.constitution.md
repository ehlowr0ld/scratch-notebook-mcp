---
description: Create or update the project constitution from interactive or provided principle inputs, ensuring all dependent templates stay in sync
---

## User Input

```text
$ARGUMENTS
```

You MUST consider the user input before proceeding (if not empty).

## Outline

You are updating the project constitution at `.specify/memory/constitution.md`. This file is a TEMPLATE containing placeholder tokens in square brackets (e.g. `[PROJECT_NAME]`, `[PRINCIPLE_1_NAME]`). Your job is to (a) collect/derive concrete values, (b) fill the template precisely, and (c) propagate any amendments across dependent artifacts.

Follow this execution flow:

1. Load the existing constitution template at `.specify/memory/constitution.md`.
   - Identify every placeholder token of the form `[ALL_CAPS_IDENTIFIER]`.
   - Adaptive principle count: If the user requests fewer or more principles than the template shows, adapt section counts accordingly while preserving the template’s structure and headings.

2. Collect/derive values for placeholders:
   - If user input (conversation) supplies a value, use it.
   - Otherwise infer from existing repo context (README, docs, prior constitution versions if embedded).
   - Governance dates:
     - `RATIFICATION_DATE` is the original adoption date (if unknown ask concisely or mark TODO).
     - `LAST_AMENDED_DATE` is today if changes are made, otherwise keep previous.
   - Versioning:
     - `CONSTITUTION_VERSION` must increment per semantic versioning:
       - MAJOR: Backward-incompatible governance/principle removals or redefinitions.
       - MINOR: New principle/section added or materially expanded guidance.
       - PATCH: Clarifications, wording, typo fixes, non-semantic refinements.
     - If bump type is ambiguous, state your reasoning and proposed bump before finalizing (inline in the Sync Impact Report).
   - Adaptive clarification policy:
     - Ask targeted questions only when a value blocks correct filling or propagation.
     - Default question budget: up to 3 micro‑questions; may expand to 5 only for high‑impact governance items (security, compliance, versioning).
     - If interaction is not possible, insert `TODO(<FIELD_NAME>): explanation` and proceed.

3. Draft the updated constitution content:
   - Replace every placeholder with concrete text (no unexplained bracket tokens left). If the project intentionally keeps a placeholder for future definition, retain it and justify inline once.
   - Preserve heading hierarchy. Remove template comments once replaced unless they still add clarifying guidance.
   - Each Principle section must include:
     - Succinct name line
     - Bullet(s) or paragraph capturing non‑negotiable rules (MUST/SHOULD with rationale)
     - Explicit rationale if not obvious
   - Governance section must include:
     - Amendment procedure
     - Versioning policy
     - Compliance review expectations and cadence

4. Consistency propagation checklist (active validations):
   - Read `.specify/templates/plan-template.md` and ensure any "Constitution Check" or rules align with updated principles.
   - Read `.specify/templates/spec-template.md` for scope/requirements alignment - update if constitution adds/removes mandatory sections or constraints.
   - Read `.specify/templates/tasks-template.md` and ensure task categorization reflects new or removed principle-driven task types (e.g., observability, versioning, testing discipline).
   - Read each command file in `.specify/templates/commands/*.md` (including this one) to verify no outdated agent-specific references remain where generic guidance is appropriate.
   - Read runtime guidance docs (e.g., `README.md`, `docs/quickstart.md`, or agent-specific guidance files if present). Update references to principles that changed.

5. Produce a Sync Impact Report (prepend as an HTML comment at top of the constitution file after update):
   - Version change: old → new (with bump rationale)
   - Modified principles (old title → new title if renamed)
   - Added sections
   - Removed sections
   - Templates requiring updates (✅ updated / ⚠ pending) with file paths
   - Deferred placeholders (TODOs) with brief justification

6. Validation before final output:
   - No remaining unexplained bracket tokens.
   - Version line matches report.
   - Dates use ISO format YYYY-MM-DD.
   - Principles use normative language and are testable (avoid vague phrasing; prefer MUST/SHOULD with rationale).
   - Propagation checks complete; pending items explicitly listed in the Sync Impact Report.

7. Write the completed constitution back to `.specify/memory/constitution.md` (overwrite).

8. Output a final summary to the user with:
   - New version and bump rationale.
   - Any files flagged for manual follow-up.
   - Suggested commit message (e.g., `docs: amend constitution to vX.Y.Z (principle additions + governance update)`).

Formatting & Style Requirements:

- Use Markdown headings exactly as in the template (do not demote/promote levels).
- Wrap long rationale lines for readability (<100 chars ideally) without awkward breaks.
- Keep a single blank line between sections.
- Avoid trailing whitespace.

If the user supplies partial updates (e.g., only one principle revision), still perform validation and version decision steps.

If critical info is missing (e.g., ratification date truly unknown), insert `TODO(<FIELD_NAME>): explanation` and include in the Sync Impact Report under deferred items.

Do not create a new template; always operate on the existing `.specify/memory/constitution.md` file.
