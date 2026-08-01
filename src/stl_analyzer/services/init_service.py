"""Transactional workspace initialization planning and commit service."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

from stl_analyzer.errors import DomainError
from stl_analyzer.filesystem.atomic import atomic_write_bytes, atomic_write_text
from stl_analyzer.filesystem.managed_blocks import (
    ManagedBlockConflict,
    ManagedBlockSpec,
    merge_managed_block,
    render_managed_block,
)
from stl_analyzer.filesystem.paths import nearest_existing_parent, normalize_path, resolve_within
from stl_analyzer.models.common import ExitCode
from stl_analyzer.models.init import (
    ActionKind,
    InitActionRecord,
    InitPlan,
    InitResult,
    NodeKind,
    PlannedAction,
)
from stl_analyzer.schema import CURRENT_SCHEMA_VERSION, WORKSPACE_TEMPLATE_VERSION
from stl_analyzer.templates import (
    AGENTS_BLOCK,
    AGENTS_TEMPLATE,
    CLAUDE_BLOCK,
    CLAUDE_TEMPLATE,
    CONFIG_MARKER,
    CONFIG_TEMPLATE,
    GITIGNORE_BLOCK,
    GITIGNORE_TEMPLATE,
    SKILL_TEMPLATE,
    load_template,
)

FailureInjector = Callable[[int, PlannedAction], None]
_REQUIRED_CONFIG_SECTIONS = {"project", "blender", "scan", "render", "workflow", "output"}


class InitService:
    """Plan and transactionally initialize an agent-ready workspace."""

    def plan(self, target: str | os.PathLike[str] | None = None) -> InitPlan:
        workspace = normalize_path(target or ".")
        if workspace.exists() and not workspace.is_dir():
            raise DomainError(
                code="TARGET_NOT_DIRECTORY",
                message="The initialization target exists and is not a directory.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={"path": str(workspace)},
                recoverable=True,
                suggested_action="Choose a missing path or an existing directory.",
            )

        actions: list[PlannedAction] = [
            self._checked(
                PlannedAction(
                    ".",
                    workspace,
                    ActionKind.UNCHANGED if workspace.exists() else ActionKind.CREATE,
                    NodeKind.DIRECTORY,
                )
            )
        ]
        config = load_template(CONFIG_TEMPLATE)
        config_action, effective_config = self._plan_config(workspace, config)
        actions.append(self._checked(config_action))
        actions.append(self._checked(self._plan_skill(workspace, load_template(SKILL_TEMPLATE))))
        for name, template, spec in (
            ("AGENTS.md", AGENTS_TEMPLATE, AGENTS_BLOCK),
            ("CLAUDE.md", CLAUDE_TEMPLATE, CLAUDE_BLOCK),
            (".gitignore", GITIGNORE_TEMPLATE, GITIGNORE_BLOCK),
        ):
            actions.append(
                self._checked(self._plan_managed(workspace, name, load_template(template), spec))
            )

        try:
            stl_relative = self._stl_root(effective_config)
            stl_root = resolve_within(workspace, stl_relative, allow_root=False)
        except (ValueError, tomllib.TOMLDecodeError, DomainError) as exc:
            actions.append(
                PlannedAction(
                    "stl-analyzer.toml",
                    workspace / "stl-analyzer.toml",
                    ActionKind.CONFLICT,
                    NodeKind.FILE,
                    reason=f"Invalid STL root: {exc}",
                )
            )
            stl_relative, stl_root = "stl", workspace / "stl"

        if stl_root.exists() and not stl_root.is_dir():
            actions.append(
                PlannedAction(
                    stl_relative,
                    stl_root,
                    ActionKind.CONFLICT,
                    NodeKind.DIRECTORY,
                    reason="The configured STL root is not a directory.",
                )
            )
        else:
            actions.append(
                self._checked(
                    PlannedAction(
                        stl_relative,
                        stl_root,
                        ActionKind.UNCHANGED if stl_root.exists() else ActionKind.CREATE,
                        NodeKind.DIRECTORY,
                    )
                )
            )
        gitkeep = stl_root / ".gitkeep"
        if gitkeep.exists() and not gitkeep.is_file():
            actions.append(
                PlannedAction(
                    f"{stl_relative}/.gitkeep",
                    gitkeep,
                    ActionKind.CONFLICT,
                    NodeKind.FILE,
                    reason="The .gitkeep path is not a file.",
                )
            )
        else:
            actions.append(
                self._checked(
                    PlannedAction(
                        f"{stl_relative}/.gitkeep",
                        gitkeep,
                        ActionKind.UNCHANGED if gitkeep.exists() else ActionKind.CREATE,
                        NodeKind.FILE,
                        content=None if gitkeep.exists() else "",
                    )
                )
            )
        return InitPlan(workspace, tuple(actions))

    def initialize(
        self,
        target: str | os.PathLike[str] | None = None,
        *,
        failure_injector: FailureInjector | None = None,
    ) -> InitResult:
        plan = self.plan(target)
        if plan.has_conflicts:
            raise DomainError(
                code="INIT_CONFLICT",
                message="Workspace initialization found conflicts and made no changes.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={
                    "workspace": str(plan.workspace),
                    "conflicts": [self._record(a).model_dump(mode="json") for a in plan.conflicts],
                },
                recoverable=True,
                suggested_action="Resolve the reported conflicts and run init again.",
            )
        return self.commit(plan, failure_injector=failure_injector)

    def commit(
        self, plan: InitPlan, *, failure_injector: FailureInjector | None = None
    ) -> InitResult:
        if plan.has_conflicts:
            raise ValueError("Cannot commit a plan with conflicts.")
        snapshots: list[tuple[Path, bytes | None]] = []
        created_dirs: list[Path] = []
        operation = 0
        try:
            for action in plan.actions:
                if action.action is ActionKind.UNCHANGED:
                    continue
                if action.node_kind is NodeKind.DIRECTORY:
                    if not action.absolute_path.exists():
                        action.absolute_path.mkdir(parents=True)
                        created_dirs.append(action.absolute_path)
                else:
                    action.absolute_path.parent.mkdir(parents=True, exist_ok=True)
                    old = (
                        action.absolute_path.read_bytes() if action.absolute_path.exists() else None
                    )
                    snapshots.append((action.absolute_path, old))
                    if action.content is None:
                        raise ValueError(f"Missing planned content for {action.path}")
                    atomic_write_text(action.absolute_path, action.content)
                operation += 1
                if failure_injector:
                    failure_injector(operation, action)
        except BaseException as exc:
            uncertain: list[str] = []
            for path, old in reversed(snapshots):
                try:
                    if old is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write_bytes(path, old)
                except BaseException:
                    uncertain.append(str(path))
            for path in reversed(created_dirs):
                try:
                    path.rmdir()
                except BaseException:
                    if path.exists():
                        uncertain.append(str(path))
            raise DomainError(
                code="INIT_COMMIT_FAILED",
                message="Workspace initialization failed during commit; rollback was attempted.",
                exit_code=ExitCode.WORKSPACE_ERROR,
                details={
                    "cause_type": type(exc).__name__,
                    "uncertain_paths": sorted(set(uncertain)),
                    "rollback_succeeded": not uncertain,
                },
                recoverable=True,
                suggested_action="Inspect uncertain paths and run init again.",
            ) from exc

        records = [self._record(a) for a in plan.actions]
        return InitResult(
            workspace=str(plan.workspace),
            created=[a.path for a in plan.actions if a.action is ActionKind.CREATE],
            updated=[a.path for a in plan.actions if a.action is ActionKind.UPDATE],
            unchanged=[a.path for a in plan.actions if a.action is ActionKind.UNCHANGED],
            actions=records,
            next_commands=["stl-analyzer doctor --json", "stl-analyzer cases list --json"],
        )

    def _plan_config(self, workspace: Path, template: str) -> tuple[PlannedAction, str]:
        path = workspace / "stl-analyzer.toml"
        if not path.exists():
            return PlannedAction(
                "stl-analyzer.toml", path, ActionKind.CREATE, NodeKind.FILE, content=template
            ), template
        if not path.is_file():
            return PlannedAction(
                "stl-analyzer.toml",
                path,
                ActionKind.CONFLICT,
                NodeKind.FILE,
                reason="Configuration path is not a file.",
            ), template
        try:
            existing = path.read_text(encoding="utf-8")
            self._validate_config(existing)
        except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError) as exc:
            return PlannedAction(
                "stl-analyzer.toml", path, ActionKind.CONFLICT, NodeKind.FILE, reason=str(exc)
            ), template
        return PlannedAction(
            "stl-analyzer.toml", path, ActionKind.UNCHANGED, NodeKind.FILE
        ), existing

    def _plan_skill(self, workspace: Path, template: str) -> PlannedAction:
        path = workspace / "SKILL.md"
        if not path.exists():
            return PlannedAction(
                "SKILL.md", path, ActionKind.CREATE, NodeKind.FILE, content=template
            )
        if not path.is_file():
            return PlannedAction(
                "SKILL.md",
                path,
                ActionKind.CONFLICT,
                NodeKind.FILE,
                reason="SKILL.md is not a file.",
            )
        existing = path.read_text(encoding="utf-8")
        if existing == template:
            return PlannedAction("SKILL.md", path, ActionKind.UNCHANGED, NodeKind.FILE)
        marker = (
            f"<!-- stl-analyzer:managed-skill template-version={WORKSPACE_TEMPLATE_VERSION} -->"
        )
        if not existing.startswith(marker):
            return PlannedAction(
                "SKILL.md",
                path,
                ActionKind.CONFLICT,
                NodeKind.FILE,
                reason="Existing SKILL.md is unmanaged.",
            )
        return PlannedAction("SKILL.md", path, ActionKind.UPDATE, NodeKind.FILE, content=template)

    def _plan_managed(
        self, workspace: Path, name: str, body: str, spec: ManagedBlockSpec
    ) -> PlannedAction:
        path = workspace / name
        if not path.exists():
            return PlannedAction(
                name,
                path,
                ActionKind.CREATE,
                NodeKind.FILE,
                content=render_managed_block(body, spec) + "\n",
            )
        if not path.is_file():
            return PlannedAction(
                name, path, ActionKind.CONFLICT, NodeKind.FILE, reason=f"{name} is not a file."
            )
        try:
            merged = merge_managed_block(path.read_text(encoding="utf-8"), body, spec)
        except (OSError, UnicodeError, ManagedBlockConflict) as exc:
            return PlannedAction(name, path, ActionKind.CONFLICT, NodeKind.FILE, reason=str(exc))
        return PlannedAction(
            name,
            path,
            ActionKind.UPDATE if merged.changed else ActionKind.UNCHANGED,
            NodeKind.FILE,
            content=merged.content if merged.changed else None,
        )

    def _validate_config(self, content: str) -> None:
        if not content.startswith(CONFIG_MARKER):
            raise ValueError("Existing stl-analyzer.toml is unmanaged.")
        parsed = tomllib.loads(content)
        if (
            parsed.get("schema_version") != CURRENT_SCHEMA_VERSION
            or parsed.get("template_version") != WORKSPACE_TEMPLATE_VERSION
        ):
            raise ValueError("Unsupported configuration schema or template version.")
        missing = sorted(_REQUIRED_CONFIG_SECTIONS.difference(parsed))
        if missing:
            raise ValueError(f"Missing configuration sections: {', '.join(missing)}")
        self._stl_root(content)

    def _stl_root(self, content: str) -> str:
        value = tomllib.loads(content).get("project", {}).get("stl_root")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("project.stl_root must be a non-empty relative path.")
        raw = value.strip()
        windows = PureWindowsPath(raw)
        if (
            Path(raw).is_absolute()
            or windows.is_absolute()
            or windows.drive
            or any(part in {".", ".."} for part in windows.parts)
        ):
            raise ValueError("project.stl_root must be workspace-relative without traversal.")
        return raw

    def _checked(self, action: PlannedAction) -> PlannedAction:
        if action.action not in {ActionKind.CREATE, ActionKind.UPDATE}:
            return action
        parent = nearest_existing_parent(
            action.absolute_path
            if action.node_kind is NodeKind.DIRECTORY
            else action.absolute_path.parent
        )
        if not os.access(parent, os.W_OK):
            return PlannedAction(
                action.path,
                action.absolute_path,
                ActionKind.CONFLICT,
                action.node_kind,
                reason=f"Parent is not writable: {parent}",
            )
        return action

    @staticmethod
    def _record(action: PlannedAction) -> InitActionRecord:
        return InitActionRecord(
            path=action.path, action=action.action, node_kind=action.node_kind, reason=action.reason
        )
