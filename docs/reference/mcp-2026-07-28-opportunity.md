# MCP 2026-07-28 / Python SDK — opportunities for Dazzle

**Date:** 2026-08-10
**Adopted:** `mcp>=2,<3` (SDK **2.0.0**, protocol **2026-07-28**)
**Server:** lowlevel `Server` with constructor `on_*` handlers; stdio transport
**Related:** ADR-0002 (MCP/CLI boundary), `src/dazzle/mcp/server/`

**Status:** Full SDK v2 adoption landed 2026-08-10. Remaining opportunities
(Streamable HTTP, Tasks, MRTR for select_project) are optional scale-out, not
blockers for local Claude Code / stdio hosts.

Will MCP “survive” now that hosts tool-call natively? Short answer: **as a
portable tool/resource contract across hosts, yes; as a bidirectional session
fabric, the 2026-07-28 rewrite is how it survives.** Dazzle already fought
session and blocking pain months ago; the new doctrine **aligns with us** more
than it threatens us.

---

## What changed (upstream)

Sources: [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/),
[Python SDK README / PyPI 2.0](https://pypi.org/project/mcp/),
[Cloudflare MCP v2](https://blog.cloudflare.com/mcp-v2/).

| Theme | 2025-era | 2026-07-28 |
|-------|----------|------------|
| Session | `initialize` + `Mcp-Session-Id`, sticky routing | **Stateless core**; each request self-describing |
| Interactivity | Server→client on open stream (elicitation/sampling) | **MRTR** (`input_required` + client retry with answers) |
| HTTP | Body-only routing | **`Mcp-Method` / `Mcp-Name` headers** for gateways |
| Lists | Re-fetch often | **`ttlMs` / `cacheScope`** on list results |
| Long work | Ad-hoc | **Tasks** extension (poll `tasks/get`) |
| Auth | DCR heavy | CIMD preferred; DCR deprecated |
| Python API | `mcp.server.Server` + stdio patterns | v2: `MCPServer`, snake_case fields, transport split |

Legacy HTTP+SSE and several features have a **≥12 month** deprecation window.

---

## What Dazzle already solved (local oral history)

| Dazzle investment | Why it existed | Relation to new MCP |
|-------------------|----------------|---------------------|
| ADR-0002 read vs side-effect boundary | MCP calls blocked agent thread | Still correct; long work → CLI or Tasks |
| `process_lock.py` / mcp-sessions | Multi-client stdio / shared state races | **Less necessary** for pure stateless HTTP; still useful for **app** state (project root, KG cache) |
| Consolidated tools | Huge tool lists | Cacheable `tools/list` is a free win |
| Dev mode multi-project | Hosts bind one cwd | Explicit handles (project id) match “state as tool args” doctrine |

Upstream’s line: *drop protocol session; if you need state, mint a handle and
pass it as an argument.* That is exactly “select_project → subsequent tools”
without transport sticky sessions.

---

## Opportunities if we embrace v2 / 2026-07-28

### 1. Stateless HTTP transport for hosted Dazzle MCP

Today the primary path is **stdio** (`mcp.server.stdio`). Stateless Streamable
HTTP enables:

- Multiple replicas behind a load balancer (no session affinity)
- Edge / Worker-style deployment (Cloudflare already marketing this)
- Ordinary HTTP observability on `Mcp-Method` / `Mcp-Name`

**Action:** spike `streamable_http` app alongside stdio; keep stdio for Claude
Code local. Do not delete process_lock until stdio multi-writer is gone.

### 2. Tool catalog caching

`tools/list` with `ttlMs` reduces host re-init cost. Our consolidated tool list
is large — mark list responses cacheable once on v2.

### 3. MRTR for “missing project / confirm destructive”

Replace awkward “error: select project first” loops with
`input_required`-style continuation **if** the host supports MRTR. Until then,
keep structured errors (hosts on old SDK).

### 4. Tasks for long digs (optional)

Improve / QA captures are CLI for a reason. Tasks extension is the MCP-native
form of “don’t block the conversation.” Only expose Tasks for operations we
already allow as long-running CLI, with the same auth posture.

### 5. Explicit state handles (align code with doctrine)

Audit tools that assume ambient session (cwd, last project). Prefer:

```text
project_id | root path as required arg after select
```

That migrates cleanly to stateless multi-instance.

### 6. Pin strategy

```toml
# until migration spike is green
mcp = ["mcp>=1.28.1,<2"]
```

`pip install mcp` now resolves **2.x**. Without an upper bound, a clean venv
can break imports (`Server` vs `MCPServer`, field renames). Add `<2` soon even
if we do not migrate yet.

### 7. ADR-0002 revision note (not rewrite)

Keep the boundary test. Add: *protocol sessions are gone upstream; Dazzle app
state remains explicit handles; long/side-effect work remains CLI or Tasks.*

---

## What not to do

- Do not expose generate/LLM/write as MCP tools “because MRTR exists.”
- Do not treat MCP death rumors as a reason to delete the server — hosts still
  need a **standard tool schema** for non-code-exec agents.
- Do not migrate to v2 mid-improve-campaign without a test plan
  (`tests/unit/test_mcp_*`, session, process_lock).

---

## Done (2026-08-10)

1. Pin `mcp>=2,<3` in pyproject.
2. Rewrite `src/dazzle/mcp/server/__init__.py` for `on_*` handlers + full result types.
3. snake_case field access (`input_schema`, `progress_token`, `mime_type`).
4. Cache hints on `tools/list` / `resources/list` / `prompts/list`.
5. Unit tests + `scripts/verify-mcp.py` green on v2.

## Follow-ups (optional scale-out)

1. Dual-stack: stdio + Streamable HTTP (`stateless_http=True`).
2. Host matrix notes (Claude Code / Cursor / Grok) vs protocol version.
3. Tasks for `qa capture` class work (only if product wants MCP-native long jobs).
4. MRTR for “select project / confirm” when hosts support it.

---

## Bottom line

MCP’s new doctrine is **stateless, header-routable, cacheable, MRTR for
interactivity** — the same pressures that produced ADR-0002 and our process
lock. Embracing it is mostly **delete session mythology, keep the boundary,
pin until migrated, then HTTP scale.** Direct tool-calling does not replace a
cross-host tool contract; it increases the number of hosts that will speak MCP
if the protocol stays easy to run.
