"""Session sub-commands: start (MVP-0706)."""

from __future__ import annotations

from typing import Annotated

import typer

from stl_analyzer.blender.adapter import SubprocessBlenderAdapter
from stl_analyzer.errors import DomainError, internal_error
from stl_analyzer.output.rendering import emit_error_json, emit_success_json, render_human_error
from stl_analyzer.services.session_start_service import SessionStartService
from stl_analyzer.services.workspace import WorkspaceService

session_app = typer.Typer(help="Manage render sessions for a case.")


@session_app.command("start")
def session_start(
    ctx: typer.Context,
    case_id: Annotated[str, typer.Argument(help="Case ID to start a session for.")],
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """Start a new render session: inspect geometry, render iteration 1, enter awaiting_review."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    try:
        svc = WorkspaceService()
        workspace = svc.find_workspace()
        config = svc.load_config(workspace)

        adapter = SubprocessBlenderAdapter()
        start_svc = SessionStartService(blender_adapter=adapter)

        result = start_svc.start(
            workspace_root=workspace,
            config=config,
            case_id=case_id,
        )

        if json_mode:
            emit_success_json(
                {
                    "case_id": case_id,
                    "session_id": result.session_id,
                    "iteration": result.iteration,
                    "state": result.state.value,
                    "image_paths": result.image_paths,
                    "warnings": result.render_result.warnings,
                }
            )
        else:
            from rich.console import Console

            console = Console()
            console.print(
                f"Session [bold]{result.session_id}[/bold] started for case [bold]{case_id}[/bold]."
            )
            console.print(
                f"  Iteration [bold]{result.iteration:03d}[/bold] rendered → "
                f"[green]{result.state.value}[/green]"
            )
            for path in result.image_paths:
                console.print(f"  [dim]{path}[/dim]")
            if result.render_result.warnings:
                for w in result.render_result.warnings:
                    console.print(f"  [yellow]⚠[/yellow]  {w}")
            console.print(
                "\nNext: inspect the images above and record a review with 'iterations review'."
            )

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
