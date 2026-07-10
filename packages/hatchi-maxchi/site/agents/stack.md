# Stack (`stack`)

Vertical rhythm: children flow top-to-bottom with one gap token. The workhorse — most page sections are a stack of stacks.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="stack" data-gap="md">
  <div class="hm-demo-box">One</div>
  <div class="hm-demo-box">Two</div>
  <div class="hm-demo-box">Three</div>
</div>
```

## Guidance (prose; HTML from the registry notes field)

Flex column + <code>gap</code> — margins stay on the children's insides, so any fragment composes without margin-collapse surprises. <code>data-dz-gap</code> takes <code>xs|sm|md|lg|xl</code> (the spacing token scale); unset = <code>md</code>. Nest freely: a stack inside a stack is the normal way to vary rhythm between groups.
