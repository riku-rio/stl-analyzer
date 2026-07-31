import pytest

from stl_analyzer.errors import DomainError
from stl_analyzer.models.common import ExitCode
from stl_analyzer.services.workspace import WorkspaceService


def test_workspace_discovery_success(tmp_path):
    (tmp_path / "stl-analyzer.toml").touch()

    service = WorkspaceService()
    workspace = service.find_workspace(start_path=tmp_path)
    assert workspace == tmp_path.resolve()


def test_workspace_discovery_not_found(tmp_path):
    service = WorkspaceService()
    with pytest.raises(DomainError) as exc:
        service.find_workspace(start_path=tmp_path)

    assert exc.value.exit_code == ExitCode.WORKSPACE_ERROR


def test_config_loading_success(tmp_path):
    config_file = tmp_path / "stl-analyzer.toml"
    config_file.write_text(
        'schema_version = "1"\n'
        'template_version = "1"\n'
        "[project]\n"
        'stl_root = "test_stl"\n'
        "[blender]\n"
        'executable = "test_blender"\n'
    )

    service = WorkspaceService()
    config = service.load_config(tmp_path)

    assert config.project.stl_root == "test_stl"
    assert config.blender.executable == "test_blender"


def test_config_loading_missing(tmp_path):
    service = WorkspaceService()
    with pytest.raises(DomainError) as exc:
        service.load_config(tmp_path)
    assert exc.value.code == "CONFIG_MISSING"


def test_config_loading_invalid_toml(tmp_path):
    config_file = tmp_path / "stl-analyzer.toml"
    config_file.write_text("[project\n")  # Missing closing bracket

    service = WorkspaceService()
    with pytest.raises(DomainError) as exc:
        service.load_config(tmp_path)
    assert exc.value.code == "CONFIG_PARSE_ERROR"


def test_config_loading_validation_error(tmp_path):
    config_file = tmp_path / "stl-analyzer.toml"
    config_file.write_text(
        'schema_version = "1"\n[blender]\ntimeout_seconds = 0\n'  # Should be >= 1
    )

    service = WorkspaceService()
    with pytest.raises(DomainError) as exc:
        service.load_config(tmp_path)
    assert exc.value.code == "CONFIG_VALIDATION_ERROR"
    assert "timeout_seconds" in exc.value.details["issues"][0]
