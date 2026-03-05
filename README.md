# TinyWebSDR

A real-time shortwave waterfall visualization system using RTL-SDR v4, designed for low-latency browser-based spectrum display.

## Quick Start

### Prerequisites
- Windows 10 with WSL2 Ubuntu 22.04
- RTL-SDR v4 device
- Python 3.8+ with RTL-SDR API support

### Setup
1. Clone repository: `git clone <repo-url>`
2. Install Python dependencies: `pip install -r requirements.txt`
3. Start stack (simulation mode): `.\run_mvp.ps1 -Source sim`
4. Open browser client at `http://127.0.0.1:8080`

### RTL Device Mode
1. Connect RTL-SDR v4 device
2. Start producer: `python core_producer.py --source rtlsdr --center-freq 6800000 --sample-rate 2048000 --gain auto`
3. Start gateway: `python ws_server.py`
4. Serve client: `cd client && python -m http.server 8080`

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
