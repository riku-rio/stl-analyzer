# STL Analyzer Development

## Requirements

- Python 3.12 or newer
- `uv`
- Blender is intentionally not required for Batch A tests

## Environment

```powershell
uv sync
```

## Run the CLI

```powershell
uv run stl-analyzer --help
uv run stl-analyzer init .
uv run stl-analyzer init C:\Projects\dental-cases --json
```

## Quality checks

Run every check before publishing a change:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Apply formatting locally with:

```powershell
uv run ruff format .
```

Batch A keeps Blender behind an import boundary. Host-side modules and tests must never import `bpy`.
