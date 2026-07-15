# 0053 — HM is the frontend UI owner; pages compose Hyperparts

**Status:** Accepted
**Date:** 2026-07-14
**Issue:** #1585
**Related:** ADR-0041 (layer rename `dazzle_ui` → `dazzle.page`), ADR-0011
(SSR/htmx), HM decisions 0001 / 0004 (invention ladder) / 0010, dual-locks
(HM README)

## Context

HaTchi-MaXchi (HM) is the product design system: Hyperparts, dual-locks,
component CSS, controllers, gallery. After ADR-0041 the package path
`src/dazzle_ui/` is **gone**, but tooling globs, comments, and mental models
still pointed at the old tree. Agents and humans then grew UI in the wrong
place — which starves `/improve` signals that assume HM is the chrome owner
(dual-lock expand, gallery probes, coherence).

This ADR freezes **ownership and the innovation funnel** so “where does UI
live?” and “how do I invent UX?” have one answer.

## Decision

### 1. Pages use Hyperparts — they do not grow a parallel UI kit

**Product surfaces** (example apps, generated fragments, workspace chrome)
**compose** from gallery Hyperparts and Dazzle emitters that already emit
HM markup (`dz-*` roots, dual-locked contracts). That is the default path
for *all* user-visible UI — not “HM for the design system and page for
whatever the app needs.”

| Goal | Do this |
|------|---------|
| Familiar pattern | Copy / compose gallery partials (and existing emitters) |
| Novel UX | **Innovate inside HM shapes** — new or extended Hyperpart, dual-lock, optional controller — via the **invention ladder** (HM decision 0004) |
| Host concerns only | CSRF, toast host, analytics, auth *plumbing*, islands that are capabilities not chrome |

We are **not** trying to prevent novel UX. We are funneling novelty into
**controlled, auditable** Hyperparts (contracts, dual-locks, gallery,
coherence) so agents and CI can keep improving them. One-off page static
“components” that bypass that funnel are the anti-pattern.

### 2. HM owns the design-system UI surface

| Owns | Location |
|------|----------|
| Hyperpart partials + exchange contracts | `packages/hatchi-maxchi/site/registry.py` |
| Dual-lock modules | `packages/hatchi-maxchi/contracts/` |
| Component CSS | `packages/hatchi-maxchi/components/` |
| Hyperpart controllers | `packages/hatchi-maxchi/controllers/` |
| Tokens / base | `packages/hatchi-maxchi/tokens/`, `base/` |
| Gallery + standalone package | `packages/hatchi-maxchi/site/`, package root |

**Default for new or changed UI chrome:** invent or extend a Hyperpart in HM,
dual-lock it, emit from Dazzle via FragmentRenderer / ingest. **Do not** add
a parallel component library under `dazzle.page`.

### 3. `dazzle.page` is host shell + residual product glue — shrinking set

Page static assets are **not** “the other place for UI.” They are host
plumbing and a **temporary parking lot** for work that has not yet been
promoted into a Hyperpart (or never will, because it is not chrome).

| Class | Examples under `src/dazzle/page/runtime/static/` | Rule |
|-------|--------------------------------------------------|------|
| **True host glue** | `dz-csrf.js`, `dz-toast.js` (stack host), `dz-analytics.js`, `dz-consent.js`, `dz-usage.js`, `dz-debug.js`, `dz-qa.js`, `dz-utils.js` | Stay in page — not design-system parts |
| **Product flows (promote candidates)** | `dz-2fa-setup.js`, `dz-2fa-settings.js`, `dz-onboarding.js`, search-box Alpine residuals | Prefer **promote to Hyperpart** when the UX is user-facing chrome; do not grow new peers here |
| **Islands / capabilities** | `islands/signing-pad.js`, PDF shell, richtext | Capability islands OK; if they grow design-system chrome, extract Hyperparts |
| **Bridge / registry** | `dz-islands.js`, `dz-widget-registry.js`, `dz-component-bridge.js`, `dashboard-builder.js`, `feedback-widget.js` | Host wiring only |
| **Host CSS shell** | `css/dazzle.css`, `dazzle-framework.css`, `reset.css`, `themes/*` | Layer/theme host; **Hyperpart skins live in HM** |
| **Vendor** | `vendor/htmx*.js`, lucide | Third-party |

**Promotion is the happy path** for user-visible chrome still stranded in
page: ladder → gallery pattern → dual-lock → emitter. What we reject is a
**bulk file move** that relocates glue without creating Hyperparts (no
contracts, no gallery, no audit surface).

### 4. Path hygiene

- **Active tooling must not glob `src/dazzle_ui/**`.** That directory does not
  exist. ESLint targets `src/dazzle/page/**/js` + HM controllers; vitest /
  stylelint match page + HM (see #1585 audit).
- Historical “was dazzle_ui” comments may teach the rename; they must not
  appear as **live** include paths.
- The string “Dazzle UI” in docs may mean the product SSR surface generically;
  the **package** is `dazzle.page`.

### 5. Examples and generated previews

- Live examples run via `dazzle serve` / typed Fragments + HM dist (`--prefix dz-`).
- `examples/*/dnr-ui/` is a **generated** static preview (`dazzle build-ui`);
  not the runtime package path. Spot-check (2026-07-14): local previews for
  `simple_task` / `contact_manager` already emit **`dz-*` Hyperpart roots**
  (shell, table, form, command). Residual noise:
  - Alpine `x-data` on search-box (promote/drain candidate — ADR-0022 / HM 0007)
  - Stale spinner classes on older exports — live emitters use
    `dz-spinner-track` / `dz-spinner-head`; re-run `dazzle build-ui` to refresh
- Improve lanes that score example UX should prefer **live** or freshly built
  HTML, not aged `dnr-ui` trees — and treat “does this compose HM Hyperparts?”
  as the quality bar.

## Success criteria (#1585)

- [x] Zero *active* tooling globs point at `src/dazzle_ui`
- [x] Written ownership + innovation-funnel doctrine (this ADR)
- [x] Agents default to HM Hyperparts for UI (AGENTS.md + this ADR)

Follow-ups that **promote** residual page chrome (auth flows, search-box,
etc.) are **encouraged product work**, not a rejection of the doctrine.
Track them as promote issues, not as “page is allowed forever.”

## Rejected

- **Bulk-move page JS into HM without Hyperparts** — relocating files without
  gallery partials, dual-locks, and emit seams does not make UI auditable
- Revive `dazzle_ui` as a package name
- Treat `dnr-ui/` export as a second design system
- Grow new user-visible chrome only under `dazzle.page` “because it’s product”
