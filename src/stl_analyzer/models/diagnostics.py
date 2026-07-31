"""Diagnostic check domain models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class DiagnosticCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: DiagnosticStatus
    message: str
    details: dict[str, str | bool | int | float | None] = Field(default_factory=dict)
    remediation: str | None = None


class DiagnosticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    checks: list[DiagnosticCheck]
