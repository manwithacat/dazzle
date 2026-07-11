# Status list (`status-list`)

System / check states as an icon + title + caption list — tone rides data-dz-state per row, never colour alone.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="status-list-region hm-measure-lg">
  <ul class="status-list" data-entry-count="3">
    <li class="status-list-entry" data-status-entry data-state="positive">
      <span class="status-list-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>
      <div class="status-list-text">
        <div class="status-list-title">Payments API</div>
        <div class="status-list-caption">Operational · 99.99% this month</div>
      </div>
      <span class="status-list-pill">positive</span>
    </li>
    <li class="status-list-entry" data-status-entry data-state="warning">
      <span class="status-list-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>
      <div class="status-list-text">
        <div class="status-list-title">Webhooks</div>
        <div class="status-list-caption">Elevated retries since 09:20</div>
      </div>
      <span class="status-list-pill">warning</span>
    </li>
    <li class="status-list-entry" data-status-entry data-state="neutral">
      <span class="status-list-icon-spacer" aria-hidden="true"></span>
      <div class="status-list-text">
        <div class="status-list-title">Nightly export</div>
        <div class="status-list-caption">Scheduled 02:00</div>
      </div>
    </li>
  </ul>
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

### `contracts/status_list.py`

- **Required root:** `[data-dz-status-entry]` (part `status-list`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-status-entry]` | `data-dz-status-entry` | present (any value) |
| `[data-dz-status-entry]` | `data-dz-state` | one of ['neutral', 'positive', 'warning', 'destructive', 'accent'] |

#### Ingestion model `StatusListEntry`

| Field | Type | Required |
|---|---|---|
| `title` | `string` | yes |
| `state` | `string ∈ ['neutral', 'positive', 'warning', 'destructive', 'accent']` | no |
| `caption` | `string` | no |
| `icon_html` | `string` | no |

#### Exemplar `render()`

```python
def render(entry: StatusListEntry) -> str:
    """Model → one ``<li>`` status entry."""
    state = html.escape(entry.state, quote=True)
    title = html.escape(entry.title)
    if entry.icon_html.strip():
        icon_html = entry.icon_html
    else:
        icon_html = '<span class="dz-status-list-icon-spacer" aria-hidden="true"></span>'
    caption_html = ""
    if entry.caption:
        caption_html = f'<div class="dz-status-list-caption">{html.escape(entry.caption)}</div>'
    pill_html = ""
    if entry.state != "neutral":
        pill_html = f'<span class="dz-status-list-pill">{html.escape(entry.state)}</span>'
    return (
        f'<li class="dz-status-list-entry" data-dz-status-entry '
        f'data-dz-state="{state}">'
        f"{icon_html}"
        f'<div class="dz-status-list-text">'
        f'<div class="dz-status-list-title">{title}</div>'
        f"{caption_html}"
        f"</div>"
        f"{pill_html}"
        f"</li>"
    )
```

## Notes

Per-row state is data-dz-state on the entry (the pill repeats it as text for WCAG 1.4.1); dual-lock root is data-dz-status-entry (contracts/status_list.py). Vocabulary: neutral / positive / warning / destructive / accent (not success). A neutral row has no pill and an icon SPACER keeps the text column aligned. The wrapper's data-dz-entry-count is the server's row count — handy for e2e assertions without counting DOM.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/status_list.py`
