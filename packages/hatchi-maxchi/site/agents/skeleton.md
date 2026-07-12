# Skeleton (`skeleton`)

Loading placeholder with a lifecycle-driven sheen (TASTE-9) — drop it into a swap target while the request is in flight.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="card card-body hm-measure hm-stack" aria-hidden="true" data-skeleton>
  <div class="hm-demo-row">
    <div class="skeleton" data-shape="circle"></div>
    <div class="hm-grow hm-stack">
      <div class="skeleton" data-shape="text"></div>
      <div class="skeleton" data-shape="text"></div>
    </div>
  </div>
  <div class="skeleton" data-shape="block"></div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/skeleton.py`

- **Required root:** `[data-dz-skeleton]` (part `skeleton`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-skeleton]` | `data-dz-skeleton` | present (any value) |

#### Ingestion model `Skeleton`

| Field | Type | Required |
|---|---|---|
| `lines` | `integer` | no |
| `body_html` | `string` | no |

#### Exemplar `render()`

```python
def render(s: Skeleton) -> str:
    """Model → skeleton-lines stack."""
    if s.body_html.strip():
        inner = s.body_html
    else:
        n = max(1, int(s.lines))
        inner = "".join('<div class="dz-skeleton" data-dz-shape="text"></div>' for _ in range(n))
    return f'<div class="dz-skeleton-lines" data-dz-skeleton>{inner}</div>'
```

## Notes

Dual-lock root is data-dz-skeleton (contracts/skeleton.py) on the placeholder stack. Purely decorative, so the region is aria-hidden; announce “loading” on the live region that owns the swap. Shapes: data-dz-shape="text|circle|block". The sheen honours prefers-reduced-motion.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/skeleton.py`
