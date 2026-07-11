# Playbook: mutate a primitive

**Goal:** Change an existing L1/L2 without silent blast-radius or greenwash CI.
**Open when:** Editing `components/*`, `controllers/*`, `contracts/*` for a shipped part.

## Steps

1. **Identify the part id** (`HYPERPART:` marker or registry).
2. **Open `CONSUMER_MAP.md`** for that id — who embeds, relates, refuses, blueprints.
3. **If dual-lock / DOM / model fields change**, note `CONTRACT_SURFACE.md` will move.
4. Implement the smallest correct change. Prefer shared metrics (e.g. form-input box
   model) over one-off hacks on a single class.
5. **Behaviour:** add or extend package behaviour tests for the regression class
   (e.g. enhance must preserve field box).
6. Rebuild: `python build.py` (and site / monorepo dist as needed).
7. **Regenerate maps when surface or graph changed:**

   ```bash
   python packages/hatchi-maxchi/tools/contract_surface.py --write
   python packages/hatchi-maxchi/tools/consumer_map.py --write
   python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write
   ```

8. Run targeted tests, then package gates.
9. In the PR/commit message: state blast radius (who consumes) in one sentence.

## Stop conditions

- Regenerating maps **only** to silence CI without reading the diff → epistemic failure.
- Changing commit path or lifetime via a new `data-*` mode → open `pick-a-surface.md`
  and `docs/decisions/0002-three-layers.md` instead.
- Touching a refused pair (e.g. grid-edit + combobox markers) without flipping
  `does_not_compose` → CI should fail; do not weaken locks casually.

## Class collisions

Public class names are stems too. Do not reuse a Hyperpart root class for a
different BEM block (historical `.dz-combobox` fragment stack vs combobox root).

## Next

- Host edge changes: `compose-or-refuse.md`
- New part: `invent-safely.md`
