"""Inspect command — geometry inspection for a case (MVP-0505)."""

from __future__ import annotations

from typing import Annotated

import typer

from stl_analyzer.blender.adapter import SubprocessBlenderAdapter
from stl_analyzer.errors import DomainError, internal_error
from stl_analyzer.output.rendering import emit_error_json, emit_success_json, render_human_error
from stl_analyzer.services.inspection_service import InspectionService
from stl_analyzer.services.workspace import WorkspaceService


def inspect_case(
    ctx: typer.Context,
    case_id: Annotated[str, typer.Argument(help="Case ID to inspect.")],
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-inspect even when a valid cached result exists."),
    ] = False,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """Inspect STL geometry for a case using headless Blender."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    try:
        svc = WorkspaceService()
        workspace = svc.find_workspace()
        config = svc.load_config(workspace)

        adapter = SubprocessBlenderAdapter()
        inspection = InspectionService(adapter)

        result, cache_hit = inspection.inspect(
            workspace_root=workspace,
            config=config,
            case_id=case_id,
            force=force,
        )

        if json_mode:
            emit_success_json(
                {
                    "case_id": case_id,
                    "cache_hit": cache_hit,
                    "geometry": result.model_dump(mode="json"),
                }
            )
        else:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            status = "[dim]cached[/dim]" if cache_hit else "[green]inspected[/green]"
            console.print(f"Geometry inspection for [bold]{case_id}[/bold]: {status}")

            table = Table(show_header=False)
            table.add_column("Field", style="cyan")
            table.add_column("Value")
            table.add_row("Vertices", str(result.vertex_count))
            table.add_row("Polygons", str(result.polygon_count))
            table.add_row("Objects", str(result.object_count))
            if result.component_count is not None:
                table.add_row("Components", str(result.component_count))
            table.add_row(
                "Bounding box",
                f"min={result.bounding_box.min}  max={result.bounding_box.max}",
            )
            table.add_row(
                "Dimensions",
                " × ".join(f"{d:.2f}" for d in result.dimensions) + f" {result.assumed_unit}",
            )
            table.add_row("Center", str([round(c, 2) for c in result.center]))
            table.add_row("Blender", result.blender_version)
            console.print(table)

            if result.warnings:
                for w in result.warnings:
                    console.print(f"[yellow]⚠[/yellow]  {w}")

    except DomainError as exc:
        if json_mode:
            emit_error_json(exc.to_envelope())
        else:
            render_human_error(exc.message, details=exc.details)
        raise typer.Exit(code=int(exc.exit_code)) from exc
    except BaseException as exc:
        mapped = internal_error(exc, verbose=verbose)
        if json_mode:
            emit_error_json(mapped.to_envelope())
        else:
            render_human_error(mapped.message)
        raise typer.Exit(code=int(mapped.exit_code)) from exc
