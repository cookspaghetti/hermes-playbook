# systemd Units for the Stack

The deployment runs as user-level systemd units. Three services, dependency-ordered.

## hermes-gateway.service

The main gateway — messaging platform bridge, agent sessions, cron scheduler.

```ini
[Unit]
Description=Hermes Agent Gateway - Messaging Platform Integration
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/home/YOURUSER/.hermes/bin/gateway start
Restart=always
RestartSec=10
# Startup health check: probes Ollama, embedder, Qdrant, extractor LLM.
# Silent on success; Telegram alert with specifics on failure. See scripts/.
ExecStartPost=/bin/bash /home/YOURUSER/.hermes/scripts/mem0_startup_check.sh
Environment=OLLAMA_KEEP_ALIVE=30m

[Install]
WantedBy=default.target
```

## qdrant.service

Local vector database for memory.

```ini
[Unit]
Description=Qdrant Vector Database Server
After=network.target

[Service]
ExecStart=/usr/local/bin/qdrant --config-path /home/YOURUSER/.hermes/qdrant_config.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

## Operational notes

1. **`ExecStartPost` health check** — the startup check runs *after* the gateway boots.
   Anything it flags was broken at boot; anything it misses broke later. For long-horizon
   coverage, add the same script as a cron watchdog.

2. **`OLLAMA_KEEP_ALIVE=30m`** — keeps the embedding model resident. Without it, the first
   memory write after ~5 idle minutes eats a 25-second cold-start. With it, warm latency
   is ~1.7s all day. Costs a fixed slice of VRAM/RAM.

3. **Restart=always, not on-failure** — the gateway occasionally exits 0 on its own
   (harness quirks); `on-failure` won't restart those.

4. **User units** (`systemctl --user`) — no root; survives reboots via
   `loginctl enable-linger YOURUSER`. Required for WSL2 without systemd-as-PID-1 hacks.

5. **Startup ordering is advisory** — `After=` doesn't wait for readiness, just for
   process start. That's what the ExecStartPost probe is for: it fails loudly if Qdrant
   came up too slowly, instead of letting the gateway write into a dead socket.