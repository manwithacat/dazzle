# Queue (`queue`)

The worklist: a count, roll-up metrics, and attention-flagged rows — the triage surface for SLA-driven work.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="queue-region hm-measure-lg">
  <div class="queue-count-row"><span class="queue-count">7</span><span>open items</span></div>
  <div class="queue-metrics">
    <div class="queue-metric">
      <div class="queue-metric-value">2</div>
      <div class="queue-metric-label">breaching today</div>
    </div>
    <div class="queue-metric">
      <div class="queue-metric-value">4h</div>
      <div class="queue-metric-label">median age</div>
    </div>
  </div>
  <div class="queue-rows">
    <div class="queue-row attn-both attn-tone-critical" data-queue-row data-attn="critical">
      <div class="queue-row-main ">
        <div class="queue-row-headline"><span class="queue-row-title">Refund request — Acme</span></div>
        <p class="queue-row-attn">SLA breaches at 16:00 — assign now.</p>
        <span class="queue-row-date">2h left</span>
      </div>
    </div>
    <div class="queue-row " data-queue-row>
      <div class="queue-row-main ">
        <div class="queue-row-headline"><span class="queue-row-title">KYC review — Globex</span></div>
        <span class="queue-row-date">due tomorrow</span>
      </div>
    </div>
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

### `contracts/queue.py`

- **Required root:** `[data-dz-queue-row]` (part `queue`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-queue-row]` | `data-dz-queue-row` | present (any value) |

#### Ingestion model `QueueRow`

| Field | Type | Required |
|---|---|---|
| `title` | `string` | yes |
| `attention_level` | `string` | no |
| `attention_message` | `string` | no |
| `date_html` | `string` | no |
| `badges_html` | `string` | no |
| `actions_html` | `string` | no |

#### Exemplar `render()`

```python
def render(row: QueueRow) -> str:
    """Model → one queue row (div; matches Dazzle emitter tag)."""
    title = html.escape(row.title)
    attn_class = ""
    attn_data_attr = ""
    attn_message_html = ""
    if row.attention_level:
        level = html.escape(row.attention_level, quote=True)
        attn_class = f"dz-attn-both dz-attn-tone-{html.escape(row.attention_level)}"
        attn_data_attr = f' data-dz-attn="{level}"'
        if row.attention_message:
            attn_message_html = (
                f'<p class="dz-queue-row-attn">{html.escape(row.attention_message)}</p>'
            )
    headline_html = (
        f'<div class="dz-queue-row-headline">'
        f'<span class="dz-queue-row-title">{title}</span>'
        f"{row.badges_html}"
        f"</div>"
    )
    # Trailing space inside class mirrors legacy Jinja when no attn.
    row_open_class = f"dz-queue-row {attn_class}" if attn_class else "dz-queue-row "
    return (
        f'<div class="{row_open_class}" data-dz-queue-row{attn_data_attr}>'
        f'<div class="dz-queue-row-main ">'
        f"{headline_html}"
        f"{attn_message_html}"
        f"{row.date_html}"
        f"</div>"
        f"{row.actions_html}"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-queue-row (contracts/queue.py). Attention rows also carry data-dz-attn plus a human message (dz-queue-row-attn) — the flag is never colour-only. Counts and metrics are SERVER-rendered rollups (the same query that produced the rows, so they can't disagree).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/queue.py`
