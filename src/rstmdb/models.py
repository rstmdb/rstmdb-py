from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class Operation(str, Enum):
    """RCP operations."""

    HELLO = "HELLO"
    AUTH = "AUTH"
    PING = "PING"
    BYE = "BYE"
    INFO = "INFO"
    PUT_MACHINE = "PUT_MACHINE"
    GET_MACHINE = "GET_MACHINE"
    LIST_MACHINES = "LIST_MACHINES"
    CREATE_INSTANCE = "CREATE_INSTANCE"
    GET_INSTANCE = "GET_INSTANCE"
    DELETE_INSTANCE = "DELETE_INSTANCE"
    APPLY_EVENT = "APPLY_EVENT"
    BATCH = "BATCH"
    SNAPSHOT_INSTANCE = "SNAPSHOT_INSTANCE"
    WAL_READ = "WAL_READ"
    COMPACT = "COMPACT"
    WATCH_INSTANCE = "WATCH_INSTANCE"
    WATCH_ALL = "WATCH_ALL"
    UNWATCH = "UNWATCH"


class ErrorCode(str, Enum):
    """Server error codes."""

    # Protocol errors
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    BAD_REQUEST = "BAD_REQUEST"

    # Auth errors
    UNAUTHORIZED = "UNAUTHORIZED"
    AUTH_FAILED = "AUTH_FAILED"

    # Not found errors
    NOT_FOUND = "NOT_FOUND"
    MACHINE_NOT_FOUND = "MACHINE_NOT_FOUND"
    INSTANCE_NOT_FOUND = "INSTANCE_NOT_FOUND"

    # Already exists errors
    MACHINE_VERSION_EXISTS = "MACHINE_VERSION_EXISTS"
    INSTANCE_EXISTS = "INSTANCE_EXISTS"

    # State machine errors
    INVALID_TRANSITION = "INVALID_TRANSITION"
    GUARD_FAILED = "GUARD_FAILED"
    CONFLICT = "CONFLICT"

    # System errors (retryable)
    WAL_IO_ERROR = "WAL_IO_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"


class Request(BaseModel):
    """RCP request message."""

    type: str = "request"
    id: str
    op: Operation
    params: dict[str, Any] = {}


class ResponseError(BaseModel):
    """Error details in a response."""

    code: ErrorCode
    message: str
    retryable: bool
    details: dict[str, Any] = {}


class Response(BaseModel):
    """RCP response message."""

    type: str = "response"
    id: str
    status: str  # "ok" or "error"
    result: dict[str, Any] | None = None
    error: ResponseError | None = None


class StreamEvent(BaseModel):
    """Event from a watch subscription."""

    type: str = "event"
    subscription_id: str
    instance_id: str
    machine: str
    version: int
    wal_offset: int
    from_state: str
    to_state: str
    event: str
    payload: dict[str, Any] | None = None
    ctx: dict[str, Any] | None = None


# Result models


class PutMachineResult(BaseModel):
    """Result of PUT_MACHINE operation."""

    machine: str
    version: int
    stored_checksum: str
    created: bool


class GetMachineResult(BaseModel):
    """Result of GET_MACHINE operation."""

    definition: dict[str, Any]
    checksum: str


class CreateInstanceResult(BaseModel):
    """Result of CREATE_INSTANCE operation."""

    instance_id: str
    state: str
    wal_offset: int


class GetInstanceResult(BaseModel):
    """Result of GET_INSTANCE operation."""

    machine: str
    version: int
    state: str
    ctx: dict[str, Any]
    last_event_id: str | None = None
    last_wal_offset: int


class ApplyEventResult(BaseModel):
    """Result of APPLY_EVENT operation."""

    from_state: str
    to_state: str
    ctx: dict[str, Any] | None = None
    wal_offset: int
    applied: bool
    event_id: str | None = None


class WatchInstanceResult(BaseModel):
    """Result of WATCH_INSTANCE operation."""

    subscription_id: str
    instance_id: str
    current_state: str
    current_wal_offset: int


class WatchAllResult(BaseModel):
    """Result of WATCH_ALL operation."""

    subscription_id: str
    wal_offset: int


class UnwatchResult(BaseModel):
    """Result of UNWATCH operation."""

    subscription_id: str
    removed: bool
