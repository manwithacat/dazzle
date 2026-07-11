# Stack (`stack`)

Vertical rhythm: children flow top-to-bottom with one gap token. The workhorse — most page sections are a stack of stacks.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="stack" data-gap="md">
  <div class="hm-demo-box">One</div>
  <div class="hm-demo-box">Two</div>
  <div class="hm-demo-box">Three</div>
</div>
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

Flex column + gap — margins stay on the children's insides, so any fragment composes without margin-collapse surprises. data-dz-gap takes xs|sm|md|lg|xl (the spacing token scale); unset = md. Nest freely: a stack inside a stack is the normal way to vary rhythm between groups.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
