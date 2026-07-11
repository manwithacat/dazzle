# Progress stages (`progress-region`)

A native progress bar with stage chips — where the work is, stage by stage, with completion tones.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="progress-region hm-measure-lg" data-progress-region>
  <div class="progress-header">
    <progress data-progress value="33" max="100"></progress>
    <span>33%</span>
  </div>
  <div class="progress-stages"><span class="progress-chip" data-stage-tone="complete">Draft (4)</span><span class="progress-chip" data-stage-tone="active">Review (2)</span><span class="progress-chip" data-stage-tone="empty">Published (0)</span></div>
  <p class="progress-summary">1 of 3 complete</p>
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

### `contracts/progress.py`

- **Required root:** `[data-dz-progress-region]` (part `progress-region`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-progress-region]` | `data-dz-progress-region` | present (any value) |

#### Ingestion model `ProgressStage`

| Field | Type | Required |
|---|---|---|
| `name` | `string` | yes |
| `count` | `integer` | no |
| `complete` | `boolean` | no |

#### Exemplar `render()`

```python
def render(p: Progress) -> str:
    """Model → progress region."""
    pct_str = _pct_str(p.complete_pct)
    chips_html = "".join(
        f'<span class="dz-progress-chip" data-dz-stage-tone="{_stage_tone(s)}">'
        f"{html.escape(s.name)} ({s.count})"
        f"</span>"
        for s in p.stages
    )
    summary_html = (
        f'<p class="dz-progress-summary">{p.complete_count} of {p.total} complete</p>'
        if p.total > 0
        else ""
    )
    return (
        f'<div class="dz-progress-region" data-dz-progress-region>'
        f'<div class="dz-progress-header">'
        f'<progress data-dz-progress value="{pct_str}" max="100"></progress>'
        f"<span>{pct_str}%</span>"
        f"</div>"
        f'<div class="dz-progress-stages">{chips_html}</div>'
        f"{summary_html}"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-progress-region (contracts/progress.py). The bar is a NATIVE <progress> (styled via data-dz-progress) with its percent readout as a plain <span> beside it in the header; chips are plain text (Name (count)) toned by data-dz-stage-tone="complete|active|empty"; the summary paragraph follows the stages.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/progress.py`
