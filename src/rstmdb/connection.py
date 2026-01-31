from __future__ import annotations

import asyncio
import json
import ssl
from collections.abc import AsyncIterator
from typing import Any

from .errors import ConnectionError, ProtocolError
from .models import Operation, Request, Response, StreamEvent
from .protocol import Frame


class Connection:
    """Low-level async connection to rstmdb server."""

    def __init__(
        self,
        host: str,
        port: int = 7401,
        *,
        ssl_context: ssl.SSLContext | None = None,
        connect_timeout: float = 10.0,
        request_timeout: float = 30.0,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0
        self._pending: dict[str, asyncio.Future[Response]] = {}
        self._events: asyncio.Queue[StreamEvent] = asyncio.Queue()
        self._read_task: asyncio.Task[None] | None = None
        self._buffer = b""
        self._closed = False
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected and not self._closed and self._writer is not None

    def _reset(self) -> None:
        """Reset connection state for reconnection."""
        self._reader = None
        self._writer = None
        self._buffer = b""
        self._connected = False
        # Don't reset _request_id to avoid ID collisions
        # Don't reset _events queue to preserve unprocessed events

    async def connect(self, client_name: str = "rstmdb-py", auth_token: str | None = None) -> None:
        """Connect to the server and perform handshake."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, ssl=self.ssl_context),
                timeout=self.connect_timeout,
            )
        except OSError as e:
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}") from e
        except asyncio.TimeoutError as e:
            raise ConnectionError(f"Connection to {self.host}:{self.port} timed out") from e

        # HELLO handshake
        await self._handshake(client_name)

        # Optional AUTH
        if auth_token:
            await self._authenticate(auth_token)

        # Mark as connected and start read loop
        self._connected = True
        self._read_task = asyncio.create_task(self._read_loop())

    async def _handshake(self, client_name: str) -> None:
        """Perform HELLO handshake."""
        response = await self._request_raw(
            Operation.HELLO,
            {
                "protocol_version": 1,
                "client_name": client_name,
                "wire_modes": ["binary_json"],
                "features": ["idempotency", "batch"],
            },
        )
        if response.status != "ok":
            error_msg = response.error.message if response.error else "Unknown error"
            raise ConnectionError(f"Handshake failed: {error_msg}")

    async def _authenticate(self, token: str) -> None:
        """Perform AUTH with bearer token."""
        from .errors import ServerError

        response = await self._request_raw(
            Operation.AUTH,
            {
                "method": "bearer",
                "token": token,
            },
        )
        if response.status != "ok":
            if response.error:
                raise ServerError(response.error.code, response.error.message)
            raise ConnectionError("Authentication failed")

    async def _request_raw(self, op: Operation, params: dict[str, Any]) -> Response:
        """Send request and wait for response (before read loop starts)."""
        if self._writer is None or self._reader is None:
            raise ConnectionError("Not connected")

        self._request_id += 1
        req_id = str(self._request_id)

        request = Request(id=req_id, op=op, params=params)
        frame = Frame(request.model_dump_json().encode())
        self._writer.write(frame.encode())
        await self._writer.drain()

        # Read response directly
        while True:
            try:
                data = await asyncio.wait_for(
                    self._reader.read(8192),
                    timeout=self.request_timeout,
                )
            except asyncio.TimeoutError as e:
                raise ConnectionError("Request timed out") from e

            if not data:
                raise ConnectionError("Connection closed by server")

            self._buffer += data
            decoded_frame, self._buffer = Frame.decode(self._buffer)
            if decoded_frame:
                return Response.model_validate_json(decoded_frame.payload)

    async def request(self, op: Operation, params: dict[str, Any]) -> Response:
        """Send request and wait for response."""
        if self._writer is None:
            raise ConnectionError("Not connected")

        self._request_id += 1
        req_id = str(self._request_id)

        request = Request(id=req_id, op=op, params=params)
        frame = Frame(request.model_dump_json().encode())

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Response] = loop.create_future()
        self._pending[req_id] = future

        try:
            self._writer.write(frame.encode())
            await self._writer.drain()
            return await asyncio.wait_for(future, timeout=self.request_timeout)
        except asyncio.TimeoutError as e:
            raise ConnectionError("Request timed out") from e
        finally:
            self._pending.pop(req_id, None)

    async def _read_loop(self) -> None:
        """Background task to read and dispatch messages."""
        if self._reader is None:
            return

        try:
            while not self._closed:
                try:
                    data = await self._reader.read(8192)
                except OSError as e:
                    self._connected = False
                    if not self._closed:
                        self._fail_pending(ConnectionError(str(e)))
                    break

                if not data:
                    self._connected = False
                    if not self._closed:
                        self._fail_pending(ConnectionError("Connection closed by server"))
                    break

                self._buffer += data
                while True:
                    try:
                        decoded_frame, self._buffer = Frame.decode(self._buffer)
                    except ProtocolError as e:
                        self._fail_pending(e)
                        return

                    if not decoded_frame:
                        break

                    try:
                        msg = json.loads(decoded_frame.payload)
                    except json.JSONDecodeError as e:
                        self._fail_pending(ProtocolError(f"Invalid JSON: {e}"))
                        return

                    msg_type = msg.get("type")

                    if msg_type == "response":
                        try:
                            response = Response.model_validate(msg)
                        except Exception as e:
                            # Handle validation errors (e.g., unknown error codes)
                            # Fail the pending request with the validation error
                            req_id = msg.get("id")
                            if req_id and req_id in self._pending:
                                self._pending[req_id].set_exception(
                                    ProtocolError(f"Failed to parse response: {e}")
                                )
                            continue

                        if response.id in self._pending:
                            self._pending[response.id].set_result(response)
                    elif msg_type == "event":
                        try:
                            event = StreamEvent.model_validate(msg)
                            await self._events.put(event)
                        except Exception:
                            # Skip malformed events
                            pass
        except asyncio.CancelledError:
            pass

    def _fail_pending(self, error: Exception) -> None:
        """Fail all pending requests with the given error."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def events(self) -> AsyncIterator[StreamEvent]:
        """Async iterator for stream events."""
        while not self._closed:
            try:
                event = await self._events.get()
                yield event
            except asyncio.CancelledError:
                break

    async def close(self) -> None:
        """Close the connection."""
        self._closed = True

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass

        self._fail_pending(ConnectionError("Connection closed"))
