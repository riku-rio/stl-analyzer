"""Tests for render models, preset, and render service (MVP-0606)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from stl_analyzer.models.render import (
    LightingRig,
    LightParams,
    MaterialParams,
    RenderParams,
    ViewCamera,
    build_dental_arch_preset,
)
from stl_analyzer.models.render_manifest import RenderManifest, RenderResult

# ──────────────────────────── preset tests ───────────────────────────────────


class TestDentalArchPreset:
    def test_default_preset_has_all_views(self) -> None:
        params = build_dental_arch_preset()
        expected_views = {"occlusal", "anterior", "posterior", "left", "right", "isometric"}
        assert set(params.views.keys()) == expected_views

    def test_requested_views_matches_all_views(self) -> None:
        params = build_dental_arch_preset()
        assert set(params.requested_views) == set(params.views.keys())

    def test_preset_is_serializable(self) -> None:
        params = build_dental_arch_preset()
        dumped = params.model_dump(mode="json")
        assert dumped["preset_name"] == "dental_arch"
        restored = RenderParams.model_validate(dumped)
        assert restored.preset_name == params.preset_name

    def test_same_geometry_produces_same_params(self) -> None:
        dims = [70.0, 50.0, 30.0]
        p1 = build_dental_arch_preset(geometry_dims=dims)
        p2 = build_dental_arch_preset(geometry_dims=dims)
        assert p1.model_dump() == p2.model_dump()

    def test_geometry_dims_influence_distance(self) -> None:
        small = build_dental_arch_preset(geometry_dims=[10.0, 10.0, 5.0])
        large = build_dental_arch_preset(geometry_dims=[200.0, 150.0, 80.0])
        small_dist = small.views["anterior"].distance
        large_dist = large.views["anterior"].distance
        assert small_dist is not None and large_dist is not None
        assert large_dist > small_dist

    def test_engine_propagated(self) -> None:
        params = build_dental_arch_preset(engine="CYCLES")
        assert params.engine == "CYCLES"

    def test_resolution_propagated(self) -> None:
        params = build_dental_arch_preset(width=512, height=768)
        assert params.width == 512
        assert params.height == 768

    def test_partial_requested_views(self) -> None:
        views = ["occlusal", "isometric"]
        params = build_dental_arch_preset(requested_views=views)
        assert params.requested_views == views
        # All six view cameras still defined even though only two were requested.
        assert len(params.views) == 6

    def test_occlusal_is_orthographic(self) -> None:
        params = build_dental_arch_preset()
        assert params.views["occlusal"].use_orthographic is True
        assert params.views["occlusal"].ortho_scale is not None

    def test_perspective_views_have_distance(self) -> None:
        params = build_dental_arch_preset()
        for name in ["anterior", "posterior", "left", "right", "isometric"]:
            v = params.views[name]
            assert v.use_orthographic is False
            assert v.distance is not None and v.distance > 0


class TestRenderParamsBounds:
    def test_invalid_engine_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RenderParams(
                preset_name="x",
                engine="INVALID_ENGINE",  # type: ignore[arg-type]
                width=512,
                height=512,
                views={},
                lighting=LightingRig(
                    key=LightParams(energy=100),
                    fill=LightParams(energy=50),
                ),
                material=MaterialParams(),
                requested_views=[],
            )

    def test_out_of_range_width_rejected(self) -> None:
        with pytest.raises((ValidationError, TypeError)):
            ViewCamera(yaw_deg=0.0, pitch_deg=0.0, distance=100.0, width=100)  # type: ignore[call-arg]

    def test_view_camera_yaw_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ViewCamera(yaw_deg=200.0, pitch_deg=0.0)  # beyond +/-180

    def test_view_camera_pitch_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ViewCamera(yaw_deg=0.0, pitch_deg=-95.0)  # beyond +/-90

    def test_light_energy_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LightParams(energy=-1.0)

    def test_material_roughness_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MaterialParams(roughness=1.5)  # beyond 0-1


# ──────────────────────────── image post-validation tests ────────────────────


class TestImageValidation:
    def _make_manifest(self, requested_views: list[str], output_dir: Path) -> RenderManifest:
        params = build_dental_arch_preset(requested_views=requested_views)
        return RenderManifest(
            case_id="case-001",
            session_id="20260101T000000Z-abcd",
            iteration=1,
            source_path="/fake/model.stl",
            source_sha256="0" * 64,
            output_dir=str(output_dir),
            params=params,
        )

    def _write_minimal_png(self, path: Path, width: int = 512, height: int = 512) -> None:
        """Write a minimal but valid 1x1 black PNG (we ignore resolution in this helper)."""
        import struct
        import zlib

        def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + chunk_type
                + data
                + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        # Write a 1x1 RGBA PNG regardless of width/height arguments (for simplicity).
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        idat_data = zlib.compress(b"\x00\xff\xff\xff")
        raw = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", ihdr_data)
            + png_chunk(b"IDAT", idat_data)
            + png_chunk(b"IEND", b"")
        )
        path.write_bytes(raw)

    def test_valid_images_pass(self, tmp_path: Path) -> None:
        from stl_analyzer.services.image_validation import validate_rendered_images

        output_dir = tmp_path / "iter"
        views = ["occlusal", "anterior"]
        manifest = self._make_manifest(views, output_dir)
        manifest = manifest.model_copy(
            update={"params": manifest.params.model_copy(update={"width": 1, "height": 1})}
        )

        for v in views:
            img = output_dir / "images" / f"{v}.png"
            self._write_minimal_png(img, width=1, height=1)

        images, _warnings = validate_rendered_images(
            manifest=manifest, output_dir=output_dir, workspace_root=tmp_path
        )
        assert len(images) == 2
        # Dimension warnings may appear because we wrote 1x1 but manifest says 512x512.
        # That's ok -- the images list is populated regardless.

    def test_missing_image_produces_warning(self, tmp_path: Path) -> None:
        from stl_analyzer.services.image_validation import validate_rendered_images

        output_dir = tmp_path / "iter"
        views = ["occlusal"]
        manifest = self._make_manifest(views, output_dir)
        # Don't create any images

        images, warnings = validate_rendered_images(
            manifest=manifest, output_dir=output_dir, workspace_root=tmp_path
        )
        assert len(images) == 0
        assert any("missing" in w.message.lower() for w in warnings)

    def test_empty_image_produces_warning(self, tmp_path: Path) -> None:
        from stl_analyzer.services.image_validation import validate_rendered_images

        output_dir = tmp_path / "iter"
        views = ["anterior"]
        manifest = self._make_manifest(views, output_dir)

        img = output_dir / "images" / "anterior.png"
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"")  # empty file

        images, warnings = validate_rendered_images(
            manifest=manifest, output_dir=output_dir, workspace_root=tmp_path
        )
        assert len(images) == 0
        assert any("empty" in w.message.lower() for w in warnings)

    def test_wrong_dimensions_produces_warning(self, tmp_path: Path) -> None:
        from stl_analyzer.services.image_validation import validate_rendered_images

        output_dir = tmp_path / "iter"
        views = ["posterior"]
        manifest = self._make_manifest(views, output_dir)
        # Manifest expects 512x512 but we write 1x1

        img = output_dir / "images" / "posterior.png"
        self._write_minimal_png(img, width=1, height=1)

        _images, warnings = validate_rendered_images(
            manifest=manifest, output_dir=output_dir, workspace_root=tmp_path
        )
        # Image included (with actual dims) but warning about mismatch
        assert any("dimensions" in w.message.lower() for w in warnings)


# ──────────────────────────── render manifest schema tests ───────────────────


class TestRenderManifestSchema:
    def test_manifest_round_trips(self) -> None:
        params = build_dental_arch_preset()
        manifest = RenderManifest(
            case_id="c",
            session_id="20260101T000000Z-abcd",
            iteration=1,
            source_path="/p/m.stl",
            source_sha256="a" * 64,
            output_dir="/tmp/out",
            params=params,
        )
        dumped = manifest.model_dump(mode="json")
        restored = RenderManifest.model_validate(dumped)
        assert restored.case_id == manifest.case_id
        assert restored.params.preset_name == params.preset_name

    def test_render_result_round_trips(self) -> None:
        from stl_analyzer.models.render_manifest import ImageInfo

        result = RenderResult(
            case_id="c",
            session_id="20260101T000000Z-abcd",
            iteration=1,
            blender_version="4.1.0",
            images=[
                ImageInfo(
                    view="occlusal",
                    path="stl/c/assets/s/i/001/images/occlusal.png",
                    width=512,
                    height=512,
                    size_bytes=12345,
                )
            ],
            duration_seconds=3.2,
            warnings=[],
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:03Z",
        )
        dumped = result.model_dump(mode="json")
        restored = RenderResult.model_validate(dumped)
        assert restored.iteration == 1
        assert len(restored.images) == 1
