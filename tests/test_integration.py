from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from rstmdb import Client, ServerError
from rstmdb.models import ErrorCode

pytestmark = pytest.mark.skipif(
    not os.environ.get("RSTMDB_HOST"),
    reason="Set RSTMDB_HOST to run live-server integration tests",
)


def _server_addr() -> tuple[str, int]:
    return os.environ["RSTMDB_HOST"], int(os.environ.get("RSTMDB_PORT", "7401"))


@pytest.mark.asyncio
async def test_live_server_protocol_parity() -> None:
    """Exercise HELLO, idempotency, BAD_REQUEST, batch, watch_all, status, and backup."""
    host, port = _server_addr()
    suffix = uuid.uuid4().hex[:8]
    machine = f"order_{suffix}"

    async with Client(host, port) as client:
        assert "durable_idempotency" in client.negotiated_features

        put_res = await client.put_machine(
            machine,
            1,
            {
                "states": ["created", "paid", "shipped"],
                "initial": "created",
                "transitions": [
                    {"from": "created", "event": "PAY", "to": "paid"},
                    {"from": "paid", "event": "SHIP", "to": "shipped"},
                ],
            },
        )
        assert put_res.machine == machine

        # Non-object initial_ctx must be rejected as non-retryable BAD_REQUEST.
        with pytest.raises(ServerError) as bad_req:
            await client.create_instance(machine, 1, initial_ctx=["not", "an", "object"])  # type: ignore[arg-type]
        assert bad_req.value.code == ErrorCode.BAD_REQUEST
        assert bad_req.value.retryable is False

        # CREATE_INSTANCE honors idempotency_key.
        inst_id = f"inst-{suffix}"
        create_key = f"create-{suffix}"
        c1 = await client.create_instance(
            machine,
            1,
            instance_id=inst_id,
            initial_ctx={"amount": 10},
            idempotency_key=create_key,
        )
        c2 = await client.create_instance(
            machine,
            1,
            instance_id=inst_id,
            initial_ctx={"amount": 10},
            idempotency_key=create_key,
        )
        assert c1.instance_id == inst_id
        assert c2.wal_offset == c1.wal_offset

        # Watch filtered events before applying transitions.
        sub = await client.watch_all(machines=[machine], events=["PAY"])
        assert sub.subscription_id

        # APPLY_EVENT replay returns applied=False.
        pay_key = f"pay-{suffix}"
        a1 = await client.apply_event(
            inst_id,
            "PAY",
            payload={"paid": True},
            idempotency_key=pay_key,
            event_id="evt-1",
        )
        assert a1.applied is True
        a2 = await client.apply_event(
            inst_id,
            "PAY",
            payload={"paid": True},
            idempotency_key=pay_key,
            event_id="evt-1",
        )
        assert a2.applied is False
        assert a2.wal_offset == a1.wal_offset

        # Confirm watch stream delivers the PAY event.
        async def _next_event() -> str:
            async for ev in client.events():
                if ev.instance_id == inst_id and ev.event == "PAY":
                    return ev.to_state
            raise AssertionError("event stream ended")

        seen_state = await asyncio.wait_for(_next_event(), timeout=5.0)
        assert seen_state == "paid"
        await client.unwatch(sub.subscription_id)

        # BATCH execution.
        batch_res = await client.batch(
            [{"op": "APPLY_EVENT", "params": {"instance_id": inst_id, "event": "SHIP"}}],
            mode="best_effort",
        )
        assert batch_res["results"][0]["status"] == "ok"

        # REPLICATION_STATUS & hot BACKUP_* pagination.
        status = await client.replication_status()
        assert status["role"] == "standalone"

        beg = await client.backup_begin(compression="gzip")
        offset = 0
        downloaded = 0
        while True:
            chk = await client.backup_chunk(beg.backup_id, offset=offset)
            downloaded += len(chk.bytes)
            if chk.eof:
                break
            offset += beg.chunk_size
        assert downloaded > 0
        end = await client.backup_end(beg.backup_id)
        assert end.ok is True
