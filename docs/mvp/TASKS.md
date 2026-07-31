# STL Analyzer MVP Tasks

## 1. Purpose

This document breaks the MVP into implementation tasks ordered by dependency. It is intended to be executable by an agentic coding tool without expanding scope beyond [`PRD.md`](PRD.md).

Task states:

- `[ ]` Not started
- `[-]` In progress
- `[x]` Complete
- `[!]` Blocked

A task is complete only when its implementation, tests, and relevant documentation are finished.

## 2. Delivery strategy

Implement the MVP in vertical slices:

1. Bootstrap the Python package and quality tooling.
2. Establish domain models, filesystem safety, and JSON contracts.
3. Implement workspace initialization.
4. Implement configuration, diagnostics, and case discovery.
5. Add Blender subprocess integration and geometry inspection.
6. Add deterministic rendering and iteration persistence.
7. Add reviews, adjustments, state transitions, and resumability.
8. Add finalization and generated agent instructions.
9. Complete end-to-end validation and documentation alignment.

Do not implement embedded AI, cloud services, multi-STL cases, or geometry editing.

---

# Phase 0 — Repository and project foundation

## MVP-0001 — Initialize the Python project

- [x] Create a `uv`-managed Python project targeting Python 3.12+.
- [x] Add the `src/stl_analyzer/` package layout.
- [x] Add `stl_analyzer.__main__`.
- [x] Define the `stl-analyzer` console script in `pyproject.toml`.
- [x] Generate and commit `uv.lock`.
- [x] Ensure `uv run stl-analyzer --help` succeeds.

**Acceptance criteria**

- A clean clone can run `uv sync` successfully.
- `uv run stl-analyzer --help` returns exit code `0`.
- Package metadata uses the repository name and a pre-1.0 MVP version.

## MVP-0002 — Add runtime dependencies

- [x] Add Typer.
- [x] Add Pydantic v2.
- [x] Add Rich.
- [x] Add a TOML parser only if the supported Python version requires one beyond the standard library.
- [x] Avoid adding `bpy` to the host environment.

**Acceptance criteria**

- Dependencies are minimal and justified.
- Blender remains an external runtime dependency.

## MVP-0003 — Add development quality tooling

- [x] Add pytest and coverage support.
- [x] Add Ruff configuration for formatting and linting.
- [x] Add mypy configuration.
- [x] Add test, lint, format-check, and type-check commands to developer documentation.
- [x] Configure deterministic test paths and temporary directories.

**Acceptance criteria**

- `uv run pytest` succeeds with the initial test scaffold.
- `uv run ruff check .` succeeds.
- `uv run ruff format --check .` succeeds.
- `uv run mypy src` succeeds.

## MVP-0004 — Define package architecture

- [x] Create initial modules for CLI, domain models, services, filesystem, Blender integration, and templates.
- [x] Keep Typer command functions thin.
- [x] Separate domain logic from terminal rendering.
- [x] Prevent Blender-specific imports from loading in normal host Python execution.

**Suggested layout**

```text
src/stl_analyzer/
├── __init__.py
├── __main__.py
├── cli.py
├── commands/
├── models/
├── services/
├── filesystem/
├── blender/
├── output/
└── templates/
```

**Acceptance criteria**

- Modules have clear responsibilities.
- Core services can be tested without invoking Typer or Blender.

---

# Phase 1 — Shared contracts and safety foundations

## MVP-0101 — Define common JSON result envelopes

- [x] Define success and error response models.
- [x] Define stable structured error fields: code, message, details, recoverable, and suggested action.
- [x] Implement one JSON serialization path shared by all commands.
- [x] Ensure JSON mode writes exactly one JSON document to stdout.
- [x] Ensure diagnostics do not leak into stdout in JSON mode.

**Acceptance criteria**

- Expected errors never require parsing Rich output.
- Unit tests verify stdout and stderr separation.
- Unknown internal exceptions map to a stable internal-error envelope.

## MVP-0102 — Define process exit codes

- [x] Implement the exit-code classes from the PRD.
- [x] Map domain errors to process exit codes in one location.
- [x] Document stable domain error codes separately from process codes.

**Acceptance criteria**

- CLI commands return consistent process codes.
- Tests cover at least one error in every exit-code class.

## MVP-0103 — Implement safe path primitives

- [x] Normalize absolute and relative paths.
- [x] Implement workspace-contained path resolution.
- [x] Reject `..` traversal outside approved roots.
- [x] Define safe handling of symlinks and junctions on Windows.
- [x] Implement safe case-ID resolution as a direct child of the STL root.
- [x] Implement atomic text and JSON writes where practical.

**Acceptance criteria**

- Paths cannot escape workspace, case, or assets roots.
- Tests cover traversal, absolute injection, symlink escape where supported, and Windows-style paths.

## MVP-0104 — Define schema versioning

- [x] Add schema-version fields to configuration-derived generated documents.
- [x] Define constants for current schema versions.
- [x] Reject unsupported future schema versions clearly.
- [x] Leave migration implementation out of scope unless needed for MVP fixtures.

**Acceptance criteria**

- Every durable generated JSON document has an explicit schema version.

## MVP-0105 — Define clock, IDs, and hashing services

- [x] Implement injectable UTC clock service.
- [x] Implement filesystem-safe sortable session IDs.
- [x] Implement SHA-256 hashing for source STL files and manifests.
- [x] Make IDs and timestamps deterministic in tests.

**Acceptance criteria**

- Session and iteration tests do not depend on real time.
- Source hash changes are detectable.

---

# Phase 2 — Workspace initialization

## MVP-0201 — Define built-in workspace templates

- [x] Create a versioned default `stl-analyzer.toml` template.
- [x] Create the canonical `SKILL.md` template.
- [x] Create managed-block templates for `AGENTS.md`.
- [x] Create managed-block templates for `CLAUDE.md`.
- [x] Create managed-block templates for `.gitignore`.
- [x] Store templates as package resources.

**Acceptance criteria**

- Installed distributions can load all templates without repository-relative paths.
- Templates contain no machine-specific absolute paths.

## MVP-0202 — Implement managed-block merging

- [x] Define stable begin/end markers per managed file.
- [x] Insert blocks into absent files.
- [x] Append blocks to existing unmanaged files while preserving content.
- [x] Replace existing managed blocks without duplicating them.
- [x] Preserve newline style where reasonable.
- [x] Detect malformed or duplicate managed markers as conflicts.

**Acceptance criteria**

- Rerunning merge produces byte-equivalent output.
- Existing unmanaged content remains unchanged.
- Tests cover empty files, existing content, existing blocks, and malformed markers.

## MVP-0203 — Implement init preflight planner

- [x] Resolve omitted path to the current directory.
- [x] Resolve `.`, relative paths, and absolute paths.
- [x] Detect a target that is an existing file.
- [x] Inspect all target paths before writing.
- [x] Classify actions as create, update, unchanged, or conflict.
- [x] Treat unmanaged `SKILL.md` as a hard conflict.
- [x] Treat invalid or unmanaged `stl-analyzer.toml` as a hard conflict.
- [x] Preserve existing `stl/` contents.
- [x] Verify required parent write permissions as far as practical.

**Acceptance criteria**

- No filesystem mutation occurs during planning.
- A complete action plan is available for human and JSON output.

## MVP-0204 — Implement transactional init commit

- [x] Create a missing target directory.
- [x] Write planned files through temporary files and atomic replacement where possible.
- [x] Create the STL root and `.gitkeep`.
- [x] Attempt rollback when a commit-stage operation fails.
- [x] Report uncertain paths after incomplete rollback.
- [x] Never remove existing user content.

**Acceptance criteria**

- Preflight conflicts leave the target unchanged.
- Repeated initialization succeeds and reports unchanged files.
- Failure-injection tests verify rollback behavior.

## MVP-0205 — Implement `stl-analyzer init [PATH]`

- [x] Add Typer command and help text.
- [x] Support omitted path.
- [x] Support `--json`.
- [x] Render created, updated, unchanged, and conflict summaries.
- [x] Return next commands in JSON output.
- [x] Clarify that init creates a workspace, not the CLI source project.

**Acceptance criteria**

- Works for omitted path, `.`, a missing relative path, and an absolute path.
- A target file fails cleanly.
- Existing user files are preserved according to the PRD.

## MVP-0206 — Add init integration tests

- [x] Fresh empty directory.
- [x] Missing target directory.
- [x] Existing populated directory.
- [x] Existing STL cases.
- [x] Existing `.gitignore`.
- [x] Existing `AGENTS.md` and `CLAUDE.md`.
- [x] Managed rerun.
- [x] Conflicting `SKILL.md`.
- [x] Invalid configuration conflict.
- [x] Simulated write failure.

**Acceptance criteria**

- Test fixtures verify exact resulting trees and contents.

---

# Phase 3 — Configuration and workspace discovery

## MVP-0301 — Define configuration models

- [x] Define Pydantic models for project, Blender, scan, render, workflow, and output sections.
- [x] Add defaults matching the PRD.
- [x] Reject unsafe values and unsupported engines.
- [x] Validate required view names.
- [x] Validate iteration limits, dimensions, and timeouts.
- [x] Reject unknown fields where silent mistakes would be unsafe.

**Acceptance criteria**

- Default generated TOML parses successfully.
- Invalid values produce field-specific errors.

## MVP-0302 — Implement workspace discovery

- [x] Detect an explicit project root option when provided.
- [x] Search upward from the working directory for `stl-analyzer.toml`.
- [x] Stop safely at filesystem root.
- [x] Reject ambiguous or invalid workspace roots.
- [x] Return workspace-relative paths in generated output where possible.

**Acceptance criteria**

- Commands work from the workspace root and nested directories.

## MVP-0303 — Implement configuration loading

- [x] Parse TOML using standard-library facilities for supported Python versions.
- [x] Validate through Pydantic.
- [x] Resolve configured paths against the workspace root.
- [x] Verify configured generated paths remain contained.
- [x] Produce a normalized effective configuration.

**Acceptance criteria**

- Loading does not create files.
- Invalid config maps to configuration exit code.

## MVP-0304 — Implement `config show`

- [x] Add human-readable output.
- [x] Add clean JSON output.
- [x] Show effective normalized values.
- [x] Avoid exposing secrets or arbitrary environment variables.

**Acceptance criteria**

- Output can be consumed by an agent without reading TOML directly.

## MVP-0305 — Implement `config validate`

- [x] Validate workspace and config structure without launching Blender.
- [x] Return all actionable configuration issues where possible.
- [x] Distinguish warnings from failures.

**Acceptance criteria**

- Valid config returns success.
- Invalid config returns structured field-level failures.

---

# Phase 4 — Environment diagnostics and case discovery

## MVP-0401 — Define diagnostic check model

- [ ] Define check name, status, message, details, and remediation fields.
- [ ] Support passed, warning, failed, and skipped states.
- [ ] Calculate overall `ok` consistently.

## MVP-0402 — Implement Blender executable resolution

- [ ] Support executable names resolved from `PATH`.
- [ ] Support configured relative and absolute executable paths.
- [ ] Handle Windows executable naming.
- [ ] Capture version output.
- [ ] Define and document the minimum supported Blender version.

**Acceptance criteria**

- Missing Blender produces a deterministic diagnostic failure.
- Version parsing is tested using fixtures.

## MVP-0403 — Implement `doctor`

- [ ] Check workspace discovery.
- [ ] Check configuration.
- [ ] Check STL-root accessibility.
- [ ] Check Blender executable and background invocation.
- [ ] Check bundled Blender scripts.
- [ ] Check workspace write access without leaving files behind.
- [ ] Check host package/runtime compatibility.
- [ ] Support human and JSON output.

**Acceptance criteria**

- `doctor` does not mutate workspace state.
- Every failure includes a remediation hint.

## MVP-0404 — Define case domain models

- [ ] Define case ID, path, source file, and classification state.
- [ ] Define validation issue and warning models.
- [ ] Keep source paths workspace-relative in serialized output.

## MVP-0405 — Implement case discovery

- [ ] Enumerate immediate child directories only.
- [ ] Ignore non-directory entries at STL root with warnings as appropriate.
- [ ] Detect root-level `.stl` files case-insensitively.
- [ ] Do not recurse.
- [ ] Do not create assets.
- [ ] Sort cases deterministically.

**Acceptance criteria**

- Ready, missing, multiple, and unreadable cases are classified correctly.

## MVP-0406 — Implement `cases list`

- [ ] Add human table output.
- [ ] Add JSON output.
- [ ] Include case ID, relative path, source candidate, and state.
- [ ] Return success even when invalid cases are listed, unless workspace discovery fails.

## MVP-0407 — Implement case validation

- [ ] Validate direct-child case IDs.
- [ ] Reject traversal and absolute case IDs.
- [ ] Require exactly one root-level STL.
- [ ] Require readable regular file.
- [ ] Validate safe assets path.
- [ ] Optionally test write capability without persistent mutation.

## MVP-0408 — Implement `cases validate`

- [ ] Support one case ID.
- [ ] Support `--all`.
- [ ] Continue after per-case failures in `--all` mode.
- [ ] Return aggregate partial-failure exit code when required.
- [ ] Support JSON output.

## MVP-0409 — Add case-discovery tests

- [ ] Empty STL root.
- [ ] One valid case.
- [ ] Missing STL.
- [ ] Multiple STL files.
- [ ] Nested STL only.
- [ ] Uppercase extension.
- [ ] Traversal attempts.
- [ ] Unsafe assets path.
- [ ] Mixed valid and invalid cases.

---

# Phase 5 — Blender process integration and inspection

## MVP-0501 — Define Blender subprocess adapter

- [ ] Build argument arrays without shell interpolation.
- [ ] Invoke Blender in background mode.
- [ ] Pass a manifest path after `--`.
- [ ] Capture stdout, stderr, exit code, and duration.
- [ ] Enforce timeout.
- [ ] Terminate child processes safely on timeout.
- [ ] Map process failures to stable errors.
- [ ] Make the adapter replaceable with a fake in tests.

**Acceptance criteria**

- No user-controlled value is interpolated into a shell command string.
- Timeout and non-zero exits are tested.

## MVP-0502 — Define inspection manifest and result schemas

- [ ] Define source path, output path, case ID, expected hash, and assumed unit.
- [ ] Define inspection result fields from the PRD.
- [ ] Validate Blender output before accepting it.
- [ ] Detect stale or mismatched source hashes.

## MVP-0503 — Implement Blender inspection script

- [ ] Reset Blender to a known empty scene.
- [ ] Import the requested STL.
- [ ] Identify usable mesh objects.
- [ ] Compute vertex and polygon counts.
- [ ] Compute object count and world-space bounding box.
- [ ] Compute dimensions and center.
- [ ] Compute connected components when feasible within MVP performance.
- [ ] Write structured result JSON atomically to the requested location.
- [ ] Never write outside the provided output directory.

**Acceptance criteria**

- Empty or invalid meshes fail with structured output or process failure.
- The script does not depend on the user's startup file.

## MVP-0504 — Implement host inspection service

- [ ] Validate case before launching Blender.
- [ ] Create assets only when required.
- [ ] Write an inspection manifest.
- [ ] Invoke Blender.
- [ ] Validate and promote the result to `assets/geometry.json`.
- [ ] Cache only when source hash, tool schema, and relevant inspection version match.
- [ ] Preserve previous valid metadata until replacement succeeds.

## MVP-0505 — Implement `inspect <CASE_ID>`

- [ ] Add human summary.
- [ ] Add JSON output.
- [ ] Support optional forced reinspection.
- [ ] Report cache usage explicitly.

## MVP-0506 — Add inspection tests

- [ ] Fake-Blender success.
- [ ] Blender missing.
- [ ] Timeout.
- [ ] Invalid JSON result.
- [ ] Source-hash mismatch.
- [ ] Cache hit and invalidation.
- [ ] Real Blender smoke test when available.

---

# Phase 6 — Render models, presets, and Blender rendering

## MVP-0601 — Define render parameter models

- [ ] Define camera, light, material, color-management, resolution, and view models.
- [ ] Define absolute bounds for every adjustable numeric value.
- [ ] Define stable view identifiers.
- [ ] Define coordinate and angle conventions.
- [ ] Define render-engine allowlist.

**Acceptance criteria**

- Invalid parameters fail before Blender starts.

## MVP-0602 — Implement the default dental-arch preset

- [ ] Define occlusal, anterior, posterior, left, right, and isometric views.
- [ ] Derive initial framing from geometry bounds.
- [ ] Define deterministic camera transforms.
- [ ] Define a neutral surface material.
- [ ] Define a bounded key/fill/rim or equivalent lighting rig.
- [ ] Define stable background and color management.
- [ ] Version the preset.

**Acceptance criteria**

- Preset output is complete and serializable.
- The same geometry metadata produces the same initial parameters.

## MVP-0603 — Define render manifest and result schemas

- [ ] Include every field required by the PRD.
- [ ] Include source, config, preset, and script version identifiers.
- [ ] Include output paths for every requested view.
- [ ] Include manifest hash.
- [ ] Validate generated image metadata.

## MVP-0604 — Implement Blender render script

- [ ] Reset scene deterministically.
- [ ] Import the STL.
- [ ] Apply non-destructive scene transforms.
- [ ] Create material, world/background, lights, and camera.
- [ ] Render each requested view.
- [ ] Set exact resolution and image format.
- [ ] Write result JSON.
- [ ] Validate that images exist before reporting success.
- [ ] Never save or overwrite a `.blend` file unless explicitly introduced later.

## MVP-0605 — Implement image post-validation

- [ ] Verify expected image files exist.
- [ ] Verify non-zero size.
- [ ] Verify dimensions match manifest.
- [ ] Verify image format.
- [ ] Reject outputs outside the iteration directory.
- [ ] Record warnings without claiming visual quality.

## MVP-0606 — Add render integration tests

- [ ] Fake Blender result success.
- [ ] Missing image despite success exit.
- [ ] Wrong image dimensions.
- [ ] Output path escape attempt.
- [ ] Real Blender rendering smoke test.
- [ ] Representative small, wide, tall, and off-center mesh fixtures.

---

# Phase 7 — Sessions and immutable iterations

## MVP-0701 — Define session and iteration models

- [ ] Define session identity and state enum.
- [ ] Define iteration identity and status enum.
- [ ] Define current-state pointer model.
- [ ] Define valid state transitions.
- [ ] Define terminal states.
- [ ] Enforce maximum iteration count.

## MVP-0702 — Implement append-only event log

- [ ] Define event schema.
- [ ] Append JSON Lines records safely.
- [ ] Include case, session, iteration, timestamp, and tool version.
- [ ] Reconstruct key state from records for validation where practical.
- [ ] Handle a truncated final line safely and report it.

## MVP-0703 — Implement session repository

- [ ] Create session directories safely.
- [ ] Persist `session.json`.
- [ ] Persist and update convenience `state.json` atomically.
- [ ] Discover latest and active sessions.
- [ ] Prevent multiple active sessions for one case.
- [ ] Never treat `state.json` as the only authoritative record.

## MVP-0704 — Implement iteration repository

- [ ] Allocate zero-padded monotonic iteration numbers.
- [ ] Create iteration directories.
- [ ] Persist manifests before render execution.
- [ ] Persist render results after validation.
- [ ] Mark completed iterations immutable.
- [ ] Reject attempts to overwrite completed iteration artifacts.

## MVP-0705 — Implement session start service

- [ ] Validate the case.
- [ ] Ensure current geometry metadata.
- [ ] Create a session.
- [ ] Generate initial preset parameters.
- [ ] Create iteration `001`.
- [ ] Render required views.
- [ ] Transition to `awaiting_review`.
- [ ] Record all state changes as events.

## MVP-0706 — Implement `session start`

- [ ] Add command and JSON output.
- [ ] Return session ID, iteration, state, and image paths.
- [ ] Reject a second active session.
- [ ] Avoid hidden prompts.

## MVP-0707 — Implement `session resume`

- [ ] Locate latest non-terminal session.
- [ ] Validate persisted state and artifacts.
- [ ] Return next expected action.
- [ ] Do not create an iteration or launch Blender.

## MVP-0708 — Implement safe `session reset`

- [ ] Require an exact session ID or explicit force-style confirmation flag.
- [ ] Keep command non-interactive.
- [ ] Never remove source STL or finalized output.
- [ ] Choose and document archive-versus-delete MVP behavior.
- [ ] Record reset operation.

## MVP-0709 — Add session tests

- [ ] First session creation.
- [ ] Duplicate active-session rejection.
- [ ] Resume after rendering.
- [ ] Resume after review.
- [ ] Corrupt state pointer with intact session records.
- [ ] Maximum iteration enforcement.
- [ ] Safe reset behavior.

---

# Phase 8 — Reviews and adjustments

## MVP-0801 — Define review schema

- [ ] Define `accept`, `retry`, and `reject` decisions.
- [ ] Define issue code, severity, view, and details.
- [ ] Require summary.
- [ ] Require actionable information for retry.
- [ ] Prevent accept with unresolved critical issues.
- [ ] Reject unknown fields.

## MVP-0802 — Implement review persistence

- [ ] Validate iteration ownership.
- [ ] Require completed render.
- [ ] Persist one canonical review per iteration.
- [ ] Refuse silent overwrite.
- [ ] Record `review.recorded` event.
- [ ] Update session state consistently.

## MVP-0803 — Implement `iterations review`

- [ ] Accept `--review <FILE>`.
- [ ] Support JSON output.
- [ ] Validate file before state mutation.
- [ ] Return next expected action.
- [ ] Transition accepted sessions toward finalization eligibility.

## MVP-0804 — Define adjustment schema and vocabulary

- [ ] Define allowed parameters.
- [ ] Define allowed operations for each parameter.
- [ ] Define absolute ranges.
- [ ] Define maximum per-iteration deltas.
- [ ] Define requested-view rules.
- [ ] Define reason field.
- [ ] Reject paths, executable options, scripts, and arbitrary expressions.

**Initial adjustable areas**

- Camera yaw and pitch per view.
- Camera distance or orthographic scale per view.
- Framing margin.
- Key-light energy and orientation.
- Fill-light energy.
- Rim-light energy if included by preset.
- Material roughness within safe bounds.
- Requested subset of configured views.

## MVP-0805 — Implement adjustment application

- [ ] Require a prior retry review for the source iteration.
- [ ] Validate adjustment schema and semantic bounds.
- [ ] Load prior effective parameters.
- [ ] Apply changes without mutating prior artifacts.
- [ ] Materialize complete next-iteration parameters.
- [ ] Enforce session iteration limit before directory creation.
- [ ] Record `adjustment.applied` event.

## MVP-0806 — Implement `render <CASE_ID> --adjustment <FILE>`

- [ ] Resolve active session.
- [ ] Validate current state.
- [ ] Apply adjustment.
- [ ] Create and render the next iteration.
- [ ] Transition back to `awaiting_review`.
- [ ] Return generated image paths.
- [ ] Support clean JSON output.

## MVP-0807 — Implement render without adjustment

- [ ] Define the valid use case for `render <CASE_ID>` in the MVP.
- [ ] Prevent accidental duplicate iteration creation.
- [ ] Prefer rerendering only from explicit state or a documented retry mechanism.
- [ ] Keep semantics clear in help and tests.

## MVP-0808 — Add review and adjustment tests

- [ ] Accept review success.
- [ ] Retry review success.
- [ ] Invalid review fields.
- [ ] Duplicate review rejection.
- [ ] Unknown adjustment parameter.
- [ ] Out-of-range absolute value.
- [ ] Excessive per-iteration delta.
- [ ] Adjustment without retry review.
- [ ] Adjustment after maximum iterations.
- [ ] Immutability of prior iteration.

---

# Phase 9 — Iteration inspection and comparison

## MVP-0901 — Implement `iterations list`

- [ ] List iterations deterministically.
- [ ] Include render state, review decision, timestamps, and finalization eligibility.
- [ ] Support human and JSON output.

## MVP-0902 — Implement `iterations show`

- [ ] Return manifest, render result, review summary, and image paths.
- [ ] Avoid dumping unbounded Blender logs by default.
- [ ] Support JSON output.

## MVP-0903 — Implement deterministic comparison

- [ ] Compare requested views.
- [ ] Compare camera parameters.
- [ ] Compare lighting parameters.
- [ ] Compare material parameters.
- [ ] Compare render duration and warnings.
- [ ] Compare review metadata.
- [ ] Explicitly avoid a visual-quality winner claim.

## MVP-0904 — Implement `iterations compare`

- [ ] Support two iteration numbers.
- [ ] Present changed and unchanged fields.
- [ ] Support JSON output.
- [ ] Reject iterations from another session unless explicitly supported later.

---

# Phase 10 — Status, terminal states, and finalization

## MVP-1001 — Define next-action codes

- [ ] Define structured next actions such as:
  - `RUN_DOCTOR`
  - `VALIDATE_CASE`
  - `INSPECT_GEOMETRY`
  - `START_SESSION`
  - `INSPECT_IMAGES`
  - `RECORD_REVIEW`
  - `CREATE_ADJUSTMENT`
  - `FINALIZE_CASE`
  - `NONE_COMPLETED`
  - `NONE_TERMINAL_FAILURE`
- [ ] Map every valid state to one next action.

## MVP-1002 — Implement status service

- [ ] Resolve source hash and latest session.
- [ ] Validate convenience state against durable artifacts.
- [ ] Identify current iteration.
- [ ] Identify images requiring agent inspection.
- [ ] Include review decision and remaining iteration capacity.
- [ ] Identify terminal success or failure.

## MVP-1003 — Implement `status <CASE_ID>`

- [ ] Add human-readable summary.
- [ ] Add complete JSON response.
- [ ] Guarantee enough information for a new agent to resume.

## MVP-1004 — Define final description validation

- [ ] Require a readable non-empty Markdown file.
- [ ] Define required observational and limitations sections or equivalent structure.
- [ ] Add simple prohibited-claim guidance without attempting medical NLP classification.
- [ ] Avoid silently rewriting agent-authored description content.

## MVP-1005 — Implement finalization service

- [ ] Validate selected session and iteration.
- [ ] Require completed render.
- [ ] Require persisted accept review.
- [ ] Require all configured required views.
- [ ] Validate description.
- [ ] Create final output transactionally.
- [ ] Copy or materialize final images.
- [ ] Persist `result.json` and selected render metadata.
- [ ] Preserve immutable iteration files.
- [ ] Transition session to `completed`.
- [ ] Record final event.

## MVP-1006 — Implement `finalize`

- [ ] Add required `--iteration` and `--description` options.
- [ ] Support JSON output.
- [ ] Refuse non-accepted iterations.
- [ ] Return final paths and result summary.

## MVP-1007 — Implement quality-not-met transition

- [ ] Transition automatically when the maximum iteration count is exhausted without acceptance.
- [ ] Return process exit code `7` where appropriate.
- [ ] Preserve all iterations and reviews.
- [ ] Ensure status reports terminal failure without requesting human action.

## MVP-1008 — Implement `clean <CASE_ID>`

- [ ] Define exact MVP cleanup scope.
- [ ] Require explicit non-interactive confirmation flag for destructive cleanup.
- [ ] Never delete source STL.
- [ ] Never delete finalized output unless a separate explicit option is provided.
- [ ] Prevent path escape.
- [ ] Support dry-run output if included in MVP.

---

# Phase 11 — Agent instruction generation

## MVP-1101 — Write canonical `SKILL.md` template

- [ ] Define tool purpose and boundaries.
- [ ] Define required input layout.
- [ ] Define the complete zero-HITL workflow.
- [ ] Require `--json` for machine-facing commands.
- [ ] Require image inspection after each render.
- [ ] Define review and adjustment file expectations.
- [ ] Define acceptance guidance.
- [ ] Define maximum-iteration behavior.
- [ ] Define final description rules.
- [ ] Prohibit STL mutation, generated-state editing, and arbitrary Blender code.
- [ ] Explain terminal states.

**Acceptance criteria**

- An agent with no prior conversation context can execute the workflow using only the generated workspace and CLI help.

## MVP-1102 — Write `AGENTS.md` managed block

- [ ] Point agents to `SKILL.md`.
- [ ] State that the CLI is the deterministic execution layer.
- [ ] Prohibit direct modification of generated state and source STL.
- [ ] Keep block short and canonical.

## MVP-1103 — Write `CLAUDE.md` managed block

- [ ] Point Claude Code to `SKILL.md`.
- [ ] Avoid duplicating the full workflow.
- [ ] Keep behavior aligned with `AGENTS.md`.

## MVP-1104 — Test generated instructions

- [ ] Snapshot-test all templates.
- [ ] Verify referenced commands exist.
- [ ] Verify examples use valid JSON schemas.
- [ ] Verify no AI SDK or provider requirement appears.
- [ ] Verify instructions explicitly require no human camera or lighting decisions.

---

# Phase 12 — End-to-end validation and release readiness

## MVP-1201 — Create non-sensitive test fixtures

- [ ] Add a minimal generic STL fixture for import testing.
- [ ] Add or generate a synthetic dental-arch-like fixture for framing tests.
- [ ] Document fixture origin and license.
- [ ] Keep fixture sizes suitable for repository and CI use.
- [ ] Do not commit patient-derived scans without explicit legal clearance.

## MVP-1202 — Implement fake Blender test harness

- [ ] Simulate successful inspection.
- [ ] Simulate successful rendering.
- [ ] Simulate timeout.
- [ ] Simulate non-zero exit.
- [ ] Simulate malformed result JSON.
- [ ] Simulate output path violation.

## MVP-1203 — Implement full end-to-end test

The test must:

- [ ] Initialize a temporary workspace.
- [ ] Add one case with one STL.
- [ ] Run diagnostics with a controlled Blender adapter.
- [ ] List and validate the case.
- [ ] Inspect geometry.
- [ ] Start a session and render iteration 1.
- [ ] Record a retry review.
- [ ] Apply a valid adjustment.
- [ ] Render iteration 2.
- [ ] Record an accept review.
- [ ] Write an observational description.
- [ ] Finalize iteration 2.
- [ ] Verify final result and images.
- [ ] Verify source STL hash and bytes are unchanged.

## MVP-1204 — Add Windows-focused tests

- [ ] Test drive-letter absolute paths.
- [ ] Test backslash input.
- [ ] Test reserved or invalid filename handling.
- [ ] Test executable paths containing spaces.
- [ ] Test atomic-write fallback behavior.
- [ ] Test directory junction or symlink containment where supported.

## MVP-1205 — Add optional real-Blender test marker

- [ ] Mark tests requiring Blender.
- [ ] Skip clearly when Blender is unavailable.
- [ ] Document how to run them locally.
- [ ] Ensure normal unit tests do not require Blender.

## MVP-1206 — Align README with implementation

- [ ] Replace planning-stage wording once commands exist.
- [ ] Add installation instructions.
- [ ] Add quick start.
- [ ] Add workspace and case examples.
- [ ] Add command reference links.
- [ ] Add troubleshooting guidance.
- [ ] Keep AI/provider boundaries explicit.

## MVP-1207 — Add CLI reference documentation

- [ ] Document every command, argument, option, output, and exit-code class.
- [ ] Document adjustment and review schemas.
- [ ] Document filesystem contracts.
- [ ] Document state transitions.

## MVP-1208 — Add security and privacy review

- [ ] Review all path-handling code.
- [ ] Review subprocess argument construction.
- [ ] Confirm no shell execution is required.
- [ ] Confirm logs avoid secrets and unnecessary absolute paths.
- [ ] Confirm source STL is never opened for writing.
- [ ] Confirm generated files remain inside assets.
- [ ] Confirm CLI performs no network requests.

## MVP-1209 — Complete MVP quality gate

- [ ] All unit tests pass.
- [ ] All fake-Blender integration tests pass.
- [ ] Real-Blender smoke tests pass on a supported environment.
- [ ] Ruff check passes.
- [ ] Ruff format check passes.
- [ ] mypy passes.
- [ ] README, PRD, TASKS, CLI help, and generated `SKILL.md` agree.
- [ ] No MVP non-goal has been implemented accidentally.

## MVP-1210 — Prepare first MVP release

- [ ] Select package version.
- [ ] Add changelog or release notes.
- [ ] Confirm build succeeds with `uv build`.
- [ ] Inspect wheel and source distribution contents.
- [ ] Verify templates are included as package data.
- [ ] Verify install-and-run in a clean temporary environment.
- [ ] Tag and publish only after the MVP quality gate is complete.

---

# 13. Cross-cutting definition of done

Every implementation task must satisfy all applicable points:

- [ ] Behavior matches the PRD.
- [ ] Public functions and models are typed.
- [ ] Expected failures use structured domain errors.
- [ ] Agent-facing output supports clean JSON.
- [ ] No command introduces an interactive prompt.
- [ ] Filesystem operations enforce containment.
- [ ] Source STL files are never modified.
- [ ] Tests cover success and failure paths.
- [ ] Documentation is updated in the same change.
- [ ] Ruff, mypy, and pytest pass.

# 14. Recommended implementation batches

## Batch A — Foundation and init

Includes:

- MVP-0001 through MVP-0004
- MVP-0101 through MVP-0105
- MVP-0201 through MVP-0206
- MVP-0301 through MVP-0305

**Outcome:** installable CLI with safe, production-quality workspace initialization.

## Batch B — Cases and diagnostics

Includes:

- MVP-0401 through MVP-0409
- MVP-0501

**Outcome:** workspaces and cases can be discovered, validated, and diagnosed without rendering.

## Batch C — Inspection and initial rendering

Includes:

- MVP-0502 through MVP-0506
- MVP-0601 through MVP-0606
- MVP-0701 through MVP-0706

**Outcome:** a case can be inspected and rendered into a durable first iteration.

## Batch D — Autonomous iteration contract

Includes:

- MVP-0707 through MVP-0709
- MVP-0801 through MVP-0808
- MVP-0901 through MVP-0904
- MVP-1001 through MVP-1003

**Outcome:** an external coding agent can review, adjust, rerender, compare, and resume without human intervention.

## Batch E — Finalization and agent interoperability

Includes:

- MVP-1004 through MVP-1008
- MVP-1101 through MVP-1104

**Outcome:** accepted iterations can be finalized and newly initialized workspaces contain complete agent instructions.

## Batch F — MVP hardening and release

Includes:

- MVP-1201 through MVP-1210

**Outcome:** tested, documented, distributable MVP.

# 15. Scope-control checklist

Before accepting any task not listed above, verify that it does not introduce:

- Embedded AI or an AI SDK.
- Remote image analysis.
- More than one STL per case.
- Geometry editing.
- Diagnostic clinical claims.
- A GUI.
- A database.
- Cloud execution.
- Parallel processing.
- Additional scan formats.

Any such change requires an explicit PRD revision rather than silent inclusion in the MVP.