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
  the live demo, glossary tooltips, and dogfood chrome.
- **Dogfood:** demos are HM partials; snippets use the code Hyperpart; theme
  control is toggle-group; part-page nav is breadcrumb. Gallery layout
  classes (`hm-*`) are site scaffolding on the same tokens — not a second kit.
- **DOM contract** (`contracts/<part>.py`) is CI stop-ship for required
  markup (root attrs / ingestion model). It is **package-internal**
  (`contracts._kit`) — not the FastAPI handler you write for a product.
  **Server exchange** (and optional `server_example` FastAPI snippets on
  the part page) is what a standalone HTMX4 API implements. Gallery mocks
  are not contracts.
- **Dialect:** gallery partials are unprefixed; Dazzle dual-lock is
  `dz-` / `data-dz-*`. Match the CSS/JS bundle you load.
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
