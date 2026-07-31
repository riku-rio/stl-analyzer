"""Configuration sub-commands: show and validate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from stl_analyzer.errors import DomainError, internal_error
from stl_analyzer.output.rendering import emit_error_json, emit_success_json, render_human_error
from stl_analyzer.services.workspace import WorkspaceService

config_app = typer.Typer(help="Inspect and validate workspace configuration.")


def _render_failure(error: DomainError, *, json_mode: bool) -> None:
    if json_mode:
        emit_error_json(error.to_envelope())
    else:
        details: dict[str, Any] = error.details
        render_human_error(error.message, details=details)


@config_app.command("show")
def show_config(
    ctx: typer.Context,
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            help="Explicit path to the workspace root directory.",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """Show the effective workspace configuration."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    try:
        service = WorkspaceService()
        workspace = service.find_workspace(project_root)
        config = service.load_config(workspace)

        if json_mode:
            emit_success_json({"config": config.model_dump()})
        else:
            from rich.console import Console
            from rich.syntax import Syntax

            console = Console()
            toml_str = ""
            for k, v in config.model_dump().items():
                if isinstance(v, dict):
                    toml_str += f"\n[{k}]\n"
                    for sk, sv in v.items():
                        if isinstance(sv, list):
                            toml_str += f"{sk} = {json.dumps(sv)}\n"
                        elif isinstance(sv, bool):
                            toml_str += f"{sk} = {'true' if sv else 'false'}\n"
                        elif isinstance(sv, str):
                            toml_str += f'{sk} = "{sv}"\n'
                        else:
                            toml_str += f"{sk} = {sv}\n"
                else:
                    toml_str += f'{k} = "{v}"\n'

            syntax = Syntax(toml_str.strip(), "toml", theme="monokai", word_wrap=True)
            console.print(syntax)

    except DomainError as exc:
        _render_failure(exc, json_mode=json_mode)
        raise typer.Exit(code=int(exc.exit_code)) from exc
    except BaseException as exc:
        mapped = internal_error(exc, verbose=verbose)
        _render_failure(mapped, json_mode=json_mode)
        raise typer.Exit(code=int(mapped.exit_code)) from exc


@config_app.command("validate")
def validate_config(
    ctx: typer.Context,
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            help="Explicit path to the workspace root directory.",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = None,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """Validate workspace configuration without launching Blender."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    try:
        service = WorkspaceService()
        workspace = service.find_workspace(project_root)
        service.load_config(workspace)

        if json_mode:
            emit_success_json({"ok": True, "message": "Configuration is valid."})
        else:
            from rich.console import Console

            Console().print(f"[green]✓[/green] Configuration in {workspace} is valid.")

    except DomainError as exc:
        _render_failure(exc, json_mode=json_mode)
        raise typer.Exit(code=int(exc.exit_code)) from exc
    except BaseException as exc:
        mapped = internal_error(exc, verbose=verbose)
        _render_failure(mapped, json_mode=json_mode)
        raise typer.Exit(code=int(mapped.exit_code)) from exc
