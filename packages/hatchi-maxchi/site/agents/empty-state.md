# Empty state (`empty-state`)

Icon + one sentence + primary action — never a bare 'No X'.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="card card-body hm-measure">
  <div class="empty-state" data-empty-state>
    <span class="empty-state__icon"><svg class="icon" aria-hidden="true"><use href="#i-inbox"/></svg></span>
    <h3 class="empty-state__title">No invoices yet</h3>
    <p class="empty-state__description">Create your first invoice to get started.</p>
    <div class="empty-state__action"><a class="button" data-variant="primary" href="#">New Invoice</a></div>
  </div>
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

### `contracts/empty_state.py`

- **Required root:** `[data-dz-empty-state]` (part `empty-state`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-empty-state]` | `data-dz-empty-state` | present (any value) |

#### Ingestion model `EmptyState`

| Field | Type | Required |
|---|---|---|
| `title` | `string` | no |
| `description` | `string` | no |
| `icon_html` | `string` | no |
| `action_html` | `string` | no |

#### Exemplar `render()`

```python
def render(e: EmptyState) -> str:
    """Model → empty-state region."""
    title = html.escape(e.title)
    desc = html.escape(e.description)
    return (
        f'<div class="dz-empty-state" data-dz-empty-state>'
        f"{e.icon_html}"
        f'<h3 class="dz-empty-state__title">{title}</h3>'
        f'<p class="dz-empty-state__description">{desc}</p>'
        f'<div class="dz-empty-state__action">{e.action_html}</div>'
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-empty-state (contracts/empty_state.py). Icon + action markup are host-owned.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/empty_state.py`
