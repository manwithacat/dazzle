# HaTchi-MaXchi

**An htmx-native design system.** The polish of the modern component
aesthetic — complete states, disciplined spacing, dark as a material —
with zero client framework. Server-rendered markup, semantic classes,
OKLCH design tokens, and interactions built on the htmx request
lifecycle.

**[Browse the live gallery →](https://manwithacat.github.io/hatchi-maxchi/)**
Every example *is* its copy-paste snippet — the demo and the docs are the
same string, so they cannot drift.

[![CI](https://github.com/manwithacat/hatchi-maxchi/actions/workflows/ci.yml/badge.svg)](https://github.com/manwithacat/hatchi-maxchi/actions/workflows/ci.yml)
[![Pages](https://github.com/manwithacat/hatchi-maxchi/actions/workflows/pages.yml/badge.svg)](https://manwithacat.github.io/hatchi-maxchi/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Quick start

Hosted on the [jsDelivr](https://www.jsdelivr.com/) free CDN, pinned to a
release tag (fonts resolve relatively — no extra setup):

```html
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/gh/manwithacat/hatchi-maxchi@v0.1.1/dist/hatchi-maxchi.css"
      integrity="sha384-4Z7gtoZuZUhVnNEMeDC3/AXOILjQcFC/nbO9nQphICi8jo1RGGYZGs+CHPwOfTYw"
      crossorigin="anonymous">
<script src="https://cdn.jsdelivr.net/gh/manwithacat/hatchi-maxchi@v0.1.1/dist/hatchi-maxchi.js"
        integrity="sha384-jGqDs8tteHH9K20CHlgS9G9u65mjpYvV3hBuarTb2oI8ahsPn8CxPYqbPMUhCtl1"
        crossorigin="anonymous" defer></script>
```

Each [release](https://github.com/manwithacat/hatchi-maxchi/releases)'s
notes carry the ready-to-paste snippet with that version's SRI hashes
(a CI drift gate pins the committed `dist/` to the sources, so the tag
serves exactly these bytes).

Prefer self-hosting? Download the same two files (plus `fonts/`) from the
[latest release](https://github.com/manwithacat/hatchi-maxchi/releases)
or build them yourself (`python build.py`):

```html
<link rel="stylesheet" href="hatchi-maxchi.css">
<script src="hatchi-maxchi.js" defer></script>
```

Then copy any component's HTML from the gallery and point its `hx-*`
attributes at your endpoints:

```html
<button class="dz-button dz-button-primary">Save changes</button>

<span class="dz-badge" data-dz-tone="success" role="status">Approved</span>

<!-- the command palette is an hx-get endpoint, not a client fuzzy-finder -->
<dialog class="dz-command" aria-label="Command palette">
  <input class="dz-command__input" type="search"
         hx-get="/app/command" hx-trigger="input changed delay:150ms"
         hx-target="next .dz-command__results">
  <div class="dz-command__results" role="listbox"></div>
</dialog>
```

No build step, no JSX, no utility soup. One semantic root class per
component, `data-dz-*` attributes for variants, tokens for every value.

## The unit is a Hyperpart, not a component

A React component bundles structure, behaviour, and *client* state into a
tree. HaTchi-MaXchi's unit is different enough to deserve its own name — a
**Hyperpart**:

> **Hyperpart** = a *partial* (server-rendered markup + classes) + its
> *exchange contract(s)* (the endpoint request/response the server must
> satisfy) + an optional *controller* (vanilla JS, only where the platform
> lacks a primitive).

The naming is deliberate. "Component" imports React priors — client state,
props, composition trees — which are exactly wrong for a server-owned
partial, and an agent told to build a "component" reaches for them. A
Hyperpart has no client state graph: state lives on the server and htmx
swaps the markup.

The second half — the **exchange contract** — is the part shadcn never had
to standardise (React resolves state locally). For interactive Hyperparts
the gallery documents it explicitly: *what request the affordance makes,
and what fragment your server must return.* It's a first-class, CI-checked
artifact (a partial that makes an undeclared request fails the build). In
Dazzle the response is emitted automatically; in any other htmx app, return
matching markup from your endpoint. (Vocabulary from *Hypermedia Systems*:
a request/response round-trip is a "hypermedia exchange"; the individual
`hx-*` control that initiates it is an "affordance".)

### One unit, distributed by the build — the manifest keeps it legible

A Hyperpart's code is physically scattered *by build necessity*: its CSS
is concatenated in cascade-layer order (so it lives in `components/*.css`
accumulators), its controller is bundled (`controllers/`), and its markup
+ contract are in `site/registry.py`. We can't co-locate everything in one
file like shadcn — but the relationship must stay legible, both to an agent
and a human. Two mechanisms, kept honest by a gate:

- **Top-down** — the registry entry is the *manifest*: `partial` and
  `exchanges` inline, `controller` and `mock` as pointers.
- **Bottom-up** — each CSS block and controller carries a
  `/* HYPERPART: <id> */` marker, so opening any file tells you which
  Hyperpart it serves. Styles are *discovered* from these markers (a
  component's CSS is genuinely many-to-many across files), not hand-listed.

`python tools/hyperpart.py <id>` assembles the full anatomy:

```
$ python tools/hyperpart.py command
Hyperpart: command  (Command palette)
  partial     site/registry.py (inline markup)
  exchanges   GET /app/command
  styles      components/hm-core.css:256
  controller  controllers/dz-command.js
  mock        /mock/command
```

`tests/test_hyperpart_cohesion.py` fails CI if the manifest and the markers
disagree (unowned controller, orphan marker, interactive Hyperpart with no
style marker, controller not marked). The gallery shows the same anatomy
inline for interactive Hyperparts.

## Why htmx-native (not transliterated React)

Most design systems assume a client framework owns the DOM. HaTchi-MaXchi
assumes **the server owns the DOM** and htmx swaps it:

- **The command palette** is an input with `hx-get` — results are a server
  swap, scoped to the signed-in user, not a client-side index.
- **Confirm dialogs**: any element with `hx-confirm` gets the designed
  dialog automatically (`dz-confirm.js` intercepts `htmx:confirm`) — no
  per-button wiring.
- **Loading, empty, and error states** key off the htmx request lifecycle
  (`htmx-request`, swap events), so states are complete by construction.
- **Menus and popovers** are `<details>`/`<dialog>` — native behaviour,
  styled; JavaScript only where the platform has no primitive.

## Theming

All colour flows through OKLCH semantic tokens; light/dark is
`light-dark()` bound to `[data-theme]` (with `prefers-color-scheme` as
the default). Rebrand by overriding tokens — never by editing components:

```css
:root {
  --colour-brand: oklch(54% 0.2 150);   /* your accent */
  --radius-md: 0.5rem;                   /* your geometry */
}
```

Key tokens: `--colour-bg`, `--colour-surface`, `--colour-surface-muted`,
`--colour-text`, `--colour-text-muted`, `--colour-border`,
`--colour-brand`, `--colour-success/warning/danger/info`, the
`--colour-*-soft` washes, and the `--focus-ring-*` family. See
[`tokens/tokens.css`](tokens/tokens.css) — it reads top to bottom.

## The `dz-` prefix is a default, not a requirement

The namespace is configurable at build time:

```bash
python build.py --prefix ax-   # .ax-button, data-ax-tone, ax-fade-in…
```

The rename is total across CSS and JS (class names, `data-dz-*`
attributes, keyframes). Your markup must use the same prefix — gallery
snippets are published with `dz-`, so search-and-replace `dz-` → `ax-`
when you copy. (In [Dazzle](https://github.com/manwithacat/dazzle), which
emits this markup from a DSL, the default prefix is part of the contract.)

## The map

| Path | What lives here |
|------|-----------------|
| `tokens/` | `tokens.css` — OKLCH ramps + semantic tokens (`--colour-*`), type, spacing, shadow, motion, focus. The single colour vocabulary. |
| `base/` | `base.css` (element defaults + focus net), `fonts.css` (Geist @font-face), `design-system.css` (non-colour tokens + vendor-widget theming). |
| `components/` | Component CSS. One semantic root class + `data-dz-*` modifiers; tokens carry the aesthetic. |
| `controllers/` | Vanilla-JS for the purely-client bits (`dz-confirm.js`, `dz-command.js`). htmx-aware, framework-free. |
| `icons/` | The Lucide subset — source of truth (`registry.py`, ISC), rendering helpers, and the generator. Dazzle vendors a drift-gated copy. |
| `site/` | The gallery — a committed build artifact, deployed to Pages as-is. `registry.py` is the **source of truth for the Hyperpart catalogue** (partials + their exchange contracts). |
| `build.py` | Builds `dist/` (CSS + JS + fonts) from package sources. Stdlib-only; takes `--prefix`. |
| `tests/` | Regression gates: contract (console), behaviour (headless Chromium), visual (screenshot vs committed per-platform baselines), and **WCAG 2.2 AA** (vendored axe-core over the gallery in light + dark + opened-overlay states; allowlist may only shrink). |

## Identity — familiar, not identical

HaTchi-MaXchi matches shadcn's *quality* signals (complete states, spacing
discipline, focus rings, layered elevation, dark-as-material) but owns its
*identity* signals — a chromatic accent (not monochrome zinc),
colour+icon+text semantics (WCAG 1.4.1: status never relies on colour
alone), tone-wash surfaces, htmx-lifecycle motion, and ops-app data
density. The review test for every component: credible to a shadcn-fluent
developer, but not mistakable for shadcn side-by-side.

## Versioning & releases

Semantic versioning from **0.1.0**; `package.json` is the version source
of truth and release tags (`v0.1.0`) must match it — CI enforces this and
attaches the built bundle to each
[GitHub release](https://github.com/manwithacat/hatchi-maxchi/releases).
Pre-1.0, minor bumps may rename or reshape components; patch bumps are
safe to restyle on.

## Development

The system is developed inside the
[Dazzle monorepo](https://github.com/manwithacat/dazzle)
(`packages/hatchi-maxchi/` — the source of truth). PRs against this repo
are welcome for discussion, but fixes land in the monorepo, where the
design system's blind-panel taste oracle and a 12-app example fleet
exercise every component.

**Publish pipeline:** every monorepo push touching the package triggers a
subtree sync to this repo's `main` (Dazzle's `sync-hatchi-maxchi.yml`,
authenticated by a repo-scoped deploy key); this repo's CI then gates the
sync and Pages redeploys the gallery. **Releases are never automatic**:
bump `package.json` in the monorepo (the sync carries it here), then
either push the matching `v*` tag or run the Release workflow from the
Actions tab with the version input — both validate tag == package.json
and attach the built bundle + CDN/SRI snippet.

Run the gates locally:

```bash
pip install pytest playwright pillow && playwright install chromium
python build.py && python -m pytest tests/
```

Visual baselines: after an intended visual change,
`HM_UPDATE_BASELINES=1 python -m pytest tests/test_visual.py` and commit
the PNGs.

### Add a Hyperpart

1. Write its CSS in `components/` — one root class, `data-dz-*` variants,
   tokens for all values.
2. Add a `Hyperpart(...)` to `site/registry.py` — its `partial` is the
   gallery demo *and* the copy-paste snippet (same string, can't drift).
3. If it makes htmx requests, declare an `Exchange(...)` per request in
   the Hyperpart's `exchanges` — method, endpoint, trigger, response
   fragment, swap. The contract gate fails if the markup makes a request
   with no matching Exchange (or declares one it doesn't make).
4. Client behaviour (only if the platform has no primitive) goes in
   `controllers/`.
5. Register the CSS file in `build.py` `CSS_SOURCES` (and, in-tree,
   Dazzle's build lists). Rebuild; the contract test fails on any
   published class without a rule.

## Licence

MIT. Vendored assets: [Geist](https://vercel.com/font) (OFL, see
`site/fonts/OFL.txt`) and [Lucide](https://lucide.dev) icons (ISC).
