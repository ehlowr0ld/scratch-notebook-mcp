---
description: Inspect diffs, batch record file reviews via JSON payloads, and monitor progress.
---

## User Input

```text
$ARGUMENTS
```

You MUST consider the user input before proceeding (if not empty).

## Run ID Inference

If run_id is not present in conversation history, try to infer it from user input.
If run_id is not present in user input, try to infer it from the current branch name feature subdirectory items inside .reviews directory.
If the branch name is not a valid item of .reviews feature subdirectory, abort and ask the user to provide a valid run_id.

## Continuous Review Loop

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g. `'I'\''m Groot'` (or double-quote if possible: "I'm Groot").
   - Treat any non‑zero exit or unparsable output as a blocker; stop and resolve before proceeding.
   - Persist the resolved absolute `${FEATURE_DIR}` for all subsequent steps; do not recompute differently mid‑run. Honor any user-provided branch/scope constraints and document assumptions if inputs are ambiguous.
   - If the conversation history so far does not already capture detailed references to the underlying specification artifacts, proactively re-read `${FEATURE_DIR}/spec-overview-${RUN_ID}.md` also available at `/$FEATURE_DIR/spec-overview.md` and the source documents (`spec.md`, `plan.md`, `tasks.md`, contracts, research, data models) before advancing so you can interpret the traceability identifiers accurately during this phase.

2. Confirm `/speckit.review.init` completed and `review-spec-validate.sh` reported success. Reuse the same `RUN_ID` for every command.
   - If validation did not succeed, return to init and fix the specification; do not record findings against an invalid spec.
   - Never switch RUN_ID mid‑review. If a mistake is made, restart using the original RUN_ID.

3. Run `.specify/scripts/bash/review-status.sh --run_id 'RUN_ID' [--limit <n>]` to triage pending files and plan the next batch.
   - Keep batches focused and coherent; prefer smaller batches for complex or cross‑cutting changes. Expand batch scope up to full semantic scope coverage.

4. Inspect diffs before recording: `.specify/scripts/bash/review-file-inspect.sh --run_id 'RUN_ID' --path '<file1>' [--path '<file2>' ...]`.
   - Treat inspection as mandatory evidence gathering; record paths inspected to avoid omissions.

5. Inspect the files and their content to understand the changes and the context of the changes if necessary. Maintain `${FEATURE_DIR}/.reviews/${RUN_ID}/spec-overview.md` (or the copied `${FEATURE_DIR}/spec-overview-${RUN_ID}.md`) open at all times during this loop and consult it for every traceability decision. When `${FEATURE_DIR}/report.md` includes remediation summaries or `${FEATURE_DIR}/remediation/` contains supporting artifacts, incorporate that guidance while assessing each change. If prior conversation context did not summarize the relevant sections of the specification, pause here to study the full documents so every identifier you cite is backed by the original wording.
   - Before drilling into per-file behavior, validate that the current implementation architecture still matches the feature design reconstructed from the specification in `/speckit.review.init`. Compare boundaries, data flow, integration points, and life-cycle hooks against the plan. Examine architectural decisions introduced during development (new services, refactors, concurrency models, caching layers) and decide whether they reinforce or erode the mandated design.
   - Classify each architectural observation on a three-tier scale that maps directly to the severity field you will use in findings: **Benign (document as residual risk using severity Note/Low)**, **At-Risk (design flaw requiring remediation or explicit follow-up using severity Medium/High depending on blast radius)**, and **Merge-Blocking (structural violation requiring architectural redesign before merge using severity Critical)**. Capture the rationale and impacted requirements in your review notes and findings so the severity is auditable.
   - Read entire files when edits are non‑local or impact interfaces/public APIs. Follow dependencies to callers/callees to evaluate systemic effects.
   - Cross‑map each change to the relevant spec identifiers (SC/AC/FR/NFR/US/PH) using the spec overview as the index.
   - If remediation guidance conflicts with the current spec, flag the discrepancy as a finding; do not silently choose one over the other.

5a. Traceability Mapping and Ranking (change-scoped, deterministic).
   - Build the candidate set of FR/AC/NFR/US/PH that could apply to the change using entity/data alignment, operation alignment, scope alignment, and normative strength (MUST/SHOULD/MAY).
   - For each candidate, capture roles (`ViolationCriterion`, `RemediationConstraint`, `Informational`), the change-relative applicability rationale (specificity, proximity, normative strength), and the concrete evidence spans (repo path plus line ranges).
   - Assign a `disposition` for each candidate: `Violated` (the change currently breaks it), `Satisfied` (the change fulfils or preserves it), or `Observed` (traceable but not directly gated). Only `Violated` entries may be marked `selected_as_primary`. Do not collapse to a single weakest identifier unless it is truly the only applicable one. Document `omitted_with_reason` for any strong candidate you decide to drop.
   - Partition candidates into Primary (minimal set of `Violated` entries that explain the issue) and Secondary (constraints the remediation must satisfy, often `RemediationConstraint` roles). Compute coverage metrics: candidate_count, considered_count, threshold (default 0.8), status (`MeetsThreshold` vs `BelowThreshold`). If coverage falls below the threshold, either expand the mapping or document the shortfall explicitly before proceeding.

5b. Remediation Fit Check (change-scoped).
   - Ensure every Primary id is matched by at least one remediation step and that constraining Secondary ids are satisfied by explicit remediation actions.
   - Split or refine remediation steps when a single generic action would violate any constraining Secondary id. Document conflicts when constraints cannot be satisfied and flag them as findings.

6. Assemble a JSON payload that matches the File Review Batch JSON Schema below.
   - `file_description`: Concise description of the file’s long-term role in the project (what the file is for, independent of this diff).
   - `functional_summary`: Paragraph summarizing the behavioral impact of this batch of edits (why the change matters to users/system). Explicitly call out when the work maps to the supporting-changes or documentation-gap feature modules created during init. Embed coverage shorthand when helpful, but rely on structured fields for gating.
   - `change_description`: Array of atomic change notes, each ≥50 characters. Every entry must list all applicable traceability identifiers (FR/US/AC/etc.) touched by that change.
   - `trace_links`: Structured mapping of every considered identifier (Primary and Secondary) with roles, disposition (`Violated` vs `Satisfied` vs `Observed`), applicability rationale, and evidence. Include `selected_as_primary` true/false plus `omitted_with_reason` for any excluded strong candidate.
   - `coverage`: Quantitative coverage gate (`candidate_count`, `considered_count`, `threshold`, `status`). Default threshold is 0.8; failing to meet it requires explicit justification before proceeding.
   - `findings`: Array of issue objects (may be empty) using the evidence-first format. Each finding must declare `primary_ids`, optional `secondary_ids`, and a `remediation_map` detailing which remediation steps satisfy which identifiers.
   - Clean/positive confirmation is allowed: if no identifiers are `Violated`, `findings` may remain empty while `trace_links` still records the satisfied set. Explain the satisfaction evidence in `functional_summary` and/or `notes`.
   - `notes`: Optional free-form context (empty string allowed) for residual commentary or justification when coverage is below threshold. If the specification does not mandate documentation and the changeset contains no documentation updates, record the missing documentation here as an optional, non-blocking merge follow-up so it can be surfaced again in the final report.
   - Keep `file_description` stable across runs; reflect role changes in `functional_summary` and `change_description` explicitly.
   - **MANDATORY:** The payload is plain JSON. Do not insert comments, relaxed quoting, schema hints, or any custom syntax. Supply only schema-compliant JSON values so the validator can parse the object without special handling.

7. Record the batch with `.specify/scripts/bash/review-file-review.sh --run_id 'RUN_ID' --json '<payload>'` or supply `--file '<payload.json>'`.
   - Re-running for the same file overwrites prior data; use this intentionally to refine without duplication. Maintain determinism of identifiers.

8. Repeat the status → inspect → record cycle until every changed file is covered. Keep batches focused (default 3–5 related files; adapt 2–8 based on change size/complexity).
   - Continue looping autonomously; do not emit interim summaries or stop after each batch. Surface progress only when genuinely blocked or when the entire review loop is complete.
   - Do not finish while any status entry remains pending or any inspected path lacks a recorded batch.

## File Review Batch JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "File Review Batch Payload v2",
  "type": "object",
  "patternProperties": {
    "^.+$": {
      "type": "object",
      "required": [
        "file_description",
        "functional_summary",
        "change_description",
        "trace_links",
        "coverage",
        "findings"
      ],
      "properties": {
        "file_description": {
          "type": "string",
          "minLength": 25
        },
        "functional_summary": {
          "type": "string",
          "minLength": 50
        },
        "change_description": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "string",
            "minLength": 50
          }
        },
        "trace_links": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["id", "roles", "disposition", "applicability", "evidence"],
            "properties": {
              "id": { "type": "string", "minLength": 3 },
              "roles": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": true,
                "items": {
                  "type": "string",
                  "enum": ["ViolationCriterion", "RemediationConstraint", "Informational"]
                }
              },
              "disposition": {
                "type": "string",
                "enum": ["Violated", "Satisfied", "Observed"]
              },
              "applicability": {
                "type": "object",
                "required": ["score", "specificity", "normative_strength", "rationale"],
                "properties": {
                  "score": { "type": "number", "minimum": 0, "maximum": 1 },
                  "specificity": {
                    "type": "string",
                    "enum": ["Line", "Block", "Function", "Component", "System"]
                  },
                  "normative_strength": {
                    "type": "string",
                    "enum": ["MUST", "SHOULD", "MAY"]
                  },
                  "rationale": { "type": "string", "minLength": 25 }
                },
                "additionalProperties": false
              },
              "evidence": {
                "type": "array",
                "minItems": 1,
                "items": {
                  "type": "object",
                  "required": ["path", "lines"],
                  "properties": {
                    "path": { "type": "string", "minLength": 1 },
                    "lines": {
                      "type": "string",
                      "pattern": "^[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*$"
                    }
                  },
                  "additionalProperties": false
                }
              },
              "selected_as_primary": { "type": "boolean" },
              "omitted_with_reason": { "type": "string", "minLength": 25 }
            },
            "additionalProperties": false
          }
        },
        "coverage": {
          "type": "object",
          "required": ["candidate_count", "considered_count", "threshold", "status"],
          "properties": {
            "candidate_count": { "type": "integer", "minimum": 0 },
            "considered_count": { "type": "integer", "minimum": 0 },
            "threshold": { "type": "number", "minimum": 0, "maximum": 1 },
            "status": {
              "type": "string",
              "enum": ["MeetsThreshold", "BelowThreshold"]
            }
          },
          "additionalProperties": false
        },
        "findings": {
          "type": "array",
          "minItems": 0,
          "items": {
            "type": "object",
            "required": [
              "finding",
              "severity",
              "remediation",
              "primary_ids",
              "remediation_map"
            ],
            "properties": {
              "finding": { "type": "string", "minLength": 25 },
              "severity": {
                "type": "string",
                "enum": ["Critical", "High", "Medium", "Low", "Note"]
              },
              "remediation": { "type": "string", "minLength": 25 },
              "primary_ids": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": true,
                "items": { "type": "string", "minLength": 3 }
              },
              "secondary_ids": {
                "type": "array",
                "minItems": 0,
                "uniqueItems": true,
                "items": { "type": "string", "minLength": 3 }
              },
              "remediation_map": {
                "type": "array",
                "minItems": 1,
                "items": {
                  "type": "object",
                  "required": ["step", "satisfies"],
                  "properties": {
                    "step": { "type": "string", "minLength": 10 },
                    "satisfies": {
                      "type": "array",
                      "minItems": 1,
                      "uniqueItems": true,
                      "items": { "type": "string", "minLength": 3 }
                    }
                  },
                  "additionalProperties": false
                }
              }
            },
            "additionalProperties": false
          }
        },
        "notes": {
          "type": "string",
          "minLength": 0
        }
      },
      "additionalProperties": false
    }
  },
  "minProperties": 1,
  "additionalProperties": false
}
```

### Traceability Field Guidance
- Compute `trace_links[].applicability.score` using deterministic heuristics: start from specificity (Line=1.0, Block=0.9, Function=0.8, Component=0.6, System=0.4), add +0.10 for exact entity/field alignment, +0.05 for aggregate/module alignment, and add +0.15 / +0.07 / +0.00 for normative strengths MUST/SHOULD/MAY respectively. Clip to the `[0,1]` range and describe the rationale in `applicability.rationale`.
- Assign `disposition` explicitly: `Violated` means the change fails the requirement (must have findings); `Satisfied` means the change enforces/fulfils it; `Observed` captures contextual references. Only `Violated` links may set `selected_as_primary`.
- Mark `selected_as_primary` on the minimal set of `Violated` links that jointly explains the issue. Use Secondary entries (typically `RemediationConstraint`) to shape the fix; provide `omitted_with_reason` whenever a strong candidate is excluded.
- Populate `coverage` with `threshold` defaulting to `0.8`. Set `status` to `MeetsThreshold` only when `considered_count / max(candidate_count, 1) ≥ threshold`; otherwise mark `BelowThreshold` and justify in `notes`.
- Ensure each finding’s `primary_ids` appears in at least one `remediation_map[].satisfies`. Include constraining Secondary ids that influence remediation steps; if a Secondary id cannot be satisfied, document the conflict and risk explicitly in `remediation_map` or `notes`.
- Treat `remediation_map` as the authoritative many-to-many mapping. Split remediation into multiple steps when needed so that every Primary and constraining Secondary id is satisfied by at least one step.

## Review Discipline
- Use `--file` when editing large payloads and keep every identifier deterministic across reruns.
- Abort the batch if `trace_links` omits Primary identifiers or if `coverage.status` is `BelowThreshold` without a documented justification in `notes`.
- Treat applicability and precedence as change-scoped: Primary and Secondary sets are determined per change, not globally. Never collapse to a single weakest identifier when stronger ones apply.
- Every remediation must declare a many-to-many mapping to traceability ids via `remediation_map`; generic remediations with no explicit trace linkage are non-compliant.
- `findings` may be empty but must remain present; add `notes` only when additional commentary is essential.
- Re-running `review-file-review.sh` with the same file overwrites prior data - leverage this to refine findings without duplication.
- Keep `file_description` stable across runs; if the file’s role changes fundamentally, call that out in `functional_summary` and the corresponding change entries.
- Use `functional_summary` for the overall behavioral narrative and `change_description` for enumerating discrete edits (guard clauses added, helper extracted, contract updated, etc.).
- Never skip diff inspection. `review-status.sh` flags missing inspections; clear those before finishing.
- Never rely on the output of `review-file-inspect.sh` alone:
  - Always use tools designed to explore the codebase for tracking of dependencies and public interfaces.
  - Expand the search space until all dependency trajectories are covered and all specification items are mapped. Use the spec overview file to guide the search.
  - Full coverage of user stories verified based on evidence in the codebase.
  - Read entire files to fully cover the semantic scope of non-isolated changes with  non-local impact.
  - Each change must be validated against the specification requirements and acceptance criteria. Every deviation from the specification must be documented as a finding.
  - Always fully understand the changes in the global context of the codebase. Follow dependencies and public interfaces.
- Never skip or ignore essential mandatory checks throughout the changeset:
  - Check for contradictions and conflicts between single changes.
- Check for side-effects of the changes and the impact on the other parts of the codebase.
  - Check for problematic code, patterns, and assumptions. Question the design choices and the rationale behind the changes. Treat unclear or conflicting syntactic, structural, architectural and behavioral elements as potential findings and investigate further.
- Check for potential regressions and new risks introduced by the changes.
- Check for potential tests that could be added or extended.
- Check for potential documentation that could be added.
- Always use the specification identifiers for the traceability of the findings and change descriptions. Each change entry should cite every requirement/user story/criterion/module it affects.
- Always include the full set of traceability identifiers for findings, declaring disposition (`Violated`/`Satisfied`/`Observed`) and Primary vs Secondary explicitly. Validate that every `Violated` Primary id is satisfied by at least one remediation step while satisfied traces are explained in the narrative.
- Once the pending list reaches zero, transition directly to `/speckit.review.finish` while preserving the original `RUN_ID`.

## Professional Review Enhancements (Evidence, Heuristics, Severity)

### Compose Evidence-First Findings
Embed concrete metadata inside the `finding` and/or `remediation` strings to preserve structure while enriching signal:
- Include: Category, Location(s), Traceability, Evidence, and Required-Before-Merge.
- Deterministic pattern:
  - Finding: "Category=Security; Location=path/to/file:123-140; Traceability=SC-012, US-004; Summary=Input used in SQL without parameterization; Evidence=see lines 125–130"
  - Severity: "Critical" | "High" | "Medium" | "Low" | "Note"
  - Remediation: "Steps=Use prepared statements with named bindings; Tests=Add negative test rejecting \"' OR 1=1 --\"; Policy=Required-Before-Merge=Yes"

Recommended categories: Correctness, Architecture, Security, Performance, Tests, Readability, Duplication, Coverage, Consistency, Docs.

### Targeted Detection Passes (run before recording)
- Duplication: Near-duplicate logic or requirements; propose Extract Method/Class/Interface with file:line references.
- Ambiguity: Vague, non-measurable terms (“fast”, “simple”); propose measurable acceptance criteria.
- Underspecification: Verbs without outcomes; tasks with no matching requirement or tests.
- Principles/Constitution: Boundary violations, architecture leaks, or conflicting rules - mark Critical.
- Inconsistencies: Terminology drift, entities in plan missing in spec, contradictory task ordering.

### Deep Technical Review Heuristics
- Correctness: Guard inputs (preconditions), verify outcomes (postconditions), maintain invariants; enumerate edge cases (null/empty, min/max, timeouts, locale, error paths).
- Architecture: Respect layering and boundaries; avoid circular deps; keep public APIs small; avoid speculative abstractions.
- Readability: Intention-revealing names; minimize nesting; “why” comments; remove dead code.
- Testing: Prefer behavior assertions over mere coverage; include negative paths; at least one integration test for changed interfaces.
- Performance: Watch for N+1 queries, blocking I/O in hot paths, unnecessary copies; ask for one quantitative metric for suspected hotspots.
- Security (OWASP-aligned): Validate/encode IO, authn/z with least privilege, secrets in vaults, CSRF/anti-replay as relevant, parameterize SQL.

### Practical Thresholds
- Cyclomatic complexity: Flag functions with complexity >10 or equivalent deep nesting; request Extract Method or guard clauses.
- Rule of three: Introduce abstractions only after ≥3 concrete duplications.
- Approval standard: Approve when code health improves and blockers are resolved; otherwise request changes with explicit, verifiable steps.

### Traceability Guidance
- Reference stable slugs from the imported spec (e.g., SC-001/AC-001, FR-001, NFR-001, US-003; module IDs like AUTH-SVC are reviewer-defined and not stable) within each `finding` string.
- Where applicable, include test IDs or names to prove the gap or the fix (e.g., “Tests=T-089”).

### Example Finding Phrases
- Blocking: “Requesting changes: input is used in SQL without parameterization; use prepared statements and add a negative test showing injection is rejected.”
- Actionable: “Extract the 18-line branch into validateSession() so the caller reads ‘authenticate → validate → respond’; add unit tests for the helper.”
- Nit: “Nit: consider userId to match domain terms; non-blocking.”
