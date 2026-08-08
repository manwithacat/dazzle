# Strategy: hyperpart_emitter

**Lane:** `framework-ux` (when `planned_emitter > 0`) or `example-apps` (when product must add `widget=` / `display:`)

**Probe:** `python scripts/improve_example_probes.py --status` → `hyperpart_scenarios` line
**CLI:** `dazzle qa hyperpart-opportunities --app <app> --table`
**Catalogue:** `packages/hatchi-maxchi/docs/agent/hyperpart_scenarios.toml`
**Doctrine:** `docs/superpowers/specs/2026-08-07-hyperpart-emitter-scenario-cognition-design.md`

## When improve forces this

| Residual | force | Action |
|----------|-------|--------|
| `planned_emitter > 0` | `framework-ux hyperpart_emitter` | Domain wants a part with no DSL path yet — ship emitter package |
| `dsl_shapes.planned > 0` | `framework-ux hyperpart_emitter` | **Programme residual** — catalogue still has unfinished first paths (not noise) |
| `author_action` only | soft (not residual_total) | Optional product adopt dig; do not thrash quiet fleets |

**Do honor** `force=framework-ux hyperpart_emitter` when either residual fires.
Do **not** skip shape drain because `planned_emitter=0` — that only means no
domain-fit scanner row; planned catalogue ids (aspect-ratio, carousel, …) still need emitters.
Prefer this over `agent_qa_smoke` when residual_total is shapes-only.

## Emitter package (one PR / dig)

1. **IR / authoring** — `widget=<name>` or `display:<mode>` token accepted by parser.
2. **Runtime** — Fragment primitive + `_emit_*` mounts **HM gallery spine** (dual-lock root).
3. **Pick matrix** — row in `pick-a-surface.md` or `pick-a-work-surface.md`.
4. **Scenario** — catalogue row: `status_if_fit` + scanner; flip planned → live.
5. **Fleet** — `SIGNALS` regex; drop `exempt`; `KNOWN_GAPS` empty after dogfood.
6. **Example home** — one surface declares the verb; unit pin.
7. **Prove** — unit tests + `dazzle qa hyperpart-opportunities` shows `emit_covered`.

## Anti-patterns

- Example densify while hyperpart is still gallery-only (`planned_emitter`).
- Density as new DSL verbs (use presentation matrix).
- Second synonym `display:` for the same job.
- Mounting controls-pill almost-DOM (`input.dz-switch`) instead of `label.dz-switch` + track.

## Reference ship: switch (2026-08-07)

- `widget=switch` → `SwitchField` → `data-dz-switch`
- Dogfood: `examples/simple_task` `user_edit` / `is_active`
- Tests: `test_form_widget_showcase_phase3`, `test_simple_task_switch_emitter`

## Reference ship: accordion (2026-08-08)

- `display: accordion` → `Accordion` → `.dz-accordion` exclusive details
- Dogfood: `examples/simple_task` `admin_dashboard.task_faq`
- Entries: `title` + `body` (or `caption`); first panel open
- Tests: `test_accordion_emitter`

## Reference ship: aspect-ratio (2026-08-08)

- Field/media compose: `logo_url` / `preview_url` / `photo_url` → `.dz-aspect-ratio` + img
- Fragment: `AspectRatio(child=…, ratio="16/9")` → dual-lock `data-dz-ratio` presets
- Dogfood: `design_studio` Brand/Asset media thumbs; `fieldtest_hub` photo_url
- Tests: `test_aspect_ratio_emitter` + media thumb Goal B pins

## Reference ship: breadcrumb (2026-08-08)

- Shell trail: `current_route` + `page_title` → `build_shell_breadcrumb` → `.dz-breadcrumb`
- Fragment: `Breadcrumb(items=(BreadcrumbItem(...), …))` dual-lock nav spine
- Dogfood: every chromed app page (Home → leaf above main)
- Tests: `test_breadcrumb_emitter`
