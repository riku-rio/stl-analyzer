"""Blender subprocess adapter."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from stl_analyzer.errors import DomainError
from stl_analyzer.models.common import ExitCode


@dataclass
class BlenderResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool


class BlenderAdapter(Protocol):
    def run(
        self,
        *,
        executable: str | Path,
        script: Path,
        manifest_path: Path,
        timeout_seconds: float,
    ) -> BlenderResult: ...


class SubprocessBlenderAdapter:
    def run(
        self,
        *,
        executable: str | Path,
        script: Path,
        manifest_path: Path,
        timeout_seconds: float,
    ) -> BlenderResult:
        args = [
            str(executable),
            "--background",
            "--python",
            str(script),
            "--",
            str(manifest_path),
        ]

        start_time = time.monotonic()
        timed_out = False

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout_seconds, check=False
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            exit_code = -1
        except FileNotFoundError:
            raise DomainError(
                code="BLENDER_NOT_FOUND",
                message=f"Blender executable not found: {executable}",
                exit_code=ExitCode.BLENDER_FAILURE,
                recoverable=True,
                suggested_action="Check Blender installation and config.",
            ) from None
        except Exception as e:
            raise DomainError(
                code="BLENDER_INVOCATION_FAILED",
                message=f"Failed to invoke Blender: {e!s}",
                exit_code=ExitCode.BLENDER_FAILURE,
                recoverable=False,
                suggested_action="Check system permissions.",
            ) from None

        duration = time.monotonic() - start_time

        return BlenderResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_seconds=duration,
            timed_out=timed_out,
        )
