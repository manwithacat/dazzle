# 0053 — HM is the frontend UI owner; page is host + product glue

**Status:** Accepted
**Date:** 2026-07-14
**Issue:** #1585
**Related:** ADR-0041 (layer rename `dazzle_ui` → `dazzle.page`), ADR-0011
(SSR/htmx), HM decisions 0001 / 0010, dual-locks (HM README)

## Context

HaTchi-MaXchi (HM) is the product design system: Hyperparts, dual-locks,
component CSS, controllers, gallery. After ADR-0041 the package path
`src/dazzle_ui/` is **gone**, but tooling globs, comments, and mental models
still pointed at the old tree. Agents and humans then grew or audited UI in
the wrong place — which starves `/improve` signals that assume HM is the
chrome owner (dual-lock expand, gallery probes, coherence).

This ADR freezes ownership so “where does UI live?” has one answer.

## Decision

### 1. HM owns the design-system UI surface

| Owns | Location |
|------|----------|
| Hyperpart partials + exchange contracts | `packages/hatchi-maxchi/site/registry.py` |
| Dual-lock modules | `packages/hatchi-maxchi/contracts/` |
| Component CSS | `packages/hatchi-maxchi/components/` |
| Hyperpart controllers | `packages/hatchi-maxchi/controllers/` |
| Tokens / base | `packages/hatchi-maxchi/tokens/`, `base/` |
| Gallery + standalone package | `packages/hatchi-maxchi/site/`, package root |

**Default for new UI chrome:** invent or extend a Hyperpart in HM (invention
ladder), dual-lock it, emit from Dazzle via FragmentRenderer / ingest. Do
**not** add a parallel component kit under `dazzle.page`.

### 2. `dazzle.page` owns host shell + product glue only

| Class | Examples under `src/dazzle/page/runtime/static/` | Rule |
|-------|--------------------------------------------------|------|
| **Product glue** | `dz-csrf.js`, `dz-toast.js`, `dz-analytics.js`, `dz-consent.js`, `dz-usage.js`, `dz-debug.js`, `dz-qa.js`, `dz-utils.js` | Stay in page; not Hyperparts |
| **Auth / product flows** | `dz-2fa-setup.js`, `dz-2fa-settings.js`, `dz-onboarding.js` | Stay in page until deliberately promoted |
| **Islands** | `islands/signing-pad.js`, PDF shell, richtext | App/product capability; promote only via ladder |
| **Bridge / registry** | `dz-islands.js`, `dz-widget-registry.js`, `dz-component-bridge.js`, `dashboard-builder.js`, `feedback-widget.js` | Host wiring; no second design system |
| **Host CSS shell** | `css/dazzle.css`, `dazzle-framework.css`, `reset.css`, `themes/*` | Layer/theme host chrome; **not** Hyperpart skins (those are HM) |
| **Vendor** | `vendor/htmx*.js`, lucide | Third-party |

### 3. Path hygiene

- **Active tooling must not glob `src/dazzle_ui/**`.** That directory does not
  exist. ESLint already targets `src/dazzle/page/**/js` + HM controllers;
  vitest / stylelint must match (see #1585 audit).
- Historical “was dazzle_ui” comments are allowed when they teach the rename;
  they must not appear as **live** include paths.
- The string “Dazzle UI” in docs may mean the product SSR surface generically;
  the **package** is `dazzle.page`.

### 4. Examples and generated previews

- Live examples run via `dazzle serve` / typed Fragments + HM dist (`--prefix dz-`).
- `examples/*/dnr-ui/` is a **generated** static preview (`dazzle build-ui`);
  not the runtime package path. Spot-check (2026-07-14): committed local
  previews for `simple_task` / `contact_manager` already emit **`dz-*` Hyperpart
  roots** (shell, table, form, command). Residual non-HM noise found:
  - Alpine `x-data` on search-box regions (known morph tension — ADR-0022 /
    HM 0007; product residual, not a second CSS kit)
  - Stale snapshot classes (`opacity-25`/`opacity-75`) on older exports — live
    emitters use `dz-spinner-track` / `dz-spinner-head`; re-run `dazzle build-ui`
    to refresh previews
- Improve lanes that score example UX should prefer **live** or freshly built
  HTML, not aged `dnr-ui` trees.

## Success criteria (#1585)

- [x] Zero *active* tooling globs point at `src/dazzle_ui`
- [x] Written ownership table (this ADR)
- [x] Agents default to HM for new UI chrome (AGENTS.md pointer + this ADR)

Promote follow-ups (auth→Hyperpart, Alpine drain on search-box, etc.) are
**separate issues** — not required to close the audit track.

## Rejected

- Mass-move every page JS file into HM in one PR (unreviewable; mixes glue with design system)
- Revive `dazzle_ui` as a package name
- Treat `dnr-ui/` export as a second design system
