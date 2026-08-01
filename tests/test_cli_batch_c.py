"""CLI integration tests for inspect and session commands (MVP-0505, MVP-0706)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from stl_analyzer.cli import app

# ──────────────────────────── helpers ────────────────────────────────────────


def _make_workspace(tmp_path: Path, case_id: str = "case-001") -> Path:
    config_toml = (
        '[project]\nstl_root = "stl"\nassets_directory = "assets"\n\n'
        '[blender]\nexecutable = "blender"\ntimeout_seconds = 30\n\n'
        '[scan]\nallowed_extensions = [".stl"]\nmaximum_files_per_case = 1\n'
        'assumed_unit = "millimeters"\n\n'
        '[render]\nwidth = 512\nheight = 512\nengine = "BLENDER_EEVEE_NEXT"\n'
        'default_preset = "dental_arch"\n\n'
        "[workflow]\nmaximum_iterations = 6\n"
        'required_views = ["occlusal", "anterior"]\n\n'
        "[output]\nretain_all_iterations = true\nwrite_event_log = true\n"
    )
    (tmp_path / "stl-analyzer.toml").write_text(config_toml, encoding="utf-8")
    case_dir = tmp_path / "stl" / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "model.stl").write_bytes(b"solid fake\nendsolid fake\n")
    return tmp_path


runner = CliRunner()


def _mock_inspect_result() -> MagicMock:
    from stl_analyzer.models.geometry import BoundingBox, InspectionResult

    result = InspectionResult(
        tool_version="0.1.0",
        case_id="case-001",
        source_path="/fake/model.stl",
        source_sha256="a" * 64,
        source_size_bytes=22,
        blender_version="4.1.0",
        vertex_count=8,
        polygon_count=12,
        object_count=1,
        component_count=1,
        bounding_box=BoundingBox(min=[-10.0, -10.0, -5.0], max=[10.0, 10.0, 5.0]),
        dimensions=[20.0, 20.0, 10.0],
        center=[0.0, 0.0, 0.0],
        assumed_unit="millimeters",
        warnings=[],
        inspection_timestamp="2026-01-01T00:00:00Z",
    )
    return result


# ──────────────────────────── inspect command ─────────────────────────────────


class TestInspectCommand:
    def test_inspect_json_success(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        result_obj = _mock_inspect_result()

        with (
            patch("stl_analyzer.commands.inspect.InspectionService") as MockService,
            patch("stl_analyzer.commands.inspect.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock(
                project=MagicMock(stl_root="stl", assets_directory="assets"),
                blender=MagicMock(executable="blender", timeout_seconds=30),
                scan=MagicMock(
                    allowed_extensions=[".stl"],
                    maximum_files_per_case=1,
                    assumed_unit="millimeters",
                ),
            )
            MockService.return_value.inspect.return_value = (result_obj, False)

            result = runner.invoke(app, ["inspect", "case-001", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["case_id"] == "case-001"
        assert data["data"]["cache_hit"] is False

    def test_inspect_json_cache_hit(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        result_obj = _mock_inspect_result()

        with (
            patch("stl_analyzer.commands.inspect.InspectionService") as MockService,
            patch("stl_analyzer.commands.inspect.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockService.return_value.inspect.return_value = (result_obj, True)

            result = runner.invoke(app, ["inspect", "case-001", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["data"]["cache_hit"] is True

    def test_inspect_human_success(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        result_obj = _mock_inspect_result()

        with (
            patch("stl_analyzer.commands.inspect.InspectionService") as MockService,
            patch("stl_analyzer.commands.inspect.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockService.return_value.inspect.return_value = (result_obj, False)

            result = runner.invoke(app, ["inspect", "case-001"])

        assert result.exit_code == 0
        assert "case-001" in result.output

    def test_inspect_domain_error_json(self, tmp_path: Path) -> None:
        from stl_analyzer.errors import DomainError
        from stl_analyzer.models.common import ExitCode

        workspace = _make_workspace(tmp_path)

        with (
            patch("stl_analyzer.commands.inspect.InspectionService") as MockService,
            patch("stl_analyzer.commands.inspect.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockService.return_value.inspect.side_effect = DomainError(
                code="BLENDER_TIMEOUT",
                message="Timed out.",
                exit_code=ExitCode.BLENDER_FAILURE,
            )

            result = runner.invoke(app, ["inspect", "case-001", "--json"])

        assert result.exit_code == int(ExitCode.BLENDER_FAILURE)
        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == "BLENDER_TIMEOUT"

    def test_inspect_human_error(self, tmp_path: Path) -> None:
        from stl_analyzer.errors import DomainError
        from stl_analyzer.models.common import ExitCode

        with patch("stl_analyzer.commands.inspect.WorkspaceService") as MockWS:
            MockWS.return_value.find_workspace.side_effect = DomainError(
                code="WORKSPACE_NOT_FOUND",
                message="No workspace found.",
                exit_code=ExitCode.WORKSPACE_ERROR,
            )
            result = runner.invoke(app, ["inspect", "case-001"])

        assert result.exit_code == int(ExitCode.WORKSPACE_ERROR)

    def test_inspect_with_warnings(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        result_obj = _mock_inspect_result()
        # Add a warning to the result
        result_obj = result_obj.model_copy(update={"warnings": ["Something unusual."]})

        with (
            patch("stl_analyzer.commands.inspect.InspectionService") as MockService,
            patch("stl_analyzer.commands.inspect.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockService.return_value.inspect.return_value = (result_obj, False)

            result = runner.invoke(app, ["inspect", "case-001"])

        assert result.exit_code == 0
        assert "Something unusual." in result.output

    def test_inspect_force_flag(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        result_obj = _mock_inspect_result()

        with (
            patch("stl_analyzer.commands.inspect.InspectionService") as MockService,
            patch("stl_analyzer.commands.inspect.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockService.return_value.inspect.return_value = (result_obj, False)

            result = runner.invoke(app, ["inspect", "case-001", "--force"])

        assert result.exit_code == 0
        # Verify force=True was passed
        call_kwargs = MockService.return_value.inspect.call_args.kwargs
        assert call_kwargs.get("force") is True


# ──────────────────────────── session command ─────────────────────────────────


class TestSessionCommand:
    def _mock_session_result(self) -> MagicMock:
        from stl_analyzer.models.render_manifest import RenderResult
        from stl_analyzer.models.session import SessionState
        from stl_analyzer.services.session_start_service import SessionStartResult

        render_result = MagicMock(spec=RenderResult)
        render_result.warnings = []
        render_result.images = []

        return SessionStartResult(
            session_id="20260101T000000Z-abcd",
            iteration=1,
            state=SessionState.AWAITING_REVIEW,
            image_paths=["stl/case-001/assets/sessions/s/iter/001/images/occlusal.png"],
            render_result=render_result,
            from_cache=False,
        )

    def test_session_start_json_success(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)

        with (
            patch("stl_analyzer.commands.session.SessionStartService") as MockSvc,
            patch("stl_analyzer.commands.session.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockSvc.return_value.start.return_value = self._mock_session_result()

            result = runner.invoke(app, ["session", "start", "case-001", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["data"]["session_id"] == "20260101T000000Z-abcd"
        assert data["data"]["iteration"] == 1
        assert data["data"]["state"] == "awaiting_review"

    def test_session_start_human_output(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)

        with (
            patch("stl_analyzer.commands.session.SessionStartService") as MockSvc,
            patch("stl_analyzer.commands.session.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockSvc.return_value.start.return_value = self._mock_session_result()

            result = runner.invoke(app, ["session", "start", "case-001"])

        assert result.exit_code == 0
        assert "20260101T000000Z-abcd" in result.output
        assert "case-001" in result.output

    def test_session_start_active_session_error(self, tmp_path: Path) -> None:
        from stl_analyzer.errors import DomainError
        from stl_analyzer.models.common import ExitCode

        workspace = _make_workspace(tmp_path)

        with (
            patch("stl_analyzer.commands.session.SessionStartService") as MockSvc,
            patch("stl_analyzer.commands.session.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockSvc.return_value.start.side_effect = DomainError(
                code="ACTIVE_SESSION_EXISTS",
                message="An active session already exists.",
                exit_code=ExitCode.INVALID_WORKFLOW_STATE,
                recoverable=True,
            )

            result = runner.invoke(app, ["session", "start", "case-001", "--json"])

        assert result.exit_code == int(ExitCode.INVALID_WORKFLOW_STATE)
        data = json.loads(result.stdout)
        assert data["success"] is False
        assert data["error"]["code"] == "ACTIVE_SESSION_EXISTS"

    def test_session_start_internal_error(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)

        with (
            patch("stl_analyzer.commands.session.SessionStartService") as MockSvc,
            patch("stl_analyzer.commands.session.WorkspaceService") as MockWS,
        ):
            MockWS.return_value.find_workspace.return_value = workspace
            MockWS.return_value.load_config.return_value = MagicMock()
            MockSvc.return_value.start.side_effect = RuntimeError("Unexpected error")

            result = runner.invoke(app, ["session", "start", "case-001", "--json"])

        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["success"] is False

    def test_session_help(self) -> None:
        result = runner.invoke(app, ["session", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
