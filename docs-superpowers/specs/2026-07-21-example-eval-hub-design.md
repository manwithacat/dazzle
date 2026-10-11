# Example eval hub — local multi-host harness

**Status:** Starting implementation (v0 hub + Host routing)
**Date:** 2026-07-21
**Audience:** humans + agents evaluating Dazzle example apps as products

---

## 1. Vision

A **persistent local evaluation harness** for the example fleet — not one-off
`cd examples/foo && dazzle serve` sessions that evaporate when the shell dies.

### Starting point (this slice)

| Surface | URL shape |
|---------|-----------|
| **Fleet directory** | `http://dazzle.local:<hub_port>/` |
| **Per-app product** | `http://{app}.dazzle.local:<hub_port>/` |

Examples:

- `http://dazzle.local:9080/` — catalogue of available examples
- `http://simple_task.dazzle.local:9080/` — simple_task app
- `http://contact_manager.dazzle.local:9080/` — contact_manager app

Same hub port for all hosts; **Host header** selects the app. Agents and humans
click links (or open Host-based URLs) instead of remembering ports.

### Evergreen goals (later slices)

1. **Persistent process supervision** — apps stay up across sessions (PID files,
   optional launchd/systemd user units).
2. **Seed + persona switcher** on the hub card (test-mode auth deep links).
3. **Health / residual badges** from `improve_example_probes` / story_walk /
   trial_verdict (reuse machine sensors without redefining quality).
4. **LLM tool surface** — MCP/CLI: `list_examples`, `open_app`, `seed_app`,
   `run_walk` against `{app}.dazzle.local`.
5. Optional TLS via Caddy once DNS is solid.

---

## 2. Why not only “spin via tool calls”?

Tool-spawned serves work for one-shot digs but:

- Ports drift; agents lose the mapping
- No shared directory of “what can I evaluate?”
- No stable URLs for bookmarks, screenshots, or multi-tab persona compare
- Process lifecycle is session-scoped

The hub makes the fleet **addressable and sticky** under one local brand:
`dazzle.local`.

---

## 3. Architecture (v0)

```text
Browser / agent
    │  Host: simple_task.dazzle.local:9080
    ▼
┌─────────────────────────────────────────┐
│  Eval hub (Starlette)  127.0.0.1:9080   │
│  • Host = dazzle.local → catalogue HTML │
│  • Host = {app}.dazzle.local → proxy    │
│  • On-demand: start dazzle serve        │
└───────────────┬─────────────────────────┘
                │ reverse proxy
                ▼
     127.0.0.1:91xx  dazzle serve (per app)
```

### Components

| Module | Role |
|--------|------|
| **Registry** | Discover `examples/*/dazzle.toml`; optional showcase filter |
| **Port map** | Stable `base_port + index` (default base 9100) |
| **Supervisor** | Spawn/stop `dazzle serve --port N --host 127.0.0.1` per app; PID + log under `.dazzle/eval-hub/` |
| **Hub app** | Directory page + reverse proxy by Host |
| **DNS helper** | Document / script for `*.dazzle.local` → `127.0.0.1` |

### Host rules

| Host | Behaviour |
|------|-----------|
| `dazzle.local`, `www.dazzle.local`, `hub.dazzle.local`, empty/`localhost` | Hub catalogue |
| `{app}.dazzle.local` where `app` is a registered example | Proxy to that app’s backend |
| Unknown subdomain | 404 hub page listing known apps |

Strip port from Host; lowercase match.

---

## 4. DNS (operator setup)

Browsers do **not** resolve `*.dazzle.local` by default (unlike `*.localhost`).

**Recommended (macOS, evergreen):** dnsmasq

```bash
# address=/.dazzle.local/127.0.0.1
# resolver: /etc/resolver/dazzle.local → nameserver 127.0.0.1
```

**Minimal (no dnsmasq):** generate `/etc/hosts` lines for hub + each app
(scripted; less evergreen when apps are added).

**Dev fallback without DNS:** hub still works at `http://127.0.0.1:9080/` with
path links that set Host via documented curl examples; browser multi-host needs DNS.

---

## 5. Catalogue content (v0)

For each example card:

- Display name (from `dazzle.toml` / directory name)
- Link: `http://{app}.dazzle.local:{hub_port}/`
- Backend port + running/stopped badge
- Optional: path to `SPECIFICATION.md`, story count, trial.toml yes/no
- Actions: Start / Stop / Open

Not v0: full bake-off scores, live screenshots (link to local stills later).

---

## 6. Process model

### On-demand start (default)

First request to `{app}.dazzle.local`:

1. Resolve app dir + port
2. If not running, spawn:

   ```bash
   dazzle serve --host 127.0.0.1 --port {port} --test-mode
   ```

   cwd = example root; env inherits + project `.env` via serve’s own load

3. Wait for `/health` (or TCP accept) with timeout
4. Reverse-proxy the request

### Explicit start-all

```bash
python scripts/example_hub/server.py --start-all
```

### State

```text
.dazzle/eval-hub/
  ports.json          # optional override map
  {app}.pid
  {app}.log
  hub.pid
```

Gitignored under existing `.dazzle/` conventions.

---

## 7. Reverse proxy notes

- Forward `Host` as the **backend expects** (usually `127.0.0.1:port` or original Host — Dazzle apps mostly bind path routing; host-based tenancy examples need original Host preserved).
- **v0:** preserve original `Host` header so future `tenant_host:` demos still work when DNS points at hub.
- WebSocket / SSE: upgrade support later if needed.
- Streaming responses: use httpx stream proxy.

---

## 8. CLI entry (v0)

```bash
# from monorepo root
.venv/bin/python scripts/example_hub/server.py
# → http://dazzle.local:9080/  (after DNS)

.venv/bin/python scripts/example_hub/server.py --port 9080 --base-backend-port 9100
.venv/bin/python scripts/example_hub/server.py --showcase-only
.venv/bin/python scripts/example_hub/dns_check.py
```

Future: `dazzle eval-hub` once stable (API surface + docs).

---

## 9. Relationship to improve / walks / trials

| Tool | Role with hub |
|------|----------------|
| story walks | `base_url=http://{app}.dazzle.local:9080` |
| qa trial | same base_url |
| improve digs | serve via hub instead of random ports |
| demo quality | open stills + live desk in one browser |

Hub does **not** replace residual sensors; it makes actuators addressable.

---

## 10. Non-goals (v0)

- Production multi-tenant SaaS hosting
- Automatic Postgres provision for every app (reuse project `.env` / existing DBs)
- Full CI job for hub (unit-test registry + Host parse only)
- HTTPS

---

## 11. Implementation slices

| Slice | Deliverable |
|-------|-------------|
| **S0 (this)** | Design + hub server + Host proxy + on-demand spawn + DNS docs |
| **S1** | Stable port file, start-all/stop-all, status JSON for agents |
| **S2** | Catalogue badges from probes (story_walk / trial) |
| **S3** | Persona deep-link / seed buttons (test-mode) |
| **S4** | `dazzle eval-hub` CLI + MCP tools |

---

## 12. Acceptance (S0)

1. With DNS configured, hub loads at `http://dazzle.local:9080/` listing examples.
2. Click/link to `http://simple_task.dazzle.local:9080/` reaches a running simple_task (auto-start).
3. Unknown host returns a helpful 404 with known app list.
4. Without DNS, hub works on `http://127.0.0.1:9080/` and documents Host header usage.
5. Unit tests for Host parse + registry discovery (no full serve in unit CI).

---

## 13. Decision record

| Decision | Choice |
|----------|--------|
| Brand domain | `dazzle.local` (user vision) |
| Single hub port | yes — Host differentiates apps |
| Reverse proxy | pure Python (Starlette + httpx) for zero extra binary in v0 |
| DNS | operator dnsmasq / hosts helper, not baked into Python process |
| On-demand spawn | yes for low RAM; optional start-all |
