from stl_analyzer.models.diagnostics import DiagnosticStatus
from stl_analyzer.services.doctor_service import DoctorService


def test_doctor_success(tmp_path, monkeypatch):
    # Setup workspace
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    config_file = workspace / "stl-analyzer.toml"
    config_file.write_text(
        'schema_version = "1"\n'
        'template_version = "1"\n'
        "[project]\n"
        'stl_root = "stl"\n'
        "[blender]\n"
        'executable = "python"\n'  # use python to fake blender execution
    )

    stl_root = workspace / "stl"
    stl_root.mkdir()

    # chdir into workspace so WorkspaceService.find_workspace() can find it
    monkeypatch.chdir(workspace)

    service = DoctorService()

    # Check individual methods
    ok_ws, ws_path, check_ws = service.check_workspace()
    assert ok_ws
    assert check_ws.status == DiagnosticStatus.PASSED

    ok_cfg, check_cfg = service.check_config(ws_path)
    assert ok_cfg
    assert check_cfg.status == DiagnosticStatus.PASSED

    check_stl = service.check_stl_root(ws_path)
    assert check_stl.status == DiagnosticStatus.PASSED

    check_write = service.check_workspace_write(ws_path)
    assert check_write.status == DiagnosticStatus.PASSED

    # We fake blender by just checking if it runs and what its version is.
    # Our python executable won't say "Blender 4.0", so it should fail the version check but run
    check_blender = service.check_blender(ws_path)
    assert check_blender.status == DiagnosticStatus.FAILED
    assert "Unsupported Blender version" in check_blender.message

    # But since it failed one check, overall it should not be ok
    result = service.run_diagnostics()
    assert not result.ok


def test_doctor_no_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    service = DoctorService()
    result = service.run_diagnostics()

    assert not result.ok

    # Find workspace check should fail
    ws_check = next(c for c in result.checks if c.name == "Workspace Discovery")
    assert ws_check.status == DiagnosticStatus.FAILED

    # Following checks should skip
    cfg_check = next(c for c in result.checks if c.name == "Configuration")
    assert cfg_check.status == DiagnosticStatus.SKIPPED
