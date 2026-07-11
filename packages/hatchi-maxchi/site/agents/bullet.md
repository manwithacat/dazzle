# Bullet chart (`bullet`)

Actual vs target on qualitative bands — the KPI-with-context bar. All geometry is server-computed inline percentages.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="bullet-region hm-measure-lg" data-bullet>
  <div class="bullet-rows">
    <div class="bullet-row">
      <span class="bullet-label">Revenue</span>
      <div class="bullet-track"><span class="bullet-band" style="left: 0%; width: 60%; background: var(--colour-danger);" title="Poor: 0–60"></span><span class="bullet-band" style="left: 60%; width: 25%; background: hsl(40, 90%, 55%);" title="OK: 60–85"></span><span class="bullet-band" style="left: 85%; width: 15%; background: hsl(145, 55%, 45%);" title="Good: 85–100"></span><span class="bullet-actual" style="width: 72%;" title="Revenue actual: 72"></span><span class="bullet-target" style="left: 80%;" title="Revenue target: 80"></span></div>
      <span class="bullet-value">72 / 80</span>
    </div>
  </div>
  <p class="bullet-summary">1 rows · scale 0–100</p>
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

### `contracts/bullet.py`

- **Required root:** `[data-dz-bullet]` (part `bullet`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-bullet]` | `data-dz-bullet` | present (any value) |

#### Ingestion model `BulletBand`

| Field | Type | Required |
|---|---|---|
| `from_value` | `number` | yes |
| `to_value` | `number` | yes |
| `label` | `string` | no |
| `color` | `string ∈ ['target', 'positive', 'warning', 'destructive', 'muted']` | no |

#### Exemplar `render()`

```python
def render(b: Bullet) -> str:
    """Model → bullet chart region."""
    if not b.rows or b.max_value <= 0:
        return (
            f'<div class="dz-bullet-region" data-dz-bullet>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(b.empty_message)}</p>"
            f"</div>"
        )

    rows_html: list[str] = []
    for row in b.rows:
        actual_pct = round(row.actual / b.max_value * 100, 2)
        bands_html = ""
        for band in b.bands:
            band_left = round(band.from_value / b.max_value * 100, 2)
            band_width = round((band.to_value - band.from_value) / b.max_value * 100, 2)
            colour = _BAND_COLORS.get(band.color, _BAND_COLORS["target"])
            bands_html += (
                f'<span class="dz-bullet-band" '
                f'style="left: {band_left}%; width: {band_width}%; '
                f'background: {colour};" '
                f'title="{html.escape(band.label, quote=True)}: '
                f'{_jinja_num(band.from_value)}–{_jinja_num(band.to_value)}"></span>'
            )

        actual_rounded = round(row.actual, 1)
        value_html = _jinja_num(actual_rounded)
        target_html = ""
        if row.target is not None:
            target_pct = round(row.target / b.max_value * 100, 2)
            target_html = (
                f'<span class="dz-bullet-target" '
                f'style="left: {target_pct}%;" '
                f'title="{html.escape(row.label, quote=True)} target: '
                f'{_jinja_num(row.target)}"></span>'
            )
            target_rounded = round(row.target, 1)
            value_html += f" / {_jinja_num(target_rounded)}"

        rows_html.append(
            f'<div class="dz-bullet-row">'
            f'<span class="dz-bullet-label">{html.escape(row.label)}</span>'
            f'<div class="dz-bullet-track">'
            f"{bands_html}"
            f'<span class="dz-bullet-actual" '
            f'style="width: {actual_pct}%;" '
            f'title="{html.escape(row.label, quote=True)} actual: '
            f'{_jinja_num(row.actual)}"></span>'
            f"{target_html}"
            f"</div>"
            f'<span class="dz-bullet-value">{value_html}</span>'
            f"</div>"
        )

    return (
        f'<div class="dz-bullet-region" data-dz-bullet>'
        f'<div class="dz-bullet-rows">{"".join(rows_html)}</div>'
        f'<p class="dz-bullet-summary">'
        f"{len(b.rows)} rows · scale 0–{_jinja_num(round(b.max_value, 1))}"
        f"</p>"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-bullet (contracts/bullet.py). Bands, the actual bar, and the target tick are absolutely positioned by SERVER-computed inline percentages (per-row data, the same contract as the funnel widths); each carries a title with its numeric range. Band fills come from the server's reference-band colour map. The value (and target, when set) renders as text beside the track; the mono summary line carries row count and scale.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/bullet.py`
