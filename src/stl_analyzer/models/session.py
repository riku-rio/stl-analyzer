"""Session and iteration domain models (MVP-0701)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SESSION_SCHEMA_VERSION = "1"
ITERATION_SCHEMA_VERSION = "1"
EVENT_SCHEMA_VERSION = "1"

# ─────────────────────────────── enums ──────────────────────────────────────


class SessionState(StrEnum):
    CREATED = "created"
    RENDERING = "rendering"
    AWAITING_REVIEW = "awaiting_review"
    ADJUSTMENT_READY = "adjustment_ready"
    COMPLETED = "completed"
    QUALITY_NOT_MET = "quality_not_met"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_SESSION_STATES: frozenset[SessionState] = frozenset(
    {
        SessionState.COMPLETED,
        SessionState.QUALITY_NOT_MET,
        SessionState.FAILED,
        SessionState.CANCELLED,
    }
)

# Valid forward transitions (source_state -> set of allowed next states)
VALID_SESSION_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.CREATED: frozenset({SessionState.RENDERING, SessionState.FAILED}),
    SessionState.RENDERING: frozenset(
        {SessionState.AWAITING_REVIEW, SessionState.FAILED, SessionState.QUALITY_NOT_MET}
    ),
    SessionState.AWAITING_REVIEW: frozenset(
        {
            SessionState.ADJUSTMENT_READY,
            SessionState.COMPLETED,
            SessionState.CANCELLED,
            SessionState.QUALITY_NOT_MET,
        }
    ),
    SessionState.ADJUSTMENT_READY: frozenset({SessionState.RENDERING, SessionState.CANCELLED}),
    # Terminal states have no forward transitions
    SessionState.COMPLETED: frozenset(),
    SessionState.QUALITY_NOT_MET: frozenset(),
    SessionState.FAILED: frozenset(),
    SessionState.CANCELLED: frozenset(),
}


class IterationStatus(StrEnum):
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


# ─────────────────────────── session model ──────────────────────────────────


class SessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SESSION_SCHEMA_VERSION
    session_id: str
    case_id: str
    state: SessionState = SessionState.CREATED
    geometry_sha256: str
    """SHA-256 of the source STL at session-start time."""
    tool_version: str
    created_at: str
    updated_at: str
    maximum_iterations: int
    current_iteration: int = 0


# ─────────────────────────── iteration model ────────────────────────────────


class IterationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = ITERATION_SCHEMA_VERSION
    session_id: str
    case_id: str
    iteration: int
    """1-based iteration number."""
    status: IterationStatus = IterationStatus.PENDING
    created_at: str
    completed_at: str | None = None


# ─────────────────────────── state pointer ──────────────────────────────────


class StatePointer(BaseModel):
    """Convenience pointer kept in assets/state.json - not the sole source of truth."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SESSION_SCHEMA_VERSION
    active_session_id: str | None = None
    session_state: SessionState | None = None
    current_iteration: int = 0
    updated_at: str


# ─────────────────────────── event log model ────────────────────────────────


class EventRecord(BaseModel):
    """One entry in the append-only events.jsonl log."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = EVENT_SCHEMA_VERSION
    event_type: str
    timestamp: str
    case_id: str
    session_id: str
    iteration: int | None = None
    tool_version: str
    payload: dict[str, Any] = Field(default_factory=dict)
