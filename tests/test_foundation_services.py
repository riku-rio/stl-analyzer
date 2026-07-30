from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from stl_analyzer.errors import DomainError
from stl_analyzer.filesystem.atomic import atomic_write_json, atomic_write_text
from stl_analyzer.models.common import ExitCode
from stl_analyzer.services.clock import FixedClock, new_session_id
from stl_analyzer.services.hashing import sha256_bytes, sha256_file, sha256_text
from stl_analyzer.templates import (
    AGENTS_TEMPLATE,
    CONFIG_MARKER,
    CONFIG_TEMPLATE,
    SKILL_MARKER,
    SKILL_TEMPLATE,
    load_template,
)


def test_exit_codes_match_prd() -> None:
    assert [int(code) for code in ExitCode] == list(range(9))


def test_domain_error_envelope() -> None:
    error = DomainError(
        code="TEST_ERROR",
        message="Test failure.",
        exit_code=ExitCode.WORKSPACE_ERROR,
        details={"path": "x"},
        recoverable=True,
        suggested_action="Fix it.",
    )
    payload = error.to_envelope().model_dump(mode="json")
    assert payload == {
        "success": False,
        "error": {
            "code": "TEST_ERROR",
            "message": "Test failure.",
            "details": {"path": "x"},
            "recoverable": True,
            "suggested_action": "Fix it.",
        },
    }


def test_fixed_clock_session_id() -> None:
    clock = FixedClock(datetime(2026, 7, 30, 19, 58, tzinfo=UTC))
    assert new_session_id(clock, lambda: "a41c") == "20260730T195800Z-a41c"


def test_naive_fixed_clock_is_treated_as_utc() -> None:
    clock = FixedClock(datetime(2026, 7, 30, 19, 58))
    assert new_session_id(clock, lambda: "0000") == "20260730T195800Z-0000"


def test_invalid_session_token_is_rejected() -> None:
    clock = FixedClock(datetime(2026, 7, 30, tzinfo=UTC))
    try:
        new_session_id(clock, lambda: "not-hex")
    except ValueError as exc:
        assert "four hexadecimal" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_hashing_helpers(tmp_path: Path) -> None:
    content = b"stl-analyzer"
    path = tmp_path / "source.stl"
    path.write_bytes(content)
    expected = sha256_bytes(content)
    assert sha256_text("stl-analyzer") == expected
    assert sha256_file(path) == expected


def test_atomic_writes(tmp_path: Path) -> None:
    text_path = tmp_path / "nested" / "value.txt"
    atomic_write_text(text_path, "first")
    atomic_write_text(text_path, "second")
    assert text_path.read_text(encoding="utf-8") == "second"

    json_path = tmp_path / "value.json"
    atomic_write_json(json_path, {"b": 2, "a": 1})
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert json_path.read_text(encoding="utf-8").endswith("\n")


def test_templates_are_installed_package_resources() -> None:
    config = load_template(CONFIG_TEMPLATE)
    skill = load_template(SKILL_TEMPLATE)
    agents = load_template(AGENTS_TEMPLATE)
    assert config.startswith(CONFIG_MARKER)
    assert skill.startswith(SKILL_MARKER)
    assert "STL Analyzer" in agents
