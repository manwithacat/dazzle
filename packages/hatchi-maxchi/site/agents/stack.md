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

## Notes

Flex column + gap — margins stay on the children's insides, so any fragment composes without margin-collapse surprises. data-dz-gap takes xs|sm|md|lg|xl (the spacing token scale); unset = md. Nest freely: a stack inside a stack is the normal way to vary rhythm between groups.
