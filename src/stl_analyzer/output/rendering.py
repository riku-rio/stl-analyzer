"""Single-path JSON serialization and Rich human output."""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from stl_analyzer.models.common import ErrorEnvelope, SuccessEnvelope
from stl_analyzer.models.init import InitResult


def emit_json(model: BaseModel) -> None:
    """Write exactly one JSON document to stdout."""

    payload = model.model_dump(mode="json", exclude_none=True)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()


def emit_success_json(data: Any) -> None:
    """Emit the common success envelope."""

    emit_json(SuccessEnvelope(data=data))


def emit_error_json(error: ErrorEnvelope) -> None:
    """Emit the common failure envelope."""

    emit_json(error)


def render_init_success(result: InitResult) -> None:
    """Render a concise human-readable initialization summary."""

    console = Console()
    console.print(f"Initialized STL Analyzer workspace: [bold]{result.workspace}[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Action")
    table.add_column("Path")
    for action in result.actions:
        table.add_row(action.action.value, action.path)
    console.print(table)
    console.print("Next commands:")
    for command in result.next_commands:
        console.print(f"  {command}")


def render_human_error(message: str, *, details: dict[str, Any] | None = None) -> None:
    """Write expected errors to stderr in human mode."""

    console = Console(stderr=True)
    console.print(f"[bold red]Error:[/bold red] {message}")
    if details:
        conflicts = details.get("conflicts")
        if isinstance(conflicts, list):
            for conflict in conflicts:
                if isinstance(conflict, dict):
                    path = conflict.get("path", "?")
                    reason = conflict.get("reason", "Conflict")
                    console.print(f"  - {path}: {reason}")
