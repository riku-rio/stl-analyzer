"""Append-only event log service (MVP-0702)."""

from __future__ import annotations

import json
from pathlib import Path

from stl_analyzer.models.session import EventRecord


class EventLog:
    """Append-only JSON Lines event log for a session."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, event: EventRecord) -> None:
        """Append one event record as a JSON line."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    def read_all(self) -> list[EventRecord]:
        """Read and return all event records, ignoring a truncated final line."""
        if not self._path.exists():
            return []
        records: list[EventRecord] = []
        with self._path.open("r", encoding="utf-8") as fh:
            for _line_no, raw_line in enumerate(fh, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    records.append(EventRecord.model_validate(data))
                except (json.JSONDecodeError, Exception):
                    # A truncated final line is safe to skip
                    break
        return records
