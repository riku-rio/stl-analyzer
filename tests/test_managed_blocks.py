from __future__ import annotations

import pytest

from stl_analyzer.filesystem.managed_blocks import (
    ManagedBlockConflict,
    ManagedBlockSpec,
    merge_managed_block,
    render_managed_block,
)

SPEC = ManagedBlockSpec("example", "# BEGIN EXAMPLE", "# END EXAMPLE")


def test_render_managed_block() -> None:
    assert render_managed_block("one\ntwo\n", SPEC) == "# BEGIN EXAMPLE\none\ntwo\n# END EXAMPLE"


def test_insert_into_empty_file() -> None:
    result = merge_managed_block("", "managed", SPEC)
    assert result.changed is True
    assert result.content == "# BEGIN EXAMPLE\nmanaged\n# END EXAMPLE\n"


def test_append_preserves_unmanaged_content() -> None:
    existing = "custom content\n"
    result = merge_managed_block(existing, "managed", SPEC)
    assert result.content.startswith(existing)
    assert "custom content" in result.content
    assert result.content.count(SPEC.begin_marker) == 1


def test_replace_existing_block_is_idempotent() -> None:
    existing = "before\n\n# BEGIN EXAMPLE\nold\n# END EXAMPLE\nafter\n"
    first = merge_managed_block(existing, "new", SPEC)
    second = merge_managed_block(first.content, "new", SPEC)
    assert first.content == "before\n\n# BEGIN EXAMPLE\nnew\n# END EXAMPLE\nafter\n"
    assert second.changed is False
    assert second.content == first.content


def test_preserves_crlf_style() -> None:
    existing = "before\r\n"
    result = merge_managed_block(existing, "line one\nline two", SPEC)
    assert "# BEGIN EXAMPLE\r\nline one\r\nline two\r\n# END EXAMPLE\r\n" in result.content


@pytest.mark.parametrize(
    "existing",
    [
        "# BEGIN EXAMPLE\nmissing end\n",
        "# END EXAMPLE\n",
        "# END EXAMPLE\n# BEGIN EXAMPLE\n",
        "# BEGIN EXAMPLE\none\n# BEGIN EXAMPLE\ntwo\n# END EXAMPLE\n",
    ],
)
def test_malformed_markers_are_conflicts(existing: str) -> None:
    with pytest.raises(ManagedBlockConflict):
        merge_managed_block(existing, "managed", SPEC)


def test_body_cannot_contain_markers() -> None:
    with pytest.raises(ManagedBlockConflict):
        merge_managed_block("", SPEC.begin_marker, SPEC)
