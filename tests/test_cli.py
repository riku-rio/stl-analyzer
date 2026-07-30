from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from stl_analyzer.cli import app

runner = CliRunner()


def test_root_help_succeeds() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "stl-analyzer" in result.stdout


def test_init_help_succeeds() -> None:
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "workspace" in result.stdout.lower()
    assert "--json" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_json_init_writes_one_document_to_stdout(tmp_path: Path) -> None:
    target = tmp_path / "workspace"
    result = runner.invoke(app, ["init", str(target), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["data"]["workspace"] == str(target.resolve())
    assert result.stderr == ""


def test_json_conflict_uses_common_error_envelope(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("# user content\n", encoding="utf-8")
    result = runner.invoke(app, ["init", str(tmp_path), "--json"])
    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert payload["error"]["code"] == "INIT_CONFLICT"
    assert payload["error"]["recoverable"] is True
    assert result.stderr == ""


def test_human_conflict_writes_error_to_stderr(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("# user content\n", encoding="utf-8")
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 3
    assert "Error:" in result.stderr


def test_module_entrypoint_help() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "stl_analyzer", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "init" in completed.stdout
