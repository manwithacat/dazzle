# Stem: Hyperpart is not a component

## Claim

Reusable UI is a **Hyperpart**: server-rendered partial + exchange contract(s) +
optional controller. No client state graph; no props/events tree.

## Reconstruct

- Implement via `agents/<id>.md`: Copy → exchange → DOM contract.
- Controllers: vanilla, DOM state, document-delegated.
- Dual-lock modules are package-internal, not app route handlers.

## Not this

- React / RSC composition priors.
- Gallery mock as product API.

## Expressions

- `docs/decisions/0001-hyperpart-not-component.md`
- `AGENTS.md`, `README.md`
- Framework: `stems/hypermedia-ssr.md`
