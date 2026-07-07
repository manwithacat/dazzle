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

### Component 1 — the resolver

```python
def resolve_answer_first_landing(persona, appspec) -> str | None:
    """Return the workspace name a persona should land on, or None to keep
    the current generic fallback. Precedence:
      1. persona.default_workspace (authoritative — today's behaviour)
      2. inferred: the persona's rhythm -> first ACTIVE-phase scene ->
         scene.surface, resolved to its owning workspace
      3. None (no declaration, no usable rhythm signal)
    """
```

**Inference rule (step 2), settled:** the persona's rhythm
(`RhythmSpec.persona == persona.id`) → the first phase whose `kind == ACTIVE` →
that phase's **first scene** → `scene.surface`. Resolve `scene.surface` to a
workspace name:

- if it names a workspace directly → use it;
- if it names a surface inside a workspace → return the owning workspace;
- if it resolves to neither (dangling / not in any workspace) → `None` (fall
  through, no guess).

**Edge cases (all → fall through to the next precedence step, never raise):**
rhythm present but no ACTIVE phase; ACTIVE phase with no scenes; persona with
multiple rhythms (take the first declared); persona identity via
`spec_display_id(persona)` — **`.id`, not `.name`** (the PersonaSpec identity
gotcha). Pure function of `(persona, appspec)`; no I/O.

### Component 2 — wiring at `persona_routes` construction

Where `persona_routes` is assembled from `default_workspace` (upstream of
`create_site_routes`): for a persona with **no** `default_workspace`, call
`resolve_answer_first_landing`; if it returns a workspace, add a `persona_routes`
entry pointing at that workspace's route (same route-shape the declared path
produces). If it returns `None`, add nothing — the persona keeps the generic
`/app` fallback, and the root redirect is **byte-identical** to today.

Declared `default_workspace` is untouched (precedence step 1 returns before
inference), so every existing app's redirect behaviour is unchanged.

### Component 3 — the drift check (`dazzle rhythm fidelity`)

For each persona that has **both** a declared `default_workspace` **and** a
rhythm: compute the inferred landing (step 2 above, ignoring the declaration);
if `declared_workspace != inferred_workspace`, emit a **warning**:

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

persona_routes construction (build time)
  for persona without default_workspace:
    resolve_answer_first_landing(persona, appspec)
      -> rhythm.first ACTIVE phase.first scene.surface -> workspace -> route

dazzle rhythm fidelity (author-invoked)
  for persona with default_workspace AND rhythm:
    declared != inferred -> warning
```

## Fixture / probe coverage

`support_tickets` is the only example that declares rhythms, and its personas also
declare `default_workspace`, so no existing example exercises the *infer-when-unset*
path. The plan will either (a) add a small validation **fixture** carrying a
persona with a rhythm and no `default_workspace`, or (b) drop `default_workspace`
from one suitable support_tickets persona if that persona's rhythm already implies
the same landing (no behaviour change, but exercises inference). Decision deferred
to the plan; the fixture route is the safer default (no example churn).

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
