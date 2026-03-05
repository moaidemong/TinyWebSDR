# Glossary

- **IQ**: In-phase and Quadrature components of a complex signal sample from RTL-SDR. Each IQ sample represents the real and imaginary parts of the received RF signal at a specific time point.

- **FFT row**: A single frequency-domain representation computed from a window of IQ samples using Fast Fourier Transform. Contains power spectrum data for 1024 frequency bins, converted to dB scale.

- **Waterfall frame**: A binary message sent from gateway to browser containing one FFT row with metadata (sequence number, timestamp, bin count). Represents one horizontal line in the waterfall display.

- **Producer**: The `core_producer.py` component that interfaces directly with RTL-SDR hardware, reads IQ samples, performs signal processing (windowing, FFT, dB conversion), and writes results to shared memory.

- **Gateway**: The `ws_server.py` component that reads processed data from shared memory and forwards it to browser clients via WebSocket. Acts as the bridge between the producer and web frontend.

- **Latest-only**: A backpressure handling policy where only the most recent data is kept. Older/stale data is discarded to prevent buffer buildup and maintain real-time performance.

- **Backpressure**: The condition when data is being produced faster than it can be consumed. In TinyWebSDR, handled by dropping stale frames to maintain real-time streaming without accumulating delays.
