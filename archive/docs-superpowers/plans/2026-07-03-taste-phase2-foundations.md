# Taste Phase 2: Foundations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the HaTchi-MaXchi foundations — vendored Geist type, server-side Lucide icon registry, focus-ring/state discipline, dark-ramp + WCAG contrast gate — so every fleet app's look moves without touching app code.

**Architecture:** All changes ride the existing token/cascade machinery (`@layer reset, vendor, tokens, base, utilities, components, overrides`; components consume custom properties, so token-level changes propagate fleet-wide). The Icon primitive keeps its API but emits inline SVG from a generated registry, falling back to the current `data-lucide` client path for unknown names. New gates: token-pair WCAG contrast (pure function of the token sheet) and icon-registry drift.

**Tech Stack:** CSS custom properties + OKLCH, Geist/Geist Mono variable woff2 (OFL), Lucide SVG path data (ISC, pinned 0.577.0 to match the vendored UMD bundle), Python registry generation.

**Spec:** `docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md` (Phase 2)
**Baseline evidence:** `dev_docs/taste/baseline-2026-07-02.md` — lever order: craft signals → spacing scale → color ramps; TASTE-1/2/3/5/6/7/9/10/11 are this phase's rules.

## Global Constraints

- Every new CSS file registers in `scripts/build_dist.py` `CSS_SOURCES` (layer, path) and `python scripts/build_dist.py` reruns AFTER the version bump (dist is committed; `tests/unit/test_asset_bundle.py` gates parity).
- Icon registry file is `# AUTO-GENERATED` — edited only via its generation script.
- No new singletons; layer rule `render/` stays pure (registry is data, no I/O).
- Baselines that will churn deliberately: fragment-primitive CSS gate, UX-walk goldens if icon markup changes reach walked pages (icons render inline-SVG only where names are known — unknown → unchanged markup).
- Full suite before ship, no `-k` (IR-drift lesson); `pytest tests/unit -m gate` pre-flight.

---

### Task 1: Vendor Geist + Geist Mono (fleet-wide type in one move)

**Files:**
- Create: `src/dazzle/page/runtime/static/fonts/Geist[wght].woff2`, `GeistMono[wght].woff2`, `fonts/OFL.txt`
- Create: `src/dazzle/page/runtime/static/css/fonts.css` (@font-face, `font-display: swap`)
- Modify: `src/dazzle/page/runtime/static/css/design-system.css` (`--font-sans` — currently names Inter which is NEVER loaded; apps render system-ui today), `tokens.css` (`--font-mono`, tabular-numeral feature setting for data tables)
- Modify: `scripts/build_dist.py` `CSS_SOURCES` (fonts.css in the `vendor` layer, before tokens)

**Steps:** download variable woff2s from the pinned vercel/geist-font release; write @font-face (family "Geist", "Geist Mono", `font-weight: 100 900`, swap); point `--font-sans: "Geist", ui-sans-serif, system-ui, …` and `--font-mono: "Geist Mono", ui-monospace, …`; add `font-feature-settings: "tnum"` on `.dz-table` numeric cells via a token (`--font-numeric: "tnum" 1`); rebuild dist; visual smoke via one example boot + screenshot.

### Task 2: Icon registry generation (server-side SVG, TASTE-6)

**Files:**
- Create: `scripts/taste/gen_icon_registry.py` — fetches pinned `lucide-static@0.577.0` SVGs for the curated set, emits registry
- Create: `src/dazzle/render/fragment/icon_registry.py` (`# AUTO-GENERATED`, `ICONS: dict[str, str]` name → inner SVG markup, `LUCIDE_VERSION`, ISC license header)
- Test: `tests/unit/test_icon_registry_drift.py` (gate marker)

**Curated set (~140):** navigation/layout (layout-dashboard, home, menu, panel-left, settings, …), actions (plus, pencil, trash-2, search, filter, download, upload, copy, check, x, refresh-cw, log-out, external-link, …), status (circle-check, circle-alert, triangle-alert, info, circle-x, clock, loader-circle, …), objects (file-text, folder, users, user, building-2, package, inbox, mail, phone, calendar, tag, credit-card, receipt, shield, key-round, database, server, globe, image, paperclip, …), data (chart-bar, chart-line, chart-pie, trending-up, trending-down, table, list, kanban, …), arrows/chevrons (all 4 chevrons + arrows, arrow-up-right, …), misc (star, heart, eye, eye-off, lock, unlock, bell, sun, moon, zap, sparkles, help-circle, …).

**Drift gate:** registry parses, every value is a well-formed `<path|<circle|<rect|<polyline|<line|<polygon` fragment, `LUCIDE_VERSION == "0.577.0"`, name list matches the generator's manifest constant, all keys kebab-case sorted.

### Task 3: Icon primitive → inline SVG emission

**Files:**
- Modify: `src/dazzle/render/fragment/renderer/_render_layout.py:227` `_emit_icon`
- Modify: `src/dazzle/render/fragment/renderer/_render_tables.py:546,1140` (action-card + nav `data-lucide` sites: registry-hit → inline SVG, miss → existing `data-lucide` span, byte-identical fallback)
- Modify: `src/dazzle/page/runtime/static/css/components/fragment-primitives.css` (`.dz-icon svg` sizing on the type scale)
- Test: `tests/unit/test_icon_inline_svg.py`

**Emission (known name):**
```html
<span class="dz-icon dz-icon--size-md" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">…paths…</svg></span>
```
Unknown name: current markup unchanged (client Lucide hydrates it) — zero-risk rollout; the drift gate reports fallback names seen in examples so the set grows deliberately.

### Task 4: Focus-ring + interactive-state tokens (TASTE-1)

**Files:**
- Modify: `tokens.css` (`--focus-ring: 0 0 0 2px …accent 40% alpha`, `--focus-ring-offset`), `base.css` (universal `:focus-visible` ring), `button.css`/`form.css` (consume tokens; press/active feedback per TASTE-2 shadows)
- Test: extend `tests/unit/test_fragment_primitive_css.py`-adjacent CSS assertions only if cheap; primary oracle is the panel.

### Task 5: WCAG contrast gate over token pairs (TASTE-11)

**Files:**
- Create: `tests/unit/test_token_contrast_wcag.py` (gate marker) — parses `tokens.css` custom properties, resolves `light-dark()` pairs, converts OKLCH→sRGB (self-contained math, no new deps), asserts WCAG AA (4.5:1) for: text/bg, text/surface, text-muted/bg (3:1 large-text floor), brand-contrast/brand, danger/success/warning-on-soft pairs — both themes.
- Fix any failing token values in `tokens.css`/`design-system.css` (dark ramp recalibration is expected — TASTE-7).

### Task 6: Rebuild, gates, bump, ship, mini-panel

- `python scripts/build_dist.py`; `pytest tests/unit -m gate`; full suite `-n auto`; ruff/mypy; CHANGELOG (### Agent Guidance: icon names resolve server-side from `icon_registry.py`; add names via `scripts/taste/gen_icon_registry.py`); `/bump patch`; `/ship`.
- Evidence check (not the full Phase 4 gate): re-capture `ops_dashboard` + `design_studio` (light+dark, above-fold), re-judge those ~12 screens against the same references via the CC-subagent protocol, and record movement vs baseline in `dev_docs/taste/phase2-check-2026-07.md`. Expect movement on typographic_hierarchy (Geist actually loading) and perceived_craft (icons+focus+shadows); full convergence is Phase 3/4's job.
