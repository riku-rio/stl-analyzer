"""Implementation of ``stl-analyzer doctor``."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from stl_analyzer.errors import DomainError, internal_error
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.diagnostics import DiagnosticStatus
from stl_analyzer.output.rendering import emit_error_json, emit_success_json
from stl_analyzer.services.doctor_service import DoctorService


def _render_failure(error: DomainError, *, json_mode: bool) -> None:
    if json_mode:
        emit_error_json(error.to_envelope())
    else:
        from rich.console import Console

        details: dict[str, Any] = error.details
        Console(stderr=True).print(f"[bold red]Error:[/bold red] {error.message} {details}")


def run_doctor(
    ctx: typer.Context,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """Run diagnostics to verify workspace, configuration, and environment."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    try:
        service = DoctorService()
        result = service.run_diagnostics()

        if json_mode:
            emit_success_json(result.model_dump())
        else:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            table = Table(title="Diagnostic Checks", show_header=True)
            table.add_column("Status", justify="center")
            table.add_column("Check")
            table.add_column("Message")
            table.add_column("Remediation", style="dim")

            for check in result.checks:
                if check.status == DiagnosticStatus.PASSED:
                    status = "[green]✓[/green]"
                elif check.status == DiagnosticStatus.WARNING:
                    status = "[yellow]⚠[/yellow]"
                elif check.status == DiagnosticStatus.FAILED:
                    status = "[red]✗[/red]"
                else:
                    status = "[dim]-[/dim]"

                table.add_row(
                    status,
                    check.name,
                    check.message,
                    check.remediation or "",
                )

            console.print(table)

        if not result.ok:
            raise typer.Exit(code=int(ExitCode.WORKSPACE_ERROR))

    except typer.Exit:
        raise
    except DomainError as exc:
        _render_failure(exc, json_mode=json_mode)
        raise typer.Exit(code=int(exc.exit_code)) from exc
    except BaseException as exc:
        mapped = internal_error(exc, verbose=verbose)
        _render_failure(mapped, json_mode=json_mode)
        raise typer.Exit(code=int(mapped.exit_code)) from exc
