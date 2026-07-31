"""Case discovery and validation services."""

from __future__ import annotations

import os
from pathlib import Path

from stl_analyzer.errors import DomainError
from stl_analyzer.filesystem.paths import resolve_case_path, resolve_within
from stl_analyzer.models.cases import Case, CaseState, ValidationIssue
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.config import ScanConfig


class CaseDiscovery:
    def list_cases(
        self,
        workspace_root: Path,
        stl_root: str,
        scan_config: ScanConfig,
    ) -> list[Case]:
        """Discover and classify cases in the STL root.

        Only immediate child directories are considered. Non-directory entries
        at the STL root are silently skipped. Results are sorted deterministically.
        """
        root_path = workspace_root / stl_root
        if not root_path.is_dir():
            return []

        cases = []
        for entry in sorted(os.scandir(root_path), key=lambda e: e.name):
            if not entry.is_dir():
                continue

            case_id = entry.name
            path_rel = f"{stl_root}/{case_id}"

            # Find STL files case-insensitively at the case root only (no recursion)
            stl_files: list[str] = []
            has_unreadable = False

            try:
                for sub_entry in os.scandir(entry.path):
                    if sub_entry.is_file():
                        ext = Path(sub_entry.name).suffix.lower()
                        if ext in scan_config.allowed_extensions:
                            stl_files.append(sub_entry.name)
            except OSError:
                has_unreadable = True

            issues: list[ValidationIssue] = []
            warnings: list[ValidationIssue] = []

            if has_unreadable:
                state = CaseState.UNREADABLE
                issues.append(
                    ValidationIssue(
                        code="UNREADABLE_DIRECTORY",
                        message="Cannot read case directory contents.",
                    )
                )
                source = None
            elif len(stl_files) == 0:
                state = CaseState.MISSING_STL
                issues.append(
                    ValidationIssue(
                        code="NO_STL_FOUND",
                        message="No valid STL files found in case directory.",
                    )
                )
                source = None
            elif len(stl_files) > scan_config.maximum_files_per_case:
                state = CaseState.MULTIPLE_STL_FILES
                count = len(stl_files)
                max_count = scan_config.maximum_files_per_case
                issues.append(
                    ValidationIssue(
                        code="MULTIPLE_STL_FILES",
                        message=f"Found {count} STL files, maximum is {max_count}.",
                    )
                )
                stl_files.sort()
                source = f"{path_rel}/{stl_files[0]}"
            else:
                state = CaseState.READY
                source = f"{path_rel}/{stl_files[0]}"

            cases.append(
                Case(
                    case_id=case_id,
                    path=path_rel,
                    source_file=source,
                    state=state,
                    issues=issues,
                    warnings=warnings,
                )
            )

        return cases


class CaseValidation:
    def validate_case(
        self,
        workspace_root: Path,
        stl_root: str,
        assets_directory: str,
        scan_config: ScanConfig,
        case_id: str,
        test_write: bool = False,
    ) -> Case:
        """Validate a single case comprehensively."""
        # 1. Resolve and validate case path (handles traversal/absolute rejection)
        try:
            case_path = resolve_case_path(
                stl_root=workspace_root / stl_root,
                case_id=case_id,
            )
        except DomainError as e:
            raise DomainError(
                code="INVALID_CASE_ID",
                message=str(e.message),
                exit_code=ExitCode.INVALID_CASE,
                details={"case_id": case_id},
                recoverable=False,
                suggested_action="Provide a valid case ID.",
            ) from e

        if not case_path.is_dir():
            raise DomainError(
                code="CASE_NOT_FOUND",
                message="Case directory not found.",
                exit_code=ExitCode.INVALID_CASE,
                details={
                    "case_id": case_id,
                    "path": str(case_path.relative_to(workspace_root)),
                },
                recoverable=True,
                suggested_action="Check the case ID or run 'cases list'.",
            )

        # 2. Check STL files
        stl_files: list[str] = []
        try:
            for entry in os.scandir(case_path):
                if entry.is_file():
                    ext = Path(entry.name).suffix.lower()
                    if ext in scan_config.allowed_extensions:
                        stl_files.append(entry.name)
        except OSError as e:
            raise DomainError(
                code="UNREADABLE_CASE",
                message="Cannot read case directory.",
                exit_code=ExitCode.INVALID_CASE,
                details={"case_id": case_id},
                recoverable=True,
                suggested_action="Check directory permissions.",
            ) from e

        if len(stl_files) == 0:
            raise DomainError(
                code="NO_STL_FOUND",
                message="No STL file found in case.",
                exit_code=ExitCode.INVALID_CASE,
                details={"case_id": case_id},
                recoverable=True,
                suggested_action="Add an STL file to the case directory.",
            )

        if len(stl_files) > scan_config.maximum_files_per_case:
            raise DomainError(
                code="MULTIPLE_STL_FILES",
                message=(
                    f"Multiple STL files found, maximum is {scan_config.maximum_files_per_case}."
                ),
                exit_code=ExitCode.INVALID_CASE,
                details={"case_id": case_id, "count": len(stl_files)},
                recoverable=True,
                suggested_action="Remove extra STL files.",
            )

        stl_file = stl_files[0]
        stl_path = case_path / stl_file

        try:
            with open(stl_path, "rb") as f:
                f.read(1)
        except OSError as e:
            raise DomainError(
                code="UNREADABLE_STL",
                message="STL file is unreadable.",
                exit_code=ExitCode.INVALID_CASE,
                details={"case_id": case_id, "file": stl_file},
                recoverable=True,
                suggested_action="Check file permissions.",
            ) from e

        # 3. Validate assets path safety
        try:
            assets_path = resolve_within(
                root=case_path,
                value=assets_directory,
            )
        except DomainError as e:
            raise DomainError(
                code="INVALID_ASSETS_PATH",
                message="Assets path resolves outside case directory.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={"case_id": case_id, "assets_dir": assets_directory},
                recoverable=False,
                suggested_action="Fix assets_directory configuration.",
            ) from e

        # 4. Optionally test write capability without persistent mutation
        if test_write:
            test_file = assets_path / ".write_test"
            try:
                assets_path.mkdir(parents=True, exist_ok=True)
                test_file.touch()
                test_file.unlink()
            except OSError as e:
                raise DomainError(
                    code="CASE_NOT_WRITABLE",
                    message="Cannot write to case assets directory.",
                    exit_code=ExitCode.WORKSPACE_ERROR,
                    details={"case_id": case_id, "error": str(e)},
                    recoverable=True,
                    suggested_action="Check directory permissions.",
                ) from e

        return Case(
            case_id=case_id,
            path=f"{stl_root}/{case_id}",
            source_file=f"{stl_root}/{case_id}/{stl_file}",
            state=CaseState.READY,
            issues=[],
            warnings=[],
        )
