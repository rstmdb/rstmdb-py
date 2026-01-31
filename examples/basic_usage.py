#!/usr/bin/env python3
"""Basic usage example for rstmdb client."""

import asyncio
import uuid

from rstmdb import Client


async def main() -> None:
    # Generate unique names for this run
    run_id = uuid.uuid4().hex[:8]
    machine_name = f"order-{run_id}"
    instance_id = f"order-{run_id}-001"

    # Connect to the server
    async with Client("127.0.0.1", 7401, token="my-secret-token") as client:
        # Ping the server
        await client.ping()
        print("Connected to server")

        # Get server info
        info = await client.info()
        print(f"Server info: {info}")

        # Create a state machine definition
        result = await client.put_machine(
            machine_name,
            1,
            {
                "states": ["created", "paid", "shipped", "delivered"],
                "initial": "created",
                "transitions": [
                    {"from": "created", "event": "PAY", "to": "paid"},
                    {"from": "paid", "event": "SHIP", "to": "shipped"},
                    {"from": "shipped", "event": "DELIVER", "to": "delivered"},
                ],
            },
        )
        print(f"Machine created: {result.machine} v{result.version}")

        # Create an instance of the state machine
        instance = await client.create_instance(
            machine=machine_name,
            version=1,
            instance_id=instance_id,
            initial_ctx={"customer_id": "cust-123", "items": ["item-a", "item-b"]},
        )
        print(f"Instance created: {instance.instance_id} in state '{instance.state}'")

        # Get instance state
        state = await client.get_instance(instance_id)
        print(f"Current state: {state.state}, context: {state.ctx}")

        # Apply events to transition the state machine
        result = await client.apply_event(
            instance_id=instance_id,
            event="PAY",
            payload={"amount": 99.99, "method": "credit_card"},
        )
        print(f"Transition: {result.from_state} -> {result.to_state}")

        result = await client.apply_event(
            instance_id=instance_id,
            event="SHIP",
            payload={"carrier": "FedEx", "tracking": "1234567890"},
        )
        print(f"Transition: {result.from_state} -> {result.to_state}")

        # Get final state
        state = await client.get_instance(instance_id)
        print(f"Final state: {state.state}")

        # List all machines
        machines = await client.list_machines()
        print(f"Registered machines: {machines}")

        # Clean up - delete the instance
        await client.delete_instance(instance_id)
        print("Instance deleted")


if __name__ == "__main__":
    asyncio.run(main())
