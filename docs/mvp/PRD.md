# STL Analyzer MVP Product Requirements Document

## 1. Document status

- **Product:** `stl-analyzer`
- **Milestone:** MVP
- **Status:** Approved for implementation planning
- **Primary users:** Agentic coding tools such as Codex, Claude Code, and Antigravity
- **Execution model:** Local-first, deterministic Python CLI controlled by an external coding agent

## 2. Summary

`stl-analyzer` is a local Python command-line tool that enables agentic coding tools to inspect dental STL scans, render them with headless Blender, evaluate the generated images using their own vision capabilities, and iteratively refine camera and lighting parameters without human intervention.

The CLI is not an AI application. It does not embed an AI SDK, vision provider, model, prompt runner, or API credentials. Its responsibility is to provide deterministic, validated operations and durable workflow state. The external coding agent is responsible for reasoning, visual evaluation, adjustment selection, acceptance, and final description generation.

The MVP handles one STL scan per case. Multi-scan and full-set dental workflows are explicitly deferred.

## 3. Problem statement

Agentic coding tools can inspect images and reason about rendering quality, but they need a safe and predictable execution layer for local STL workflows. Directly manipulating Blender scripts and filesystem state on every iteration creates several problems:

- Commands and outputs vary between agents.
- Camera and lighting changes are difficult to validate.
- Workflow state may exist only in conversation context.
- A different agent cannot reliably resume an interrupted workflow.
- Source STL files can be modified or overwritten accidentally.
- Visual iterations are difficult to compare and audit.
- Agents may generate arbitrary Blender code instead of constrained changes.
- Human input may be requested when an agent loses context.

The product solves these problems by exposing a stable CLI, structured schemas, immutable render iterations, persistent reviews, and a canonical `SKILL.md` workflow.

## 4. Product principles

### 4.1 Agent-controlled, not AI-embedded

The coding agent orchestrates the workflow. The CLI only performs deterministic operations.

### 4.2 Zero Human-in-the-Loop during execution

Once a case workflow begins, the coding agent must not ask a human to select views, camera angles, lighting settings, or the best iteration. It must continue autonomously until it succeeds or reaches a defined terminal failure state.

### 4.3 Local-first

The CLI does not upload STL files, images, reviews, or descriptions. It performs local filesystem and Blender operations only.

### 4.4 Non-destructive

Source STL files are read-only. Generated artifacts are written only beneath the case's configured assets directory.

### 4.5 Deterministic execution

Given the same input STL, configuration, render parameters, Blender version, and tool version, the CLI should produce repeatable state transitions and materially equivalent render output.

### 4.6 Structured agent interface

Every command used by an agent must support machine-readable JSON output. Errors must be structured and must never require interactive confirmation.

### 4.7 Durable workflow state

Sessions, iterations, render manifests, reviews, and final selections must be persisted so another agent can understand and resume the workflow without conversation history.

## 5. Goals

The MVP must:

1. Provide a Python CLI installable and runnable with `uv`.
2. Initialize an arbitrary directory as an agent-ready STL Analyzer workspace.
3. Discover case folders under a configured STL root.
4. Validate exactly one root-level STL file per case.
5. Inspect STL geometry using headless Blender.
6. Create a render session with deterministic initial parameters.
7. Render a standard set of dental scan views with headless Blender.
8. Accept validated, bounded camera and lighting adjustments from an external coding agent.
9. Persist every render iteration and review.
10. Expose enough state for an agent to resume safely.
11. Finalize an accepted iteration with an observational description.
12. Generate and install a canonical `SKILL.md` for autonomous agent operation.
13. Prevent source mutation and unsafe filesystem writes.
14. Terminate cleanly when quality cannot be achieved within configured limits.

## 6. Non-goals

The MVP will not:

- Embed OpenAI, Anthropic, Google, or another AI SDK.
- Call a remote vision model.
- Manage AI API keys.
- Contain model prompts for image interpretation.
- Provide a web UI or desktop UI.
- Provide a Blender add-on UI.
- Edit or repair STL geometry.
- Produce a clinical diagnosis or treatment recommendation.
- Measure margins, occlusion, preparation geometry, or pathology.
- Support DICOM, OBJ, PLY, CBCT, or proprietary scan formats.
- Support more than one STL file per case.
- Support upper, lower, and bite scans as one combined case.
- Run multiple cases in parallel.
- Use a database, cloud queue, or hosted worker.
- Guarantee compatibility with every agentic coding tool.
- Install Blender, Python, or `uv` automatically.

## 7. Personas

### 7.1 Agentic coding tool

The primary persona is a coding agent operating in a local repository or workspace. It can:

- Read Markdown instructions.
- Execute shell commands.
- Read JSON files.
- Open generated images.
- Reason about framing and visual quality.
- Create structured JSON and Markdown files.

It needs deterministic commands, explicit state, bounded adjustment schemas, and non-interactive failures.

### 7.2 Developer or operator

A developer installs the CLI, initializes a workspace, places case folders under `stl/`, and chooses the agentic coding tool. The developer is not expected to intervene in the active render loop.

## 8. Technology requirements

### 8.1 Runtime and packaging

- Python 3.12 or newer.
- `uv` for dependency management, environment execution, lockfile creation, builds, and developer commands.
- `pyproject.toml` using a standard Python build backend.
- Console entry point named `stl-analyzer`.

### 8.2 Core libraries

- Typer for command definitions and argument parsing.
- Pydantic v2 for domain models, configuration, JSON schemas, and validation.
- Rich for human-readable output.
- Standard library subprocess APIs for Blender execution.

### 8.3 Development quality

- pytest for unit and integration testing.
- Ruff for formatting and linting.
- mypy for static type checking.
- No runtime dependency on an installed `bpy` package in the `uv` environment.

### 8.4 Blender integration

Blender-specific scripts run inside Blender's bundled Python environment:

```powershell
blender --background --python <script> -- <arguments>
```

The host Python process communicates with Blender through validated JSON manifests and result files, not through direct `bpy` imports.

## 9. Workspace model

### 9.1 Project root marker

A workspace root is identified by `stl-analyzer.toml`.

Commands executed from nested directories may search upward for this file unless an explicit project path is provided.

### 9.2 Initialized layout

```text
<workspace>/
├── stl-analyzer.toml
├── SKILL.md
├── AGENTS.md
├── CLAUDE.md
├── .gitignore
└── stl/
    └── .gitkeep
```

### 9.3 Case layout

Each immediate child of the configured `stl_root` is one case. Its directory name is its `case_id`.

```text
stl/
└── case-001/
    ├── upper.stl
    └── assets/
```

MVP case rules:

- Exactly one regular file with a `.stl` extension must exist at the case root.
- Extension matching is case-insensitive.
- STL discovery does not recurse into subdirectories.
- Symlink behavior must be explicit and safe; following symlinks outside the workspace is prohibited by default.
- The source STL must never be modified, renamed, copied over, or deleted.
- The assets directory is created only when persistent generated state is required.

## 10. `init` requirements

### 10.1 Command

```text
stl-analyzer init [PATH]
```

`PATH` defaults to the current directory.

Examples:

```powershell
stl-analyzer init .
stl-analyzer init C:\Projects\dental-cases
```

### 10.2 Purpose

`init` converts a target directory into an STL Analyzer workspace. It does not scaffold the CLI source repository itself.

### 10.3 Required behavior

The command must:

1. Resolve the target to an absolute normalized path.
2. Create the target directory when it does not exist.
3. Reject a target that exists as a regular file.
4. Perform a complete preflight before writing.
5. Detect conflicts and abort without partial writes.
6. Create `stl-analyzer.toml` from a versioned built-in template.
7. Create `SKILL.md` from a versioned built-in template.
8. Create the configured STL root and `.gitkeep`.
9. Create or update a managed section in `AGENTS.md`.
10. Create or update a managed section in `CLAUDE.md`.
11. Create or update a managed section in `.gitignore`.
12. Report created, updated, unchanged, and conflicting paths.
13. Support JSON output.
14. Return success when rerun against an unchanged managed workspace.

### 10.4 Conflict behavior

- Existing unmanaged `SKILL.md`: hard conflict in the MVP.
- Existing `stl-analyzer.toml` not recognized as managed or valid: hard conflict.
- Existing `AGENTS.md`, `CLAUDE.md`, or `.gitignore`: preserve all unmanaged content and add/update only a delimited managed block.
- Existing `stl/`: preserve all contents.

Managed blocks must use stable markers and must not be duplicated.

### 10.5 Transactional behavior

If any preflight conflict or permission failure is discovered, the command must not change the target. During commit, temporary files and atomic replacement should be used where supported. If a commit-stage failure occurs, the command should attempt rollback and report every path whose state may require inspection.

### 10.6 Explicit exclusions

`init` must not:

- Install Blender, Python, or `uv`.
- Create a virtual environment.
- Run `uv init`.
- Create sample cases or sample STL files.
- Create `assets/` directories for cases.
- Run `doctor`, inspection, or rendering.
- Invoke an AI model.

## 11. Configuration

The default configuration file is TOML.

Required initial sections:

```toml
[project]
stl_root = "stl"
assets_directory = "assets"

[blender]
executable = "blender"
timeout_seconds = 180

[scan]
allowed_extensions = [".stl"]
maximum_files_per_case = 1
assumed_unit = "millimeters"

[render]
width = 1024
height = 1024
engine = "BLENDER_EEVEE_NEXT"
default_preset = "dental_arch"

[workflow]
maximum_iterations = 6
required_views = [
    "occlusal",
    "anterior",
    "posterior",
    "left",
    "right",
    "isometric",
]

[output]
retain_all_iterations = true
write_event_log = true
```

Configuration requirements:

- Parse through a Pydantic model.
- Reject unknown or invalid values where ambiguity would be unsafe.
- Resolve workspace-relative paths against the project root.
- Keep source and generated paths within approved roots.
- Expose the effective merged configuration through `config show`.
- Validate without running Blender through `config validate`.

## 12. CLI behavior

### 12.1 General requirements

All commands must:

- Be non-interactive.
- Have stable help output.
- Support useful human-readable output.
- Support `--json` for agent-facing output where applicable.
- Write errors to stderr in human mode.
- Never emit logs before or after a JSON document in JSON mode.
- Use non-zero exit codes for failures.
- Avoid stack traces by default for expected user errors.
- Offer verbose diagnostics through an explicit flag.

### 12.2 Planned command surface

```text
stl-analyzer init [PATH]
stl-analyzer doctor
stl-analyzer config show
stl-analyzer config validate

stl-analyzer cases list
stl-analyzer cases validate <CASE_ID>
stl-analyzer cases validate --all

stl-analyzer inspect <CASE_ID>

stl-analyzer session start <CASE_ID>
stl-analyzer session resume <CASE_ID>
stl-analyzer session reset <CASE_ID>

stl-analyzer render <CASE_ID>
stl-analyzer render <CASE_ID> --adjustment <FILE>

stl-analyzer iterations list <CASE_ID>
stl-analyzer iterations show <CASE_ID> <ITERATION>
stl-analyzer iterations compare <CASE_ID> <A> <B>
stl-analyzer iterations review <CASE_ID> <ITERATION> --review <FILE>

stl-analyzer status <CASE_ID>
stl-analyzer finalize <CASE_ID> --iteration <N> --description <FILE>
stl-analyzer clean <CASE_ID>
```

## 13. Environment diagnostics

`doctor` must inspect the environment without mutating it.

Required checks:

- Workspace root can be resolved.
- Configuration parses successfully.
- STL root exists or can be created according to command context.
- Blender executable can be resolved.
- Blender can execute in background mode.
- Blender version is supported.
- Bundled Blender scripts are present.
- Workspace and relevant assets roots are writable.
- Required Python package versions are available.

The output must include an overall `ok` value and one structured record per check.

## 14. Case discovery and validation

### 14.1 `cases list`

The command must enumerate immediate child directories of the STL root and classify each case without creating assets.

Possible case states include:

- `ready`
- `missing_stl`
- `multiple_stl_files`
- `invalid_case_directory`
- `unreadable`

### 14.2 `cases validate`

Validation must verify:

- The case ID resolves to a direct child of the STL root.
- Directory traversal is rejected.
- Exactly one allowed STL exists at the root.
- The STL is a readable regular file.
- The configured assets path does not escape the case.
- Generated state can be written when requested.

`--all` must continue across cases and return an aggregate result.

## 15. Geometry inspection

`inspect <CASE_ID>` must invoke Blender headlessly and produce `assets/geometry.json`.

Minimum fields:

- Schema version.
- Tool version.
- Case ID.
- Source relative path.
- Source SHA-256.
- Source size.
- Blender version.
- Triangle or polygon count.
- Vertex count.
- Object count.
- Connected component count when feasible.
- Bounding box minimum and maximum.
- Dimensions.
- Geometric center.
- Assumed unit.
- Warnings.
- Inspection timestamp.

Inspection must fail when Blender cannot import the STL or no usable mesh is present.

The CLI must not assume that STL coordinates contain a formal unit declaration. `assumed_unit` is configuration metadata, not a fact extracted from STL.

## 16. Session model

A session represents one autonomous attempt to obtain acceptable visual coverage for a case.

### 16.1 Session identity

A session ID must be filesystem-safe and sortable, for example:

```text
20260730T195800Z-a41c
```

### 16.2 Session states

Minimum states:

- `created`
- `rendering`
- `awaiting_review`
- `adjustment_ready`
- `completed`
- `quality_not_met`
- `failed`
- `cancelled`

### 16.3 Session start

`session start` must:

1. Validate the case.
2. Ensure current geometry inspection exists for the source hash.
3. Create a new session directory.
4. Derive deterministic initial render parameters from geometry.
5. Persist session state before invoking Blender.
6. Create the first iteration and render it unless an explicit future option suppresses rendering.
7. End in `awaiting_review` after a successful render.

Starting another active session for the same case should fail unless the previous session is terminal or an explicit reset policy is used.

### 16.4 Resume

`session resume` must report and restore the latest non-terminal session without discarding its iterations or reviews. It must not create a new iteration by itself.

### 16.5 Reset

`session reset` is a destructive command and must remain non-interactive. It requires an explicit confirmation flag or exact session identifier. It may archive or delete generated session state according to configuration, but never source STL or finalized output.

## 17. Rendering

### 17.1 Standard views

The default dental arch preset includes:

- `occlusal`
- `anterior`
- `posterior`
- `left`
- `right`
- `isometric`

The precise coordinate convention and camera transforms must be documented and stable.

### 17.2 Initial framing

Initial camera placement must be derived from the imported mesh bounding box and must:

- Center the mesh for rendering without altering the source file.
- Preserve the entire scan inside frame margins.
- Avoid near and far clipping.
- Use deterministic transforms.
- Record every transform in the render manifest.

### 17.3 Scene requirements

The render script must create a controlled scene including:

- A neutral material that exposes surface form.
- A stable background.
- A bounded lighting rig.
- A stable color-management configuration.
- Explicit resolution and render engine.
- No dependency on the user's Blender startup scene.

### 17.4 Render manifest

Each iteration must persist the complete validated render input before Blender is executed. It must include:

- Schema version.
- Case and session IDs.
- Iteration number.
- Source STL path and hash.
- Output directory.
- Required views.
- Camera parameters.
- Lighting parameters.
- Material parameters.
- Resolution.
- Render engine.
- Blender script version.

### 17.5 Render result

Each successful iteration must persist:

- Manifest reference or hash.
- Generated image paths.
- Image dimensions.
- Render duration.
- Blender version.
- Warnings.
- Exit status.
- Timestamps.

A render iteration is immutable after completion.

## 18. Adjustment contract

The external coding agent creates an adjustment JSON document. The CLI validates and applies it to create a new iteration.

Example:

```json
{
  "reason": "The posterior region is underexposed and the occlusal view has excessive empty space.",
  "changes": [
    {
      "parameter": "lighting.fill.energy",
      "operation": "increase",
      "value": 0.2
    },
    {
      "parameter": "camera.occlusal.scale",
      "operation": "multiply",
      "value": 0.9
    }
  ],
  "requested_views": [
    "occlusal",
    "posterior",
    "isometric"
  ]
}
```

Requirements:

- Only an allowlisted parameter vocabulary is accepted.
- Only allowlisted operations are accepted per parameter.
- Every numeric value has an absolute valid range and maximum per-iteration delta.
- Unknown fields are rejected.
- Path or code injection is impossible through the schema.
- The adjustment cannot alter source paths, output roots, Blender scripts, or executable arguments.
- The previous iteration remains unchanged.
- The new effective render parameters are fully materialized in the next manifest.

The MVP must not accept arbitrary Python, Blender expressions, or free-form executable commands from the agent.

## 19. Review contract

The coding agent records its evaluation through `iterations review`.

Example:

```json
{
  "decision": "retry",
  "summary": "The full scan is visible, but posterior surface detail remains difficult to inspect.",
  "issues": [
    {
      "code": "posterior_underexposed",
      "severity": "high",
      "view": "posterior",
      "details": "The distal region blends into shadow."
    }
  ],
  "next_action": "Increase fill illumination and rerender posterior and isometric views."
}
```

Allowed decisions:

- `accept`
- `retry`
- `reject`

Requirements:

- One canonical review per iteration.
- A review cannot be silently overwritten.
- Revisions, if supported, must preserve history.
- `accept` must include a summary and no unresolved critical issues.
- `retry` must contain at least one actionable issue or next action.
- Reviews are agent-authored observations, not CLI-generated clinical judgments.

## 20. Iteration management

### 20.1 Listing and showing

The CLI must expose iteration number, render status, review decision, timestamps, image paths, and whether the iteration is eligible for finalization.

### 20.2 Comparison

`iterations compare` performs deterministic metadata comparison only. It may compare:

- Render parameters.
- Requested and generated views.
- Image dimensions.
- Render duration.
- Warnings.
- Recorded review decisions.

It must not claim one render is clinically or visually superior.

### 20.3 Maximum iterations

The configured maximum is enforced by the CLI. When the maximum is reached without an accepted iteration, the session transitions to `quality_not_met`. The agent must not bypass this limit by manually editing state files.

## 21. Status and resumability

`status <CASE_ID>` must return enough information for an agent with no prior conversation context to choose the next valid action.

Minimum output:

- Case ID.
- Source hash.
- Active or latest session ID.
- Session state.
- Current iteration.
- Maximum iterations.
- Latest render status.
- Latest review decision.
- Paths to images requiring inspection.
- Next expected action as a structured code and human-readable text.
- Finalization status.

## 22. Finalization

### 22.1 Command

```text
stl-analyzer finalize <CASE_ID> --iteration <N> --description <FILE>
```

### 22.2 Preconditions

Finalization requires:

- The selected iteration belongs to the active or specified session.
- Rendering completed successfully.
- All configured required views exist, unless a documented accepted override policy is added later.
- The selected iteration has a persisted `accept` review.
- No unresolved critical issue exists in that review.
- The description file exists, is readable, and is non-empty.
- The description passes basic structural validation.

### 22.3 Description policy

The final description must be observational. It should distinguish:

- What is visibly present.
- What is not visible or is uncertain.
- Limitations caused by scan coverage or render quality.

It must not claim a diagnosis, pathology, treatment plan, or measurement that the workflow does not establish.

### 22.4 Final output

```text
assets/final/
├── result.json
├── clinical-description.md
├── render.json
└── images/
```

`result.json` must include source hash, session ID, selected iteration, review reference, description reference, copied image references, tool version, Blender version, and completion timestamp.

Finalization must copy or materialize final artifacts without changing the immutable iteration.

## 23. Generated filesystem model

```text
stl/<case-id>/
├── <source>.stl
└── assets/
    ├── geometry.json
    ├── state.json
    ├── sessions/
    │   └── <session-id>/
    │       ├── session.json
    │       ├── events.jsonl
    │       └── iterations/
    │           └── 001/
    │               ├── manifest.json
    │               ├── render.json
    │               ├── review.json
    │               └── images/
    └── final/
        ├── result.json
        ├── clinical-description.md
        ├── render.json
        └── images/
```

Requirements:

- JSON files are written atomically where practical.
- Session events are append-only.
- Completed iterations are immutable.
- `state.json` is a convenience pointer, not the sole authoritative record.
- No generated path may escape its case assets directory.
- Windows-compatible paths and filenames are required.

## 24. Agent instruction files

### 24.1 `SKILL.md`

`SKILL.md` is the canonical workflow contract. It must instruct the agent to:

1. Run environment diagnostics.
2. Discover and validate the requested case.
3. Inspect geometry.
4. Start or resume a session.
5. Open every generated image.
6. Evaluate framing, orientation, coverage, lighting, contrast, clipping, and visible detail.
7. Record a structured review.
8. Create only schema-valid bounded adjustments.
9. Repeat without human intervention.
10. Stop at the configured maximum iterations.
11. Select an accepted iteration only.
12. Write an observational description with limitations.
13. Finalize and verify the structured result.
14. Treat `quality_not_met` and deterministic failures as terminal results rather than asking a human for camera guidance.

It must also prohibit:

- Modifying source STL files.
- Editing generated state or manifests manually.
- Running arbitrary Blender code as a substitute for CLI adjustments.
- Inventing clinical findings not visible in the rendered images.
- Exposing patient-identifying data unnecessarily.

### 24.2 `AGENTS.md`

Contains a short managed section directing compatible tools to read `SKILL.md` and use the CLI as the execution layer.

### 24.3 `CLAUDE.md`

Contains a short managed section directing Claude Code to the same canonical `SKILL.md`.

## 25. Privacy and safety

- The CLI itself performs no network upload.
- Case IDs and filenames should avoid names, dates of birth, record numbers, or other patient identifiers.
- Logs should prefer workspace-relative paths.
- Secrets and environment variables must not be written into generated state.
- The final description must be framed as an observational artifact rather than a medical diagnosis.
- Users remain responsible for the data-handling configuration of the external coding agent.

## 26. Error model

Every JSON failure should follow a common envelope similar to:

```json
{
  "success": false,
  "error": {
    "code": "MULTIPLE_STL_FILES",
    "message": "Case 'case-001' contains more than one root-level STL file.",
    "details": {
      "files": [
        "upper.stl",
        "lower.stl"
      ]
    },
    "recoverable": true,
    "suggested_action": "Keep exactly one STL file in the case root for the MVP."
  }
}
```

Initial exit-code classes:

| Exit code | Meaning |
|---:|---|
| 0 | Success |
| 1 | Unexpected internal error |
| 2 | Invalid CLI usage |
| 3 | Configuration or workspace error |
| 4 | Invalid case or source STL |
| 5 | Blender inspection or rendering failure |
| 6 | Invalid workflow state or schema document |
| 7 | Quality threshold not met within iteration limit |
| 8 | Partial multi-case command failure |

Exact error codes must be stable and documented independently from process exit codes.

## 27. Observability

The CLI must maintain append-only JSON Lines events for each session. Events should include:

- Timestamp.
- Event type.
- Case ID.
- Session ID.
- Iteration number when applicable.
- Tool version.
- Structured payload.

Expected events include:

- `session.created`
- `inspection.started`
- `inspection.completed`
- `iteration.created`
- `render.started`
- `render.completed`
- `render.failed`
- `review.recorded`
- `adjustment.applied`
- `session.completed`
- `session.quality_not_met`
- `session.failed`

Human-readable Rich output is not a substitute for durable structured records.

## 28. Performance expectations

The MVP prioritizes correctness and determinism over throughput.

- Case listing and validation should complete without launching Blender.
- Blender should launch only for operations that require import or rendering.
- A single command must enforce configured Blender timeout.
- The host process must capture exit code, stdout, and stderr without deadlocking.
- Batch case validation must continue after one invalid case.
- Parallel rendering is out of scope.

No strict render-duration SLA is defined because performance depends heavily on STL complexity and host hardware.

## 29. Testing requirements

### 29.1 Unit tests

Cover at minimum:

- Workspace discovery.
- Safe path resolution.
- Case discovery and classification.
- Configuration parsing.
- Managed-block merging.
- Transactional init planning.
- Adjustment allowlists and bounds.
- Review validation.
- Session state transitions.
- Iteration numbering.
- Finalization preconditions.
- JSON output envelopes.

### 29.2 Integration tests without Blender

Use a fake Blender executable or subprocess adapter to test:

- Invocation arguments.
- Timeout behavior.
- Exit-code mapping.
- Manifest and result handling.
- stdout/stderr capture.
- Failure recovery.

### 29.3 Blender integration tests

When Blender is available, test:

- STL import.
- Geometry inspection.
- Deterministic scene reset.
- Generation of every required view.
- Image dimensions.
- Camera framing for representative fixtures.
- No writes outside the provided output directory.

Large or sensitive clinical STL fixtures must not be committed. Tests should use synthetic or properly licensed minimal meshes.

### 29.4 End-to-end acceptance fixture

Provide at least one non-sensitive synthetic dental-arch-like STL fixture or a generated mesh fixture. An end-to-end test should:

1. Initialize a temporary workspace.
2. Add one case.
3. Validate and inspect it.
4. Start a session.
5. Produce the initial render.
6. Record a retry review.
7. Apply a valid adjustment.
8. Produce a second iteration.
9. Record an accept review.
10. Finalize with a description.
11. Verify all expected files and terminal state.

## 30. MVP acceptance criteria

The MVP is complete when all of the following are true:

### Workspace

- `stl-analyzer init` works with omitted path, `.`, relative paths, and absolute paths.
- Init is non-destructive, repeatable, and conflict-safe.
- The generated workspace contains valid config and agent instructions.

### Cases

- Cases are discovered from immediate child directories.
- Exactly one root-level STL is enforced.
- Source STL mutation is prevented by design and tests.

### Blender

- `doctor` detects Blender availability and support.
- `inspect` writes valid geometry metadata.
- The default preset renders every required image headlessly.

### Iteration loop

- Sessions persist across commands.
- An agent can record a review and apply a bounded adjustment.
- Each render creates an immutable iteration.
- The maximum iteration count is enforced.
- `status --json` always identifies the next valid action.

### Finalization

- Only an accepted iteration can be finalized.
- Final artifacts are written under `assets/final/`.
- The final result links to source, session, iteration, review, description, and images.

### Agent interoperability

- The generated `SKILL.md` describes a complete zero-HITL loop.
- `AGENTS.md` and `CLAUDE.md` point to the canonical instructions.
- Core agent-facing commands return clean JSON.

### Quality

- The full test suite passes.
- Ruff formatting and linting pass.
- mypy passes for the configured source set.
- Documentation matches implemented command behavior.

## 31. Deferred roadmap

Potential post-MVP work includes:

- Multiple STL roles per case: upper, lower, bite, preparation, antagonist.
- Full-set scan manifests.
- PLY and OBJ input.
- Scan-role detection.
- More dental render presets.
- Geometry-based automatic orientation.
- Deterministic image-quality metrics.
- Agent-independent workflow adapters.
- Batch queues and parallel execution.
- Optional local vision-model integration as a separate package.
- Versioned migration of generated workspace files.
- Plugin or skill packaging for specific agent ecosystems.

These items must not expand MVP scope unless the PRD is explicitly revised.