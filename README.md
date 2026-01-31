# rstmdb-py

[![CI](https://github.com/rstmdb/rstmdb-py/actions/workflows/ci.yml/badge.svg)](https://github.com/rstmdb/rstmdb-py/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/rstmdb)](https://pypi.org/project/rstmdb/)
[![PyPI](https://img.shields.io/pypi/v/rstmdb)](https://pypi.org/project/rstmdb/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Python client library for communicating with the rstmdb server using the RCP (rstmdb Command Protocol).

## Features

- Async-first design using `asyncio`
- Full feature parity with the Rust client
- Type hints with `pydantic` models
- Support for TLS and mTLS
- Event streaming with async iterators

## Installation

```bash
pip install rstmdb
```

For development:

```bash
pip install rstmdb[dev]
```

## Quick Start

```python
import asyncio
from rstmdb import Client

async def main():
    async with Client("127.0.0.1", 7401, token="my-secret-token") as client:
        # Create machine
        await client.put_machine("order", 1, {
            "states": ["created", "paid", "shipped"],
            "initial": "created",
            "transitions": [
                {"from": "created", "event": "PAY", "to": "paid"},
                {"from": "paid", "event": "SHIP", "to": "shipped"},
            ]
        })

        # Create instance
        result = await client.create_instance("order", 1, "order-001")
        print(f"Created: {result.instance_id} in state {result.state}")

        # Apply event
        result = await client.apply_event("order-001", "PAY", {"amount": 99.99})
        print(f"Transition: {result.from_state} -> {result.to_state}")

asyncio.run(main())
```

## Watch Events

```python
import asyncio
from rstmdb import Client

async def main():
    async with Client("127.0.0.1", 7401, token="my-secret-token") as client:
        # Start watching
        sub = await client.watch_all(machines=["order"], to_states=["shipped"])
        print(f"Subscription: {sub.subscription_id}")

        # Process events
        async for event in client.events():
            print(f"Event: {event.instance_id} {event.from_state} -> {event.to_state}")

asyncio.run(main())
```

## TLS/mTLS

```python
from rstmdb import Client

# TLS with CA verification
client = Client(
    "127.0.0.1", 7401,
    token="my-secret-token",
    tls=True,
    ca_cert="./certs/ca-cert.pem",
)

# mTLS
client = Client(
    "127.0.0.1", 7401,
    token="my-secret-token",
    tls=True,
    ca_cert="./certs/ca-cert.pem",
    client_cert="./certs/client-cert.pem",
    client_key="./certs/client-key.pem",
)

# Insecure (dev only)
client = Client(
    "127.0.0.1", 7401,
    token="my-secret-token",
    tls=True,
    insecure=True,
)
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all checks with tox
tox

# Run specific tox environments
tox -e py312        # Run tests with Python 3.12
tox -e lint         # Run linting
tox -e typecheck    # Run type checking
tox -e install      # Verify package installation
tox -e format       # Auto-format code

# Or run tools directly
pytest tests/ -v    # Run tests
mypy src/           # Type checking
ruff check src/     # Linting
ruff format src/    # Formatting
```

## License

MIT
