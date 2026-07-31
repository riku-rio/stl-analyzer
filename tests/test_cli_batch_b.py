import json

from typer.testing import CliRunner

from stl_analyzer.cli import app
from stl_analyzer.models.common import ExitCode

runner = CliRunner()


def test_config_show_json(tmp_path):
    # Setup workspace
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    result = runner.invoke(app, ["config", "show", "--json", "--project-root", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert "config" in data["data"]


def test_config_show_human(tmp_path):
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    result = runner.invoke(app, ["config", "show", "--project-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "[project]" in result.stdout


def test_config_validate_success(tmp_path):
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    result = runner.invoke(app, ["config", "validate", "--json", "--project-root", str(tmp_path)])
    assert result.exit_code == 0


def test_config_validate_error(tmp_path):
    bad_toml = 'schema_version = "1"\n[blender]\ntimeout_seconds=0\n'
    (tmp_path / "stl-analyzer.toml").write_text(bad_toml)
    result = runner.invoke(app, ["config", "validate", "--json", "--project-root", str(tmp_path)])
    assert result.exit_code == ExitCode.WORKSPACE_ERROR


def test_cases_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    (tmp_path / "stl").mkdir()
    (tmp_path / "stl" / "case1").mkdir()
    (tmp_path / "stl" / "case1" / "file.stl").touch()

    result = runner.invoke(app, ["cases", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data["data"]["cases"]) == 1


def test_cases_validate_all(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    (tmp_path / "stl").mkdir()
    (tmp_path / "stl" / "case1").mkdir()
    (tmp_path / "stl" / "case1" / "file.stl").touch()

    result = runner.invoke(app, ["cases", "validate", "--all", "--json"])
    assert result.exit_code == 0


def test_cases_validate_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    (tmp_path / "stl").mkdir()
    (tmp_path / "stl" / "case1").mkdir()  # missing file

    result = runner.invoke(app, ["cases", "validate", "case1", "--json"])
    assert result.exit_code == ExitCode.INVALID_CASE


def test_doctor_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    (tmp_path / "stl").mkdir()

    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code in (0, ExitCode.WORKSPACE_ERROR)


def test_cases_list_human(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stl-analyzer.toml").write_text('schema_version = "1"\ntemplate_version = "1"\n')
    (tmp_path / "stl").mkdir()

    result = runner.invoke(app, ["cases", "list"])
    assert result.exit_code == 0


def test_doctor_command_human(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in (0, ExitCode.WORKSPACE_ERROR)
