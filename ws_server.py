#!/usr/bin/env python3
"""TinyWebSDR WebSocket gateway.

Reads latest row from shared memory and pushes binary frames to clients.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import struct
import time
from multiprocessing import resource_tracker, shared_memory
from pathlib import Path

from websockets import serve


HEADER_FORMAT = "<I d H"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
DEFAULT_BINS = 8192


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


def load_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


async def run_server(
    shm_name: str, host: str, port: int, send_fps: float, state_file: str, meta_interval: float
) -> None:
    clients: set = set()
    reader: ShmReader | None = None
    interval = 1.0 / send_fps if send_fps > 0 else 0.005
    state_path = Path(state_file) if state_file else None
    active_shm = shm_name
    last_state_emit = 0.0
    last_state_sig = ""

    async def handler(ws):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async def broadcaster() -> None:
        nonlocal reader, active_shm, last_state_emit, last_state_sig
        last_seq = -1
        while True:
            now = time.time()

            if state_path is not None:
                state = load_state(state_path)
                if state is not None:
                    desired = state.get("active_shm", active_shm)
                    if isinstance(desired, str) and desired and desired != active_shm:
                        if reader is not None:
                            reader.close()
                            reader = None
                        active_shm = desired
                    if clients and (now - last_state_emit >= meta_interval):
                        msg = {
                            "type": "meta",
                            "band_name": state.get("band_name", ""),
                            "center_freq_hz": state.get("center_freq_hz"),
                            "sample_rate_hz": state.get("sample_rate_hz"),
                            "next_change_epoch_sec": state.get("next_change_epoch_sec"),
                        }
                        sig = json.dumps(msg, sort_keys=True)
                        if sig != last_state_sig or now - last_state_emit >= (meta_interval * 3):
                            await asyncio.gather(
                                *(c.send(sig) for c in tuple(clients)),
                                return_exceptions=True,
                            )
                            last_state_sig = sig
                        last_state_emit = now

            if reader is None:
                try:
                    reader = ShmReader(active_shm)
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
    p.add_argument("--state-file", default="runtime/band_state.json")
    p.add_argument("--meta-interval", type=float, default=1.0)
    args = p.parse_args()
    asyncio.run(
        run_server(
            args.shm_name,
            args.host,
            args.port,
            args.fps,
            args.state_file,
            args.meta_interval,
        )
    )


if __name__ == "__main__":
    main()
