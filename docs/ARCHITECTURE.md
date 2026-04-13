# TinyWebSDR Architecture (MVP)

## Goal
- Build a real-time shortwave waterfall visualization using RTL-SDR v4.
- Render SDR++-style waterfall in browser with stable general-latency updates.

## MVP Decisions (Fixed for Phase 1)
- Hardware access: Python RTL-SDR API direct control, single process singleton.
- IQ ingest in backend: Python reads IQ samples directly from RTL-SDR device.
- Processing: Python producer computes FFT and dB scaling per row.
- Bus between backend and gateway: shared memory, latest-row only.
- Browser transport: WebSocket binary frames.
- Renderer: 2D canvas first for stability and debugging speed.
- Three.js renderer: Phase 2 after MVP metrics are satisfied.

## Pipeline
1. `src/core_producer.py` opens RTL-SDR device via Python RTL-SDR API.
2. Producer reads IQ samples, performs windowing + FFT, and converts to dB row.
3. Producer writes only latest row to shared memory (`latest-only` policy).
4. `src/ws_server.py` reads latest row and pushes to browser over WebSocket.
5. Browser app draws each row into waterfall texture on 2D canvas.

## Data Contract (MVP)
- Sample type: complex IQ (`uint8 I/Q`) from RTL-SDR API.
- FFT size: `1024` bins.
- Window: Hann.
- Hop size: `512` samples (50% overlap).
- Backend row type: `float32` dB array, length `1024`.
- dB clamp range: `[-110 dB, -20 dB]`.
- WebSocket row type: `uint8` normalized row, length `1024`.
- Normalization rule: `u8 = round((clamp(db, -110, -20) + 110) * 255 / 90)`.
- Binary frame layout (little-endian):
  - `uint32 seq`
  - `float64 t_capture_monotonic_sec`
  - `uint16 bins` (=1024)
  - `uint8[1024] row`

## Performance Targets (MVP)
- End-to-end latency (IQ capture to browser draw): `<= 120 ms` p95.
- Render/update rate in browser: `>= 20 FPS` sustained.
- Frame drop rate at gateway/browser: `< 5%` over 5-minute run.
- Recovery: stream resumes within `<= 3 s` after temporary disconnect.

## Runtime Topology
- Host: Windows 10.
- Linux runtime: WSL2 Ubuntu 22.04.
- SDR stack runs inside one runtime boundary (prefer WSL2 end-to-end).
- Components:
  - `src/core_producer.py`
  - shared memory segment
  - `src/ws_server.py`
  - browser client

## Development Environment
- Primary development host: Windows 10.
- Linux development runtime: WSL2 Ubuntu 22.04.
- Python version: `3.8+` (recommended `3.10+`).
- Required packages: `numpy`, `websockets`, `pyrtlsdr`.
- Browser client is served locally via Python static server (`python -m http.server`).

## Operation Environment (MVP)
- Target runtime: WSL2 Ubuntu 22.04 on Windows 10 host.
- SDR hardware: RTL-SDR v4 connected to host and accessible from WSL2.
- Producer and gateway run in the same Linux runtime boundary for shared memory IPC.
- Browser client runs on host browser and connects to gateway via WebSocket.
- Single-node deployment only (no distributed bus, no multi-instance coordination).

## Failure and Backpressure Policy
- Latest-only overwrite in shared memory; no deep queue in MVP.
- If browser is slow, gateway drops stale rows and sends newest row only.
- On RTL-SDR read/device errors, producer retries with bounded backoff and re-init.

## Out of Scope (MVP)
- Redis pub/sub path.
- `rtl_tcp` network ingest path.
- Multi-client QoS and persistence.
- Advanced Three.js shader pipeline.

## Next Milestones
1. Implement producer + shared memory contract and a row replay test.
2. Implement WebSocket binary protocol and browser 2D canvas renderer.
3. Measure latency/FPS/drop and lock ADR from "Proposed" to "Accepted".

## Related Docs
- `docs/PROTOCOL.md`: WebSocket binary frame specification for gateway/client.
