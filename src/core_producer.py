#!/usr/bin/env python3
"""TinyWebSDR producer: generates latest FFT row into shared memory.

MVP behavior:
- Uses simulated IQ source by default (works without RTL hardware).
- Computes 8192-bin FFT rows with Nuttall window, 50% overlap.
- Writes latest row into shared memory as uint8 encoded dB values.
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import struct
import time
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np


HEADER_FORMAT = "<I d H"  # seq, capture epoch seconds, bins
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
AM_HEADER_FORMAT = "<I d I H"  # seq, t_capture, tuned_freq_hz, sample_count
AM_HEADER_SIZE = struct.calcsize(AM_HEADER_FORMAT)
IQPRODUCER_MAGIC = b"IQPROD1\0"
IQPRODUCER_CONTROL_FORMAT = "<8sIIIIIIQqQQQ"
IQPRODUCER_CONTROL_STRUCT = struct.Struct(IQPRODUCER_CONTROL_FORMAT)
DEFAULT_BINS = 8192
DB_MIN = -110.0
DB_MAX = -20.0
AM_AUDIO_RATE = 8000
AM_CHUNK_SAMPLES = 160


class IQSource:
    def read(self, n: int) -> np.ndarray:
        raise NotImplementedError

    def get_sample_rate(self) -> float | None:
        return None

    def get_center_freq(self) -> float | None:
        return None

    def close(self) -> None:
        return None


class SimIQSource(IQSource):
    def __init__(self, sample_rate: float) -> None:
        self.sample_rate = sample_rate
        self.phase_t = time.monotonic()

    def read(self, n: int) -> np.ndarray:
        out = synth_iq(n, self.sample_rate, self.phase_t)
        self.phase_t += n / self.sample_rate
        return out


class RtlSdrIQSource(IQSource):
    def __init__(self, sample_rate: float, center_freq: float, gain: str) -> None:
        try:
            from rtlsdr import RtlSdr
        except ImportError as exc:
            raise RuntimeError(
                "pyrtlsdr is not installed. Run: pip install pyrtlsdr"
            ) from exc
        except Exception as exc:
            msg = str(exc)
            if "rtlsdr_set_dithering" in msg:
                raise RuntimeError(
                    "librtlsdr/pyrtlsdr version mismatch: missing symbol "
                    "'rtlsdr_set_dithering'. Update system librtlsdr or install "
                    "a compatible pyrtlsdr version."
                ) from exc
            raise

        try:
            self.sdr = RtlSdr()
        except Exception as exc:
            msg = str(exc)
            if "rtlsdr_set_dithering" in msg:
                raise RuntimeError(
                    "Failed to initialize RTL-SDR: missing symbol "
                    "'rtlsdr_set_dithering' in system librtlsdr."
                ) from exc
            raise
        self.sdr.sample_rate = sample_rate
        self.sdr.center_freq = center_freq
        if gain.lower() == "auto":
            self.sdr.gain = "auto"
        else:
            self.sdr.gain = float(gain)

    def read(self, n: int) -> np.ndarray:
        # read_samples returns complex64 normalized IQ samples.
        return self.sdr.read_samples(n).astype(np.complex64, copy=False)

    def get_sample_rate(self) -> float | None:
        return float(self.sdr.sample_rate)

    def get_center_freq(self) -> float | None:
        return float(self.sdr.center_freq)

    def close(self) -> None:
        self.sdr.close()


class IQProducerShmSource(IQSource):
    def __init__(self, prefix: str) -> None:
        self.control = shared_memory.SharedMemory(name=f"{prefix}_control", create=False)
        self.proc_i8 = shared_memory.SharedMemory(name=f"{prefix}_proc_i8", create=False)
        _unregister_from_resource_tracker(self.control)
        _unregister_from_resource_tracker(self.proc_i8)
        snap = self._snapshot()
        if snap["magic"] != IQPRODUCER_MAGIC:
            raise RuntimeError(f"Invalid IQProducer shared-memory magic: {snap['magic']!r}")
        if snap["bytes_per_sample"] != 2:
            raise RuntimeError(
                f"Unsupported IQProducer bytes_per_sample={snap['bytes_per_sample']}; expected 2"
            )
        self.block_size = int(snap["block_size"])
        self.block_count = int(snap["block_count"])
        self.block_bytes = self.block_size * 2
        self.sample_rate = float(snap["sample_rate"])
        self.center_freq = float(snap["center_freq_hz"])
        self._seq: int | None = None
        self._offset = 0

    def _snapshot(self) -> dict[str, int | bytes]:
        values = IQPRODUCER_CONTROL_STRUCT.unpack(
            bytes(self.control.buf[: IQPRODUCER_CONTROL_STRUCT.size])
        )
        return {
            "magic": values[0],
            "version": values[1],
            "block_size": values[2],
            "block_count": values[3],
            "sample_rate": values[4],
            "bytes_per_sample": values[5],
            "flags": values[6],
            "center_freq_hz": values[7],
            "gain_mdb": values[8],
            "write_seq": values[9],
            "overrun_count": values[10],
            "timestamp_ns": values[11],
        }

    def read(self, n: int) -> np.ndarray:
        need_bytes = n * 2
        out = bytearray(need_bytes)
        filled = 0

        while filled < need_bytes:
            snap = self._snapshot()
            write_seq = int(snap["write_seq"])
            available = min(write_seq, self.block_count)
            min_seq = write_seq - available

            if write_seq == 0:
                time.sleep(0.005)
                continue

            if self._seq is None:
                self._seq = max(min_seq, write_seq - 1)
                self._offset = 0

            if self._seq < min_seq:
                self._seq = min_seq
                self._offset = 0

            if self._seq >= write_seq:
                time.sleep(0.002)
                continue

            slot = self._seq % self.block_count
            start = (slot * self.block_bytes) + self._offset
            take = min(need_bytes - filled, self.block_bytes - self._offset)
            out[filled : filled + take] = self.proc_i8.buf[start : start + take]
            filled += take
            self._offset += take

            if self._offset >= self.block_bytes:
                self._seq += 1
                self._offset = 0

        ints = np.frombuffer(out, dtype=np.int8).astype(np.float32, copy=False).reshape(-1, 2)
        return ((ints[:, 0] + 1j * ints[:, 1]) / 128.0).astype(np.complex64, copy=False)

    def get_sample_rate(self) -> float | None:
        return self.sample_rate

    def get_center_freq(self) -> float | None:
        return self.center_freq

    def close(self) -> None:
        self.control.close()
        self.proc_i8.close()


def encode_db_to_u8(db: np.ndarray) -> np.ndarray:
    clipped = np.clip(db, DB_MIN, DB_MAX)
    scaled = np.rint((clipped - DB_MIN) * 255.0 / (DB_MAX - DB_MIN))
    return scaled.astype(np.uint8, copy=False)


def synth_iq(n: int, sample_rate: float, t0: float) -> np.ndarray:
    t = t0 + np.arange(n, dtype=np.float64) / sample_rate
    tone1 = np.exp(1j * 2.0 * math.pi * 120_000.0 * t)
    tone2 = 0.6 * np.exp(1j * 2.0 * math.pi * -240_000.0 * t)
    noise = 0.08 * (np.random.randn(n) + 1j * np.random.randn(n))
    return (tone1 + tone2 + noise).astype(np.complex64)


def nuttall_window(n: int) -> np.ndarray:
    # 4-term Nuttall window improves sidelobe suppression for thin-line rendering.
    i = np.arange(n, dtype=np.float64)
    a0 = 0.355768
    a1 = 0.487396
    a2 = 0.144232
    a3 = 0.012604
    phase = 2.0 * math.pi * i / (n - 1)
    w = a0 - a1 * np.cos(phase) + a2 * np.cos(2.0 * phase) - a3 * np.cos(3.0 * phase)
    return w.astype(np.float32)


def open_shared_memory(name: str, size: int) -> shared_memory.SharedMemory:
    try:
        return shared_memory.SharedMemory(name=name, create=True, size=size)
    except FileExistsError:
        old = shared_memory.SharedMemory(name=name, create=False)
        old.close()
        old.unlink()
        return shared_memory.SharedMemory(name=name, create=True, size=size)


def _unregister_from_resource_tracker(shm: shared_memory.SharedMemory) -> None:
    try:
        from multiprocessing import resource_tracker

        resource_tracker.unregister(shm._name, "shared_memory")
    except Exception:
        pass


def build_source(
    source_kind: str,
    sample_rate: float,
    center_freq: float,
    gain: str,
    iq_prefix: str,
) -> IQSource:
    if source_kind == "sim":
        return SimIQSource(sample_rate)
    if source_kind == "rtlsdr":
        return RtlSdrIQSource(sample_rate, center_freq, gain)
    if source_kind == "iqproducer":
        return IQProducerShmSource(iq_prefix)
    raise ValueError(f"Unsupported source: {source_kind}")


def run(
    shm_name: str,
    audio_shm_name: str,
    control_file: str,
    sample_rate: float,
    target_fps: float,
    source_kind: str,
    center_freq: float,
    gain: str,
    db_offset: float,
    iq_prefix: str,
) -> None:
    bins = DEFAULT_BINS
    hop = bins // 2
    win = nuttall_window(bins)
    shm_size = HEADER_SIZE + bins
    am_shm_size = AM_HEADER_SIZE + (AM_CHUNK_SAMPLES * 2)
    source: IQSource | None = None
    shm: shared_memory.SharedMemory | None = None
    am_shm: shared_memory.SharedMemory | None = None
    source = build_source(source_kind, sample_rate, center_freq, gain, iq_prefix)
    source_sample_rate = source.get_sample_rate()
    if source_sample_rate is not None and source_sample_rate > 0:
        sample_rate = float(source_sample_rate)
    source_center_freq = source.get_center_freq()
    if source_center_freq is not None and source_center_freq > 0:
        center_freq = float(source_center_freq)
    shm = open_shared_memory(shm_name, shm_size)
    am_shm = open_shared_memory(audio_shm_name, am_shm_size)
    buf = shm.buf
    am_buf = am_shm.buf
    stop = False
    control_path = Path(control_file)

    def _handle_stop(_sig: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    seq = 0
    am_seq = 0
    carry = np.zeros(bins - hop, dtype=np.complex64)
    frame_interval = 1.0 / target_fps if target_fps > 0 else 0.0
    last_control_check = 0.0
    tuned_freq_hz = 0.0
    nco_phase = 0.0
    audio_accum = np.zeros(0, dtype=np.float32)

    try:
        while not stop:
            loop_start = time.monotonic()
            new_iq = source.read(hop)
            block = np.concatenate((carry, new_iq))
            carry = block[hop:]

            # Remove residual DC bias before the spectrum FFT to suppress the center spike.
            fft_block = block - np.mean(block, dtype=np.complex64)
            spec = np.fft.fftshift(np.fft.fft(fft_block * win, n=bins))
            mag = np.abs(spec) / bins
            db = 20.0 * np.log10(mag + 1e-12) + db_offset
            row_u8 = encode_db_to_u8(db)

            payload = struct.pack(HEADER_FORMAT, seq, time.time(), bins)
            buf[:HEADER_SIZE] = payload
            buf[HEADER_SIZE : HEADER_SIZE + bins] = row_u8.tobytes()
            seq += 1

            now = time.time()
            if now - last_control_check >= 0.2:
                last_control_check = now
                if control_path.exists():
                    try:
                        obj = json.loads(control_path.read_text(encoding="utf-8"))
                        freq = float(obj.get("hover_freq_hz", 0.0))
                        updated = float(obj.get("updated_epoch_sec", 0.0))
                        mode = str(obj.get("mode", "am")).lower()
                        if mode == "am" and now - updated <= 3.0:
                            tuned_freq_hz = freq
                        else:
                            tuned_freq_hz = 0.0
                    except (ValueError, OSError, json.JSONDecodeError):
                        tuned_freq_hz = 0.0

            if tuned_freq_hz > 0:
                freq_offset = tuned_freq_hz - center_freq
                max_off = sample_rate * 0.5
                if freq_offset < -max_off:
                    freq_offset = -max_off
                elif freq_offset > max_off:
                    freq_offset = max_off

                n = block.size
                t = np.arange(n, dtype=np.float64)
                phase = nco_phase + (2.0 * math.pi * freq_offset / sample_rate) * t
                mixer = np.exp(-1j * phase).astype(np.complex64)
                mixed = block * mixer
                nco_phase = float((phase[-1] + (2.0 * math.pi * freq_offset / sample_rate)) % (2.0 * math.pi))

                am = np.abs(mixed).astype(np.float32)
                am -= float(np.mean(am))
                am = np.clip(am, -2.0, 2.0)

                decim = max(1, int(sample_rate // AM_AUDIO_RATE))
                usable = (am.size // decim) * decim
                if usable > 0:
                    am_dec = am[:usable].reshape(-1, decim).mean(axis=1)
                    audio_accum = np.concatenate((audio_accum, am_dec)).astype(np.float32, copy=False)

                if audio_accum.size >= AM_CHUNK_SAMPLES:
                    chunk = audio_accum[:AM_CHUNK_SAMPLES]
                    audio_accum = audio_accum[AM_CHUNK_SAMPLES:]
                    peak = float(np.max(np.abs(chunk))) + 1e-6
                    pcm = np.clip((chunk / peak) * 28000.0, -32768, 32767).astype(np.int16)
                    am_payload = struct.pack(
                        AM_HEADER_FORMAT,
                        am_seq,
                        now,
                        int(round(tuned_freq_hz)),
                        AM_CHUNK_SAMPLES,
                    )
                    am_buf[:AM_HEADER_SIZE] = am_payload
                    am_buf[AM_HEADER_SIZE : AM_HEADER_SIZE + (AM_CHUNK_SAMPLES * 2)] = pcm.tobytes()
                    am_seq += 1

            if frame_interval > 0:
                elapsed = time.monotonic() - loop_start
                sleep_s = frame_interval - elapsed
                if sleep_s > 0:
                    time.sleep(sleep_s)
    finally:
        if source is not None:
            source.close()
        if shm is not None:
            shm.close()
            try:
                shm.unlink()
            except FileNotFoundError:
                # Another process (or previous cleanup) may have already removed it.
                pass
        if am_shm is not None:
            am_shm.close()
            try:
                am_shm.unlink()
            except FileNotFoundError:
                pass


def main() -> None:
    p = argparse.ArgumentParser(description="TinyWebSDR FFT producer")
    p.add_argument("--shm-name", default="tinywebsdr_latest")
    p.add_argument("--audio-shm-name", default="tinywebsdr_latest_audio")
    p.add_argument("--control-file", default="runtime/hover_control.json")
    p.add_argument("--sample-rate", type=float, default=2_048_000.0)
    p.add_argument("--fps", type=float, default=60.0)
    p.add_argument("--source", choices=["sim", "rtlsdr", "iqproducer"], default="sim")
    p.add_argument("--center-freq", type=float, default=6_800_000.0)
    p.add_argument("--gain", default="auto")
    p.add_argument("--db-offset", type=float, default=-35.0)
    p.add_argument("--iq-prefix", default="iqproducer")
    args = p.parse_args()
    run(
        args.shm_name,
        args.audio_shm_name,
        args.control_file,
        args.sample_rate,
        args.fps,
        args.source,
        args.center_freq,
        args.gain,
        args.db_offset,
        args.iq_prefix,
    )


if __name__ == "__main__":
    main()
