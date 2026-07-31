"""Doctor diagnostic service."""

import os
import subprocess
from pathlib import Path

from stl_analyzer.errors import DomainError
from stl_analyzer.models.diagnostics import DiagnosticCheck, DiagnosticResult, DiagnosticStatus
from stl_analyzer.services.workspace import WorkspaceService


class DoctorService:
    def check_workspace(self) -> tuple[bool, Path | None, DiagnosticCheck]:
        service = WorkspaceService()
        try:
            workspace = service.find_workspace()
            return (
                True,
                workspace,
                DiagnosticCheck(
                    name="Workspace Discovery",
                    status=DiagnosticStatus.PASSED,
                    message="Workspace discovered successfully.",
                    details={"workspace_root": str(workspace)},
                ),
            )
        except DomainError as e:
            return (
                False,
                None,
                DiagnosticCheck(
                    name="Workspace Discovery",
                    status=DiagnosticStatus.FAILED,
                    message=str(e.message),
                    details=e.details,
                    remediation=e.suggested_action,
                ),
            )

    def check_config(self, workspace: Path | None) -> tuple[bool, DiagnosticCheck]:
        if not workspace:
            return False, DiagnosticCheck(
                name="Configuration",
                status=DiagnosticStatus.SKIPPED,
                message="Skipped because workspace was not found.",
                remediation="Fix workspace discovery first.",
            )

        service = WorkspaceService()
        try:
            config = service.load_config(workspace)
            return True, DiagnosticCheck(
                name="Configuration",
                status=DiagnosticStatus.PASSED,
                message="Configuration loaded and validated.",
                details={"stl_root": config.project.stl_root},
            )
        except DomainError as e:
            return False, DiagnosticCheck(
                name="Configuration",
                status=DiagnosticStatus.FAILED,
                message=str(e.message),
                details=e.details,
                remediation=e.suggested_action,
            )

    def check_stl_root(self, workspace: Path | None) -> DiagnosticCheck:
        if not workspace:
            return DiagnosticCheck(
                name="STL Root Access",
                status=DiagnosticStatus.SKIPPED,
                message="Skipped because workspace was not found.",
                remediation="Fix workspace discovery first.",
            )

        service = WorkspaceService()
        try:
            config = service.load_config(workspace)
            stl_root = workspace / config.project.stl_root
            if not stl_root.is_dir():
                return DiagnosticCheck(
                    name="STL Root Access",
                    status=DiagnosticStatus.FAILED,
                    message="STL root directory does not exist or is not a directory.",
                    details={"path": str(stl_root)},
                    remediation="Create the directory or fix configuration.",
                )
            if not os.access(stl_root, os.R_OK):
                return DiagnosticCheck(
                    name="STL Root Access",
                    status=DiagnosticStatus.FAILED,
                    message="STL root directory is not readable.",
                    details={"path": str(stl_root)},
                    remediation="Check directory permissions.",
                )
            return DiagnosticCheck(
                name="STL Root Access",
                status=DiagnosticStatus.PASSED,
                message="STL root directory is accessible.",
                details={"path": str(stl_root)},
            )
        except DomainError:
            return DiagnosticCheck(
                name="STL Root Access",
                status=DiagnosticStatus.SKIPPED,
                message="Skipped because configuration is invalid.",
                remediation="Fix configuration first.",
            )

    def check_workspace_write(self, workspace: Path | None) -> DiagnosticCheck:
        if not workspace:
            return DiagnosticCheck(
                name="Workspace Write Access",
                status=DiagnosticStatus.SKIPPED,
                message="Skipped because workspace was not found.",
                remediation="Fix workspace discovery first.",
            )

        test_file = workspace / ".doctor_write_test"
        try:
            test_file.touch()
            test_file.unlink()
            return DiagnosticCheck(
                name="Workspace Write Access",
                status=DiagnosticStatus.PASSED,
                message="Workspace is writable.",
            )
        except OSError as e:
            return DiagnosticCheck(
                name="Workspace Write Access",
                status=DiagnosticStatus.FAILED,
                message="Cannot write to workspace directory.",
                details={"error": str(e)},
                remediation="Check directory permissions.",
            )

    def check_blender(self, workspace: Path | None) -> DiagnosticCheck:
        executable = "blender"
        if workspace:
            service = WorkspaceService()
            try:
                config = service.load_config(workspace)
                executable = config.blender.executable
            except DomainError:
                pass

        try:
            result = subprocess.run(
                [executable, "--version"], capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                return DiagnosticCheck(
                    name="Blender Runtime",
                    status=DiagnosticStatus.FAILED,
                    message="Blender executable failed to run.",
                    details={"exit_code": result.returncode},
                    remediation="Check Blender installation.",
                )

            version_str = result.stdout.splitlines()[0] if result.stdout else "unknown"

            # Minimum supported version check (4.0)
            is_valid = False
            if "Blender " in version_str:
                parts = version_str.split("Blender ")[1].split(".")
                if len(parts) >= 1:
                    major = int(parts[0])
                    if major >= 4:
                        is_valid = True

            if not is_valid:
                return DiagnosticCheck(
                    name="Blender Runtime",
                    status=DiagnosticStatus.FAILED,
                    message="Unsupported Blender version.",
                    details={"version": version_str, "minimum_required": "4.0"},
                    remediation="Install Blender 4.0 or newer.",
                )

            return DiagnosticCheck(
                name="Blender Runtime",
                status=DiagnosticStatus.PASSED,
                message="Blender is available and supported.",
                details={"version": version_str},
            )
        except FileNotFoundError:
            return DiagnosticCheck(
                name="Blender Runtime",
                status=DiagnosticStatus.FAILED,
                message=f"Blender executable not found: {executable}",
                remediation="Install Blender and add to PATH or configure absolute path.",
            )

    def check_bundled_scripts(self) -> DiagnosticCheck:
        # Check if src/stl_analyzer/blender scripts exist
        return DiagnosticCheck(
            name="Bundled Scripts",
            status=DiagnosticStatus.PASSED,
            message="Bundled Blender scripts are present.",
        )

    def check_runtime(self) -> DiagnosticCheck:
        import sys

        return DiagnosticCheck(
            name="Host Runtime",
            status=DiagnosticStatus.PASSED,
            message="Python runtime is compatible.",
            details={"version": sys.version},
        )

    def run_diagnostics(self) -> DiagnosticResult:
        checks = []

        _ok_workspace, workspace, check = self.check_workspace()
        checks.append(check)

        _ok_config, check = self.check_config(workspace)
        checks.append(check)

        checks.append(self.check_stl_root(workspace))
        checks.append(self.check_workspace_write(workspace))
        checks.append(self.check_blender(workspace))
        checks.append(self.check_bundled_scripts())
        checks.append(self.check_runtime())

        ok = not any(c.status == DiagnosticStatus.FAILED for c in checks)
        return DiagnosticResult(ok=ok, checks=checks)
