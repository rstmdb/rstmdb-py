#!/usr/bin/env python3
"""TLS and mTLS connection examples for rstmdb client."""

import asyncio

from rstmdb import Client


async def connect_with_tls() -> None:
    """Connect using TLS with CA certificate verification."""
    client = Client(
        "rstmdb.example.com",
        7401,
        token="my-secret-token",
        tls=True,
        ca_cert="./certs/ca-cert.pem",
    )

    async with client:
        await client.ping()
        print("Connected with TLS")


async def connect_with_mtls() -> None:
    """Connect using mutual TLS (mTLS) with client certificate."""
    client = Client(
        "rstmdb.example.com",
        7401,
        token="my-secret-token",
        tls=True,
        ca_cert="./certs/ca-cert.pem",
        client_cert="./certs/client-cert.pem",
        client_key="./certs/client-key.pem",
    )

    async with client:
        await client.ping()
        print("Connected with mTLS")


async def connect_insecure() -> None:
    """Connect with TLS but skip certificate verification (development only)."""
    client = Client(
        "localhost",
        7401,
        token="my-secret-token",
        tls=True,
        insecure=True,  # WARNING: Only use for development!
    )

    async with client:
        await client.ping()
        print("Connected with insecure TLS (dev mode)")


async def connect_with_custom_timeouts() -> None:
    """Connect with custom timeout settings."""
    client = Client(
        "rstmdb.example.com",
        7401,
        token="my-secret-token",
        tls=True,
        ca_cert="./certs/ca-cert.pem",
        connect_timeout=5.0,   # 5 second connection timeout
        request_timeout=60.0,  # 60 second request timeout for long operations
    )

    async with client:
        # This operation might take longer, but we have a 60s timeout
        result = await client.compact(force_snapshot=True)
        print(f"Compaction result: {result}")


async def main() -> None:
    """Demonstrate different connection modes."""
    print("TLS Connection Examples")
    print("=" * 40)
    print()
    print("1. TLS with CA verification:")
    print('   Client(..., tls=True, ca_cert="./certs/ca-cert.pem")')
    print()
    print("2. mTLS with client certificate:")
    print('   Client(..., tls=True, ca_cert="...", client_cert="...", client_key="...")')
    print()
    print("3. Insecure TLS (dev only):")
    print("   Client(..., tls=True, insecure=True)")
    print()

    # Example: connect insecurely to localhost for development
    # Uncomment to run:
    # await connect_insecure()


if __name__ == "__main__":
    asyncio.run(main())
