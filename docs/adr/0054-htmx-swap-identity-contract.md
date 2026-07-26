# ADR-0054 — HTMX swap / identity contract

**Status:** Accepted
**Date:** 2026-07-26
**Related:** [ADR-0011](0011-ssr-htmx.md) (SSR + HTMX), [ADR-0053](0053-hm-frontend-ui-ownership.md) (HM owns Hyperparts), [ADR-0049](0049-substrate-universal-render-path.md) (typed Fragment path), card-safety invariants (`docs/reference/card-safety-invariants.md`), HM decisions 0005–0008 / **0012**
**Origin:** Nested region-chrome regression (fleet smoke structure oracle; live DOM nested `data-dz-region` / `id="region-*"` on poll)

## Context

ADR-0011 chose SSR + HTMX. ADR-0053 made HaTchi-MaXchi the owner of **Hyperpart** markup (dual-lock). Card-safety (INV-1) forbids **nested card chrome** (`dz-card` / rounded+border). HM decisions 0005–0006 prefer morph for stable surfaces and stable DOM identity.

None of those layers owned the **host HTMX topology** question:

> Who may mint DOM identity for a persistent slot, and what may a fragment response re-emit when swapped into that slot?

In practice the dashboard **card body** owned `id="region-{name}-{card_id}"` with `hx-swap="innerHTML"`, while the **region GET** re-wrapped every response in chrome with bare `id="region-{name}"`. Polls nested wrappers (9-deep live). Dual-lock stayed green (queue rows were fine). Card-safety stayed green (not card chrome). Smoke flagged duplicate `region-*` ids as framework noise.

Agents were told dual-lock = HTML safety. That is **false**: dual-lock is part-local; **swap identity is host/exchange-local**.

## Thesis

### The swap / identity contract

For every hypermedia exchange that updates a **persistent slot**, the host must declare a single **identity owner** and a **response envelope**:

```
Slot (owner of id / data-dz-region hook)
  ← hx-get + hx-target + hx-swap
Fragment response (must not re-own the same identity under inner* swaps)
```

| Role | Owns | Must not |
|------|------|----------|
| **Slot** (card body, `#{region}-body`, list host) | Stable `id`, optional `data-dz-region` / `data-dz-region-name`, `hx-*` on the slot | Disappear and reappear with a new random id each poll |
| **Fragment (innerHTML / innerMorph)** | Interior content only (rows, queue body, chart) | Re-emit the slot’s `id`, or nest another `data-dz-region` chrome with the same region name |
| **Fragment (outerHTML / outerMorph)** | Full replacement of the target element | Silently change identity without a domain reason |

### Normative rules

1. **Sole identity owner.** Exactly one element owns a given stable id for a given logical slot at rest. Duplicate ids after a swap are a contract violation (not “browser quirks”).

2. **Inner swap ⇒ body-only response.** When `hx-swap` is `innerHTML`, `innerMorph`, or equivalent **into** a slot that already carries identity (`id` and/or `data-dz-region`), the HTMX response **must not** wrap content in a second chrome element that re-declares that identity (same bare `id`, or nested `data-dz-region` for the same region name). Prefer: return the typed interior only.

3. **Outer swap ⇒ replacement may carry identity.** When `hx-swap` is `outerHTML` / `outerMorph`, the response root **may** carry the target’s identity (it *is* the new element). Use outer swaps for poll-stop self-replace and whole-slot replacement, not as a default for every region refresh.

4. **No nested region hooks.** `data-dz-region` must not nest inside another `data-dz-region` that names the same region (and should not nest arbitrarily). Nesting is the smoking gun of rule 2 violations under poll.

5. **Dual-lock is orthogonal.** Dual-lock (`contracts/*.py`) validates **Hyperpart** interiors (schema + DOM for a part). It does **not** validate host slot ownership or HTMX response envelopes. Region chrome / layout furniture remains host-owned (queue contract: “region chrome are layout furniture”).

6. **Card-safety is orthogonal.** INV-1 forbids nested **card** chrome. Nested **region** hooks are this contract, not INV-1.

7. **Morph policy still applies.** ADR-0011 + HM 0005: prefer morph for stable surfaces; replacement for disposable. This ADR constrains **identity under either strategy**, not the morph-vs-replace choice itself.

### Relationship to layers

```
┌──────────────────────────────────────────────────────────┐
│ dual-lock (HM contracts) — Hyperpart fragment shape      │
├──────────────────────────────────────────────────────────┤
│ card-safety (INV-1) — no nested dz-card chrome           │
├──────────────────────────────────────────────────────────┤
│ swap / identity (this ADR) — sole slot owner + envelope  │
│   host SSR slot  ·  exchange response  ·  poll/filter    │
└──────────────────────────────────────────────────────────┘
```

## Decision

1. **Adopt the swap / identity contract** as a first-class architectural rule for Dazzle host emission and for HM exchange documentation.

2. **Dazzle host (already partially fixed):** HTMX region GETs (`HX-Request: true`) return typed body only; card body SSR owns `id="region-{name}-{card_id}"` and `data-dz-region` / `data-dz-region-name`. Unit gate: `tests/unit/test_region_chrome_id_policy.py`.

3. **HaTchi-MaXchi:** encode the contract as package decision **0012**, extend morph-safe stem + template lint / morph gates so agents cannot ship exchange partials that re-own slot identity under inner swaps. Exchange tables and agent packs document **response envelope** (body-only vs outer replace), not only swap mode.

4. **Promote detection:** smoke’s duplicate-`region-*` oracle remains defence-in-depth; ship-surface / composite tests should assert **poll×2** (or synthetic double-swap) unique ids, not only first-stitch card-safety.

5. **Agent instruction:** dual-lock green ≠ HTMX-safe. Agents must check sole identity owner + response envelope before shipping host or exchange changes.

## Consequences

### Positive

- Closes the dual-lock / card-safety blind spot that allowed nested region chrome.
- Gives agents a named checklist orthogonal to Hyperpart dual-lock expand.
- Aligns Dazzle host and HM gallery exchange language.

### Negative / cost

- More rules for host authors and agent packs to keep in sync.
- Gallery mocks that use `innerHTML` into `#hm-*-body` while returning a full chrome root must be fixed or explicitly marked outer-replace demos.

### Rejected

- **Fold into dual-lock:** dual-lock is part-local; folding host topology into every `QueueRow` contract confuses ownership and bloats part fixtures.
- **“Only Playwright / smoke will catch it”:** already failed (fleet noise, late signal). Static / unit envelope checks are required (HM 0008 posture).
- **Ban all region ids:** slots still need stable targets; the bug is **re-owning**, not identity itself.

## Implementation status

| Work | Status |
|------|--------|
| Dazzle: HTMX body-only region response + card-body data-dz-region | Shipped (2026-07-26, nested-chrome fix) |
| ADR-0054 (this record) | Accepted |
| HM decision 0012 + stem/lint/tests (`contracts/swap_identity.py`) | Shipped with this ADR |
| Composite poll×2 gate in Dazzle ship-surface | Recommended follow-up |

## See also

- `docs/reference/card-safety-invariants.md` — nested **card** chrome only
- `packages/hatchi-maxchi/docs/decisions/0005-morphing-policy.md`, `0006-dom-identity-and-state.md`, `0012-swap-identity-contract.md`
- `packages/hatchi-maxchi/stems/morph-safe-hypermedia.md`
- `src/dazzle/qa/smoke_crawl.py` — `evaluate_structure_oracles` (duplicate region ids)
- `src/dazzle/http/runtime/workspace_region_render.py` — HTMX body-only wrap policy
