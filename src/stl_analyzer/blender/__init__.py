"""Blender integration boundary.

Blender-specific modules must not import ``bpy`` in the host Python runtime.
Scripts inside ``blender/scripts/`` are invoked via subprocess only.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent / "scripts"


def get_script(name: str) -> Path:
    """Return the absolute path to a bundled Blender script.

    Args:
        name: Filename of the script, e.g. ``"inspect_geometry.py"``.

    Raises:
        FileNotFoundError: If the script does not exist in the package.
    """
    script = _SCRIPTS_DIR / name
    if not script.is_file():
        raise FileNotFoundError(
            f"Bundled Blender script not found: {name!r} (expected at {script})"
        )
    return script
