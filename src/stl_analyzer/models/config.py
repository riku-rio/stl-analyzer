"""Configuration domain models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from stl_analyzer.schema import CURRENT_SCHEMA_VERSION


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stl_root: str = "stl"
    assets_directory: str = "assets"


class BlenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executable: str = "blender"
    timeout_seconds: int = Field(default=180, ge=1)


class ScanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_extensions: list[str] = Field(default_factory=lambda: [".stl"])
    maximum_files_per_case: int = Field(default=1, ge=1)
    assumed_unit: str = "millimeters"


class RenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(default=1024, ge=256, le=4096)
    height: int = Field(default=1024, ge=256, le=4096)
    engine: Literal["BLENDER_EEVEE_NEXT", "CYCLES"] = "BLENDER_EEVEE_NEXT"
    default_preset: str = "dental_arch"


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum_iterations: int = Field(default=6, ge=1)
    required_views: list[str] = Field(
        default_factory=lambda: [
            "occlusal",
            "anterior",
            "posterior",
            "left",
            "right",
            "isometric",
        ]
    )


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retain_all_iterations: bool = True
    write_event_log: bool = True


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = CURRENT_SCHEMA_VERSION
    template_version: str = "1"
    project: ProjectConfig = Field(default_factory=lambda: ProjectConfig())
    blender: BlenderConfig = Field(default_factory=lambda: BlenderConfig())
    scan: ScanConfig = Field(default_factory=lambda: ScanConfig())
    render: RenderConfig = Field(default_factory=lambda: RenderConfig())
    workflow: WorkflowConfig = Field(default_factory=lambda: WorkflowConfig())
    output: OutputConfig = Field(default_factory=lambda: OutputConfig())
