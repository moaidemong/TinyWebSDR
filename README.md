# TinyWebSDR

A real-time shortwave waterfall visualization system for low-latency browser-based spectrum display.
The current primary runtime path uses `OpenWebRX -> IQProducer shared memory -> TinyWebSDR`.

## Quick Start

### Prerequisites
- Linux host with Python 3.8+
- OpenWebRX with local `rtltcp_compat` enabled
- `IQProducer` available on the same host

### Setup
1. Clone repository: `git clone <repo-url>`
2. Move to project directory:
   `cd /home/moai/Workspace/Codex/TinyWebSDR`
3. Install Python dependencies or create a local `.venv`:
   `python3 -m pip install -r requirements.txt`
4. Normalize shell script line endings (once):
   `sed -i 's/\r$//' script/run_mvp.sh`
5. Start TinyWebSDR in the current primary mode:
   `chmod +x script/run_mvp.sh && ./script/run_mvp.sh --source iqproducer --iq-prefix iqproducer`
6. Open browser client at `http://127.0.0.1:8080` or your server LAN address such as `http://192.168.219.109:8080`

### Legacy RTL Device Mode
Direct RTL-SDR capture is still available, but it is no longer the primary runtime path.

1. Connect RTL-SDR v4 device.
2. In the project path, run:
   `./script/run_mvp.sh --source rtlsdr --center-freq 6850000 --sample-rate 2400000 --gain 38.6`
3. This setting shows about `5.65 MHz ~ 8.05 MHz` (`center ± sample_rate/2`), close to the SDR++ screenshot span.
4. Waterfall resolution is `8192` FFT bins for sharper narrowband lines.
5. Default producer frame rate is `60 FPS`. You can override with `--fps` (e.g. `--fps 75`).
6. If CPU usage is high, reduce FPS (e.g. `--fps 45`) while keeping `8192` bins.

### IQProducer Shared Memory Mode
Use this mode when IQ is supplied by the shared `IQProducer` bridge instead of direct RTL access.

1. Start `IQProducer` against the OpenWebRX `rtltcp_compat` port:
   `./run_ubuntu22.sh run-soapy --prefix iqproducer --host 127.0.0.1 --port 12345 --sample-rate 768000 --center-freq 14070000`
2. Start TinyWebSDR using the shared-memory source:
   `./script/run_mvp.sh --source iqproducer --iq-prefix iqproducer`
3. TinyWebSDR reads `proc_i8` IQ blocks from `iqproducer_*` shared memory and uses SHM metadata for sample rate and center frequency at startup.
4. When accessing from another device on the LAN, open the client using the server IP, for example:
   `http://192.168.219.109:8080`

What was added for this mode:

- new `iqproducer` source option in `src/core_producer.py`
- SHM consumer for `iqproducer_control` and `iqproducer_proc_i8`
- startup now adopts sample rate and center frequency from IQProducer SHM metadata
- `script/run_mvp.sh` now supports:
  - `--source iqproducer`
  - `--iq-prefix`
  - `--db-offset`
  - `--ws-host`
  - `--ws-port`
  - `--http-port`
- default websocket bind host is `0.0.0.0`, which allows browser access from another LAN device
- residual DC bias is removed before the spectrum FFT to suppress the center spike

Typical manual launch on this server:

```bash
cd /home/moai/Workspace/Codex/TinyWebSDR
./script/run_mvp.sh --source iqproducer --iq-prefix iqproducer
```

Useful overrides:

```bash
# More visible background noise / brighter waterfall
./script/run_mvp.sh --source iqproducer --iq-prefix iqproducer --db-offset 10

# Explicit LAN bind
./script/run_mvp.sh --source iqproducer --iq-prefix iqproducer --ws-host 0.0.0.0 --ws-port 8765 --http-port 8080
```

Related files:

- `src/core_producer.py`
- `src/ws_server.py`
- `client/index.html`
- `script/run_mvp.sh`

### IQProducer Operational Notes

- TinyWebSDR does not tune the radio in `iqproducer` mode.
- The active passband always follows the IQ currently being emitted by OpenWebRX through IQProducer.
- If `iqproducer_control` is missing, TinyWebSDR fails at startup because the upstream SHM publisher is not available.
- Startup order should therefore be:
  1. OpenWebRX
  2. IQProducer
  3. TinyWebSDR
- If the waterfall page is opened from another machine, use the server LAN address for HTTP access:
  - example: `http://192.168.219.109:8080`
- The browser websocket URL follows `location.hostname`, so LAN access requires the gateway to bind on a non-loopback host. `script/run_mvp.sh` now defaults to `--ws-host 0.0.0.0`.

Common checks:

```bash
# TinyWebSDR processes
ps -ef | grep -E 'TinyWebSDR/src/core_producer.py|TinyWebSDR/src/ws_server.py|http.server 8080' | grep -v grep

# IQProducer SHM health
cd /home/moai/Workspace/Codex/IQProducer
./run_ubuntu22.sh inspect --prefix iqproducer
```

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for current Linux operation notes.

### Legacy RTL Troubleshooting
If logs repeatedly show `[R82XX] PLL not locked!`:

1. Test with safer parameters first:
   `./script/run_mvp.sh --source rtlsdr --center-freq 100000000 --sample-rate 1024000 --gain 20`
2. Verify device health:
   - `rtl_test -t`
   - `rtl_test -s 2048000`
3. Ensure the device is attached to WSL:
   - `usbipd list`
   - `usbipd attach --wsl <DISTRO> --busid <BUSID>`
4. If PLL warnings persist, update WSL-side `librtlsdr`/driver stack to a version compatible with RTL-SDR Blog V4.
5. If startup fails with missing symbol `rtlsdr_set_dithering`, reinstall dependencies:
   - `pip install -r requirements.txt`
   - This project pins `pyrtlsdr` to a compatible range for Ubuntu 22.04.

### Performance Targets (MVP)
- End-to-end latency: ≤120ms (p95)
- Render rate: ≥20 FPS sustained  
- Frame drop rate: <5% over 5min
- Recovery time: ≤3s after disconnect

## Architecture

TinyWebSDR uses a 3-component pipeline optimized for real-time performance:

1. **Producer** (`src/core_producer.py`) - RTL-SDR interface, IQ processing, FFT computation
2. **Shared Memory Bus** - Latest-only data exchange with backpressure handling  
3. **Gateway** (`src/ws_server.py`) - WebSocket server for browser clients
4. **Browser Client** - 2D canvas waterfall renderer

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed technical specifications.

## Development Rules

1. **Performance First**: All changes must maintain latency/FPS targets
2. **MVP Scope**: Focus on core functionality, defer advanced features to Phase 2
3. **Measurable Progress**: Use concrete metrics for DoD validation
4. **Documentation**: Keep ADR records for architectural decisions
5. **Testing**: Verify against the active runtime path (`iqproducer` or direct RTL) rather than simulation alone

### Key Documents
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Signal Chain And Services](docs/SIGNAL_CHAIN.md)
- [WebSocket Protocol](docs/PROTOCOL.md) 
- [Technical Glossary](docs/GLOSSARY.md)
- [Development Workflow](docs/WORKFLOW.md)
- [Architectural Decisions](docs/DECISIONS/)

### Contributing
Follow the workflow defined in [docs/WORKFLOW.md](docs/WORKFLOW.md) for feature requests and progress updates.
