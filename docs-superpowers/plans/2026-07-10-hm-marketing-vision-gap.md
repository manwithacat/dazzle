# HM marketing-vision gap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the residual HM marketing-vision gap (#1565) — lift `cta_prominence` (6→8) and `finish_polish` (7→8+) — with delegated HM CSS, keeping the deterministic hygiene floor green.

**Architecture:** All work is CSS in HaTchi-MaXchi. Structure lives in `packages/hatchi-maxchi/components/sitespec.css`; per-family accent/flavor lives in each family's marketing-reflavor block (`packages/hatchi-maxchi/families/*.css`). New tokens get defaults in `packages/hatchi-maxchi/base/design-system.css`. Nothing is app-side. The example `examples/llm_ticket_classifier/sitespec.yaml` already declares hero + features + cta sections, so no content changes are needed — only styling.

**Tech Stack:** CSS custom properties (oklch/hsl), the HM build (`scripts/build_dist.py`), the on-subscription vision pilot (Playwright capture + agent-as-judge against `src/dazzle/core/sitespec_vision_rubric.py`).

## Global Constraints

- **Delegated design only** — all CSS stays in HM (`packages/hatchi-maxchi/…`). No app-side CSS, no renderer/DSL changes.
- **HM owns source; Dazzle serves** — after editing HM CSS, rebuild with `python scripts/build_dist.py` (regenerates the served dist + theme families). The dist is drift-gated; the ux-catalogue (`tests/unit/test_ux_catalogue.py`) globs HM CSS and must stay current.
- **Hygiene floor** — `tests/unit/test_sitespec_hygiene.py` (score 97.2, floor 90) must stay green after every change.
- **Measurement is fold-only** — the vision pilot captures the 1440×1024 hero fold (`full_page=False`). Below-fold changes (the CTA band) are real UX but do not move the score.
- **Feature cards use `.dz-feature-item`** (features section, in the fold), NOT `.dz-card-item` (card-grid section). Mirror finish changes to both for consistency, but the score-mover is `.dz-feature-item`.
- **Ship discipline** — `/bump patch`, clean worktree, hold the `.dazzle/improve.lock` across ship, `mypy`/`ruff`/gate green (no src changes here, but the drift gates apply).

---

### Task 1: Feature-card + icon finish (Part B — above-fold, moves the score)

**Files:**
- Modify: `packages/hatchi-maxchi/base/design-system.css` (site-section token block, ~L83-101 — refine `--dz-shadow-card`, add `--dz-card-border`, `--dz-card-shadow-hover`, `--dz-card-icon-ring`)
- Modify: `packages/hatchi-maxchi/components/sitespec.css` (`.dz-feature-item` L1023-1031, `.dz-feature-icon` L1049-1060; mirror to `.dz-card-item` L294-306, `.dz-card-icon` L323-334)
- Modify: `packages/hatchi-maxchi/families/expressive.css` (marketing block ~L104-139 — accent card border/icon tint)

**Interfaces:**
- Produces tokens later tasks/families reflavor: `--dz-shadow-card`, `--dz-card-shadow-hover`, `--dz-card-border`, `--dz-card-icon-ring`.

- [ ] **Step 1: Refine/add the card-finish tokens (design-system.css defaults)**

In the `/* --- Site section tokens (marketing pages) --- */` block of `packages/hatchi-maxchi/base/design-system.css`, replace the flat card shadow default and add the new tokens:

```css
  /* Card finish (features / cards / testimonials) — families reflavor */
  --dz-shadow-card: 0 1px 2px oklch(0 0 0 / 0.04), 0 8px 20px -10px oklch(0 0 0 / 0.14);
  --dz-card-shadow-hover: 0 2px 4px oklch(0 0 0 / 0.06), 0 20px 36px -14px oklch(0 0 0 / 0.22);
  --dz-card-border: 1px solid oklch(0 0 0 / 0.06);
  --dz-card-icon-ring: inset 0 0 0 1px oklch(0 0 0 / 0.06);
```

(If `--dz-shadow-card` is already declared elsewhere in this block, replace that line; otherwise add all four.)

- [ ] **Step 2: Apply the finish to `.dz-feature-item` (and mirror `.dz-card-item`)**

In `packages/hatchi-maxchi/components/sitespec.css`, update the feature-item rule (L1023) and its hover (L1032):

```css
.dz-feature-item,
.dz-testimonial-item {
  background: var(--dz-surface-card);
  padding: var(--dz-spacing-card-padding, 1.5rem);
  border: var(--dz-card-border);
  border-radius: var(--dz-radius-card, 0.75rem);
  box-shadow: var(--dz-shadow-card);
  transition: transform var(--dz-transition-fast, 150ms), box-shadow var(--dz-transition-fast, 150ms),
              border-color var(--dz-transition-fast, 150ms);
}

.dz-feature-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--dz-card-shadow-hover);
  border-color: color-mix(in oklab, var(--dz-hero-bg-from) 35%, transparent);
}
```

Apply the identical three additions (`border`, refined `box-shadow`, hover `box-shadow`/`border-color`, `translateY(-2px)`) to `.dz-card-item` (L294) and `.dz-card-item:hover` (L305).

- [ ] **Step 3: Craft the icon container (`.dz-feature-icon` + `.dz-card-icon`)**

In `packages/hatchi-maxchi/components/sitespec.css`, add a ring + subtle gradient to the icon tiles (L1049 and L323):

```css
.dz-feature-icon {
  width: 3rem;
  height: 3rem;
  background: var(--dz-feature-icon-bg, oklch(0.92 0.03 260));
  border-radius: 0.625rem;
  box-shadow: var(--dz-card-icon-ring);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
  color: var(--dz-hero-bg-from);
}
```

Apply the same `border-radius: 0.625rem;` + `box-shadow: var(--dz-card-icon-ring);` additions to `.dz-card-icon` (L323).

- [ ] **Step 4: Expressive family — accent the icon tint (marketing block)**

In `packages/hatchi-maxchi/families/expressive.css` marketing block (light ~L133, dark ~L196), the `--dz-feature-icon-bg` already carries the violet tint. Add a slightly stronger card-border accent so expressive cards read crafted. In the light block add:

```css
    --dz-card-border: 1px solid oklch(0.55 0.10 300 / 0.14);
```

and in the dark block add:

```css
    --dz-card-border: 1px solid oklch(0.75 0.10 300 / 0.18);
```

- [ ] **Step 5: Rebuild the dist**

Run: `python scripts/build_dist.py`
Expected: `generated N HM aesthetic-family theme(s)` + dist table; no errors.

- [ ] **Step 6: Hygiene floor stays green**

Run: `python -m pytest tests/unit/test_sitespec_hygiene.py -q`
Expected: PASS (score ≥ 90; still ~97).

- [ ] **Step 7: Commit**

```bash
git add packages/hatchi-maxchi/base/design-system.css packages/hatchi-maxchi/components/sitespec.css packages/hatchi-maxchi/families/expressive.css src/dazzle/page/runtime/static/
git commit -m "hm-sitespec: feature-card finish — border, depth, hover-lift, icon ring (#1565 B)"
```

---

### Task 2: Hero CTA button prominence (Part A — above-fold, moves the score)

**Files:**
- Modify: `packages/hatchi-maxchi/base/design-system.css` (add `--dz-cta-*` tokens)
- Modify: `packages/hatchi-maxchi/components/sitespec.css` (`.dz-section-hero .btn-primary` L811-819, `.btn-secondary/.btn-outline` L822-834)
- Modify: `packages/hatchi-maxchi/families/expressive.css` (marketing block — CTA glow)

**Interfaces:**
- Consumes: `--dz-hero-bg-from`, `--dz-hero-btn-hover` (existing).
- Produces: `--dz-cta-fill`, `--dz-cta-text`, `--dz-cta-fill-hover`, `--dz-cta-shadow`, `--dz-cta-shadow-hover` (reused by Task 3's band button).

- [ ] **Step 1: Add the CTA tokens (design-system.css)**

In the site-section token block:

```css
  /* Marketing CTA buttons — families reflavor (glow) */
  --dz-cta-fill: white;
  --dz-cta-text: var(--dz-hero-bg-from);
  --dz-cta-fill-hover: var(--dz-hero-btn-hover, oklch(0.98 0 0));
  --dz-cta-shadow: 0 6px 20px -8px oklch(0 0 0 / 0.35);
  --dz-cta-shadow-hover: 0 12px 28px -8px oklch(0 0 0 / 0.45);
```

- [ ] **Step 2: Make the hero primary CTA confident (sitespec.css)**

Replace `.dz-section-hero .btn-primary` (L811) and its hover (L817):

```css
.dz-section-hero .btn-primary {
  background: var(--dz-cta-fill);
  color: var(--dz-cta-text);
  border: none;
  font-weight: 700;
  font-size: 1.0625rem;
  padding: 0.875rem 1.75rem;
  border-radius: var(--dz-radius-button, 0.5rem);
  box-shadow: var(--dz-cta-shadow);
  transition: transform var(--dz-transition-fast, 150ms), box-shadow var(--dz-transition-fast, 150ms),
              background var(--dz-transition-fast, 150ms);
}

.dz-section-hero .btn-primary:hover {
  background: var(--dz-cta-fill-hover);
  box-shadow: var(--dz-cta-shadow-hover);
  transform: translateY(-1px);
}
```

- [ ] **Step 3: Make the secondary CTA a clear outline (sitespec.css)**

Update `.dz-section-hero .btn-secondary, .dz-section-hero .btn-outline` (L822) to a legible ghost with matching size:

```css
.dz-section-hero .btn-secondary,
.dz-section-hero .btn-outline {
  background: transparent;
  color: white;
  border: 1.5px solid var(--dz-hero-border, oklch(1 0 0 / 0.5));
  font-weight: 600;
  font-size: 1.0625rem;
  padding: 0.875rem 1.75rem;
  border-radius: var(--dz-radius-button, 0.5rem);
  transition: background var(--dz-transition-fast, 150ms), border-color var(--dz-transition-fast, 150ms);
}
```

Keep the existing `:hover` rule (L828) as-is.

- [ ] **Step 4: Expressive family — accent-fill CTA + glow (marketing block)**

In `packages/hatchi-maxchi/families/expressive.css` light marketing block, override the CTA to a bright accent surface with a glow (more confident than plain white on the violet gradient):

```css
    --dz-cta-fill: oklch(0.99 0.01 300);
    --dz-cta-text: oklch(0.42 0.20 300);
    --dz-cta-shadow: 0 6px 22px -6px oklch(0.52 0.24 300 / 0.55);
    --dz-cta-shadow-hover: 0 12px 32px -8px oklch(0.52 0.24 300 / 0.7);
```

- [ ] **Step 5: Rebuild + hygiene + commit**

```bash
python scripts/build_dist.py
python -m pytest tests/unit/test_sitespec_hygiene.py -q
git add packages/hatchi-maxchi/ src/dazzle/page/runtime/static/
git commit -m "hm-sitespec: hero CTA prominence — bold solid primary + ghost secondary + glow (#1565 A)"
```
Expected: build clean; hygiene PASS.

---

### Task 3: Reinforced CTA band styling (Part C — below-fold UX; styling only)

**Files:**
- Modify: `packages/hatchi-maxchi/components/sitespec.css` (`.dz-section-cta` L124-133)
- (No example change — `examples/llm_ticket_classifier/sitespec.yaml` already declares a `cta` section.)

**Interfaces:**
- Consumes: `--dz-hero-bg-from/to`, `--dz-cta-*` (Task 2).

- [ ] **Step 1: Make the CTA band a confident full-width band (sitespec.css)**

Replace `.dz-section-cta` (L124) and add a button rule:

```css
.dz-section-cta {
  padding: var(--dz-spacing-section-y, 5rem) 1.5rem;
  background: linear-gradient(135deg, var(--dz-hero-bg-from) 0%, var(--dz-hero-bg-to) 100%);
  color: white;
  text-align: center;
}

.dz-section-cta h2 {
  font-size: var(--dz-font-size-cta-headline, 3rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  color: white;
}

.dz-section-cta .btn-primary {
  background: var(--dz-cta-fill);
  color: var(--dz-cta-text);
  border: none;
  font-weight: 700;
  font-size: 1.0625rem;
  padding: 0.875rem 1.75rem;
  border-radius: var(--dz-radius-button, 0.5rem);
  box-shadow: var(--dz-cta-shadow);
  transition: transform var(--dz-transition-fast, 150ms), box-shadow var(--dz-transition-fast, 150ms);
}

.dz-section-cta .btn-primary:hover {
  background: var(--dz-cta-fill-hover);
  box-shadow: var(--dz-cta-shadow-hover);
  transform: translateY(-1px);
}
```

Check the `[data-theme="dark"] .dz-section-cta` rule (~L543) still reads correctly against the gradient; adjust only if it forces a conflicting background.

- [ ] **Step 2: Rebuild + hygiene + commit**

```bash
python scripts/build_dist.py
python -m pytest tests/unit/test_sitespec_hygiene.py -q
git add packages/hatchi-maxchi/components/sitespec.css src/dazzle/page/runtime/static/
git commit -m "hm-sitespec: reinforced CTA band — gradient band + prominent button (#1565 C)"
```

---

### Task 4: Vision measurement, human sign-off, ship & close

**Files:** none (measurement + release).

- [ ] **Step 1: Boot the example with the expressive family**

```bash
(cd examples/llm_ticket_classifier && DAZZLE_OVERRIDE_THEME=expressive nohup dazzle serve --local --port 3625 > /tmp/vg_serve.log 2>&1 &)
```
Wait for HTTP 200 on `http://localhost:3625/`. (Note: `serve --local` was removed — use `dazzle serve` with `DATABASE_URL`/`REDIS_URL` set, or `DAZZLE_SKIP_INFRA_CHECK=1` for a quick UI-only boot. Use whatever the current serve contract requires.)

- [ ] **Step 2: Capture the 1440×1024 fold**

Playwright capture to `/tmp/vg_after.png` (viewport 1440×1024, `full_page=False`), and a `full_page=True` capture to `/tmp/vg_full.png` so the reinforced CTA band is visible for the human review.

- [ ] **Step 3: Judge the fold against the rubric**

Read `/tmp/vg_after.png` and score against `SITESPEC_VISION_DIMENSIONS` (`src/dazzle/core/sitespec_vision_rubric.py`). Target: `cta_prominence` 6→8, `finish_polish` 7→8+, avg ~7.1 → ~8. If a dimension didn't move, tune the Task 1/2 token values (shadow depth, CTA fill/size/glow) and re-run Steps 1-3. Iterate until the targets are hit or clearly plateaued.

- [ ] **Step 4: Human aesthetic sign-off**

Send `/tmp/vg_after.png` (fold) + `/tmp/vg_full.png` (full page, showing the CTA band) to the user with the before/after vision numbers. Wait for approval before closing.

- [ ] **Step 5: Ship**

`/bump patch`; ensure the HM dist is rebuilt + committed (clean worktree); commit the CHANGELOG (Fixed: closed the #1565 marketing-vision gap — CTA prominence + feature-card finish, vision score ~7.1 → ~X); push; tag; monitor CI green; release the lock.

- [ ] **Step 6: Close #1565**

Comment with the before/after vision numbers + the shipped version; `gh issue close 1565`; emit the `fix-deployed` signal.

---

## Self-Review

**Spec coverage:** Part A (hero CTA) → Task 2. Part B (feature-card finish) → Task 1. Part C (reinforced CTA band) → Task 3 (styling only; example already declares the section). Measurement + hygiene floor + dist rebuild + human sign-off → Task 4 + each task's gate. All spec sections covered.

**Placeholder scan:** every CSS step carries the actual declarations; the one judgment latitude (token value tuning) is explicit in Task 4 Step 3 as a measured iteration loop, not a placeholder.

**Type/selector consistency:** tokens introduced in Task 1 (`--dz-shadow-card`, `--dz-card-*`) and Task 2 (`--dz-cta-*`) are reused by name in Task 3. Feature cards target `.dz-feature-item` (the in-fold class) with `.dz-card-item` mirrored — consistent with the exploration finding.
