# Progress (`progress`)

Toned determinate bar.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack hm-measure">
  <div class="progress" role="progressbar" aria-label="Storage used" aria-valuenow="62" aria-valuemin="0" aria-valuemax="100">
    <div class="progress__bar" style="--progress-value:62%"></div>
  </div>
  <div class="progress" data-tone="success" role="progressbar" aria-label="Upload progress" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100">
    <div class="progress__bar" style="--progress-value:100%"></div>
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
<div id="progress-root" data-dz-region>…</div>
```

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/progress_bar.py`

- **Required root:** `.dz-progress` (part `progress`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-progress` | `—` | — |

#### Ingestion model `ProgressBarModel`

| Field | Type | Required |
|---|---|---|
| `value` | `number` | no |
| `label` | `string` | no |
| `tone` | `string ∈ ['', 'success', 'warning', 'destructive']` | no |
| `max_value` | `number` | no |

#### Exemplar `render()`

```python
def render(p: ProgressBarModel) -> str:
    """Model → dual-lock progress bar markup."""
    pct = _pct_str(p.value, p.max_value)
    now = (
        str(int(p.value))
        if float(p.value) == int(p.value)
        else f"{float(p.value):.1f}".rstrip("0").rstrip(".")
    )
    max_s = (
        str(int(p.max_value))
        if float(p.max_value) == int(p.max_value)
        else f"{float(p.max_value):.1f}".rstrip("0").rstrip(".")
    )
    label = html.escape(p.label or "Progress", quote=True)
    tone_attr = f' data-dz-tone="{html.escape(p.tone, quote=True)}"' if p.tone else ""
    return (
        f'<div class="dz-progress" role="progressbar" aria-label="{label}" '
        f'aria-valuenow="{now}" aria-valuemin="0" aria-valuemax="{max_s}"{tone_attr}>'
        f'<div class="dz-progress__bar" style="--dz-progress-value:{pct}%"></div>'
        f"</div>"
    )
```

## Notes

Dual-lock root is .dz-progress (contracts/progress_bar.py) + role=progressbar.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/progress_bar.py`
