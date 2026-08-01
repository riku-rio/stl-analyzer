"""Tests for session models, repositories, event log, and session start (MVP-0709 partial)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stl_analyzer.blender.adapter import BlenderResult
from stl_analyzer.errors import DomainError
from stl_analyzer.models.session import (
    TERMINAL_SESSION_STATES,
    VALID_SESSION_TRANSITIONS,
    EventRecord,
    IterationRecord,
    IterationStatus,
    SessionRecord,
    SessionState,
    StatePointer,
)
from stl_analyzer.services.clock import FixedClock
from stl_analyzer.services.event_log import EventLog
from stl_analyzer.services.session_repository import (
    IterationRepository,
    SessionRepository,
)

# ──────────────────────── helpers ────────────────────────────────────────────


_NOW = "2026-01-01T00:00:00Z"
_SESSION_ID = "20260101T000000Z-abcd"
_TOOL_VER = "0.1.0"


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


def _assets_path(workspace: Path, case_id: str = "case-001") -> Path:
    return workspace / "stl" / case_id / "assets"


def _make_session(state: SessionState = SessionState.CREATED) -> SessionRecord:
    return SessionRecord(
        session_id=_SESSION_ID,
        case_id="case-001",
        state=state,
        geometry_sha256="a" * 64,
        tool_version=_TOOL_VER,
        created_at=_NOW,
        updated_at=_NOW,
        maximum_iterations=6,
        current_iteration=0,
    )


def _make_pointer(state: SessionState = SessionState.CREATED) -> StatePointer:
    return StatePointer(
        active_session_id=_SESSION_ID,
        session_state=state,
        current_iteration=0,
        updated_at=_NOW,
    )


# ──────────────────────── session state model ─────────────────────────────────


class TestSessionStateModel:
    def test_terminal_states_defined(self) -> None:
        assert SessionState.COMPLETED in TERMINAL_SESSION_STATES
        assert SessionState.QUALITY_NOT_MET in TERMINAL_SESSION_STATES
        assert SessionState.FAILED in TERMINAL_SESSION_STATES
        assert SessionState.CANCELLED in TERMINAL_SESSION_STATES

    def test_non_terminal_states_not_in_terminal(self) -> None:
        for state in [
            SessionState.CREATED,
            SessionState.RENDERING,
            SessionState.AWAITING_REVIEW,
            SessionState.ADJUSTMENT_READY,
        ]:
            assert state not in TERMINAL_SESSION_STATES

    def test_all_states_have_transition_entry(self) -> None:
        for state in SessionState:
            assert state in VALID_SESSION_TRANSITIONS

    def test_terminal_states_have_no_transitions(self) -> None:
        for state in TERMINAL_SESSION_STATES:
            assert len(VALID_SESSION_TRANSITIONS[state]) == 0

    def test_created_can_transition_to_rendering(self) -> None:
        assert SessionState.RENDERING in VALID_SESSION_TRANSITIONS[SessionState.CREATED]

    def test_session_record_round_trips(self) -> None:
        session = _make_session()
        dumped = session.model_dump(mode="json")
        restored = SessionRecord.model_validate(dumped)
        assert restored.session_id == _SESSION_ID
        assert restored.state == SessionState.CREATED

    def test_iteration_record_round_trips(self) -> None:
        rec = IterationRecord(
            session_id=_SESSION_ID,
            case_id="case-001",
            iteration=1,
            created_at=_NOW,
        )
        dumped = rec.model_dump(mode="json")
        restored = IterationRecord.model_validate(dumped)
        assert restored.iteration == 1
        assert restored.status == IterationStatus.PENDING


# ──────────────────────── event log ──────────────────────────────────────────


class TestEventLog:
    def test_append_and_read(self, tmp_path: Path) -> None:
        log = EventLog(tmp_path / "events.jsonl")
        event = EventRecord(
            event_type="session.created",
            timestamp=_NOW,
            case_id="case-001",
            session_id=_SESSION_ID,
            tool_version=_TOOL_VER,
        )
        log.append(event)
        records = log.read_all()
        assert len(records) == 1
        assert records[0].event_type == "session.created"

    def test_multiple_appends(self, tmp_path: Path) -> None:
        log = EventLog(tmp_path / "events.jsonl")
        for event_type in ["session.created", "render.started", "render.completed"]:
            log.append(
                EventRecord(
                    event_type=event_type,
                    timestamp=_NOW,
                    case_id="case-001",
                    session_id=_SESSION_ID,
                    tool_version=_TOOL_VER,
                )
            )
        records = log.read_all()
        assert [r.event_type for r in records] == [
            "session.created",
            "render.started",
            "render.completed",
        ]

    def test_truncated_final_line_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        log = EventLog(path)
        log.append(
            EventRecord(
                event_type="session.created",
                timestamp=_NOW,
                case_id="c",
                session_id="s",
                tool_version="0.1.0",
            )
        )
        # Append a truncated (broken) final line
        with path.open("a", encoding="utf-8") as fh:
            fh.write("{truncated")

        records = log.read_all()
        assert len(records) == 1

    def test_empty_log(self, tmp_path: Path) -> None:
        log = EventLog(tmp_path / "events.jsonl")
        assert log.read_all() == []


# ──────────────────────── session repository ─────────────────────────────────


class TestSessionRepository:
    def test_create_and_load(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()
        session = _make_session()
        pointer = _make_pointer()

        repo.create(assets_path=assets, session=session, pointer=pointer)

        loaded = repo.load(assets_path=assets, session_id=_SESSION_ID)
        assert loaded.session_id == _SESSION_ID
        assert loaded.state == SessionState.CREATED

    def test_state_pointer_written(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()
        repo.create(assets_path=assets, session=_make_session(), pointer=_make_pointer())

        pointer = repo.load_state_pointer(assets_path=assets)
        assert pointer is not None
        assert pointer.active_session_id == _SESSION_ID

    def test_find_active_session(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()
        repo.create(
            assets_path=assets,
            session=_make_session(SessionState.AWAITING_REVIEW),
            pointer=_make_pointer(SessionState.AWAITING_REVIEW),
        )

        active = repo.find_active_session(assets_path=assets)
        assert active is not None
        assert active.session_id == _SESSION_ID

    def test_terminal_session_not_active(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()
        repo.create(
            assets_path=assets,
            session=_make_session(SessionState.COMPLETED),
            pointer=_make_pointer(SessionState.COMPLETED),
        )

        active = repo.find_active_session(assets_path=assets)
        assert active is None

    def test_update_session(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()
        repo.create(assets_path=assets, session=_make_session(), pointer=_make_pointer())

        updated = _make_session(SessionState.RENDERING)
        new_pointer = _make_pointer(SessionState.RENDERING)
        repo.update(assets_path=assets, session=updated, pointer=new_pointer)

        loaded = repo.load(assets_path=assets, session_id=_SESSION_ID)
        assert loaded.state == SessionState.RENDERING

    def test_load_missing_session_raises(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()

        with pytest.raises(DomainError) as exc_info:
            repo.load(assets_path=assets, session_id="nonexistent")

        assert exc_info.value.code == "SESSION_NOT_FOUND"

    def test_list_sessions_empty(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()
        assert repo.list_sessions(assets_path=assets) == []

    def test_list_sessions_one(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = SessionRepository()
        repo.create(assets_path=assets, session=_make_session(), pointer=_make_pointer())
        sessions = repo.list_sessions(assets_path=assets)
        assert len(sessions) == 1
        assert sessions[0].session_id == _SESSION_ID


# ──────────────────────── iteration repository ───────────────────────────────


class TestIterationRepository:
    def _make_manifest(self, output_dir: Path) -> RenderManifest:  # noqa: F821
        from stl_analyzer.models.render import build_dental_arch_preset
        from stl_analyzer.models.render_manifest import RenderManifest

        params = build_dental_arch_preset(requested_views=["occlusal", "anterior"])
        return RenderManifest(
            case_id="case-001",
            session_id=_SESSION_ID,
            iteration=1,
            source_path="/fake/model.stl",
            source_sha256="a" * 64,
            output_dir=str(output_dir),
            params=params,
        )

    def test_next_number_empty(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = IterationRepository()
        assert repo.next_number(assets_path=assets, session_id=_SESSION_ID) == 1

    def test_next_number_after_create(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = IterationRepository()

        record = IterationRecord(
            session_id=_SESSION_ID, case_id="case-001", iteration=1, created_at=_NOW
        )
        iter_dir = assets / "sessions" / _SESSION_ID / "iterations" / "001"
        manifest = self._make_manifest(iter_dir)
        repo.create(assets_path=assets, record=record, manifest=manifest)

        assert repo.next_number(assets_path=assets, session_id=_SESSION_ID) == 2

    def test_create_writes_manifest(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = IterationRepository()

        record = IterationRecord(
            session_id=_SESSION_ID, case_id="case-001", iteration=1, created_at=_NOW
        )
        iter_dir = assets / "sessions" / _SESSION_ID / "iterations" / "001"
        manifest = self._make_manifest(iter_dir)
        created_dir = repo.create(assets_path=assets, record=record, manifest=manifest)

        assert (created_dir / "manifest.json").exists()
        assert (created_dir / "iteration.json").exists()

    def test_complete_writes_render_json(self, tmp_path: Path) -> None:
        from stl_analyzer.models.render_manifest import ImageInfo, RenderResult

        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = IterationRepository()

        record = IterationRecord(
            session_id=_SESSION_ID, case_id="case-001", iteration=1, created_at=_NOW
        )
        iter_dir = assets / "sessions" / _SESSION_ID / "iterations" / "001"
        manifest = self._make_manifest(iter_dir)
        repo.create(assets_path=assets, record=record, manifest=manifest)

        render_result = RenderResult(
            case_id="case-001",
            session_id=_SESSION_ID,
            iteration=1,
            blender_version="4.1.0",
            images=[
                ImageInfo(
                    view="occlusal",
                    path="stl/case-001/assets/s/i/001/images/occlusal.png",
                    width=512,
                    height=512,
                    size_bytes=1000,
                )
            ],
            duration_seconds=1.0,
            warnings=[],
            started_at=_NOW,
            completed_at=_NOW,
        )
        repo.complete(
            assets_path=assets,
            session_id=_SESSION_ID,
            iteration=1,
            render_result=render_result,
        )

        assert (iter_dir / "render.json").exists()

    def test_complete_twice_raises(self, tmp_path: Path) -> None:
        from stl_analyzer.models.render_manifest import RenderResult

        workspace = _make_workspace(tmp_path)
        assets = _assets_path(workspace)
        repo = IterationRepository()

        record = IterationRecord(
            session_id=_SESSION_ID, case_id="case-001", iteration=1, created_at=_NOW
        )
        iter_dir = assets / "sessions" / _SESSION_ID / "iterations" / "001"
        manifest = self._make_manifest(iter_dir)
        repo.create(assets_path=assets, record=record, manifest=manifest)

        render_result = RenderResult(
            case_id="case-001",
            session_id=_SESSION_ID,
            iteration=1,
            blender_version="4.1.0",
            images=[],
            duration_seconds=1.0,
            warnings=[],
            started_at=_NOW,
            completed_at=_NOW,
        )
        repo.complete(
            assets_path=assets,
            session_id=_SESSION_ID,
            iteration=1,
            render_result=render_result,
        )

        with pytest.raises(DomainError) as exc_info:
            repo.complete(
                assets_path=assets,
                session_id=_SESSION_ID,
                iteration=1,
                render_result=render_result,
            )

        assert exc_info.value.code == "ITERATION_ALREADY_COMPLETE"


# ──────────────────────── session start service ──────────────────────────────


class TestSessionStartService:
    """Tests for SessionStartService using a fake Blender adapter."""

    def _make_fake_adapter(
        self,
        *,
        inspect_exit_code: int = 0,
        render_exit_code: int = 0,
        timed_out: bool = False,
    ) -> FakeSessionAdapter:
        return FakeSessionAdapter(
            inspect_exit_code=inspect_exit_code,
            render_exit_code=render_exit_code,
            timed_out=timed_out,
        )

    def test_session_start_success(self, tmp_path: Path) -> None:
        from stl_analyzer.services.session_start_service import SessionStartService
        from stl_analyzer.services.workspace import WorkspaceService

        workspace = _make_workspace(tmp_path)
        config = WorkspaceService().load_config(workspace)
        adapter = self._make_fake_adapter()

        clock = FixedClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
        svc = SessionStartService(blender_adapter=adapter, clock=clock)

        result = svc.start(workspace_root=workspace, config=config, case_id="case-001")

        assert result.state == "awaiting_review"
        assert result.iteration == 1
        assert result.session_id.startswith("20260101T")

        # Session files must exist
        session_dir = workspace / "stl" / "case-001" / "assets" / "sessions" / result.session_id
        assert (session_dir / "session.json").exists()
        assert (session_dir / "events.jsonl").exists()
        assert (session_dir / "iterations" / "001" / "manifest.json").exists()

    def test_duplicate_active_session_rejected(self, tmp_path: Path) -> None:
        from stl_analyzer.services.session_start_service import SessionStartService
        from stl_analyzer.services.workspace import WorkspaceService

        workspace = _make_workspace(tmp_path)
        config = WorkspaceService().load_config(workspace)
        adapter = self._make_fake_adapter()

        clock = FixedClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
        svc = SessionStartService(blender_adapter=adapter, clock=clock)

        svc.start(workspace_root=workspace, config=config, case_id="case-001")

        with pytest.raises(DomainError) as exc_info:
            svc.start(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "ACTIVE_SESSION_EXISTS"

    def test_blender_timeout_in_render_fails(self, tmp_path: Path) -> None:
        from stl_analyzer.services.session_start_service import SessionStartService
        from stl_analyzer.services.workspace import WorkspaceService

        workspace = _make_workspace(tmp_path)
        config = WorkspaceService().load_config(workspace)
        # Inspection succeeds but render times out
        adapter = TimingOutRenderAdapter()

        clock = FixedClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
        svc = SessionStartService(blender_adapter=adapter, clock=clock)

        with pytest.raises(DomainError) as exc_info:
            svc.start(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "RENDER_TIMEOUT"

    def test_missing_case_fails(self, tmp_path: Path) -> None:
        from stl_analyzer.services.session_start_service import SessionStartService
        from stl_analyzer.services.workspace import WorkspaceService

        workspace = _make_workspace(tmp_path)
        config = WorkspaceService().load_config(workspace)
        adapter = self._make_fake_adapter()

        clock = FixedClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
        svc = SessionStartService(blender_adapter=adapter, clock=clock)

        with pytest.raises(DomainError):
            svc.start(workspace_root=workspace, config=config, case_id="nonexistent")

    def test_events_are_logged(self, tmp_path: Path) -> None:
        from stl_analyzer.services.session_start_service import SessionStartService
        from stl_analyzer.services.workspace import WorkspaceService

        workspace = _make_workspace(tmp_path)
        config = WorkspaceService().load_config(workspace)
        adapter = self._make_fake_adapter()

        clock = FixedClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
        svc = SessionStartService(blender_adapter=adapter, clock=clock)

        result = svc.start(workspace_root=workspace, config=config, case_id="case-001")

        session_dir = workspace / "stl" / "case-001" / "assets" / "sessions" / result.session_id
        log = EventLog(session_dir / "events.jsonl")
        events = log.read_all()
        event_types = [e.event_type for e in events]
        assert "session.created" in event_types
        assert "render.started" in event_types
        assert "render.completed" in event_types


# ──────────────────────── fake adapters ──────────────────────────────────────


class FakeSessionAdapter:
    """Fake adapter for session start tests: handles inspect and render manifests."""

    def __init__(
        self,
        *,
        inspect_exit_code: int = 0,
        render_exit_code: int = 0,
        timed_out: bool = False,
    ) -> None:
        self._inspect_exit = inspect_exit_code
        self._render_exit = render_exit_code
        self._timed_out = timed_out

    def run(self, *, executable, script, manifest_path, timeout_seconds):  # type: ignore[no-untyped-def]
        import hashlib

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if self._timed_out:
            return BlenderResult("", "", -1, 0.1, True)

        # Determine whether this is an inspect or render call.
        if "output_path" in manifest:
            # Inspection manifest
            output_path = Path(manifest["output_path"])
            source_path = Path(manifest["source_path"])
            sha = hashlib.sha256()
            if source_path.exists():
                sha.update(source_path.read_bytes())
            actual_hash = sha.hexdigest()

            if self._inspect_exit != 0:
                return BlenderResult("", "error", self._inspect_exit, 0.1, False)

            from stl_analyzer.models.geometry import (
                INSPECTION_SCHEMA_VERSION,
                INSPECTION_SCRIPT_VERSION,
            )

            payload = {
                "schema_version": INSPECTION_SCHEMA_VERSION,
                "script_version": INSPECTION_SCRIPT_VERSION,
                "tool_version": "0.1.0",
                "case_id": manifest["case_id"],
                "source_path": str(source_path),
                "source_sha256": actual_hash,
                "source_size_bytes": source_path.stat().st_size if source_path.exists() else 0,
                "blender_version": "4.1.0",
                "vertex_count": 4,
                "polygon_count": 4,
                "object_count": 1,
                "component_count": 1,
                "bounding_box": {
                    "min": [-10.0, -10.0, -5.0],
                    "max": [10.0, 10.0, 5.0],
                },
                "dimensions": [20.0, 20.0, 10.0],
                "center": [0.0, 0.0, 0.0],
                "assumed_unit": "millimeters",
                "warnings": [],
                "inspection_timestamp": "2026-01-01T00:00:00Z",
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return BlenderResult("OK", "", 0, 0.1, False)
        else:
            # Render manifest
            if self._render_exit != 0:
                return BlenderResult("", "render error", self._render_exit, 0.1, False)

            output_dir = Path(manifest["output_dir"])
            images_dir = output_dir / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            # Write tiny placeholder images for requested views
            requested_views: list[str] = manifest["params"]["requested_views"]
            rendered: list[dict] = []
            for view in requested_views:
                img_path = images_dir / f"{view}.png"
                # Write a minimal valid PNG (1x1 black)
                _write_tiny_png(img_path)
                rendered.append(
                    {
                        "view": view,
                        "path": str(img_path),
                        "width": manifest["params"]["width"],
                        "height": manifest["params"]["height"],
                        "size_bytes": img_path.stat().st_size,
                    }
                )

            result = {
                "schema_version": "1",
                "script_version": "1",
                "case_id": manifest["case_id"],
                "session_id": manifest["session_id"],
                "iteration": manifest["iteration"],
                "blender_version": "4.1.0",
                "images": rendered,
                "duration_seconds": 0.1,
                "warnings": [],
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:00:00Z",
            }
            result_path = output_dir / "render_result.json"
            result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return BlenderResult("OK", "", 0, 0.1, False)


class TimingOutRenderAdapter:
    """Inspection succeeds but render times out."""

    def run(self, *, executable, script, manifest_path, timeout_seconds):  # type: ignore[no-untyped-def]
        import hashlib

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if "output_path" in manifest:
            # Inspection — succeed
            output_path = Path(manifest["output_path"])
            source_path = Path(manifest["source_path"])
            sha = hashlib.sha256()
            if source_path.exists():
                sha.update(source_path.read_bytes())
            actual_hash = sha.hexdigest()

            from stl_analyzer.models.geometry import (
                INSPECTION_SCHEMA_VERSION,
                INSPECTION_SCRIPT_VERSION,
            )

            payload = {
                "schema_version": INSPECTION_SCHEMA_VERSION,
                "script_version": INSPECTION_SCRIPT_VERSION,
                "tool_version": "0.1.0",
                "case_id": manifest["case_id"],
                "source_path": str(source_path),
                "source_sha256": actual_hash,
                "source_size_bytes": source_path.stat().st_size if source_path.exists() else 0,
                "blender_version": "4.1.0",
                "vertex_count": 4,
                "polygon_count": 4,
                "object_count": 1,
                "component_count": 1,
                "bounding_box": {
                    "min": [-10.0, -10.0, -5.0],
                    "max": [10.0, 10.0, 5.0],
                },
                "dimensions": [20.0, 20.0, 10.0],
                "center": [0.0, 0.0, 0.0],
                "assumed_unit": "millimeters",
                "warnings": [],
                "inspection_timestamp": "2026-01-01T00:00:00Z",
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return BlenderResult("OK", "", 0, 0.1, False)
        else:
            # Render — time out
            return BlenderResult("", "", -1, 0.1, True)


def _write_tiny_png(path: Path) -> None:
    """Write a minimal valid 1x1 PNG."""
    import struct
    import zlib

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    path.write_bytes(data)
