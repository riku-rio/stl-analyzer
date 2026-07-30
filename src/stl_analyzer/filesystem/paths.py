"""Safe path normalization and containment primitives."""

from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath

from stl_analyzer.errors import PathSafetyError

_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def _raw_path(value: str | os.PathLike[str]) -> str:
    raw = os.fspath(value)
    if "\x00" in raw:
        raise PathSafetyError("Paths must not contain null bytes.", details={"path": raw})
    return raw


def normalize_path(
    value: str | os.PathLike[str], *, base: Path | None = None
) -> Path:
    """Return an absolute normalized path without requiring it to exist.

    Windows drive-qualified paths are rejected on non-Windows hosts instead of
    being silently interpreted as relative POSIX paths.
    """

    raw = _raw_path(value)
    if os.name != "nt" and (_WINDOWS_ABSOLUTE.match(raw) or PureWindowsPath(raw).is_absolute()):
        raise PathSafetyError(
            "A Windows absolute path cannot be resolved on this operating system.",
            details={"path": raw},
        )

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (base or Path.cwd()) / candidate
    return candidate.resolve(strict=False)


def is_path_within(root: Path, candidate: Path) -> bool:
    """Return whether ``candidate`` resolves within ``root``."""

    root_resolved = root.resolve(strict=False)
    candidate_resolved = candidate.resolve(strict=False)
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError:
        return False
    return True


def resolve_within(
    root: Path,
    value: str | os.PathLike[str],
    *,
    allow_root: bool = True,
) -> Path:
    """Resolve a path and reject traversal or symlink escape from ``root``."""

    root_resolved = root.resolve(strict=False)
    raw = _raw_path(value)
    if os.name != "nt" and (_WINDOWS_ABSOLUTE.match(raw) or PureWindowsPath(raw).is_absolute()):
        raise PathSafetyError(
            "A Windows absolute path cannot be resolved on this operating system.",
            details={"path": raw, "root": str(root_resolved)},
        )

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    candidate_resolved = candidate.resolve(strict=False)

    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathSafetyError(
            "The resolved path escapes the approved root.",
            details={"path": raw, "root": str(root_resolved)},
        ) from exc

    if not allow_root and candidate_resolved == root_resolved:
        raise PathSafetyError(
            "The approved root itself is not a valid target for this operation.",
            details={"path": raw, "root": str(root_resolved)},
        )
    return candidate_resolved


def resolve_case_path(stl_root: Path, case_id: str) -> Path:
    """Resolve a case ID as exactly one direct child of the STL root."""

    if not case_id or case_id in {".", ".."}:
        raise PathSafetyError("Case IDs must be non-empty direct child names.", details={"case_id": case_id})
    if "/" in case_id or "\\" in case_id:
        raise PathSafetyError(
            "Case IDs must not contain path separators.", details={"case_id": case_id}
        )
    windows = PureWindowsPath(case_id)
    if windows.drive or windows.root:
        raise PathSafetyError(
            "Case IDs must not be absolute or drive-qualified.", details={"case_id": case_id}
        )

    root_resolved = stl_root.resolve(strict=False)
    resolved = resolve_within(root_resolved, case_id, allow_root=False)
    if resolved.parent != root_resolved:
        raise PathSafetyError(
            "Case IDs must resolve to an immediate child of the STL root.",
            details={"case_id": case_id, "stl_root": str(root_resolved)},
        )
    return resolved


def nearest_existing_parent(path: Path) -> Path:
    """Return the nearest existing ancestor, including ``path`` itself."""

    current = path.resolve(strict=False)
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current
