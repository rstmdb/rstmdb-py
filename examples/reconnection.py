#!/usr/bin/env python3
"""Reconnection example for rstmdb client.

This example demonstrates automatic reconnection when the server
becomes unreachable and comes back online.
"""

import asyncio
import logging

from rstmdb import Client, ConnectionError

# Enable logging to see reconnection attempts
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def on_reconnect() -> None:
    """Callback invoked after successful reconnection."""
    print("*** Reconnected to server! ***")


async def main() -> None:
    """Demonstrate automatic reconnection."""
    print("=" * 60)
    print("rstmdb Reconnection Example")
    print("=" * 60)
    print()
    print("This client will automatically reconnect if the server")
    print("becomes unavailable. Try stopping and restarting the server.")
    print()

    # Create client with auto-reconnect enabled
    client = Client(
        "127.0.0.1",
        7401,
        token="my-secret-token",
        # Enable automatic reconnection
        auto_reconnect=True,
        # Unlimited reconnection attempts (0 = unlimited)
        max_reconnect_attempts=0,
        # Start with 1 second delay
        reconnect_base_delay=1.0,
        # Max delay of 30 seconds between attempts
        reconnect_max_delay=30.0,
        # Callback when reconnected
        on_reconnect=on_reconnect,
    )

    try:
        # Initial connection
        print("Connecting to server...")
        await client.connect()
        print(f"Connected! is_connected={client.is_connected}")

        # Periodic ping to demonstrate reconnection
        ping_count = 0
        while True:
            try:
                await client.ping()
                ping_count += 1
                print(f"Ping #{ping_count} successful")
            except ConnectionError as e:
                print(f"Connection error: {e}")
                print("Will attempt to reconnect on next request...")

            await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.close()
        print("Client closed")


async def manual_reconnect_example() -> None:
    """Example of manual reconnection handling."""
    client = Client(
        "127.0.0.1",
        7401,
        token="my-secret-token",
        # Disable auto-reconnect for manual control
        auto_reconnect=False,
    )

    try:
        await client.connect()
        print("Connected!")

        while True:
            try:
                if not client.is_connected:
                    print("Connection lost, attempting manual reconnect...")
                    await client.reconnect()
                    print("Reconnected!")

                await client.ping()
                print("Ping successful")

            except ConnectionError as e:
                print(f"Error: {e}")
                print("Waiting 5 seconds before retry...")
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.close()


async def limited_retries_example() -> None:
    """Example with limited reconnection attempts."""
    client = Client(
        "127.0.0.1",
        7401,
        token="my-secret-token",
        auto_reconnect=True,
        # Only try 5 times before giving up
        max_reconnect_attempts=5,
        reconnect_base_delay=2.0,
        reconnect_max_delay=10.0,
    )

    try:
        await client.connect()
        print("Connected!")

        while True:
            try:
                await client.ping()
                print("Ping successful")
            except ConnectionError as e:
                print(f"Fatal connection error: {e}")
                print("Max reconnection attempts exceeded, giving up.")
                break

            await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
