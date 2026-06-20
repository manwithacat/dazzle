# In-process data-access core: eliminate the page→REST HTTP self-fetch (#1422 option b)

**Status:** Design — awaiting review
**Issue:** #1422 (RFC), motivated by #1421
**Date:** 2026-06-20
**Decision record:** Approach A (extract `gated_*` functions); co-located-only topology (drop `DAZZLE_BACKEND_URL`)

---

## 1. Problem statement

A single FastAPI process serves both the HTML page layer (`/app/<slug>/{id}`) and the
JSON REST API (`/<plural>/{id}`). To render a page, the page handler **makes an HTTP
request to its own process's REST endpoint**: it opens a TCP socket to `127.0.0.1:$PORT`,
sends an HTTP request that travels back through the entire ASGI stack (middleware,
routing, auth, tenant resolution), reaches the REST handler, which queries the DB,
serializes JSON, and ships it back over the socket to be deserialized and rendered.

One logical operation — *"render entity X"* — is **two full trips through the server
stack in the same process.**

This violates four core principles of HTTP-server architecture:

1. **HTTP is a boundary-crossing protocol; there is no boundary here.** Using HTTP to
   invoke code in your own process pays every cost of the boundary (serialization,
   socket, a second middleware/routing/auth pass) to cross a boundary that does not
   exist. The DB connection, the auth context, and the data are all already in memory.
2. **It discards context, then pays to reconstruct it.** The page handler has already
   authenticated the user and resolved the tenant (both in `request.state`). The
   self-fetch throws that away, serializes the session cookie, and forces the REST stack
   to re-authenticate and re-resolve the tenant from forwarded HTTP headers.
3. **Rendering depends on deployment topology.** The self-fetch needs a URL to reach
   itself, so `_resolve_backend_url` carries a 4-way fallback (`DAZZLE_BACKEND_URL` →
   `$PORT` loopback → `base_url` → hardcoded). How a page renders now depends on what
   port the process bound to — a layering inversion.
4. **It is a tax with no upside.** Per render: JSON-encode → socket write → ASGI re-entry
   → middleware → re-auth → re-tenant → DB → JSON-encode → socket read → JSON-decode →
   render, plus an `asyncio.to_thread` worker hop (the client is blocking `urllib`). The
   principled cost is DB → render.

**#1421 is the proof of the diagnosis.** On Heroku/Railway single-dyno deploys,
`_resolve_backend_url` returns a loopback URL and the self-fetch forwarded only `Cookie`,
never `Host` → the internal request reached `TenantResolutionMiddleware` with
`Host: 127.0.0.1`, was rejected 400 "Bad Host", and the detail handler surfaced that as a
404 (the list handler swallowed it into an empty 200). The fix — conditionally forward
`Host` on loopback only — patches the seams of a boundary invented for no reason. *You
cannot lose context you never serialized.*

### 1.1 Generalizable principle

The underlying principle is **efficiency at boundary operations**: pay the cost of a
boundary (serialization, transport, re-authentication) only where a real boundary exists.
The loopback self-call is one instance; §9 records a post-implementation audit to find
others.

## 2. Current mechanism (as-is)

Self-fetch call sites (all in one process):

| Surface | Handler | File:line | Fetch |
|---------|---------|-----------|-------|
| Detail | `_handle_detail` | `page_routes.py:1275` | `GET /<entity>/{id}` + N related-tab fetches |
| List | `_handle_table` | `page_routes.py:1449` | `GET /<entity>?page&filter&search` |
| Edit form | `_handle_edit_form` | `page_routes.py:1402` | `GET /<entity>/{id}` |
| Experience POST | `_experience_step_post` | `experience_routes.py:483` | `POST /<plural>` (mutation) |

Machinery: `_resolve_backend_url` (`page_routes.py:157`), `_resolve_host_to_forward`
(`page_routes.py:190`), `_sync_fetch`/`_fetch_url`/`_fetch_json` (`page_routes.py:100-236`),
`_sync_post`/`_proxy_to_backend` (`experience_routes.py:35-77`).

Workspace charts/metrics already bypass HTTP and call the repository in-process
(`workspace_aggregation.py`, `workspace_scope.py::_apply_workspace_scope_filters`) — the
**production precedent** this design generalizes.

### 2.1 Where enforcement lives today (the central fact)

- **Scope (tenant isolation)** is compiled into `Repository.list()/.aggregate()` SQL via a
  `__scope_predicate` filter key (`repository.py:1150`, `query_builder.py:389-404`). Any
  in-process caller passing the same filters gets it **identically, for free**.
- **Permit (RBAC/Cedar)** is enforced **in the route-handler closures** —
  `_list_handler_body` (`list_handlers.py:302-332`), `_read_cedar` (`read_handlers.py:166-196`),
  `_build_cedar_handler` for writes (`audit_wrap.py:339-382`). An in-process caller that
  calls `service.list()` directly **bypasses the permit gate**. This is the defect: a
  security-critical check living in a transport adapter.

## 3. Deployment-topology decision: co-located only

`DAZZLE_BACKEND_URL` (the split-service override) is **undocumented** and **vestigial for
the page path**:

- Serve modes are: default (page + API **co-located** in one app), `--backend-only` (API,
  *no pages*), `--ui-only` (**static** preview files, *no dynamic page routes*).
- The dynamic page handlers that self-fetch are **only ever mounted co-located** with the
  REST API. There is **no supported topology** that runs the dynamic page routes against a
  *remote* API. `--ui-only`'s "separate frontend" is static files calling the API
  client-side, not server-side self-fetches.
- The only *real* `_resolve_backend_url` resolutions are loopback (`$PORT`, the #1421 case)
  and same-origin (`base_url`) — both co-located.

**Decision:** treat co-located as the only real topology. In-process replaces the self-fetch
entirely; `DAZZLE_BACKEND_URL` and the loopback/Host-forward machinery are removed (clean
break, consistent with ADR-0003). `--backend-only` is unaffected (it has no page routes).

## 4. Architecture: transport-agnostic core + thin adapters

Separate transport from logic. Business logic in the center; transport adapters (REST, HTML
pages, and future GraphQL/CLI) around the edge, all calling **inward** to one core, never
**sideways** over the network.

- **Core:** a flat set of `gated_*` functions (Approach A) — one per operation, each
  applying *all* enforcement (scope + permit) + relation hydration, returning typed data or
  raising a typed error. No `Request`, no HTTP.
- **REST adapter:** parse HTTP → call core → serialize JSON.
- **Page adapter:** parse path → call core → render HTML.

### 4.1 The `gated_*` core

New module `src/dazzle/http/runtime/access/gated.py`:

```python
async def gated_read(service, access: AccessContext, entity_id: str,
                     *, include: list[str] | None = None) -> dict[str, Any]: ...
async def gated_list(service, access: AccessContext, params: ListParams) -> PageResult: ...
async def gated_aggregate(service, access: AccessContext, spec: AggSpec) -> Buckets: ...
# writes (phase 4):
async def gated_create(service, access: AccessContext, data) -> dict[str, Any]: ...
async def gated_update(service, access: AccessContext, entity_id: str, data) -> dict[str, Any]: ...
async def gated_delete(service, access: AccessContext, entity_id: str) -> None: ...
```

`AccessContext` bundles exactly what enforcement needs (each already computed per request
today): `auth_context`, `user_id`, effective roles (`effective_roles_of`), the entity's
`cedar_access_spec`, `entity_name`, and `fk_graph`/`ref_targets`. A single
`access_context_from(request, entity_spec) -> AccessContext` builder constructs it.

Each `gated_*` function: resolve scope predicate (`_resolve_scope_filters`) → evaluate permit
(`evaluate_permission`) → fetch via `service`/`repository` with scope filters merged →
hydrate relations. On permit denial raise `AccessForbidden`; on missing/scope-denied row
raise `RecordNotFound`.

**Read-path precision (avoid the bare-`read` trap):** `Repository.read(id)` applies **no**
scope — it returns any row by id. So `gated_read` must use the scoped-pre-read mechanism the
REST detail route already uses (`read_handlers.py::_scoped_pre_read` — a scoped
`list(filters={"id": id, **scope_predicate}, page_size=1)`), *not* a bare `repository.read`.
Scope-denied → no row → `RecordNotFound`. This is exactly the logic being relocated, so the
extraction inherits it; the trap is only if an implementer "simplifies" to `repository.read`.

### 4.2 The permit relocation — a move, not a rewrite

`_read_cedar` today already does *scope → `evaluate_permission` → return* — it **is**
`gated_read`, wrapped in a FastAPI closure that also parses the request and serializes the
response. The extraction cleaves the closure: the *enforcement+data* half becomes
`gated_read`; the *HTTP shaping* half stays in the route. The **same** `evaluate_permission`
and `_resolve_scope_filters` calls move, byte-for-byte, into the core. `_list_handler_body`
and `_build_cedar_handler` split identically. No enforcement logic is rewritten, so there is
nothing to drift.

### 4.3 Adapters become symmetric and thin

```python
# REST read route (after):
rec = await gated_read(svc, access_context_from(req, e), entity_id)
return JSONResponse(rec)

# Page detail handler (after) — replaces `_fetch_json(...)`:
rec = await gated_read(svc, access_context_from(req, e), prc.path_id, include=[...])
# existing RBAC-aware rendering (FK display names, when_expr, edit/delete button
# suppression) runs on `rec` UNCHANGED — same record dict + auth_ctx it consumes today.
```

## 5. Error handling — one taxonomy, two presentations

`gated_*` raises `AccessForbidden` / `RecordNotFound`. The REST adapter maps them to
`403`/`404` JSON; the page adapter maps them to its existing forbid-detail render / 404
page. Current page behavior (forbid-detail on denied, empty-state on list) is preserved — it
keys off a typed exception instead of an HTTP status decoded from a loopback response.

## 6. Migration order (each step independently shippable, parity-gated)

1. Extract `gated_read`; REST read route delegates to it (route behavior unchanged).
2. Page detail + edit handlers call `gated_read` instead of `_fetch_json`.
3. Extract `gated_list`; REST list delegates; page `_handle_table` + related-tabs call it.
4. **(writes)** Extract `gated_create/update/delete`; experience-POST calls them instead of
   `_proxy_to_backend`.
5. **Delete** `_resolve_backend_url`, `_resolve_host_to_forward`, `_sync_fetch`/`_fetch_url`/
   `_fetch_json`, `_sync_post`/`_proxy_to_backend`, `DAZZLE_BACKEND_URL`, and
   `tests/unit/test_page_route_internal_fetch_host_1421.py`. The #1421 class is now
   structurally impossible.

## 7. Test strategy — the scope+permit parity gate

Before any self-fetch site is removed, a test asserts, over the existing RBAC/scope fixtures
(`fixtures/rbac_validation`, `fixtures/scope_runtime`): for each `(user, tenant, role)`,
`gated_read/list(...)` returns the same data as a real HTTP GET of the REST endpoint, **and**
a permit-denied user gets `AccessForbidden` from `gated_*` exactly as they get `403` from
REST. This proves enforcement parity *before* the HTTP path is deleted — a relocation
mistake fails the gate, not production. The PG-backed scope fixtures
(`tests/integration/test_scope_runtime_pg.py`) are the strongest oracle for tenant isolation.

## 8. Scope & phasing

**One spec covers the full elimination** (reads + writes + deletion). The implementation
plan phases it reads → writes → delete (§6), each phase independently shippable behind the
parity gate (§7).

## 9. Post-implementation follow-on: boundary-efficiency audit

Once `gated_*` is proven on the page path, audit the codebase for other places that pay a
boundary cost without a boundary: internal HTTP/serialization self-calls, redundant
re-auth/re-tenant passes, in-process serialize→deserialize round-trips. File findings as
issues using this design's "core + thin adapters" shape as the remediation template.
(Recorded per review observation, 2026-06-20.)

## 10. Tradeoffs (honest)

- **The real work is the permit relocation**, not the call-site swaps. Done wrong it is an
  RBAC regression — mitigated by the parity gate (§7) landing *before* each self-fetch
  removal.
- **The mutation path** (experience POST → create/update) has its own permit gate +
  state-machine validation; same relocation applied to writes, sequenced last.
- **"The page exercises the public API contract" is lost** — but it was never a real
  guarantee (the page is a privileged in-process caller, not a third-party client). Contract
  tests cover the API directly.
- **`page_routes.py` is large (~3000 lines)** and the closures are entangled with FastAPI
  specifics; the extraction must cleanly cleave enforcement from HTTP shaping. This is
  surgery, but mechanical surgery on already-grouped code.

## 11. Non-goals

- No change to the scope predicate algebra, Cedar policy model, or the repository SQL layer.
- No change to client-side behavior or rendered HTML output (parity, not redesign).
- `--backend-only` / `--ui-only` serve modes are untouched.
