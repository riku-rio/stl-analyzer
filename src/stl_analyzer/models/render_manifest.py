"""Render manifest and result schemas (MVP-0603)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from stl_analyzer.models.render import RenderParams

RENDER_MANIFEST_SCHEMA_VERSION = "1"
RENDER_RESULT_SCHEMA_VERSION = "1"
RENDER_SCRIPT_VERSION = "1"


class RenderManifest(BaseModel):
    """Persisted before Blender is invoked; provides the complete render input."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = RENDER_MANIFEST_SCHEMA_VERSION
    script_version: str = RENDER_SCRIPT_VERSION
    case_id: str
    session_id: str
    iteration: int
    source_path: str
    """Workspace-relative path to the source STL."""
    source_sha256: str
    output_dir: str
    """Absolute path to the directory where images and render.json will be written."""
    params: RenderParams
    manifest_sha256: str = ""
    """SHA-256 of this document (set after serialisation)."""


class ImageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: str
    path: str
    """Workspace-relative path to the rendered image."""
    width: int
    height: int
    size_bytes: int


class RenderResult(BaseModel):
    """Written by the Blender render script and validated by the host."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = RENDER_RESULT_SCHEMA_VERSION
    script_version: str = RENDER_SCRIPT_VERSION
    case_id: str
    session_id: str
    iteration: int
    blender_version: str
    images: list[ImageInfo]
    duration_seconds: float
    warnings: list[str] = Field(default_factory=list)
    started_at: str
    completed_at: str
