"""Injectable clocks and filesystem-safe sortable identifiers."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Minimal UTC clock contract."""

    def now(self) -> datetime:
        """Return the current instant."""
        ...


class SystemClock:
    """Production UTC clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Deterministic clock for tests."""

    instant: datetime

    def now(self) -> datetime:
        if self.instant.tzinfo is None:
            return self.instant.replace(tzinfo=UTC)
        return self.instant.astimezone(UTC)


def new_session_id(
    clock: Clock | None = None,
    token_factory: Callable[[], str] | None = None,
) -> str:
    """Create a sortable, Windows-safe session identifier."""

    instant = (clock or SystemClock()).now().astimezone(UTC)
    token = (token_factory or (lambda: secrets.token_hex(2)))().lower()
    if len(token) != 4 or any(character not in "0123456789abcdef" for character in token):
        raise ValueError(
            "Session ID token factories must return exactly four hexadecimal characters."
        )
    return f"{instant:%Y%m%dT%H%M%SZ}-{token}"
