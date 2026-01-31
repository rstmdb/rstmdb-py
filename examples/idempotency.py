#!/usr/bin/env python3
"""Idempotency example for rstmdb client.

Idempotency keys ensure that operations are applied at most once,
even if the client retries due to network issues or timeouts.
"""

import asyncio
import uuid

from rstmdb import Client, ServerError


async def main() -> None:
    async with Client("127.0.0.1", 7401, token="my-secret-token") as client:
        # Generate a unique idempotency key for this operation
        # In production, you'd typically derive this from your request ID
        idempotency_key = str(uuid.uuid4())

        # Create an instance with an idempotency key
        # If this request is retried, the same instance will be returned
        instance = await client.create_instance(
            machine="order",
            version=1,
            instance_id="order-idempotent-001",
            initial_ctx={"source": "web"},
            idempotency_key=idempotency_key,
        )
        print(f"Created instance: {instance.instance_id}")

        # Retry the same request with the same idempotency key
        # This should return the same result without creating a duplicate
        instance_retry = await client.create_instance(
            machine="order",
            version=1,
            instance_id="order-idempotent-001",
            initial_ctx={"source": "web"},
            idempotency_key=idempotency_key,
        )
        print(f"Retry returned same instance: {instance_retry.instance_id}")

        # Apply an event with idempotency
        event_key = str(uuid.uuid4())

        result = await client.apply_event(
            instance_id="order-idempotent-001",
            event="PAY",
            payload={"amount": 50.00},
            idempotency_key=event_key,
        )
        print(f"First apply: {result.from_state} -> {result.to_state}, applied={result.applied}")

        # Retry the same event - should be idempotent
        result_retry = await client.apply_event(
            instance_id="order-idempotent-001",
            event="PAY",
            payload={"amount": 50.00},
            idempotency_key=event_key,
        )
        print(
            f"Retry apply: {result_retry.from_state} -> {result_retry.to_state}, "
            f"applied={result_retry.applied}"
        )

        # Delete with idempotency
        delete_key = str(uuid.uuid4())
        await client.delete_instance("order-idempotent-001", idempotency_key=delete_key)
        print("Instance deleted")

        # Retry delete - should be idempotent (no error)
        await client.delete_instance("order-idempotent-001", idempotency_key=delete_key)
        print("Delete retry succeeded (idempotent)")


if __name__ == "__main__":
    asyncio.run(main())
