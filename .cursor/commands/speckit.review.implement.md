---
description: Implement remediation work for findings captured in the finalized review report.
---

## User Input

```text
$ARGUMENTS
```

You MUST consider the user input before proceeding (if not empty).#

## Run ID Inference

If run_id is not present in conversation history, try to infer it from user input.
If run_id is not present in user input, try to infer it from the current branch name feature subdirectory items inside .reviews directory.
If the branch name is not a valid item of .reviews feature subdirectory, abort and ask the user to provide a valid run_id.

## Focused Remediation Workflow

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root to resolve `FEATURE_DIR` and artifact availability. All paths must be absolute; escape quotes exactly as in `/speckit.implement`.
   - Treat any non-zero exit or unparsable output as a blocker; stop and resolve before continuing.
   - Persist the resolved absolute `${FEATURE_DIR}` for all subsequent steps and respect user-provided scope constraints; do not recompute mid-run.
   - If the conversation to this point does not already document detailed references to the specification artifacts, immediately revisit `${FEATURE_DIR}/spec-overview-${RUN_ID}.md` and re-open the authoritative documents (`spec.md`, `plan.md`, `tasks.md`, contracts, research) so each remediation is grounded in the exact requirement wording.
2. Verify `${FEATURE_DIR}/report.md` (Markdown) and `${FEATURE_DIR}/report.pdf` exist. If either is missing, halt and rerun `/speckit.review.finish` to publish the artifacts before attempting remediation.
3. Decide whether to run the checklist completeness audit:
   - If this chat has already executed `/speckit.review.implement` for the same `${FEATURE_DIR}` or the user explicitly instructed you to skip checklist validation, bypass this step immediately and continue with the next step without pausing for confirmation.
   - Otherwise, open `${FEATURE_DIR}/checklists/requirements.md` and any other checklists in `${FEATURE_DIR}/checklists/` to confirm mandatory items are marked complete. Record outstanding gaps in your remediation notes or escalate if they block remediation activities.
4. Read the canonical spec documents in `${FEATURE_DIR}`: `spec.md`, `plan.md`, `tasks.md`, supporting research, plus the published `report.md`. Extract every unresolved finding (focus on severity Critical/High/Medium first) along with referenced requirement/user-story slugs. Pay special attention to the architectural assessment recorded in the report—identify which items were marked Benign (document-only), At-Risk (requires planned remediation), or Merge-Blocking (structural redesign demanded before merge).
5. Build a remediation checklist:
   - Group findings by impacted file/module.
   - Note requirement IDs, expected behavior, and acceptance tests that must be satisfied after the fix.
   - Record whether new or updated automated tests are required.
6. For each checklist item, execute targeted fixes:
   - Inspect the referenced code paths and confirm the existing behavior vs. the review expectation.
   - Implement the minimal change that resolves the finding while preserving architectural principles outlined in `plan.md`. Address Merge-Blocking architectural flaws first (these map to Critical severity), then work through At-Risk architectural issues (Medium/High severity) before tackling Benign notes.
   - Update or add tests proving the remediation. Prefer deterministic unit/integration coverage over manual validation.
   - Store any supplemental evidence (patch plans, logs, screenshots) inside `${FEATURE_DIR}/remediation/` and reference the filenames in your summary. Creating these artifacts is optional; skip when not needed.
7. After each fix (or logical batch of related fixes), run the relevant automated test suites and linting commands. Do not proceed while failures remain.
8. Once all findings are addressed, perform a final verification pass:
   - Re-read the affected sections of `report.md` to ensure each Critical/High/Medium item has an implemented resolution.
   - Document any residual Low/Note follow-ups in `tasks.md` or the project tracker as instructed by the spec.
   - Capture the concise summary of code changes and updated tests inside your remediation notes or the `## Remediation Summary` section from step 9 rather than emitting it as conversational output.
9. Append a remediation summary to `${FEATURE_DIR}/report.md` (vehicle for re-reviewers):
   - Add or update a section titled `## Remediation Summary – <YYYY-MM-DD> #<N>` near the end of the document, where `<N>` is a zero-padded daily counter starting at 01 for the first summary added on a given date (e.g., `## Remediation Summary – 2025-11-11 #01`).
   - Start the section with a brief slug snapshot (e.g., "Spec Snapshot: SC-101, SC-205, US-014, FR-003") copied from the overview file recorded in the `Spec Snapshot File` row (`{{MANUAL_SPEC_SNAPSHOT}}`). If that row is empty, fill it first with the correct overview filename (for example, `spec-overview-${RUN_ID}.md`).
   - List resolved findings, linked requirement/user-story slugs, tests executed, and references to any artifacts under `${FEATURE_DIR}/remediation/`.
   - Never delete earlier remediation sections; maintain chronological history. If rerunning the same remediation cycle on the same date, increment `<N>` and append a new section rather than editing prior entries unless you are correcting typos.

## Guardrails
- Work only within the files required to satisfy the documented findings; avoid opportunistic refactors unless they unblock the remediation.
- Maintain deterministic behavior - do not introduce randomness or environment-specific logic.
- Preserve encryption, review artifacts, and audit logs; never edit files under `${FEATURE_DIR}/.reviews/` directly.
- Treat the appended remediation summary in `${FEATURE_DIR}/report.md` as the canonical hand-off to the next reviewer; keep references stable and descriptive. If new imports generate different requirement slugs, state the mapping (old → new) in the summary so reviewers can reconcile history.
- If the remediation uncovers contradictions in the original specification, pause and escalate before merging changes.
