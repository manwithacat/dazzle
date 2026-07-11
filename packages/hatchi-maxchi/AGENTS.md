# AGENTS.md — working on or consuming HaTchi-MaXchi with a coding agent

This file is the entry point for coding agents (Claude Code, Copilot,
Cursor, …). It is deliberately short; everything it references is
machine-checkable.

## What this is

An htmx4-native design system. The unit of reuse is a **Hyperpart**: a
server-rendered partial + its **exchange contracts** (the endpoint
request/response the server must satisfy) + optionally a vanilla-JS
controller and extensions. There is no client state graph — state lives
on the server and in the DOM.

## Two audiences (same Hyperpart, different entry)

| Audience | Who | What the agent should do |
|---|---|---|
| **Dazzle** | Founders / vibe coders building SaaS without deep stack knowledge | Treat Dazzle as the product surface. Emit SSR + wiring from the app model; HM supplies the design system the runtime already knows. Prefer monorepo dual-lock (`dz-` / `data-dz-*`) and Dazzle emitters over hand-rolled FastAPI. |
| **Standalone HM** | HTMX4 developers (often with agent support) who own their server | Read each part as: **this markup** (Copy this) → **this DOM contract** (what the fragment must look like) → **this API shape** (Server exchange + optional `server_example`). Wire `hx-*` to your handlers; return HTML fragments, not JSON. |

**Humans on the HTML part pages:** dotted glossary terms (Hyperpart, affordance,
Server exchange, DOM contract, …) show a short plain-language tooltip on hover
or keyboard focus. They are confidence aids — fundamental hypermedia, not a
black box. Agents should still prefer section prose, tables, and this file;
do not scrape tooltip attributes as the contract.

Example direction that should resolve from the agent pack alone:

> I'm building an HTMX4 site using HM as the design system. I need an API
> that emits the correct server-side rendered code and is wired up to my
> file. I normally use React, but I've heard good things about Hyperparts.

→ Open `agents/<part>.md` (or `hyperparts/<id>.html`): copy the partial,
implement the Server exchange handler (FastAPI-shaped when present),
satisfy the DOM contract tables, load the listed controller. Do **not**
paste `contracts/*.py` dual-lock modules into app routes.

## Consuming components (building an app with HM)

- **Source of truth for every component**: `site/registry.py`. Each
  entry carries the canonical markup (`partial`), the endpoint contracts
  (`exchanges` — method, endpoint shape, trigger, response fragment,
  swap, states, optional `server_example`), controller/extension pointers,
  and wiring notes. Parse it; don't scrape the gallery HTML.
- **Per-part agent pack**: `site/agents/<id>.md` (Pages: `agents/<id>.md`)
  is the one-fetch scrape target — **same linear skeleton on every part**
  as `hyperparts/<id>.html`: Copy this → Server exchange → How to use it →
  DOM contract → Notes (if any) → Source files. Empty states are explicit
  (“no server exchange”, “no typed dual-lock yet”) so a thin part never
  looks incomplete. Prefer the `.md` when implementing; the HTML page adds
  the live demo and glossary tooltips. Dialect / dogfood / provenance sit in
  an **About this page** footer on HTML (not above the spine). This pack still
  leads with dialect because agents scrape markdown first.
- **Dogfood:** demos are HM partials; snippets use the code Hyperpart; theme
  control is toggle-group; part-page nav is breadcrumb. Gallery layout
  classes (`hm-*`) are site scaffolding on the same tokens — not a second kit.
- **DOM contract** (`contracts/<part>.py`) is CI stop-ship for required
  markup (root attrs / ingestion model). It is **package-internal**
  (`contracts._kit`) — not the FastAPI handler you write for a product.
  **Server exchange** (and optional `server_example` FastAPI snippets on
  the part page) is what a standalone HTMX4 API implements.
- **Dialect:** gallery partials are unprefixed; Dazzle dual-lock is
  `dz-` / `data-dz-*`. Match the CSS/JS bundle you load.

### Gallery demos are not the product API (anti-pattern)

The static gallery uses a **mock htmx** (`MOCK_HTMX` in `site/build_site.py`)
so demos work offline. That mock invents scaffolding that **is not** Hyperpart
surface and **must not** be reimplemented in an app:

| Gallery-only (ignore for production) | Real contract (implement this) |
|---|---|
| `/mock/*` endpoints | **Server exchange** table + optional `server_example` |
| Flash toasts (e.g. confirm’s “Deleted (demo).”) | Exchange **response fragment** (row delete, empty-state, confirm hold, …) |
| Canned HTML strings in the mock map | Markup that satisfies **DOM contract** / `Copy this` |
| `hm-toast`, demo-only chrome | Your app’s real success/error UX (if any) |

**Agent trap:** spending turns inventing a toast API, a `/mock/…` route, or
“how do I make the gallery toast appear?” — stop. Read the **Server exchange**
section: return that HTML fragment (or the empty/OOB shape it describes). Dazzle
often emits those routes from the app model; standalone HTMX4 apps write them
explicitly. If Notes call something “gallery-only” / `MOCK_HTMX`, treat it as
documentation of the demo, not a requirement.

### Composition: who uses whom (and what is *not* composition)

Hyperparts do **not** import each other at runtime like React components. What
we have today:

| Mechanism | Meaning | Enforced by |
|---|---|---|
| **`composes`** on a Hyperpart | Declares child parts this one embeds (inline in `partial` or via exchange). Drives “Composed of” on the part page + Composite dependency chip. | `test_composes_references_real_hyperparts` |
| **`guidance.composes_with`** | Soft related-parts graph for agents (links). | Ids must exist (`test_guidance_composes_with_ids_are_real`) |
| **`extensions`** | Optional controllers on another part’s seams (e.g. grid-edit rides grid). Absence must not break the parent. | Bundled + cohesion; contracts often pair by stem (`grid_edit.py` ↔ `dz-grid-edit.js`) |
| **DOM / dual-lock contracts** | What markup a *producer* must emit. | `tests/test_contracts.py`, Dazzle `test_hm_contract_*` |
| **Prose ↔ controller attrs** | Controller must implement contract attrs. | `test_contract_prose_drift` |

**Not present yet:** a reverse **consumer** index (who depends on combobox?),
or a gate that “grid select cells must enhance as combobox.” Related-looking
UX is often a **local primitive**, not dogfooding.

**Example — grid does *not* use combobox today.** Inline
`kind=select` cells (`contracts/grid_edit.py` / `dz-grid-edit.js`) build a bare
`<select class="dz-inline-edit-select">` for density, morph survival, and
single-field PUT commits. That is intentional. To dogfood combobox inside
grid later would be an explicit composition decision (list combobox in
`composes` / `extensions` notes + dual-lock that the editor DOM satisfies
combobox’s contract when mounted) — not assumed by “select-ish UI.”

**When composing Hyperparts (recipe):**

1. Declare **`composes=(…)`** if the parent’s partial embeds the child.
2. Point agents via **`composes_with`**.
3. Prefer **child’s contract module** as the child’s interface; parent contracts
   name only parent seams.
4. If parent only *resembles* a part (native control in a dense surface),
   **document the non-composition** in seams/pitfalls so agents don’t “wire
   combobox into the grid” by accident.

- The snippets ship unprefixed by default. `build.py --prefix dz-`
  (or any prefix) renamespaces classes, data-attributes, and keyframes
  consistently — pick one and stay with it.
- What a page needs: the dist CSS + JS, the icon symbol sheet once per
  page (`sprite_sheet.svg`), htmx4, and idiomorph for
  `hx-swap="innerMorph"`. See the gallery's Setup section (`#setup`).

## Changing the system (contributing)

- **Authoring a new Hyperpart?** Follow `contracts/AUTHORING.md` — the ordered
  contract-first path (decision test → contract module → controller → registry →
  Dazzle emitter). Contract modules in `contracts/` are the typed source of truth
  for each part's ingestion shape and DOM contract.
- **This repo is a synced mirror** — the source of truth is
  `packages/hatchi-maxchi/` in the
  [Dazzle monorepo](https://github.com/manwithacat/dazzle). See
  CONTRIBUTING.md for the PR-port flow. If you are an agent working in
  the monorepo, edit there; never push here.
- Gates (run `python build.py && python -m pytest tests/`):
  - every class in markup **or assigned from controller JS** needs a CSS
    rule or a commented `SEMANTIC_ONLY` entry (`tests/test_contract.py`);
  - every request affordance (hx-\* attr or a declared raw-fetch seam)
    needs an `Exchange`, and vice versa;
  - controllers/extensions must be owned by exactly one Hyperpart and
    carry a `HYPERPART: <id>` marker (`tests/test_hyperpart_cohesion.py`);
  - behaviour tests run Chromium **and** WebKit; touch accommodations
    get a chromium `is_mobile` context (see README › Touch input);
  - visual baselines (`HM_UPDATE_BASELINES=1` to regenerate on an
    intended change), WCAG/axe, and W3C HTML validation.
- Conventions the gates can't fully see: state lives in the DOM
  (attributes, not JS objects); controllers are document-delegated
  Pointer-Events vanilla JS; hover-only affordances are forbidden;
  `dz-` in source is the namespace token (rewritten at build) — don't
  write it into custom-property names or prose that shouldn't rename.
