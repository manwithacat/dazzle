# Example eval hub

Local multi-host harness for evaluating Dazzle examples.

| URL | Purpose |
|-----|---------|
| `http://dazzle.local:9080/` | Fleet directory |
| `http://simple_task.dazzle.local:9080/` | simple_task app |
| `http://contact_manager.dazzle.local:9080/` | contact_manager app |

Design: [`docs/superpowers/specs/2026-07-21-example-eval-hub-design.md`](../../docs/superpowers/specs/2026-07-21-example-eval-hub-design.md)

## Quick start

```bash
# from monorepo root
.venv/bin/python scripts/example_hub/server.py
# or showcase fleet only:
.venv/bin/python scripts/example_hub/server.py --showcase-only
```

Open **http://127.0.0.1:9080/** immediately (no DNS).
With DNS configured, open **http://dazzle.local:9080/** and click an app host.

First request to `{app}.dazzle.local` **starts** `dazzle serve` on a stable backend port (9100+). Logs/PIDs: `.dazzle/eval-hub/`.

```bash
# start every backend up front
.venv/bin/python scripts/example_hub/server.py --start-all --showcase-only
```

## DNS: `*.dazzle.local` → 127.0.0.1

Browsers do not resolve `*.dazzle.local` by default.

### Option A — dnsmasq (recommended, evergreen)

```bash
brew install dnsmasq
# $(brew --prefix)/etc/dnsmasq.conf  (or dnsmasq.d/dazzle.conf):
address=/.dazzle.local/127.0.0.1
# sudo brew services start dnsmasq

sudo mkdir -p /etc/resolver
echo "nameserver 127.0.0.1" | sudo tee /etc/resolver/dazzle.local
# dscacheutil -flushcache; sudo killall -HUP mDNSResponder
```

### Option B — /etc/hosts (simple, not wildcard)

```bash
.venv/bin/python scripts/example_hub/print_hosts.py
# paste lines into /etc/hosts (hub + each app)
```

### Option C — no DNS

Hub works on `http://127.0.0.1:9080/`. For a single app via proxy:

```bash
curl -sI -H "Host: simple_task.dazzle.local" http://127.0.0.1:9080/
```

## Agent API

```bash
curl -s http://127.0.0.1:9080/_hub/api/apps | jq .
curl -s -X POST http://127.0.0.1:9080/_hub/start/simple_task
curl -s -X POST http://127.0.0.1:9080/_hub/stop/simple_task
```

Walks / trials against a hub-hosted app:

```text
base_url = http://simple_task.dazzle.local:9080
```

## Requirements

- Each example needs a working `DATABASE_URL` in its `.env` (or env) for full app boot — same as `dazzle serve`.
- Port **9080** free for hub; **9100+** free for backends.
- Monorepo `.venv` with `dazzle`, `uvicorn`, `httpx`, `starlette`.

## Later

- Probe badges on the catalogue (story_walk / trial_verdict)
- Persona / seed controls
- `dazzle eval-hub` CLI + MCP tools
