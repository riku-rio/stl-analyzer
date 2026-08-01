"""Image post-validation service (MVP-0605)."""

from __future__ import annotations

import struct
from pathlib import Path

from stl_analyzer.models.render_manifest import ImageInfo, RenderManifest


class ImageValidationWarning:
    def __init__(self, view: str, message: str) -> None:
        self.view = view
        self.message = message

    def __repr__(self) -> str:
        return f"ImageValidationWarning({self.view!r}, {self.message!r})"


def _read_png_dimensions(path: Path) -> tuple[int, int] | None:
    """Return (width, height) from a PNG header, or None on failure."""
    try:
        with path.open("rb") as fh:
            sig = fh.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return None
            # IHDR chunk: 4 length + 4 type + 4 width + 4 height + ...
            fh.read(4)  # length field of IHDR
            chunk_type = fh.read(4)
            if chunk_type != b"IHDR":
                return None
            width = struct.unpack(">I", fh.read(4))[0]
            height = struct.unpack(">I", fh.read(4))[0]
            return width, height
    except Exception:
        return None


def validate_rendered_images(
    *,
    manifest: RenderManifest,
    output_dir: Path,
    workspace_root: Path,
) -> tuple[list[ImageInfo], list[ImageValidationWarning]]:
    """Verify that rendered images exist, are non-zero, have correct dimensions,
    and remain inside the output directory.

    Returns:
        (images, warnings) where images is the validated list of ImageInfo objects.
    """
    images: list[ImageInfo] = []
    warnings: list[ImageValidationWarning] = []

    expected_w = manifest.params.width
    expected_h = manifest.params.height

    for view_name in manifest.params.requested_views:
        image_path = output_dir / "images" / f"{view_name}.png"

        # ── containment check ────────────────────────────────────────────
        try:
            image_path.resolve().relative_to(output_dir.resolve())
        except ValueError:
            warnings.append(
                ImageValidationWarning(
                    view_name,
                    f"Image path {image_path} escapes output directory.",
                )
            )
            continue

        # ── existence check ──────────────────────────────────────────────
        if not image_path.exists():
            warnings.append(
                ImageValidationWarning(view_name, f"Image file missing: {image_path.name}")
            )
            continue

        # ── non-zero size check ──────────────────────────────────────────
        size_bytes = image_path.stat().st_size
        if size_bytes == 0:
            warnings.append(
                ImageValidationWarning(view_name, f"Image file is empty: {image_path.name}")
            )
            continue

        # ── dimension check ──────────────────────────────────────────────
        dims = _read_png_dimensions(image_path)
        if dims is None:
            warnings.append(
                ImageValidationWarning(
                    view_name, f"Cannot read PNG dimensions for: {image_path.name}"
                )
            )
            # Still include with declared resolution; Blender produced it.
            w, h = expected_w, expected_h
        else:
            w, h = dims
            if w != expected_w or h != expected_h:
                warnings.append(
                    ImageValidationWarning(
                        view_name,
                        f"Image dimensions {w}x{h} do not match manifest "
                        f"{expected_w}x{expected_h}.",
                    )
                )

        # ── workspace-relative path ──────────────────────────────────────
        try:
            rel = image_path.relative_to(workspace_root)
            rel_str = rel.as_posix()
        except ValueError:
            rel_str = str(image_path)

        images.append(
            ImageInfo(
                view=view_name,
                path=rel_str,
                width=w,
                height=h,
                size_bytes=size_bytes,
            )
        )

    return images, warnings
