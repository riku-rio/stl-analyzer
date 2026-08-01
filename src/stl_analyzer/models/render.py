"""Render parameter models and dental arch preset (MVP-0601, MVP-0602)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RENDER_SCHEMA_VERSION = "1"
PRESET_VERSION = "1"

# ───────────────────────────── allowed engines ──────────────────────────────

RenderEngine = Literal["BLENDER_EEVEE_NEXT", "CYCLES"]

# ────────────────────────────── absolute bounds ──────────────────────────────

_CAMERA_YAW_RANGE = (-180.0, 180.0)
_CAMERA_PITCH_RANGE = (-90.0, 90.0)
_CAMERA_DISTANCE_MIN = 0.001
_CAMERA_DISTANCE_MAX = 10_000.0
_CAMERA_SCALE_MIN = 0.001
_CAMERA_SCALE_MAX = 10_000.0
_MARGIN_RANGE = (0.0, 0.5)
_LIGHT_ENERGY_MIN = 0.0
_LIGHT_ENERGY_MAX = 50_000.0
_ROUGHNESS_RANGE = (0.0, 1.0)


# ──────────────────────────── per-view camera ───────────────────────────────


class ViewCamera(BaseModel):
    """Camera parameters for one named view."""

    model_config = ConfigDict(extra="forbid")

    yaw_deg: float = Field(..., ge=_CAMERA_YAW_RANGE[0], le=_CAMERA_YAW_RANGE[1])
    """Azimuth rotation around the vertical axis in degrees."""
    pitch_deg: float = Field(..., ge=_CAMERA_PITCH_RANGE[0], le=_CAMERA_PITCH_RANGE[1])
    """Elevation angle above the horizontal plane in degrees."""
    distance: float | None = Field(default=None, ge=_CAMERA_DISTANCE_MIN, le=_CAMERA_DISTANCE_MAX)
    """Distance from the mesh center (perspective). Derived from geometry when None."""
    ortho_scale: float | None = Field(default=None, ge=_CAMERA_SCALE_MIN, le=_CAMERA_SCALE_MAX)
    """Orthographic scale. Derived from geometry when None."""
    use_orthographic: bool = False
    margin: float = Field(default=0.1, ge=_MARGIN_RANGE[0], le=_MARGIN_RANGE[1])
    """Fractional padding around the bounding box to add to framing."""


# ──────────────────────────── lighting rig ─────────────────────────────────


class LightParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    energy: float = Field(..., ge=_LIGHT_ENERGY_MIN, le=_LIGHT_ENERGY_MAX)
    """Lamp energy in Watts (Blender units)."""
    yaw_deg: float = Field(default=0.0, ge=_CAMERA_YAW_RANGE[0], le=_CAMERA_YAW_RANGE[1])
    pitch_deg: float = Field(default=45.0, ge=_CAMERA_PITCH_RANGE[0], le=_CAMERA_PITCH_RANGE[1])
    distance: float = Field(default=10.0, ge=_CAMERA_DISTANCE_MIN, le=_CAMERA_DISTANCE_MAX)


class LightingRig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: LightParams
    fill: LightParams
    rim: LightParams | None = None


# ──────────────────────────── material ─────────────────────────────────────


class MaterialParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roughness: float = Field(default=0.6, ge=_ROUGHNESS_RANGE[0], le=_ROUGHNESS_RANGE[1])
    color: list[float] = Field(
        default_factory=lambda: [0.85, 0.80, 0.72, 1.0],
        min_length=4,
        max_length=4,
    )
    """RGBA in linear color space."""


# ─────────────────────── color management ──────────────────────────────────


class ColorManagement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_device: str = "sRGB"
    view_transform: str = "Filmic"
    look: str = "None"
    exposure: float = Field(default=0.0, ge=-10.0, le=10.0)
    gamma: float = Field(default=1.0, ge=0.1, le=10.0)


# ──────────────────────────── full render params ────────────────────────────


class RenderParams(BaseModel):
    """Complete set of validated parameters for one render iteration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = RENDER_SCHEMA_VERSION
    preset_name: str
    preset_version: str = PRESET_VERSION
    engine: RenderEngine = "BLENDER_EEVEE_NEXT"
    width: int = Field(default=1024, ge=256, le=4096)
    height: int = Field(default=1024, ge=256, le=4096)
    views: dict[str, ViewCamera]
    """Keyed by view name, e.g. 'occlusal', 'anterior', …"""
    lighting: LightingRig
    material: MaterialParams
    color_management: ColorManagement = Field(default_factory=ColorManagement)
    requested_views: list[str]
    """The subset of view names to render for this iteration."""


# ─────────────────────── dental arch preset ────────────────────────────────

# Coordinate convention
# ---------------------
# The dental arch is assumed to be centred at the origin after centering the
# bounding box.  We use a right-handed Y-up coordinate system.
#
# Occlusal  - camera looks straight down (pitch -90 deg)
# Anterior  - camera looks from the front (yaw 0 deg, pitch 0 deg)
# Posterior - camera looks from behind (yaw 180 deg, pitch 0 deg)
# Left      - camera to the patient's right, looking left (yaw -90 deg, pitch 0 deg)
# Right     - camera to the patient's left, looking right (yaw 90 deg, pitch 0 deg)
# Isometric - three-quarter view from top-right (yaw 45 deg, pitch -35 deg)


def build_dental_arch_preset(
    geometry_dims: list[float] | None = None,
    engine: RenderEngine = "BLENDER_EEVEE_NEXT",
    width: int = 1024,
    height: int = 1024,
    requested_views: list[str] | None = None,
) -> RenderParams:
    """Build the default dental arch render parameters.

    Camera distances and orthographic scales are derived from the geometry
    bounding-box dimensions when provided; otherwise sensible defaults are used.
    All transforms are recorded in the returned model for determinism.
    """
    if requested_views is None:
        requested_views = ["occlusal", "anterior", "posterior", "left", "right", "isometric"]

    # Derive base framing scale from the largest dimension of the mesh.
    max_dim = max(geometry_dims) if geometry_dims and len(geometry_dims) == 3 else 80.0

    # Distance for perspective cameras - place the camera 2x the largest dim away.
    dist = max_dim * 2.0
    # Orthographic scale - show the largest dimension plus 10 % margin.
    ort_scale = max_dim * 1.1

    margin = 0.10

    views: dict[str, ViewCamera] = {
        "occlusal": ViewCamera(
            yaw_deg=0.0,
            pitch_deg=-90.0,
            ortho_scale=ort_scale,
            use_orthographic=True,
            margin=margin,
        ),
        "anterior": ViewCamera(
            yaw_deg=0.0,
            pitch_deg=-10.0,
            distance=dist,
            use_orthographic=False,
            margin=margin,
        ),
        "posterior": ViewCamera(
            yaw_deg=180.0,
            pitch_deg=-10.0,
            distance=dist,
            use_orthographic=False,
            margin=margin,
        ),
        "left": ViewCamera(
            yaw_deg=-90.0,
            pitch_deg=-10.0,
            distance=dist,
            use_orthographic=False,
            margin=margin,
        ),
        "right": ViewCamera(
            yaw_deg=90.0,
            pitch_deg=-10.0,
            distance=dist,
            use_orthographic=False,
            margin=margin,
        ),
        "isometric": ViewCamera(
            yaw_deg=45.0,
            pitch_deg=-35.0,
            distance=dist * 1.2,
            use_orthographic=False,
            margin=margin,
        ),
    }

    # Light rig energies scaled to geometry size.
    energy_scale = max_dim / 80.0  # 1.0 at default dental-arch scale
    key_energy = 500.0 * energy_scale
    fill_energy = 200.0 * energy_scale
    rim_energy = 300.0 * energy_scale

    lighting = LightingRig(
        key=LightParams(energy=key_energy, yaw_deg=-45.0, pitch_deg=60.0, distance=dist),
        fill=LightParams(energy=fill_energy, yaw_deg=45.0, pitch_deg=30.0, distance=dist),
        rim=LightParams(energy=rim_energy, yaw_deg=180.0, pitch_deg=20.0, distance=dist),
    )

    return RenderParams(
        preset_name="dental_arch",
        preset_version=PRESET_VERSION,
        engine=engine,
        width=width,
        height=height,
        views=views,
        lighting=lighting,
        material=MaterialParams(),
        color_management=ColorManagement(),
        requested_views=requested_views,
    )
