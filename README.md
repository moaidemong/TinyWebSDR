# TinyWebSDR

A real-time shortwave waterfall visualization system using RTL-SDR v4, designed for low-latency browser-based spectrum display.

## Quick Start

### Prerequisites
- Windows 10 with WSL2 Ubuntu 22.04
- RTL-SDR v4 device
- Python 3.8+ with RTL-SDR API support

### Setup
1. Clone repository: `git clone <repo-url>`
2. Open WSL2 terminal and move to mounted path:
   `cd /mnt/c/Workspace/Codex/TinyWebSDR`
3. Install Python dependencies:
   `python3 -m pip install -r requirements.txt`
4. Normalize shell script line endings (once):
   `sed -i 's/\r$//' run_mvp.sh`
5. Run simulation stack:
   `chmod +x run_mvp.sh && ./run_mvp.sh --source sim`
6. Open browser client at `http://127.0.0.1:8080`

### Windows PowerShell (Optional)
- Run simulation stack: `.\run_mvp.ps1 -Source sim`

### Windows USB Pass-through to WSL2 (RTL-SDR)
Run in **Windows PowerShell (Administrator)**.

1. Install utility (`usbipd-win`) if missing:
   - `winget install --exact dorssel.usbipd-win`
   - or install latest MSI from: `https://github.com/dorssel/usbipd-win/releases`
2. Check BUSID:
   - `usbipd list`
   - Find your RTL-SDR device and copy its BUSID (example: `1-1`).
3. Re-attach to WSL2 using BUSID placeholder:
   - `usbipd detach --busid <BUSID>`
   - `usbipd attach --wsl --busid <BUSID>`
4. Example with fixed BUSID:
   - `usbipd detach --busid 1-1`
   - `usbipd attach --wsl --busid 1-1`

### RTL Device Mode
1. Connect RTL-SDR v4 device.
2. In WSL2 mounted path (`/mnt/c/Workspace/Codex/TinyWebSDR`), run:
   `./run_mvp.sh --source rtlsdr --center-freq 6800000 --sample-rate 2048000 --gain auto`

### RTL Troubleshooting (WSL2)
If logs repeatedly show `[R82XX] PLL not locked!`:

1. Test with safer parameters first:
   `./run_mvp.sh --source rtlsdr --center-freq 100000000 --sample-rate 1024000 --gain 20`
2. Verify device health:
   - `rtl_test -t`
   - `rtl_test -s 2048000`
3. Ensure the device is attached to WSL:
   - `usbipd list`
   - `usbipd attach --wsl --busid <BUSID>`
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

1. **Producer** (`core_producer.py`) - RTL-SDR interface, IQ processing, FFT computation
2. **Shared Memory Bus** - Latest-only data exchange with backpressure handling  
3. **Gateway** (`ws_server.py`) - WebSocket server for browser clients
4. **Browser Client** - 2D canvas waterfall renderer

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed technical specifications.

## Development Rules

1. **Performance First**: All changes must maintain latency/FPS targets
2. **MVP Scope**: Focus on core functionality, defer advanced features to Phase 2
3. **Measurable Progress**: Use concrete metrics for DoD validation
4. **Documentation**: Keep ADR records for architectural decisions
5. **Testing**: Verify against real RTL-SDR hardware, not simulated data

### Key Documents
- [Architecture Overview](docs/ARCHITECTURE.md)
- [WebSocket Protocol](docs/PROTOCOL.md) 
- [Technical Glossary](docs/GLOSSARY.md)
- [Development Workflow](docs/WORKFLOW.md)
- [Architectural Decisions](docs/DECISIONS/)

### Contributing
Follow the workflow defined in [docs/WORKFLOW.md](docs/WORKFLOW.md) for feature requests and progress updates.
