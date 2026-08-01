"""Workspace discovery and configuration service."""

import tomllib
from pathlib import Path

from pydantic import ValidationError

from stl_analyzer.errors import DomainError
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.config import WorkspaceConfig


class WorkspaceService:
    def find_workspace(self, start_path: Path | None = None) -> Path:
        """Find the workspace root containing stl-analyzer.toml."""
        current = (start_path or Path.cwd()).resolve()

        for p in [current, *current.parents]:
            if (p / "stl-analyzer.toml").is_file():
                return p

        raise DomainError(
            code="WORKSPACE_NOT_FOUND",
            message="Not inside an stl-analyzer workspace.",
            exit_code=ExitCode.WORKSPACE_ERROR,
            details={"search_started_at": str(current)},
            recoverable=True,
            suggested_action="Run 'stl-analyzer init' to create a workspace.",
        )

    def load_config(self, workspace_root: Path) -> WorkspaceConfig:
        """Load and validate the workspace configuration."""
        config_path = workspace_root / "stl-analyzer.toml"
        if not config_path.is_file():
            raise DomainError(
                code="CONFIG_MISSING",
                message="Workspace configuration file is missing.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={"expected_path": str(config_path)},
                recoverable=True,
                suggested_action="Reinitialize the workspace or restore the file.",
            )

        try:
            content = config_path.read_text(encoding="utf-8")
            data = tomllib.loads(content)
            return WorkspaceConfig.model_validate(data)
        except tomllib.TOMLDecodeError as e:
            raise DomainError(
                code="CONFIG_PARSE_ERROR",
                message="Configuration file contains invalid TOML.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={"error": str(e)},
                recoverable=True,
                suggested_action="Fix syntax errors in stl-analyzer.toml.",
            ) from e
        except ValidationError as e:
            issues = []
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"])
                issues.append(f"{loc}: {err['msg']}")

            raise DomainError(
                code="CONFIG_VALIDATION_ERROR",
                message="Configuration file is invalid.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={"issues": issues},
                recoverable=True,
                suggested_action="Fix the indicated fields in stl-analyzer.toml.",
            ) from e
