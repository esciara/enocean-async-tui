"""Passive EnOcean dongle discovery via USB VID/PID matching."""

from __future__ import annotations

import asyncio

import serial.tools.list_ports

# Known (VID, PID) pairs for EnOcean USB dongles.
# FTDI FT232R (USB300/300J) and Silicon Labs CP2102 (USB300U variants).
ENOCEAN_VID_PIDS: frozenset[tuple[int, int]] = frozenset({
    (0x0403, 0x6001),  # FTDI FT232R — USB300 / USB300J
    (0x0403, 0x6010),  # FTDI FT2232H
    (0x0403, 0xB401),  # EnOcean proprietary PID
    (0x10C4, 0xEA60),  # Silicon Labs CP2102 — USB300U
})


async def discover_dongles() -> list[str]:
    """Return serial port names of connected EnOcean dongles.

    Passive: no probe commands sent. Wraps the blocking comports() call
    in asyncio.to_thread so the event loop is never blocked.
    """
    ports = await asyncio.to_thread(serial.tools.list_ports.comports)
    return [
        p.device
        for p in ports
        if p.vid is not None and p.pid is not None and (p.vid, p.pid) in ENOCEAN_VID_PIDS
    ]
