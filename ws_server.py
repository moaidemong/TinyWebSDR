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
AM_HEADER_FORMAT = "<I d I H"
AM_HEADER_SIZE = struct.calcsize(AM_HEADER_FORMAT)
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


class AudioShmReader:
    def __init__(self, name: str) -> None:
        self.shm = shared_memory.SharedMemory(name=name, create=False)
        resource_tracker.unregister(self.shm._name, "shared_memory")
        self.buf = self.shm.buf

    def read_chunk(self) -> tuple[int, int, list[float]] | None:
        head = bytes(self.buf[:AM_HEADER_SIZE])
        seq, _t_capture, freq_hz, n = struct.unpack(AM_HEADER_FORMAT, head)
        if n <= 0 or n > 1024:
            return None
        payload = bytes(self.buf[AM_HEADER_SIZE : AM_HEADER_SIZE + (n * 2)])
        samples_i16 = struct.unpack("<" + ("h" * n), payload)
        samples = [max(-1.0, min(1.0, s / 32768.0)) for s in samples_i16]
        return seq, freq_hz, samples

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
    shm_name: str,
    host: str,
    port: int,
    send_fps: float,
    state_file: str,
    meta_interval: float,
    control_file: str,
) -> None:
    clients: set = set()
    reader: ShmReader | None = None
    audio_reader: AudioShmReader | None = None
    interval = 1.0 / send_fps if send_fps > 0 else 0.005
    state_path = Path(state_file) if state_file else None
    control_path = Path(control_file) if control_file else None
    active_shm = shm_name
    last_state_emit = 0.0
    last_state_sig = ""
    last_audio_seq = -1
    last_hover_write = 0.0

    async def handler(ws):
        nonlocal last_hover_write
        clients.add(ws)
        try:
            async for raw in ws:
                if not isinstance(raw, str):
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "hover" or control_path is None:
                    continue
                now = time.time()
                if now - last_hover_write < 0.08:
                    continue
                freq = float(msg.get("freq_hz", 0.0))
                strength = float(msg.get("strength", 0.0))
                payload = {
                    "mode": "am",
                    "hover_freq_hz": freq,
                    "strength": strength,
                    "updated_epoch_sec": now,
                }
                control_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = control_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
                tmp.replace(control_path)
                last_hover_write = now
        finally:
            clients.discard(ws)

    async def broadcaster() -> None:
        nonlocal reader, audio_reader, active_shm, last_state_emit, last_state_sig, last_audio_seq
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
                        if audio_reader is not None:
                            audio_reader.close()
                            audio_reader = None
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
            if audio_reader is None:
                try:
                    audio_reader = AudioShmReader(f"{active_shm}_audio")
                except FileNotFoundError:
                    audio_reader = None

            frame = reader.read_frame()
            if frame is not None:
                seq, _, _ = struct.unpack(HEADER_FORMAT, frame[:HEADER_SIZE])
                if seq != last_seq and clients:
                    await asyncio.gather(
                        *(c.send(frame) for c in tuple(clients)),
                        return_exceptions=True,
                    )
                    last_seq = seq
            if audio_reader is not None and clients:
                chunk = audio_reader.read_chunk()
                if chunk is not None:
                    aseq, freq_hz, samples = chunk
                    if aseq != last_audio_seq:
                        payload = {
                            "type": "am_wave",
                            "freq_hz": freq_hz,
                            "sample_rate_hz": 8000,
                            "samples": samples,
                        }
                        await asyncio.gather(
                            *(c.send(json.dumps(payload)) for c in tuple(clients)),
                            return_exceptions=True,
                        )
                        last_audio_seq = aseq
            await asyncio.sleep(interval)

    try:
        async with serve(handler, host, port, max_size=None):
            await broadcaster()
    finally:
        if reader is not None:
            reader.close()
        if audio_reader is not None:
            audio_reader.close()


def main() -> None:
    p = argparse.ArgumentParser(description="TinyWebSDR websocket gateway")
    p.add_argument("--shm-name", default="tinywebsdr_latest")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--fps", type=float, default=120.0)
    p.add_argument("--state-file", default="runtime/band_state.json")
    p.add_argument("--meta-interval", type=float, default=1.0)
    p.add_argument("--control-file", default="runtime/hover_control.json")
    args = p.parse_args()
    asyncio.run(
        run_server(
            args.shm_name,
            args.host,
            args.port,
            args.fps,
            args.state_file,
            args.meta_interval,
            args.control_file,
        )
    )


if __name__ == "__main__":
    main()
