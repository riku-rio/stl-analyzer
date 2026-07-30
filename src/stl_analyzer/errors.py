"""Stable domain exceptions and error-envelope conversion."""

from collections.abc import Mapping
from typing import Any

from stl_analyzer.models.common import ErrorEnvelope, ErrorPayload, ExitCode


class DomainError(Exception):
    """Expected failure that maps to a stable domain and process error."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        exit_code: ExitCode,
        details: Mapping[str, Any] | None = None,
        recoverable: bool = False,
        suggested_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = dict(details or {})
        self.recoverable = recoverable
        self.suggested_action = suggested_action

    def to_envelope(self) -> ErrorEnvelope:
        """Convert the exception to the common JSON error contract."""
        return ErrorEnvelope(
            error=ErrorPayload(
                code=self.code,
                message=self.message,
                details=self.details,
                recoverable=self.recoverable,
                suggested_action=self.suggested_action,
            )
        )


class PathSafetyError(DomainError):
    """Raised when a path escapes or violates an approved root."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(
            code="UNSAFE_PATH",
            message=message,
            exit_code=ExitCode.WORKSPACE_ERROR,
            details=details,
            recoverable=True,
            suggested_action="Use a path contained within the approved workspace or case root.",
        )


def internal_error(exc: BaseException, *, verbose: bool = False) -> DomainError:
    """Map an unexpected exception to the stable internal-error envelope."""
    details: dict[str, Any] = {"exception_type": type(exc).__name__}
    if verbose:
        details["exception_message"] = str(exc)
    return DomainError(
        code="INTERNAL_ERROR",
        message="An unexpected internal error occurred.",
        exit_code=ExitCode.INTERNAL_ERROR,
        details=details,
        recoverable=False,
        suggested_action="Run again with --verbose and report the diagnostic details.",
    )
