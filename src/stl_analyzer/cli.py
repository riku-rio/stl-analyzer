"""Top-level Typer application."""

from __future__ import annotations

from typing import Annotated

import typer

from stl_analyzer import __version__
from stl_analyzer.commands.init import init_workspace

app = typer.Typer(
    name="stl-analyzer",
    help="Deterministic local execution layer for agent-driven dental STL workflows.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Include additional safe diagnostic details."),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = False,
) -> None:
    """Configure global non-interactive CLI behavior."""

    del version
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


app.command("init")(init_workspace)
