from __future__ import annotations

import os
from pathlib import Path

import pytest

from stl_analyzer.errors import PathSafetyError
from stl_analyzer.filesystem.paths import (
    is_path_within,
    nearest_existing_parent,
    normalize_path,
    resolve_case_path,
    resolve_within,
)


def test_normalize_relative_path(tmp_path: Path) -> None:
    assert normalize_path("workspace", base=tmp_path) == (tmp_path / "workspace").resolve()


def test_resolve_within_accepts_child(tmp_path: Path) -> None:
    resolved = resolve_within(tmp_path, "case/assets")
    assert resolved == (tmp_path / "case" / "assets").resolve()
    assert is_path_within(tmp_path, resolved)


def test_resolve_within_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(PathSafetyError):
        resolve_within(tmp_path, "../outside")


def test_resolve_within_rejects_absolute_outside(tmp_path: Path) -> None:
    with pytest.raises(PathSafetyError):
        resolve_within(tmp_path, tmp_path.parent / "outside")


def test_resolve_within_can_reject_root_itself(tmp_path: Path) -> None:
    with pytest.raises(PathSafetyError):
        resolve_within(tmp_path, ".", allow_root=False)


@pytest.mark.skipif(os.name == "nt", reason="POSIX-specific interpretation guard")
def test_windows_absolute_path_is_not_treated_as_relative(tmp_path: Path) -> None:
    with pytest.raises(PathSafetyError):
        normalize_path(r"C:\Cases\scan")
    with pytest.raises(PathSafetyError):
        resolve_within(tmp_path, r"C:\Cases\scan")


def test_case_path_requires_direct_child(tmp_path: Path) -> None:
    assert resolve_case_path(tmp_path, "case-001") == (tmp_path / "case-001").resolve()
    for invalid in ["", ".", "..", "a/b", r"a\b", r"C:\case"]:
        with pytest.raises(PathSafetyError):
            resolve_case_path(tmp_path, invalid)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks are not available on this platform")
    with pytest.raises(PathSafetyError):
        resolve_within(tmp_path, "link/file.txt")


def test_nearest_existing_parent(tmp_path: Path) -> None:
    assert nearest_existing_parent(tmp_path / "a" / "b") == tmp_path.resolve()
