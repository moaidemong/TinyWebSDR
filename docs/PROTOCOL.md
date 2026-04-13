# TinyWebSDR WebSocket Protocol (MVP)

## Scope
- This document defines the binary frame between `src/ws_server.py` and browser client.
- Source data contract comes from `docs/ARCHITECTURE.md`.

## Transport
- Protocol: WebSocket.
- Message type: binary only for waterfall rows.
- Frequency: latest-only push; stale rows may be dropped by gateway.

## Binary Frame (little-endian)
1. `uint32 seq`
2. `float64 t_capture_monotonic_sec`
3. `uint16 bins`
4. `uint8[bins] row`

## Fixed MVP Values
- `bins = 1024`
- Total frame length: `4 + 8 + 2 + 1024 = 1038` bytes.
- dB clamp range: `[-110 dB, -20 dB]`
- Encoding:
  - `u8 = round((clamp(db, -110, -20) + 110) * 255 / 90)`
- Optional decode on client:
  - `db = (u8 * 90 / 255) - 110`

## Validation Rules (Client)
- Reject if payload length `< 14`.
- Reject if `bins == 0`.
- Reject if payload length `!= 14 + bins`.
- Reject if `bins != 1024` (MVP strict mode).
- If invalid frame ratio increases, log warning and keep rendering previous rows.

## Sequence and Timing
- `seq` increments by 1 per emitted row.
- Client may estimate frame drops from sequence gaps.
- End-to-end latency estimate:
  - `latency_ms = (client_monotonic_now - t_capture_monotonic_sec) * 1000`

## Error Handling (Gateway)
- If producer data unavailable, gateway sends nothing (no fake frames).
- On producer recovery, sequence resumes from latest producer sequence.

## Minimal Parsing Example (JavaScript)
```js
function parseFrame(arrayBuffer) {
  const view = new DataView(arrayBuffer);
  if (view.byteLength < 14) return null;

  const seq = view.getUint32(0, true);
  const tCapture = view.getFloat64(4, true);
  const bins = view.getUint16(12, true);
  if (bins !== 1024) return null;
  if (view.byteLength !== 14 + bins) return null;

  const row = new Uint8Array(arrayBuffer, 14, bins);
  return { seq, tCapture, bins, row };
}
```
