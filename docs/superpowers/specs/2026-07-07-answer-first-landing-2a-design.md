# Answer-First Landing (2a → L4) Design

**Issue:** #1558 (criterion 2a). **Date:** 2026-07-07.

**Goal:** Take UX-maturity criterion **2a (answer-first landing)** from L3 to L4 by
inferring a persona's landing surface from its rhythm when `default_workspace` is
unset, and warning when a declared `default_workspace` contradicts what the
rhythm implies.

**One-line:** Author declaration stays authoritative; inference fills the gap when
it's silent; a fidelity check flags contradiction. Cold-start byte-identical.

---

## Background — current state (L3)

The root `/` route redirects an authenticated user to their persona's dashboard.
The mechanism (site_routes.py):

- `create_site_routes(..., persona_routes: dict[str, str])` receives a map of
  **persona id → dashboard route** (e.g. `{"customer": "/app/workspaces/customer_dashboard"}`),
  built upstream from each persona's declared `default_workspace`.
- `_resolve_auth(request)` matches the caller's role to a `persona_routes` entry
  and returns that route; with no match it falls back to the generic `/app`,
  which serves the marketing landing instead of redirecting.

So today a persona with **no** `default_workspace` produces **no** `persona_routes`
entry → lands on the generic `/app`. That is the gap 2a-L4 closes: infer the
landing from the persona's rhythm.

**Why rhythms, not stories.** Only a `rhythm` carries the temporal/phase structure
(`PhaseKind.ACTIVE` = the persona's day-to-day) that answers "where should this
persona land." A `story` is an event-triggered behavioral leaf (trigger +
given/when/then) with **no landing concept**. The #1517/#1558 "rhythms/stories"
phrasing conflates the two; the honest inference source is **rhythms only**. (The
broader story/rhythm agent-cognition cleanup is tracked separately as #1559 and is
**not** a dependency of this work.)

---

## Architecture

Four pieces, mirroring the ADR-0050 resolver pattern already used for criteria
1a/2d/3a (`form_engagement_resolver`, `action_prominence_resolver`,
`column_economy_resolver`):

1. **`src/dazzle/page/runtime/landing_resolver.py`** (new) — one pure function.
2. **`persona_routes` construction seam** (upstream of `create_site_routes`) —
   consult the resolver when a persona has no declared `default_workspace`.
3. **Drift check** in `dazzle rhythm fidelity` (`cli/rhythm.py` +
   `core/fidelity_scorer.py`) — warn on declared-vs-inferred contradiction.
4. **`_probe_2a`** + the `ux_maturity.py` CRITERIA declaration: L3 → L4.

### Component 1 — the rhythm-inference helper

```python
def infer_landing_workspace(
    persona, rhythms, workspaces
) -> str | None:
    """Return the WORKSPACE NAME inferred from a persona's rhythm, or None.
    Rhythm-only; does NOT consider persona.default_workspace (the caller,
    _resolve_persona_route, owns declaration precedence)."""
```

This is **rhythm-only inference** — it does not encode the declaration
precedence (that stays in `_resolve_persona_route`, Component 2). Returning a
workspace NAME (not a route) lets the caller reuse its existing
`_workspace_root_route` helper.

**Inference rule (settled, refined during planning):**

1. *Select the active phase* — `PhaseSpec.kind` is an **optional** hint
   (`PhaseKind | None`, usually unset in real rhythms):
   - the first phase with `kind == PhaseKind.ACTIVE`, else
   - the first phase whose `kind` is **not** `ONBOARDING`/`GATE`/`OFFBOARDING`
     (with `kind` unset everywhere — the common case — this is simply the first
     phase, since phases are declared in temporal order), else
   - `None` (only one-time phases exist) → no inference.
2. *Take the first scene* of that phase → `scene.surface`.
3. *Resolve to a workspace* — **workspace-only in v1:** if `scene.surface`
   equals a `WorkspaceSpec.name` → return that name; otherwise → `None`.
   **v1 does NOT map a bare surface to an owning workspace** — that mapping is
   ambiguous (a surface can appear in zero or several workspaces) and
   lower-signal, so the honest choice is to fall through to the existing generic
   fallback. A rhythm scene that names a workspace directly (`on: ticket_queue`)
   is the unambiguous landing signal we act on.

**Edge cases (all → return `None`, never raise):** no rhythm for the persona;
rhythm with no usable active phase; active phase with no scenes; first scene
names a bare surface (not a workspace); persona with multiple rhythms → first
declared. Persona identity matched via `persona.id` (**not `.name`** — the
PersonaSpec identity gotcha; `RhythmSpec.persona` holds the persona id). Pure
function of `(persona, rhythms, workspaces)`; no I/O.

### Component 2 — wiring into `_resolve_persona_route`

The route map is built by `compute_persona_default_routes(personas, workspaces)`
→ `_resolve_persona_route(persona, workspaces)` in
`src/dazzle/page/converters/workspace_converter.py`. Its precedence today:

1. `persona.default_route` (explicit) →
2. `persona.default_workspace` → `_workspace_root_route(ws)` →
3. first workspace with `access.allow_personas` including the persona →
4. first workspace with `AUTHENTICATED` access →
5. first workspace (fallback).

**Insert a new step 2.5**, between the declared `default_workspace` (step 2) and
the generic workspace fallbacks (steps 3–5):

```python
# 2.5 (#1558): infer the answer-first landing from the persona's rhythm
inferred = infer_landing_workspace(persona, rhythms, workspaces)
if inferred:
    for ws in workspaces:
        if ws.name == inferred:
            return _workspace_root_route(ws)
```

Both `compute_persona_default_routes` and `_resolve_persona_route` gain a
`rhythms: list[ir.RhythmSpec]` parameter, threaded from the two call sites in
`src/dazzle/http/runtime/app_factory.py` (lines ~855 and ~1256) as
`appspec.rhythms`.

Because inference sits **after** the declared `default_workspace` and only fires
when that is unset, every app with a declared landing — or no rhythms — produces
a **byte-identical** route map. A persona with no declaration, no usable rhythm
signal, and no explicit-access workspace still falls through to steps 3–5 exactly
as today.

### Component 3 — the drift check (`dazzle rhythm fidelity`)

For each persona that has **both** a declared `default_workspace` **and** a
rhythm: compute `infer_landing_workspace(persona, rhythms, workspaces)` (which
ignores the declaration); if it returns a workspace and
`declared_workspace != inferred_workspace`, emit a **warning**:

> persona `P` declares `default_workspace=X`, but its rhythm's active landing
> points at `Y` — the landing may not be answer-first for this persona.

**Severity: warning, not error.** An author may deliberately override the rhythm
(e.g. land an admin on a control panel even though their day-to-day rhythm centers
elsewhere). The check is a coherence hint, never a gate. Silent when the persona
lacks either a `default_workspace` or a rhythm, and silent when they agree.

### Component 4 — the maturity probe (the L4 gate)

Update `_probe_2a` and the CRITERIA tuple (`"2a"`, level `3` → `4`) in
`src/dazzle/qa/ux_maturity.py`. The probe exercises three paths, each with an
**explain-trace** (the ADR-0050 traceability invariant — every inferred choice
carries a human-readable reason):

- **(a) infer-when-unset:** a persona with no `default_workspace` + a rhythm →
  the resolver returns the ACTIVE-phase landing;
- **(b) declared-authoritative:** a persona with `default_workspace` set → the
  resolver returns it and never consults the rhythm;
- **(c) drift:** a persona whose declared landing contradicts its rhythm → the
  fidelity check reports it.

The `ux_maturity` index rises accordingly (2a joins the 11 already at L4 → 12/13).

---

## Data flow

```
Root GET / (authed)
  -> _resolve_auth -> persona_routes[role]           (declared OR inferred entry)
  -> RedirectResponse(landing route)                  or /app generic (unchanged)

_resolve_persona_route (build time), new step 2.5:
  for persona without default_route/default_workspace:
    infer_landing_workspace(persona, rhythms, workspaces)
      -> active phase.first scene.surface (if it names a workspace) -> route

dazzle rhythm fidelity (author-invoked)
  for persona with default_workspace AND rhythm:
    default_workspace != infer_landing_workspace(...) -> warning
```

## Fixture / probe coverage — resolved: no fixture needed

`support_tickets` is the only example that declares rhythms, and its personas also
declare `default_workspace`, so no existing example exercises the *infer-when-unset*
path at runtime. But the established probe pattern (`_probe_2d`, `_probe_3a`) builds
**synthetic in-memory IR** and calls the resolver directly — no app boot, no DB, no
fixture app. `_probe_2a` and the integration test follow suit: construct
`PersonaSpec` + `RhythmSpec` + `WorkspaceSpec` objects in memory and call
`infer_landing_workspace` / `compute_persona_default_routes`. This avoids churning
`support_tickets` (whose declared landings we do not want to disturb) and keeps the
tests fast and hermetic. **No new fixture is added.**

## Error handling

The resolver never raises — every unresolvable branch returns `None` and the
caller falls back to today's behaviour. The fidelity check is advisory and cannot
fail a build. No new runtime failure modes; no new exceptions.

## Testing

- **Unit — `landing_resolver`:** declared wins; infer-when-unset; none-when-no-rhythm;
  ACTIVE-phase selection (skips onboarding/gate/periodic); surface→workspace
  resolution (workspace-named vs surface-in-workspace vs dangling); multiple-rhythm
  first-declared; `.id` identity.
- **Unit — drift check:** warns on mismatch; silent on match; silent when either
  input absent.
- **Probe:** `_probe_2a` green at L4 with explain-traces; `ux_maturity` index ticks
  to 12/13.
- **Integration:** root `/` redirect serves the *inferred* landing for a persona
  with no declared `default_workspace` (site_routes seam), and is byte-identical
  for a persona with a declaration or no rhythm.

## Scope guardrails (YAGNI)

- **Rhythm-only** — no story path (stories carry no landing concept; #1559 tracks
  the broader cleanup and is not a dependency).
- **No grammar change, no new DSL keyword.** `default_workspace` stays the author's
  knob; this fills the gap when it's silent and warns when it's contradicted.
- **Purely additive, cold-start byte-identical** — an app with declared
  `default_workspace` on every persona, or no rhythms, behaves exactly as today.
- **Model-Driven Failure Modes note:** this adds an *inference* (MDF risk: hidden
  magic the author can't trace). Mitigations: (1) declaration always wins and is
  never overridden; (2) every inference carries an explain-trace; (3) the drift
  check makes any divergence between declaration and inference visible to the
  author. A competent engineer can trace any landing back to either an explicit
  `default_workspace` or a named rhythm scene.

---

## Post-review extension (2026-07-08)

An adversarial review of the workspace-only v1 found two gaps that undermined the
L4 claim, both fixed before ship (per the "complete it now" decision):

1. **Surface landings.** The v1 "workspace-only" narrowing meant a rhythm scene
   naming a bare *surface* (the common authoring shape — open on a list, drill
   inward) inferred nothing, so the only fleet rhythm (support_tickets) never
   fired. The resolver is now `infer_landing_route(persona, rhythms, workspaces,
   surfaces) -> str | None`, returning a **route**: a workspace root route, or a
   **list-mode** surface's route via `app_paths.list_path("/app",
   app_paths.entity_slug(surface.entity_ref))` — the same SSOT the list route
   registers with, so it can never be a dead link. Non-list surfaces (VIEW/
   CREATE/EDIT/CUSTOM) and entity-less surfaces still return `None`.

2. **Both redirect paths.** Inference is now consulted in `_resolve_persona_route`
   (step 2.5, site landing) *and* `resolve_persona_workspace_route` (step 1.5,
   the in-app `/app` root redirect, page_routes.py). `compute_persona_default_routes`
   and `resolve_persona_workspace_route` gained a `surfaces` param; all callers
   and the existing workspace-route test suite were updated.

Known advisory-only limitation: `check_landing_drift` can warn when a persona's
declared `default_workspace` and its rhythm's list-surface landing express the
same intent by different routes (e.g. a `ticket_queue` workspace vs a
`ticket_list` surface). It's a `dazzle rhythm fidelity` advisory, never a gate.
