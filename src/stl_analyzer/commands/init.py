"""Implementation of ``stl-analyzer init``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from stl_analyzer.errors import DomainError, internal_error
from stl_analyzer.output.rendering import (
    emit_error_json,
    emit_success_json,
    render_human_error,
    render_init_success,
)
from stl_analyzer.services.init_service import InitService


def init_workspace(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Directory to initialize. Defaults to the current working directory.",
            show_default=False,
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """Initialize an agent-ready workspace, not the CLI source repository."""

    verbose = bool((ctx.obj or {}).get("verbose", False))
    service = InitService()
    try:
        result = service.initialize(path)
    except DomainError as exc:
        _render_failure(exc, json_output=json_output)
        raise typer.Exit(code=int(exc.exit_code)) from exc
    except BaseException as exc:
        mapped = internal_error(exc, verbose=verbose)
        _render_failure(mapped, json_output=json_output)
        raise typer.Exit(code=int(mapped.exit_code)) from exc

    if json_output:
        emit_success_json(result.model_dump(mode="json"))
    else:
        render_init_success(result)


def _render_failure(error: DomainError, *, json_output: bool) -> None:
    if json_output:
        emit_error_json(error.to_envelope())
    else:
        details: dict[str, Any] = error.details
        render_human_error(error.message, details=details)
