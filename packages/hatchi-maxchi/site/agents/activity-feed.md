# Activity feed (`activity-feed`)

Who-did-what rows on a dotted spine — actor, time, and a message bubble.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-measure-lg">
  <ul class="activity-feed">
    <li class="activity-row" data-activity-row>
      <span class="activity-dot"><svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="activity-row-inner">
        <div class="activity-time">09:41</div>
        <div class="activity-bubble"><span class="activity-actor">Ada</span> approved the refund.</div>
      </div>
    </li>
    <li class="activity-row" data-activity-row>
      <span class="activity-dot"><svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6"/></svg></span>
      <div class="activity-row-inner">
        <div class="activity-time">09:12</div>
        <div class="activity-bubble"><span class="activity-actor">System</span> flagged the account for review.</div>
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

### `contracts/activity_feed.py`

- **Required root:** `[data-dz-activity-row]` (part `activity-feed`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-activity-row]` | `data-dz-activity-row` | present (any value) |

#### Ingestion model `ActivityRow`

| Field | Type | Required |
|---|---|---|
| `time_str` | `string` | yes |
| `description` | `string` | yes |
| `actor` | `string` | no |

#### Exemplar `render()`

```python
def render(row: ActivityRow) -> str:
    """Model → one ``<li>`` activity row."""
    time_s = html.escape(row.time_str)
    actor_html = ""
    if row.actor:
        actor_html = f'<span class="dz-activity-actor">{html.escape(row.actor)}</span> '
    # Trailing space after bubble open class mirrors Dazzle emitter legacy.
    return (
        f'<li class="dz-activity-row" data-dz-activity-row>'
        f'<span class="dz-activity-dot">{_DOT_SVG}</span>'
        f'<div class="dz-activity-row-inner">'
        f'<div class="dz-activity-time">{time_s}</div>'
        f'<div class="dz-activity-bubble" >'
        f"{actor_html}{html.escape(row.description)}"
        f"</div>"
        f"</div>"
        f"</li>"
    )
```

## Notes

Dual-lock root is data-dz-activity-row (contracts/activity_feed.py). Rows are server-rendered newest-first; an empty feed renders dz-activity-empty. The dot column and bubble keep alignment without a grid — the row is the flex unit.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/activity_feed.py`
