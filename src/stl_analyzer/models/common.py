"""Common machine-readable response contracts."""

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExitCode(IntEnum):
    """Stable process exit-code classes defined by the MVP PRD."""

    SUCCESS = 0
    INTERNAL_ERROR = 1
    INVALID_CLI_USAGE = 2
    WORKSPACE_ERROR = 3
    INVALID_CASE = 4
    BLENDER_FAILURE = 5
    INVALID_WORKFLOW_STATE = 6
    QUALITY_NOT_MET = 7
    PARTIAL_FAILURE = 8


class ErrorPayload(BaseModel):
    """Structured error details shared by all commands."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    recoverable: bool
    suggested_action: str | None = None


class ErrorEnvelope(BaseModel):
    """Top-level JSON failure envelope."""

    model_config = ConfigDict(extra="forbid")

    success: Literal[False] = False
    error: ErrorPayload


class SuccessEnvelope(BaseModel):
    """Top-level JSON success envelope."""

    model_config = ConfigDict(extra="forbid")

    success: Literal[True] = True
    data: Any
