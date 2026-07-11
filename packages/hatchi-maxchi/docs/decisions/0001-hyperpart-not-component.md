# 0001 — Hyperpart is not a component

**Status:** Accepted
**Date:** 2026-07-11

## Context

Agents and humans trained on React (and Server Components) reconstruct any
reusable UI unit as a **component**: props down, events up, client or server
trees, nested composition by import. That reconstruction produces wrong HM
code: parallel client state, prop-shaped `data-*` forests, JSON view models,
and “components” without exchange contracts.

## Decision

The unit of reuse is a **Hyperpart**:

> partial (server-rendered markup) + exchange contract(s) + optional controller/extensions.

- State lives on the **server** and in the **DOM**, not in a client state graph.
- Interactivity that needs a round-trip is an **affordance** (`hx-*` or a
  documented raw-fetch seam) with a declared **Exchange**.
- Controllers are vanilla JS, document-delegated, only where the platform lacks
  a primitive.
- Naming is deliberate: “component” imports priors we reject.

## Consequences

- Agent packs teach Copy this → Server exchange → DOM contract, not props/API.
- Gallery mocks are not the product API.
- New parts are judged by partial + exchange + contract, not by “reusability”
  alone.
- Dual-lock modules (`contracts/`) are package-internal; app routes implement
  exchanges, they do not paste dual-lock kits into FastAPI as product handlers.

## See also

- `AGENTS.md` › Stems
- `README.md` › Hyperpart definition
