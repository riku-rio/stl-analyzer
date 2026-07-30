"""Workspace initialization domain and response models."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from stl_analyzer.schema import CURRENT_SCHEMA_VERSION


class ActionKind(StrEnum):
    """Preflight classification for a workspace path."""

    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


class NodeKind(StrEnum):
    """Filesystem node type for a planned action."""

    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True, slots=True)
class PlannedAction:
    """Internal immutable preflight action."""

    path: str
    absolute_path: Path
    action: ActionKind
    node_kind: NodeKind
    content: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class InitPlan:
    """Complete preflight plan with no filesystem mutation."""

    workspace: Path
    actions: tuple[PlannedAction, ...]

    @property
    def conflicts(self) -> tuple[PlannedAction, ...]:
        return tuple(action for action in self.actions if action.action is ActionKind.CONFLICT)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


class InitActionRecord(BaseModel):
    """Serializable preflight or commit action."""

    model_config = ConfigDict(extra="forbid")

    path: str
    action: ActionKind
    node_kind: NodeKind
    reason: str | None = None


class InitResult(BaseModel):
    """Successful workspace initialization result."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = CURRENT_SCHEMA_VERSION
    workspace: str
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    actions: list[InitActionRecord] = Field(default_factory=list)
    next_commands: list[str] = Field(default_factory=list)
