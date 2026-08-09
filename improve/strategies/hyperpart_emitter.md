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

## Reference ship: bubble (2026-08-08)

- `display: conversation` → stack of `Bubble` → `.dz-bubble` + `data-dz-from`
- Fragment: `Bubble(text=…, from_="in|out")` dual-lock speech shell
- Dogfood: `support_tickets` `live_conversation`; `simple_task` `sample_thread` entries
- Tests: `test_bubble_emitter`

## Reference ship: carousel (2026-08-08)

- `display: carousel` → `Carousel` → `.dz-carousel` + `data-dz-carousel`
- Fragment: `Carousel(slides=(CarouselSlide(...), …))` dual-lock stage strip
- Entries: `title`=alt + `body`/`caption`=image URL; or entity `preview_url`/`logo_url`/`photo_url`
- Dogfood: `design_studio` `brand_desk.asset_carousel`; `simple_task` `sample_gallery`
- Tests: `test_carousel_emitter`

## Reference ship: hover-card (2026-08-09)

- Compose guest (no region verb): person chip + email/role meta → `.dz-hover-card`
- Fragment: `HoverCard(trigger=…, title=…, description=…)` dual-lock preview
- Runtime: `wrap_hover_card_preview` in `user_chip.py` (opt-out `hover_card: false`)
- Dogfood: any `ref User` with loaded email/role (simple_task / support_tickets)
- Tests: `test_hover_card_emitter`

## Reference ship: marker (2026-08-09)

- `display: map` → `MapBoard` of `Marker` → `.dz-marker` pin chrome
- Fragment: `Marker(label=…, tone=…, size=…)` dual-lock; host placement via x/y %
- Vendor-free plan canvas (no tile SDK); status → tone; location/name → label
- Dogfood: fieldtest_hub `device_map`; simple_task `sample_map` static entries
- Tests: `test_marker_emitter`

## Reference ship: master-detail (2026-08-09)

- `stage: dual_pane_flow` + LIST/DETAIL region pair → HM master-detail shell
- Emission: `render_master_detail_shell` → `.dz-master-detail` + `data-dz-master-detail`
- List rows: `dz-master-detail__item` + hx-get into detail pane (not full-page drill)
- Controller: `dz-master-detail.js` owns `aria-current` + keyboard arrows
- Dogfood: contact_manager `contacts` (`contact_list` + `contact_detail`)
- Tests: `test_dual_pane_master_detail` + `test_master_detail_emitter`

## Reference ship: menubar (2026-08-09)

- `menubar: true` on app block → app_config.features → shell mount
- Fragment: `Menubar` / `MenubarMenu` / `MenubarAction` → dual-lock `.dz-menubar`
- Shell: `build_shell_menubar` from nav groups (or File/Edit/View fallback) in topbar leading
- Controller: `dz-menubar.js` exclusive open + outside/Escape dismiss
- Dogfood: design_studio `menubar: true`
- Tests: `test_menubar_emitter`

## Reference ship: message (2026-08-09)

- `display: conversation` → stack of `Message` (each nests `Bubble`) → `.dz-message` + `.dz-bubble`
- Fragment: `Message(bubble=…, author=…, time_label=…, media_label=…)` dual-lock row
- Optional media chip + author/time meta; orientation `data-dz-from` flex-reverses outbound
- Live rows: actor keys + timestamps → meta; `is_internal` → outbound
- Dogfood: support_tickets `live_conversation`; simple_task `sample_thread`
- Tests: `test_message_emitter` (+ bubble pins still nest)


## Reference ship: message-scroller (2026-08-09)

- `display: conversation` → `MessageScroller` of `Message`+`Bubble` → `.dz-message-scroller`
- Fragment: `MessageScroller(messages=…, label=…, size=…)` dual-lock transcript viewport
- `role=log` + `aria-live=polite`; empty affordance; auto-scroll controller deferred
- Dogfood: support_tickets `live_conversation`; simple_task `sample_thread`
- Tests: `test_message_scroller_emitter` (+ message pins nest)

## Reference ship: navigation-menu (2026-08-09)

- Sitespec `layout.nav` → `NavigationMenu` → `.dz-navigation-menu` + `data-dz-navigation-menu`
- Fragment: `NavigationMenu` / `NavigationMenuLink` / `NavigationMenuBranch` / `NavigationMenuGroup`
- Shell: `build_site_navigation_menu` in site chrome (logo + dual-lock IA + CTA/theme)
- Optional mega branches (`details` + `data-dz-layout=mega`); controller exclusive open
- Dogfood: every example sitespec public nav (design_studio Home / Sign In)
- Tests: `test_navigation_menu_emitter`
