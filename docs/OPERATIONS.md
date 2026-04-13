# TinyWebSDR Operations

## Current Runtime Model

TinyWebSDR is currently operated in `iqproducer` mode.

Runtime split:

- `OpenWebRX` owns the radio and exports IQ through `rtltcp_compat`
- `IQProducer` connects to OpenWebRX and writes SHM
- `TinyWebSDR src/core_producer.py` reads IQ from SHM and generates waterfall frames
- `TinyWebSDR src/ws_server.py` publishes websocket frames to browsers
- `python -m http.server 8080` serves the local static client

## Manual Startup

Start `IQProducer` first:

```bash
cd /home/moai/Workspace/Codex/IQProducer
./run_ubuntu22.sh run-soapy \
  --prefix iqproducer \
  --host 127.0.0.1 \
  --port 12345 \
  --sample-rate 768000 \
  --center-freq 14070000
```

Then start TinyWebSDR:

```bash
cd /home/moai/Workspace/Codex/TinyWebSDR
./script/run_mvp.sh --source iqproducer --iq-prefix iqproducer
```

LAN client example:

```text
http://192.168.219.109:8080
```

## Startup Order

Recommended order:

1. `openwebrx.service`
2. `iqproducer.service` or manual `IQProducer run-soapy`
3. `TinyWebSDR script/run_mvp.sh`

TinyWebSDR startup fails if `iqproducer_control` is not present yet.

## Common Checks

Check TinyWebSDR processes:

```bash
ps -ef | grep -E 'TinyWebSDR/src/core_producer.py|TinyWebSDR/src/ws_server.py|http.server 8080' | grep -v grep
```

Check IQProducer SHM:

```bash
cd /home/moai/Workspace/Codex/IQProducer
./run_ubuntu22.sh inspect --prefix iqproducer
```

Check IQProducer service logs:

```bash
systemctl status iqproducer.service --no-pager
sudo journalctl -u iqproducer.service -f
```

## Notes

- TinyWebSDR does not independently tune the radio in `iqproducer` mode.
- The visible passband follows whatever OpenWebRX is currently serving.
- The browser websocket URL is now Caddy-friendly:
  - direct access from `:8080` uses `ws://host:8765`
  - reverse-proxied HTTPS access can use same-origin `/ws`
- The waterfall FFT removes residual DC bias before rendering to suppress the center spike.
