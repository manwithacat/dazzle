# 0012 — Swap / identity contract (htmx exchanges)

**Status:** Accepted
**Date:** 2026-07-26
**Stem:** `stems/morph-safe-hypermedia.md`
**Framework ADR:** monorepo `docs/adr/0054-htmx-swap-identity-contract.md`
**Builds on:** decisions 0005 (morph), 0006 (identity), 0008 (lint)

## Context

Dual-lock and morph lint already guard **part** markup and **morph roots**. They
did not stop hosts (and agent-authored exchanges) from **re-wrapping** a
persistent slot on every HTMX poll: the slot owned `id="region-x-card-0"` while
each response re-emitted chrome with `id="region-x"`, nesting wrappers and
duplicating ids. Dual-lock stayed green; card-safety stayed green; smoke
structure failed fleet-wide.

Agents need a **named** contract orthogonal to dual-lock: who owns identity, and
what the exchange response may re-emit under which swap mode.

## Decision

Adopt the framework **swap / identity contract** (ADR-0054) as HM package law.

### Vocabulary (agent-facing)

| Term | Meaning |
|------|---------|
| **Swap contract** | The full agent-visible package for a Hyperpart: whether it owns HTMX exchanges, each exchange’s swap mode, and its **exchange envelope**. Every part’s `agents/<id>.md` has a `## Swap contract` section. |
| **Exchange envelope** | What the **response** may re-emit relative to the persistent slot: `body_only` \| `outer` \| `none` \| `host_owned` \| `document`. |

### Rules

1. **Sole identity owner** — one stable id / region hook per logical slot.
2. **Inner swap ⇒ body_only** — `innerHTML` / `innerMorph` into a slot must not
   re-declare that slot’s id or nest another `data-dz-region` chrome for the
   same region name. Return the interior fragment only.
3. **Outer swap ⇒ outer** — `outerHTML` / `outerMorph` may replace the target
   element wholesale.
4. **Dual-lock is orthogonal** — part contracts validate interiors; this
   contract validates host/exchange envelopes.
5. **Every Hyperpart has a swap contract** — presentation-only parts declare
   envelope `n/a` explicitly (no silent omission). Every declared `Exchange`
   resolves to a known envelope (CI fails on `unspecified`).

### Machine gates (HM)

| Check | Where |
|-------|--------|
| Nested `data-dz-region` / duplicate ids in fixtures | `contracts/swap_identity.py` + `tools/template_lint.py` |
| Inner-swap response re-owns target id | `validate_inner_swap_response` |
| Every Hyperpart has `## Swap contract`; no unspecified envelope | `test_every_hyperpart_has_agent_visible_swap_contract` |
| Registry / composition lint | `tests/test_morph_template_gates.py` |

CLI: `python packages/hatchi-maxchi/tools/template_lint.py` (existing entry;
swap-identity codes appear as `swap-identity` / `nested-region`).

## Consequences

- Gallery mocks that return a full chrome root into `#hm-*-body` with
  `innerHTML` must switch to body-only content or document `outerHTML` and use
  it deliberately.
- Pagination / grid exchanges that already say “innerMorph of `#{region}-body`”
  must return **rows/body only**, not a second body root with the same id.
- Agent packs: Morph / swap section gains **Identity / envelope** bullets
  (see stem update).

## See also

- ADR-0054 (normative monorepo record)
- decisions 0005, 0006, 0008
- `stems/morph-safe-hypermedia.md`
- Dazzle host: `workspace_region_render.render_region_html` (HTMX body-only)
