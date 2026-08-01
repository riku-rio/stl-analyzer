"""Geometry inspection manifest and result schemas (MVP-0502)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

INSPECTION_SCHEMA_VERSION = "1"
INSPECTION_SCRIPT_VERSION = "1"


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: list[float] = Field(..., min_length=3, max_length=3)
    max: list[float] = Field(..., min_length=3, max_length=3)


class InspectionManifest(BaseModel):
    """Written to disk before launching Blender for geometry inspection."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = INSPECTION_SCHEMA_VERSION
    case_id: str
    source_path: str
    """Workspace-relative path to the source STL."""
    output_path: str
    """Absolute path where Blender should write the result JSON."""
    expected_hash: str
    """SHA-256 of the source STL at manifest creation time."""
    assumed_unit: str = "millimeters"


class InspectionResult(BaseModel):
    """Written by the Blender inspection script and validated by the host."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = INSPECTION_SCHEMA_VERSION
    script_version: str = INSPECTION_SCRIPT_VERSION
    tool_version: str
    case_id: str
    source_path: str
    source_sha256: str
    source_size_bytes: int
    blender_version: str
    vertex_count: int
    polygon_count: int
    object_count: int
    component_count: int | None = None
    bounding_box: BoundingBox
    dimensions: list[float] = Field(..., min_length=3, max_length=3)
    center: list[float] = Field(..., min_length=3, max_length=3)
    assumed_unit: str
    warnings: list[str] = Field(default_factory=list)
    inspection_timestamp: str
    """ISO-8601 UTC timestamp."""


def validate_inspection_result_hash(result: InspectionResult, expected_hash: str) -> list[str]:
    """Return a list of hash-mismatch warnings (empty if the hash matches)."""
    issues: list[str] = []
    if result.source_sha256 != expected_hash:
        issues.append(
            f"Source hash mismatch: manifest expected {expected_hash!r} "
            f"but result reports {result.source_sha256!r}."
        )
    return issues
