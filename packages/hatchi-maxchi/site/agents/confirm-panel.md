# Confirm panel (`confirm-panel`)

The irreversible-action consent gate: a checklist of obligations that must be ticked before the primary action arms, plus live and revoked summary states.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-measure">
  <div class="confirm-panel" data-state-value="off">
    <ul data-confirm-gate class="confirm-checklist" data-required-count="2">
      <li class="confirm-row" data-required="true">
        <input type="checkbox" class="confirm-checkbox" data-required="true" id="confirm-1">
        <label for="confirm-1" class="confirm-row-label"><span class="confirm-title">I have exported a backup of live data</span><span class="confirm-caption">Rollback needs a snapshot taken today.</span></label>
      </li>
      <li class="confirm-row" data-required="true">
        <input type="checkbox" class="confirm-checkbox" data-required="true" id="confirm-2">
        <label for="confirm-2" class="confirm-row-label"><span class="confirm-title">The billing owner has approved this change</span></label>
      </li>
      <li class="confirm-row" data-required="false">
        <input type="checkbox" class="confirm-checkbox" id="confirm-3">
        <label for="confirm-3" class="confirm-row-label"><span class="confirm-title">Notify the team afterwards (optional)</span></label>
      </li>
      <li class="confirm-actions"><a href="#" class="confirm-secondary">Save draft</a><a data-confirm-href="#go-live" aria-disabled="true" class="confirm-primary">Go live</a></li>
    </ul>
    <p class="confirm-audit">This action is recorded in the audit log with your identity and timestamp.</p>
  </div>
  <div class="confirm-panel" data-state-value="live">
    <div class="confirm-summary" data-confirm-tone="success">
      <div class="confirm-summary-title">Currently live</div>
      <div class="confirm-summary-body">Enabled 12 May by j.reyes.</div>
    </div>
    <div class="confirm-actions"><a href="#" class="confirm-revoke">Revoke</a></div>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- data-dz-confirm-gate root + data-dz-required=true checkboxes + data-dz-required-count
- primary anchor parks destination in data-dz-confirm-href until armed
- pick-a-surface: checklist consent → confirm-panel (not dialog / hx-confirm)

### Do / Don't

| Do | Don't |
|---|---|
| keep armed state in the DOM (aria-disabled + href promotion) | mirror checked counts into a JS boolean a swap would orphan |

### Pitfalls

- optional boxes never gate — only data-dz-required=true count
- zero required boxes means the gate is always armed
- not a modal — do not replace with dialog that only mirrors checkbox state in JS

### Keyboard / AT

- primary stays aria-disabled until required count is met
- live/revoked branches use data-dz-confirm-tone for tone, not colour alone

### Related parts

- `button` — agents/button.md
- `field` — agents/field.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/confirm_panel.py`

- **Required root:** `[data-dz-confirm-gate]` (part `confirm-panel`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-confirm-gate]` | `data-dz-required-count` | present (any value) |
| `[data-dz-required="true"]` | `data-dz-required` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: confirm-panel — irreversible-action consent gate."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="confirm-panel",
    root="[data-dz-confirm-gate]",
    nodes=(
        Node(
            "[data-dz-confirm-gate]",
            attrs={"data-dz-required-count": Present()},
        ),
        Node('[data-dz-required="true"]', attrs={"data-dz-required": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

**Pick:** in-flow consent gate — not modal chrome (dialog) and not hx-confirm yes/no (confirm). Stem chrome-vs-protocol: no addressing/gating modal; state-in-DOM. Primary ships aria-disabled with destination in data-dz-confirm-href; dz-confirm-gate.js recounts data-dz-required=true vs data-dz-required-count and arms the primary. Optional boxes never gate. Live/revoked branches use dz-confirm-summary + data-dz-confirm-tone.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/confirm_panel.py`
- `controllers/dz-confirm-gate.js`
