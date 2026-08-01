"""Case domain models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CaseState(StrEnum):
    READY = "ready"
    MISSING_STL = "missing_stl"
    MULTIPLE_STL_FILES = "multiple_stl_files"
    INVALID_CASE_DIRECTORY = "invalid_case_directory"
    UNREADABLE = "unreadable"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    path: str
    source_file: str | None = None
    state: CaseState
    issues: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
