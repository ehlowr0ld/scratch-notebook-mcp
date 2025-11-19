---
description: Synthesize the streamlined review report and complete manual sections.
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

## Finalization Checklist

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and capture `FEATURE_DIR` plus the AVAILABLE_DOCS list. Preserve absolute paths; use the same quoting guidance as in `/speckit.review.init`.
   - Treat any non-zero exit or unparsable output as a blocker; stop and resolve before continuing.
   - Persist the resolved absolute `${FEATURE_DIR}` for all remaining steps; do not recompute mid-run. Honor user-input scope constraints and document any assumptions.
   - If the conversation history does not already reflect detailed references to the specification documents, revisit `${FEATURE_DIR}/spec-overview-${RUN_ID}.md` and reopen the underlying spec artifacts (`spec.md`, `plan.md`, `tasks.md`, contracts, research, etc.) now so the manual sections you complete later reflect the true wording of each traceability item.
2. Run `.specify/scripts/bash/review-status.sh --run_id 'RUN_ID'` to confirm current progress. If the pending list is non-empty, decide whether to finish the review loop or proceed with a partial report using `--force` (the report will include a warning and outstanding file list).
3. Execute `.specify/scripts/bash/review-report-synthesize.sh --run_id 'RUN_ID' [--layout vertical|tabular] [--force]` to rewrite the report with the latest data.
4. Immediately open `report.md` and replace every `{{MANUAL_*}}` placeholder (including `{{MANUAL_SPEC_SNAPSHOT}}`) with your own narrative before any copying or PDF generation.
5. If you need to rerun the synthesizer after making manual edits, rerun it after updating file reviews and be prepared to reapply manual content.
6. Before producing new artifacts, check whether `${FEATURE_DIR}/report.md` already exists. If it does, extract every `## Remediation Summary – <date> #<N>` section (including lists/tables) and append them to `${FEATURE_DIR}/.reviews/${RUN_ID}/report.md` so the history remains intact. Add a new dated section only after the previous ones; never drop earlier summaries.
7. When the consolidated report text is final, run `${FEATURE_DIR}/.reviews/${RUN_ID}/report-to-pdf.sh` to generate the PDF artifact (requires `pandoc` and `wkhtmltopdf` in PATH). Re-run this helper whenever you refresh the report.
8. Copy `${FEATURE_DIR}/.reviews/${RUN_ID}/report.md` and `${FEATURE_DIR}/.reviews/${RUN_ID}/report.pdf` into `${FEATURE_DIR}/` so the canonical spec folder holds the finalized review artifacts alongside `spec.md`, `plan.md`, and related documents. Overwrite existing files if you regenerate the report.
   - **MANDATORY:** `report.md` is ordinary Markdown. Do not embed custom delimiters, templating syntax beyond the documented placeholders, or any proprietary mark-up. Write standard Markdown so downstream tooling and reviewers can read it without special rendering logic.

## Additional Guidance
- Choose the layout that best fits the evidence set; `vertical` favors per-file property tables, while `tabular` summarizes multiple files side-by-side.
- When the specification omitted documentation requirements and no documentation assets were touched in the review, record the missing documentation as an optional, non-blocking follow-up in the final report: add it to `{{MANUAL_FOLLOWUPS}}` and flag it in `{{MANUAL_RISK_COMMENTARY}}` so the gap is visible without blocking merge.
- Preserve any existing `## Remediation Summary` sections in `${FEATURE_DIR}/report.md`; new appendices must extend, not replace, prior remediation history. Store supporting evidence under `${FEATURE_DIR}/remediation/` and reference it from the report when applicable.
- Keep `${FEATURE_DIR}/spec-overview-${RUN_ID}.md` in addition to prior snapshots (e.g., `spec-overview-review-20251108-main-001.md`) so reviewers can trace requirement slugs without re-importing the ledger. Make sure the filename you recorded in `{{MANUAL_SPEC_SNAPSHOT}}` matches this newly copied snapshot.
- Do not modify or inspect the automation plumbing - interact only through the published scripts.
- Retain all script outputs for auditability and submit the completed `report.md` alongside any exported PDF.
- Carry forward the architectural assessment from `/speckit.review.record`: document which architectural decisions remained compliant (Benign), which are At-Risk and require follow-up, and which are Merge-Blocking. Use the Note/Low → Medium/High → Critical severity ladder consistently between findings, risk commentary, and the final verdict.

## Professional Finalization Enhancements (Manual Sections & Verdict)

Fill the following MANUAL sections in `report.md` with concise, actionable content grounded in recorded evidence:

- Spec Snapshot File (`{{MANUAL_SPEC_SNAPSHOT}}`):
  - Record the exact filename or identifier of the spec overview snapshot that matches the current report (e.g., `spec-overview-review-20251111-main-002.md`).
  - If you created a new snapshot for this run, ensure the file resides in the feature directory so future remediation work references the correct slug set.
- Executive Summary (`{{MANUAL_EXEC_SUMMARY}}`):
  - State scope, key changes reviewed, topline severity counts, and high-risk areas.
  - Declare whether the change improves overall code health, explicitly stating the architectural verdict (Benign / At-Risk / Merge-Blocking) and the evidence that led to it.
- Severity Policy and Gates (`{{MANUAL_SEVERITY_POLICY}}`):
  - Document the severity rubric and merge gates.
  - Include outcomes for each level (Critical blocks, High usually blocks, Medium requires risk acceptance, Low/Note optional).
- Traceability Coverage Matrix (`{{MANUAL_TRACEABILITY}}`):
  - Build a table with columns: `Requirement`, `Implementation Files`, `Tests Exercised`, `Implementation Status`, `Test Status`, and optionally `Notes`.
  - For each requirement slug, list the concrete files/lines touched and relevant automated tests. Use `Yes` / `No` (optionally `No – reason`) in the status columns so the answer to “Is this implemented?” and “Is this covered by automated tests?” is unambiguous. Ensure the traceability IDs listed here match the complete set referenced in the file review records.
  - Close the section with a coverage summary in the form `Coverage summary: <implemented>/<total> requirements implemented; <tested>/<total> requirements covered by automated tests.`
  - Flag tasks touching files with no linked requirement/tests and propose linkage, removal, or deferral.
- Merge Verdict (`{{MANUAL_VERDICT}}`):
  - Approve or Request Changes with rationale tied to severity counts and gates.
  - If approving with follow-ups, list tracked items and owners, and reconcile the architectural severity classification (any Merge-Blocking architectural flaw must result in Request Changes).
- Risk Commentary (`{{MANUAL_RISK_COMMENTARY}}`):
  - Call out residual risks (performance hotspots, security assumptions, flaky tests) and expected mitigations. Highlight all At-Risk architectural decisions, the rationale behind their classification, and the planned remediation path.
  - When documentation is missing (spec omitted documentation deliverables and no docs were created), explicitly list it here as a non-blocking risk with the plan to address it.
- Follow-up Actions (`{{MANUAL_FOLLOWUPS}}`):
  - Provide next steps and owners; include suggested commands or references for remediation patches when helpful.
  - Mirror any optional documentation action item here so the merge checklist captures it.
- Review Method & Checklist (`{{MANUAL_METHOD}}`):
  - Summarize detection passes executed (duplication, ambiguity, underspecification, principles, inconsistency) and deep-review axes (correctness, architecture, readability, tests, performance, security).
- Additional Notes (`{{MANUAL_ADDITIONAL_NOTES}}`):
  - Capture context that does not fit other sections (communication with authors, environment gotchas, etc.).
