---
name: searxng-scrapling-setup
description: Use when setting up free SearXNG + Scrapling web backends.
---

# SearXNG + Scrapling/Trafilatura Free Web Backend Setup

## Architecture
- **Search**: SearXNG (Docker, port 8080) — aggregates 70+ search engines
- **Extract**: Scrapling (fetch HTML, anti-bot bypass) + Trafilatura (extract → markdown)
- Replaces Firecrawl cloud API with zero API costs

## SearXNG Setup

```bash
docker run -d --name searxng -p 8080:8080 searxng/searxng:latest

# Enable JSON API (blocked by default). Use sh not bash (Alpine image)
docker exec searxng sh -c 'cat > /etc/searxng/settings.yml << "EOF"
server:
  bind_address: 0.0.0.0
  port: 8080
  formats: [html, json]
search:
  formats: [html, json]
EOF'

# Add to ~/.hermes/.env: SEARXNG_URL=http://localhost:8080
# Config: hermes config set web.search_backend searxng
```

SearXNG is a **bundled** Hermes plugin — auto-loads, no `plugins.enabled` entry needed.

## Scrapling + Trafilatura Plugin

### Install
```bash
python3.13 -m pip install --user --break-system-packages trafilatura
```

### Plugin at `~/.hermes/plugins/web/scrapling/`
- `plugin.yaml` — manifest with `kind: backend`
- `__init__.py` — register() function, relative import from `.provider`
- `provider.py` — ScraplingWebExtractProvider implementing WebSearchProvider ABC

### Key details
- Auto-mode: tries basic `Fetcher` first, falls back to `StealthyFetcher` on 403/503
- StealthyFetcher timeout is in **milliseconds** — use `timeout=30000` for 30s
- Trafilatura: `trafilatura.extract(html, output_format="markdown", include_links=True)`
- User plugins need `plugins.enabled` entry + session restart to load
- `plugins.enabled` must be a YAML list, not a string

### Enable
```yaml
plugins:
  enabled:
    - web-scrapling
web:
  extract_backend: scrapling
```

## Benchmark (vs Firecrawl)
- Search: SearXNG 6.6x faster (0.3s vs 2.0s), same top results
- Extract: 1.9x faster (0.79s vs 1.49s), cleaner content (boilerplate stripped)
- Trafilatura over-strips docs sites; excels on articles

## Fetcher modes
- `Fetcher` — basic HTTP, fast, no JS/anti-bot
- `StealthyFetcher` — Camoufox/Playwright, Cloudflare bypass (2-3s)
- `DynamicFetcher` — Playwright JS rendering, for SPAs
- Set via `SCRAPLING_FETCHER=auto|basic|stealthy|dynamic`

## Pitfalls
- StealthyFetcher timeout is **milliseconds** not seconds
- SearXNG container uses Alpine — use `sh` not `bash`
- Docker breaks after WSL restart — `docker start searxng`
- `hermes config set` saves complex values as strings — edit config.yaml directly for lists