# Cluster (`cluster`)

A wrapping horizontal group — buttons, chips, metadata rows. Items keep their size and wrap when the line runs out.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="cluster" data-gap="sm"><button class="button" data-variant="primary">Save</button><button class="button" data-variant="outline">Cancel</button><span class="badge" data-tone="neutral">Draft</span></div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Flex row + flex-wrap + gap. data-dz-gap as on stack. data-dz-align (center|start|end|baseline, default center) sets cross-axis alignment; data-dz-justify (start|end|between|center, default start) distributes the line. Never fixes widths — that's what makes it safe for translation-length and zoom changes.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
