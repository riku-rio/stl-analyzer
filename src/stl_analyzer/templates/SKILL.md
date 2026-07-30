<!-- stl-analyzer:managed-skill template-version=1 -->
# STL Analyzer Agent Workflow

Use `stl-analyzer` as the deterministic execution layer for every STL case in this workspace. The CLI performs validation, Blender execution, bounded render changes, and state persistence. You remain responsible for planning, opening images, visual evaluation, adjustment selection, acceptance, and the final observational description.

## Safety rules

- Never modify, rename, overwrite, or delete a source STL file.
- Never edit generated manifests, session state, reviews, or results manually.
- Never replace the CLI workflow with arbitrary Blender or Python code.
- Never request human guidance for camera or lighting choices during an active workflow.
- Never invent clinical findings, measurements, diagnoses, or treatment recommendations.
- Avoid patient-identifying information in case IDs, filenames, logs, and descriptions.

## Required autonomous workflow

1. Run `stl-analyzer doctor --json` and resolve deterministic environment failures.
2. Run `stl-analyzer cases list --json` and identify the requested case.
3. Run `stl-analyzer cases validate <CASE_ID> --json`.
4. Run `stl-analyzer inspect <CASE_ID> --json`.
5. Start or resume the case session according to `stl-analyzer status <CASE_ID> --json`.
6. Open every generated image for the current iteration.
7. Evaluate framing, orientation, scan coverage, lighting, contrast, clipping, and visible surface detail.
8. Persist one schema-valid review for the iteration.
9. When quality is insufficient, create only an allowlisted bounded adjustment document and render the next iteration.
10. Repeat without human intervention until an iteration is accepted or the configured iteration limit is reached.
11. Select only an accepted iteration and write an observational description that clearly states visible findings and limitations.
12. Finalize the case and verify that `result.json` reports completion.

Treat `quality_not_met` and deterministic unrecoverable failures as terminal outcomes. Report them clearly instead of asking a human to choose a view, camera, or lighting change.

## Workspace layout

Each immediate child of `stl/` is one case and must contain exactly one root-level `.stl` file for the MVP. Generated artifacts belong only under that case's `assets/` directory.
