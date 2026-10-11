# Taste Phase 3: Component Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the Phase 2 foundations to work at the component seams the judges actually see — nav icons, designed empty states, SVG badge glyphs, registry row-action icons, card/button craft — so content-light screens (the Phase 2 check's residue) move.

**Architecture:** Markup changes concentrate at five seams, all already recon'd to exact lines. Icons come only from the vendored registry via `lucide_icon_html` (TASTE-6). Golden churn is deliberate and re-baselined per slice (data_row_char_1505 snapshots, #1493 badge tests, nav primitive tests). Card-safety invariants + viewport-geometry gates must stay green — no grid-geometry spacing changes this phase (the #1494 lesson); the spacing sweep waits for judged evidence that it's still the binding constraint.

**Spec:** `docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md` (Phase 3)
**Evidence:** `dev_docs/taste/phase2-check-2026-07.md` — foundations move dense screens; empty/content-light screens need the seams below.

## Global Constraints

- Icons only via `dazzle.render.fragment.icon_html.lucide_icon_html` (registry hit → inline SVG; miss → client fallback). New icon names go through `scripts/taste/gen_icon_registry.py`.
- Card-safety invariants (8+1) green throughout; no region grid-geometry changes.
- Dist rebuild after the last slice; full suite (no `-k`); walks re-baselined only where markup deliberately changed.

### Slice 1 — Nav icons everywhere (TASTE-6/craft)

- Create `src/dazzle/render/fragment/nav_icons.py`: pure `infer_nav_icon(label: str) -> str` — lowercase keyword map (dashboard/overview→layout-dashboard, task→list-checks, ticket→ticket, user/people/team/member→users, setting/admin/config→settings, health/status→gauge, deploy/release→rocket, report/analytic→chart-bar, billing/invoice/payment→receipt, asset/file/document→file-text, project→kanban, work→briefcase, feedback→message-square, mail/inbox/message→inbox, calendar/schedule→calendar, order/product/inventory/package→package, approval→badge-check, audit/log/history→history, security/permission/role→shield, brand→tag, campaign→target, contact→users, class/course→book-open, …) with fallback `"list"`. Every returned name MUST be in the registry (unit-asserted).
- `_render_shell.py` NavItem/NavGroup emit: `n.icon or infer_nav_icon(n.label)` → `lucide_icon_html(..., cls="dz-nav-link__icon")` (replaces the dead `data-dz-icon` span; authored icons keep working and now actually render).
- CSS: `.dz-nav-link__icon`/`.dz-nav-group__icon` sizing (1rem, muted → currentColor on active/hover).
- Tests: new `test_nav_icons.py` (inference map total, registry-membership); update `test_navigation_primitives.py` icon assertions.

### Slice 2 — Designed empty states (TASTE-8)

- `EmptyState` primitive gains `icon: str = "inbox"`; emitter renders `lucide_icon_html(e.icon, cls="dz-empty-state__icon")` above the title.
- The region/list empty seams (list_handlers `htmx_empty_message`, workspace region empty) upgrade from a bare `<p>` to the EmptyState shape (icon + one sentence; keep the author's `empty_message` verbatim as the sentence). Display-kind default icons: list/table→inbox, chart/metrics→chart-bar, calendar→calendar, kanban→kanban, search→search.
- CSS: `.dz-empty-state__icon` (2rem, muted). Existing `dz-empty-state` block styling reused.
- Watch: the #1494 when_empty machinery (collapse/suppress) sits at the same seam — message-mode only gets the upgrade; collapse/suppress behavior untouched.

### Slice 3 — Badge glyphs → registry SVGs (TASTE-6, supersedes #1493 entities)

- `render/filters.py badge_icon_html`: tone → registry icon (success→circle-check, warning→triangle-alert, destructive→circle-x, info→info) rendered inline via `lucide_icon_html(cls="dz-badge-icon")`; neutral stays empty (byte-stable).
- CSS: `.dz-badge-icon svg` sizing (0.75em, aligned).
- Update `test_badge_wcag_icon_1493.py` glyph assertions (entities → SVG presence); WCAG non-colour-channel guarantee unchanged.

### Slice 4 — Row-action icons from the registry

- `_data_row.py` View/Edit/Delete: replace the three hand-drawn 14px SVGs with `lucide_icon_html` (eye, pencil, trash-2); wrapper classes unchanged (`dz-tr-action`, `is-destructive`), aria-labels unchanged.
- CSS: `.dz-tr-action svg { width: 0.875rem; height: 0.875rem; }`.
- Re-baseline `__snapshots__/data_row_char_1505/*.html` deliberately (find the regen mechanism in `test_data_row_characterization_1505.py` first).

### Slice 5 — Card + button craft (TASTE-2/10)

- `.dz-card`: `box-shadow: var(--shadow-sm)` at rest (border stays); hover already transitions.
- `.dz-button-primary`: replace `filter: brightness(1.1)` hover with explicit `background: var(--brand-700)`; add `:active` press (`translateY(0.5px)` + shadow-none); subtle rest shadow `--shadow-sm` on primary only. Reduced-motion safe (transform is 0.5px; still gate under prefers-reduced-motion no-transform rule already global in htmx-states.css — verify).

### Ship + evidence

- `build_dist.py`, gate suite, full suite, walks; CHANGELOG (+Agent Guidance), `/bump patch`, `/ship`.
- Mini-panel re-judge (same two vehicles + references, CC-subagent protocol) → append movement to `dev_docs/taste/phase2-check-2026-07.md` (Phase 3 section) or new `phase3-check` doc. Full-fleet Phase 4 judgment remains separate.
