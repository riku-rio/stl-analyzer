"""Host-side geometry inspection service (MVP-0504)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from stl_analyzer.blender import get_script
from stl_analyzer.blender.adapter import BlenderAdapter, BlenderResult
from stl_analyzer.errors import DomainError
from stl_analyzer.filesystem.atomic import atomic_write_json
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.config import WorkspaceConfig
from stl_analyzer.models.geometry import (
    INSPECTION_SCHEMA_VERSION,
    INSPECTION_SCRIPT_VERSION,
    InspectionManifest,
    InspectionResult,
    validate_inspection_result_hash,
)
from stl_analyzer.services.case_service import CaseValidation
from stl_analyzer.services.hashing import sha256_file


class InspectionService:
    """Orchestrate geometry inspection for one case (MVP-0504)."""

    def __init__(self, adapter: BlenderAdapter) -> None:
        self._adapter = adapter

    def inspect(
        self,
        *,
        workspace_root: Path,
        config: WorkspaceConfig,
        case_id: str,
        force: bool = False,
    ) -> tuple[InspectionResult, bool]:
        """Run geometry inspection for a case.

        Returns:
            A tuple of (result, cache_hit) where cache_hit is True when an
            existing valid geometry.json was reused without relaunching Blender.

        Raises:
            DomainError: on any validation, Blender, or filesystem failure.
        """
        # ── 1. Validate case ──────────────────────────────────────────────
        validator = CaseValidation()
        case = validator.validate_case(
            workspace_root=workspace_root,
            stl_root=config.project.stl_root,
            assets_directory=config.project.assets_directory,
            scan_config=config.scan,
            case_id=case_id,
        )

        stl_root_path = workspace_root / config.project.stl_root
        case_path = stl_root_path / case_id
        # source_file is workspace-relative
        source_abs = workspace_root / (case.source_file or "")
        assets_path = case_path / config.project.assets_directory
        geometry_json = assets_path / "geometry.json"

        # ── 2. Compute source hash ────────────────────────────────────────
        try:
            source_hash = sha256_file(source_abs)
        except OSError as exc:
            raise DomainError(
                code="STL_UNREADABLE",
                message="Cannot read source STL for hashing.",
                exit_code=ExitCode.INVALID_CASE,
                details={"case_id": case_id, "error": str(exc)},
                recoverable=True,
                suggested_action="Check file permissions.",
            ) from exc

        # ── 3. Cache check ────────────────────────────────────────────────
        if not force and geometry_json.exists():
            cached = self._load_cached(geometry_json)
            if (
                cached is not None
                and cached.source_sha256 == source_hash
                and cached.schema_version == INSPECTION_SCHEMA_VERSION
                and cached.script_version == INSPECTION_SCRIPT_VERSION
            ):
                return cached, True

        # ── 4. Create assets directory ────────────────────────────────────
        try:
            assets_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DomainError(
                code="ASSETS_MKDIR_FAILED",
                message="Cannot create case assets directory.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={"case_id": case_id, "error": str(exc)},
                recoverable=True,
                suggested_action="Check directory permissions.",
            ) from exc

        # ── 5. Write inspection manifest ──────────────────────────────────
        result_tmp_path = assets_path / "_inspect_result.json"
        manifest = InspectionManifest(
            case_id=case_id,
            source_path=str(source_abs),
            output_path=str(result_tmp_path),
            expected_hash=source_hash,
            assumed_unit=config.scan.assumed_unit,
        )
        manifest_path = assets_path / "_inspect_manifest.json"
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))

        # ── 6. Invoke Blender ─────────────────────────────────────────────
        try:
            script = get_script("inspect_geometry.py")
        except FileNotFoundError as exc:
            raise DomainError(
                code="SCRIPT_NOT_FOUND",
                message="Bundled inspection script is missing.",
                exit_code=ExitCode.BLENDER_FAILURE,
                recoverable=False,
                suggested_action="Reinstall stl-analyzer.",
            ) from exc

        blender_result: BlenderResult = self._adapter.run(
            executable=config.blender.executable,
            script=script,
            manifest_path=manifest_path,
            timeout_seconds=float(config.blender.timeout_seconds),
        )

        # ── 7. Handle Blender failures ────────────────────────────────────
        if blender_result.timed_out:
            raise DomainError(
                code="BLENDER_TIMEOUT",
                message=(f"Blender inspection timed out after {config.blender.timeout_seconds}s."),
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": case_id},
                recoverable=True,
                suggested_action="Increase blender.timeout_seconds in config.",
            )

        if blender_result.exit_code != 0:
            raise DomainError(
                code="BLENDER_NONZERO_EXIT",
                message=f"Blender inspection exited with code {blender_result.exit_code}.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={
                    "case_id": case_id,
                    "exit_code": blender_result.exit_code,
                    "stderr_tail": blender_result.stderr[-2000:],
                },
                recoverable=False,
                suggested_action="Check the STL file and Blender configuration.",
            )

        # ── 8. Validate result ────────────────────────────────────────────
        if not result_tmp_path.exists():
            raise DomainError(
                code="INSPECTION_RESULT_MISSING",
                message="Blender succeeded but the result file was not written.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": case_id},
                recoverable=False,
                suggested_action="Check the inspection script output.",
            )

        raw = self._read_raw_result(result_tmp_path, case_id)

        # Check for script-level failure payload
        if raw.get("ok") is False:
            err = raw.get("error", {})
            raise DomainError(
                code=err.get("code", "BLENDER_SCRIPT_ERROR"),
                message=err.get("message", "Blender script reported failure."),
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": case_id},
                recoverable=False,
                suggested_action="Check the source STL file.",
            )

        result = self._parse_result(raw, case_id)

        # ── 9. Verify hash ────────────────────────────────────────────────
        hash_warnings = validate_inspection_result_hash(result, source_hash)
        if hash_warnings:
            # Hash mismatch after successful Blender run is a hard error
            raise DomainError(
                code="INSPECTION_HASH_MISMATCH",
                message="Source file changed during inspection.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": case_id, "warnings": hash_warnings},
                recoverable=True,
                suggested_action="Reinspect the case.",
            )

        # ── 10. Promote to geometry.json ──────────────────────────────────
        atomic_write_json(geometry_json, result.model_dump(mode="json"))

        # Cleanup temporary files
        manifest_path.unlink(missing_ok=True)
        result_tmp_path.unlink(missing_ok=True)

        return result, False

    def load_geometry(
        self,
        *,
        workspace_root: Path,
        config: WorkspaceConfig,
        case_id: str,
    ) -> InspectionResult | None:
        """Load cached geometry.json without re-inspecting."""
        case_path = workspace_root / config.project.stl_root / case_id
        assets_path = case_path / config.project.assets_directory
        geometry_json = assets_path / "geometry.json"
        if not geometry_json.exists():
            return None
        return self._load_cached(geometry_json)

    # ── helpers ───────────────────────────────────────────────────────────

    def _load_cached(self, path: Path) -> InspectionResult | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return InspectionResult.model_validate(raw)
        except Exception:
            return None

    def _read_raw_result(self, path: Path, case_id: str) -> dict:  # type: ignore[type-arg]
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise DomainError(
                code="INSPECTION_INVALID_JSON",
                message="Blender inspection result is not valid JSON.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": case_id, "error": str(exc)},
                recoverable=False,
                suggested_action="Check the inspection script output.",
            ) from exc
        except OSError as exc:
            raise DomainError(
                code="INSPECTION_RESULT_UNREADABLE",
                message="Cannot read inspection result file.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": case_id, "error": str(exc)},
                recoverable=False,
                suggested_action="Check filesystem permissions.",
            ) from exc

    def _parse_result(self, raw: dict, case_id: str) -> InspectionResult:  # type: ignore[type-arg]
        try:
            return InspectionResult.model_validate(raw)
        except ValidationError as exc:
            raise DomainError(
                code="INSPECTION_SCHEMA_INVALID",
                message="Blender inspection result does not match the expected schema.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": case_id, "error": str(exc)},
                recoverable=False,
                suggested_action="Reinstall stl-analyzer (script version mismatch).",
            ) from exc
