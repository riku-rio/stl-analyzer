"""
Blender render script — runs inside Blender's Python environment (MVP-0604).

Invocation:
    blender --background --python render_views.py -- <manifest_path>

The manifest must follow stl_analyzer.models.render_manifest.RenderManifest.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _find_manifest_path() -> Path:
    try:
        separator = sys.argv.index("--")
        return Path(sys.argv[separator + 1])
    except (ValueError, IndexError):
        raise RuntimeError(
            "Usage: blender --background --python render_views.py -- <manifest_path>"
        )


def _write_result(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _fail(output_path: Path | None, code: str, message: str) -> None:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {"code": code, "message": message},
    }
    if output_path is not None:
        _write_result(output_path, payload)
    print(f"[render_views] FAILURE {code}: {message}", file=sys.stderr)
    sys.exit(1)


def _deg_to_rad(deg: float) -> float:
    import math
    return math.radians(deg)


def _place_camera_perspective(
    camera_obj: Any, center: list[float], yaw_deg: float, pitch_deg: float, distance: float
) -> None:
    """Position a perspective camera in spherical coordinates around center."""
    import math

    import mathutils  # type: ignore[import]

    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)

    # Spherical to Cartesian (Y-up, yaw around Y)
    x = center[0] + distance * math.cos(pitch) * math.sin(yaw)
    y = center[1] - distance * math.sin(pitch)
    z = center[2] + distance * math.cos(pitch) * math.cos(yaw)

    camera_obj.location = (x, y, z)

    direction = mathutils.Vector(center) - mathutils.Vector((x, y, z))
    rot_quat = direction.to_track_quat("-Z", "Y")
    camera_obj.rotation_euler = rot_quat.to_euler()


def _place_camera_ortho(
    camera_obj: Any, center: list[float], yaw_deg: float, pitch_deg: float, scale: float
) -> None:
    """Position an orthographic camera."""
    # Use a large distance so we avoid near-clip issues
    _place_camera_perspective(camera_obj, center, yaw_deg, pitch_deg, distance=500.0)
    camera_obj.data.type = "ORTHO"
    camera_obj.data.ortho_scale = scale


def _create_light(name: str, energy: float, yaw_deg: float, pitch_deg: float,
                  distance: float, center: list[float]) -> Any:
    import math

    import bpy
    import mathutils  # type: ignore[import]

    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    x = center[0] + distance * math.cos(pitch) * math.sin(yaw)
    y = center[1] - distance * math.sin(pitch)
    z = center[2] + distance * math.cos(pitch) * math.cos(yaw)

    bpy.ops.object.light_add(type="AREA", location=(x, y, z))
    light_obj = bpy.context.active_object
    light_obj.name = name
    light_obj.data.energy = energy
    light_obj.data.size = distance * 0.5

    direction = mathutils.Vector(center) - mathutils.Vector((x, y, z))
    rot_quat = direction.to_track_quat("-Z", "Y")
    light_obj.rotation_euler = rot_quat.to_euler()
    return light_obj


def main() -> None:
    result_path: Path | None = None
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        import bpy

        manifest_path = _find_manifest_path()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        output_dir = Path(manifest["output_dir"])
        images_dir = output_dir / "images"
        result_path = output_dir / "render_result.json"

        # Validate output directory is within output_dir.
        try:
            images_dir.relative_to(output_dir)
        except ValueError:
            _fail(None, "OUTPUT_PATH_ESCAPE", "Images dir escapes output directory.")

        case_id: str = manifest["case_id"]
        session_id: str = manifest["session_id"]
        iteration: int = manifest["iteration"]
        source_path = Path(manifest["source_path"])
        params = manifest["params"]
        requested_views: list[str] = params["requested_views"]

        # ── Reset scene ──────────────────────────────────────────────────
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 0.001

        # ── Import STL ───────────────────────────────────────────────────
        import_result = bpy.ops.wm.stl_import(filepath=str(source_path))
        if "FINISHED" not in import_result:
            _fail(result_path, "STL_IMPORT_FAILED", f"STL import returned {import_result!r}.")

        mesh_objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        if not mesh_objects:
            _fail(result_path, "NO_MESH", "No mesh objects after STL import.")

        # ── Compute world-space bounding box center ───────────────────────
        import math

        import mathutils  # type: ignore[import]
        gmin = [math.inf, math.inf, math.inf]
        gmax = [-math.inf, -math.inf, -math.inf]
        for obj in mesh_objects:
            for local_corner in obj.bound_box:
                wc = obj.matrix_world @ mathutils.Vector(local_corner)
                for i in range(3):
                    if wc[i] < gmin[i]:
                        gmin[i] = wc[i]
                    if wc[i] > gmax[i]:
                        gmax[i] = wc[i]
        center = [(gmin[i] + gmax[i]) / 2.0 for i in range(3)]

        # ── Apply neutral material ────────────────────────────────────────
        mat_params = params.get("material", {})
        roughness = float(mat_params.get("roughness", 0.6))
        color = mat_params.get("color", [0.85, 0.80, 0.72, 1.0])

        mat = bpy.data.materials.new(name="STL_Material")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = tuple(color)
            bsdf.inputs["Roughness"].default_value = roughness

        for obj in mesh_objects:
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

        # ── World / background ────────────────────────────────────────────
        world = bpy.data.worlds.new(name="RenderWorld")
        scene.world = world
        world.use_nodes = True
        bg_node = world.node_tree.nodes.get("Background")
        if bg_node:
            bg_node.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)
            bg_node.inputs["Strength"].default_value = 0.0

        # ── Lighting rig ──────────────────────────────────────────────────
        lighting = params.get("lighting", {})
        key_p = lighting.get("key", {})
        fill_p = lighting.get("fill", {})
        rim_p = lighting.get("rim")

        _create_light(
            "Key",
            float(key_p.get("energy", 500)),
            float(key_p.get("yaw_deg", -45)),
            float(key_p.get("pitch_deg", 60)),
            float(key_p.get("distance", 10)),
            center,
        )
        _create_light(
            "Fill",
            float(fill_p.get("energy", 200)),
            float(fill_p.get("yaw_deg", 45)),
            float(fill_p.get("pitch_deg", 30)),
            float(fill_p.get("distance", 10)),
            center,
        )
        if rim_p:
            _create_light(
                "Rim",
                float(rim_p.get("energy", 300)),
                float(rim_p.get("yaw_deg", 180)),
                float(rim_p.get("pitch_deg", 20)),
                float(rim_p.get("distance", 10)),
                center,
            )

        # ── Render engine & resolution ───────────────────────────────────
        engine_map = {
            "BLENDER_EEVEE_NEXT": "BLENDER_EEVEE_NEXT",
            "CYCLES": "CYCLES",
        }
        engine = engine_map.get(params.get("engine", "BLENDER_EEVEE_NEXT"), "BLENDER_EEVEE_NEXT")
        scene.render.engine = engine
        scene.render.resolution_x = int(params.get("width", 1024))
        scene.render.resolution_y = int(params.get("height", 1024))
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"

        # ── Color management ─────────────────────────────────────────────
        cm = params.get("color_management", {})
        if hasattr(scene, "view_settings"):
            scene.view_settings.view_transform = cm.get("view_transform", "Filmic")
            scene.view_settings.look = cm.get("look", "None")
            scene.view_settings.exposure = float(cm.get("exposure", 0.0))
            scene.view_settings.gamma = float(cm.get("gamma", 1.0))

        # ── Render each view ─────────────────────────────────────────────
        images_dir.mkdir(parents=True, exist_ok=True)

        # Add and configure camera
        bpy.ops.object.camera_add()
        camera_obj = bpy.context.active_object
        camera_obj.name = "RenderCamera"
        scene.camera = camera_obj

        all_views = params.get("views", {})
        warnings: list[str] = []
        rendered_images: list[dict[str, Any]] = []

        for view_name in requested_views:
            view_params = all_views.get(view_name)
            if view_params is None:
                warnings.append(f"View '{view_name}' not found in params, skipping.")
                continue

            yaw = float(view_params.get("yaw_deg", 0.0))
            pitch = float(view_params.get("pitch_deg", 0.0))
            margin = float(view_params.get("margin", 0.1))
            use_ortho = bool(view_params.get("use_orthographic", False))

            camera_obj.data.type = "PERSP"  # reset each time

            if use_ortho:
                scale = float(view_params.get("ortho_scale") or 80.0) * (1.0 + margin)
                _place_camera_ortho(camera_obj, center, yaw, pitch, scale)
            else:
                dist_raw = view_params.get("distance")
                dist = float(dist_raw) if dist_raw is not None else 200.0
                dist = dist * (1.0 + margin)
                _place_camera_perspective(camera_obj, center, yaw, pitch, dist)

            # Set output path for this view
            output_image = images_dir / f"{view_name}.png"
            scene.render.filepath = str(output_image)

            render_result = bpy.ops.render.render(write_still=True)
            if "FINISHED" not in render_result:
                warnings.append(f"Render for view '{view_name}' did not finish cleanly.")
                continue

            if not output_image.exists() or output_image.stat().st_size == 0:
                warnings.append(f"Image for view '{view_name}' was not written.")
                continue

            # Validate path containment
            try:
                output_image.relative_to(output_dir)
            except ValueError:
                _fail(result_path, "OUTPUT_PATH_ESCAPE",
                      f"Image path {output_image} escapes output directory.")

            stat = output_image.stat()
            rendered_images.append({
                "view": view_name,
                "path": str(output_image),
                "width": scene.render.resolution_x,
                "height": scene.render.resolution_y,
                "size_bytes": stat.st_size,
            })

        blender_version = ".".join(str(v) for v in bpy.app.version)
        completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        result: dict[str, Any] = {
            "schema_version": "1",
            "script_version": "1",
            "case_id": case_id,
            "session_id": session_id,
            "iteration": iteration,
            "blender_version": blender_version,
            "images": rendered_images,
            "duration_seconds": 0.0,  # host will fill in actual duration
            "warnings": warnings,
            "started_at": started_at,
            "completed_at": completed_at,
        }

        _write_result(result_path, result)
        print(f"[render_views] OK: {len(rendered_images)} views rendered.", file=sys.stderr)

    except SystemExit:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[render_views] EXCEPTION: {exc}\n{tb}", file=sys.stderr)
        _fail(result_path, "UNEXPECTED_ERROR", str(exc))


if __name__ == "__main__":
    main()
