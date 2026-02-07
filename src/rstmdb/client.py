from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from .connection import Connection
from .errors import ConnectionError, ServerError
from .models import (
    ApplyEventResult,
    CreateInstanceResult,
    GetInstanceResult,
    GetMachineResult,
    ListInstancesResult,
    Operation,
    PutMachineResult,
    StreamEvent,
    UnwatchResult,
    WalStatsResult,
    WatchAllResult,
    WatchInstanceResult,
)
from .tls import create_ssl_context

logger = logging.getLogger(__name__)


class Client:
    """High-level async client for rstmdb server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7401,
        *,
        token: str | None = None,
        tls: bool = False,
        ca_cert: str | None = None,
        client_cert: str | None = None,
        client_key: str | None = None,
        insecure: bool = False,
        connect_timeout: float = 10.0,
        request_timeout: float = 30.0,
        # Reconnection settings
        auto_reconnect: bool = False,
        max_reconnect_attempts: int = 0,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        """
        Initialize the client.

        Args:
            host: Server hostname or IP address.
            port: Server port (default 7401).
            token: Optional bearer token for authentication.
            tls: Enable TLS (automatically enabled if any cert is provided).
            ca_cert: Path to CA certificate for server verification.
            client_cert: Path to client certificate for mTLS.
            client_key: Path to client private key for mTLS.
            insecure: Disable certificate verification (dev only).
            connect_timeout: Connection timeout in seconds.
            request_timeout: Request timeout in seconds.
            auto_reconnect: Enable automatic reconnection on connection loss.
            max_reconnect_attempts: Max reconnection attempts (0 = unlimited).
            reconnect_base_delay: Initial delay between reconnection attempts.
            reconnect_max_delay: Maximum delay between reconnection attempts.
            on_reconnect: Optional callback invoked after successful reconnection.
        """
        self.host = host
        self.port = port
        self.token = token

        # Reconnection settings
        self._auto_reconnect = auto_reconnect
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_base_delay = reconnect_base_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._on_reconnect = on_reconnect
        self._reconnect_attempt = 0

        ssl_context = None
        if tls or ca_cert or client_cert:
            ssl_context = create_ssl_context(
                ca_cert=ca_cert,
                client_cert=client_cert,
                client_key=client_key,
                insecure=insecure,
            )

        self._ssl_context = ssl_context
        self._connect_timeout = connect_timeout
        self._request_timeout = request_timeout

        # Store watch parameters for re-subscription after reconnect
        self._watch_params: dict[str, Any] | None = None

        self._conn = Connection(
            host,
            port,
            ssl_context=ssl_context,
            connect_timeout=connect_timeout,
            request_timeout=request_timeout,
        )

    @property
    def is_connected(self) -> bool:
        """Check if currently connected to the server."""
        return self._conn.is_connected

    async def connect(self) -> None:
        """Connect to the server."""
        await self._conn.connect(auth_token=self.token)
        self._reconnect_attempt = 0

    async def close(self) -> None:
        """Close the connection."""
        await self._conn.close()

    async def reconnect(self) -> None:
        """
        Attempt to reconnect to the server.

        Creates a new connection and performs handshake/auth.
        """
        # Close existing connection if any
        await self._conn.close()

        # Create new connection
        self._conn = Connection(
            self.host,
            self.port,
            ssl_context=self._ssl_context,
            connect_timeout=self._connect_timeout,
            request_timeout=self._request_timeout,
        )

        # Connect
        await self._conn.connect(auth_token=self.token)
        self._reconnect_attempt = 0

        # Invoke callback if set
        if self._on_reconnect:
            self._on_reconnect()

    async def _ensure_connected(self) -> None:
        """Ensure connection is active, reconnecting if needed."""
        if self._conn.is_connected:
            return

        if not self._auto_reconnect:
            raise ConnectionError("Not connected to server")

        await self._reconnect_with_backoff()

    async def _reconnect_with_backoff(self) -> None:
        """Reconnect with exponential backoff."""
        while True:
            self._reconnect_attempt += 1

            if (
                self._max_reconnect_attempts > 0
                and self._reconnect_attempt > self._max_reconnect_attempts
            ):
                raise ConnectionError(
                    f"Failed to reconnect after {self._max_reconnect_attempts} attempts"
                )

            # Calculate delay with exponential backoff
            delay = min(
                self._reconnect_base_delay * (2 ** (self._reconnect_attempt - 1)),
                self._reconnect_max_delay,
            )

            logger.info(
                f"Reconnecting to {self.host}:{self.port} "
                f"(attempt {self._reconnect_attempt}, delay {delay:.1f}s)"
            )

            await asyncio.sleep(delay)

            try:
                await self.reconnect()
                logger.info(f"Reconnected to {self.host}:{self.port}")
                return
            except ConnectionError as e:
                logger.warning(f"Reconnection failed: {e}")
                continue

    async def __aenter__(self) -> Client:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _request(self, op: Operation, params: dict[str, Any]) -> dict[str, Any]:
        """Send a request and return the result."""
        # Ensure we're connected (with auto-reconnect if enabled)
        await self._ensure_connected()

        try:
            response = await self._conn.request(op, params)
        except ConnectionError:
            if not self._auto_reconnect:
                raise
            # Try to reconnect and retry once
            await self._reconnect_with_backoff()
            response = await self._conn.request(op, params)

        if response.status != "ok":
            if response.error:
                raise ServerError(response.error.code, response.error.message)
            raise ServerError("INTERNAL", "Unknown error")  # type: ignore[arg-type]
        return response.result or {}

    # System operations

    async def ping(self) -> bool:
        """Ping the server."""
        await self._request(Operation.PING, {})
        return True

    async def info(self) -> dict[str, Any]:
        """Get server information."""
        return await self._request(Operation.INFO, {})

    # Machine operations

    async def put_machine(
        self,
        machine: str,
        version: int,
        definition: dict[str, Any],
    ) -> PutMachineResult:
        """
        Create or update a state machine definition.

        Args:
            machine: Machine name.
            version: Machine version.
            definition: Machine definition dict.

        Returns:
            PutMachineResult with machine details.
        """
        result = await self._request(
            Operation.PUT_MACHINE,
            {
                "machine": machine,
                "version": version,
                "definition": definition,
            },
        )
        return PutMachineResult.model_validate(result)

    async def get_machine(self, machine: str, version: int) -> GetMachineResult:
        """
        Get a state machine definition.

        Args:
            machine: Machine name.
            version: Machine version.

        Returns:
            GetMachineResult with definition and checksum.
        """
        result = await self._request(
            Operation.GET_MACHINE,
            {
                "machine": machine,
                "version": version,
            },
        )
        return GetMachineResult.model_validate(result)

    async def list_machines(self) -> list[dict[str, Any]]:
        """
        List all registered machines.

        Returns:
            List of machine info dicts.
        """
        result = await self._request(Operation.LIST_MACHINES, {})
        items: list[dict[str, Any]] = result.get("items", [])
        return items

    # Instance operations

    async def create_instance(
        self,
        machine: str,
        version: int,
        instance_id: str | None = None,
        initial_ctx: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> CreateInstanceResult:
        """
        Create a new state machine instance.

        Args:
            machine: Machine name.
            version: Machine version.
            instance_id: Optional custom instance ID.
            initial_ctx: Optional initial context.
            idempotency_key: Optional idempotency key.

        Returns:
            CreateInstanceResult with instance details.
        """
        params: dict[str, Any] = {"machine": machine, "version": version}
        if instance_id:
            params["instance_id"] = instance_id
        if initial_ctx:
            params["initial_ctx"] = initial_ctx
        if idempotency_key:
            params["idempotency_key"] = idempotency_key

        result = await self._request(Operation.CREATE_INSTANCE, params)
        return CreateInstanceResult.model_validate(result)

    async def get_instance(self, instance_id: str) -> GetInstanceResult:
        """
        Get an instance's current state.

        Args:
            instance_id: Instance ID.

        Returns:
            GetInstanceResult with instance details.
        """
        result = await self._request(
            Operation.GET_INSTANCE,
            {"instance_id": instance_id},
        )
        return GetInstanceResult.model_validate(result)

    async def list_instances(
        self,
        machine: str | None = None,
        state: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> ListInstancesResult:
        """
        List instances with optional filtering and pagination.

        Args:
            machine: Filter by machine name.
            state: Filter by current state.
            limit: Maximum number of instances to return.
            offset: Number of instances to skip (for pagination).

        Returns:
            ListInstancesResult with instances list and pagination info.
        """
        params: dict[str, Any] = {}
        if machine:
            params["machine"] = machine
        if state:
            params["state"] = state
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        result = await self._request(Operation.LIST_INSTANCES, params)
        return ListInstancesResult.model_validate(result)

    async def delete_instance(
        self,
        instance_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Delete an instance.

        Args:
            instance_id: Instance ID.
            idempotency_key: Optional idempotency key.

        Returns:
            Result dict.
        """
        params: dict[str, Any] = {"instance_id": instance_id}
        if idempotency_key:
            params["idempotency_key"] = idempotency_key
        return await self._request(Operation.DELETE_INSTANCE, params)

    # Event operations

    async def apply_event(
        self,
        instance_id: str,
        event: str,
        payload: dict[str, Any] | None = None,
        expected_state: str | None = None,
        idempotency_key: str | None = None,
    ) -> ApplyEventResult:
        """
        Apply an event to an instance.

        Args:
            instance_id: Instance ID.
            event: Event name.
            payload: Optional event payload.
            expected_state: Optional expected current state.
            idempotency_key: Optional idempotency key.

        Returns:
            ApplyEventResult with transition details.
        """
        params: dict[str, Any] = {"instance_id": instance_id, "event": event}
        if payload:
            params["payload"] = payload
        if expected_state:
            params["expected_state"] = expected_state
        if idempotency_key:
            params["idempotency_key"] = idempotency_key

        result = await self._request(Operation.APPLY_EVENT, params)
        return ApplyEventResult.model_validate(result)

    # Watch operations

    async def watch_instance(
        self,
        instance_id: str,
        include_ctx: bool = True,
    ) -> WatchInstanceResult:
        """
        Watch a specific instance for state changes.

        Args:
            instance_id: Instance ID to watch.
            include_ctx: Include context in events.

        Returns:
            WatchInstanceResult with subscription details.
        """
        result = await self._request(
            Operation.WATCH_INSTANCE,
            {
                "instance_id": instance_id,
                "include_ctx": include_ctx,
            },
        )
        return WatchInstanceResult.model_validate(result)

    async def watch_all(
        self,
        machines: list[str] | None = None,
        from_states: list[str] | None = None,
        to_states: list[str] | None = None,
        events: list[str] | None = None,
        include_ctx: bool = True,
    ) -> WatchAllResult:
        """
        Watch all instances matching the filter criteria.

        Args:
            machines: Filter by machine names.
            from_states: Filter by source states.
            to_states: Filter by target states.
            events: Filter by event names.
            include_ctx: Include context in events.

        Returns:
            WatchAllResult with subscription details.
        """
        params: dict[str, Any] = {"include_ctx": include_ctx}
        if machines:
            params["machines"] = machines
        if from_states:
            params["from_states"] = from_states
        if to_states:
            params["to_states"] = to_states
        if events:
            params["events"] = events

        # Store params for re-subscription after reconnect
        self._watch_params = params.copy()

        result = await self._request(Operation.WATCH_ALL, params)
        return WatchAllResult.model_validate(result)

    async def unwatch(self, subscription_id: str) -> UnwatchResult:
        """
        Cancel a watch subscription.

        Args:
            subscription_id: Subscription ID to cancel.

        Returns:
            UnwatchResult with removal status.
        """
        # Clear stored watch params
        self._watch_params = None

        result = await self._request(
            Operation.UNWATCH,
            {"subscription_id": subscription_id},
        )
        return UnwatchResult.model_validate(result)

    async def events(self) -> AsyncIterator[StreamEvent]:
        """
        Async iterator for stream events from watch subscriptions.

        If auto_reconnect is enabled and watch_all() was called before,
        this will automatically reconnect and re-establish the watch
        subscription if the connection drops.

        Note: Events that occur during disconnection may be missed.
        For reliable event processing, track WAL offsets.

        Yields:
            StreamEvent objects as they arrive.
        """
        while True:
            try:
                # Yield events until disconnection
                async for event in self._conn.events():
                    yield event

                # Connection closed gracefully
                if not self._auto_reconnect or not self._watch_params:
                    return

                logger.info("Event stream ended, reconnecting...")

            except ConnectionError as e:
                if not self._auto_reconnect or not self._watch_params:
                    raise

                logger.warning(f"Watch connection lost: {e}")

            # Reconnect and re-establish watch subscription
            try:
                await self._reconnect_with_backoff()
                logger.debug("Re-establishing watch subscription")
                await self._request(Operation.WATCH_ALL, self._watch_params)
            except ConnectionError:
                if not self._auto_reconnect:
                    raise
                # Will retry on next iteration

    # WAL operations

    async def wal_read(
        self,
        from_offset: int = 0,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Read entries from the write-ahead log.

        Args:
            from_offset: Starting offset.
            limit: Maximum entries to return.

        Returns:
            Dict with WAL entries.
        """
        params: dict[str, Any] = {"from_offset": from_offset}
        if limit:
            params["limit"] = limit
        return await self._request(Operation.WAL_READ, params)

    async def wal_stats(self) -> WalStatsResult:
        """
        Get WAL statistics.

        Returns:
            WalStatsResult with WAL statistics including entry count,
            segment count, total size, and I/O stats.
        """
        result = await self._request(Operation.WAL_STATS, {})
        return WalStatsResult.model_validate(result)

    # Compaction

    async def compact(self, force_snapshot: bool = False) -> dict[str, Any]:
        """
        Trigger compaction.

        Args:
            force_snapshot: Force snapshot creation.

        Returns:
            Compaction result dict.
        """
        return await self._request(
            Operation.COMPACT,
            {"force_snapshot": force_snapshot},
        )
