from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ErrorCode


class RstmdbError(Exception):
    """Base exception for rstmdb client errors."""

    pass


class ConnectionError(RstmdbError):
    """Connection-related errors."""

    pass


class ProtocolError(RstmdbError):
    """Protocol parsing errors."""

    pass


class ServerError(RstmdbError):
    """Server returned an error response."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
