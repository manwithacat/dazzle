# Timeline (`timeline`)

Dated events on a vertical line — bullets carry the attention contract, dates keep a fixed column so titles align.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="timeline-region hm-measure-lg">
  <ul class="timeline-list">
    <li class="timeline-item" data-timeline-item>
      <span class="timeline-bullet-wrap"><svg class="timeline-bullet attn-bullet attn-tone-critical" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="timeline-row">
        <div class="timeline-date">Today</div>
        <div class="timeline-content">
          <p class="timeline-title">Payment failed — retry scheduled</p>
          <p class="timeline-field">Card declined (insufficient funds)</p>
        </div>
      </div>
    </li>
    <li class="timeline-item" data-timeline-item>
      <span class="timeline-bullet-wrap"><svg class="timeline-bullet attn-bullet attn-tone-default" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="timeline-row">
        <div class="timeline-date">Mon</div>
        <div class="timeline-content">
          <p class="timeline-title">Invoice sent</p>
        </div>
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

### `contracts/timeline.py`

- **Required root:** `[data-dz-timeline-item]` (part `timeline`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-timeline-item]` | `data-dz-timeline-item` | present (any value) |

#### Ingestion model `TimelineEvent`

| Field | Type | Required |
|---|---|---|
| `title` | `string` | yes |
| `date_label` | `string` | no |
| `fields_html` | `string` | no |
| `bullet_html` | `string` | no |

#### Exemplar `render()`

```python
def render(evt: TimelineEvent) -> str:
    """Model → one ``<li>`` timeline item."""
    title = html.escape(evt.title)
    date = html.escape(evt.date_label)
    bullet = evt.bullet_html.strip() or _DEFAULT_BULLET
    return (
        f'<li class="dz-timeline-item" data-dz-timeline-item>'
        f'<span class="dz-timeline-bullet-wrap">{bullet}</span>'
        f'<div class="dz-timeline-row">'
        f'<div class="dz-timeline-date">{date}</div>'
        f'<div class="dz-timeline-content">'
        f'<p class="dz-timeline-title">{title}</p>'
        f"{evt.fields_html}"
        f"</div>"
        f"</div>"
        f"</li>"
    )
```

## Notes

Dual-lock root is data-dz-timeline-item (contracts/timeline.py). The bullet is an inline SVG on currentColor, toned by dz-attn-tone-* (critical/warning/notice/default). Overflowing timelines append a dz-timeline-overflow count line.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/timeline.py`
