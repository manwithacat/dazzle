# Design — Guides as Falsifiable Intent Specs for Every Example App

**Date:** 2026-06-13
**Status:** Approved (brainstorm) — pending implementation plans per phase
**Author:** in-session agent (with James)

---

## 1. Problem & reframe

Dazzle has a first-class `guide` construct (onboarding overlays — 8 render kinds,
concordance-checked at `dazzle validate` time; see `src/dazzle/core/ir/onboarding.py`).
Today only **5 of 14** example apps ship guides, and there is no harness gate that
*requires* a guide or proves one actually works at runtime.

The ambition is larger than "add onboarding copy." A `guide` is a **terse,
in-fiction, falsifiable statement of intended per-persona user journeys**:

- **In-fiction ("kayfabe")** — example apps maintain the fiction of being real
  products for real businesses. A guide speaks *as the product* ("File a ticket
  here"), never as a meta demo ("this example shows `bar_chart`").
- **Falsifiable** — the guide is a claim about what a user can do. Static checks
  prove it *references* real DSL constructs; an e2e walk proves the journey is
  *actually achievable* at runtime. Divergence is a signal an agent can act on:
  either the guide drifted from the app, or the app drifted from intent.
- **Agent-authored, not founder-authored** — the founder describes the app to a
  coding agent; the agent recognises each persona's onboarding needs and crafts
  the guide. The agent is best placed to keep concordance between developed intent
  and described user interactions. (Aligns with the Authoring-vs-API boundary,
  #1222: structural authoring stays in-session.)

This makes the guide a natural-language intent layer that is machine-checkable
against the runtime — squarely in Dazzle's "trace runtime behaviour back to
DSL/AppSpec" philosophy (model-driven failure-mode rule #4).

### Goals
1. Every **example** app carries per-persona guides that explain intent in-fiction.
2. Guides are validated in **both** the fast suite (`pytest -m "not e2e"`) and the
   **e2e** suite — high quality and reliability, enforced not documented.
3. The `guide` concept is surfaced in docs with clarity, written so a coding agent
   can reliably reproduce the bar for any downstream app.

### Non-goals (parked)
- **Externalised guide content** (prose in separate copy files, `body_ref:`
  indirection — "Option B"). We will need it eventually for long-form content, but
  onboarding overlays are terse by best practice; inline + a terseness cap is the
  right model now. Revisit only on concrete need.
- Long-form explanatory/help content. That is a *different artifact* (a help
  surface or an `experience` that owns a route), not an overlay.

---

## 2. Taxonomy: examples are kayfabe businesses (Strand 0 / Phase 0)

**Rule:** an *example* is a kayfabe business demonstrating Dazzle as a working app
factory, and therefore carries per-persona guides. Anything that is a *framework
artifact* (a conformance corpus, a component gallery, a renderer-extension demo)
is a *fixture* — useful and test-consumed, but not a product story. This matches
the split `CLAUDE.md` already draws (examples = "Working Dazzle apps"; fixtures =
"not user-facing… used only by `tests/`").

### Reclassification
Move `examples/ → fixtures/`:

| App | → | Why |
|-----|---|-----|
| `pra` | fixture | Conformance corpus; already excluded from `/ux-converge`. Not a product. |
| `component_showcase` | fixture | Admin gallery of every component; only honest intent is meta. |
| `custom_renderer` | fixture | Demonstrates a renderer *extension*, not a business. |

`llm_ticket_classifier` **stays an example** (interesting developing use-case);
it needs a guide and a DSL-uplift pass to be a meaningful demonstration.

**Result:** 11 examples (all kayfabe, all must carry guides):
`simple_task`, `contact_manager`, `support_tickets`, `ops_dashboard`,
`fieldtest_hub`, `project_tracker`, `design_studio`, `llm_ticket_classifier`,
`acme_billing`, `hr_records`, `invoice_ops`.

### Blast radius (measured 2026-06-13)
Live references that must be updated (frozen history — CHANGELOG, `docs/history/`,
`docs/plans/`, past specs, agent-upgrade guides — is **not** rewritten):
- **`custom_renderer`** — sharpest edge: hardcoded in **framework source**
  (`src/dazzle/core/manifest.py`, `linker.py`, `renderer_registry.py`,
  `back/runtime/services.py`, `back/runtime/renderers/init.py`,
  `render/dispatch.py`) + 3 unit tests + `docs/reference/htmx-templates.md`.
- **`pra`** — `tests/unit/test_dazzle_validate_drift.py`, `.github/workflows/ci.yml`,
  `src/dazzle/core/validation/flows.py`, `src/dazzle/mcp/examples.py`,
  `scripts/bench_interp.py`, `examples/pra/README.md`.
- **`component_showcase`** — lightest: mostly docs + `.claude/commands/fuzz.md`.

Also update: `test_docs_drift.py` (both example + fixture lists), `CLAUDE.md`
(Examples/fixtures lines — both drift-gated), each moved app's `dazzle.toml` if it
encodes its own path, the `/improve` + `/ux-converge` lane app-lists.

**Acceptance:** `git status` clean; full non-e2e suite green; `dazzle validate`
green for every moved app at its new path; CI matrices reference new paths;
`test_docs_drift` passes against the new trees. Ships as one coherent commit
before any guide work.

---

## 3. The guide quality bar (Strand 1 / Phase 1)

The convention every example guide must satisfy, **per primary persona** —
defined as a *login persona that lands on a workspace/surface* (admins are
deliberately exempt; overlays are friction for power users — see the existing
support_tickets comment):

1. **Coverage** — ≥1 guide whose `audience` targets that persona, whose **first
   step is rooted on the persona's landing surface** (the surface they hit on
   login).
2. **Terse** — every `body` ≤ a hard cap (proposed **240 chars / ~40 words**),
   `title` non-empty, guide ≤ ~5 steps. (Exact caps finalised in the Phase 1 plan
   by measuring the existing 5 guides so the bar matches proven-good copy.)
3. **In-fiction** — speaks as the product. (Enforced by a lint heuristic flagging
   meta phrases — "this demo", "this example", "Dazzle", "showcase" — in body/title.)
4. **Concordance-clean** — targets/events/fields/CTA-permits resolve
   (`guide_concordance.py`; already exists).
5. **Closes the loop** — ends with `on_complete.redirect` to the persona's home.

The bar is encoded as machine-checkable predicates (Strand 3 fast tier), not just
prose — so "explains intent" is enforced structurally, since kayfabe forbids a
uniform sentinel name.

---

## 4. Author guides to the bar (Strand 2 / Phase 2)

- **Audit/uplift (5):** `simple_task`, `contact_manager`, `support_tickets`,
  `ops_dashboard`, `fieldtest_hub` — confirm each meets the bar; tighten copy/roots
  as needed. These are the reference corpus and should be exemplary.
- **New (6):** `project_tracker`, `design_studio`, `llm_ticket_classifier` (+ DSL
  uplift first), `acme_billing`, `hr_records`, `invoice_ops`.

All agent-authored in-session, one guide per primary persona, in each app's
established story/persona/entity vocabulary. Each app ships green against the
Phase 1 fast gate before moving on.

---

## 5. Two-tier validation (Strand 3 / Phase 3)

### Fast tier — `pytest -m "not e2e"`
A drift/coverage test (sibling to `test_docs_drift.py`) that, for every example:
- asserts the per-persona coverage rule (every primary persona has a conforming
  guide rooted on its landing surface);
- runs concordance and asserts zero errors;
- runs the terseness/in-fiction quality lint and asserts zero violations.

Cheap, deterministic, every commit. This is the gate that makes "every example has
a high-quality guide" a structural invariant rather than an aspiration.

### E2E tier — guide-walk-as-oracle
Extend `dazzle ux verify --interactions` (the existing INTERACTION_WALK CI job):
load each guide, authenticate as its `audience` persona, and **walk the declared
journey** — for each step in `step_order`, assert:
- the `target` surface/element actually **renders** for that persona at runtime;
- a `cta_target`, if present, **navigates** to a real, permitted surface;
- the `complete_on` trigger is **reachable** (the field exists and is editable /
  the action that emits the event is present).

A failed walk is a real bug surfaced to the agent: the guide promises an
interaction the app can't deliver (or vice-versa). Wire into the CI walk matrix so
it runs per example per audience persona. This is the largest net-new engineering
and the core of the "reliability" guarantee; static concordance proves *reference*,
the walk proves *achievability*.

---

## 6. Docs (Strand 4 / Phase 4)

- A dedicated **`guide` reference page** (`docs/reference/guides.md`): what a guide
  is (the intent-spec reframe), the 8 render kinds, the per-persona quality bar,
  the two-tier validation contract, and **authoring guidance written for the coding
  agent**, using the 11 examples as the imitation corpus.
- Cross-links from `docs/reference/grammar.md` and `CLAUDE.md`.
- A KB concept / counter-prior hook so `bootstrap` and lint surface the
  "every persona needs a guide" expectation during app authoring.

Can overlap Phase 2.

---

## 7. Decomposition & sequencing

One design doc (this, the north star) → five independently-shippable phases, each
with its own implementation plan:

| Phase | Strand | Ships | Depends on |
|-------|--------|-------|-----------|
| **0** | Reclassify | examples=11, fixtures gain 3; all gates green at new paths | — |
| **1** | Quality bar + fast static gate | gate built & green against the existing 5 guides | 0 |
| **2** | Author all 11 to the bar (+ llm_ticket_classifier DSL uplift) | every example green on the fast gate | 1 |
| **3** | E2E guide-walk oracle | walk runs per example/persona in CI | 1 (content from 2) |
| **4** | Docs + agent authoring guidance | reference page + KB hook | can overlap 2 |

Each phase: bump + ship per Dazzle ship discipline; pre-ship runs the full
non-e2e suite (Phase 0 and the gates touch broad surfaces).

---

## 8. Risks & failure-mode notes (per `CLAUDE.md` review rule)

- **Which failure mode does this risk increasing?** *Round-trip / semantic gap* —
  a guide that lies about the app erodes trust in the spec. **Mitigation:** the
  e2e walk makes lies fail CI; the guide can't silently drift.
- **Detector liveness:** the fast gate runs every commit; the walk runs in the
  existing CI INTERACTION_WALK job — both *live*, not merely documented.
- **Traceability:** a guide step maps 1:1 to a surface/field/event in the
  AppSpec — a competent engineer (or agent) traces overlay → DSL directly.
- **Semantics preserved:** no new runtime authority; guides decorate existing
  surfaces (no route ownership, unlike `experience`). RBAC/workflow semantics are
  honoured because the walk authenticates as the real persona and respects
  permits/scopes.
- **Parking Option B** is an explicit risk note: if long-form content demand
  appears, revisit the externalised-copy layer rather than letting `body` grow
  past the cap.

---

## 9. Open items for the per-phase plans
- Finalise the terseness caps (Phase 1) by measuring the existing 5 guides.
- Define "primary persona / landing surface" precisely against the persona+workspace
  IR (Phase 1) — likely "login persona with a workspace whose access admits it."
- Decide whether the e2e walk reuses the guide resolver (`render/onboarding/
  resolver.py`) to pick the active step, or walks `step_order` directly (Phase 3).
- `llm_ticket_classifier` DSL-uplift scope (Phase 2) — enough structure (entities,
  surfaces, a workspace, a clear persona journey) to host a meaningful guide.
