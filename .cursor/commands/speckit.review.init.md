---
description: Initialize streamlined SpecKit review workspace and import specification JSON payloads.
---

## User Input

```text
$ARGUMENTS
```

You MUST consider the user input before proceeding (if not empty).

## Step-by-Step Workflow

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g. `'I'\''m Groot'` (or double-quote if possible: "I'm Groot").
   - Treat any non‑zero exit or unparsable output as a blocker; stop and resolve before proceeding.
   - Persist the resolved absolute `${FEATURE_DIR}` for all subsequent steps; do not recompute differently mid‑run.
   - Honor applicable user input constraints (e.g., branch, scope); document assumptions when inputs are ambiguous.
   - Immediately determine the commit boundaries and branch for this review:
     - If the user specifies boundaries use them as is. If the user provides partial boundaries flag this and stop the workflow.
     - If the user doesn't specify boundaries use the range between origin branch and local branch both matching the name of the current branch.
     - If there is no remote branch in origin with matching name use the last commit on the local branch as the subject to review.
   - If any of these commands fail, pause and fix the repository state before continuing.

2. Choose a deterministic `RUN_ID` (example: `review-20251108-main-001`) and reuse it for the entire run.
   - Construct deterministically (recommend: `review-<UTC YYYYMMDD>-<branch|tag>-<NNN>`). Reuse across restarts of the same run to preserve traceability.
   - Never create multiple RUN_IDs for the same feature review. If a mistake occurs, restart using the original RUN_ID.

3. Execute `.specify/scripts/bash/review-init.sh --run_id 'RUN_ID' [--base '<sha>'] [--head '<sha>'] [--branch '<name>']` from the repository root.
   - Pass the exact base/head commits and branch you collected in step 1, for example:<br>`./.specify/scripts/bash/review-init.sh --run_id 'review-20251112-main-001' --base 'abc1234' --head 'def5678' --branch '002-project-scheduled-tasks'`
   - Treat any missing or mismatched arguments as a blocker - do not guess. Re-run the prerequisite commands if you need to reconfirm the values.
   - The script bootstraps the encrypted ledgers and run workspace. Confirm it exits cleanly before moving on.
   - Do not run import/append commands until this step completes successfully.

4. Read all specification artifacts within the feature directory (spec, plan, tasks, research, data model, quickstart, contracts).
   - Use only the artifacts present in `${FEATURE_DIR}` as the authoritative evidence set; do not import external sources.
   - If `${FEATURE_DIR}/report.md` contains appended remediation summaries (headings such as `## Remediation Summary – <date> #<N>`) or `${FEATURE_DIR}/remediation/` holds supplemental artifacts, review them for context before proceeding. Skip this branch when those assets are absent. When remediation sections exist, read the earlier review content in `report.md` as well to re-establish the full history before analyzing new work.
   - Do not edit these artifacts during import. Capture intent faithfully; avoid editorializing beyond making wording measurable.
   - Reconstruct the intended architecture and feature design from these sources before touching implementation details. Identify mandated boundaries, integration contracts, data flow expectations, and non-functional constraints so you can later judge whether the code adheres to them. Record explicit notes about unacceptable architectural regressions versus acceptable deviations to guide severity decisions in `/speckit.review.record` and `/speckit.review.finish`.

5. Build a JSON payload that matches the Spec Import JSON Schema and capture every required mapping:
   - Derive the smallest possible feature modules from the specification that represent clear, factual logical or functional units.
   - Ensure full coverage of the specification by the feature modules; no orphaned requirements or unmapped stories.
   - Maintain clear and unambiguous feature module definitions with single responsibility boundaries and minimal overlap.
   - Always add a deterministic “supporting changes” feature module (for example `SUPPORTING-CHANGES`) to capture work required to unblock the delivery but not mandated by the spec (hotfixes, refactors, environment prep). Populate it only with those auxiliary efforts.
   - Evaluate whether the specification explicitly calls for documentation deliverables. If it does not, create an additional feature module (e.g., `DOCUMENTATION-GAP`) to track documentation authored during the change or to flag documentation that must be produced to round out the release.
   - Keep descriptions concise, measurable, and ≥ the schema minimum lengths; prefer outcome-focused phrasing over vague terms.
   - Use stable, deterministic slugs for requirements/stories/phases; verify uniqueness and consistency across sections.
   - Do not omit any traceability identifiers in the import payload.
   - Maintain a detail level sufficient to perform an entire code review based only on the items captured in the summary payload and not requiring the full specification to be present. Capture all **relevant** nuances and details in addition to general descriptions.
   - **MANDATORY:** The payload is plain JSON. Do not add comments, trailing commas, custom tags, or any other markup. The contents must validate exactly against the schema without extra syntax or semantics.

6. Import the payload with `review-import-spec.sh`, supplying either `--json '<payload>'` or `--file '<path>'`.
   - Validate that the command returns success; treat failures as blockers and correct the payload rather than weakening constraints.

7. When additional identifiers are needed, construct a payload that follows the Append Spec JSON Schema and call `review-append-spec.sh`.
   - Prefer append for additive changes to preserve existing slugs. Re-import only when structural errors in the baseline require reset (record rationale).

8. Run `review-spec-validate.sh --run_id 'RUN_ID'` to confirm the specification is complete before proceeding to `/speckit.review.record`.
   - The validator writes `${FEATURE_DIR}/.reviews/${RUN_ID}/spec-overview.md`. Open this file now to verify every phase, story, criterion, and module you recorded.
   - Copy it to `${FEATURE_DIR}/spec-overview-${RUN_ID}.md` immediately so the snapshot sits alongside `spec.md` and `plan.md`. If earlier snapshots exist, keep them intact - do not delete or overwrite.
   - If the new identifiers differ from a previous run, summarize the slug remapping (old → new) in your review notes before proceeding so remediation histories stay reconcilable. Ensure the filename you just copied is what you will record later in the `Spec Snapshot File` row of `report.md`.
   - Do not proceed to recording until validation succeeds with no unresolved errors.

## Spec Import JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Spec Import Payload",
  "type": "object",
  "required": [
    "name",
    "overview",
    "details",
    "phases",
    "user_stories",
    "acceptance_criteria",
    "feature_modules"
  ],
  "properties": {
    "name": { "type": "string", "minLength": 3 },
    "overview": { "type": "string", "minLength": 25 },
    "details": { "type": "string", "minLength": 25 },
    "phases": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    },
    "user_stories": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    },
    "acceptance_criteria": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    },
    "feature_modules": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    }
  },
  "additionalProperties": false
}
```

## Append Spec JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Append Spec Payload",
  "type": "object",
  "properties": {
    "phases": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    },
    "user_stories": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    },
    "acceptance_criteria": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    },
    "feature_modules": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "string", "minLength": 25 }
    }
  },
  "additionalProperties": false
}
```

## Operational Notes
- Use `--file` when editing large payloads; keep identifiers deterministic.
- Re-importing the full specification resets validation; always rerun `review-spec-validate.sh` afterward.
- Append commands update only the sections provided; untouched sections remain intact.
- Prefer stable ordering of keys and arrays in JSON payloads to make diffs deterministic and reproducible (tooling-agnostic recommendation).

## Professional Review Enhancements (Traceability & Inputs)
- Evidence-first inputs: Only use available artifacts in the feature directory: `spec.md`, `plan.md`, `tasks.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`. If any of `spec.md` or `tasks.md` are missing, halt and fix prerequisites before proceeding.
- Stable requirement slugs: Encode traceable, stable keys in the import payload:
  - Use identifiers based on specification identifiers: `acceptance_criteria` → `"SC-001"`/`"AC-001"`, functional requirements → `"FR-001"`, non-functional → `"NFR-001"`, `user_stories` → `"US-003"`, `phases` → `"PH-1"`, `feature_modules` → reviewer-defined (e.g., `"AUTH-SVC"`, not stable) with descriptive values.
  - These keys become canonical slugs for deterministic linkage (except `feature_modules`, which are logical and may change); reference them in file-review findings.
- Minimal high-signal extraction: From `spec.md`, capture requirements and user stories; from `plan.md`, capture architecture boundaries and constraints; from `tasks.md`, capture formal task IDs and file touchpoints. Prefer concise, measurable descriptions (avoid vague terms).
- Traceability model (lightweight): Ensure each imported section enables bidirectional mapping:
  - Requirement slug → description (acceptance_criteria)
  - User story slug → description (user_stories)
  - Module slug → responsibility boundary (feature_modules)
  - Phase slug → scope narrative (phases)
- Do not omit any traceability identifiers in the import payload.
- Constitution and principles: If the imported spec reveals contradictions (e.g., requirements conflict with plan boundaries), note them and resolve in `tasks.md` before deeper review. Treat such conflicts as Critical in later phases. Do not “paper over” conflicts by weakening wording; record them explicitly.
- Approval standard: Adopt the principle “approve when overall code health improves and all blockers are resolved”. Judge code quality based on the principles of the review process and the evidence set. This principle informs the merge verdict in the final report.
