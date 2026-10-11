# HaTchi-MaXchi Tranche 1 — every-screen components

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Inline execution; gates per slice.

**Goal:** The six components that appear on (or one click from) every screen, each passing the "familiar, not identical" review test, plus the dark empty-state contrast nit.

**Spec:** `docs/superpowers/specs/2026-07-03-hatchi-maxchi-standalone-design.md`

1. **`dz-alert`** — tone wash + registry icon + title/description (identity signals #2/#3). New `components/alert.css`; contract markup:
   `<div class="dz-alert" data-dz-tone="warning" role="alert"><span class="dz-alert__icon">{svg}</span><div class="dz-alert__body"><div class="dz-alert__title">…</div><div class="dz-alert__description">…</div></div></div>`
2. **Selection controls** — designed checkbox/radio/switch on native inputs (`appearance:none`, tokens, focus ring, `:checked` accent). form.css additions: `.dz-checkbox`, `.dz-radio`, `.dz-switch`.
3. **`data-dz-tooltip`** — CSS-only attribute tooltip (::after, token-styled, reduced-motion safe, `prefers-reduced-motion` honoured; pair with aria-label at emit sites).
4. **`dz-separator`** — horizontal/vertical rule on tokens.
5. **`dz-menu`** — generic dropdown as `<details class="dz-menu">` (hypermedia answer: no JS for open state; light JS for click-outside/Esc close shared with existing patterns). Contract + CSS; column menu adoption deferred to tranche 2.
6. **`dz-alert-dialog` + `dz-confirm.js`** — the flagship: intercept `htmx:confirm`, render a designed `<dialog>` (icon, title, message, destructive-styled confirm), `issueRequest()` on accept. Every existing `hx-confirm` in the fleet upgrades automatically — zero emitter changes.
7. **Nit:** `.dz-empty-state__title` dark contrast (title must use `--colour-text`).

Each: CSS registered in the 3 lists, `test_hm_tranche1.py` (bundle carries the rules; dz-confirm wired into JS_SOURCES), dist rebuild, gate suite, full suite, specimen regenerated with the new components, ship, mini-panel spot-check on one app.
