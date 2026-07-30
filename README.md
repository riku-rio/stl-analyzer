# STL Analyzer

`stl-analyzer` is a local-first Python CLI that gives agentic coding tools such as Codex, Claude Code, and Antigravity a deterministic execution layer for inspecting dental STL scans, rendering them with headless Blender, and iterating on camera and lighting parameters.

The CLI does not contain an AI model or an AI SDK. The coding agent reads `SKILL.md`, runs the CLI, inspects the generated images with its own vision capabilities, records structured reviews, applies bounded render adjustments, and repeats the workflow without human intervention.

> [!NOTE]
> This repository is currently in the MVP planning stage. The product requirements and implementation plan are available under [`docs/mvp/`](docs/mvp/).

## Product model

The system is intentionally split into two responsibilities:

- **The agentic coding tool** plans the workflow, opens screenshots, evaluates visual quality, selects adjustments, writes the final observational description, and decides when the result is acceptable.
- **The `stl-analyzer` CLI** discovers cases, validates inputs, invokes headless Blender, applies validated camera and lighting changes, persists sessions and iterations, and finalizes outputs.

This keeps the CLI deterministic, testable, provider-independent, and usable by different coding agents.

## MVP scope

The MVP supports:

- Python 3.12+ managed with `uv`.
- A Typer-based, non-interactive CLI.
- One dental STL file per case folder.
- Local headless Blender inspection and rendering.
- Structured render sessions and immutable iterations.
- Bounded camera and lighting adjustments supplied by the coding agent.
- Machine-readable JSON output for every agent-facing command.
- Persistent reviews, status, and final results.
- A canonical `SKILL.md` workflow for coding agents.
- Zero Human-in-the-Loop intervention during an active workflow.

The MVP does not include an AI SDK, embedded vision provider, web UI, cloud queue, database, DICOM support, STL geometry editing, or multi-scan/full-set cases.

## Planned technology stack

- **Python 3.12+** for the CLI and application code.
- **uv** for Python version, dependency, environment, and lockfile management.
- **Typer** for the command-line interface.
- **Pydantic** for configuration, manifests, reviews, adjustments, state, and output schemas.
- **Rich** for human-readable terminal output.
- **Blender Python API (`bpy`)** inside Blender's bundled Python runtime.
- **pytest**, **Ruff**, and **mypy** for testing and quality checks.

The project will not install `bpy` into the `uv` environment. Blender-specific scripts will be executed by the Blender executable in background mode.

## Workspace initialization

After the CLI is installed, initialize the current directory:

```powershell
stl-analyzer init .
```

Or initialize another directory without changing the current working directory:

```powershell
stl-analyzer init C:\Projects\dental-cases
```

`PATH` defaults to the current directory, so this is also valid:

```powershell
stl-analyzer init
```

The command initializes an agent-ready workspace rather than scaffolding the `stl-analyzer` source repository itself.

Planned output:

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

Initialization is designed to be transactional, non-destructive, and idempotent:

- Missing target directories are created.
- Existing STL cases are never deleted or rewritten.
- Existing `.gitignore`, `AGENTS.md`, and `CLAUDE.md` files receive managed sections instead of full replacement.
- A conflicting unmanaged `SKILL.md` causes initialization to stop before any files are changed.
- Re-running the command against an initialized workspace reports files as unchanged.

`init` does not install Blender or Python, create sample STL files, create case `assets/` directories, start a render session, or invoke AI.

## Case layout

Each immediate child directory of the configured STL root is one case. The folder name is the case ID.

```text
stl/
├── case-001/
│   └── upper.stl
└── case-002/
    └── scan.stl
```

MVP rules:

- A case contains exactly one `.stl` file at its root.
- The STL filename is not semantically significant.
- STL discovery is not recursive.
- The source STL is read-only.
- Generated files belong under the case's `assets/` directory.
- The CLI creates `assets/` when the case first needs persistent generated state.

A case with generated state will resemble:

```text
stl/case-001/
├── upper.stl
└── assets/
    ├── geometry.json
    ├── state.json
    ├── sessions/
    │   └── <session-id>/
    │       ├── session.json
    │       ├── events.jsonl
    │       └── iterations/
    │           ├── 001/
    │           │   ├── render.json
    │           │   ├── review.json
    │           │   └── images/
    │           └── 002/
    │               ├── adjustment.json
    │               ├── render.json
    │               ├── review.json
    │               └── images/
    └── final/
        ├── result.json
        ├── clinical-description.md
        ├── render.json
        └── images/
```

## Planned CLI surface

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

Agent-facing invocations should use `--json` whenever available:

```powershell
stl-analyzer doctor --json
stl-analyzer cases list --json
stl-analyzer status case-001 --json
```

All commands are non-interactive. Missing input, invalid state, and unsafe operations must fail with structured errors rather than waiting for human confirmation.

## Autonomous agent workflow

The canonical loop will be defined in the generated `SKILL.md`:

1. Run `doctor` and resolve deterministic environment failures.
2. Discover and validate the requested case.
3. Inspect its STL geometry.
4. Start a session and create the initial render.
5. Open every generated image.
6. Evaluate framing, orientation, coverage, lighting, contrast, clipping, and visible detail.
7. Record a structured review.
8. When quality is insufficient, create a bounded adjustment file and render a new iteration.
9. Repeat until an iteration is acceptable or the maximum iteration count is reached.
10. Select the best accepted iteration.
11. Write an observational description with explicit limitations and no unsupported diagnosis.
12. Finalize the case and verify `result.json` reports a completed state.

The agent must not ask a human to choose camera or lighting changes during this loop.

## Documentation

- [`docs/mvp/PRD.md`](docs/mvp/PRD.md) — complete MVP product requirements and acceptance criteria.
- [`docs/mvp/TASKS.md`](docs/mvp/TASKS.md) — ordered implementation plan with dependencies and completion criteria.

## Safety and privacy

The MVP is local-first and should not transmit STL files or rendered images to a service on its own. The selected coding agent may have its own data-handling behavior, so users remain responsible for configuring that tool appropriately.

Case IDs and filenames should avoid patient-identifying information. Generated descriptions are observational aids, not diagnoses or treatment recommendations.

## License

A license has not yet been selected.