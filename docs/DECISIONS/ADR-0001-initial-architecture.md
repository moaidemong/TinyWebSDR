# ADR-0001: Initial Architecture for TinyWebSDR MVP

- **Date**: 2026-03-05
- **Status**: Proposed
- **Context**: Need to build a real-time shortwave waterfall visualization using RTL-SDR v4 with SDR++-style waterfall rendering in browser. Priority is on stability and measurable performance for MVP phase.

- **Decision**: 
  - Use Python RTL-SDR API for direct hardware control in single process
  - Implement shared memory bus with latest-only policy between producer and gateway
  - Use WebSocket binary protocol for browser transport
  - Start with 2D canvas renderer for stability, defer Three.js to Phase 2
  - Target <120ms p95 latency, >=20 FPS sustained, <5% frame drop rate

- **Consequences**:
  - **Positive**: Simple architecture with clear performance boundaries, proven technologies, fast debugging cycle
  - **Negative**: Single-process limitation, no multi-client support in MVP, 2D canvas may limit future visual effects
  - **Risks**: RTL-SDR device handling robustness, shared memory coordination between processes
