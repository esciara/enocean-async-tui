"""SnifferScreen — Phase 1-B task 5.

Performance note (task 4.5 spike, 2026-05-07):
  RichLog.write() x 10 000 = ~488 ms in run_test() (size known, real rendering).
  Exceeds the 200 ms threshold — batch_write() helper required.
  Use batch_write() for all bulk writes (e.g. filter re-renders) to keep the
  event loop responsive.
"""

from __future__ import annotations

import asyncio

from textual.widgets import RichLog

_CHUNK_SIZE = 100


async def batch_write(log: RichLog, lines: list[str]) -> None:
    """Write *lines* to *log* in chunks, yielding to the event loop between chunks.

    Prevents blocking the event loop when writing thousands of entries at once,
    e.g. during retroactive filter re-renders.
    """
    for offset in range(0, len(lines), _CHUNK_SIZE):
        for line in lines[offset : offset + _CHUNK_SIZE]:
            log.write(line)
        await asyncio.sleep(0)
