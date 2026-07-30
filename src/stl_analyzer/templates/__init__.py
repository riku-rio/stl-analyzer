"""Versioned package-resource templates for initialized workspaces."""

from importlib.resources import files

from stl_analyzer.filesystem.managed_blocks import ManagedBlockSpec
from stl_analyzer.schema import WORKSPACE_TEMPLATE_VERSION

CONFIG_TEMPLATE = "stl-analyzer.toml"
SKILL_TEMPLATE = "SKILL.md"
AGENTS_TEMPLATE = "AGENTS.md.block"
CLAUDE_TEMPLATE = "CLAUDE.md.block"
GITIGNORE_TEMPLATE = "gitignore.block"

CONFIG_MARKER = f"# stl-analyzer:managed-config template-version={WORKSPACE_TEMPLATE_VERSION}"
SKILL_MARKER = f"<!-- stl-analyzer:managed-skill template-version={WORKSPACE_TEMPLATE_VERSION} -->"

AGENTS_BLOCK = ManagedBlockSpec(
    name="AGENTS.md",
    begin_marker="<!-- BEGIN STL-ANALYZER:AGENTS -->",
    end_marker="<!-- END STL-ANALYZER:AGENTS -->",
)
CLAUDE_BLOCK = ManagedBlockSpec(
    name="CLAUDE.md",
    begin_marker="<!-- BEGIN STL-ANALYZER:CLAUDE -->",
    end_marker="<!-- END STL-ANALYZER:CLAUDE -->",
)
GITIGNORE_BLOCK = ManagedBlockSpec(
    name=".gitignore",
    begin_marker="# BEGIN STL-ANALYZER:GITIGNORE",
    end_marker="# END STL-ANALYZER:GITIGNORE",
)


def load_template(name: str) -> str:
    """Load one UTF-8 template from installed package resources."""

    return files(__package__).joinpath(name).read_text(encoding="utf-8")
