# Stem: Morph-safe hypermedia (htmx4)

## Claim

HM is **htmx4-native**: the server owns rendering; **morphing** is the preferred
update for *stable* application surfaces; **replacement** stays correct for
disposable fragments. The **DOM is the state and configuration surface** —
stable identity, ARIA, and `data-*` affordances — not a client component graph
and not Alpine scopes in core. Controllers are small, **document-delegated**,
and reconstructable from markup.

## Reconstruct

- Prefer `innerMorph` / `outerMorph` (or equivalent) for shells, tables, forms,
  menus, and other persistent regions where focus or row identity should survive.
- Prefer plain swap/replacement for flash messages, one-shots, full resets,
  security-sensitive clears, and third-party widgets that cannot reconcile.
- Give morph participants **stable IDs** (domain keys, not loop indexes or
  random tokens). Avoid wrapper churn and reordering without identity.
- Put UI state in URL, form controls, `data-*`, ARIA, and server classes — not
  `x-data` or a parallel JSON blob that duplicates the rendered DOM.
- Write JS that discovers behaviour via attributes (`data-hm-*` / dual-lock
  `data-dz-*`), reads/writes the DOM narrowly, and survives morphs.
- Mark third-party / preserve boundaries explicitly (island attrs); never bury
  them inside morphed trees without a contract.
- Agent checklist before a template change: second source of truth? survive
  morph? morph vs replace? stable IDs? delegated behaviour? legible from HTML?
- CI enforces the checklist via `tools/template_lint.py` (pytest + CLI):
  Alpine ban, ids, morph roots, ARIA id refs, brittle `hx-target`, swap policy,
  JSON-vs-DOM duplication, third-party island boundaries, and composition
  fixtures (`grid`, `command`) for cross-fragment id/target resolution.
  Agents: `python packages/hatchi-maxchi/tools/template_lint.py`.

## Not this

- “htmx + Alpine” as the default HM stack.
- Morphing every swap “because htmx4 has morph.”
- Client reactive scopes for tables, filters, sort, selection, menus.
- Index-based or random IDs in frequently morphed regions.
- JSON config that re-lists columns/actions already rendered in markup.
- Inferring behaviour from incidental ancestry (`closest div`) when a stable
  target id exists.

## Expressions

- `docs/decisions/0005-morphing-policy.md`
- `docs/decisions/0006-dom-identity-and-state.md`
- `docs/decisions/0007-no-alpine-in-core.md`
- `docs/decisions/0008-template-lint-posture.md`
- `AGENTS.md` › Stems; framework `stems/hypermedia-ssr.md`
- Controllers under `controllers/`; dual-lock + grid morph notes in spikes
