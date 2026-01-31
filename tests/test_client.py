from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rstmdb import Client
from rstmdb.connection import Connection
from rstmdb.errors import ServerError
from rstmdb.models import (
    ErrorCode,
    Operation,
    Response,
    ResponseError,
)


@pytest.fixture
def mock_connection() -> MagicMock:
    """Create a mock connection."""
    conn = MagicMock(spec=Connection)
    conn.connect = AsyncMock()
    conn.close = AsyncMock()
    conn.request = AsyncMock()
    conn.events = MagicMock()
    return conn


class TestClientInit:
    """Tests for Client initialization."""

    def test_default_values(self) -> None:
        """Client has sensible defaults."""
        client = Client()

        assert client.host == "127.0.0.1"
        assert client.port == 7401
        assert client.token is None

    def test_custom_host_port(self) -> None:
        """Client accepts custom host and port."""
        client = Client("example.com", 8080)

        assert client.host == "example.com"
        assert client.port == 8080

    def test_with_token(self) -> None:
        """Client stores auth token."""
        client = Client(token="secret-token")

        assert client.token == "secret-token"

    def test_tls_creates_context(self) -> None:
        """TLS flag creates SSL context."""
        with patch("rstmdb.client.create_ssl_context") as mock_ssl:
            mock_ssl.return_value = MagicMock()
            Client(tls=True)

            mock_ssl.assert_called_once_with(
                ca_cert=None,
                client_cert=None,
                client_key=None,
                insecure=False,
            )

    def test_mtls_with_certs(self) -> None:
        """mTLS with certificates."""
        with patch("rstmdb.client.create_ssl_context") as mock_ssl:
            mock_ssl.return_value = MagicMock()
            Client(
                tls=True,
                ca_cert="/path/to/ca.pem",
                client_cert="/path/to/client.pem",
                client_key="/path/to/client-key.pem",
            )

            mock_ssl.assert_called_once_with(
                ca_cert="/path/to/ca.pem",
                client_cert="/path/to/client.pem",
                client_key="/path/to/client-key.pem",
                insecure=False,
            )


class TestClientContextManager:
    """Tests for Client async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_connects(self, mock_connection: MagicMock) -> None:
        """Context manager connects on enter."""
        client = Client()
        client._conn = mock_connection

        async with client:
            mock_connection.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_closes(self, mock_connection: MagicMock) -> None:
        """Context manager closes on exit."""
        client = Client()
        client._conn = mock_connection

        async with client:
            pass

        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_error(self, mock_connection: MagicMock) -> None:
        """Context manager closes even on error."""
        client = Client()
        client._conn = mock_connection

        with pytest.raises(ValueError):
            async with client:
                raise ValueError("test error")

        mock_connection.close.assert_called_once()


class TestSystemOperations:
    """Tests for system operations."""

    @pytest.mark.asyncio
    async def test_ping(self, mock_connection: MagicMock) -> None:
        """Ping returns True on success."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={},
        )

        client = Client()
        client._conn = mock_connection

        result = await client.ping()

        assert result is True
        mock_connection.request.assert_called_once_with(Operation.PING, {})

    @pytest.mark.asyncio
    async def test_info(self, mock_connection: MagicMock) -> None:
        """Info returns server info dict."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={"version": "1.0.0", "uptime": 3600},
        )

        client = Client()
        client._conn = mock_connection

        result = await client.info()

        assert result == {"version": "1.0.0", "uptime": 3600}


class TestMachineOperations:
    """Tests for machine operations."""

    @pytest.mark.asyncio
    async def test_put_machine(self, mock_connection: MagicMock) -> None:
        """Put machine creates/updates machine definition."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "machine": "order",
                "version": 1,
                "stored_checksum": "abc123",
                "created": True,
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.put_machine(
            "order",
            1,
            {"states": ["created", "paid"], "initial": "created"},
        )

        assert result.machine == "order"
        assert result.version == 1
        assert result.created is True

    @pytest.mark.asyncio
    async def test_get_machine(self, mock_connection: MagicMock) -> None:
        """Get machine returns definition."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "definition": {"states": ["a", "b"]},
                "checksum": "def456",
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.get_machine("order", 1)

        assert result.definition == {"states": ["a", "b"]}
        assert result.checksum == "def456"

    @pytest.mark.asyncio
    async def test_list_machines(self, mock_connection: MagicMock) -> None:
        """List machines returns machine list."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "items": [
                    {"machine": "order", "version": 1},
                    {"machine": "payment", "version": 2},
                ]
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.list_machines()

        assert len(result) == 2
        assert result[0]["machine"] == "order"


class TestInstanceOperations:
    """Tests for instance operations."""

    @pytest.mark.asyncio
    async def test_create_instance(self, mock_connection: MagicMock) -> None:
        """Create instance with minimal params."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "instance_id": "inst-123",
                "state": "initial",
                "wal_offset": 1,
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.create_instance("order", 1)

        assert result.instance_id == "inst-123"
        assert result.state == "initial"
        mock_connection.request.assert_called_once_with(
            Operation.CREATE_INSTANCE,
            {"machine": "order", "version": 1},
        )

    @pytest.mark.asyncio
    async def test_create_instance_with_all_params(self, mock_connection: MagicMock) -> None:
        """Create instance with all optional params."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "instance_id": "my-instance",
                "state": "initial",
                "wal_offset": 1,
            },
        )

        client = Client()
        client._conn = mock_connection

        await client.create_instance(
            "order",
            1,
            instance_id="my-instance",
            initial_ctx={"key": "value"},
            idempotency_key="idem-123",
        )

        mock_connection.request.assert_called_once_with(
            Operation.CREATE_INSTANCE,
            {
                "machine": "order",
                "version": 1,
                "instance_id": "my-instance",
                "initial_ctx": {"key": "value"},
                "idempotency_key": "idem-123",
            },
        )

    @pytest.mark.asyncio
    async def test_get_instance(self, mock_connection: MagicMock) -> None:
        """Get instance returns instance state."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "machine": "order",
                "version": 1,
                "state": "paid",
                "ctx": {"amount": 99.99},
                "last_wal_offset": 10,
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.get_instance("inst-123")

        assert result.state == "paid"
        assert result.ctx == {"amount": 99.99}

    @pytest.mark.asyncio
    async def test_delete_instance(self, mock_connection: MagicMock) -> None:
        """Delete instance."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={"deleted": True},
        )

        client = Client()
        client._conn = mock_connection

        result = await client.delete_instance("inst-123")

        assert result == {"deleted": True}


class TestEventOperations:
    """Tests for event operations."""

    @pytest.mark.asyncio
    async def test_apply_event_minimal(self, mock_connection: MagicMock) -> None:
        """Apply event with minimal params."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "from_state": "created",
                "to_state": "paid",
                "wal_offset": 11,
                "applied": True,
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.apply_event("inst-123", "PAY")

        assert result.from_state == "created"
        assert result.to_state == "paid"
        assert result.applied is True

    @pytest.mark.asyncio
    async def test_apply_event_with_payload(self, mock_connection: MagicMock) -> None:
        """Apply event with payload and expected state."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "from_state": "created",
                "to_state": "paid",
                "wal_offset": 11,
                "applied": True,
                "ctx": {"amount": 99.99},
            },
        )

        client = Client()
        client._conn = mock_connection

        await client.apply_event(
            "inst-123",
            "PAY",
            payload={"amount": 99.99},
            expected_state="created",
        )

        mock_connection.request.assert_called_once_with(
            Operation.APPLY_EVENT,
            {
                "instance_id": "inst-123",
                "event": "PAY",
                "payload": {"amount": 99.99},
                "expected_state": "created",
            },
        )


class TestWatchOperations:
    """Tests for watch operations."""

    @pytest.mark.asyncio
    async def test_watch_instance(self, mock_connection: MagicMock) -> None:
        """Watch instance returns subscription."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "subscription_id": "sub-123",
                "instance_id": "inst-123",
                "current_state": "created",
                "current_wal_offset": 5,
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.watch_instance("inst-123")

        assert result.subscription_id == "sub-123"
        assert result.current_state == "created"

    @pytest.mark.asyncio
    async def test_watch_all_with_filters(self, mock_connection: MagicMock) -> None:
        """Watch all with filter criteria."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "subscription_id": "sub-456",
                "wal_offset": 100,
            },
        )

        client = Client()
        client._conn = mock_connection

        await client.watch_all(
            machines=["order"],
            to_states=["shipped"],
            events=["SHIP"],
        )

        mock_connection.request.assert_called_once_with(
            Operation.WATCH_ALL,
            {
                "include_ctx": True,
                "machines": ["order"],
                "to_states": ["shipped"],
                "events": ["SHIP"],
            },
        )

    @pytest.mark.asyncio
    async def test_unwatch(self, mock_connection: MagicMock) -> None:
        """Unwatch cancels subscription."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "subscription_id": "sub-123",
                "removed": True,
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.unwatch("sub-123")

        assert result.subscription_id == "sub-123"
        assert result.removed is True


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_server_error(self, mock_connection: MagicMock) -> None:
        """Server error raises ServerError."""
        mock_connection.request.return_value = Response(
            id="1",
            status="error",
            error=ResponseError(
                code=ErrorCode.NOT_FOUND,
                message="Instance not found",
                retryable=False,
            ),
        )

        client = Client()
        client._conn = mock_connection

        with pytest.raises(ServerError) as exc_info:
            await client.get_instance("nonexistent")

        assert exc_info.value.code == ErrorCode.NOT_FOUND
        assert "Instance not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_transition_error(self, mock_connection: MagicMock) -> None:
        """Invalid transition raises ServerError."""
        mock_connection.request.return_value = Response(
            id="1",
            status="error",
            error=ResponseError(
                code=ErrorCode.INVALID_TRANSITION,
                message="No transition from 'shipped' on event 'PAY'",
                retryable=False,
            ),
        )

        client = Client()
        client._conn = mock_connection

        with pytest.raises(ServerError) as exc_info:
            await client.apply_event("inst-123", "PAY")

        assert exc_info.value.code == ErrorCode.INVALID_TRANSITION


class TestWalAndCompaction:
    """Tests for WAL and compaction operations."""

    @pytest.mark.asyncio
    async def test_wal_read(self, mock_connection: MagicMock) -> None:
        """WAL read returns entries."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={
                "entries": [{"offset": 1}, {"offset": 2}],
                "next_offset": 3,
            },
        )

        client = Client()
        client._conn = mock_connection

        result = await client.wal_read(from_offset=0, limit=100)

        assert len(result["entries"]) == 2
        mock_connection.request.assert_called_once_with(
            Operation.WAL_READ,
            {"from_offset": 0, "limit": 100},
        )

    @pytest.mark.asyncio
    async def test_compact(self, mock_connection: MagicMock) -> None:
        """Compact triggers compaction."""
        mock_connection.request.return_value = Response(
            id="1",
            status="ok",
            result={"compacted": True},
        )

        client = Client()
        client._conn = mock_connection

        result = await client.compact(force_snapshot=True)

        assert result == {"compacted": True}
        mock_connection.request.assert_called_once_with(
            Operation.COMPACT,
            {"force_snapshot": True},
        )
