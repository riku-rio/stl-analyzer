"""Host-side render service (MVP-0604/0605 host side)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from stl_analyzer.blender import get_script
from stl_analyzer.blender.adapter import BlenderAdapter
from stl_analyzer.errors import DomainError
from stl_analyzer.filesystem.atomic import atomic_write_json
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.config import WorkspaceConfig
from stl_analyzer.models.render_manifest import RenderManifest, RenderResult
from stl_analyzer.services.image_validation import validate_rendered_images


class RenderService:
    """Orchestrate one Blender render iteration on the host side."""

    def __init__(self, adapter: BlenderAdapter) -> None:
        self._adapter = adapter

    def render(
        self,
        *,
        workspace_root: Path,
        config: WorkspaceConfig,
        manifest: RenderManifest,
        iteration_dir: Path,
    ) -> RenderResult:
        """Invoke Blender with *manifest*, validate images, return RenderResult.

        Raises:
            DomainError: on timeout, non-zero exit, missing images, or schema failure.
        """
        output_dir = iteration_dir

        # Write manifest to disk (caller may have already done this; overwrite is safe).
        manifest_path = iteration_dir / "manifest.json"
        atomic_write_json(manifest_path, manifest.model_dump(mode="json"))

        try:
            script = get_script("render_views.py")
        except FileNotFoundError as exc:
            raise DomainError(
                code="RENDER_SCRIPT_NOT_FOUND",
                message="Bundled render script is missing.",
                exit_code=ExitCode.BLENDER_FAILURE,
                recoverable=False,
                suggested_action="Reinstall stl-analyzer.",
            ) from exc

        start = time.monotonic()
        blender_result = self._adapter.run(
            executable=config.blender.executable,
            script=script,
            manifest_path=manifest_path,
            timeout_seconds=float(config.blender.timeout_seconds),
        )
        duration = time.monotonic() - start

        if blender_result.timed_out:
            raise DomainError(
                code="RENDER_TIMEOUT",
                message=f"Blender render timed out after {config.blender.timeout_seconds}s.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={
                    "case_id": manifest.case_id,
                    "session_id": manifest.session_id,
                    "iteration": manifest.iteration,
                },
                recoverable=True,
                suggested_action="Increase blender.timeout_seconds in config.",
            )

        if blender_result.exit_code != 0:
            raise DomainError(
                code="RENDER_NONZERO_EXIT",
                message=f"Blender render exited with code {blender_result.exit_code}.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={
                    "case_id": manifest.case_id,
                    "iteration": manifest.iteration,
                    "exit_code": blender_result.exit_code,
                    "stderr_tail": blender_result.stderr[-2000:],
                },
                recoverable=False,
                suggested_action="Check the STL file and Blender configuration.",
            )

        # Read the result JSON written by the script.
        result_json_path = output_dir / "render_result.json"
        if not result_json_path.exists():
            raise DomainError(
                code="RENDER_RESULT_MISSING",
                message="Blender render succeeded but result file was not written.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": manifest.case_id, "iteration": manifest.iteration},
                recoverable=False,
                suggested_action="Check the render script output.",
            )

        raw = self._read_raw(result_json_path, manifest)

        if raw.get("ok") is False:
            err = raw.get("error", {})
            raise DomainError(
                code=err.get("code", "RENDER_SCRIPT_ERROR"),
                message=err.get("message", "Blender render script reported failure."),
                exit_code=ExitCode.BLENDER_FAILURE,
                details={"case_id": manifest.case_id, "iteration": manifest.iteration},
                recoverable=False,
                suggested_action="Check the source STL file.",
            )

        # Post-validate images (MVP-0605).
        images, img_warnings = validate_rendered_images(
            manifest=manifest,
            output_dir=output_dir,
            workspace_root=workspace_root,
        )

        # Build final result.
        blender_warnings: list[str] = raw.get("warnings", [])
        all_warnings: list[str] = blender_warnings + [
            f"[image-validation] {w.view}: {w.message}" for w in img_warnings
        ]

        result = RenderResult(
            case_id=manifest.case_id,
            session_id=manifest.session_id,
            iteration=manifest.iteration,
            blender_version=raw.get("blender_version", "unknown"),
            images=images,
            duration_seconds=round(duration, 3),
            warnings=all_warnings,
            started_at=raw.get("started_at", ""),
            completed_at=raw.get("completed_at", ""),
        )

        return result

    def _read_raw(self, path: Path, manifest: RenderManifest) -> dict:  # type: ignore[type-arg]
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise DomainError(
                code="RENDER_INVALID_JSON",
                message="Blender render result is not valid JSON.",
                exit_code=ExitCode.BLENDER_FAILURE,
                details={
                    "case_id": manifest.case_id,
                    "iteration": manifest.iteration,
                    "error": str(exc),
                },
                recoverable=False,
                suggested_action="Check the render script output.",
            ) from exc
