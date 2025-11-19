---
description: Execute the implementation plan by processing and executing all tasks defined in tasks.md
---

## User Input

```text
$ARGUMENTS
```

You MUST consider the user input before proceeding (if not empty).

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. Check checklists status (if FEATURE_DIR/checklists/ exists):
   - Skip gate: If this chat session has already executed `/speckit.implement` for the same `${FEATURE_DIR}` **or** the user explicitly instructs you to skip checklist validation, bypass this entire step immediately and continue with step 3 without emitting any prompts or summaries about checklist status.
   - Scan all checklist files in the checklists/ directory
   - For each checklist, count:
     - Total items: All lines matching `- [ ]` or `- [X]` or `- [x]`
     - Completed items: Lines matching `- [X]` or `- [x]`
     - Incomplete items: Lines matching `- [ ]`

   - Are there any post-implementation checklist items that can only be completed after implementation is complete?
     - If yes, ingore these items for now, if no other incomplete pre-implementation items, proceed directly to step 3 without asking for user confirmation and without further status reporting.
     - Remember to process those items after implementation is complete.

   - Create a status table:

     ```text
     | Checklist | Total | Completed | Incomplete | Status |
     |-----------|-------|-----------|------------|--------|
     | ux.md     | 12    | 12        | 0          | ✓ PASS |
     | test.md   | 8     | 5         | 3          | ✗ FAIL |
     | security.md | 6   | 6         | 0          | ✓ PASS |
     ```

   - Calculate overall status:
     - PASS: All checklists have 0 incomplete items
     - FAIL: One or more checklists have incomplete items

   - If any pre-implementation checklist items are incomplete:
     - Display the table with incomplete item counts
     - STOP and ask: "Some checklists are incomplete. Do you want to proceed with implementation anyway? (yes/no)"
     - Wait for user response before continuing
     - If user says "no" or "wait" or "stop", halt execution
     - If user says "yes" or "proceed" or "continue", proceed to step 3

   - If all checklists are complete:
     - Display the table showing all checklists passed
     - Automatically proceed to step 3

3. Load and analyze the implementation context:
   - REQUIRED: Read tasks.md for the complete task list and execution plan
   - REQUIRED: Read plan.md for tech stack, architecture, and file structure
   - IF EXISTS: Read data-model.md for entities and relationships
   - IF EXISTS: Read contracts/ for API specifications and test requirements
   - IF EXISTS: Read research.md for technical decisions and constraints
   - IF EXISTS: Read quickstart.md for integration scenarios

4. Initialize and maintain an implementation log:
   - Create `${FEATURE_DIR}/implementation.md` if it does not exist and seed it with the RUN_ID, branch, and current UTC timestamp so later readers can trace the context.
   - After every checklist gate, setup checkpoint, phase completion, or substantial development step, append a dated entry capturing which tasks ran, which files/tests changed, and any requirement/user-story slugs addressed. This file is the authoritative running log of intermediate progress.
   - Use the log to capture remediation details for blockers before requesting help; each entry should include the failing command, diagnostics gathered, and hypotheses so the context is preserved.
   - Intermediate conversational summaries are unnecessary—maintain the chronology inside `implementation.md` and reference it when producing the final summary or blocker description.
   - The log will supply the material for the synthesized final summary or hard-block report in step 10.

5. Project Setup Verification:
   - REQUIRED: Create/verify ignore files based on actual project setup:

   Detection & Creation Logic:
   - Check if the following command succeeds to determine if the repository is a git repo (create/verify .gitignore if so):

     ```sh
     git rev-parse --git-dir 2>/dev/null
     ```

   - The following section is only to be processed after the user has given an explicit intruction to do so. If the user has already stated to skip ignore files, continue directly to step 6. Otherwise ask the user if they want to create/verify ignore files now.
     - If user says "yes" or otherwise explicitly agrees to create/verify ignore files, proceed to create/verify ignore files
     - If user says "stop" or otherwise signals to abort the execution, halt execution
     - If user says "no", "proceed", "continue", "skip" or "skip this step" or otherwise signals he wants to skip this and go directly into implementation, proceed to step 6

     - ignore files to process in case user agrees to create/verify ignore files:
         - Check if Dockerfile* exists or Docker in plan.md → create/verify .dockerignore
         - Check if .eslintrc* or eslint.config.* exists → create/verify .eslintignore
         - Check if .prettierrc* exists → create/verify .prettierignore
         - Check if .npmrc or package.json exists → create/verify .npmignore (if publishing)
         - Check if terraform files (*.tf) exist → create/verify .terraformignore
         - Check if .helmignore needed (helm charts present) → create/verify .helmignore

         If ignore file already exists: Verify it contains essential patterns, append missing critical patterns only
         If ignore file missing: Create with full pattern set for detected technology:

           Common Patterns by Technology (from plan.md tech stack):
            - Node.js/JavaScript/TypeScript: `node_modules/`, `dist/`, `build/`, `*.log`, `.env*`
            - Python: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`
            - Java: `target/`, `*.class`, `*.jar`, `.gradle/`, `build/`
            - C#/.NET: `bin/`, `obj/`, `*.user`, `*.suo`, `packages/`
            - Go: `*.exe`, `*.test`, `vendor/`, `*.out`
            - Ruby: `.bundle/`, `log/`, `tmp/`, `*.gem`, `vendor/bundle/`
            - PHP: `vendor/`, `*.log`, `*.cache`, `.env`
            - Rust: `target/`, `debug/`, `release/`, `*.rs.bk`, `*.rlib`, `*.prof*`, `.idea/`, `*.log`, `.env*`
            - Kotlin: `build/`, `out/`, `.gradle/`, `.idea/`, `*.class`, `*.jar`, `*.iml`, `*.log`, `.env*`
            - C++: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.so`, `*.a`, `*.exe`, `*.dll`, `.idea/`, `*.log`, `.env*`
            - C: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.a`, `*.so`, `*.exe`, `Makefile`, `config.log`, `.idea/`, `*.log`, `.env*`
            - Swift: `.build/`, `DerivedData/`, `*.swiftpm/`, `Packages/`
            - R: `.Rproj.user/`, `.Rhistory`, `.RData`, `.Ruserdata`, `*.Rproj`, `packrat/`, `renv/`
            - Universal: `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.swp`, `.vscode/`, `.idea/`

            Tool-Specific Patterns:
            - Docker: `node_modules/`, `.git/`, `Dockerfile*`, `.dockerignore`, `*.log*`, `.env*`, `coverage/`
            - ESLint: `node_modules/`, `dist/`, `build/`, `coverage/`, `*.min.js`
            - Prettier: `node_modules/`, `dist/`, `build/`, `coverage/`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
            - Terraform: `.terraform/`, `*.tfstate*`, `*.tfvars`, `.terraform.lock.hcl`
            - Kubernetes/k8s: `*.secret.yaml`, `secrets/`, `.kube/`, `kubeconfig*`, `*.key`, `*.crt`

6. Parse tasks.md structure and extract:
   - Task phases: Setup, Tests, Core, Integration, Polish
   - Task dependencies: Sequential vs parallel execution rules
   - Task details: ID, description, file paths, parallel markers [P]
   - Execution flow: Order and dependency requirements

7. Execute implementation following the task plan:
   - Phase-by-phase execution: Complete each phase before moving to the next
   - Respect dependencies: Run sequential tasks in order, parallel tasks [P] can run together
   - Follow TDD approach: Execute test tasks before their corresponding implementation tasks
   - File-based coordination: Tasks affecting the same files must run sequentially
   - Validation checkpoints: Verify each phase completion before proceeding

8. Implementation execution rules:
   - Setup first: Initialize project structure, dependencies, configuration
   - Tests before code: If you need to write tests for contracts, entities, and integration scenarios
   - Core development: Implement models, services, CLI commands, endpoints
   - Integration work: Database connections, middleware, logging, external services
   - Polish and validation: Unit tests, performance optimization, documentation

9. Progress tracking and error handling:
   - Persist progress privately by appending each completed checkpoint to `${FEATURE_DIR}/implementation.md`; do **not** emit conversational summaries after individual tasks. Surface status only when a hard block occurs or when step 10’s final summary is ready.
   - Halt execution if any non-parallel task fails; capture diagnostics and hypotheses in `implementation.md` before requesting help.
   - For parallel tasks [P], continue with successful tasks, log the failed ones in `implementation.md`, and report the blockage only if remediation requires user input.
   - Provide clear error messages with context for debugging **inside** the log; when escalation is necessary, reference the relevant log entries instead of restating the entire history.
   - Suggest next steps only when implementation cannot proceed autonomously.
   - IMPORTANT For completed tasks, mark them as `[X]` inside `tasks.md` using the appropriate editing tool; keep the ledger synchronized with actual progress.
   - EXEMPTION FROM THE PERSISTENCE AND AUTONOMOUS EXECUTION RULES ABOVE: When a big chunk of work is finished and it is advisable to check back with the user. For example on an Critical Phase's boundary or at a pivotal point of the entire spec implementation, you can emit a well designed summary of the work done, lay out the next steps and ask for feedback if needed.

10. Completion validation:
   - Verify all required tasks are completed
   - Check that implemented features match the original specification
   - Validate that tests pass and coverage meets requirements
   - Confirm the implementation follows the technical plan
   - Use `${FEATURE_DIR}/implementation.md` to synthesize a single final summary covering the entire implementation pass (or, if a hard block prevented completion, to describe the blocker with full context) and share only that consolidated status with the user.

Note: This command assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, suggest running `/speckit.tasks` first to regenerate the task list.
