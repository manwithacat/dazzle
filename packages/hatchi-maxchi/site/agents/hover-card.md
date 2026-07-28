# Hover card (`hover-card`)

Rich preview on hover/focus — CSS-only progressive enhancement over a trigger link or button.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hover-card" data-hover-card>
  <button type="button" class="hover-card__trigger">@maya</button>
  <div class="hover-card__content" role="tooltip">
    <p class="hover-card__title">Maya Reyes</p>
    <p class="hover-card__description">Operations lead · Online now</p>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

**No host HTMX exchange** on this part — presentation or client chrome only. **Exchange envelope:** `n/a`.

If a **host** wraps this markup in `hx-*`, **that host owns the swap contract** (sole identity + envelope). Prefer `innerMorph` / `outerMorph` for stable slots; replacement for flash; body-only responses under inner swaps.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

This part has no owned exchange (envelope `n/a`). If a host adds `hx-*`, that host’s envelope applies — typically `body_only`:

```html
<!-- Prefer hx-swap=innerMorph into a stable body slot -->
<div class="dz-stack">content…</div>
```

Do **not** re-own the slot:

```html
<div id="hover-card-root" data-dz-region>…</div>
```

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/hover_card.py`

- **Required root:** `.dz-hover-card` (part `hover-card`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-hover-card` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: hover-card — rich preview on hover/focus.

Dual-lock unit is the card root. Trigger chrome and tooltip body are
host-owned. Class ``.dz-hover-card`` is the stable substrate root
(gallery CSS :hover/:focus-within; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="hover-card",
    root=".dz-hover-card",
    nodes=(Node(".dz-hover-card", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

shadcn parity (HMC-035). Opens on :hover / :focus-within; coarse pointers use focus (tab). Transparent ::before bridge covers the visual gap so the cursor can move into the panel without dropping :hover. Distinct from popover (explicit open). Dual-lock root .dz-hover-card (HMC-133). No JS controller. Canonical panel class is __content (__panel is a legacy alias).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/hover_card.py`
