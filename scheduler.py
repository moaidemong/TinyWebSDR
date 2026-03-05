#!/usr/bin/env python3
"""Time-based band scheduler with A/B producer handover."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class BandProfile:
    name: str
    start: dtime
    end: dtime
    center_freq: int
    sample_rate: int
    gain: str
    fps: int
    db_offset: float


SCHEDULE: list[BandProfile] = [
    BandProfile("Night SW", dtime(0, 0), dtime(8, 0), 6_850_000, 2_400_000, "38.6", 60, -35.0),
    BandProfile("Morning 9-11MHz", dtime(8, 0), dtime(13, 0), 10_000_000, 2_000_000, "38.6", 60, -35.0),
    BandProfile("Afternoon 13-15MHz", dtime(13, 0), dtime(18, 0), 14_000_000, 2_000_000, "38.6", 60, -35.0),
    BandProfile("Evening SW", dtime(18, 0), dtime(23, 59, 59), 6_850_000, 2_400_000, "38.6", 60, -35.0),
]


def find_profile(now_local: datetime) -> BandProfile:
    t = now_local.time()
    for p in SCHEDULE:
        if p.start <= t < p.end:
            return p
    return SCHEDULE[0]


def next_change_epoch(now_local: datetime, tz: ZoneInfo) -> float:
    t = now_local.time()
    for p in SCHEDULE:
        if t < p.end:
            return datetime.combine(now_local.date(), p.end, tzinfo=tz).timestamp()
    tomorrow = now_local.date().fromordinal(now_local.date().toordinal() + 1)
    return datetime.combine(tomorrow, SCHEDULE[0].start, tzinfo=tz).timestamp()


def producer_cmd(python_bin: str, shm_name: str, profile: BandProfile) -> list[str]:
    return [
        python_bin,
        "core_producer.py",
        "--source",
        "rtlsdr",
        "--shm-name",
        shm_name,
        "--center-freq",
        str(profile.center_freq),
        "--sample-rate",
        str(profile.sample_rate),
        "--gain",
        profile.gain,
        "--fps",
        str(profile.fps),
        "--db-offset",
        str(profile.db_offset),
    ]


def write_state(state_file: Path, shm_name: str, profile: BandProfile, tz: ZoneInfo) -> None:
    now = datetime.now(tz)
    payload = {
        "active_shm": shm_name,
        "band_name": profile.name,
        "center_freq_hz": profile.center_freq,
        "sample_rate_hz": profile.sample_rate,
        "gain": profile.gain,
        "fps": profile.fps,
        "db_offset": profile.db_offset,
        "updated_epoch_sec": now.timestamp(),
        "updated_local": now.isoformat(),
        "next_change_epoch_sec": next_change_epoch(now, tz),
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, state_file)


def main() -> None:
    p = argparse.ArgumentParser(description="TinyWebSDR day-part scheduler")
    p.add_argument("--state-file", default="runtime/band_state.json")
    p.add_argument("--timezone", default="Asia/Seoul")
    p.add_argument("--python-bin", default=sys.executable)
    p.add_argument("--warmup-sec", type=float, default=2.5)
    args = p.parse_args()

    tz = ZoneInfo(args.timezone)
    state_file = Path(args.state_file)
    stop = False

    def _stop(_sig: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    slots = ["tinywebsdr_a", "tinywebsdr_b"]
    slot_idx = 0

    current_profile = find_profile(datetime.now(tz))
    proc = subprocess.Popen(producer_cmd(args.python_bin, slots[slot_idx], current_profile))
    time.sleep(max(0.5, args.warmup_sec))
    if proc.poll() is not None:
        raise RuntimeError("initial producer failed to start")
    write_state(state_file, slots[slot_idx], current_profile, tz)
    print(f"[scheduler] active={current_profile.name} shm={slots[slot_idx]}")

    try:
        while not stop:
            now = datetime.now(tz)
            desired = find_profile(now)
            if desired != current_profile:
                next_slot = 1 - slot_idx
                new_proc = subprocess.Popen(
                    producer_cmd(args.python_bin, slots[next_slot], desired)
                )
                time.sleep(max(0.5, args.warmup_sec))
                if new_proc.poll() is not None:
                    print("[scheduler] new producer failed; keep current profile")
                else:
                    write_state(state_file, slots[next_slot], desired, tz)
                    old = proc
                    proc = new_proc
                    slot_idx = next_slot
                    current_profile = desired
                    old.terminate()
                    try:
                        old.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        old.kill()
                    print(f"[scheduler] switched to {current_profile.name} shm={slots[slot_idx]}")
            time.sleep(1.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
