"""Session and iteration repository services (MVP-0703, MVP-0704)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from stl_analyzer.errors import DomainError
from stl_analyzer.filesystem.atomic import atomic_write_json
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.render_manifest import RenderManifest, RenderResult
from stl_analyzer.models.session import (
    TERMINAL_SESSION_STATES,
    IterationRecord,
    IterationStatus,
    SessionRecord,
    StatePointer,
)

# ─────────────────────────── path helpers ────────────────────────────────────


def _sessions_dir(assets_path: Path) -> Path:
    return assets_path / "sessions"


def _session_dir(assets_path: Path, session_id: str) -> Path:
    return _sessions_dir(assets_path) / session_id


def _iterations_dir(assets_path: Path, session_id: str) -> Path:
    return _session_dir(assets_path, session_id) / "iterations"


def _iteration_dir(assets_path: Path, session_id: str, iteration: int) -> Path:
    return _iterations_dir(assets_path, session_id) / f"{iteration:03d}"


def _state_pointer_path(assets_path: Path) -> Path:
    return assets_path / "state.json"


# ─────────────────────────── session repository ──────────────────────────────


class SessionRepository:
    """Create, update, and query sessions (MVP-0703)."""

    def create(
        self,
        *,
        assets_path: Path,
        session: SessionRecord,
        pointer: StatePointer,
    ) -> None:
        """Persist a new session and update the state pointer."""
        session_path = _session_dir(assets_path, session.session_id)
        session_path.mkdir(parents=True, exist_ok=True)

        # Write session.json
        atomic_write_json(
            session_path / "session.json",
            session.model_dump(mode="json"),
        )

        # Update state pointer
        self._write_state_pointer(assets_path, pointer)

    def update(
        self,
        *,
        assets_path: Path,
        session: SessionRecord,
        pointer: StatePointer,
    ) -> None:
        """Atomically update session.json and state.json."""
        session_path = _session_dir(assets_path, session.session_id)
        atomic_write_json(
            session_path / "session.json",
            session.model_dump(mode="json"),
        )
        self._write_state_pointer(assets_path, pointer)

    def load(self, *, assets_path: Path, session_id: str) -> SessionRecord:
        """Load a session record by ID."""
        path = _session_dir(assets_path, session_id) / "session.json"
        if not path.exists():
            raise DomainError(
                code="SESSION_NOT_FOUND",
                message=f"Session '{session_id}' not found.",
                exit_code=ExitCode.INVALID_WORKFLOW_STATE,
                details={"session_id": session_id},
                recoverable=False,
                suggested_action="Use 'session start' or 'session resume'.",
            )
        try:
            return SessionRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise DomainError(
                code="SESSION_CORRUPT",
                message="Session record cannot be parsed.",
                exit_code=ExitCode.INVALID_WORKFLOW_STATE,
                details={"session_id": session_id, "error": str(exc)},
                recoverable=False,
                suggested_action="Run 'session reset' to clear corrupted state.",
            ) from exc

    def load_state_pointer(self, *, assets_path: Path) -> StatePointer | None:
        """Load the convenience state pointer, or None if absent."""
        path = _state_pointer_path(assets_path)
        if not path.exists():
            return None
        try:
            return StatePointer.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def find_active_session(self, *, assets_path: Path) -> SessionRecord | None:
        """Return the active (non-terminal) session for this case, or None."""
        pointer = self.load_state_pointer(assets_path=assets_path)
        if pointer is None or pointer.active_session_id is None:
            return None
        try:
            session = self.load(assets_path=assets_path, session_id=pointer.active_session_id)
        except DomainError:
            return None
        if session.state in TERMINAL_SESSION_STATES:
            return None
        return session

    def list_sessions(self, *, assets_path: Path) -> list[SessionRecord]:
        """List all sessions sorted by session ID (lexicographic/chronological)."""
        sessions_dir = _sessions_dir(assets_path)
        if not sessions_dir.is_dir():
            return []
        records: list[SessionRecord] = []
        for entry in sorted(sessions_dir.iterdir()):
            if not entry.is_dir():
                continue
            session_json = entry / "session.json"
            if not session_json.exists():
                continue
            try:
                records.append(
                    SessionRecord.model_validate(
                        json.loads(session_json.read_text(encoding="utf-8"))
                    )
                )
            except Exception:
                continue
        return records

    def _write_state_pointer(self, assets_path: Path, pointer: StatePointer) -> None:
        atomic_write_json(
            _state_pointer_path(assets_path),
            pointer.model_dump(mode="json"),
        )


# ─────────────────────────── iteration repository ────────────────────────────


class IterationRepository:
    """Create and manage immutable iterations (MVP-0704)."""

    def next_number(self, *, assets_path: Path, session_id: str) -> int:
        """Return the next 1-based iteration number."""
        iterations_dir = _iterations_dir(assets_path, session_id)
        if not iterations_dir.is_dir():
            return 1
        existing = [e for e in iterations_dir.iterdir() if e.is_dir() and e.name.isdigit()]
        if not existing:
            return 1
        return max(int(e.name) for e in existing) + 1

    def create(
        self,
        *,
        assets_path: Path,
        record: IterationRecord,
        manifest: RenderManifest,
    ) -> Path:
        """Create an iteration directory and persist the manifest before rendering.

        Returns the iteration directory path.
        """
        iteration_dir = _iteration_dir(assets_path, record.session_id, record.iteration)
        iteration_dir.mkdir(parents=True, exist_ok=True)
        (iteration_dir / "images").mkdir(exist_ok=True)

        # Persist record and manifest before executing Blender.
        atomic_write_json(
            iteration_dir / "iteration.json",
            record.model_dump(mode="json"),
        )
        atomic_write_json(
            iteration_dir / "manifest.json",
            manifest.model_dump(mode="json"),
        )

        return iteration_dir

    def complete(
        self,
        *,
        assets_path: Path,
        session_id: str,
        iteration: int,
        render_result: RenderResult,
    ) -> None:
        """Persist the render result and mark the iteration completed.

        Raises DomainError if the iteration has already been completed.
        """
        iteration_dir = _iteration_dir(assets_path, session_id, iteration)
        render_path = iteration_dir / "render.json"

        if render_path.exists():
            raise DomainError(
                code="ITERATION_ALREADY_COMPLETE",
                message=f"Iteration {iteration} has already been completed.",
                exit_code=ExitCode.INVALID_WORKFLOW_STATE,
                details={"session_id": session_id, "iteration": iteration},
                recoverable=False,
                suggested_action="Do not attempt to overwrite a completed iteration.",
            )

        atomic_write_json(render_path, render_result.model_dump(mode="json"))

        # Update iteration record status.
        record_path = iteration_dir / "iteration.json"
        try:
            record = IterationRecord.model_validate(
                json.loads(record_path.read_text(encoding="utf-8"))
            )
            record = record.model_copy(update={"status": IterationStatus.COMPLETED})
            atomic_write_json(record_path, record.model_dump(mode="json"))
        except Exception:
            # Tolerate missing/corrupt record; render.json is the authoritative signal.
            pass

    def load_manifest(
        self, *, assets_path: Path, session_id: str, iteration: int
    ) -> RenderManifest | None:
        """Load the render manifest for an iteration."""
        path = _iteration_dir(assets_path, session_id, iteration) / "manifest.json"
        if not path.exists():
            return None
        try:
            return RenderManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def load_render_result(
        self, *, assets_path: Path, session_id: str, iteration: int
    ) -> RenderResult | None:
        """Load the render result for a completed iteration."""
        path = _iteration_dir(assets_path, session_id, iteration) / "render.json"
        if not path.exists():
            return None
        try:
            return RenderResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def get_iteration_dir(self, *, assets_path: Path, session_id: str, iteration: int) -> Path:
        return _iteration_dir(assets_path, session_id, iteration)
