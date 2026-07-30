"""Idempotent managed-block merging for shared workspace files."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ManagedBlockSpec:
    """Stable marker pair for one managed file."""

    name: str
    begin_marker: str
    end_marker: str


@dataclass(frozen=True, slots=True)
class ManagedBlockMerge:
    """Result of merging one managed block."""

    content: str
    changed: bool


class ManagedBlockConflict(ValueError):
    """Raised when markers are malformed or duplicated."""


def detect_newline(content: str) -> str:
    """Prefer the existing CRLF style when present."""

    return "\r\n" if "\r\n" in content else "\n"


def _normalize_body(body: str) -> list[str]:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    return normalized.split("\n") if normalized else []


def render_managed_block(body: str, spec: ManagedBlockSpec, newline: str = "\n") -> str:
    """Render a complete block using the requested newline style."""

    body_lines = _normalize_body(body)
    lines = [spec.begin_marker, *body_lines, spec.end_marker]
    return newline.join(lines)


def merge_managed_block(existing: str, body: str, spec: ManagedBlockSpec) -> ManagedBlockMerge:
    """Insert or replace one managed block while preserving all unmanaged text."""

    if spec.begin_marker in body or spec.end_marker in body:
        raise ManagedBlockConflict(f"Managed block body for {spec.name} contains its own markers.")

    newline = detect_newline(existing)
    rendered = render_managed_block(body, spec, newline)
    lines = existing.splitlines(keepends=True)

    begin_indexes = [
        index for index, line in enumerate(lines) if line.rstrip("\r\n") == spec.begin_marker
    ]
    end_indexes = [
        index for index, line in enumerate(lines) if line.rstrip("\r\n") == spec.end_marker
    ]

    if not begin_indexes and not end_indexes:
        if not existing:
            merged = rendered + newline
        else:
            prefix = existing
            if not prefix.endswith(("\n", "\r")):
                prefix += newline
            if not prefix.endswith(newline * 2):
                prefix += newline
            merged = prefix + rendered + newline
        return ManagedBlockMerge(content=merged, changed=merged != existing)

    if len(begin_indexes) != 1 or len(end_indexes) != 1:
        raise ManagedBlockConflict(
            f"Managed markers for {spec.name} are missing, duplicated, or unbalanced."
        )

    begin_index = begin_indexes[0]
    end_index = end_indexes[0]
    if begin_index >= end_index:
        raise ManagedBlockConflict(f"Managed markers for {spec.name} are in the wrong order.")

    prefix = "".join(lines[:begin_index])
    suffix = "".join(lines[end_index + 1 :])
    merged = prefix + rendered + newline + suffix
    return ManagedBlockMerge(content=merged, changed=merged != existing)
