# HaTchi-MaXchi

An **htmx4-native design system** — the maturity of the modern component
aesthetic without a client framework. Server-rendered markup, semantic
`dz-*` classes + `data-dz-*` modifiers, design tokens for all variation,
and interactions built on the htmx request lifecycle.

This directory is self-contained: `hatchi-maxchi.css`, `hatchi-maxchi.js`
(behaviour controllers + a mock htmx for the static demos), vendored fonts,
and `index.html` (the component gallery). Serve it on GitHub Pages as-is.

## Use

```html
<link rel="stylesheet" href="hatchi-maxchi.css">
<script src="hatchi-maxchi.js" defer></script>
```

Copy any component's HTML from the gallery. In a real app, swap the mock
htmx for [htmx](https://htmx.org) and point the `hx-*` attributes at your
endpoints (e.g. the command palette's `hx-get` at your search route).

Generated from the [Dazzle](https://github.com/manwithacat/dazzle) source of
truth by `scripts/hm_site/build_site.py`. Geist (OFL) and Lucide (ISC) are
vendored; see `fonts/OFL.txt`.
