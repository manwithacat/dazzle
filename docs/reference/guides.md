# Onboarding Guides

A `guide` is a first-class DSL construct for **per-persona onboarding overlays** — the
terse, in-fiction coachmarks a real user of the app sees on first run. This page is the
agent-discoverable entry point: read it before authoring or editing a guide.

## What a guide really is

A guide is more than onboarding copy. It is a **terse, in-fiction, falsifiable statement
of intended per-persona user journeys**:

- **In-fiction.** A guide speaks *as the product* ("File a ticket here"), never as a meta
  demo ("this example shows `bar_chart`"). Example apps maintain the fiction of being real
  products for real businesses; the guide stays inside that fiction.
- **Falsifiable.** A guide is a claim about what a user can do. Static checks prove it
  *references* real DSL constructs; an e2e walk proves the journey is *actually achievable*
  at runtime. Divergence is a signal: either the guide drifted from the app, or the app
  drifted from intent.
- **Agent-authored.** The founder describes the app; the coding agent recognises each
  persona's onboarding needs and writes the guide — keeping concordance between developed
  intent and described user interactions. (See the Authoring-vs-API boundary, #1222.)

Distinct from `experience` (which owns its own route segment), a guide **decorates
already-mounted surfaces** without taking over navigation.

## DSL shape

```dsl
guide customer_onboarding "Filing your first ticket":
  audience: persona = customer

  step welcome_empty:
    kind: empty_state
    target: surface.ticket_list
    title: "Need help? File a ticket"
    body: "Describe your issue and a support agent will pick it up."
    cta_label: "New Ticket"
    cta_target: surface.ticket_create
    complete_on: event entity.Ticket.created

  step write_title:
    kind: popover
    target: surface.ticket_create
    title: "Write a clear subject"
    body: "Keep it short and specific — it's the first thing the agent sees."
    placement: bottom
    complete_on: field_filled surface.ticket_create.field.title

  step_order: [welcome_empty, write_title]

  on_complete:
    redirect: surface.ticket_list
```

| Key | Meaning |
|-----|---------|
| `audience:` | Predicate naming the personas who see the guide (`persona = customer`, `persona = agent or persona = manager`). |
| `step <name>:` | One overlay. 1+ per guide. |
| `step_order:` | The linear sequence the steps fire in. |
| `on_complete:` | `emit` an event and/or `redirect: surface.<name>` when the guide finishes. |

Per step:

| Key | Meaning |
|-----|---------|
| `kind:` | One of the 8 render kinds (below). |
| `target:` | **Must be `surface.<name>`** (optionally `.action`/`.field`/`.section`.`<id>`). Workspaces are *not* valid targets — the overlay shows when the user is on that surface. |
| `title:` / `body:` | The overlay copy (kept terse — see the quality bar). |
| `placement:` | `top` \| `bottom` \| `left` \| `right` \| `center` (floating kinds). |
| `cta_label:` / `cta_target:` | Optional call-to-action; `cta_target` is a `surface.<name>` the audience persona must have permission to reach. |
| `complete_on:` | `click` \| `dismiss` \| `event entity.<E>.created` (or an hless event) \| `field_filled surface.<s>.field.<f>`. |
| `audience_when:` | Optional extra predicate AND-ed with the guide's `audience`. |

### The 8 render kinds (`GuideStepKind`)

`popover` (floating callout) · `spotlight` (dimmed page + halo + card) · `inline_card`
(card in page flow) · `empty_state` (large replace-the-list prompt) · `banner`
(full-width sticky strip) · `checklist_item` (row with a checkbox) · `blocking_task`
(native `<dialog>` modal) · `nudge` (auto-dismiss toast).

## The per-persona quality bar

Every example app must satisfy this, enforced by `tests/unit/test_example_guide_bar.py`
on every commit:

1. **Coverage** — every **interactive** persona (a login persona that lands on a workspace)
   is either covered by a guide whose `audience` names it, deliberately `EXEMPT` (admins —
   overlays are friction for power users), or on the explicit `PENDING` worklist.
2. **Terse** — `body` ≤ 200 chars, `title` ≤ 60 chars, ≤ 6 steps per guide. Onboarding
   overlays nobody reads a paragraph in; if you need long-form content it belongs in a help
   surface or an `experience`, not a guide.
3. **In-fiction** — no meta tokens (`dazzle`, `showcase`, `demonstrat…`, "this demo",
   "example app", "sample data"). Speak as the product.
4. **Concordance-clean** — every `target`, `complete_on` ref, `field_filled` path, and
   `cta_target` (with audience permit) resolves. Enforced at `dazzle validate` time by the
   linker (`guide_concordance.py`); a drifted reference fails the build.
5. **Closes the loop** — ends with `on_complete.redirect` so a finished guide routes the
   user home.

## Two-tier validation

| Tier | What it proves | Command / gate |
|------|----------------|----------------|
| **Fast** (every commit) | Coverage + terseness + in-fiction + concordance, statically | `pytest tests/unit/test_example_guide_bar.py tests/unit/test_example_guides_concordance.py` |
| **E2E** (CI) | The overlay **actually renders** for the audience persona where they land | `dazzle ux verify --guides` |

`dazzle ux verify --guides` boots the app, authenticates as each guide's audience persona,
fetches the first step's target surface, and asserts the `<dz-onboarding-step>` overlay
renders there — the runtime proof that the persona is shown the guide the DSL promises.
Exit `0` = every walked guide's overlay rendered, `1` = a guide promised an overlay the
runtime didn't show (guide or app drifted), `2` = setup/boot failure. Add `--persona <id>`
to walk only one persona's guides.

## Authoring guidance (for the coding agent)

When you add a persona to an example app, or build a new app, give each **interactive,
non-admin** persona a guide rooted in the work that persona actually does. Use the 11
example apps as the reference corpus — `examples/*/dsl/onboarding.dsl`. Recipe:

1. **One guide per primary persona.** Name it `<persona>_onboarding` (e.g.
   `manager_onboarding`). Audience = `persona = <id>`.
2. **Root the first step on a list/create surface** the persona reaches on login — that's
   what the e2e walk asserts and what the user sees first.
3. **Match the persona's real job.** Action personas (who *create*) get an
   `event entity.<E>.created` completion and a `cta_target` to the create surface. Read-only
   personas (auditors, viewers) get `dismiss`-driven orientation steps and **no CTA to a
   create surface** (RBAC concordance rejects it).
4. **Stay terse and in-fiction** (the bar). 2–4 steps is typical.
5. **Close with `on_complete.redirect`** to the persona's home surface.
6. **Update the coverage registry** — remove the persona from `_PENDING_GUIDE_AUTHORING` in
   `test_example_guide_bar.py` (the hygiene ratchet fails if you author a guide but leave the
   worklist entry).
7. **`dazzle validate`** the app (concordance) and run the fast gate.

### Gotchas

- **Targets are surfaces, not workspaces.** A guide can't root on `workspace.X`.
- **Detail/edit targets need a record id at runtime** — the e2e walk (scope A) walks the
  *first* step only and log-skips a first step that targets a detail/edit surface.
- **Declaring guides introduces the framework `OnboardingState` entity** (per-user guide
  progress, `PERMIT_SCOPED` to each user's own rows) into the app's RBAC matrix and
  compliance evidence — analogous to `AIJob` from `llm_intent`. If the app has committed
  `expected/` references, regenerate them after adding guides.
- **Admins are exempt** by convention, but a first-run *setup* guide for an admin (e.g.
  simple_task's `workspace_setup`) is fine when it reflects a real admin job.

## Runtime & MCP

At request time, `_inject_onboarding_step` (`ui/runtime/page_routes.py`) resolves the active
step for the user's persona + progress and prepends the rendered `<dz-onboarding-step>`
fragment to the surface body; `POST /api/onboarding/{guide}/{step}/complete` (or `/dismiss`)
advances state. Server-rendered + HTMX — no SPA. Inspect guides with the `guide` MCP tool
(`list` / `get` / `concordance` / `narrate`) or `dazzle guide list` / `dazzle guide narrate <name>`.

## Source map

- IR: `src/dazzle/core/ir/onboarding.py` (`GuideSpec`, `GuideStep`, `GuideCompleteOn`)
- Parser: `src/dazzle/core/dsl_parser_impl/onboarding.py`
- Concordance (validate-time): `src/dazzle/core/guide_concordance.py`
- Render: `src/dazzle/render/onboarding/` (resolver, renderer) + `ui/runtime/static/{js/dz-onboarding.js,css/components/onboarding.css}`
- State: `src/dazzle/http/runtime/onboarding/` (Postgres `OnboardingState`)
- Quality bar gate: `tests/unit/test_example_guide_bar.py`
- E2E oracle: `dazzle ux verify --guides` (`src/dazzle/testing/ux/interactions/guide_walk.py`)
