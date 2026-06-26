# ADR-0046 — Introspection boots the app's real entrypoint

**Status:** Accepted (2026-06-26) — **shipped & complete for its (now-narrowed)
scope**: `dazzle inspect … --runtime` (renderers / primitives / routes) and
`dazzle perf trace --all-surfaces` boot the app's declared `[serve] app`
entrypoint via `cli/inspect.py::_boot_app`, with graceful fallback to
`create_app` + a note (closes #1485). **Scope narrowed 2026-06-26 (#1486 closed,
superseded):** `ux verify` is NOT in scope — its guide-walk oracle depends on
framework test seams (`runtime.json`, `/__test__/authenticate`,
`DAZZLE_TEST_SECRET`) the app's prod entrypoint doesn't expose, and its
persona-switch assumes the framework auth model; that case stays solved by the
`page_auth_context` bridge (#1401). The "boot the real entrypoint" principle
applies to in-process registry reads, not the live oracle (see D1). Supersedes
the per-subsystem
`pipeline.serve.app_init` hook approach (#1290 `register_middleware`, #1401
`page_auth_context`) as the *general* answer to the introspection-vs-production
divergence class; those hooks are not removed yet (D5). Relates to #1485
(renderers), #1401 (page auth), #1413 (custom renderer signpost), ADR-0005
(RuntimeServices on `app.state`), ADR-0040 (conformant custom routes).

## Context

The framework's introspection / verification tooling — `dazzle inspect … --runtime`,
`dazzle ux verify`, and the static signposts in `dazzle validate` — exists to tell
the operator the truth about *their running app*: which renderers are registered,
which primitives, which routes, whether onboarding guides render. To do that it boots
the app and reads `app.state.services`.

But it boots the **wrong app**. `src/dazzle/cli/inspect.py::_boot_app` calls
`dazzle.http.runtime.app_factory.create_app(appspec, database_url=None)` — the
*framework-default* app assembled from the AppSpec. That path replays the
`pipeline.serve.app_init` project hooks (`register_middleware`, `page_auth_context`),
but it is **not the app's real ASGI entrypoint** (`server:app`). Anything an app wires
in its own entrypoint *after* `create_app`/`build()` — the supported standalone-server
pattern — is invisible to the tooling.

This produces **false negatives that are structurally identical across subsystems**:

| Issue | Subsystem | Symptom |
|-------|-----------|---------|
| #1401 (closed) | page-render auth context | app wires UI auth in `server.py` → oracle boots `create_app` → `auth_ctx=None` → `ux verify --guides` reports guides "did not render" though they render in prod |
| #1485 (open) | renderer registry | app registers 5 renderers in `server.py` post-build → `inspect renderers --runtime` reports "declared in manifest but no runtime handler" though surfaces return 200 in prod |
| latent | primitives, routes, oauth-providers | every `--runtime` introspection uses the same `_boot_app` → same blind spot |

The reactive mitigation so far has been a **named project hook per subsystem** on
`pipeline.serve.app_init` that `create_app` replays: `register_middleware` (#1290),
`page_auth_context` (#1401). #1485 proposes a third, `register_renderers`. This is
**hook proliferation**: each new subsystem that an app can configure post-build needs
its own framework hook, its own invocation site, and its own app re-wiring — forever,
and asymptotically never complete. The defect is not any one missing hook; it is that
**the tooling models a different app than production**.

## Decision

### D1 — Runtime introspection boots the app's declared real entrypoint, not `create_app`.

An app may declare its ASGI entrypoint in the manifest:

```toml
# dazzle.toml
[serve]
app = "server:app"   # the module:attr the app actually runs in prod
```

When present, the **in-process introspection tools** — `inspect … --runtime` and
`perf trace --all-surfaces` — import and boot **that** app, so `app.state.services`
reflects exactly what production wires. When absent, they fall back to
`create_app(appspec)` — today's behavior. The change is therefore **opt-in and
zero-impact for apps that don't customize post-build wiring** (the common case, and all
current example apps).

**`ux verify` is explicitly out of scope** (narrowed 2026-06-26, #1486). It is *not* an
in-process registry read — it drives a **live server through framework test seams**:
`.dazzle/runtime.json` (URL + secret discovery) and `/__test__/authenticate` +
`DAZZLE_TEST_SECRET` (the persona-switch the guide walk uses), both injected by
`dazzle serve` in test mode and absent from an app's real prod entrypoint. The
test-auth seam also assumes the *framework* session model, whereas the apps this ADR
targets run their *own* auth. So "boot the real entrypoint" does not translate to the
ux-verify-class: there, the app instead **bridges its auth into the framework serve**
via the `page_auth_context` hook (#1401) — which keeps the oracle's seams intact and
already works. The general principle here ("introspect what prod runs") holds for
in-process registry reads; the live-oracle case is a different problem solved by the
bridge, not by booting the app's server. #1486 is closed as superseded by that
distinction.

### D2 — Only the already-runtime tools adopt this. `validate` stays static.

`dazzle validate` is a DSL/manifest gate whose value is that it runs **offline, in CI,
without infra**. It does not boot an app today; its #1413 renderer check is a *static
signpost* pointing at `inspect renderers --runtime`. That stays. The signpost becomes
*accurate* for free — because the runtime check it points to now reflects the real app.
Coupling the static gate to a real-app boot would regress validate's offline property
and is explicitly **rejected**.

### D3 — Boot failure degrades to `create_app` with a loud note, never a silent or fatal result.

The real entrypoint may not boot in the inspect environment (missing DB / Redis /
secrets — see Consequences). On failure the tool falls back to `create_app` and emits
a clear note — `"introspected framework-default app; declared entrypoint
'server:app' failed to boot: <error>"` — so the operator knows the report reflects the
framework default, not their app. It must not crash and must not silently present the
fallback as if it were the real app.

### D4 — Capture lifespan-time registration via the ASGI lifespan context, best-effort.

Registration that happens at *import* (synchronous, after `build()` — the PD pattern)
is captured by importing `server:app`. Registration inside a FastAPI **lifespan
startup** handler is not visible until startup runs. The tool therefore enters the
app's lifespan context before reading `app.state.services`; if lifespan startup fails
(e.g. no DB), it degrades to import-only state with a note (D3). Apps that want
reliable `--runtime` visibility should prefer import/build-time registration.

### D5 — Supersedes the per-subsystem hooks **for the inspect-class only**; existing hooks are not removed.

`register_renderers` (the #1485 proposal) is **not added** — the declared entrypoint
replaces it for in-process introspection. `register_middleware` (#1290) remains
supported. **`page_auth_context` (#1401) is explicitly NOT superseded** (corrected
2026-06-26): it is the load-bearing answer for the ux-verify-class (D1), where booting
the real entrypoint does not apply — an app bridges its auth into the framework serve
so the oracle's test seams keep working. So the supersession is scoped: the entrypoint
mechanism replaces named hooks *for what `inspect --runtime` reads* (renderers,
primitives, routes), while the auth bridge stays the mechanism *for what `ux verify`
drives*. No named hook is removed in this ADR.

## Consequences

**Closes the whole class, not one instance.** #1485 (renderers), #1401 (auth, already
patched), and the latent primitives/routes/oauth cases all resolve through one
mechanism. No new framework hook is ever needed for a new post-build subsystem.

**The fidelity cost is real and inherent (the one thing the design cannot make free):**
an app that wants accurate `--runtime` introspection must have a **bootable entrypoint
in the inspect environment**. `create_app(database_url=None)` is deliberately minimal;
a real `server.py` may assume prod env/secrets/Redis/DB at import or in lifespan. D1's
opt-in + D3's graceful fallback bound the blast radius (apps that don't declare an
entrypoint, or whose entrypoint can't boot, get today's behavior plus a clear note),
but the price of "introspect what prod runs" is that prod must be runnable where you
introspect. This is acceptable: it is the same fidelity contract `--runtime` already
implies (it already needs a reachable DB).

**Slower / less predictable boot.** A real entrypoint can warm caches, run checks, and
connect to externals where `create_app` would not. Scoped to the already-slow
`--runtime` path (D2), so no fast path regresses.

**Tooling executes more app code.** `--runtime` already imports and boots app code;
this boots the app's own entrypoint instead of the framework default. Not a new risk
class, but the surface is the app's `server.py` rather than `create_app`.

## Alternatives considered

- **Add the named `register_renderers(registry)` hook (#1485 as written).** Smallest
  change, mirrors the #1401 precedent. **Rejected as the general answer** — it continues
  the per-subsystem proliferation D5 exists to end; the next post-build subsystem needs
  yet another hook. (An app can already register renderers today inside the existing
  `register_middleware(app)` hook, which receives the built `app` with
  `app.state.services.renderer_registry` — so #1485 is partly an ergonomics ask the
  entrypoint approach obviates entirely.)
- **Unified `configure(app)` post-build hook.** Collapse the named hooks into one hook
  that does all post-build wiring, called by both `create_app` and the app's
  `server.py`. Ends the proliferation, but **still boots the framework default** — it
  only fixes subsystems the app remembers to route through `configure`, and still keeps
  two sources of truth (the framework-default app + the app's real entrypoint) that can
  drift. The declared-entrypoint approach has **one** source of truth: the app the
  operator runs.
- **Keep `validate` able to boot the app.** Rejected — see D2; regresses validate's
  offline/CI property.
