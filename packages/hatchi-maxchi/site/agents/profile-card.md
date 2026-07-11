# Profile card (`profile-card`)

The identity panel: avatar or initials beside name and meta, an optional 3-up stats grid, and a bulleted facts list.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="profile-card-region hm-measure">
  <div class="profile-card" data-profile-card>
    <div class="profile-identity">
      <span class="profile-initials" aria-hidden="true">MR</span>
      <div class="profile-text">
        <h3 class="profile-primary">Maya Reyes</h3>
        <p class="profile-secondary">Operations lead · North grid</p>
      </div>
    </div>
    <dl class="profile-stats">
      <div class="profile-stat">
        <dt class="profile-stat-label">Open work orders</dt>
        <dd class="profile-stat-value">7</dd>
      </div>
      <div class="profile-stat">
        <dt class="profile-stat-label">Sites</dt>
        <dd class="profile-stat-value">3</dd>
      </div>
      <div class="profile-stat">
        <dt class="profile-stat-label">On call</dt>
        <dd class="profile-stat-value">—</dd>
      </div>
    </dl>
    <ul class="profile-facts">
      <li class="profile-fact"><span class="profile-fact-bullet" aria-hidden="true">·</span><span class="profile-fact-text">Certified for HV switching</span></li>
      <li class="profile-fact"><span class="profile-fact-bullet" aria-hidden="true">·</span><span class="profile-fact-text">Joined March 2024</span></li>
    </ul>
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

### `contracts/profile_card.py`

- **Required root:** `[data-dz-profile-card]` (part `profile-card`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-profile-card]` | `data-dz-profile-card` | present (any value) |

#### Ingestion model `ProfileCard`

| Field | Type | Required |
|---|---|---|
| `primary` | `string` | no |
| `secondary` | `string` | no |
| `avatar_url` | `string` | no |
| `initials` | `string` | no |
| `stats` | `array` | no |
| `facts` | `array` | no |

#### Exemplar `render()`

```python
def render(card: ProfileCard) -> str:
    """Model → profile card (with region wrapper matching Dazzle emit)."""
    if card.avatar_url:
        avatar_html = (
            f'<img src="{html.escape(card.avatar_url, quote=True)}" '
            f'alt="{html.escape(card.primary, quote=True)}" '
            f'class="dz-profile-avatar" />'
        )
    elif card.initials:
        avatar_html = (
            f'<span class="dz-profile-initials" aria-hidden="true">'
            f"{html.escape(card.initials)}</span>"
        )
    else:
        avatar_html = ""

    text_inner = ""
    if card.primary:
        text_inner += f'<h3 class="dz-profile-primary">{html.escape(card.primary)}</h3>'
    if card.secondary:
        text_inner += f'<p class="dz-profile-secondary">{html.escape(card.secondary)}</p>'
    identity_html = (
        f'<div class="dz-profile-identity">'
        f"{avatar_html}"
        f'<div class="dz-profile-text">{text_inner}</div>'
        f"</div>"
    )

    stats_html = ""
    if card.stats:
        stat_rows = "".join(
            f'<div class="dz-profile-stat">'
            f'<dt class="dz-profile-stat-label">{html.escape(label)}</dt>'
            f'<dd class="dz-profile-stat-value">'
            f"{html.escape(value) if value else '—'}</dd>"
            f"</div>"
            for label, value in card.stats
        )
        stats_html = f'<dl class="dz-profile-stats">{stat_rows}</dl>'

    facts_html = ""
    if card.facts:
        fact_items = "".join(
            f'<li class="dz-profile-fact">'
            f'<span class="dz-profile-fact-bullet" aria-hidden="true">·</span>'
            f'<span class="dz-profile-fact-text">{html.escape(fact)}</span>'
            f"</li>"
            for fact in card.facts
        )
        facts_html = f'<ul class="dz-profile-facts">{fact_items}</ul>'

    return (
        f'<div class="dz-profile-card-region">'
        f'<div class="dz-profile-card" data-dz-profile-card>'
        f"{identity_html}{stats_html}{facts_html}"
        f"</div>"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-profile-card (contracts/profile_card.py). The avatar slot prefers an <img class="dz-profile-avatar"> and falls back to an initials chip; empty stat values render an em-dash (absence is data). Stats are a real <dl>; the facts bullet is decorative markup, hidden from assistive tech.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/profile_card.py`
