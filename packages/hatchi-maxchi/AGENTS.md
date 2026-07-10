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

## Consuming components (building an app with HM)

- **Source of truth for every component**: `site/registry.py`. Each
  entry carries the canonical markup (`partial`), the endpoint contracts
  (`exchanges` — method, endpoint shape, trigger, response fragment,
  swap, states), controller/extension pointers, and wiring notes. Parse
  it; don't scrape the gallery HTML.
- The [gallery](https://manwithacat.github.io/hatchi-maxchi/) renders
  the same strings live. Each component's **Agent Implementation
  Guidance** disclosure is written for you: it names the seams, the
  attribute contracts, and the mistakes the design already rejected.
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
