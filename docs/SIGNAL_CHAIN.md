# TinyWebSDR Signal Chain And Services

## End-To-End Flow

Current runtime on this server:

```text
Airspy HF+ Discovery
  -> OpenWebRX
  -> soapy_connector (rtltcp_compat on 127.0.0.1:12345)
  -> IQProducer
  -> shared memory (iqproducer_control / iqproducer_proc_i8)
  -> TinyWebSDR src/core_producer.py
  -> shared memory (tinywebsdr_latest / tinywebsdr_latest_audio)
  -> TinyWebSDR src/ws_server.py
  -> Caddy reverse proxy
  -> browser at https://tinysdr.setflux.com/
```

## Module By Module

### 1. Airspy HF+ Discovery

- Physical SDR hardware.
- It is not opened directly by TinyWebSDR.
- OpenWebRX owns the radio and remains the top-priority controller.

### 2. OpenWebRX

- Service name: `openwebrx.service`
- Role:
  - opens the Airspy HF+ Discovery
  - selects the active center frequency / passband
  - exports a local rtl_tcp-compatible IQ stream
- Live settings file:
  - `/var/lib/openwebrx/settings.json`
- Important current setting:
  - `type: "airspyhf"`
  - `rtltcp_compat: 12345`
- Manual control:
  - `sudo systemctl start openwebrx.service`
  - `sudo systemctl stop openwebrx.service`
  - `sudo systemctl restart openwebrx.service`

### 3. soapy_connector / rtltcp_compat

- Spawned by OpenWebRX internally.
- Role:
  - bridges the Airspy input into a local rtl_tcp-compatible IQ socket
- Current local endpoint:
  - `127.0.0.1:12345`
- TinyWebSDR does not connect here directly.
- IQProducer is the downstream consumer.

### 4. IQProducer

- Service name: `iqproducer.service`
- Registration state:
  - `enabled`
- Role:
  - connects to OpenWebRX `rtltcp_compat`
  - receives IQ
  - writes IQ into shared memory
- Shared memory outputs:
  - `iqproducer_control`
  - `iqproducer_raw_u8`
  - `iqproducer_proc_i8`
- Project path:
  - `/home/moai/Workspace/Codex/IQProducer`

Manual launch command:

```bash
cd /home/moai/Workspace/Codex/IQProducer
./run_ubuntu22.sh run-soapy \
  --prefix iqproducer \
  --host 127.0.0.1 \
  --port 12345 \
  --sample-rate 768000 \
  --center-freq 14070000
```

Operational notes:

- `IQProducer` is the producer for the IQ SHM bus.
- `TinyWebSDR` reads this SHM in read-only consumer mode.
- OpenWebRX remains the owner of tuning and passband selection.

### 5. TinyWebSDR `src/core_producer.py`

- Service name: `tinywebsdr-producer.service`
- Registration state:
  - `enabled`
- Role:
  - consumes `IQProducer` SHM
  - converts IQ to FFT / waterfall rows
  - writes TinyWebSDR-local waterfall SHM
- Input SHM:
  - `iqproducer_control`
  - `iqproducer_proc_i8`
- Output SHM:
  - `tinywebsdr_latest`
  - `tinywebsdr_latest_audio`
- Source file:
  - `/home/moai/Workspace/Codex/TinyWebSDR/src/core_producer.py`

Manual launch command:

```bash
cd /home/moai/Workspace/Codex/TinyWebSDR
./.venv/bin/python src/core_producer.py \
  --source iqproducer \
  --iq-prefix iqproducer \
  --fps 60 \
  --db-offset 0
```

Important note:

- Despite the service name, this module is an upstream SHM consumer and a downstream waterfall SHM producer.

### 6. TinyWebSDR `src/ws_server.py`

- Service name: `tinywebsdr-ws.service`
- Registration state:
  - `enabled`
- Role:
  - consumes `tinywebsdr_latest`
  - sends binary waterfall frames to web clients over WebSocket
- Bind address:
  - `127.0.0.1:8765`
- Source file:
  - `/home/moai/Workspace/Codex/TinyWebSDR/src/ws_server.py`

Manual launch command:

```bash
cd /home/moai/Workspace/Codex/TinyWebSDR
./.venv/bin/python src/ws_server.py --host 127.0.0.1 --port 8765
```

Important note:

- This service binds to loopback intentionally.
- External clients do not connect to `8765` directly.
- Caddy reverse-proxies `/ws` to this local service.

### 7. TinyWebSDR Static Web

- Service name: `tinywebsdr-web.service`
- Registration state:
  - `enabled`
- Role:
  - serves `client/index.html` and related static assets
- Bind address:
  - `127.0.0.1:8080`
- Manual launch command:

```bash
cd /home/moai/Workspace/Codex/TinyWebSDR/client
/home/moai/Workspace/Codex/TinyWebSDR/.venv/bin/python -m http.server 8080 --bind 127.0.0.1
```

Important note:

- This is an internal local static server.
- Public access is fronted by Caddy, not by direct `:8080` exposure.

### 8. Caddy

- Service name: `caddy.service`
- Role:
  - terminates HTTPS for `tinysdr.setflux.com`
  - reverse-proxies static web and WebSocket
- Relevant Caddyfile block:

```caddyfile
tinysdr.setflux.com {
    encode zstd gzip

    @ws path /ws
    handle @ws {
        reverse_proxy 127.0.0.1:8765
    }

    handle {
        reverse_proxy 127.0.0.1:8080
    }
}
```

Public entry point:

- `https://tinysdr.setflux.com/`

## Service Registration Summary

`systemctl list-unit-files` currently shows these units as `enabled`:

- `openwebrx.service`
- `iqproducer.service`
- `tinywebsdr-producer.service`
- `tinywebsdr-ws.service`
- `tinywebsdr-web.service`

## Startup Order

Recommended order:

1. `openwebrx.service`
2. `iqproducer.service`
3. `tinywebsdr-producer.service`
4. `tinywebsdr-ws.service`
5. `tinywebsdr-web.service`
6. `caddy.service`

Practical note:

- `caddy.service` can remain always-on.
- The real dependency chain is:
  - OpenWebRX must export IQ first
  - IQProducer must publish IQ SHM next
  - TinyWebSDR producer must build waterfall SHM after that
  - TinyWebSDR WS can then publish frames

## Common Commands

Check service enablement:

```bash
systemctl list-unit-files | rg 'openwebrx|iqproducer|tinywebsdr|caddy'
```

Check runtime status:

```bash
sudo systemctl status openwebrx.service --no-pager
sudo systemctl status iqproducer.service --no-pager
sudo systemctl status tinywebsdr-producer.service --no-pager
sudo systemctl status tinywebsdr-ws.service --no-pager
sudo systemctl status tinywebsdr-web.service --no-pager
sudo systemctl status caddy.service --no-pager
```

Tail logs:

```bash
sudo journalctl -u openwebrx.service -f
sudo journalctl -u iqproducer.service -f
sudo journalctl -u tinywebsdr-producer.service -f
sudo journalctl -u tinywebsdr-ws.service -f
sudo journalctl -u tinywebsdr-web.service -f
sudo journalctl -u caddy.service -f
```

## Current Network View

Internal-only listeners:

- `127.0.0.1:12345` for OpenWebRX `rtltcp_compat`
- `127.0.0.1:8080` for TinyWebSDR static web
- `127.0.0.1:8765` for TinyWebSDR WebSocket

Public listeners:

- `:80` and `:443` on Caddy

This separation is intentional and helps avoid exposing internal backend ports directly.
