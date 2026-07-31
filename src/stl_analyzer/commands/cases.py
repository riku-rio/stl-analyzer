"""Cases sub-commands: list and validate."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from stl_analyzer.errors import DomainError, internal_error
from stl_analyzer.models.common import ExitCode
from stl_analyzer.output.rendering import emit_error_json, emit_success_json, render_human_error
from stl_analyzer.services.case_service import CaseDiscovery, CaseValidation
from stl_analyzer.services.workspace import WorkspaceService

cases_app = typer.Typer(help="Manage and inspect cases.")


def _render_failure(error: DomainError, *, json_mode: bool) -> None:
    if json_mode:
        emit_error_json(error.to_envelope())
    else:
        details: dict[str, Any] = error.details
        render_human_error(error.message, details=details)


@cases_app.command("list")
def list_cases(
    ctx: typer.Context,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """List discovered cases in the STL root without creating assets."""
    verbose = bool((ctx.obj or {}).get("verbose", False))
    try:
        service = WorkspaceService()
        workspace = service.find_workspace()
        config = service.load_config(workspace)

        discovery = CaseDiscovery()
        cases = discovery.list_cases(
            workspace_root=workspace,
            stl_root=config.project.stl_root,
            scan_config=config.scan,
        )

        if json_mode:
            emit_success_json({"cases": [c.model_dump() for c in cases]})
        else:
            from rich.console import Console
            from rich.table import Table

            table = Table(title="Workspace Cases", show_header=True)
            table.add_column("Case ID", style="cyan")
            table.add_column("State")
            table.add_column("Source File", style="green")
            table.add_column("Path", style="dim")

            for c in cases:
                state_color = "green" if c.state == "ready" else "red"
                table.add_row(
                    c.case_id,
                    f"[{state_color}]{c.state.value}[/{state_color}]",
                    c.source_file or "—",
                    c.path,
                )

            Console().print(table)

    except DomainError as exc:
        _render_failure(exc, json_mode=json_mode)
        raise typer.Exit(code=int(exc.exit_code)) from exc
    except BaseException as exc:
        mapped = internal_error(exc, verbose=verbose)
        _render_failure(mapped, json_mode=json_mode)
        raise typer.Exit(code=int(mapped.exit_code)) from exc


@cases_app.command("validate")
def validate_cases(
    ctx: typer.Context,
    case_id: Annotated[
        str | None,
        typer.Argument(help="Specific case ID to validate."),
    ] = None,
    all_cases: Annotated[
        bool,
        typer.Option("--all", help="Validate all discovered cases."),
    ] = False,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit exactly one machine-readable JSON document."),
    ] = False,
) -> None:
    """Validate one or all cases against the workspace configuration."""
    if not case_id and not all_cases:
        typer.echo("Error: Must specify either a CASE_ID or --all.", err=True)
        raise typer.Exit(code=int(ExitCode.INVALID_CLI_USAGE))

    verbose = bool((ctx.obj or {}).get("verbose", False))
    try:
        service = WorkspaceService()
        workspace = service.find_workspace()
        config = service.load_config(workspace)

        discovery = CaseDiscovery()
        validator = CaseValidation()

        target_ids: list[str]
        if all_cases:
            target_ids = [
                c.case_id
                for c in discovery.list_cases(
                    workspace_root=workspace,
                    stl_root=config.project.stl_root,
                    scan_config=config.scan,
                )
            ]
        else:
            assert case_id is not None
            target_ids = [case_id]

        successes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for cid in target_ids:
            try:
                case = validator.validate_case(
                    workspace_root=workspace,
                    stl_root=config.project.stl_root,
                    assets_directory=config.project.assets_directory,
                    scan_config=config.scan,
                    case_id=cid,
                    test_write=True,
                )
                successes.append({"case_id": cid, "ok": True, "case": case.model_dump()})
            except DomainError as e:
                failures.append(
                    {
                        "case_id": cid,
                        "ok": False,
                        "error": {
                            "code": e.code,
                            "message": e.message,
                            "details": e.details,
                        },
                    }
                )

        all_results = successes + failures
        all_results.sort(key=lambda r: r["case_id"])

        has_failures = bool(failures)

        if json_mode:
            payload = {"ok": not has_failures, "results": all_results}
            if has_failures:
                sys_stdout = json.dumps(
                    {"success": False, "data": payload}, ensure_ascii=False, indent=2
                )
                import sys

                sys.stdout.write(sys_stdout + "\n")
                sys.stdout.flush()
            else:
                emit_success_json(payload)
        else:
            from rich.console import Console

            console = Console()
            for r in all_results:
                if r["ok"]:
                    console.print(f"[green]✓[/green] {r['case_id']}: valid")
                else:
                    err = r["error"]
                    console.print(f"[red]✗[/red] {r['case_id']}: {err['message']}")

        if has_failures:
            raise typer.Exit(
                code=int(ExitCode.PARTIAL_FAILURE if all_cases else ExitCode.INVALID_CASE)
            )

    except typer.Exit:
        raise
    except DomainError as exc:
        _render_failure(exc, json_mode=json_mode)
        raise typer.Exit(code=int(exc.exit_code)) from exc
    except BaseException as exc:
        mapped = internal_error(exc, verbose=verbose)
        _render_failure(mapped, json_mode=json_mode)
        raise typer.Exit(code=int(mapped.exit_code)) from exc
