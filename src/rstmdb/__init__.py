from .client import Client
from .connection import Connection
from .errors import ConnectionError, ProtocolError, RstmdbError, ServerError
from .models import (
    ApplyEventResult,
    CreateInstanceResult,
    ErrorCode,
    GetInstanceResult,
    GetMachineResult,
    Operation,
    PutMachineResult,
    Request,
    Response,
    ResponseError,
    StreamEvent,
    UnwatchResult,
    WatchAllResult,
    WatchInstanceResult,
)
from .protocol import Frame
from .tls import create_ssl_context

__version__ = "0.1.0"

__all__ = [
    # Client
    "Client",
    "Connection",
    # Errors
    "RstmdbError",
    "ConnectionError",
    "ProtocolError",
    "ServerError",
    # Models
    "Operation",
    "ErrorCode",
    "Request",
    "Response",
    "ResponseError",
    "StreamEvent",
    "PutMachineResult",
    "GetMachineResult",
    "CreateInstanceResult",
    "GetInstanceResult",
    "ApplyEventResult",
    "WatchInstanceResult",
    "WatchAllResult",
    "UnwatchResult",
    # Protocol
    "Frame",
    # TLS
    "create_ssl_context",
]
