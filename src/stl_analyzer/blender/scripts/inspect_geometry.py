"""
Blender inspection script — runs inside Blender's Python environment (MVP-0503).

Invocation:
    blender --background --python inspect_geometry.py -- <manifest_path>

The manifest_path argument must point to a JSON file whose schema matches
stl_analyzer.models.geometry.InspectionManifest.

The script writes a JSON result to the path specified in manifest["output_path"].
It never writes outside that path.
"""

from __future__ import annotations

import json
import math
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _find_manifest_path() -> Path:
    """Extract the manifest path from the '--' separator in sys.argv."""
    try:
        separator = sys.argv.index("--")
        return Path(sys.argv[separator + 1])
    except (ValueError, IndexError):
        raise RuntimeError(
            "Usage: blender --background --python inspect_geometry.py -- <manifest_path>"
        )


def _write_result(output_path: Path, payload: dict[str, Any]) -> None:
    """Write the result JSON atomically-ish to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _fail(output_path: Path | None, code: str, message: str) -> None:
    """Write a structured failure result and exit with code 1."""
    payload: dict[str, Any] = {
        "ok": False,
        "error": {"code": code, "message": message},
    }
    if output_path is not None:
        _write_result(output_path, payload)
    print(f"[inspect_geometry] FAILURE {code}: {message}", file=sys.stderr)
    sys.exit(1)


def _compute_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _count_components(mesh_obj: Any) -> int | None:
    """Count connected components via BFS on the mesh.  Returns None on failure."""
    try:
        import bmesh  # type: ignore[import]

        bm = bmesh.new()
        bm.from_mesh(mesh_obj.data)
        bm.verts.ensure_lookup_table()

        visited: set[int] = set()
        components = 0

        for start in bm.verts:
            if start.index in visited:
                continue
            components += 1
            queue = [start]
            while queue:
                v = queue.pop()
                if v.index in visited:
                    continue
                visited.add(v.index)
                for edge in v.link_edges:
                    other = edge.other_vert(v)
                    if other.index not in visited:
                        queue.append(other)

        bm.free()
        return components
    except Exception:
        return None


def main() -> None:
    output_path: Path | None = None
    try:
        import bpy

        manifest_path = _find_manifest_path()
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)

        output_path = Path(manifest["output_path"])
        source_path = Path(manifest["source_path"])
        case_id = manifest["case_id"]
        expected_hash = manifest["expected_hash"]
        assumed_unit = manifest.get("assumed_unit", "millimeters")

        # Verify the output path is within the declared parent directory.
        output_parent = output_path.parent
        try:
            output_path.relative_to(output_parent)
        except ValueError:
            _fail(None, "OUTPUT_PATH_ESCAPE", "Output path escapes declared output directory.")

        # Compute source hash to verify integrity.
        actual_hash = _compute_sha256(source_path)
        source_size = source_path.stat().st_size

        warnings: list[str] = []
        if actual_hash != expected_hash:
            warnings.append(
                f"Source hash mismatch: expected {expected_hash!r}, "
                f"got {actual_hash!r}."
            )

        # Reset to a known empty scene.
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # Ensure metric units (millimeters) to avoid scale distortion.
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 0.001

        # Import the STL.
        import_result = bpy.ops.wm.stl_import(filepath=str(source_path))
        if "FINISHED" not in import_result:
            _fail(
                output_path,
                "STL_IMPORT_FAILED",
                f"bpy.ops.wm.stl_import returned {import_result!r}.",
            )

        # Collect mesh objects.
        mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        if not mesh_objects:
            _fail(output_path, "NO_MESH", "No mesh objects found after STL import.")

        # Aggregate statistics across all mesh objects.
        total_vertices = 0
        total_polygons = 0
        global_min = [math.inf, math.inf, math.inf]
        global_max = [-math.inf, -math.inf, -math.inf]
        total_components: int | None = 0

        for obj in mesh_objects:
            mesh = obj.data
            total_vertices += len(mesh.vertices)
            total_polygons += len(mesh.polygons)

            # Bounding box in world space.
            world_matrix = obj.matrix_world
            for local_corner in obj.bound_box:
                world_corner = world_matrix @ __import__("mathutils").Vector(local_corner)
                for i in range(3):
                    if world_corner[i] < global_min[i]:
                        global_min[i] = world_corner[i]
                    if world_corner[i] > global_max[i]:
                        global_max[i] = world_corner[i]

            # Count connected components (only for single-object imports in MVP).
            if total_components is not None and len(mesh_objects) == 1:
                total_components = _count_components(obj)
            else:
                total_components = None  # Multi-object: skip for MVP

        dimensions = [
            round(global_max[i] - global_min[i], 6) for i in range(3)
        ]
        center = [
            round((global_max[i] + global_min[i]) / 2.0, 6) for i in range(3)
        ]

        blender_version = ".".join(str(v) for v in bpy.app.version)

        tool_version = manifest.get("tool_version", "")

        result: dict[str, Any] = {
            "schema_version": "1",
            "script_version": "1",
            "tool_version": tool_version,
            "case_id": case_id,
            "source_path": str(source_path),
            "source_sha256": actual_hash,
            "source_size_bytes": source_size,
            "blender_version": blender_version,
            "vertex_count": total_vertices,
            "polygon_count": total_polygons,
            "object_count": len(mesh_objects),
            "component_count": total_components,
            "bounding_box": {
                "min": [round(v, 6) for v in global_min],
                "max": [round(v, 6) for v in global_max],
            },
            "dimensions": dimensions,
            "center": center,
            "assumed_unit": assumed_unit,
            "warnings": warnings,
            "inspection_timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        _write_result(output_path, result)
        print(f"[inspect_geometry] OK: {source_path}", file=sys.stderr)

    except SystemExit:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[inspect_geometry] EXCEPTION: {exc}\n{tb}", file=sys.stderr)
        _fail(output_path, "UNEXPECTED_ERROR", str(exc))


if __name__ == "__main__":
    main()
