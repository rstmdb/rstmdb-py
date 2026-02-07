#!/usr/bin/env python3
"""Example demonstrating list_instances and wal_stats functionality."""

import asyncio
import uuid

from rstmdb import Client


async def main() -> None:
    # Generate unique names for this run
    run_id = uuid.uuid4().hex[:8]
    machine_name = f"order-{run_id}"

    async with Client("127.0.0.1", 7401, token="my-secret-token") as client:
        print("Connected to server\n")

        # Create a state machine definition
        await client.put_machine(
            machine_name,
            1,
            {
                "states": ["pending", "processing", "completed", "failed"],
                "initial": "pending",
                "transitions": [
                    {"from": "pending", "event": "START", "to": "processing"},
                    {"from": "processing", "event": "COMPLETE", "to": "completed"},
                    {"from": "processing", "event": "FAIL", "to": "failed"},
                ],
            },
        )
        print(f"Created machine: {machine_name}\n")

        # Create multiple instances in different states
        instance_ids = []
        for i in range(5):
            instance = await client.create_instance(
                machine=machine_name,
                version=1,
                instance_id=f"{machine_name}-{i:03d}",
                initial_ctx={"order_number": i + 1000},
            )
            instance_ids.append(instance.instance_id)

        # Transition some instances to different states
        # Instance 0, 1 -> processing
        await client.apply_event(instance_ids[0], "START")
        await client.apply_event(instance_ids[1], "START")

        # Instance 0 -> completed
        await client.apply_event(instance_ids[0], "COMPLETE")

        # Instance 1 -> failed
        await client.apply_event(instance_ids[1], "FAIL")

        # Instance 2 -> processing
        await client.apply_event(instance_ids[2], "START")

        print("Created 5 instances in various states\n")

        # =====================================================================
        # List all instances (no filters)
        # =====================================================================
        print("=" * 60)
        print("LIST ALL INSTANCES")
        print("=" * 60)

        result = await client.list_instances()
        print(f"Total instances: {result.total}")
        print(f"Has more: {result.has_more}\n")

        for inst in result.instances:
            print(f"  {inst.id}: state={inst.state}, machine={inst.machine}")

        # =====================================================================
        # List instances filtered by machine
        # =====================================================================
        print("\n" + "=" * 60)
        print(f"LIST INSTANCES FOR MACHINE '{machine_name}'")
        print("=" * 60)

        result = await client.list_instances(machine=machine_name)
        print(f"Found {result.total} instances\n")

        for inst in result.instances:
            print(f"  {inst.id}: state={inst.state}")

        # =====================================================================
        # List instances filtered by state
        # =====================================================================
        print("\n" + "=" * 60)
        print("LIST INSTANCES IN 'pending' STATE")
        print("=" * 60)

        result = await client.list_instances(
            machine=machine_name,
            state="pending",
        )
        print(f"Found {result.total} pending instances\n")

        for inst in result.instances:
            print(f"  {inst.id}: state={inst.state}")

        # =====================================================================
        # List instances with pagination
        # =====================================================================
        print("\n" + "=" * 60)
        print("LIST INSTANCES WITH PAGINATION (limit=2)")
        print("=" * 60)

        # First page
        result = await client.list_instances(
            machine=machine_name,
            limit=2,
            offset=0,
        )
        print(f"Page 1 (offset=0, limit=2): {len(result.instances)} items, has_more={result.has_more}")
        for inst in result.instances:
            print(f"  {inst.id}: state={inst.state}")

        # Second page
        result = await client.list_instances(
            machine=machine_name,
            limit=2,
            offset=2,
        )
        print(f"\nPage 2 (offset=2, limit=2): {len(result.instances)} items, has_more={result.has_more}")
        for inst in result.instances:
            print(f"  {inst.id}: state={inst.state}")

        # Third page
        result = await client.list_instances(
            machine=machine_name,
            limit=2,
            offset=4,
        )
        print(f"\nPage 3 (offset=4, limit=2): {len(result.instances)} items, has_more={result.has_more}")
        for inst in result.instances:
            print(f"  {inst.id}: state={inst.state}")

        # =====================================================================
        # WAL Statistics
        # =====================================================================
        print("\n" + "=" * 60)
        print("WAL STATISTICS")
        print("=" * 60)

        stats = await client.wal_stats()
        print(f"Entry count:      {stats.entry_count}")
        print(f"Segment count:    {stats.segment_count}")
        print(f"Total size:       {stats.total_size_bytes:,} bytes")
        print(f"Latest offset:    {stats.latest_offset}")
        print("\nI/O Statistics:")
        print(f"  Bytes written:  {stats.io_stats.bytes_written:,}")
        print(f"  Bytes read:     {stats.io_stats.bytes_read:,}")
        print(f"  Write ops:      {stats.io_stats.writes}")
        print(f"  Read ops:       {stats.io_stats.reads}")
        print(f"  Fsync calls:    {stats.io_stats.fsyncs}")

        # =====================================================================
        # Cleanup
        # =====================================================================
        print("\n" + "=" * 60)
        print("CLEANUP")
        print("=" * 60)

        for instance_id in instance_ids:
            await client.delete_instance(instance_id)
        print(f"Deleted {len(instance_ids)} instances")


if __name__ == "__main__":
    asyncio.run(main())
