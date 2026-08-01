"""Session start service (MVP-0705)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stl_analyzer import __version__
from stl_analyzer.blender.adapter import BlenderAdapter
from stl_analyzer.errors import DomainError
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.config import WorkspaceConfig
from stl_analyzer.models.geometry import INSPECTION_SCHEMA_VERSION, INSPECTION_SCRIPT_VERSION
from stl_analyzer.models.render import build_dental_arch_preset
from stl_analyzer.models.render_manifest import RenderManifest, RenderResult
from stl_analyzer.models.session import (
    EventRecord,
    IterationRecord,
    IterationStatus,
    SessionRecord,
    SessionState,
    StatePointer,
)
from stl_analyzer.services.case_service import CaseValidation
from stl_analyzer.services.clock import Clock, SystemClock, new_session_id
from stl_analyzer.services.event_log import EventLog
from stl_analyzer.services.hashing import sha256_file
from stl_analyzer.services.inspection_service import InspectionService
from stl_analyzer.services.render_service import RenderService
from stl_analyzer.services.session_repository import (
    IterationRepository,
    SessionRepository,
    _session_dir,
)


@dataclass
class SessionStartResult:
    session_id: str
    iteration: int
    state: SessionState
    image_paths: list[str]
    render_result: RenderResult
    from_cache: bool


class SessionStartService:
    """Orchestrate session creation and first render (MVP-0705)."""

    def __init__(
        self,
        blender_adapter: BlenderAdapter,
        clock: Clock | None = None,
    ) -> None:
        self._inspection = InspectionService(blender_adapter)
        self._render = RenderService(blender_adapter)
        self._session_repo = SessionRepository()
        self._iter_repo = IterationRepository()
        self._clock = clock or SystemClock()

    def start(
        self,
        *,
        workspace_root: Path,
        config: WorkspaceConfig,
        case_id: str,
    ) -> SessionStartResult:
        """Create a session, render iteration 001, and return to awaiting_review.

        Raises DomainError when:
        - An active session already exists for this case.
        - Case validation fails.
        - Geometry is missing or stale.
        - Blender inspection or render fails.
        """
        stl_root = workspace_root / config.project.stl_root
        case_path = stl_root / case_id
        assets_path = case_path / config.project.assets_directory

        # ── 1. Validate the case ─────────────────────────────────────────
        validator = CaseValidation()
        case = validator.validate_case(
            workspace_root=workspace_root,
            stl_root=config.project.stl_root,
            assets_directory=config.project.assets_directory,
            scan_config=config.scan,
            case_id=case_id,
        )

        # ── 2. Reject second active session ──────────────────────────────
        existing = self._session_repo.find_active_session(assets_path=assets_path)
        if existing is not None:
            raise DomainError(
                code="ACTIVE_SESSION_EXISTS",
                message=(
                    f"Case '{case_id}' already has an active session "
                    f"'{existing.session_id}' in state '{existing.state}'."
                ),
                exit_code=ExitCode.INVALID_WORKFLOW_STATE,
                details={
                    "case_id": case_id,
                    "session_id": existing.session_id,
                    "state": existing.state,
                },
                recoverable=True,
                suggested_action="Use 'session resume' or 'session reset' first.",
            )

        # ── 3. Ensure current geometry metadata ──────────────────────────
        source_abs = workspace_root / (case.source_file or "")
        source_hash = sha256_file(source_abs)

        geometry = self._inspection.load_geometry(
            workspace_root=workspace_root,
            config=config,
            case_id=case_id,
        )

        if (
            geometry is None
            or geometry.source_sha256 != source_hash
            or geometry.schema_version != INSPECTION_SCHEMA_VERSION
            or geometry.script_version != INSPECTION_SCRIPT_VERSION
        ):
            # Re-inspect.
            geometry, _ = self._inspection.inspect(
                workspace_root=workspace_root,
                config=config,
                case_id=case_id,
                force=True,
            )

        # ── 4. Create session ─────────────────────────────────────────────
        now = self._clock.now()
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        session_id = new_session_id(clock=self._clock)

        session = SessionRecord(
            session_id=session_id,
            case_id=case_id,
            state=SessionState.CREATED,
            geometry_sha256=source_hash,
            tool_version=__version__,
            created_at=now_str,
            updated_at=now_str,
            maximum_iterations=config.workflow.maximum_iterations,
            current_iteration=0,
        )
        pointer = StatePointer(
            active_session_id=session_id,
            session_state=SessionState.CREATED,
            current_iteration=0,
            updated_at=now_str,
        )

        assets_path.mkdir(parents=True, exist_ok=True)
        self._session_repo.create(
            assets_path=assets_path,
            session=session,
            pointer=pointer,
        )

        # Event log
        event_log = EventLog(_session_dir(assets_path, session_id) / "events.jsonl")
        event_log.append(
            EventRecord(
                event_type="session.created",
                timestamp=now_str,
                case_id=case_id,
                session_id=session_id,
                tool_version=__version__,
                payload={"geometry_sha256": source_hash},
            )
        )

        # ── 5. Transition → rendering ────────────────────────────────────
        session = session.model_copy(
            update={"state": SessionState.RENDERING, "updated_at": now_str, "current_iteration": 1}
        )
        pointer = pointer.model_copy(
            update={
                "session_state": SessionState.RENDERING,
                "current_iteration": 1,
                "updated_at": now_str,
            }
        )
        self._session_repo.update(
            assets_path=assets_path,
            session=session,
            pointer=pointer,
        )

        # ── 6. Build initial preset parameters ───────────────────────────
        render_params = build_dental_arch_preset(
            geometry_dims=geometry.dimensions,
            engine=config.render.engine,  # type: ignore[arg-type]
            width=config.render.width,
            height=config.render.height,
            requested_views=list(config.workflow.required_views),
        )

        # ── 7. Create iteration 001 ──────────────────────────────────────
        iteration_number = 1
        iter_record = IterationRecord(
            session_id=session_id,
            case_id=case_id,
            iteration=iteration_number,
            status=IterationStatus.RENDERING,
            created_at=now_str,
        )
        self._iter_repo.next_number(assets_path=assets_path, session_id=session_id)

        manifest = RenderManifest(
            case_id=case_id,
            session_id=session_id,
            iteration=iteration_number,
            source_path=str(source_abs),
            source_sha256=source_hash,
            output_dir=str(
                assets_path / "sessions" / session_id / "iterations" / f"{iteration_number:03d}"
            ),
            params=render_params,
        )

        # We pass the actual output dir, not a string.
        iter_dir = self._iter_repo.create(
            assets_path=assets_path,
            record=iter_record,
            manifest=manifest,
        )

        event_log.append(
            EventRecord(
                event_type="render.started",
                timestamp=now_str,
                case_id=case_id,
                session_id=session_id,
                iteration=iteration_number,
                tool_version=__version__,
                payload={},
            )
        )

        # ── 8. Render ─────────────────────────────────────────────────────
        render_result = self._render.render(
            workspace_root=workspace_root,
            config=config,
            manifest=manifest,
            iteration_dir=iter_dir,
        )

        completed_str = self._clock.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        event_log.append(
            EventRecord(
                event_type="render.completed",
                timestamp=completed_str,
                case_id=case_id,
                session_id=session_id,
                iteration=iteration_number,
                tool_version=__version__,
                payload={
                    "image_count": len(render_result.images),
                    "warnings": render_result.warnings,
                },
            )
        )

        # ── 9. Persist render result ──────────────────────────────────────
        self._iter_repo.complete(
            assets_path=assets_path,
            session_id=session_id,
            iteration=iteration_number,
            render_result=render_result,
        )

        # ── 10. Transition → awaiting_review ─────────────────────────────
        session = session.model_copy(
            update={
                "state": SessionState.AWAITING_REVIEW,
                "updated_at": completed_str,
            }
        )
        pointer = pointer.model_copy(
            update={
                "session_state": SessionState.AWAITING_REVIEW,
                "updated_at": completed_str,
            }
        )
        self._session_repo.update(
            assets_path=assets_path,
            session=session,
            pointer=pointer,
        )

        image_paths = [img.path for img in render_result.images]

        return SessionStartResult(
            session_id=session_id,
            iteration=iteration_number,
            state=SessionState.AWAITING_REVIEW,
            image_paths=image_paths,
            render_result=render_result,
            from_cache=False,
        )
