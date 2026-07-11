# Pivot table (`pivot`)

Two group-bys crossed into a matrix — row labels × column buckets, empty intersections rendered as explicit nulls.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="pivot-region hm-measure-lg" data-pivot>
  <div class="pivot-scroll">
    <table class="pivot-grid">
      <thead>
        <tr>
          <th>System</th>
          <th>Severity</th>
          <th class="is-measure">Count</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>API</td>
          <td><span class="badge badge-sm" data-tone="destructive" role="status" aria-label="Status: Critical"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-x"/></svg></span>Critical</span></td>
          <td class="is-measure">3</td>
        </tr>
        <tr>
          <td>Dashboard</td>
          <td><span class="pivot-null">—</span></td>
          <td class="is-measure">9</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="pivot-summary">2 rows</p>
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

### `contracts/pivot.py`

- **Required root:** `[data-dz-pivot]` (part `pivot`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-pivot]` | `data-dz-pivot` | present (any value) |

#### Ingestion model `PivotTable`

| Field | Type | Required |
|---|---|---|
| `dim_headers` | `array` | no |
| `measure_headers` | `array` | no |
| `rows` | `array` | no |
| `empty_message` | `string` | no |

#### Exemplar `render()`

```python
def render(p: PivotTable) -> str:
    """Model → pivot table region."""
    if not p.rows:
        return (
            f'<div class="dz-pivot-region" data-dz-pivot>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(p.empty_message)}</p>"
            f"</div>"
        )

    head_dim = "".join(f"<th>{html.escape(h)}</th>" for h in p.dim_headers)
    head_measure = "".join(
        f'<th class="is-measure">{html.escape(h)}</th>' for h in p.measure_headers
    )
    thead = f"<thead><tr>{head_dim}{head_measure}</tr></thead>"
    n_dim = len(p.dim_headers)
    body_parts: list[str] = []
    for row in p.rows:
        cells = ""
        for i, c in enumerate(row):
            if i >= n_dim:
                cells += f'<td class="is-measure">{c}</td>'
            else:
                cells += f"<td>{c}</td>"
        body_parts.append(f"<tr>{cells}</tr>")
    tbody = f"<tbody>{''.join(body_parts)}</tbody>"
    n = len(p.rows)
    suffix = "" if n == 1 else "s"
    summary = f'<p class="dz-pivot-summary">{n} row{suffix}</p>'
    return (
        f'<div class="dz-pivot-region" data-dz-pivot>'
        f'<div class="dz-pivot-scroll">'
        f'<table class="dz-pivot-grid">{thead}{tbody}</table>'
        f"</div>"
        f"{summary}"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-pivot (contracts/pivot.py). One scope-aware two-dimensional GROUP BY fills the whole matrix: dimension columns lead (status values render as badges, FK values as their label text), then measure columns — class="is-measure" on the measure th/td pair drives the mono right-aligned numeric treatment. Empty intersections render dz-pivot-null em-dashes rather than blanks (absence is data). The scroll wrapper keeps wide matrices inside their card. Cell HTML is host-trusted SSR so badges stay on the Dazzle side.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/pivot.py`
