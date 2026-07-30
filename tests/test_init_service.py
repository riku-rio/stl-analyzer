from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stl_analyzer.errors import DomainError
from stl_analyzer.models.init import ActionKind
from stl_analyzer.services.init_service import InitService
from stl_analyzer.templates import CONFIG_TEMPLATE, load_template


def snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | None]] | None:
    if not root.exists():
        return None
    snapshot: dict[str, tuple[str, bytes | None]] = {".": ("directory", None)}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", None)
        else:
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


def test_plan_does_not_mutate_missing_target(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "workspace"
    plan = InitService().plan(target)
    assert plan.workspace == target.resolve()
    assert not target.exists()
    assert any(action.path == "." and action.action is ActionKind.CREATE for action in plan.actions)


def test_initialize_fresh_existing_directory(tmp_path: Path) -> None:
    result = InitService().initialize(tmp_path)
    expected = {
        "stl-analyzer.toml",
        "SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        ".gitignore",
        "stl",
        "stl/.gitkeep",
    }
    assert expected.issubset(set(snapshot_tree(tmp_path) or {}))
    assert result.workspace == str(tmp_path.resolve())
    assert "stl-analyzer doctor --json" in result.next_commands
    assert "." in result.unchanged


def test_initialize_missing_target(tmp_path: Path) -> None:
    target = tmp_path / "new" / "workspace"
    result = InitService().initialize(target)
    assert target.is_dir()
    assert "." in result.created
    assert (target / "stl" / ".gitkeep").is_file()


def test_existing_unmanaged_content_is_preserved(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("keep me", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("custom.log\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Existing agents guidance\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Existing Claude guidance\n", encoding="utf-8")

    InitService().initialize(tmp_path)

    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").startswith("custom.log\n")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8").startswith(
        "# Existing agents guidance\n"
    )
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8").startswith(
        "# Existing Claude guidance\n"
    )


def test_existing_stl_cases_are_never_changed(tmp_path: Path) -> None:
    source = tmp_path / "stl" / "case-001" / "upper.stl"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"solid test\nendsolid test\n")
    before = source.read_bytes()

    InitService().initialize(tmp_path)

    assert source.read_bytes() == before
    assert not (source.parent / "assets").exists()
    assert (tmp_path / "stl" / ".gitkeep").is_file()


def test_rerun_is_byte_equivalent_and_reports_unchanged(tmp_path: Path) -> None:
    service = InitService()
    service.initialize(tmp_path)
    first = snapshot_tree(tmp_path)
    second_result = service.initialize(tmp_path)
    second = snapshot_tree(tmp_path)

    assert second == first
    assert second_result.created == []
    assert second_result.updated == []
    assert set(second_result.unchanged) == {
        ".",
        "stl-analyzer.toml",
        "SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        ".gitignore",
        "stl",
        "stl/.gitkeep",
    }


def test_conflicting_skill_aborts_without_changes(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("# User-owned skill\n", encoding="utf-8")
    before = snapshot_tree(tmp_path)

    with pytest.raises(DomainError) as raised:
        InitService().initialize(tmp_path)

    assert raised.value.code == "INIT_CONFLICT"
    assert snapshot_tree(tmp_path) == before
    conflicts = raised.value.details["conflicts"]
    assert any(item["path"] == "SKILL.md" for item in conflicts)


def test_invalid_configuration_aborts_without_changes(tmp_path: Path) -> None:
    (tmp_path / "stl-analyzer.toml").write_text("not = [valid", encoding="utf-8")
    before = snapshot_tree(tmp_path)

    with pytest.raises(DomainError) as raised:
        InitService().initialize(tmp_path)

    assert raised.value.code == "INIT_CONFLICT"
    assert snapshot_tree(tmp_path) == before


def test_unmanaged_valid_configuration_is_a_conflict(tmp_path: Path) -> None:
    (tmp_path / "stl-analyzer.toml").write_text(
        '[project]\nstl_root = "stl"\n', encoding="utf-8"
    )
    with pytest.raises(DomainError) as raised:
        InitService().initialize(tmp_path)
    assert raised.value.code == "INIT_CONFLICT"


def test_managed_configuration_is_preserved_and_controls_stl_root(tmp_path: Path) -> None:
    config = load_template(CONFIG_TEMPLATE).replace('stl_root = "stl"', 'stl_root = "data/scans"')
    (tmp_path / "stl-analyzer.toml").write_text(config, encoding="utf-8")

    result = InitService().initialize(tmp_path)

    assert (tmp_path / "data" / "scans" / ".gitkeep").is_file()
    assert not (tmp_path / "stl").exists()
    assert "data/scans" in result.created
    assert (tmp_path / "stl-analyzer.toml").read_text(encoding="utf-8") == config


def test_malformed_managed_markers_abort(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "<!-- BEGIN STL-ANALYZER:AGENTS -->\nmissing end\n", encoding="utf-8"
    )
    before = snapshot_tree(tmp_path)
    with pytest.raises(DomainError) as raised:
        InitService().initialize(tmp_path)
    assert raised.value.code == "INIT_CONFLICT"
    assert snapshot_tree(tmp_path) == before


def test_transaction_rolls_back_after_injected_failure(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Existing\n", encoding="utf-8")
    before = snapshot_tree(tmp_path)

    def fail_after_third_write(index: int, _action: Any) -> None:
        if index == 3:
            raise OSError("simulated write failure")

    with pytest.raises(DomainError) as raised:
        InitService().initialize(tmp_path, failure_injector=fail_after_third_write)

    assert raised.value.code == "INIT_COMMIT_FAILED"
    assert raised.value.details["rollback_succeeded"] is True
    assert raised.value.details["uncertain_paths"] == []
    assert snapshot_tree(tmp_path) == before


def test_transaction_removes_new_target_after_failure(tmp_path: Path) -> None:
    target = tmp_path / "new-workspace"

    def fail_immediately(_index: int, _action: Any) -> None:
        raise RuntimeError("stop")

    with pytest.raises(DomainError):
        InitService().initialize(target, failure_injector=fail_immediately)
    assert not target.exists()


def test_existing_target_file_fails_cleanly(tmp_path: Path) -> None:
    target = tmp_path / "workspace"
    target.write_text("file", encoding="utf-8")
    with pytest.raises(DomainError) as raised:
        InitService().plan(target)
    assert raised.value.code == "TARGET_NOT_DIRECTORY"
