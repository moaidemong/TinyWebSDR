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
from websockets.exceptions import ConnectionClosed


HEADER_FORMAT = "<I d H"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
AM_HEADER_FORMAT = "<I d I H"
AM_HEADER_SIZE = struct.calcsize(AM_HEADER_FORMAT)
DEFAULT_BINS = 8192
IQPRODUCER_MAGIC = b"IQPROD1\0"
IQPRODUCER_CONTROL_FORMAT = "<8sIIIIIIQqQQQ"
IQPRODUCER_CONTROL_STRUCT = struct.Struct(IQPRODUCER_CONTROL_FORMAT)


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


class IQProducerControlReader:
    def __init__(self, prefix: str) -> None:
        self.shm = shared_memory.SharedMemory(name=f"{prefix}_control", create=False)
        resource_tracker.unregister(self.shm._name, "shared_memory")
        self.buf = self.shm.buf

    def read_meta(self) -> dict[str, float] | None:
        values = IQPRODUCER_CONTROL_STRUCT.unpack(
            bytes(self.buf[: IQPRODUCER_CONTROL_STRUCT.size])
        )
        if values[0] != IQPRODUCER_MAGIC:
            return None
        return {
            "sample_rate_hz": float(values[4]),
            "center_freq_hz": float(values[7]),
        }

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
    iq_prefix: str,
) -> None:
    interval = 1.0 / send_fps if send_fps > 0 else 0.005
    state_path = Path(state_file) if state_file else None
    control_path = Path(control_file) if control_file else None

    async def handler(ws):
        reader: ShmReader | None = None
        audio_reader: AudioShmReader | None = None
        iq_control: IQProducerControlReader | None = None
        active_shm = shm_name
        last_state_emit = 0.0
        last_state_sig = ""
        last_audio_seq = -1
        last_hover_write = 0.0
        last_seq = -1
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=interval)
                except TimeoutError:
                    raw = None
                except ConnectionClosed:
                    break

                if isinstance(raw, str):
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        msg = None
                    if msg is not None and msg.get("type") == "hover" and control_path is not None:
                        now = time.time()
                        if now - last_hover_write >= 0.08:
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

                now = time.time()

                meta_state: dict | None = None
                if state_path is not None:
                    state = load_state(state_path)
                    if state is not None:
                        meta_state = state
                        desired = state.get("active_shm", active_shm)
                        if isinstance(desired, str) and desired and desired != active_shm:
                            if reader is not None:
                                reader.close()
                                reader = None
                            if audio_reader is not None:
                                audio_reader.close()
                                audio_reader = None
                            active_shm = desired

                if iq_control is None:
                    try:
                        iq_control = IQProducerControlReader(iq_prefix)
                    except FileNotFoundError:
                        iq_control = None

                if now - last_state_emit >= meta_interval:
                    if meta_state is None:
                        meta_state = {}
                    if iq_control is not None:
                        fallback_meta = iq_control.read_meta()
                        if fallback_meta is not None:
                            meta_state.setdefault("center_freq_hz", fallback_meta["center_freq_hz"])
                            meta_state.setdefault("sample_rate_hz", fallback_meta["sample_rate_hz"])
                    meta = {
                        "type": "meta",
                        "band_name": meta_state.get("band_name", ""),
                        "center_freq_hz": meta_state.get("center_freq_hz"),
                        "sample_rate_hz": meta_state.get("sample_rate_hz"),
                        "next_change_epoch_sec": meta_state.get("next_change_epoch_sec"),
                    }
                    sig = json.dumps(meta, sort_keys=True)
                    if sig != last_state_sig or now - last_state_emit >= (meta_interval * 3):
                        await ws.send(sig)
                        last_state_sig = sig
                    last_state_emit = now

                if reader is None:
                    try:
                        reader = ShmReader(active_shm)
                    except FileNotFoundError:
                        continue
                if audio_reader is None:
                    try:
                        audio_reader = AudioShmReader(f"{active_shm}_audio")
                    except FileNotFoundError:
                        audio_reader = None

                frame = reader.read_frame()
                if frame is not None:
                    seq, _, _ = struct.unpack(HEADER_FORMAT, frame[:HEADER_SIZE])
                    if seq != last_seq:
                        await ws.send(frame)
                        last_seq = seq

                if audio_reader is not None:
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
                            await ws.send(json.dumps(payload))
                            last_audio_seq = aseq
        finally:
            if reader is not None:
                reader.close()
            if audio_reader is not None:
                audio_reader.close()
            if iq_control is not None:
                iq_control.close()

    async with serve(handler, host, port, max_size=None):
        await asyncio.Future()


def main() -> None:
    p = argparse.ArgumentParser(description="TinyWebSDR websocket gateway")
    p.add_argument("--shm-name", default="tinywebsdr_latest")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--fps", type=float, default=120.0)
    p.add_argument("--state-file", default="runtime/band_state.json")
    p.add_argument("--meta-interval", type=float, default=1.0)
    p.add_argument("--control-file", default="runtime/hover_control.json")
    p.add_argument("--iq-prefix", default="iqproducer")
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
            args.iq_prefix,
        )
    )


if __name__ == "__main__":
    main()
