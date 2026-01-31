#!/usr/bin/env python3
"""Event watching example for rstmdb client.

This example demonstrates how to watch for state machine events.
To see events, you need to run this script in one terminal, then
run basic_usage.py (or apply events) in another terminal.
"""

import asyncio
import uuid

from rstmdb import Client


async def watch_all_events() -> None:
    """Watch ALL events across all machines (no filters)."""
    async with Client("127.0.0.1", 7401, token="my-secret-token") as client:
        # Watch all events without any filters
        sub = await client.watch_all(include_ctx=True)
        print(f"Watching ALL events")
        print(f"Subscription ID: {sub.subscription_id}")
        print(f"Starting from WAL offset: {sub.wal_offset}")
        print()
        print("Waiting for events... (run basic_usage.py in another terminal)")
        print("-" * 60)

        event_count = 0
        async for event in client.events():
            event_count += 1
            print(f"\n[Event #{event_count}]")
            print(f"  Machine:    {event.machine} v{event.version}")
            print(f"  Instance:   {event.instance_id}")
            print(f"  Transition: {event.from_state} -> {event.to_state}")
            print(f"  Event:      {event.event}")
            print(f"  WAL offset: {event.wal_offset}")
            if event.payload:
                print(f"  Payload:    {event.payload}")
            if event.ctx:
                print(f"  Context:    {event.ctx}")


async def watch_with_auto_reconnect() -> None:
    """Watch events with automatic reconnection.

    This version will automatically reconnect if the server goes down
    and re-establish the watch subscription.
    """
    # Create client with auto_reconnect enabled
    client = Client(
        "127.0.0.1",
        7401,
        token="my-secret-token",
        auto_reconnect=True,
        reconnect_base_delay=1.0,
        reconnect_max_delay=30.0,
    )

    try:
        await client.connect()
        print("Connected to server")
        print("Watching with auto-reconnect enabled...")
        print("Try stopping and restarting the server to test reconnection")
        print("-" * 60)

        # Call watch_all() first - this stores the params for reconnection
        sub = await client.watch_all(include_ctx=True)
        print(f"Subscription: {sub.subscription_id}")

        event_count = 0
        # events() will automatically reconnect and re-subscribe if connection drops
        async for event in client.events():
            event_count += 1
            print(f"\n[Event #{event_count}]")
            print(f"  Machine:    {event.machine} v{event.version}")
            print(f"  Instance:   {event.instance_id}")
            print(f"  Transition: {event.from_state} -> {event.to_state}")
            print(f"  Event:      {event.event}")

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await client.close()


async def watch_and_generate() -> None:
    """Watch events while generating them in the same script."""
    async with Client("127.0.0.1", 7401, token="my-secret-token") as client:
        # Create a unique machine for this demo
        run_id = uuid.uuid4().hex[:8]
        machine_name = f"demo-{run_id}"
        instance_id = f"inst-{run_id}"

        # Create the machine
        await client.put_machine(
            machine_name,
            1,
            {
                "states": ["pending", "active", "completed"],
                "initial": "pending",
                "transitions": [
                    {"from": "pending", "event": "START", "to": "active"},
                    {"from": "active", "event": "FINISH", "to": "completed"},
                ],
            },
        )
        print(f"Created machine: {machine_name}")

        # Start watching BEFORE creating the instance
        sub = await client.watch_all(include_ctx=True)
        print(f"Started watching (subscription: {sub.subscription_id})")

        # Create instance - this should trigger an event
        await client.create_instance(machine_name, 1, instance_id)
        print(f"Created instance: {instance_id}")

        # Apply events
        await client.apply_event(instance_id, "START")
        print("Applied START event")

        await client.apply_event(instance_id, "FINISH")
        print("Applied FINISH event")

        # Small delay to ensure events are queued
        await asyncio.sleep(0.1)

        # Now read the events we generated
        print("\n" + "=" * 60)
        print("Events received:")
        print("=" * 60)

        # Use a timeout to avoid blocking forever
        event_count = 0
        try:
            async for event in client.events():
                event_count += 1
                print(f"\n[{event_count}] {event.instance_id}")
                print(f"    {event.from_state} --({event.event})--> {event.to_state}")

                # We expect ~2 transition events (START, FINISH)
                # Note: create_instance may or may not generate an event depending on server
                if event_count >= 3 or event.to_state == "completed":
                    break
        except asyncio.TimeoutError:
            pass

        # Cleanup
        await client.unwatch(sub.subscription_id)
        await client.delete_instance(instance_id)
        print(f"\nCleaned up. Total events received: {event_count}")


async def main() -> None:
    """Run the watch example."""
    print("=" * 60)
    print("rstmdb Event Watching Example")
    print("=" * 60)
    print()
    print("Options:")
    print("  1. watch_all_events() - Watch all events (need another terminal)")
    print("  2. watch_and_generate() - Watch while generating events")
    print("  3. watch_with_auto_reconnect() - Watch with auto-reconnection")
    print()

    # Run watch with reconnect by default
    await watch_with_auto_reconnect()


if __name__ == "__main__":
    asyncio.run(main())
