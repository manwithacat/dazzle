# Playbook: compose or refuse

**Goal:** As an L2 host, either embed an L1 correctly or declare a local primitive.
**Open when:** Building/editing grid, shell, toolbar, form chrome, or any composite.
**Stem:** `docs/decisions/0003-composition-declared.md`

## Steps

1. List every child interaction the host needs (job + lifetime + exchange).
2. For each, run `pick-a-surface.md` → candidate L1.
3. Ask: can this host **mount** that L1 without breaking morph, density, or commit?

### If yes — compose

1. Embed markup that satisfies the **child’s** DOM contract (or load via exchange).
   - Overlay hosts: pick **form_shell** vs **exchange_shell** first
     (`stems/host-chrome-symmetry.md`). Body colour stays primary so guests
     inherit correctly.
   - Peek vs full page vs expand are three jobs: fragment into the body,
     `<a href>` to the owned record URL, and Expand/Restore
     (`data-dz-drawer-expand`, resting width ↔ `xl`) — never one dead
     button for all three, never a multi-step “Widen” cycle.
   - **Demo must exercise behaviour:** scrollable hosts need overflowing
     content; toggles must flip observable state (see
     `stems/host-chrome-symmetry.md` › *Demos must exercise the behaviour*).
   - Do not invent almost-DOM (e.g. `input.dz-switch` for the Switch
     Hyperpart; legend inside `dz-toggle-group`; `form-field` as read-only
     meta). Pin with `tools/composition_matrix.py --validate`.
2. Add child id to parent `composes=(…)` in `site/registry.py`.
3. Soft-link via `guidance.composes_with` if agents should discover the child.
4. Parent contract names **host** seams only.
5. Rebuild site packs if guidance changes; run cohesion tests + composition matrix.

### If no — refuse (local primitive)

1. Implement the minimal host-local control (e.g. bare `<select class="dz-inline-edit-select">`).
2. Declare on the parent:

   ```python
   does_not_compose=(
       NonComposition(
           other="combobox",  # the L1 you are not using
           seam="…",          # short seam name
           reason="…",        # density / morph / PUT / …
           require_substrings=("…",),   # prove local primitive still there
           forbid_substrings=("…",),    # block accidental dogfood
           spike="docs/spikes/….md",  # optional promotion path
       ),
   )
   ```

3. Regenerate: `python tools/consumer_map.py --write`
4. Document in guidance seams/pitfalls (generated into agent pack).
5. Do **not** leave refusal as prose-only notes.

## Stop conditions

- Mounting a child “to dogfood” without `composes` → undeclared composition.
- Copying a child’s classes with different attrs → almost-DOM fork.
- Refusing without locks → next agent will wire the child anyway.

## Example (data table / `grid`)

| Job | Outcome |
|-----|---------|
| In-cell enum | **Refuse** combobox → bare select; spike for promotion |
| Toolbar plan filter | Local filter select today; composition with combobox is a separate, lower-risk decision |
| Row bulk delete | **Compose** confirm via `hx-confirm`, not a new modal part |

## Next

- Promotion attempt: spike checklist + dual-lock + behaviour tests
- Mutating either side: `mutate-a-primitive.md`
