#!/usr/bin/env python3
"""TinyWebSDR WebSocket gateway.

Reads latest row from shared memory and pushes binary frames to clients.
"""

from __future__ import annotations

import argparse
import asyncio
import struct
from multiprocessing import resource_tracker, shared_memory

from websockets import serve


HEADER_FORMAT = "<I d H"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
DEFAULT_BINS = 1024


class ShmReader:
    def __init__(self, name: str) -> None:
        self.shm = shared_memory.SharedMemory(name=name, create=False)
        # The gateway only attaches to an existing segment and must not unlink it.
        # Unregister from resource_tracker to avoid cross-process unlink races.
        resource_tracker.unregister(self.shm._name, "shared_memory")
        self.buf = self.shm.buf

    def read_frame(self) -> bytes | None:
        head = bytes(self.buf[:HEADER_SIZE])
        seq, t_capture, bins = struct.unpack(HEADER_FORMAT, head)
        if bins != DEFAULT_BINS:
            return None
        row = bytes(self.buf[HEADER_SIZE : HEADER_SIZE + bins])
        return struct.pack(HEADER_FORMAT, seq, t_capture, bins) + row

    def close(self) -> None:
        self.shm.close()


async def run_server(shm_name: str, host: str, port: int, send_fps: float) -> None:
    clients: set = set()
    reader: ShmReader | None = None
    interval = 1.0 / send_fps if send_fps > 0 else 0.005

    async def handler(ws):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async def broadcaster() -> None:
        last_seq = -1
        while True:
            nonlocal reader
            if reader is None:
                try:
                    reader = ShmReader(shm_name)
                except FileNotFoundError:
                    await asyncio.sleep(interval)
                    continue

            frame = reader.read_frame()
            if frame is not None:
                seq, _, _ = struct.unpack(HEADER_FORMAT, frame[:HEADER_SIZE])
                if seq != last_seq and clients:
                    await asyncio.gather(
                        *(c.send(frame) for c in tuple(clients)),
                        return_exceptions=True,
                    )
                    last_seq = seq
            await asyncio.sleep(interval)

    try:
        async with serve(handler, host, port, max_size=None):
            await broadcaster()
    finally:
        if reader is not None:
            reader.close()


def main() -> None:
    p = argparse.ArgumentParser(description="TinyWebSDR websocket gateway")
    p.add_argument("--shm-name", default="tinywebsdr_latest")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--fps", type=float, default=120.0)
    args = p.parse_args()
    asyncio.run(run_server(args.shm_name, args.host, args.port, args.fps))


if __name__ == "__main__":
    main()
