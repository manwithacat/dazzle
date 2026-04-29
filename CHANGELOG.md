# Changelog

All notable changes to DAZZLE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.61.108] - 2026-04-29

### Fixed
- **#936 — same-URL workspace re-click no longer empties the dashboard** —
  clicking the active workspace's sidebar link triggers a same-URL
  morph swap. The per-component `htmx:afterSettle` listener that drove
  re-hydration captured `this` at init time. Whether idiomorph morphed
  the existing `<div x-data>` in place or replaced it, the captured
  `this` could end up pointing at a dead Alpine proxy — mutations to
  `cards` no longer flowed into the rendered `<template x-for>`, so
  the workspace collapsed to zero rendered region cards.

  Re-hydration is now driven by a single global handler in
  `dz-alpine.js` that runs on every `htmx:afterSettle` whose target
  contains `<script id="dz-workspace-layout">`. The handler looks up
  the live Alpine instance via `Alpine.$data(root)` so it always
  finds the current proxy, and calls `_hydrateFromLayout()` on it.
  The per-component listener is gone — eliminates the stale-`this`
  footgun and the listener-stacking risk it carried.

### Agent Guidance
- For Alpine + HTMX morph integrations, **never capture `this` in a
  listener registered from `init()`** — same-URL morph can re-create
  the component root without re-running `init()`/`destroy()`,
  leaving the captured `this` pointing at a dead proxy. Use
  `Alpine.$data(root)` from a single global handler instead.

## [0.61.107] - 2026-04-28

### Fixed
- **#932 — `manifest.storage_defs` now reaches `DazzleBackendApp`** —
  AegisMark hit a wiring gap adopting the v0.61.106 storage primitive:
  the manifest parsed `[storage.<name>]` blocks correctly and
  `_wire_storage_routes()` ran the validator, but the dict never
  travelled from `manifest` → `ServerConfig` → `DazzleBackendApp`,
  so apps with declared storages crashed at startup with
  `Storage validation failed: ... (no [storage.*] blocks declared)`.

  Threaded `storage_defs` through every layer:
  - `ServerConfig.storage_defs` field added
  - `build_server_config(..., storage_defs=...)` keyword
  - `run_unified_server(..., storage_defs=...)` keyword + kwarg in
    `UnifiedServerConfig`
  - `run_backend_only(..., storage_defs=...)` keyword
  - `_serve_combined` and `_serve_backend_only` now pass
    `mf.storage_defs` from the loaded manifest
  - `DazzleBackendApp.__init__` falls back to `config.storage_defs`
    when the kwarg is `None` (matches every other field's precedence)

  6 regression tests in `test_storage_cycle3.py` cover the full
  manifest → config → builder propagation chain.

## [0.61.106] - 2026-04-29

### Added
- **Storage primitive cycle 3: validator + auto-routes** — third
  installment of #932. Closes the loop on the upload-ticket path:
  authors can now declare `[storage.<name>]` blocks in `dazzle.toml`,
  bind file fields via `field foo: file storage=<name>`, and the
  framework auto-generates `POST /api/{entity}/upload-ticket` for
  every entity with at least one bound field.

  - **Validator**: `validate_storage_refs(appspec, storage_defs)` —
    fails fast at server startup if any `field.storage` reference
    doesn't resolve to a declared block. Errors list every available
    storage name to help debug typos. Warns when `storage=` is
    applied to a non-`file` field (parser allows it; validator
    flags it).
  - **`register_upload_ticket_routes(app, appspec, registry)`** —
    walks every entity, registers `POST /api/{entity}/upload-ticket`
    for entities with `file storage=...` fields. Single-field
    entities use a direct handler; multi-field entities use a
    dispatcher that reads `body["field"]` to pick the binding.
    Defaults to first-declared field when omitted.
  - **Server startup wiring** — `DazzleBackendApp.__init__`
    accepts a new `storage_defs` kwarg. Validation runs before
    route registration; missing env vars / unresolved references
    raise loud `RuntimeError` with the offending `[storage.<name>]`
    name in the message.
  - **Per-request behaviour**: handler authenticates via #933's
    `current_user_id`, sanitises filename (path traversal +
    non-ASCII), validates content-type against the declared
    allowlist, generates a UUID `record_id`, calls
    `provider.render_prefix` + `provider.mint_upload_ticket`,
    returns `{record_id, s3_bucket, s3_key, upload: {url, fields},
    max_bytes, expires_in_seconds}`. Returns 401 / 400 / 503 / 500
    based on the failure class.

  14-test suite (`test_storage_cycle3.py`) covers validator
  correctness (valid pass, unresolved error, available-list hint,
  non-file warn, no-storage no-op), route registration (single +
  multi-field + entity-without-storage), and end-to-end request
  handling with `FakeStorageProvider` (auth gate, ticket minting,
  filename sanitisation, content-type allowlist, unconfigured
  storage 503, multi-field dispatcher, unknown-field 400).

### Agent Guidance
- The framework auto-generates upload-ticket routes; **finalize
  is project-side for v1**. The clean pattern is ~30 lines:
  ```python
  # routes/cohort_finalize.py
  from dazzle_back.runtime.auth import current_user_id, require_auth
  from dazzle_back.runtime.storage import StorageRegistry  # accessible via app state

  @require_auth(roles=["teacher"])
  async def handler(request, auth):
      user_id = str(auth.user.id)
      body = await request.json()
      registry: StorageRegistry = request.app.state.storage_registry
      provider = registry.get("cohort_pdfs")
      meta = provider.head_object(body["s3_key"])
      if meta is None:
          return JSONResponse({"error": "not uploaded"}, status_code=404)
      # validate body, INSERT row, return id
  ```
  Cycle 4 evaluates whether finalize can be auto-generated cleanly
  enough to ship; for now keep finalize bespoke.
- Default backend is `s3`. Other backends (R2, MinIO, GCS) plug in
  via `endpoint_url` on `[storage.<name>]` — no S3Provider subclass
  needed for v1. New backends slot in by extending
  `StorageRegistry._build_from_config`.

## [0.61.105] - 2026-04-29

### Added
- **Storage primitive cycle 2: runtime providers + registry** — second
  installment of #932. Now ships the runtime layer that cycle 3's
  upload-ticket / finalize routes will hang off:

  - **`S3Provider(StorageProvider)`** wrapping `boto3.client("s3")`'s
    `generate_presigned_post` and `head_object`. Honours
    `[storage.<name>] endpoint_url` for R2 / MinIO / LocalStack
    routing per-storage; falls back to `aws_config.endpoint_url`
    when not set. Encodes `content-length-range` constraint up to
    `max_bytes` and a `Content-Type` lock on the policy.
  - **`FakeStorageProvider`** in `dazzle_back.runtime.storage.testing`
    — in-memory dict-backed implementation. Exposes the same
    protocol surface plus test-only `put_object`, `objects()`, and
    `reset()`. Tests construct one directly — no fixtures, no
    environment, no boto3.
  - **`StorageRegistry`** mapping storage name → provider. Lazy
    construction (boto3 client only built on first use) and a
    `register_provider(name, provider)` injection point so the
    route generator can swap a `FakeStorageProvider` in for tests.
    `${VAR}` env-var interpolation on `bucket` / `region` /
    `endpoint_url` runs at provider-build time with loud-on-missing
    `EnvVarMissingError`.

  46-test suite (`test_storage_cycle1.py` + `test_storage_cycle2.py`)
  covers FakeStorageProvider behaviour, registry lifecycle (lazy
  construction, override-registration, env-var resolution, missing-
  storage errors), and S3Provider via both a stub client (fast unit
  tests with no boto3) and **moto** (real boto3 surface — signing
  math, content-length-range encoding, 404→None). Adds a new
  `[aws-test]` extra pulling `moto[s3]>=5.0` for projects + CI.

### Agent Guidance
- For unit tests that need an upload primitive, use
  `from dazzle_back.runtime.storage import FakeStorageProvider`.
  For integration tests that exercise the real boto3 surface,
  install with `pip install -e ".[dev,aws-test]"` and use moto's
  `mock_aws()` context manager around a `boto3.client("s3")` you
  pass into `S3Provider(cfg, client=client)`.
- The route generator (cycle 3) will get a `StorageRegistry` from
  the manifest at server startup. To inject a fake in tests,
  `registry.register_provider(name, FakeStorageProvider(...))`
  before the request. The registry caches providers, so the
  registration must happen before the first `registry.get(name)`.

## [0.61.104] - 2026-04-29

### Added
- **Storage primitive cycle 1: DSL + config + protocol** — first
  installment of #932 (built-in S3 upload primitive). Cycle 1 lays
  the foundations with no runtime / boto3 dependency change. Authors
  can now declare storage targets in `dazzle.toml` and bind file
  fields to them in DSL; routes + S3 implementation land in cycle 2.

  **`dazzle.toml`** — new `[storage.<name>]` blocks:

      [storage.cohort_pdfs]
      backend = "s3"
      bucket = "${S3_BUCKET}"            # ${VAR} interpolation
      region = "${AWS_REGION}"
      endpoint_url = "${S3_ENDPOINT_URL}"  # optional — R2/MinIO/LocalStack
      prefix = "production/{user_id}/{record_id}/"
      max_bytes = 200_000_000
      content_types = ["application/pdf"]
      ticket_ttl_seconds = 600

  **DSL** — new `storage=<name>` field attribute:

      entity Doc:
        source_pdf_url: file storage=cohort_pdfs

  **Protocol** — `dazzle_back.runtime.storage.StorageProvider`
  Protocol with four methods (`render_prefix`, `mint_upload_ticket`,
  `head_object`) + `UploadTicket` / `ObjectMetadata` value types.
  Cycle-2 backend implementations (real S3, in-memory fake) satisfy
  this interface. Tight surface chosen so MinIO / R2 / GCS slot in
  via 50-line subclasses.

  **Env-var interpolation** — `interpolate_env_vars` /
  `extract_env_var_refs` helpers with loud-on-missing semantics.
  Mirrors the `env("KEY")` pattern already used by `AuthSpec.credentials`.

  Regression tests in `tests/unit/test_storage_cycle1.py` (24
  cases) cover toml parsing, env-var interpolation,
  protocol shape, DSL parser binding, and the FrozenInstanceError
  immutability invariant on the value types. Snapshots refreshed for
  the new optional `FieldSpec.storage` IR field (purely additive,
  defaults to None).

### Agent Guidance
- Storage config is `dazzle.toml`-only — explicitly NOT a top-level
  DSL block. Treat storage as deployment configuration, not domain.
- The `${VAR}` interpolation pattern fails LOUDLY when a referenced
  env var is missing. No silent empty-string fallback. New
  `EnvVarMissingError` carries the var name + context for clear
  diagnostics.
- `StorageProvider` Protocol is `runtime_checkable` — `isinstance(x,
  StorageProvider)` works. Cycle 2's S3 impl + in-memory fake will
  both satisfy it without inheritance.

## [0.61.103] - 2026-04-28

### Fixed
- **`runtime/workspace_rendering.py`** — closes #935 (framework-side
  hardening). The two `repo.list` exception handlers in the
  workspace-region path previously logged at `WARN` and rendered an
  empty result. AegisMark hit this as a 6-cycle debugging puzzle when
  a hand-rolled migration left `CohortAssessment.uploaded_by` as
  `varchar` while `User.id` was `uuid` — the Postgres
  `varchar = uuid` cross-type comparison errors out, but the
  framework swallowed the error and silently returned 0 rows.
  Meanwhile the entity-list path (`/app/<entity>`) succeeded because
  it stringifies `current_user` before the comparison.
  Bumped both swallow-sites to `logger.error(...)` with structured
  fields (`entity=... region=... exc=<ExceptionClass>`) so production
  log filters surface the underlying cause on first occurrence. The
  fail-closed security semantics from #546 are preserved — the
  region still renders empty, never an unscoped fallback. Regression
  tests in `tests/unit/test_workspace_region_error_visibility.py`
  pin the absence of the old WARN message, the structured ERROR
  log + exception-class capture, and the unchanged "Do NOT fall back
  to unfiltered queries" anchor comment.

### Agent Guidance
- When swallowing an exception inside a fail-closed render path, log
  at `ERROR` with structured fields (entity name, region name,
  `type(exc).__name__`). `WARN` hides errors below most prod log
  filters and the silent-failure pattern wastes engineer time.

## [0.61.102] - 2026-04-28

### Added
- **DSL: companion regions on create/edit surfaces (Part D of #918)** —
  closes #923. New top-level surface block declares read-only panels
  rendered alongside the form at one of three positions:

      surface ingestion_create "Upload":
        uses entity IngestionBatch
        mode: create
        layout: single_page

        companion summary "Batch summary" position=top:
          eyebrow: "Live"
          display: summary_row
          aggregate:
            pages: max(page_count)
            strands: count(AssessmentObjective)

        section automation "Automation":
          field auto_run_marking "Run AI marking after attribution"

        companion job_plan "What this upload creates" position=below_section[automation]:
          display: status_list
          entries:
            - title: "Classify the batch"
              caption: "Match paper, subject, year group"
            - title: "Separate the PDF"
              caption: "Pages become individual student manuscripts"

  v1 ships declarative display modes (`summary_row`, `status_list`,
  `pipeline_steps`) end-to-end. Source-bound companions
  (`source: Entity` + `filter:`) parse cleanly and render as a
  placeholder pending the form-renderer→workspace-region pipeline
  integration. New IR types: `CompanionSpec`, `CompanionPosition`
  (top / bottom / below_section), `CompanionEntrySpec`,
  `CompanionStageSpec`. New context types: `CompanionContext` +
  entry / stage variants. New macro: `templates/macros/form_companion.html`.
  New CSS family: `.dz-form-companion-*` in `components/form.css`.
  Form template (`components/form.html`) renders companions at top,
  after each named section anchor, and at bottom. Regression tests:
  `tests/unit/test_parser.py::TestSurfaceCompanions` (6 cases) +
  `tests/unit/test_form_companions_render.py` (11 cases) cover IR,
  parser, position routing, every display mode, and the compiler
  conversion.

### Changed
- Promoted `companion`, `position`, and `below_section` to
  `KEYWORD_AS_IDENTIFIER_TYPES` so they don't shadow common field /
  enum names.
- `feedback_widget.py` parser now accepts `position` as a sub-key
  even though it's a reserved keyword (was previously matching only
  `IDENTIFIER`-typed tokens).

### Agent Guidance
- Companion blocks live INSIDE a surface, parallel to `section` and
  `action`. They do NOT submit to the create/edit handler. When
  authoring DSL that mixes form fields with context-setting copy /
  KPI tiles / job-plan previews, prefer companions over inline
  field-shaped widgets.
- v1 display modes are declarative. Source-bound
  (`source: Entity`) panels parse but render a placeholder — defer
  source-bound companions to a v2 once the workspace-region
  invocation pipeline integrates with form rendering.

## [0.61.101] - 2026-04-28

### Fixed
- **`templates/workspace/_content.html`** — closes #934. The drawer
  IIFE re-executed on every htmx morph swap that re-rendered
  `_content.html`, stacking duplicate `dz:drawerOpen` /
  `keydown` listeners on `document.body` and capturing now-stale
  drawer/backdrop element references in closures. AegisMark hit the
  user-visible failure as an empty drawer "sliding in" mid-page on
  workspace→workspace nav. Three-part fix:
  1. **Init guard** — listeners register exactly once across the
     session via `window.__dzDrawerInit`. Subsequent script re-runs
     refresh the `window.dzDrawer` facade only.
  2. **Fresh element lookups** — `dzDrawer.open` and `.close` now
     resolve `#dz-detail-drawer` / `#dz-drawer-backdrop` via
     `getElementById` on every call, so they don't operate on
     detached nodes after morph replaces the drawer DOM.
  3. **`htmx:afterSettle` defensive close** — any swap landing
     anywhere other than `#dz-detail-drawer-content` force-closes the
     drawer. The drawer-targeting path opens via `dz:drawerOpen` AFTER
     `htmx:afterSettle`, so this is safe — opening still works.
  Click delegation for in-drawer links also moved to `document.body`
  with a `contains()` filter, since the drawer's content node is
  recreated on every workspace render.
  Regression tests in `tests/unit/test_drawer_morph_safety.py` (7
  cases) pin all three invariants — init guard, fresh lookups,
  defensive close + drawer-target skip + only-when-open guard.

## [0.61.100] - 2026-04-28

### Fixed
- **`templates/workspace/regions/radar.html` +
  `runtime/template_renderer.py`** — closes #929. The radar widget
  used `<g transform="rotate">` chains to position vertices because
  Jinja can't call cos/sin directly. The chain produced correct
  results for elements at constant radius (axis lines, labels) but
  silently broke at varying radii (data dots, polygon outlines, ring
  grid). Symptom: every data circle ended up on the north spoke,
  ring polygons emitted as zero-length lines (invisible). Replaced
  the rotation hack with an explicit polar→cartesian helper:
  `radar_polar_xy(index, count, ratio, cx, cy, r_max)` registered as
  a Jinja global. Template now emits explicit (x, y) coords for ring
  polygons (proper N-gons), spoke axis lines, data polygons (with
  translucent fill — the readable shape every chart library
  converges on), vertex circles, and labels (no longer rotated;
  upright text reads better than spoke-aligned text per user
  testing). Regression tests in `tests/unit/test_radar_geometry.py`
  pin the helper, the rendered SVG's distinct cx values across
  spokes (the smoking gun for #929), the explicit polygon points,
  and the absence of `<g transform="rotate">` wrappers around
  circles.

## [0.61.99] - 2026-04-28

### Added
- **`runtime/auth/current.py`** — closes #933. Project route handlers
  declared via `# dazzle:route-override` had to re-implement the
  cookie + sessions-table dance themselves (12-line snippet copy-pasted
  in every handler that needed auth). Exposed thin wrappers around
  `AuthStore.validate_session`:
  - `current_user_id(request) -> str | None` — UUID string or None
  - `current_user(request) -> dict | None` — `{id, email, roles, preferences}`
  - `current_auth(request) -> AuthContext` — full pydantic context (always returns; check `.is_authenticated`)
  - `@require_auth(roles=["..."])` — decorator returning 401/403 JSONResponses; injects `auth: AuthContext` kwarg into the wrapped handler
  - `register_auth_store(store)` — server wires this at startup; tests can install stubs
  All helpers are best-effort: malformed sessions, DB errors, and
  unauthenticated paths all map to `None` / empty `AuthContext` so
  callers don't need try/except around every call. Role-required spec
  accepts both `role_*` (DB-style) and bare (persona-id-style) names.
  Regression tests in `tests/unit/test_auth_current_helpers.py` (14
  cases) cover both helpers and the decorator's gating semantics.

### Agent Guidance
- For project route overrides that need auth, prefer
  `from dazzle_back.runtime.auth import current_user_id, require_auth`
  over hand-rolling `SELECT user_id FROM sessions ...`. The
  framework's session validation handles expiry + token rotation
  correctly and a hand-rolled query won't.

## [0.61.98] - 2026-04-28

### Fixed
- **`static/css/components/form.css`** — closes #930. The canonical
  `.dz-form-input` class shipped with `height: 2rem` (32px) and only
  `padding-inline`, leaving ~16px of vertical content area for a
  ~22px line-box. Result: descenders on `g`/`p`/`y` clipped against
  the border on every input + select placeholder. Switched to
  `height: auto; min-height: 2.5rem; line-height: 1.4;` plus
  `padding-block` so the line-box always fits and future multi-line
  content (group labels in selects, wrapped placeholders) scales
  naturally. Updated `.dz-form-money-prefix` and
  `.dz-form-money-select` to the same `min-height: 2.5rem` so the
  currency-prefixed amount input stays flush. Regression tests in
  `tests/unit/test_form_input_height.py` pin the input + money-prefix
  + money-select rules so the descender clip can't recur.

## [0.61.97] - 2026-04-28

### Fixed
- **`templates/macros/form_field.html` + `static/js/dz-widget-registry.js`** —
  closes #927. Branch-precedence bug: `field.ref_entity` matched before
  `field.widget == "combobox"` in `form_field.html`, so FK fields with
  `widget=combobox` always rendered as the auto-wired Alpine select
  rather than a TomSelect-bound combobox. Restoring the combobox path
  also exposed a deeper issue — the existing combobox branch reads
  static `field.options`, not an FK API. Added a dedicated
  `field.ref_entity AND widget == "combobox"` branch above the plain
  ref_entity branch that emits a TomSelect-friendly `<select>` with
  `data-dz-widget="combobox"` + `data-dz-ref-api`. Extended the
  combobox widget registration to detect `data-dz-ref-api` and wire
  TomSelect's `load` callback to fetch from the target entity's list
  endpoint, with `valueField: "id"`, `labelField: "__display__"`,
  `searchField: ["__display__"]` (relies on the `__display__`
  injection from #928). Static-options combobox path is unaffected —
  the new branch only activates when both `data-dz-ref-api` and
  `data-dz-widget="combobox"` are present. Regression tests in
  `tests/unit/test_phase4_widgets.py::TestComboboxFkRemoteLoad` pin
  the registry behaviour and `TestFormFieldWidgets` pins the template
  branching (combobox path emits widget+refApi, plain ref_entity path
  keeps Alpine x-for fallback).

### Agent Guidance
- FK-bound `widget=combobox` selects use TomSelect's remote-load
  pattern, not Alpine's x-for. When adding new widget bindings that
  need async option population, prefer TomSelect's `load` callback
  over Alpine reactivity — TomSelect wraps the select once at mount
  and ignores later DOM mutations.

## [0.61.96] - 2026-04-28

### Fixed
- **`runtime/route_generator.py` + `runtime/server.py`** — closes #928.
  Top-level entity list endpoints (`/api/<entity>/?page_size=N`) were
  returning rows without a `__display__` key, even when the entity had
  a registered `display_field`. The relation_loader injects
  `__display__` when eager-loading FKs as nested objects, but the FK
  `<select>` widget on create surfaces fetches the **target** entity's
  plain list endpoint — that path bypassed relation_loader, so option
  text fell back to the UUID PK ("English Language" rendered as
  `2658aabf-a5c4-...`). Added `entity_display_fields` plumbing through
  `RouteGenerator → create_list_handler → _list_handler_body`; when
  set, the handler now walks each row and writes
  `row["__display__"] = row[display_field]`. Existing `__display__`
  values (e.g. from relation_loader resolving a nested FK whose
  display_field is itself a FK) win — first-write semantics. The JSON
  projection allow-list is augmented with `__display__` so it survives
  view-backed list surfaces. Regression tests in
  `tests/unit/test_view_projection.py::TestListHandlerDisplayFieldInjection`.

## [0.61.95] - 2026-04-28

### Added
- **DSL: shared `nav <name>:` definitions** — closes #926. New
  top-level construct declares a reusable list of nav groups that
  workspaces can bind to via `uses nav <name>`. Cuts paste-and-edit
  duplication when a persona has multiple workspaces (a primary
  landing + N drill-downs) that all need to share the same sidebar
  shape. Composition: a workspace may also declare its own
  `group "..."` / `nav_group "..."` blocks; the linker prepends the
  inherited groups, then appends the workspace's own. Inside a
  `nav <name>:` block both `group` and `nav_group` keywords parse
  identically. New IR types: `ir.NavDefinitionSpec`,
  `WorkspaceSpec.nav_ref`, `ModuleFragment.nav_definitions`. New
  parser mixin: `NavParserMixin`. Linker resolution lives in
  `merge_fragments` so the surfaced `WorkspaceSpec.nav_groups`
  always carries the fully composed list — downstream renderers and
  scanners need no per-feature awareness. Regression tests in
  `tests/unit/test_parser.py::TestNavGroupParsing`. Snapshots
  refreshed for the new optional `nav_ref` IR field (purely
  additive, defaults to None).

### Changed
- Promoted `nav` and `group` to keyword-as-identifier set so the new
  reserved keywords don't shadow common field/entity names like
  `entity Group`, `field nav_position`, `enum[group_a, group_b]`.

## [0.61.94] - 2026-04-28

### Fixed
- **`runtime/static/js/dz-alpine.js`** — closes #924. The previous fix
  for #919 (v0.61.89) installed the htmx:afterSettle listener inside
  the `dzDashboardBuilder` Alpine component's `init()`. That works
  when the SAME component instance survives a morph swap (re-clicking
  the active workspace nav link), but when the user navigates between
  *different* workspaces via the sidebar, idiomorph replaces the
  `<div x-data="dzDashboardBuilder()">` element entirely and Alpine
  never picks up the new one — `<template x-for>` directives stay
  inert and the JSON layout island renders as raw text. Added a
  module-level `htmx:afterSettle` listener (outside `alpine:init`) on
  document.body that calls `Alpine.initTree(target)` on every swap,
  forcing Alpine to discover and initialize any new `x-data` roots.
  Idempotent — Alpine tags processed elements internally so
  re-initializing inited components is a no-op. Regression tests in
  `tests/unit/test_dashboard_builder_triggers.py::TestGlobalInitTreeBridge`
  pin: listener exists, sits at module scope (not inside
  alpine:init), uses afterSettle (not afterSwap), guards missing
  Alpine.

## [0.61.93] - 2026-04-28

### Fixed
- **`templates/macros/form_field.html`** — closes #925. The
  `field.type == "checkbox"` branch wired
  `aria-describedby="hint-{name}"` on the input but never rendered the
  matching `<p id="hint-{name}" class="dz-form-hint">{{ field.help
  }}</p>` element, so help text on boolean fields was silently
  dropped (and the aria reference dangled). Added the missing
  paragraph after the checkbox label, mirroring every other field-type
  branch. Regression tests in
  `tests/unit/test_phase4_widgets.py::TestFieldHelpRendering` pin
  checkbox + four other branches and assert the absence path
  (no help → no hint markup).

## [0.61.92] - 2026-04-28

### Fixed
- **`core/dsl_parser_impl/base.py`** — closes #922. The
  `_parse_hyphenated_identifier` helper falls back to
  `expect_identifier_or_keyword` for parts after a hyphen, but that
  helper only accepts keywords listed in `KEYWORD_AS_IDENTIFIER_TYPES`.
  v0.61.88 (#918) added two new reserved keywords (`help`, `note`)
  that weren't added to that set, and the older `question` declaration
  keyword was already missing. As a result hyphenated identifiers
  used in value positions (e.g. `icon=help-circle`,
  `icon=file-question`, `icon=sticky-note` on `nav_group`) failed to
  parse. Added `HELP`, `QUESTION_DECL`, and `NOTE` to the identifier
  set; common Lucide icon names now parse again. Regression test in
  `tests/unit/test_parser.py::TestNavGroupParsing::test_nav_group_icon_with_keyword_substring`.
- **`tests/integration/__snapshots__/test_golden_master.ambr` +
  `tests/parser_corpus/__snapshots__/test_appspec_corpus.ambr`** —
  refresh golden-master snapshots for the new IR fields introduced by
  #918 (`SurfaceSpec.layout: 'wizard'` and `FormElementSpec.help`).
  The change is purely additive — both fields default to None /
  'wizard'. CI was failing on every push since v0.61.88 from this
  drift; bundling the snapshot refresh here.

## [0.61.91] - 2026-04-28

### Fixed
- **`static/css/site-sections.css`** — closes #921. The greedy
  `.dz-section h1/h2/h3/p` typography rules (centred, large, heavy)
  bled into article markdown bodies inside `.dz-section-markdown` and
  `.dz-section .prose` containers, rendering blog-post H2s centred at
  2.25rem instead of left-aligned at body sizes. Added a dedicated
  article-body block that re-declares `text-align: start`, smaller
  weights, and prose-scale font sizes for `h1-h4` and `p` inside any
  markdown / prose section content. The base `.dz-section h2 { ...
  text-align: center }` rule is unchanged so marketing section
  headlines keep their existing styling. Responsive (`@media
  max-width: 768px`) override added so mobile article H2s also
  resolve to body-scale (1.375rem) rather than headline-scale
  (1.75rem). Regression tests in
  `tests/unit/test_section_markdown_typography.py` pin the override
  block, the responsive override, and the unchanged base headline
  rule.

## [0.61.90] - 2026-04-28

### Fixed
- **`runtime/css_loader.py` + `scripts/build_dist.py`** — closes #920.
  Both bundling paths (the runtime `/styles/dazzle.css` route and the
  CDN `dist/dazzle.min.css` build) had stale source-file lists that
  pre-dated the v0.62 CSS refactor: they emitted only the three
  legacy framework files (`dazzle-layer.css`, `design-system.css`,
  `site-sections.css`) and skipped every `components/*.css` family
  including `button.css`. Result: any page served the bundle (notably
  the marketing site) rendered `dz-button` and similar classes with
  zero CSS rules. Both lists now mirror the canonical
  `static/css/dazzle.css` cascade — same files, same order, same
  layer assignments (`reset` / `vendor` / `tokens` / `base` /
  `utilities` / `components`, with `dz.css` / `dz-widgets.css` /
  `dz-tones.css` unlayered for cascade-override). Tests in
  `tests/unit/test_css_delivery.py::TestCssLoader` and `TestBuildDist`
  now positively assert `.dz-button` exists in both bundles, so a
  future stale-list regression fails immediately.

## [0.61.89] - 2026-04-28

### Fixed
- **`static/js/dashboard-builder.js`** — closes #919. The component
  now listens for `htmx:afterSettle` instead of `htmx:afterSwap` to
  decide when to re-hydrate `cards` / `catalog` / `workspaceName` from
  the `<script id="dz-workspace-layout">` JSON island. Under the
  `morph:innerHTML` extension, `htmx:afterSwap` fires before
  idiomorph commits child-node `textContent`, so the previous
  workspace's layout JSON was being read and the destination
  workspace rendered with an empty cards array. `afterSettle` fires
  after all DOM mutations are complete, including child-node text
  updates. Tests in
  `tests/unit/test_dashboard_builder_triggers.py::TestRehydrateOnHtmxAfterSettle`.

## [0.61.88] - 2026-04-28

### Added
- **DSL: `layout: single_page` on create/edit surfaces** — closes #918
  (parts A+B+C). New surface-level `layout:` keyword accepts `wizard`
  (default, existing multi-step behaviour) or `single_page` (all
  sections stack top-to-bottom on one page with a single submit at
  the end). Wired through `SurfaceSpec.layout` → `FormContext.layout`
  → `templates/components/form.html` which now branches on
  `is_wizard` vs `is_single_page` (the dzWizard Alpine scope is only
  attached in wizard mode). Parser tests in
  `tests/unit/test_parser.py::TestSurfaceParsing::test_surface_layout_*`.
- **DSL: `note:` on surface sections** — closes #918 part B. Sections
  may now declare `note: "<string>"` directly under the section
  header to render a muted descriptive subtitle below the section
  title (`<p class="dz-form-section-note">`). New CSS rule in
  `static/css/components/fragments.css`. Parser test
  `test_surface_section_note`.
- **DSL: `help:` on form fields** — closes #918 part C. Fields may
  now declare `help: "<string>"` (alongside the existing `visible:`,
  `when:`, `widget=` trailing options) to render muted helper text
  below the field label. Plumbs through `SurfaceElement.help` →
  `FieldContext.help` → existing `dz-form-hint` markup in
  `templates/macros/form_field.html` (the data attribute renamed
  from the previously-dead `field.hint` to `field.help`; the CSS
  class kept its `dz-form-hint` name). Parser test
  `test_surface_field_help`.

### Notes
- Issue #918 part D (companion regions — read-only sidebar/secondary
  panels alongside form sections) is intentionally deferred. It
  needs a placement design decision (sidebar vs stacked) that should
  not be bundled with the mechanical A+B+C wiring above.

## [0.61.87] - 2026-04-28

### Fixed
- **`static/css/components/regions.css`** — closes #917. Adds
  `.dz-radar-svg { overflow: visible }` so radar axis labels at the
  -90°/90° spokes can render past the SVG bounds rather than being
  clipped mid-word. SVG defaults to `overflow: hidden` per spec, and
  the existing nested-rotate label markup ends up with rendered
  positions outside the viewBox at the side spokes. Trig-placing
  each label (the issue's "option 1") would eliminate the need for
  this rule entirely — worth a follow-up cycle. Test in
  `tests/unit/test_workspace_radar.py::TestRadarSvgOverflow`.

## [0.61.86] - 2026-04-28

### Fixed
- **`src/dazzle_ui/runtime/workspace_renderer.py`** — closes #916.
  When `display: heatmap` (or any region) declares `action: <name>`,
  the action-resolution loop now checks `app_spec.workspaces` BEFORE
  `app_spec.surfaces`. If `<name>` matches a workspace, the URL
  pattern is `/app/workspaces/<name>?context_id={id}` — the heatmap
  template substitutes `{id}` with the row identifier, producing the
  app-shell URL with the row's identifier passed via the standard
  `context_id` query param. Previous behaviour silently downgraded
  to source-record detail because only `surfaces` was checked. Tests
  in `tests/unit/test_heatmap_action_workspace.py`.

## [0.61.85] - 2026-04-28

### Fixed
- **`templates/workspace/regions/radar.html`** — closes #915. Spoke
  `<title>` tooltips, the `aria-label`, the `dz-chart-summary` line,
  and the degenerate-list value cells all now run aggregate values
  through the existing `metric_number` Jinja filter, so a radar with
  `aggregate: avg(score)` returning `10.453333333333333` renders as
  `10.5` (>= 1 → 1dp + thousands separator) rather than leaking the
  full Python float repr. Other chart families (line_chart, box_plot)
  may carry the same pattern; not in scope here — file separately
  if hit. Tests in `tests/unit/test_workspace_radar.py::TestRadarFloatFormatting`.

## [0.61.84] - 2026-04-28

### Fixed
- **`tests/integration/__snapshots__/test_golden_master.ambr`** — refresh
  the golden-master IR snapshot to include the new `width: None` key on
  `WorkspaceRegion`. The v0.61.83 ship of #914 added the optional field
  to the IR but didn't refresh the snapshot; CI on v0.61.83 caught it
  via `test_simple_dsl_to_ir_snapshot`. Snapshot diff is the new
  `width` key only — no other shape change.

## [0.61.83] - 2026-04-28

### Added
- **Region-level `width:` field** — closes #914. DSL authors can now
  set an explicit grid-column span (1..12) per region in a workspace
  declaration:
  ```dsl
  hero_marked_overnight:
    title: "Marked overnight"
    eyebrow: "Today"
    source: Manuscript
    display: summary
    width: 3
    aggregate:
      count: count(Manuscript where status = marked)
  ```
  Replaces the project-side `:has()` + `!important` CSS overrides
  that hero strips and KPI rows previously needed to escape the
  default 12-column-stack layout. Out-of-range values are clamped
  to 1..12 at parse time. Saved layouts (drag-resize via the
  dashboard builder) still win — the user's explicit resize is the
  highest signal. New `WIDTH` token + `WorkspaceRegion.width` IR
  field; `_default_col_span()` consults the IR field before falling
  back to the stage-default lookup. Tests in
  `tests/unit/test_workspace_region_width.py`.

## [0.61.82] - 2026-04-28

### v0.62 CSS refactor — semantic class families replace inline Tailwind

A multi-cycle big-bang migration. Every Dazzle UI template now consumes
semantic `.dz-*` class families served by checked-in static CSS files
(`dazzle-framework.css`, `design-system.css`, `site-sections.css`,
`components/*.css`) — no more inline `text-[hsl(var(--…))]` Tailwind
utilities, no more JIT bundle compile step at build time.

Lands as ~38 commits on the `css-refactor-2026-04-27` branch. Final
commit (Phase 4 teardown) removes the `build_css.py` module, the
`dazzle build-css` CLI, the publish-workflow Tailwind step, and the
two `<link rel="stylesheet" href="…dazzle-bundle.css">` references in
`base.html` and `site_base.html`.

### Changed
- **All UI templates** — every template now uses semantic `.dz-*`
  classes that reference design tokens via CSS rules rather than
  inline `bg-[hsl(var(--…))]` Tailwind utilities. The class families
  are organised by surface: `.dz-form-*`, `.dz-detail-*`,
  `.dz-button-*`, `.dz-table-*`, `.dz-card-*`, `.dz-toast-*`,
  `.dz-modal-*`, `.dz-slideover-*`, `.dz-pipeline-*`, `.dz-steps-*`,
  `.dz-experience-*`, `.dz-error-*`, `.dz-auth-*`, `.dz-feature-*`,
  `.dz-testimonial-*`, `.dz-faq-*`, `.dz-qa-personas`, etc.
- **Toast tones** keyed off `:data-dz-toast-level` attribute selectors
  (replaces dynamic Tailwind class strings invisible to JIT).
- **Modal sizes** keyed off `data-dz-modal-size="sm|md|lg|xl"`
  attribute selectors.
- **Step states** in the experience stepper use `.is-completed` /
  `.is-current` modifier classes; CSS descendant rules resolve the
  bullet/label/connector colour for each state.
- **Form-field error border** driven by `aria-invalid="true"` on the
  input element (CSS rule `.dz-form-input[aria-invalid="true"]`),
  replacing per-branch conditional class concatenation in 8 widget
  branches of `macros/form_field.html`.
- **`/static/css/dazzle-bundle.css` route** kept for back-compat — now
  serves theme override CSS only (when a theme is active), instead of
  the Tailwind+theme combo.

### Removed
- **`src/dazzle_ui/build_css.py`** — the standalone Tailwind CLI
  wrapper + binary download/cache logic (226 LOC).
- **`dazzle build-css` CLI command** — registration in
  `src/dazzle/cli/__init__.py`, the `build_css_command` symbol from
  `runtime_impl/__init__.py` and `build.py`.
- **Tailwind+DaisyUI build invocation** in
  `src/dazzle_ui/runtime/combined_server.py`. `bundled_css` parameter
  now carries only theme override CSS.
- **`_tailwind_bundled` Jinja global** + the per-request filesystem
  existence check in `src/dazzle_ui/runtime/template_renderer.py`.
- **`<link rel="stylesheet" href="…dazzle-bundle.css">`** in
  `templates/base.html` and `templates/site/site_base.html`.
- **Three publish-workflow steps** in
  `.github/workflows/publish-pypi.yml`: editable install for the
  `dazzle build-css` CLI, the rebuild step itself, and the post-build
  `dazzle-bundle.css in wheel` verification.
- **`dazzle-bundle.css` entry** from `.gitignore`.
- **`tests/unit/test_build_css.py`** — the entire file (23 tests).

### Fixed
- **`templates/components/review_queue.html`** — the cycle-250
  DaisyUI sweep had renamed the `btn` arrow-function parameter in the
  notes-toggle script to a Tailwind class string, throwing
  SyntaxError at parse time. Restored the parameter name.
- **`templates/site/sections/qa_personas.html`** — same JS-corruption
  bug as review_queue. Restored the `btn` parameter.
- **`templates/site/sections/faq.html`** — markup used radio buttons
  + div wrappers that the `.dz-faq-item` CSS (which expects
  `<details>`/`<summary>`) never matched. Switched to the
  contract-matching markup.
- **`templates/site/sections/testimonials.html`** — markup wrapped
  each item in Tailwind-styled `<div>`s that didn't match the
  `.dz-testimonial-item` CSS (which expects `<blockquote>` +
  `.dz-testimonial-author`). Switched to the contract-matching markup.

### Agent Guidance
- **`.dz-button` is the universal button primitive.** Compose with
  `.dz-button-primary` / `-outline` / `-ghost` / `-destructive` for
  variant, optionally with `.dz-button-sm` for the smaller size.
  Direct utility-style buttons are no longer the norm.
- **Tone tinting via `data-*` attribute selectors.** When a component
  has 3+ tone variants (info/success/warning/error etc.), prefer
  `data-dz-{thing}-{type}="value"` attribute selectors over per-tone
  inline class strings. CSS rules
  `.dz-{thing}[data-dz-...="value"]` resolve the matrix without
  touching dynamic class strings — this matters because Tailwind's
  JIT won't see dynamic strings (the original #906 bug class).
- **State via `.is-*` modifier classes.** When an Alpine component
  has 2-branch state ternaries on `:class`, prefer setting `.is-*`
  modifiers and resolving them via CSS rules. Same advantage —
  static class names visible to any tooling.
- **`aria-invalid="true"` drives error state, not a class.** Form
  field error borders should be CSS
  `.dz-form-input[aria-invalid="true"]` rather than per-branch
  `border-[hsl(var(--destructive))]` conditionals. The aria attribute
  is the single source of truth (visual + screen reader behaviour
  share one attribute).

### Fixed (post-merge)
- **`templates/base.html` + `static/css/dazzle.css`** — the v0.62
  merge left base.html pointing at the legacy `dazzle-framework.css`
  entry, which only `@import`s the legacy 6-file stack
  (dazzle-layer, design-system, site-sections, dz, dz-widgets,
  dz-tones) and skipped every `components/*.css` file — including
  the load-bearing `fragments.css` — so every template the v0.62
  refactor migrated rendered unstyled. base.html now loads
  `dazzle.css`, and `dazzle.css` was extended to also `@import` the
  legacy framework files (whose tone/transition/structural rules
  the templates still rely on). Reported by aegismark; new
  `TestDazzleCssEntry` regression class in
  `tests/unit/test_css_delivery.py` pins both invariants.

## [0.61.81] - 2026-04-28

Patch bump. **Fix #912** — v0.61.79's #911 progress-bar work landed the parser, IR, runtime helper, and template — but silently dropped the `progress` field at the IR→template-context boundary in `workspace_renderer.py`. Result: parser parsed `progress: 100` fine, IR carried it, but the rendered template never saw `stage.progress` so the bar never appeared. Same bug shape as #910 — data drops at a boundary.

### Fixed
- **`src/dazzle_ui/runtime/workspace_renderer.py`** — `pipeline_stages` boundary now includes `"progress": s.progress` in each dict alongside `label`, `caption`, `value`. The runtime then reads `_stage.get("progress")` and the template's `{% if stage.progress is not none %}` finally evaluates true.

### Tests
- **`test_workspace_pipeline_steps.py::TestProgressFlowsThroughBoundary`** — 4 new tests pinning the full IR→context→template flow:
  - `test_boundary_emits_progress_in_dict` — pin the boundary shape directly via `build_workspace_context`.
  - `test_template_renders_bar_when_progress_set` — render the template with realistic `pipeline_stage_data` and assert `data-dz-progress`, ARIA wiring, percent labels.
  - `test_template_omits_bar_when_progress_none` — negative case, legacy pipelines unchanged.
  - `test_template_emits_overshoot_flag_when_clamped` — overshoot path.

The pre-fix template-wiring test only checked the template *source* for `stage.progress is not none`. It never verified that `progress` actually flowed through the boundary so it couldn't catch this regression — exactly the same blind spot as #910's profile_stats render path. The new tests instantiate the boundary and the template, not just the source files.

### Agent Guidance
- **#910 lesson restated.** When adding a new field to an IR spec that flows through a boundary into a render path, write **at least one test that exercises the boundary with a non-empty value**. Source-text contract tests catch refactoring drift but miss data-flow gaps. The pattern: parse DSL → build context → render template → assert the value reaches the rendered output. The previous #911 test set asserted the parser, IR, runtime helper, *and* template-source contract — every link in the chain except the one that broke.
- **A "/issues closed" event is not a /deploy verified event.** v0.61.79 closed #911 and shipped — both the parser and the template change landed in commits — but the boundary in workspace_renderer.py wasn't touched. Production exposed it within hours. The fix loop already had this as guidance for #910 ("when closing a fix issue, ask the reporter to verify"); the same applies for feature work that crosses multiple layers.

## [0.61.80] - 2026-04-28

Patch bump. **Fix #910 (second attempt)** — v0.61.78 fixed the predicate compiler so scope filters now correctly emit `school_id` for relation-name shorthand. That restored real items for AegisMark's `pupil_identity` profile_card region (sibling regions all returning 200 confirmed the predicate compiler is now correct). But the same region kept returning 500 because there was a second, distinct bug in the profile_card render path itself — masked for the entire lifetime of `display: profile_card` because it never had non-empty items in any production test.

### Fixed
- **`src/dazzle_back/runtime/workspace_rendering.py`** — the PROFILE_CARD branch built `profile_card_data["stats"]` via attribute access (`_stat.label`, `_stat.value`) on items pulled from `ctx.ctx_region.profile_stats`. That attribute is `list[dict[str, str]]` per the IR→template-context boundary in `workspace_renderer.py` (line 569: `profile_stats=[{"label": s.label, "value": s.value} for s in ...]`). On any non-empty `items` list, the comprehension raised `AttributeError: 'dict' object has no attribute 'label'` and surfaced as a 500. Switched to dict access — `_stat["label"]` / `_stat["value"]` — matching the boundary shape.

### Tests
- **`test_workspace_profile_card.py::TestProfileCardStatsBuildFromDicts`** — 3 new tests:
  - `test_build_profile_stats_from_dict_specs_no_attribute_error` — pin the dict-access contract in the source (windowed substring check around the comprehension so docstring history doesn't trip).
  - `test_runtime_boundary_emits_dicts_not_models` — pin the IR→template-context shape so the dict-access fix and the boundary stay in sync. If the boundary ever switches to passing pydantic models through, the runtime access pattern must move with it.
  - `test_stat_value_resolves_against_item_via_dict_key` — exercises the exact comprehension lines on a synthetic item + dict-shaped specs, asserting the produced shape.

### Agent Guidance
- **The data shape at the boundary is the contract.** When code on one side of a boundary builds dicts and code on the other side uses attribute access, the integration only works when the consumer never runs. The `_stat.label` access "worked" for the entire lifetime of `display: profile_card` because pre-#909 the predicate compiler emptied `items` before the consumer ever fired. The bug surfaced only when a sibling fix made `items` non-empty. **Lesson: when adding a new render-path consumer for a value that crosses an IR→template-context boundary, write a regression test that exercises the consumer with a non-empty input — not just the parser side.** All four pre-existing profile_card tests checked the parser, the IR construction, the template wiring, and the safety helpers — none rendered the runtime branch with non-empty items.
- **A "fix verified by deploy" report is the strongest signal.** The user's comment on #910 — "tested in prod after deploying v0.61.79, still 500, sibling regions all 200" — pinpointed exactly that the fix landed in the predicate compiler but didn't reach the render path. The "sibling regions all 200" bit is the load-bearing observation: it ruled out the predicate compiler and forced the search to the profile_card-specific path. **When closing a fix issue, ask the reporter to verify in their environment if they can — the round-trip cost is small and it catches second-order bugs the unit suite missed.**

## [0.61.79] - 2026-04-28

Patch bump. **Add #911** — `display: pipeline_steps` regions now accept a per-stage `progress: 0..100` field. Turns the menu-shape into a thermometer-shape so operators see how complete each stage is, not just whether anything is in it. Same expression vocabulary as `value:` — either a literal numeric string or a `count(<Entity> where ...)` aggregate. Clamped to 0-100 at render; values >100 set `data-dz-progress-overshoot="true"` for theme styling. Aligns with AegisMark's prototype shape (`scan-ingestion-job.html` per-stage progress bar).

### Added
- **`src/dazzle/core/ir/workspaces.py`** — `PipelineStageSpec.progress: str = ""`. Default empty preserves the v0.61.56 shape — existing pipelines render unchanged. Field shape mirrors `value:` so the parser + runtime can reuse the same dispatcher.
- **`src/dazzle/core/dsl_parser_impl/workspace.py`** — `_parse_pipeline_stages` accepts `progress:` alongside `caption:` and `value:` inside each stage block. Same literal-or-aggregate acceptor (quoted string OR unquoted multi-token aggregate expression). Unknown-key error now lists `progress` as a valid key.
- **`src/dazzle_back/runtime/workspace_rendering.py`** — `_coerce_pipeline_progress` helper clamps numeric input to 0-100 and returns `(int|None, overshoot_bool)`. None / empty / unparseable → `(None, False)` so the template renders no bar (preserves existing layout). Overshoot (>100) → `(100, True)`. The PIPELINE_STEPS branch dispatches both `value` and `progress` per stage through a single `_queue_stage_field` helper that gathers async count tasks; literals short-circuit. Cross-entity scope warning is parameterised over field name so `progress` aggregates surface the same audit log line as `value` aggregates.
- **`src/dazzle_ui/templates/workspace/regions/pipeline_steps.html`** — new conditional progress block beneath each stage's headline value. Renders only when `stage.progress is not none`. Emits `data-dz-progress="{n}"`, `data-dz-progress-overshoot="true"` when clamped, ARIA `progressbar` role + `aria-valuenow`. Inline `style="width: {n}%;"` on the fill so themes don't need to compute it; `data-dz-progress` carries the bound number for tone-keyed CSS.

### Tests
- **`test_workspace_pipeline_steps.py`** — 15 new tests across four classes:
  - `TestPipelineStepsProgressParser` (5) — literal numeric, quoted literal, aggregate, default-empty, value+progress coexist.
  - `TestPipelineStageSpecProgressField` (3) — IR construction with progress, default empty, independent of value.
  - `TestProgressCoercion` (6) — in-range, 0/100 boundaries, overshoot clamps to 100 + flag, negative clamps to 0, None/empty/unparseable → None, garbage → None (no exception).
  - `TestProgressTemplateWiring` (1) — template gates on `stage.progress is not none`, emits `data-dz-progress`, ARIA `progressbar` role + valuemin/valuemax/valuenow.

### Agent Guidance
- **Per-field async dispatch over per-stage.** The pre-#911 PIPELINE_STEPS branch had one task list keyed by stage index. Adding a second field (progress) needed task results addressable by `(stage_idx, field_name)`. The refactor introduced a single `_queue_stage_field` helper and a tuple-keyed result dict — easier to extend a third or fourth aggregate field without growing the loop body. When adding a parallel field to an existing stage spec, look for a one-task-per-stage shape and broaden it.
- **Clamping is presentation, not validation.** `progress: 120` from the DSL is accepted at parse time and clamped at render time to 100 with an overshoot flag. The user might genuinely have 120% capacity (over-allocated work queue) and want the theme to surface "over capacity". Reject-at-parse would discard that signal. Same pattern for any numeric metric where >100% is meaningful: clamp + flag, don't error.

## [0.61.78] - 2026-04-28

Patch bump. **Fix #910** — v0.61.77's #909 fix qualified scope predicate columns with the source entity table (`"StudentProfile"."school" = %s`). That was correct for the JOIN-ambiguity case but broke any DSL where the author wrote a *relation name* as shorthand for the FK column. AegisMark's `school = current_user.school` pre-fix bound (incorrectly) to the User-join's `school` column; post-fix Postgres errored with `column "StudentProfile"."school" does not exist` because the actual column is `school_id`. `display: profile_card` regions on `pupil_dashboard` returned 500 instead of the previous (wrong but non-crashing) empty state.

### Fixed
- **`src/dazzle_back/runtime/predicate_compiler.py`** — `_qualify_column` now mirrors the `_compile_path_check` heuristic: when the bare field name doesn't exist on the source entity, try `<field>_id`; if neither exists fall back to the bare ref so legitimate edge cases (entity not in the FK graph, ad-hoc tests) don't 500. `fk_graph` is threaded through `_compile_column_check`, `_compile_user_attr_check`, and `_compile_column_ref_check` so every leaf can resolve. Same effect when `fk_graph` is `None` — bare-name passthrough — preserving the v0.61.77 behaviour for callers that don't supply the graph.

### Tests
- **`test_predicate_qualified_columns.py`** — 7 new tests in `TestRelationNameResolvesToFkColumn`: relation-name → FK-id resolution for `UserAttrCheck` + `ColumnCheck`; field-exists-as-is keeps the bare name (no clobbering scalar columns); neither form exists falls through (genuine schema errors still surface); no FK graph disables resolution; `BoolComposite` threads the graph to every leaf; `ColumnRefCheck` resolves both sides. Plus a small helper that builds an `FKGraph` from a single entity spec for compact test cases.

### Agent Guidance
- **Defence in depth, not just defence in width.** The #909 fix added column qualification — that closes the ambiguity hole. But qualification by itself is too literal: it assumes the DSL author wrote the actual column name. The DSL allows relation-name shorthand (`school` for `school_id`), so the resolver pass needs the same `_id`-suffix heuristic that `_compile_path_check` already had. Whenever a fix tightens one layer, audit the adjacent compilers for the same shorthand convention so the new strictness doesn't break legitimate inputs.
- **Mirror established conventions across compilers.** `_compile_path_check` already had the `<segment>_id` fallback for FK terminal fields (lines 268-274). The #909 fix didn't apply the same heuristic to the simpler leaf compilers because the fix was scoped to the JOIN-ambiguity bug. When extending an established compiler family, scan siblings for relevant heuristics — they're usually load-bearing.

## [0.61.77] - 2026-04-28

Patch bump. **Fix #909** — RBAC scope predicates emitted unqualified column references like `"school" = %s`. When the runtime later applied a source-table alias to user filters (because FK display joins introduced ambiguity), the scope predicate stayed unqualified — `"school"` could bind to a JOINed table's `school` column instead of the source entity's. AegisMark hit this with StudentProfile (the FK display join on `user: ref User` brought in `User.school`, which most pupils' user accounts didn't have set to the teacher's school, so the AND-combined query returned 0 rows).

The user reported the symptom as a `display: profile_card` vs `display: summary` divergence; the actual root cause is in the predicate compiler. The summary path "worked" only because it bypassed the region's `filter:` declaration entirely (a separate, broken-but-invisible bug surfaced in the analysis comment on #909 — to be addressed in a follow-up).

### Fixed
- **`src/dazzle_back/runtime/predicate_compiler.py`** — `_compile_column_check`, `_compile_user_attr_check`, and `_compile_column_ref_check` now qualify column references with the source entity table (e.g. `"StudentProfile"."school" = %s` instead of `"school" = %s`). Schema qualification flows through when set. The dispatch in `compile_predicate` threads `entity_name` + `schema` to all three leaf compilers; `_compile_bool_composite` already recursed via `compile_predicate` so no change needed there. Empty `entity_name` (callers that pre-date the fix) falls back to bare column ref for compatibility.

### Tests
- **`test_predicate_qualified_columns.py`** — 9 new tests across four classes: `UserAttrCheck` qualification (the #909 case + schema variant + fallback compatibility), `ColumnCheck` qualification (literal-value comparisons + IS NULL), `ColumnRefCheck` qualification (both sides), `BoolComposite` recursive qualification (AND/OR), and a full WHERE-clause integration that simulates the AegisMark scenario (StudentProfile + FK display join + scope predicate + user `id` filter) and asserts both sides end up qualified to `"StudentProfile"`.
- **`test_aggregate_where_parser.py`** — 7 assertion lines updated. The aggregate where-parser uses `compile_predicate` internally and now produces qualified columns; tests pinning the unqualified shape were updated. One test (`test_where_and_existing_scope_predicate_combine_with_and`) deliberately keeps an unqualified LHS in its hand-built scope predicate input — it's documenting the AND-combine logic, not the column-qualification fix.

### Agent Guidance
- **A symptom that looks like "feature X is broken vs feature Y" can have a root cause that's neither X nor Y.** The user's report framed #909 as `profile_card` vs `summary` divergence on the same source/filter. The actual bug was in the predicate compiler, several layers down. Don't jump to "fix the divergence" — trace the data flow and find the real fault. The diagnostic comment on the issue saved a speculative fix that would have changed `_workspace_region_handler` semantics for everyone.
- **JOINs change the meaning of unqualified column references.** When code emits SQL into a context that may or may not have JOINs, always qualify columns with their source table. The cost is a few extra characters per column ref; the benefit is immunity from ambiguity errors AND from silent wrong-binding when the joined table happens to have a column of the same name. The scope-predicate path here had been emitting unqualified references for years — it just happened that no production app's joined tables had colliding column names until AegisMark's StudentProfile + User both had `school`.
- **Test the produced SQL exactly, including table prefixes.** The pre-existing `test_aggregate_where_parser.py` had 7 assertions of the form `assert sql == '"foo" = %s'`. After my fix they all needed updating to `assert sql == '"X"."foo" = %s'`. That noise IS the point — tests that pin SQL shape catch this class of regression immediately. Don't relax the assertion to "contains the column name"; assert the full string including qualification.

## [0.61.76] - 2026-04-28

Patch bump. **Fix #908** — `status_list` authored regions rendered "No data available." even when the IR held entries. The route registered correctly post-#907, the parser populated `status_entries`, the template iterated `status_entries` correctly — but `workspace_rendering.py` never forwarded the variable to the `render_fragment(...)` call. Template gate fell through to the empty-state branch every time.

This is the second forwarding bug in the same render path inside 24h (#908 sibling to the AegisMark-reported `confirm_action_panel` and similar). The unit-tier template binding tests passed because they checked the template SOURCE for the right Jinja constructs but never actually rendered the template through `render_fragment` with a realistic kwargs payload.

### Fixed
- **`src/dazzle_back/runtime/workspace_rendering.py`** — `render_fragment(...)` call now includes `status_entries=getattr(ctx.ctx_region, "status_entries", [])` alongside the other authored-display payloads (`action_card_data`, `pipeline_stage_data`, `confirmations`, `profile_card_data`).

### Tests
- **`test_workspace_status_list.py`** extended with `TestStatusListRendersAuthoredEntries` — three tests that actually render the template through `render_fragment(...)`: positive (entries present → entries render, empty-state suppressed), negative (no entries → empty-state fires correctly), and a defensive string-match guard pinning the forwarding line in `workspace_rendering.py` so a future refactor doesn't drop it again.

### Agent Guidance
- **Template-binding tests that check source aren't enough.** The `test_workspace_status_list.py::TestStatusListTemplateBinding` class verified the template iterates `status_entries`, references each field, uses `data-lucide`, etc. — all correctly. But it never asked "does the template actually render the entries when called through the runtime path?" The pre-fix bug shipped because the source-level tests were green. **For any authored display mode (where data flows from IR → render call → template), add at least one test that calls `render_fragment(template, **kwargs)` directly and asserts on the rendered HTML.**
- **The render-call kwargs are a contract surface.** Every new authored display mode (status_list, confirm_action_panel, action_grid, pipeline_steps) needs a corresponding kwarg in the `render_fragment(...)` call in `workspace_rendering.py`. There's no DRY mechanism currently — each one is added by hand. Worth considering a contextual unpack pattern (`**ctx.template_kwargs()`) once we have 5+ display modes; adds one tested layer instead of N hand-maintained call-site lines.

## [0.61.75] - 2026-04-27

Patch bump. **Fix #907** — `WorkspaceRouteBuilder.init_workspace_routes` short-circuited via `if not ctx_region.source: continue`, silently skipping route registration for any sourceless region. The four bodyless authored display modes (action_grid #891, pipeline_steps #890, status_list #3, confirm_action_panel #6) all hit this — their HTMX endpoints 404'd, the skeleton placeholder never got replaced, the entries never rendered. AegisMark hit it on three consecutive `status_list` regions in the SIMS sync settings workspace before reporting it.

The parser-level bodyless-region exemption (added in #891 for action_grid and extended through each subsequent bodyless mode) made the regions *parse* without a source, but the route-builder kept its source-required check unchanged. Two parallel exemption surfaces, only one was kept in sync.

### Fixed
- **`src/dazzle_back/runtime/workspace_route_builder.py`** — bodyless display modes now register routes even with no source. Allowlist is the four named modes (`ACTION_GRID`, `PIPELINE_STEPS`, `STATUS_LIST`, `CONFIRM_ACTION_PANEL`); other display modes still require a source as before. The downstream handler short-circuits the items fetch when source is None and renders the template from the IR's authored config.

### Tests
- **`test_workspace_route_builder_bodyless.py`** — 6 new tests: one per bodyless display mode (action_grid, pipeline_steps, status_list, confirm_action_panel) parsing a sourceless DSL and asserting the route exists in `app.routes`; one positive guard (sourced LIST still registers); one negative guard (sourceless LIST is still skipped — only the four named modes are exempt).

### Agent Guidance
- **Two parallel exemption surfaces drift.** When the parser says "this construct is allowed in shape X", the runtime must also accept shape X — and these are usually different files maintained by different mental models. The bodyless-region exemption was added to the parser five times across #891, #890, #3, #6 — and zero times across the route-builder. Anytime you add a parser exemption for a structural pattern, grep for the inverse runtime check (in this case, `if not ctx_region.source`) and add the matching exemption. The unit-test suite passed because tests called the renderer directly with hand-built contexts, never the route-builder.
- **The "I have no users so this code path is never exercised" trap.** action_grid and pipeline_steps shipped sourceless variants ages before AegisMark first declared a sourceless region in production. The bug was latent for months. Whenever a feature has an authored variant (data declared in the IR, not fetched from a source), add at least one integration-tier test that exercises the full route registration → handler → template render path with realistic input. Unit tests that mock the route layer don't surface this class of bug.

## [0.61.74] - 2026-04-27

Patch bump. **#906 cleanup pass** — completed an audit of all 30 region templates for the buried-dynamic-class pattern that bit AegisMark in #906. Found two remaining instances missed in the v0.61.70 fix: `action_grid` (per-card tone tints + count-badge tints) and `metrics` (period-over-period delta arrow tone). Both migrated to `data-dz-*` attributes styled by `dz-tones.css`. The audit also surfaced 5 hardcoded HSL literals (positive=145,55%,45%; warning=40,90%,55%; specific shades) in those templates — all replaced with design-system slot references.

After this pass, **all 30 region templates use only static design-token references**. The bug class is closed at the framework level; downstream consumers will get correct colors regardless of their Tailwind scan glob configuration.

### Fixed
- **`action_grid.html`**: dropped `_tone_classes` and `_tone_count_classes` Jinja dictionaries. Card surface and count-badge tints now route via `data-dz-tone` and `data-dz-tone-badge` attributes respectively. The hardcoded `hsl(145,55%,45%)` (positive green) and `hsl(40,90%,55%)` (warning amber) literals are gone — both use `--success` and `--warning` design-system slots so theming applies.
- **`metrics.html`** delta arrow: dropped the `_tone_class` dynamic Tailwind expression that picked between three colour classes via Jinja conditional. Now emits `data-dz-delta-tone="positive|destructive|neutral"`. The hardcoded `hsl(142 76% 36%)` literal (which was the positive-direction arrow colour) is gone — also routes via `--success`.

### Added
- **`dz-tones.css`** extended with rules for `.dz-action-card[data-dz-tone]` (surface tint + hover), `.dz-action-card-count[data-dz-tone-badge]` (badge background + foreground), and `.dz-metric-delta[data-dz-delta-tone]` (arrow colour). All five tones for the action-card/badge slots; three for the delta arrow (positive/destructive/neutral — the up/down/flat axis is independent and stays as `data-dz-delta-direction`).

### Tests
- **`test_dz_tones_css.py`** extended with 7 new tests across two new classes: action_grid + metrics-delta absence-of-dynamic-class guards, presence-of-data-attribute guards, and per-tone CSS rule presence. The existing per-component test classes now cover all four tinted components (metric tile, notice band, status pill+icon, action card+badge, metric delta arrow).

### Agent Guidance
- **Audit-then-fix pattern works.** The audit took ~30 min via a single Explore subagent run that categorised all 30 templates into three buckets (static / dynamic-from-data / hardcoded-color). Result was actionable: 2 templates needed work, 28 were already correct. Without the audit I'd have either (a) shipped the half-fix from #906 thinking it was complete, or (b) over-rotated and migrated all 30 templates unnecessarily. **When fixing a bug class, audit the surface before assuming the fix is local OR systemic.**
- **The dynamic-class pattern is rare even when it exists.** Out of ~250 arbitrary-value HSL class references across 30 templates, only ~12 were the buried-dynamic kind. The rest are static literals using design-system variables — the JIT happily compiles them, downstream consumers' Tailwind scanners happily ignore them (because the rules ship in dz-tones-aware CSS bundles). The bug class is small even in templates that look superficially "Tailwind-heavy".
- **CSS-side migration removes hardcoded color literals "for free".** The original action_grid had `hsl(145,55%,45%)` for positive — a one-off green that didn't match `--success`. Migrating the tone routing to dz-tones.css forced a decision: hardcode the literal in CSS, or use `--success`. Using the design slot is obviously right; doing the migration surfaces the choice you'd otherwise never get to.

## [0.61.73] - 2026-04-27

Patch bump. **CI fix** — the AegisMark UX patterns roadmap shipped seven new fields on `WorkspaceRegion` IR (eyebrow, notice, tones, status_entries, confirmations, state_field, revoke, primary_action, secondary_action) across v0.61.65–v0.61.72. The integration-tier `test_simple_dsl_to_ir_snapshot` golden-master snapshot needed regeneration to include the new fields. Local unit-suite runs passed because the test lives under `tests/integration/` and the local pre-flight script filters with `-m "not e2e"` (which doesn't deselect the integration tier — but my own local invocations did).

### Fixed
- **`tests/integration/__snapshots__/test_golden_master.ambr`** regenerated to include the seven new region fields. CI was red on every commit since v0.61.65.

### Agent Guidance
- **Run the integration tier locally before shipping IR changes.** `pytest tests/ -m "not e2e"` filters by mark, not by directory — but my local pre-flight script ran `tests/unit/` only, so integration-tier snapshot drift went unnoticed for nine versions. When adding any field to a frozen IR type that goes into a serialised snapshot, run `pytest tests/integration/test_golden_master.py` explicitly OR run the full suite without the directory filter. The CI badge would have caught this on commit one if I had been checking it after each ship.
- **Snapshot tests are blast-radius-multipliers for IR changes.** A single new field on `WorkspaceRegion` lights up every snapshot that serialises a region. With nine versions of additions, the diff is large but mechanical: `pytest --snapshot-update` regenerates everything in one pass. The lesson: when adding ANY new IR field, the next test run should include snapshot tests in scope.

## [0.61.72] - 2026-04-27

Patch bump. **AegisMark UX patterns roadmap item #6** — `display: confirm_action_panel` ships the irreversible-action consent primitive. State-bound rather than monolithic: a single panel declaration with `state_field:` handles all visual modes (off / pending / live / revoked) by reading the entity's status field. Multi-stage consent flows compose by chaining `experience` + `step` blocks, each step rendering a confirm_action_panel — no new wizard primitive needed.

This completes the AegisMark UX patterns roadmap (Phases 1-3, items #1-#7). Five components shipped today: eyebrow (#1, v0.61.60), tones (#2, v0.61.65), status_list (#3, v0.61.69), pipeline_steps `value:` (#4, v0.61.66), pair_strip (#5, v0.61.71), notice band (#7, v0.61.68), and now confirm_action_panel (#6).

### Added
- **`DisplayMode.CONFIRM_ACTION_PANEL`** + `workspace/regions/confirm_action_panel.html`. Renders the AegisMark "Final authorisation" shape: checklist of obligations + dual button (primary commit / secondary draft) + audit footer. Branches on resolved `state_value`: `off`/`pending`/`draft` → checklist + dual-button; `live`/`active` → "Currently live" summary + revoke; `revoked` → audit + re-enable.
- **`ConfirmationItemSpec` IR type** (`src/dazzle/core/ir/workspaces.py`) with `title: str`, `caption: str = ""`, `required: bool = True`. Required items must all be ticked for the primary action to enable; optional items are advisory.
- **DSL keywords**: `confirmations:` block, `state_field:` (entity column driving panel mode), `revoke:` (action surface for the live state). `primary_action:` / `secondary_action:` use IDENTIFIER string-match (avoiding clash with profile_card's `primary:` / `secondary:` which mean entity-field names there). `required:` on individual confirmations stays an IDENTIFIER (NOT a lexer keyword) so the field-modifier parser elsewhere keeps working.
- **`dzConfirmGate` Alpine component** (`src/dazzle_ui/runtime/static/js/dz-alpine.js`) — counts required-checkbox toggles and exposes `enabled` (true when all required boxes are ticked). Template binds `:href` and `:class` on the primary button to the `enabled` getter so the disabled state is purely visual + click-blocking.
- **Audit footer auto-detection** — when the source entity has an `audit:` block declared, the renderer sets `audit_enabled=true` upstream and the template emits the "recorded in audit log with your account, IP address, and timestamp" disclosure. Authors don't write the copy by hand.
- **`examples/ops_dashboard`** new `Integration` entity (`audit: all`, status enum) + `integration_authorise` region in the `incident_review` workspace exercising the full panel — all three confirmations, dual button, revoke, audit footer.

### Tests
- **`test_workspace_confirm_action_panel.py`** — 23 tests across parser (minimal panel, required default, required false, caption, state-field optional, invalid required value raises, unknown key raises), bodyless exemption, `ConfirmationItemSpec` construction, action-key isolation from profile_card, runtime wiring (display map, template file, RegionContext defaults + carries fields), template branches (state_value reference, three render modes, confirmations iteration, dual button, revoke in live mode, audit footer gate, Alpine gate registration), and audit auto-detect parser path.

### Agent Guidance
- **State-bound panels are simpler than archetypes.** The original "consent archetype" idea would have stamped 4 regions out of one DSL block. Modeling the panel as a single state-bound display mode keeps the surface area small (one IR type, one template, one display value) AND lets authors compose multi-stage flows out of existing `experience` / `step` primitives. Each step renders a confirm_action_panel surface; the wizard plumbing is reused from the existing experience system. Resist the temptation to bake "consent archetype" wizard mechanics into the panel itself — composition wins.
- **Pydantic v2 BaseModel.copy() shadow strikes again.** `ConfirmationItemSpec` deliberately uses `caption` (not `copy`) for the secondary line — same dodge as `StatusListEntrySpec.caption` (#3). Defensive: any new IR type with a "secondary descriptive line" should reach for `caption` first. The `test_field_named_caption_not_copy` tests in the status_list suite already pin this; future IR types should add their own.
- **Don't promote field modifiers to lexer keywords.** Adding `REQUIRED = "required"` to the lexer broke field parsing where `required` appears as a modifier (`name: str(100) required`). The parser couldn't tell modifier-required from new-field-required-with-colon. Fix: keep `required` as an IDENTIFIER and string-match its value in the new parser branch (`elif key == "required"`). Same applies to any common-shape modifier word — `nullable`, `unique`, `pk`, etc. They all need to stay IDENTIFIER tokens.
- **Mutating frozen Pydantic IR fails silently in some contexts.** I tried to set `ctx.ctx_region.state_value = ...` to thread the resolved entity-field value into the template — but `ctx_region` is the frozen `WorkspaceRegion` IR. The right pattern is to thread per-request values through the template render call as separate kwargs, not by mutating the IR. Same lesson applies any time you need to add "resolved at request time" data: pass it explicitly to `render_fragment(...)`, don't try to stuff it back onto the IR.

## [0.61.71] - 2026-04-27

Patch bump. **AegisMark UX patterns roadmap item #5** — `pair_strip` workspace stage layout. AegisMark's SIMS-sync-opt-in prototype's `consent-grid` pattern is a stack of explicit `(info, action)` pairs; pair_strip is the framework primitive that gives DSL authors the same shape via a one-line stage declaration. Mobile fallback piggybacks on the existing 12-column responsive grid — no framework JS, no per-region template branching.

### Added
- **`pair_strip` stage value** in `STAGE_DEFAULT_SPANS` and `STAGE_FOLD_COUNTS` (`src/dazzle_ui/runtime/workspace_renderer.py`). Every region under a `stage: "pair_strip"` workspace gets `col_span=6`; CSS grid auto-flow stacks them into rows of two. Sibling to `dual_pane_flow` but reads more naturally for multi-pair flows. Eager-loads six regions above the fold (three pairs).
- **`examples/ops_dashboard`** `incident_review` workspace demonstrates pair_strip with four regions = two pairs (`alert_summary` + `recent_alerts`, `system_overview` + `review_checklist`). Exercises the new stage alongside metrics tones (#2), notice band (#7), and status_list (#3) — full UX vocabulary in one workspace.

### Tests
- **`test_workspace_pair_strip.py`** — 8 tests across stage registration (default spans + fold counts), `_default_col_span` behaviour (first region, subsequent regions, regression guard for unrelated stages), example-app demo (workspace exists, has at least 4 regions), and a responsive-contract guard that pins the "no Python branching for mobile, CSS does it" decision so a future "let me add JS for mobile" temptation trips a test before shipping.

### Agent Guidance
- **A new layout intent doesn't always need new IR.** pair_strip and dual_pane_flow have identical col_span behaviour (every region half-width); pair_strip exists as a separate stage VALUE because authors thinking about an explicit-pair flow will reach for the more descriptive name. Adding a stage table entry is ~5 LOC; inventing a new region group primitive would have been ~150 LOC — and the second cycle of authors would still have written `stage: "pair_strip"` if it had been there.
- **CSS grid auto-flow handles multi-row pair layouts natively.** When every region declares `col-span-6` and the parent is a 12-column grid, three pairs stack into three rows of two. Mobile fallback comes from the project's standard responsive media queries (the 12-column grid collapses to 1 column at narrow widths, which makes col-span-6 equivalent to col-span-12). Don't write framework JS for layout; let CSS do it.
- **Stage values are free-form strings — adding one means just registering it.** No parser changes, no IR changes, no template changes. `STAGE_DEFAULT_SPANS[name] = pattern` + `STAGE_FOLD_COUNTS[name] = N` and the stage is ready. Same shape as how authors will discover it: read the DEFAULT_SPANS table, find a stage that matches their layout intent, type its name.

## [0.61.70] - 2026-04-27

Patch bump. **Fix #906** — tone tints on `metrics` tiles, `notice` bands, and `status_list` pills/icons no longer rely on dynamic Tailwind arbitrary-value classes that the JIT can't observe at build time. Three components shipped with this bug across v0.61.65 / v0.61.68 / v0.61.69; AegisMark deployments saw transparent tiles + uncoloured pills despite the data attributes being correct.

### Added
- **`src/dazzle_ui/runtime/static/css/dz-tones.css`** — static tint rules keyed off `[data-dz-tone]` (metrics), `[data-dz-notice-tone]` (notice band), and `[data-dz-state]` (status_list pill + icon). All tints route through HSL design-system slots so theming applies. Wired into `dazzle-framework.css`, `css_loader.py` `CSS_UNLAYERED_FILES`, and `build_dist.py` `CSS_SOURCES` so it ships with every install shape.

### Fixed
- **#906**: `metrics.html`, `_content.html` (notice band), and `status_list.html` no longer build dynamic class strings like `bg-[hsl(var(--primary)/0.10)]`. Templates emit only the data attributes; `dz-tones.css` provides the matching rules. Templates kept their always-applied static fallback class (e.g. `bg-[hsl(var(--muted)/0.4)]` on every metric tile) so neutral entries render unchanged.

### Tests
- **`test_dz_tones_css.py`** — 15 new tests across four classes: file presence, per-component rule presence (metric tile, notice band, status_list pill, status_list icon — all tones), design-system token usage, three-path load order (framework CSS @import, css_loader CSS_UNLAYERED_FILES, build_dist CSS_SOURCES), absence of dynamic Tailwind tone classes in each template, and presence of the data attributes the CSS keys off.
- **`test_workspace_region_tones.py`**, **`test_workspace_region_notice.py`**, **`test_workspace_status_list.py`** — pre-existing template-binding tests that pinned the OLD dynamic-class branches were inverted to assert the data-attribute contract instead. Per-tone HSL branches now pinned in the dz-tones.css test file (single source of truth).
- **`test_css_delivery.py::TestCssLoader::test_canonical_order`** — extended `UNLAYERED_FILES` fixture to include `dz-tones.css`.
- **`test_workspace_routes.py::TestMetricsRegionTemplate::test_no_hardcoded_hsl_literals`** — re-scoped to assert the `data-dz-tone="warning"` attribute renders on the tile (the dz-tones.css rule does the rest).

### Agent Guidance
- **Tailwind JIT can't see classes built at runtime.** When a template constructs a class string from server-side IR data (`tones:`, `state:`, `tone:` blocks etc.), the JIT scans nothing — it builds CSS from what it sees in source files at build time. Anything more dynamic than a static literal class needs an alternative source-of-truth: a static CSS rule keyed off a data attribute, a Tailwind safelist entry, or moving the decision into a CSS variable that a static rule consumes. **Default to the data-attribute pattern** (`[data-dz-tone="..."]`) — it's grep-able, theme-aware (HSL slots), and survives any Tailwind config refactor.
- **Three load paths means three places to wire CSS.** Dazzle ships static assets via the `dazzle-framework.css` @import bundle (browser-native CSS @layers), the `css_loader.py` runtime concatenator (for inline serving), and `scripts/build_dist.py` (for the `dist/` bundle). Adding a new CSS file means updating all three or some deployment shape will ship without it. The `TestDzTonesCssLoadOrder` test class pins this contract.
- **Same bug in three components is one bug, not three.** When a pattern is duplicated across components (the dynamic `bg-[hsl(...)]` lookup appeared in metrics, notice, and status_list templates) and one of them breaks, check the others before shipping a per-component fix. Better to ship one cross-cutting fix and three regression tests than three separate patches.

## [0.61.69] - 2026-04-27

Patch bump. **AegisMark UX patterns roadmap item #3** — `display: status_list` mode renders a vertical list of icon + title + caption + state-pill entries. The canonical row shape from AegisMark's "agreement card", "schedule grid", and "scope grid" prototype patterns. Authored variant only this cycle (DSL `entries:` dash-list); the source-bound variant that maps entity rows to entries is deferred to a later cycle per the roadmap.

This completes Phase 2's largest single piece. Phases 1+2 of the roadmap are now complete except the deliberately deferred items (#5 pair_strip and #6 consent archetype, both pending more example-app data).

### Added
- **`DisplayMode.STATUS_LIST`** + `workspace/regions/status_list.html` template. State pill colours route through design-system HSL slots (`var(--success)`, `var(--warning)`, etc.) — five tone tokens reuse the action_grid + metrics + notice vocabulary. Neutral-state entries omit the pill so the row reads as plain info rather than a status row.
- **`StatusListEntrySpec` IR type** (`src/dazzle/core/ir/workspaces.py`) — frozen Pydantic model with `title: str`, `caption: str = ""`, `icon: str = ""`, `state: str = "neutral"`. Field is `caption` (not `copy`) to dodge the `BaseModel.copy()` shadow and stay consistent with `PipelineStageSpec.caption`.
- **DSL `entries:` block parser** (`src/dazzle/core/dsl_parser_impl/workspace.py`) — mirrors the action_grid `actions:` parser. Each entry is a dash-list dict with `title:` (required) plus optional `caption:` / `icon:` / `state:`. Validates state token against the five-token palette at parse time. status_list joins action_grid and pipeline_steps in the bodyless-region exemption (no `source:` / `aggregate:` required when `entries:` IS the body).
- **New tokens** `ENTRIES`, `STATE` (and an existing `CAPTION` reuse). Both new tokens added to `KEYWORD_AS_IDENTIFIER_TYPES` so authors can still use `state` / `entries` as field names elsewhere.
- **`examples/ops_dashboard`** `ops_readiness` region demonstrates four entries spanning all the relevant tones (positive on-call rotation, positive runbook coverage, warning pager test, accent audit window).

### Tests
- **`test_workspace_status_list.py`** — 23 tests across parser (minimal pair, title-only entry, state defaults to neutral, invalid state raises, unknown key raises, entry must start with title, each valid state token parses), bodyless exemption, `StatusListEntrySpec` (minimal/full/`copy`-shadow check), runtime wiring (display map, template file exists, RegionContext default + carries entries), template binding (iterates `status_entries`, renders each field, Lucide icon attribute, design-system tokens for all five tones, region_card macro, canonical class markers, neutral-state pill omission), and empty-state.

### Agent Guidance
- **Don't name a Pydantic field `copy`.** `BaseModel.copy()` is a deprecated method — a field with that name shadows it and triggers a `UserWarning` on every parse. Use `caption` (consistent with `PipelineStageSpec`), `body` (consistent with `NoticeSpec`), or `description`. The `copy`-shadow check (`callable(spec.copy)`) is a useful regression guard.
- **Bodyless region exemption is now a 3-component contract.** action_grid (`actions:`), pipeline_steps (`stages:`), and status_list (`entries:`) all sidestep the "source: or aggregate: required" check because their indented dash-list IS the body. When adding a new authored-list display mode, add the corresponding `and not <new_field>` to the exemption check in `parse_workspace`. Forgetting this surfaces as `Workspace region 'X' requires 'source:' or 'aggregate:' block` even though the DSL is correct.
- **One entry parser shape, three components.** action_grid, pipeline_steps, and status_list all use the same dash-list-of-dicts shape with one required leading key (`label:` for the first two, `title:` for status_list). This consistency lets authors transfer mental model between components — and makes the parser implementation almost copy-paste. When adding a fourth entry-shaped component, mirror the same shape rather than inventing a new one.

## [0.61.68] - 2026-04-27

Patch bump. **AegisMark UX patterns roadmap item #7** — region-level `notice:` field renders a prominent banner band above the data body in the dashboard slot. AegisMark's SIMS-sync-opt-in prototype uses notices for legal-basis disclosure, opt-in context, and status banners — strong line + secondary copy with tone tinting. Phase 1 of the roadmap is now complete (items #1, #2, #4, #7).

### Added
- **`notice:` field on workspace regions** (`src/dazzle/core/lexer.py` already had `NOTICE` from the surface-side `attention notice:` block; reused here in workspace context). Two parser shapes: shorthand `notice: "Title text"` (title-only, neutral tone) and block form with `title:` / `body:` / `tone:` keys. Tone tokens reuse the action_grid + metrics vocabulary (positive / warning / destructive / accent / neutral).
- **`NoticeSpec` IR type** (`src/dazzle/core/ir/workspaces.py`) — frozen Pydantic model with `title: str`, `body: str = ""`, `tone: str = "neutral"`. Exported from `dazzle.core.ir`.
- **Notice band template** (`src/dazzle_ui/templates/workspace/_content.html`) — sits between the card header (drag handle + title + actions) and the HTMX-loaded body. Tinted background + left rail via design-system HSL slots (`var(--success)`, `var(--warning)`, etc.) so the active theme applies. Hidden via `x-show` when no notice is configured — existing dashboard frames render unchanged.
- **Renderer wiring** (`src/dazzle_ui/runtime/workspace_renderer.py`, `src/dazzle_ui/runtime/page_routes.py`) — `RegionContext.notice: dict[str, str]` carries the band; `cards_for_json` includes the entry on every card payload. Empty dict when omitted.
- **`examples/ops_dashboard`** Health Summary region picks up an accent-toned notice ("Status as of last sync / Counts refresh every 30s; alert deltas use the prior 24h window.") to demonstrate.

### Tests
- **`test_workspace_region_notice.py`** — 18 tests covering parser (default None, shorthand, block with all keys, block title-only, block with tone, missing title raises, unknown key raises), `NoticeSpec` construction, `RegionContext` wiring, card payload propagation, and template binding (`card.notice` reference, truthy gate, all four tone branches present, design-system tokens for tints).

### Agent Guidance
- **Two parser shapes for one IR field is a usability multiplier.** The shorthand `notice: "Title"` covers the common case (~70% in AegisMark's prototype); the block form `notice:` with `title:`/`body:`/`tone:` covers the rich case. Detection is trivial — peek the next token after the colon: STRING → shorthand, INDENT → block. Same pattern works any time you have a "name + optional metadata" pair (action, asset, integration, etc.).
- **Static frame > HTMX swap for chrome.** The notice band is rendered in `_content.html` as part of the static card frame, NOT inside the HTMX-loaded region body. This means: (a) it appears immediately on first paint, before the data load, (b) it survives HTMX swaps when the region body refreshes, (c) the band's tone classes don't need to be re-evaluated per swap. Anything that's per-region-but-not-per-data belongs in the static frame.
- **Reuse the tone vocabulary across components.** `action_grid` cards (#891), `metrics` tiles (#894/#2), and now `notice` bands all share the five-token palette (positive / warning / destructive / accent / neutral). When introducing a new tinted component, reuse — don't invent. Authors learn one vocabulary; theming applies uniformly.

## [0.61.67] - 2026-04-27

Patch bump. **Fix #905** — `display: summary` and `display: metrics` regions no longer render the underlying items table inside the hero tile. AegisMark's teacher_workspace was rendering a 600-row Manuscript table under the "Marked overnight" hero, and an 82,568-row MarkingResult table under "Class average" — both crowded prototype-tight hero strips with ~400px of vertical waste per tile.

### Removed
- **Items+columns block in `metrics.html`** (`src/dazzle_ui/templates/workspace/regions/metrics.html`) — deleted the `<div class="overflow-x-auto"><table>...</table></div>` block, the divider `<div class="h-px ... my-3"></div>` above it, the `for item in items` / `for col in columns` iterations, the `_attention` row tinting, and the unused `render_status_badge` macro import. Summary/metrics regions are about the headline number; authors who want both metric tiles AND a list should declare two regions (one METRICS, one LIST).

### Changed
- `tests/unit/test_workspace_routes.py::TestMetricsRegionTemplate::test_drill_down_table_renders_when_items_and_columns` renamed and inverted to `test_no_drill_down_table_rendered_even_with_items` — pins the new contract: even when `items` and `columns` are populated, no table renders.
- `test_no_hardcoded_hsl_literals` re-scoped to assert tone tints route through design-system tokens (`var(--warning)` etc.) — the previous form exercised the deleted items-table warning row tint.

### Tests
- **`test_metrics_no_items_table.py`** — 10 new string-level invariants on the template source: no `<table>`, no `<thead>`/`<tbody>`, no `for item in items` loop, no `for col in columns` loop, no `h-px` divider, no `overflow-x-auto` wrapper. Also four positive checks: still iterates `metrics`, still emits `dz-metric-tile`, still branches on `metric.tone`, still renders delta.

### Agent Guidance
- **"Hybrid metrics+table" cards are an anti-pattern.** Hero strip is the most prized visual real-estate in any dashboard; an unfiltered rows table underneath turns it into a list region with a metric on top. Better: declare separate regions with separate display modes. The DSL's job is to make this composition trivial — the template's job is to refuse it.
- **Removing template branches is reversible only if the test suite pins the absence.** Without `test_metrics_no_items_table.py`, a future "let me add a small drill-down toggle" temptation could quietly reintroduce the bloat. String-level invariants on the template source are stronger than rendered-DOM checks because they catch the regression before the template even compiles.

## [0.61.66] - 2026-04-27

Patch bump. **AegisMark UX patterns roadmap item #4** — generalise `pipeline_steps` per-stage `aggregate:` to `value:`, accepting either an aggregate expression OR a literal string. Authors can now mix count-driven stages with descriptive flow-card labels ("Daily 02:00 UTC", "Manual review") in the same pipeline.

### Changed
- **`pipeline_steps` per-stage key renamed `aggregate:` → `value:`** (`src/dazzle/core/dsl_parser_impl/workspace.py`, `src/dazzle/core/ir/workspaces.py`). Clean break per project policy — no shim. The new `value:` accepts a quoted string literal OR an unquoted aggregate expression; runtime uses `_AGGREGATE_RE.match` to dispatch.
- **`PipelineStageSpec.aggregate_expr` renamed `value`** — single source of truth, matches the DSL field name. All call sites updated in the same commit (parser, runtime, renderer, tests, ops_dashboard example).

### Added
- **Literal-string render path in `pipeline_steps` runtime** (`src/dazzle_back/runtime/workspace_rendering.py`) — non-aggregate values short-circuit the query path entirely. They're stashed into `_stage_literals` during the dispatch loop and re-attached to the build output, so they render verbatim alongside count-driven siblings. Honours the scope-deny gate (literals still render even when scope-denied — they don't depend on row visibility).
- **`examples/ops_dashboard` `alert_pipeline`** picked up a literal-value stage ("Audit / Daily 02:00 UTC") to demonstrate mixed-shape pipelines.

### Tests
- **`test_workspace_pipeline_steps.py`** — 4 new tests in `TestPipelineStepsValueShape`: quoted literal parses, literal with em-dash, mixed aggregate + literal in same block, and a regex-contract pin asserting `_AGGREGATE_RE` distinguishes both shapes correctly. All 14 existing tests updated for the rename.

### Agent Guidance
- **Field renames require updating the `getattr(...)` callers too.** When renaming a Pydantic field on an IR type, grep for both the field name AND `getattr(thing, "old_name")` patterns — the renderer often defensively reads via `getattr` to avoid IR-import cycles, and a missed `getattr("aggregate_expr")` would silently revert the new field to its default. The full call graph for this rename: parser → IR → runtime (`_stage.get(...)`) → renderer dict-build → template var name. Touching any one without the others lights up the test suite immediately, so don't be precious about it.
- **Polymorphic field shapes (aggregate-expr OR literal-string) belong on a single field with runtime dispatch, not two parallel fields.** The wrong design here would have been `value:` for literals + keeping `aggregate:` for queries. Two fields means double the parser branches, double the IR fields, double the runtime gates, and forces authors to know the difference upfront. One field with runtime regex-dispatch (`_AGGREGATE_RE.match`) means authors write the natural form and the framework figures it out — same pattern as `_compute_aggregate_metrics` already uses for region-level aggregates.
- **Reserved-keyword traps in test DSL.** `flow:` is reserved; `kind:` is reserved; `title:` works only because the workspace parser string-matches it. When writing pipeline-style test DSL, use `pipeline:`, `alerting:`, etc. for region names — reserved keywords surface as `Expected DEDENT, got flow` errors that look unrelated to what you actually broke.

## [0.61.65] - 2026-04-27

Patch bump. **AegisMark UX patterns roadmap item #2** — per-tile `tone:` on `display: metrics` regions. Authors can now tint individual metric tiles to communicate at-a-glance state (positive / warning / destructive / accent / neutral). Mirrors the action_grid card vocabulary so the palette tokens stay consistent across components.

### Added
- **`tones:` block on workspace regions** (`src/dazzle/core/lexer.py`, `src/dazzle/core/dsl_parser_impl/workspace.py`, `src/dazzle/core/ir/workspaces.py`) — sibling to `aggregate:`. Maps metric name → tone token. Pure presentation hook with no impact on data, scope, or semantics.
- **Per-tile background tint in `metrics.html`** — branches on `metric.tone` with five render paths (positive / warning / destructive / accent / default). All tones map to design-system HSL slots so the active theme applies; no hard-coded colours. Untoned tiles render unchanged (default muted bg). A `data-dz-tone` attribute is emitted when a tone is set, for downstream test/styling hooks.
- **Renderer wiring** (`src/dazzle_back/runtime/workspace_rendering.py`, `src/dazzle_ui/runtime/workspace_renderer.py`) — `_compute_aggregate_metrics` accepts a `tones=` kwarg and attaches `tone` to each output metric dict whose name has an entry. The two render paths that build `metrics` for HTMX responses pass it through; the stats-only path (used by the workspace JSON endpoint) intentionally skips it.
- **`examples/ops_dashboard`** Health Summary region demonstrates per-tile tones — `healthy_count: positive`, `critical_count: destructive`. Real-app coverage so the new field is exercised in a working DSL.

### Tests
- **`test_workspace_region_tones.py`** — 16 tests covering parser (default empty, single, multi, unknown-metric tolerance, presentation-only invariant), keyword-as-identifier escape hatch, RegionContext wiring, `_compute_aggregate_metrics` tone attachment (with / without / partial tones map), template binding (`metric.tone` reference, all five tone branches present, design-system tokens), and presentation-only invariant (tones don't change metric value or label).

### Agent Guidance
- **Sibling `tones:` block over inline tone-on-aggregate.** The natural temptation is `aggregate: { active: { expr: count(Item), tone: positive } }` — but that forks the existing `name: expr` flat-dict shape across every region author. Adding a parallel `tones:` map keeps the aggregate vocabulary unchanged and makes the per-metric tone optional and orthogonal. Same pattern applies to future per-metric metadata (icons, captions, links).
- **Tone tokens are reused, not minted.** When introducing a new component-level tone slot, reuse the action_grid vocabulary (positive / warning / destructive / accent / neutral) before inventing new ones. Keeps the palette small and predictable for downstream theming.
- **Conditional Jinja attributes need careful whitespace.** A naïve `{% if x %}attr="{{ x }}"{% endif %}` leaves trailing spaces in the rendered HTML when `x` is empty, which breaks DOM snapshot tests for unrelated regressions. The fix is `class="..."{% if x %} attr="{{ x }}"{% endif %}` — the leading space lives inside the conditional, so an empty `x` produces zero added whitespace.

## [0.61.64] - 2026-04-27

Patch bump. **Fix #904** — `display: summary` + `aggregate: avg(field)` rendered "Avg Score 0" because the scalar-aggregate path through `Repository.aggregate` was broken in two compounding ways. AegisMark's class-average tile showed 0 despite ~82,000 visible MarkingResult rows with non-zero scores.

### Fixed
- **`build_aggregate_sql` no-dimension path** (`src/dazzle_back/runtime/aggregate.py`) — pre-fix, `if not dimensions: return "", []` short-circuited to empty SQL, which `_fetch_scalar_metric` saw as `buckets=[]` and returned 0. Now emits `SELECT <measures> FROM <table> [WHERE...] LIMIT N` (no GROUP BY) for the scalar-aggregate path. The `_fetch_scalar_metric` helper that #888 Phase 1 introduced for region-level avg/sum/min/max tiles now actually fires its query.
- **`rows_to_buckets` Decimal handling** — pre-fix: `int(Decimal("0.834"))` truncated to 0 (the secondary half of the #904 symptom). Now `Decimal` / `str` numeric values cast through `float()` so fractional means render correctly. `None` → 0 (empty filtered set).

### Tests
- **`test_aggregate_sql.py`** extended:
  - `test_no_dimensions_emits_scalar_aggregate` (replaces `test_no_dimensions_returns_empty` which pinned the broken behaviour)
  - `test_no_dimensions_avg_field_emits_correct_sql` — canonical #904 repro: `avg(score)` on MarkingResult emits `SELECT AVG("score") FROM "MarkingResult" LIMIT N` with no GROUP BY
  - `test_no_dimensions_no_measures_returns_empty` — empty-on-both still gives empty SQL
  - `test_decimal_avg_value_preserved_as_float` (#904): `Decimal("6.8")` round-trips as `6.8`, not `6`
  - `test_decimal_sub_one_avg_does_not_truncate_to_zero` (#904): `Decimal("0.834")` → `0.834`, not `0`
  - `test_none_measure_value_renders_as_zero`: NULL aggregate over empty filtered set → 0

### Agent Guidance
- **Two compounding bugs producing one symptom.** The user's report ("Avg Score 0") was caused by the SQL never firing AT ALL. But even if the SQL had fired and returned `Decimal("0.834")`, the truncation-to-int would have converted it back to 0 — same symptom, different root cause. When investigating "always 0" reports for scalar aggregates, check both the SQL emission path AND the result-type conversion. Pin both with separate regression tests.
- **Repository.aggregate has TWO valid input shapes**, not one. With dimensions → multi-row GROUP BY result. Without dimensions → single-row scalar aggregate over the whole filtered table. Both shapes share the same WHERE / scope-predicate plumbing; only the SELECT body differs.
- **Decimal/numeric type handling: `float()` not `int()` for measures.** Postgres returns `Decimal` for `AVG(int_col)`, `SUM(int_col)`, etc. — never `int` or `float` directly. Use `float()` to preserve the value through JSON serialisation. `int()` truncates toward zero, which is destructive for any sub-1 mean (the #904 symptom).
- **Test the type contract, not just the value.** `test_decimal_avg_value_preserved_as_float` asserts both the value AND the type — catches the regression class even if a future refactor produces the right value through a wrong-typed path (e.g. returning `Decimal` directly which JSON-serialises differently).

## [0.61.63] - 2026-04-27

Patch bump. **Fix #903** — region-level `title:` field for explicit title override (vs auto-derived from snake_case region key). Closes the cosmetic-finish gap for prototype-fidelity dashboards: AegisMark's teacher_workspace had eight cards rendering with PascalCase titles like "Hero Marked Overnight" / "Pupil Ao Heatmap" — every other gap (palette, typography, hero strip, journey-row, action band) was closed but cards still read as raw IDs. Pairs with `eyebrow:` (v0.61.60) to complete the AegisMark "eyebrow / title / copy" panel header trio.

### Added
- **`WorkspaceRegion.title: str | None`** — explicit title override. When `None`/empty, runtime falls back to auto-derived title from snake_case region key (e.g. `hero_marked_overnight` → "Hero Marked Overnight"). Pure presentation hook.
- **Parser branch** in `src/dazzle/core/dsl_parser_impl/workspace.py` — string-matches `IDENTIFIER` value `"title"` instead of promoting `title` to a lexer keyword. **This is deliberate**: making `title` a keyword would break every `expect(IDENTIFIER)` site that expected `title` as a literal identifier (flow assertions, demo blocks, persona scenarios, etc.). String-matching scopes the new region behaviour without altering the global identifier vocabulary.
- **Empty-string fallback** — `title: ""` parses to `None` (per #903 edge-case spec) so the runtime falls back to auto-derived rather than rendering an empty title.

### Tests
- **`tests/unit/test_workspace_region_title_override.py`** (new) — 13 cases:
  - `TestTitleParser` (5): default-None, override parses, both `title:` + `eyebrow:` together (the #903 repro DSL), empty-string-treated-as-None, must-be-quoted enforcement
  - `TestTitleAsIdentifier` (3): `title` as entity field name (most common case), as enum value, **and a guard test pinning that `title` is NOT a lexer keyword** (catches the wrong-fix attempt)
  - `TestTitleRenderingFallback` (3): explicit title wins, missing title auto-derives, empty title falls back
  - `TestTitleIsPresentationOnly` (1): scope/data/aggregate fields unaffected

### Agent Guidance
- **Don't promote ultra-common identifiers like `title`, `name`, `id` to lexer keywords.** Even with `KEYWORD_AS_IDENTIFIER_TYPES` registration (the #899 escape hatch), every parser site that does `expect(TokenType.IDENTIFIER)` would need to convert to `expect_identifier_or_keyword()`. That's hundreds of sites for the most common identifiers. The string-match-on-IDENTIFIER pattern in the workspace region parser scopes the new keyword to the one context it's needed in. Apply the same pattern when adding region-level fields whose name is a common identifier.
- **`KEYWORD_AS_IDENTIFIER_TYPES` is for keywords that are NEEDED elsewhere as keywords AND occasionally appear as identifiers.** Adding to that list is the right escape hatch when the keyword's primary use is its keyword form (e.g. `display`, `aggregate`, `class`). When the new "keyword" is overwhelmingly used as an identifier in the wild (`title`, `name`, `id`), keep it as IDENTIFIER and string-match in the parser.
- **AegisMark UX patterns roadmap progress:** `eyebrow:` (v0.61.60) + `title:` (v0.61.63) complete item #1 (panel header trio). Items #2-7 remain queued — see `dev_docs/2026-04-27-aegismark-ux-patterns.md`.

## [0.61.62] - 2026-04-27

Patch bump. **Fix #902** — multi-section `mode: create` surfaces emitted Alpine bindings (`isCurrent(N)`, `isActive(N)`, `step > N`, `goToStep(N)`) outside any `x-data` scope, throwing 20+ ReferenceErrors per page render and leaving step indicators stuck grey instead of highlighting the current step. Form chrome still functioned (Next/Cancel worked) but UX was degraded and the browser console was flooded.

### Fixed
- **`components/form.html`** — moved the `x-data="dzWizard(N)"` scope from the `<form>` element up to the outer wrapper `<div class="max-w-2xl">`. The stepper include sits ABOVE the form in source order, so a form-element-scoped binding left the stepper outside scope. The new wrapper-scoped binding wraps both the stepper AND the form.
- **`dzWizard.validateStage` still works** — it uses `$el.querySelectorAll("[data-dz-stage]")` to find stage elements. Moving the scope from `<form>` to `<div>` keeps stages inside `$el` (they're inside the form which is inside the div).

### Tests
- **`tests/unit/test_form_stepper_alpine_scope_regression.py`** (new) — 4 cases:
  - `TestFormStepperScope` (3): static-source guards pinning the dzWizard scope on the wrapper (not the form), the source-order check that the stepper include sits inside the scope, and the `#902` comment annotation
  - `TestStepperBindingsRequireScope` (1): sanity check that the stepper still uses `isActive(`, `isCurrent(`, `step `, `goToStep(` — if a future edit changes the stepper to inline its own helpers, the regression test should be revisited

### Agent Guidance
- **Alpine `x-data` scope position is load-bearing.** When a template emits Alpine bindings (`:class`, `x-show`, `x-text`, etc.) that reference data/methods, those bindings MUST sit inside the element that opens the matching `x-data` scope. Move-the-scope-up is usually safer than move-the-binding-down because it preserves visual layout. When a fragment include depends on a parent's data scope, document that dependency in a comment so the include site doesn't get refactored without thinking.
- **Source-order matters for include + x-data combinations.** A `{% include %}` that uses Alpine bindings must come AFTER the `x-data` opening tag in the rendered output. The `test_stepper_include_sits_inside_dzwizard_scope` invariant pins this by checking string positions in the rendered template — cheap and effective.
- **Console-error floods are a sign of scope-shadowing bugs.** When users report "20+ ReferenceErrors per page" the cause is almost always an Alpine binding evaluated in the wrong x-data context. Grep the stack-trace identifiers (`isCurrent`, `step`, etc.) to find the `Alpine.data("dzX", () => ({...}))` definition, then trace the template tree from the binding upward to find where `x-data="dzX(...)"` should have wrapped it.

## [0.61.61] - 2026-04-27

Patch bump. **Fix #901** — `action_grid` and `pipeline_steps` per-card / per-stage `count_aggregate` queries silently returned 0 when the per-card entity differed from the region's `source:` entity. AegisMark's cross-entity action cards (e.g. an `action_grid` whose source is `MarkingResult` but with a card counting `AssessmentEvent`) were all showing zero counts.

### Fixed
- **`action_grid` per-card scope gate** in `src/dazzle_back/runtime/workspace_rendering.py` — `_card_scope = _scope_only_filters if _entity_name == ctx.source else None`. Pre-fix, `_scope_only_filters` (resolved against the source entity's columns) was unconditionally passed to a different-entity repo, causing silent SQL failures (caught + swallowed) and 0 counts.
- **`pipeline_steps` per-stage scope gate** — same shape: `_stage_scope = _scope_only_filters if _entity_name == ctx.source else None`. The user verified empirically that all 4 stages of AegisMark's `ingestion_journey` showed 0 because of this same root cause.
- **Operator audit signal** — both branches now log a warning when scope is dropped: "cross-entity count is unscoped — destination entity's own RBAC at navigation time still applies, but the count badge shows ALL rows the runtime can read". Operators see this in their server logs and can choose to add explicit per-entity scoping if needed.

### Tests
- **`tests/unit/test_cross_entity_aggregate_scope_regression.py`** (new) — 7 cases:
  - `TestCrossEntityScopeGate` (4): static-source guards pinning the entity-match gate in both branches, the warning log calls, and the `#901` comment annotations
  - `TestSimulatedScopeGateBehaviour` (3): pure-function simulation of the `_card_scope = ... if ... else None` decision rule covering same-entity (passes through), different-entity (drops to None), and no-scope (no-op)

### Security
- **Cross-entity counts are now unscoped** (with operator warning). This is a known UX cost: the count badge for a card targeting a different entity than the region source shows ALL rows the runtime can read, not just rows the user would see if they navigated to the destination. The destination entity's RBAC still applies at click-time, so users can't access data they shouldn't — but the count itself becomes a coarse signal. **Resolving the destination entity's own scope predicate** at aggregation time would require threading `app_spec.surfaces` lookups; deferred until a real consumer needs scoped cross-entity counts. The operator warning makes this audit-visible.

### Agent Guidance
- **Per-card / per-stage aggregates can target ANY entity**, not just the region source. The action_grid plan-stated story is "things the user can do next" — those naturally span entities. The pipeline_steps "ingestion → review → output" pattern often crosses entities too. The runtime now handles this correctly; authors don't need to constrain all cards/stages to the source entity.
- **`_scope_only_filters` is entity-specific.** It carries column references that only resolve against the entity it was computed for. When passing to a different-entity repo, it MUST be dropped (or the destination entity's own scope must be re-resolved). The gate `if entity_name == ctx.source` is the load-bearing check; do not strip it without also wiring the per-destination scope resolution.
- **Silent SQL failures are an anti-pattern.** Pre-fix, `_fetch_count_metric` swallowed the exception and returned 0 — operators saw "0 cards" with no signal anything was wrong. The fix adds a per-call warning log so cross-entity unscoped queries are audit-visible. When adding new per-card/per-stage paths, mirror this pattern.
- **Future improvement: scoped cross-entity counts.** To make cross-entity per-card/per-stage queries fully scoped, the runtime would need to look up the destination entity's `cedar_access_spec` (via `app_spec.surfaces` matching `entity_ref + mode=list`) and re-run `_apply_workspace_scope_filters` per per-card-entity. Deferred until a real consumer asks; current behaviour is correct + audit-visible.

## [0.61.60] - 2026-04-27

Patch bump. **AegisMark UX patterns roadmap — item #1 (`eyebrow:` field on regions).** Every panel in AegisMark's SIMS-sync-opt-in prototype has a kicker line ("Data flow", "Legal basis", "Approved data scopes") above the title. Promoting this to a first-class region field gives DSL authors the eyebrow / title / copy header trio without forking templates. First of six items in the AegisMark roadmap (see `dev_docs/2026-04-27-aegismark-ux-patterns.md`).

### Added
- **`WorkspaceRegion.eyebrow: str | None`** — kicker line rendered above the region title in the dashboard slot's panel header. Default `None`. Pure presentation hook — no impact on data, scope, or aggregates.
- **Lexer token** `EYEBROW = "eyebrow"` in `src/dazzle/core/lexer.py`. Added to `KEYWORD_AS_IDENTIFIER_TYPES` per the #899 fix pattern so `eyebrow` remains usable as a field name (e.g. `entity Article: eyebrow: str(60)`) and enum value (e.g. `enum[heading, eyebrow, body, caption]`).
- **Parser branch** in `src/dazzle/core/dsl_parser_impl/workspace.py` — quoted-string-only (eyebrow text typically contains spaces). Sibling pattern to `purpose:` and other meta-text fields.
- **`RegionContext.eyebrow: str = ""`** in `src/dazzle_ui/runtime/workspace_renderer.py` — flows IR to render context.
- **`cards_for_json` payload extension** in `src/dazzle_ui/runtime/page_routes.py` — each card carries `eyebrow` so the Alpine card-grid template binds it via `x-text`.
- **Template binding** in `src/dazzle_ui/templates/workspace/_content.html` — `<span x-show="card.eyebrow" x-text="card.eyebrow">` rendered above the title `<h3>`. Empty eyebrow → no element, so existing dashboards render unchanged.

### Tests
- **`tests/unit/test_workspace_region_eyebrow.py`** (new) — 13 cases:
  - `TestEyebrowParser` (5): default-None, quoted string, special chars (em-dash / slash), no-clobber-other-fields, must-be-quoted enforcement
  - `TestEyebrowAsIdentifier` (3): enum value round-trip, field name round-trip, static guard pinning EYEBROW in `KEYWORD_AS_IDENTIFIER_TYPES`
  - `TestEyebrowRuntimeWiring` (3): RegionContext default, carries value, cards_for_json payload includes the field
  - `TestEyebrowTemplateBinding` (1): static check that the template binds `card.eyebrow` and gates on `x-show` so empty doesn't render
  - `TestEyebrowIsPresentationOnly` (1): scope/aggregate/data-shape fields unaffected

### Agent Guidance
- **AegisMark UX patterns roadmap is in `dev_docs/2026-04-27-aegismark-ux-patterns.md`.** Six items prioritised; this ships #1. Phase 1 (small, high-impact): #1 eyebrow, #2 metric tile tones, #4 pipeline_steps.value generalisation, #7 notice band. Phase 2: #3 status_list (~250 LOC). Phase 3: #5 layout pair-strip, #6 consent archetype — both deferred until 2-3 example apps anchor the API and AegisMark conversation continues.
- **`eyebrow:` is the first of two "panel header trio" fields.** `purpose:` already exists as the explanatory copy below the title. With `eyebrow:` above and `title:` in the middle, every workspace region can express the AegisMark "kicker / heading / copy" three-line pattern that's foundational to their visual language.
- **Adding a new region-block keyword? Follow the established three-step pattern:** (1) lexer token, (2) parser branch, (3) `KEYWORD_AS_IDENTIFIER_TYPES` registration. The static-guard test from #899 catches missing step 3 before it ships.
- **Pure-presentation fields don't need scope-deny gating.** `eyebrow:` (like `class:` from #894) doesn't read or render data — just author-supplied text in the header chrome. The `TestEyebrowIsPresentationOnly` invariant pins this. Contrast with aggregate fields which need the #887 scope-deny gate.

## [0.61.59] - 2026-04-27

Patch bump. **Fix #900** — region `class:` field landed in card data JSON but Alpine binding silently dropped the string element on the rendered DOM. AegisMark's `class: "action-band"` and `class: "journey-row"` weren't applying to the actual element classNames despite being on the wire.

### Fixed
- **Alpine `:class` binding** in `src/dazzle_ui/templates/workspace/_content.html` — array form `[obj, str]` was unreliable for the `card.css_class` string element. Replaced with explicit string output: `[card.css_class, transitionExpr].filter(Boolean).join(' ')`. Alpine now sets the className to a single concatenated string, unambiguous.

### Tests
- **`test_workspace_region_class.py`** extended to 20 cases (was 18): two new `TestCssClassTemplateBinding` cases — `test_template_binding_uses_string_concat_pattern` (static guard pinning the `.filter(Boolean).join(' ')` pattern) and `test_alpine_binding_simulation_includes_css_class` (pure-Python simulation of the binding evaluation that catches the `card.css_class` getting dropped at the test level).

### Agent Guidance
- **Static template-text assertions are insufficient for Alpine binding correctness.** The original v0.61.52 test only checked the BINDING TEXT was in the template — it didn't verify the binding actually applied at runtime. The new `test_alpine_binding_simulation_includes_css_class` mirrors the JS expression in Python and asserts the output includes the project class. Apply this pattern when adding any Alpine binding that author DSL feeds into.
- **Single-string output is more robust than array form for `:class` bindings.** Alpine v3's `:class="[obj, str]"` should work but had a silent-drop failure mode here. The `.filter(Boolean).join(' ')` pattern produces a single string output that Alpine unambiguously appends to the static `class=` attribute. Use this pattern when reactive content joins user-supplied strings.
- **Downstream-consumer feedback catches what synthetic tests miss.** v0.61.52 shipped with passing tests, but only AegisMark's real teacher_workspace caught the binding bug. The Python-simulation pattern adopted here is the cheapest mitigation; full Playwright validation of card rendering is a future improvement.

## [0.61.58] - 2026-04-27

Patch bump. **Fix #899** — keyword-shadowing regression introduced by the v0.61.52–v0.61.56 display-mode batch. Common identifier names (`primary`, `secondary`, `caption`, `actions`, `tone`, `stats`, `facts`, `track_max`, `track_format`, etc.) were unusable as enum literal values and field names in downstream projects. AegisMark hit this with `school_phase: enum[primary, secondary, all_through, special]` and had to pin back to v0.61.54.

### Fixed
- **`KEYWORD_AS_IDENTIFIER_TYPES` extended** in `src/dazzle/core/dsl_parser_impl/base.py` — added all 12 region-block tokens introduced across v0.61.52–v0.61.56:
  - `AVATAR_FIELD`, `PRIMARY`, `SECONDARY`, `STATS`, `FACTS` (v0.61.55, #892 profile_card)
  - `CAPTION` (v0.61.56, #890 pipeline_steps)
  - `ACTIONS`, `TONE`, `COUNT_AGGREGATE` (v0.61.54, #891 action_grid)
  - `TRACK_MAX`, `TRACK_FORMAT` (v0.61.53, #893 bar_track)
  - `CSS_CLASS` (v0.61.52, #894 region class hook)
- Same fix pattern as the v0.61.35 `DELTA` keyword fix — the tokens still function as region-block keys but the parser treats them as plain identifiers in expression / enum contexts.

### Tests
- **`tests/unit/test_keyword_as_identifier_regression.py`** (new) — 22 cases:
  - `TestSchoolPhaseEnumLiteral` (1): the canonical #899 repro — `enum[primary, secondary, all_through, special]` parses cleanly
  - `test_keyword_usable_as_enum_value` (11 parametrized): each new token round-trips as an enum literal value
  - `test_keyword_usable_as_field_name` (9 parametrized): each new token round-trips as a plain entity field name
  - `TestKeywordIdentifierListContainsNewTokens` (1): static invariant guard — if a future edit drops any of these tokens from `KEYWORD_AS_IDENTIFIER_TYPES`, this test fails loudly before the regression returns

### Agent Guidance
- **Adding a new lexer keyword? Add it to `KEYWORD_AS_IDENTIFIER_TYPES` at the same time.** Any keyword that names something authors would commonly use as a field or enum value (which is most of them) MUST be added to the list, otherwise downstream projects that already use the name break on upgrade. Pattern: keyword serves as a region-block key when it leads its line; identifier elsewhere (enum literals, field names, expressions). See `src/dazzle/core/dsl_parser_impl/base.py:488` for the list.
- **The `TestKeywordIdentifierListContainsNewTokens` invariant test is the second line of defence.** If you add a new region-block keyword that's lexer-tokenised but forget to register it in `KEYWORD_AS_IDENTIFIER_TYPES`, this static-source test catches it. Update the `required` list in the test in the same commit when adding new tokens.
- **Fix the regression class, not just the symptom.** v0.61.55–v0.61.56 each could have caught this individually, but it took a downstream consumer (AegisMark) to surface the pattern. The 22-case parametrized test now pins all 12 tokens at once — and any future region-block keyword should join the parametrize list.
- **Downstream consumer feedback is the real validation.** The display-mode batch shipped with passing CI on every patch; the regression only manifested when a real project (AegisMark) tried to upgrade. Add a "downstream-DSL smoke test" job to CI? Tracked as a future improvement — for now, `KEYWORD_AS_IDENTIFIER_TYPES` is the operative invariant.

## [0.61.57] - 2026-04-27

Patch bump. **CI fixes + security defence-in-depth + framework artefact coverage**. Closes the four CI failures introduced by the v0.61.52–v0.61.56 display-mode batch (absolute paths in tests, snapshot drift, ANSI in help text, framework coverage gate) plus a CodeQL XSS-through-DOM warning on the live theme switcher.

### Fixed
- **Absolute path in 6 test files** — `Path("/Volumes/SSD/Dazzle/...")` replaced with `Path(__file__).resolve().parents[2] / "..."` so tests pass on CI runners where the repo is at `/home/runner/work/dazzle/dazzle/`. Affected: `test_workspace_action_grid.py`, `test_workspace_pipeline_steps.py`, `test_workspace_profile_card.py`, `test_workspace_bar_track.py`, `test_workspace_region_class.py`, `test_workspace_scope_enforcement.py`.
- **Golden-master snapshot drift** — regenerated `test_simple_dsl_to_ir_snapshot.ambr` to reflect the new `WorkspaceRegion` fields landed across v0.61.52–v0.61.56 (`css_class`, `track_max`, `track_format`, `action_cards`, `avatar_field`, `primary`, `secondary`, `profile_stats`, `facts`, `pipeline_stages`).
- **`test_list_help_mentions_filters`** — Typer's help formatter inserts ANSI escape codes that split flag names across format runs in CI environments. Test now strips ANSI codes (`re.sub(r"\x1b\[[0-9;]*m", "", result.output)`) before substring assertion.

### Added
- **Framework artefact coverage to 100%** — added 4 region examples to `examples/ops_dashboard` so each new display mode (action_grid, bar_track, profile_card, pipeline_steps) has at least one live consumer in an example app:
  - `system_response_track` — bar_track of avg(response_time_ms) per system
  - `ops_actions` — action_grid with 2 CTAs (active alerts, add system)
  - `alert_pipeline` — 3-stage pipeline_steps for Alert lifecycle
  - `system_identity` — profile_card narrowed by `current_context`
- The framework artefact coverage gate at `src/dazzle/cli/coverage.py` was the source of CI's lint failure; coverage now reports 71/71 (100%) across display_modes, dsl_constructs, and fragment_templates.

### Security
- **CodeQL #81 (`js/xss-through-dom`)** — `dz-alpine.js`'s `dzThemeSwitcher.setTheme()` assigns server-emitted theme URLs to `link.href`. Even though the URL list comes from a server-rendered `<script type="application/json">` payload (not user input), CodeQL flagged the DOM sink. Added a defence-in-depth whitelist regex (`SAFE_THEME_URL = /^\/(?:static\/)?(?:css\/)?themes\/[\w-]+\.css$/`) that rejects any value not matching the expected theme-CSS shape — including `javascript:` / `data:` payloads that would otherwise reach the sink if the server-side payload were ever compromised.
- **CodeQL #78 dismissed** — `py/clear-text-logging-sensitive-data` in `ga4.py` was a false positive. The variable `_API_SECRET_ENV = "DAZZLE_GA4_API_SECRET"` is the env-var NAME (the string told to operators), not the secret VALUE. CodeQL matched on the lexical "SECRET" token in the variable name.
- **CodeQL #71-77, #79-80 dismissed** (9 alerts) — `py/incomplete-url-substring-sanitization` warnings in `tests/unit/test_analytics_*.py` and `test_tenant_analytics_resolver.py`. All test-only substring assertions checking that generated CSP/script-src URLs include known domains. Same rationale as previously-dismissed #66-70 for the same rule.

### Agent Guidance
- **Use `Path(__file__).resolve().parents[2]` for repo-root references in tests, not absolute paths.** The pattern derives the project root from the test file location, so tests pass on local dev (`/Volumes/SSD/Dazzle/`) and CI runners (`/home/runner/work/dazzle/dazzle/`) alike. When writing source-code-grep tests (static checks on the implementation), use this idiom.
- **Strip ANSI escape codes before substring-asserting on Typer help output.** Typer's formatter wraps flag names with colour/wrap escapes in CI environments. The pattern `re.sub(r"\x1b\[[0-9;]*m", "", output)` converts the help text to plain text for assertions.
- **Framework artefact coverage gate gates new display modes.** Any new `DisplayMode` enum value, DSL construct, or fragment template that lands without at least one example app exercising it fails CI at `python -m dazzle coverage --fail-on-uncovered`. When shipping a new display mode, add at least a minimal region in one of the example apps in the same commit.
- **Defence-in-depth whitelist for any DOM sink fed from server-emitted JSON.** Even when the source is server-rendered (and therefore not directly user-controlled), a tight regex at the assignment site closes both real attacks (server-side compromise) and CodeQL alerts. The pattern: parse → validate against shape → assign. The whitelist regex is part of the security contract; document the expected shape in a comment.
- **`_API_SECRET_ENV` naming guidance.** When a constant holds an env-var NAME for a secret (not the secret value itself), CodeQL's lexical pattern matcher will flag any log line that includes the constant. Two options: (a) rename the constant to drop "SECRET" from the local identifier, or (b) dismiss as false positive with a clear rationale. We chose (b) here because the constant name is meaningful to operators reading log messages.

## [0.61.56] - 2026-04-27

Patch bump. **Fix #890** — `display: pipeline_steps`. Sequential-stage workflow visualisation: a row of stage cards with arrow connectors. Each stage carries an independent aggregate query (RBAC scope rules apply per-stage). **Closes the AegisMark display-mode batch** — all 5 issues (#890–#894) shipped.

### Added
- **`DisplayMode.PIPELINE_STEPS = "pipeline_steps"`** in `src/dazzle/core/ir/workspaces.py`.
- **`PipelineStageSpec`** IR — frozen Pydantic model with `label` (required), `caption`, `aggregate_expr`.
- **`WorkspaceRegion.pipeline_stages: list[PipelineStageSpec]`** — empty list by default.
- **Lexer token** `CAPTION` in `src/dazzle/core/lexer.py`.
- **`_parse_pipeline_stages_block`** in `src/dazzle/core/dsl_parser_impl/workspace.py` — same dash-list shape as `actions:`. Each entry leads with `label:`; `caption:` and `aggregate:` are optional.
- **`stages:` shape dispatch** — the existing `STAGES` lexer token now triggers two parser paths based on the next token: `LBRACKET` → legacy progress-mode bracketed list (`stages: [a, b, c]`), `INDENT` → new pipeline_steps indented dash-list. **Backwards compatible** with all existing `progress` regions.
- **`RegionContext.pipeline_stages`** — list of dicts (`{label, caption, aggregate_expr}`) for the runtime branch to consume.
- **Runtime branch** in `src/dazzle_back/runtime/workspace_rendering.py` — fires one `_fetch_count_metric` per stage with non-empty `aggregate_expr` via `asyncio.gather`. Honours the #887 scope-deny gate. Stages with unsupported aggregates (median, avg, sum, min, max) render `—` in the MVP — only `count(...)` is wired through. Mirrors the action_grid pattern (#891).
- **Template** `src/dazzle_ui/templates/workspace/regions/pipeline_steps.html` — flex row of stage cards with SVG chevron connectors between (desktop) / vertical chevrons (mobile). Token-coloured. `region_card` macro wrapper for card safety.
- **Region-bodyless validation exemption** extended — `pipeline_stages` joins `action_cards` as a region body (no `source:`/`aggregate:` required at the top level when the region has its own stage-level aggregates).
- **`PipelineStageSpec`** exported from `dazzle.core.ir.__init__`.

### Tests
- **`tests/unit/test_workspace_pipeline_steps.py`** (new) — 15 cases:
  - `TestPipelineStepsParser` (5): minimal pipeline, label-only stage, multiple stages order, unknown key rejected, full repro DSL from issue
  - `TestStagesShapeDispatch` (2): legacy `stages: [...]` for progress mode still works AFTER the dispatch refactor; pipeline indented form parses as pipeline_stages (NOT progress_stages)
  - `TestPipelineStageSpec` (2): construct minimal, construct full
  - `TestPipelineStepsTemplateWiring` (5): template map, file existence, `region_card` macro, RegionContext default empty, RegionContext carries stages
  - `TestPipelineStepsBodyless` (1): no source/aggregate required at region level when stages provide the body

### Changed
- **`stages:` keyword is now polymorphic** — bracketed list for progress mode (legacy), indented dash-list for pipeline_steps (new). The shape detector keeps `progress` regions parsing identically to before.

### Agent Guidance
- **Per-stage aggregates fire concurrently.** Stages are independent; the runtime uses `asyncio.gather` so a 4-stage pipeline runs 4 parallel count queries. Single-batched query is a future optimisation; concurrency is fine for typical pipeline_steps scale (≤ 6 stages).
- **MVP supports `count(...)` per stage only.** The issue's example uses `median(Manuscript.computed_grade)` — that aggregate isn't in the count/sum/avg/min/max vocabulary today and renders `—`. Adding median is a separate scope-of-work; sum/avg/min/max would route through `_fetch_scalar_metric` (already exists from #888 Phase 1) but isn't wired through the pipeline_steps branch yet — small follow-up if a real consumer asks.
- **Region-bodyless validation now covers two display modes.** action_grid (#891) and pipeline_steps (#890) both populate the region's "body" via stage/card lists rather than `source:` or `aggregate:`. When adding a third such display mode, extend the exemption check at `workspace.py:_parse_workspace_region` to include the new field.
- **Reserved-keyword footgun for region names.** `flow`, `class`, `scope`, etc. are reserved tokens — don't use them as region names. Tests should use unambiguous names like `pipeline`, `cards`, `metrics`. (Discovered while writing pipeline_steps tests; the parser error "Expected DEDENT, got <keyword>" is the symptom.)
- **AegisMark display-mode batch complete.** v0.61.52–v0.61.56 deliver region `class:` (#894) + bar_track (#893) + action_grid (#891) + profile_card (#892) + pipeline_steps (#890). Combined: a project can compose AegisMark-style teacher dashboards (pupil-identity sidebar + journey-row pipeline + action-band CTAs + per-AO confidence-stack) using only DSL primitives — no template forking needed.

## [0.61.55] - 2026-04-27

Patch bump. **Fix #892** — `display: profile_card`. Single-record identity panel: avatar (img or initials fallback) + primary name + secondary meta line + 3-up stat grid + bulleted facts list. Resolves a single record (typically via `filter: id = current_context`) and supports tiny `{{ field }}` / `{{ field.path }}` interpolation in `secondary` and `facts` strings — server-side, no Jinja eval.

### Added
- **`DisplayMode.PROFILE_CARD = "profile_card"`** in `src/dazzle/core/ir/workspaces.py`.
- **`ProfileCardStatSpec`** IR — frozen Pydantic model with `label` + `value` (field name or dotted path).
- **`WorkspaceRegion`** new fields:
  - `avatar_field: str | None` — column name for the avatar URL
  - `primary: str | None` — column name for the primary identity heading
  - `secondary: str | None` — quoted-string template (interpolated)
  - `profile_stats: list[ProfileCardStatSpec]` — stat grid entries
  - `facts: list[str]` — bulleted-list templates (interpolated)
- **Lexer tokens** `AVATAR_FIELD`, `PRIMARY`, `SECONDARY`, `STATS`, `FACTS` in `src/dazzle/core/lexer.py`.
- **`_parse_profile_stats_block`** + **`_parse_facts_block`** in `src/dazzle/core/dsl_parser_impl/workspace.py` — same dash-list shape as `actions:`.
- **Tiny safe interpolator** in `src/dazzle_back/runtime/workspace_rendering.py`:
  - `_resolve_path(item, path)` — walks dotted paths against an item dict
  - `_initials_from(name)` — first-letter-of-up-to-2-words fallback for the avatar
  - `_interpolate_card_template(tmpl, item)` — `re.sub` over `{{ IDENT(.IDENT)* }}` only. **No Jinja eval, no expressions, no filters.** FK dicts auto-resolve via the `__display__` chain (mirrors heatmap/box_plot). Unresolved paths render empty.
- **Runtime branch** for `display == "PROFILE_CARD"` — takes the first item from the standard fetch, builds `profile_card_data` dict (avatar_url, initials, primary, secondary, stats, facts) for the template.
- **Template** `src/dazzle_ui/templates/workspace/regions/profile_card.html` — flex identity row + grid stats (1 col mobile / 3 col desktop) + bulleted facts list, all design-token colours, `region_card` wrapper for card safety.
- **`ProfileCardStatSpec`** exported from `dazzle.core.ir.__init__` for downstream consumers.

### Tests
- **`tests/unit/test_workspace_profile_card.py`** (new) — 31 cases:
  - `TestProfileCardParser` (6): minimal, secondary template, stats block, dotted-path stat values, facts block, full repro DSL from issue
  - `TestInterpolateCardTemplate` (9): simple field, dotted path, multiple fields, missing field renders empty, missing dotted-path renders empty, FK dict resolves via `__display__`, empty template, no-placeholders pass-through, **unsafe-expression-left-as-literal** (key safety invariant)
  - `TestInitialsFrom` (5): two-word, three-word caps at two, single-word, empty, lowercase uppercased
  - `TestResolvePath` (5): single-segment, dotted path, missing segment, descend into non-dict, empty path
  - `TestProfileCardTemplateWiring` (5): template map, file existence, `region_card` macro, RegionContext fields, ProfileCardStatSpec construct
  - `TestProfileCardSafety` (1): static-source guard pinning that the interpolator uses `re.sub`, never Jinja eval

### Agent Guidance
- **Logic-less template by design.** The template renders pre-resolved strings via the standard Jinja autoescape pipeline. All `{{ ... }}` expansion happens server-side in `_interpolate_card_template` via a strict `IDENT(.IDENT)*` regex — never Jinja's expression parser. Pipe filters (`{{ a | upper }}`), arithmetic (`{{ a + 1 }}`), and function calls aren't supported and are left as literal placeholders so authors notice. **Critically: never eval'd**, so the surface for template injection from author DSL is zero.
- **FK dict resolution is automatic in interpolation.** A single-segment path like `{{ tutor }}` against an FK dict resolves via the `__display__` → `name` → `title` → `code` → `label` chain (same precedence as heatmap/box_plot). Authors can write `{{ tutor }}` for the display name OR `{{ tutor.full_name }}` for an explicit field — both work.
- **Unresolved paths render empty, not "None" or error.** A missing path renders an empty string, so cards with one missing field still render the rest. This trades visibility-of-bugs for graceful degradation; combined with the literal-passthrough for unsafe expressions, authors get clear feedback on syntax errors but smooth handling of optional fields.
- **Single-record fetch.** profile_card uses the standard region fetch path with `filter:` narrowing to one row. The runtime takes `items[0]`. Authors should pair `display: profile_card` with `filter: id = current_context` (or another single-record predicate) — pagination doesn't apply.
- **Foundation chain complete.** v0.61.52 (#894 region `class:`) + v0.61.53 (#893 bar_track) + v0.61.54 (#891 action_grid) + v0.61.55 (#892 profile_card) deliver the four AegisMark-prototype primitives. Combined: a project can compose a per-pupil dashboard from a `profile_card` sidebar, an `action_grid` CTA strip, multiple `bar_track` confidence rows, all branded via region-level `class:` hooks. Only #890 (pipeline_steps) remains in this batch.

## [0.61.54] - 2026-04-27

Patch bump. **Fix #891** — `display: action_grid`. CTA cards on dashboards: each card has a label, optional icon (Lucide), optional count badge driven by an aggregate, and a click target resolved to a URL. Tone tokens (positive/warning/destructive/neutral/accent) map to design palette. Foundation pattern for "things the user can do next" surfaces.

### Added
- **`DisplayMode.ACTION_GRID = "action_grid"`** in `src/dazzle/core/ir/workspaces.py`.
- **`ActionCardSpec`** IR — frozen Pydantic model with `label` (required), `icon`, `count_aggregate`, `action`, `tone` (defaults `neutral`).
- **`WorkspaceRegion.action_cards: list[ActionCardSpec]`** — empty list by default; populated by the parser when `actions:` block is present.
- **Lexer tokens** `ACTIONS`, `TONE`, `COUNT_AGGREGATE` in `src/dazzle/core/lexer.py`.
- **`_parse_action_cards_block`** in `src/dazzle/core/dsl_parser_impl/workspace.py` — indented dash-list parser mirroring `_parse_overlay_series_block`. Each entry must lead with `label:`. Sub-keys: `icon` (string), `count_aggregate` (token-stream), `action` (string OR identifier — string required for URLs containing `?`/`/`/`=`), `tone` (whitelisted to {positive, warning, destructive, neutral, accent}).
- **`_action_to_url(action: str)`** helper in `workspace_renderer.py` — bare identifiers slugify to `/app/<slug>` (with optional `?query` preserved); paths starting with `/` pass through verbatim.
- **`RegionContext.action_cards`** — list of dicts (`{label, icon, count_aggregate, url, tone}`) with `url` pre-resolved at context build time.
- **Runtime branch** in `src/dazzle_back/runtime/workspace_rendering.py` — fires one `_fetch_count_metric` per card with non-empty `count_aggregate` via `asyncio.gather` (single batched query is a future optimisation). Honours scope-deny gate from #887: when scope denies, cards still render but counts are suppressed.
- **Template** `src/dazzle_ui/templates/workspace/regions/action_grid.html` — responsive 1/2/3 grid of token-coloured cards with Lucide icon (`data-lucide="<name>"`) + count badge. Region-bodyless validation exemption added to parser (#891-aware: action_cards counts as a body alongside source/aggregate).
- **`ActionCardSpec`** exported from `dazzle.core.ir.__init__` for downstream consumers.

### Tests
- **`tests/unit/test_workspace_action_grid.py`** (new) — 20 cases:
  - `TestActionGridParser` (8): minimal DSL, label-only defaults, multiple cards order, action accepts quoted-string-with-query, action accepts bare identifier, invalid tone rejected, unknown key rejected, must-start-with-label
  - `TestActionToUrl` (4): empty input, slugify bare identifier, literal URL passes through, bare-with-query preserves query
  - `TestActionGridContext` (3): RegionContext default empty, carries cards, ActionCardSpec defaults
  - `TestActionGridTemplateWiring` (4): template map, file exists, region_card macro, no interpolated tag names (XSS guard)
  - `TestActionGridIsCountOnly` (1): IR accepts any aggregate text — runtime gates count-only

### Changed
- **Region body validation** (`workspace.py`) now treats `action_cards` as a valid region body alongside `source:` and `aggregate:`. action_grid regions are static-CTA-driven and don't need a data source.

### Security
- **Static-template guard test** pins that `action_grid.html` does NOT use Jinja-interpolated HTML tag names (`<{{ _Tag }}>`). The first draft tripped a Semgrep XSS warning; fixed by explicit `{% if card.url %}<a>{% else %}<div>{% endif %}` branches with body duplication. Test prevents regression.

### Agent Guidance
- **action_grid is a NEW region shape — not aggregate-derived data, but author-declared CTAs.** Each card carries its own count_aggregate (independent query) rather than slicing a shared bucketed aggregate. This trades batching opportunity for vocabulary cleanliness — single batched query when all cards share the same source entity is a future optimisation noted in the issue.
- **Tone vocabulary is whitelisted.** Five tokens — `positive`, `warning`, `destructive`, `neutral`, `accent` — map to design palette via `_tone_classes` in the template. Add new tones at both the parser whitelist AND the template map; don't let either drift.
- **Action target resolution is intentionally simple.** `_action_to_url` slugifies bare identifiers + preserves literal URLs. Surface-name → URL coupling deferred (would need surface metadata lookup) — for the MVP, authors who need surface-aware resolution can write the literal path: `action: "/app/parents-evening/create"`.
- **Scope-deny invariant from #887 extends to action_grid.** When the active persona has scope denied, cards still render (they're static UI elements) but counts are suppressed — same posture as the chart aggregate gates.
- **Foundation chain.** Combined with #894 (region `class:` hook) and #893 (bar_track), authors can compose dashboards from action-band-style CTAs without reinventing per-app templates: `display: action_grid` + `class: "action-band"` for project-specific styling.

## [0.61.53] - 2026-04-27

Patch bump. **Fix #893** — `display: bar_track`. Compact horizontal value bars (per-row label + filled track + numeric) — pill-shaped tracks ideal for "AO score per pupil" or "feature adoption per cohort" cards. Reuses the existing single-dim chart pipeline for data, so existing `group_by` + `aggregate:` vocabulary works unchanged; only `track_max:` and `track_format:` are bar_track-specific.

### Added
- **`DisplayMode.BAR_TRACK = "bar_track"`** in `src/dazzle/core/ir/workspaces.py`.
- **`WorkspaceRegion.track_max: float | None`** — fill denominator. `None` means auto (max of bucketed values, falls back to 1.0 for the all-zero edge case to avoid div-by-zero).
- **`WorkspaceRegion.track_format: str | None`** — Python format spec applied server-side via `format()` or `str.format()`. Accepts both styles transparently: `".0%"` (bare spec, passed to `format()`) and `"{:.0%}"` (str.format template, used as-is). Authors can copy from f-string code without re-learning vocabulary.
- **Lexer tokens** `TRACK_MAX` + `TRACK_FORMAT` in `src/dazzle/core/lexer.py`. Parser branches accept numeric for `track_max:` and quoted-string-only for `track_format:` (format specs commonly contain `:` and `{}` that don't tokenise as bare identifiers).
- **`RegionContext.track_max` / `track_format`** in `src/dazzle_ui/runtime/workspace_renderer.py` — flows IR → render context.
- **Runtime branch** in `src/dazzle_back/runtime/workspace_rendering.py` — adds `BAR_TRACK` to `_single_dim_chart_modes` so the existing `_compute_bucketed_aggregates` machinery fires unchanged. Post-processes `bucketed_metrics` into `bar_track_rows` with `fill_pct` (clamped to [0, 100] — values above max clamp; negatives clamp to 0) and `formatted_value` (format spec applied with graceful fallback to raw `str()` on malformed spec).
- **Template** `src/dazzle_ui/templates/workspace/regions/bar_track.html` — pill-shaped track using design tokens (`hsl(var(--muted))` + `hsl(var(--primary))`), ARIA `progressbar` semantics, server-rendered formatted values. Card safety: zero chrome + zero title — wrapped in the `region_card` macro per the dashboard slot contract.

### Tests
- **`tests/unit/test_workspace_bar_track.py`** (new) — 23 cases across 3 classes:
  - `TestBarTrackParser` (6 cases): minimal DSL, `track_max:` parses, int → float coercion, `track_format:` parses, must-be-quoted enforcement, full repro DSL from the issue
  - `TestBarTrackPostProcessing` (11 cases): explicit max → fill_pct, auto-max scaling, format spec applied (both `{:.0%}` and bare `.0%` styles), thousands separator, no-format default, malformed spec falls back, value > max clamps to 100%, negative → 0%, empty buckets, zero value, non-numeric coerces to 0
  - `TestBarTrackTemplateWiring` (6 cases): template map registration, file existence, `region_card` macro use, RegionContext fields, single-dim mode set membership

### Agent Guidance
- **Bar_track reuses bar_chart's data path.** When adding similar single-dim chart modes, prefer extending the existing `_compute_bucketed_aggregates` pipeline with a new template + post-processing step over building a parallel data path. The split is intentional: data shape is shared (`bucketed_metrics`); presentation is per-template.
- **Format specs accept both styles.** `track_format: ".0%"` and `track_format: "{:.0%}"` produce identical output. The runtime detects `{` in the spec and routes to `str.format()` if present; otherwise to `format()`. Authors can copy from f-strings without translation.
- **Server-side formatting, not Jinja.** `formatted_value` is computed in Python before the template renders so author intent (`"{:,.0f}"`, `"{:.0%}"`) works without Jinja filter gymnastics. Side benefit: a malformed format spec logs a warning + falls back to raw `str()` rather than crashing the dashboard.
- **Foundation chain.** Combined with #894 (region `class:` hook), authors can ship a "kpi-strip" cluster of bar_track regions with project-specific styling: `display: bar_track` + `class: "kpi-strip dense"` for a tight, branded layout.

## [0.61.52] - 2026-04-27

Patch bump. **Fix #894** — region-level `class:` field. DSL authors can now attach a project-supplied CSS hook to any workspace region's outer card wrapper without forking templates or relying on heuristic class hooks.

### Added
- **`WorkspaceRegion.css_class: str | None`** in `src/dazzle/core/ir/workspaces.py` — IR field. Default `None`. Naming follows the `from`/`to` → `from_value`/`to_value` precedent on `ReferenceBand`: user-facing keyword is `class:` (matches HTML); Python field name is `css_class` to avoid the keyword collision.
- **`TokenType.CSS_CLASS = "class"`** in `src/dazzle/core/lexer.py` — lexer token for the new keyword.
- **Parser branch** in `src/dazzle/core/dsl_parser_impl/workspace.py` — accepts both bare-identifier (`class: highlight`) and quoted-string (`class: "metrics-strip dense"`) forms. Quoted form required for kebab-case / multi-class — bare form constrained to Python-identifier shapes (lexer treats `-` as operator everywhere in the DSL).
- **`RegionContext.css_class: str = ""`** in `src/dazzle_ui/runtime/workspace_renderer.py` — flows the value from IR to the rendering context. Empty string when not set.
- **`cards_for_json` payload extension** in `src/dazzle_ui/runtime/page_routes.py` — each card dict now carries `css_class` so the Alpine card-grid template can bind it without import dance.
- **Template binding** in `src/dazzle_ui/templates/workspace/_content.html` — the outer card wrapper's `:class` array now includes `card.css_class || ''`, composing with the existing transition/drag-state binding rather than replacing it.

### Tests
- **`tests/unit/test_workspace_region_class.py`** (new) — 18 cases across 4 classes:
  - `TestCssClassParser` (5 cases): default-None, bare identifier, quoted multi-class, BEM-style classes, no-clobber-other-fields
  - `TestRegionContextCssClass` (3 cases): default empty string, value carried, card payload includes hook
  - `TestCssClassTemplateBinding` (1 case): static template check pins the Alpine binding
  - `TestCssClassIsPresentationOnly` (9 parametrized + 1 case): scope/data fields unaffected; bare and quoted form variants

### Agent Guidance
- **Pure presentation hook — no semantic impact.** `css_class` doesn't affect data, scope, RBAC, or any non-render behaviour. The `TestCssClassIsPresentationOnly` class pins this invariant; respect it when extending the field (e.g. don't tee it into RegionContext.filter_expr).
- **Naming convention for keyword/Python collisions.** When a DSL keyword would shadow a Python keyword, follow the `class` → `css_class` (and `from`/`to` → `from_value`/`to_value`) pattern: keep the user-facing DSL string natural; alias to a Python-safe field name in the IR. Update Pydantic Field aliases when the IR uses Pydantic models for parsing.
- **Bare vs quoted identifier.** The lexer treats `-` as an operator throughout the DSL — kebab-case identifiers always need the quoted-string form. This is a global constraint, not specific to `class:`. The parser tests pin both shapes for documentation.
- **Foundation for the new display modes.** Issues #890–#893 (pipeline_steps / action_grid / profile_card / bar_track) will land their own templates that render inside the same card wrapper — they automatically pick up the `css_class` hook with no additional work.

## [0.61.51] - 2026-04-27

Patch bump. **Fix #888 (Phase 1)** — reporting predicate algebra unification. Aggregate where-clauses now route through the same structured predicate algebra used by RBAC scope rules, closing three long-standing gaps: column-vs-column comparisons, OR clauses, and proper sum/avg/min/max with where-clauses.

### Added
- **`ColumnRefCheck` predicate node** in `src/dazzle/core/ir/predicates.py` — same-row column-vs-column comparison (e.g. `latest_grade >= target_grade`). Distinct from `ColumnCheck` (column vs literal) and `UserAttrCheck` (column vs subject attribute) — neither covers same-row column pairs. Not used by RBAC scope rules; reporting-only.
- **`_compile_column_ref_check` in the predicate compiler** — emits `"f1" op "f2"` with no parameters (both sides are quoted identifiers — same SQL safety as `ColumnCheck`).
- **`src/dazzle_back/runtime/aggregate_where_parser.py`** — recursive-descent parser. Grammar: `expr := or_expr; or_expr := and_expr ('or' and_expr)*; and_expr := not_expr ('and' not_expr)*; not_expr := 'not' atom | atom; atom := '(' expr ')' | comparison`. Disambiguates column-vs-column from column-vs-literal by checking the RHS identifier against known entity columns.
- **`_build_aggregate_filters` helper** in `workspace_rendering.py` — orchestrator: parse → compile → AND-compose with existing `__scope_predicate` → return filter dict ready for `Repository.list` / `Repository.aggregate`. Falls back to legacy `_parse_simple_where` for clauses the new grammar doesn't accept (e.g. hyphenated UUIDs from `current_bucket` substitution), preserving all pre-existing behaviour.
- **`_fetch_scalar_metric`** — routes `sum/avg/min/max` aggregates through `Repository.aggregate` with no dimensions and a single non-count measure. Pre-fix, scalar aggregates with where-clauses silently produced 0 in `_compute_aggregate_metrics`.

### Fixed
- **`count(StudentProfile where latest_grade >= target_grade)`** now returns the correct count instead of always-zero (the legacy parser produced `WHERE latest_grade >= 'target_grade'` — literal string comparison).
- **`count(X where flagged = true or confidence < 0.7)`** now honours the OR (legacy parser silently dropped the `or` because it split by ` and `).
- **`avg(field where ...)` / `sum(field where ...)`** now compute against the DB instead of resolving to 0.
- **Range predicates** (`field >= a and field < b`) now keep numeric type in parameters instead of stringifying.

### Tests
- **`tests/unit/test_aggregate_where_parser.py`** (new) — 27 cases covering the parser (literals, identifiers, AND/OR/NOT, parens, precedence), error paths (unbalanced parens, unknown ops, garbage RHS), SQL round-trip per #888 sub-feature, and `_build_aggregate_filters` integration (scope merge, column-vs-column, fallback to legacy parser).

### Agent Guidance
- **One predicate algebra, two consumers.** RBAC scope rules and reporting where-clauses now share the same `ScopePredicate` algebra, the same `compile_predicate` SQL emitter, and the same composition rules at the QueryBuilder boundary. When adding a new aggregate/predicate feature, extend the algebra rather than the parser-of-the-day. See `dev_docs/2026-04-27-reporting-predicate-algebra.md` for the unification design.
- **`__scope_predicate` is the single composition slot.** When two predicates need to apply (RBAC scope + aggregate where), AND-compose them at the SQL fragment level inside `_build_aggregate_filters` and emit one combined `__scope_predicate` tuple. Don't extend QueryBuilder to stack predicate slots — composition at the algebra/SQL level keeps QueryBuilder's contract simple.
- **Legacy fallback is intentional.** `_build_aggregate_filters` falls back to `_parse_simple_where` when the new algebra grammar can't tokenise the input. This handles edge cases like hyphenated UUIDs from `current_bucket` substitution without forcing every existing call site to migrate. Phase 2 may revisit if the legacy parser becomes maintenance burden.
- **Phase 2 is a follow-up, not a blocker.** Phase 1 closes #888 by enabling the predicate forms in the issue's repros. Phase 2 (migrate the DSL `scope:` block parser to share the same text→algebra parser) and Phase 3 (static where-clause validation against the FK graph) are pure consolidation — same SQL output either way.

## [0.61.50] - 2026-04-27

Patch bump. **Fix #889** — `box_plot` with `group_by: <fk_column>` now renders one bucket per FK value (labelled with the resolved display name) instead of collapsing to one bucket whose label is the FK dict's `str()` repr.

### Fixed
- **`_compute_box_plot_stats`** — bucket key resolution now follows the same pattern as heatmap (lines 1058-1074): prefer the `{group_by}_display` sibling injected by `_inject_display_names()`, fall back to `_resolve_display_name(item.get(group_by))`. Pre-fix the code did `str(item.get(group_by, ""))` which produced `"{'id': 'uuid…', '__display__': 'AO1'}"` for FK fields — one bucket, dict-repr label.
- **`BOX_PLOT` added to the limit-boost set** in `_workspace_region_handler` — joins KANBAN / BAR_CHART / FUNNEL_CHART so a paginated default fetches up to 200 items rather than the standard page size, ensuring all FK-distinct values surface as buckets.

### Tests
- **`test_workspace_box_plot.py`** extended to 19 cases (was 16): three new `TestComputeBoxPlotStats` cases — `test_fk_dict_uses_display_sibling_for_bucket_label` (the canonical pre-fix repro), `test_fk_dict_falls_back_to_resolve_display_name_without_sibling` (defensive path when display sibling absent), `test_scalar_group_by_still_works` (scalar `group_by: status` regression guard).

### Agent Guidance
- **Bucket-label resolution for FK columns is a shared pattern.** Heatmap (1058-1074) had it right; box_plot didn't. Any new chart with `group_by: <fk_column>` must consult `{group_by}_display` first and fall back to `_resolve_display_name()` — never rely on `str(item.get(group_by))` for FK columns. If a future chart mode ships, audit it for the same probe order.
- **Limit-boost belongs to any chart that distributes across buckets.** KANBAN / BAR_CHART / FUNNEL_CHART / BOX_PLOT all need ≥200 items to surface all FK values without pagination dropping buckets. New chart modes that bucket on a categorical column (RADAR is debatable, single-dim charts that LIMIT 20 implicitly) should be added to this set.

## [0.61.49] - 2026-04-27

Patch bump. **Security fix #887** — chart aggregations were bypassing the workspace scope-deny gate, leaking cross-tenant counts / sums / averages from `_compute_aggregate_metrics`, `_compute_bucketed_aggregates`, `_compute_pivot_buckets`, and the line/area overlay loop. The list-items path correctly returned an empty result on denial; the parallel aggregate paths ran unfiltered SQL and exposed totals across all tenants.

### Security
- **Default-deny scope state in `_workspace_region_handler`** — `_scope_only_filters` and `_scope_denied` are now initialized to `(None, True)` BEFORE the `if repo:` block, so any failure path that skips scope evaluation (no repo, early exception) surfaces as a denial rather than silently dropping into unfiltered aggregates.
- **Aggregate gate at every call site** — `_compute_aggregate_metrics`, `_compute_bucketed_aggregates` (single-dim), the `_ir_overlays` loop's `_compute_bucketed_aggregates` (overlays), and `_compute_pivot_buckets` (multi-dim) all now check `not _scope_denied` before firing. Each comment cites #887 so future edits don't strip the guard accidentally.
- **`_fetch_region_json` (batch handler) parity fix** — pre-init mirrors the primary handler, scope-only filters captured separately and propagated to `_compute_aggregate_metrics(scope_filters=...)`. Pre-fix, the batch handler ran aggregates with no filter at all AND no denial check.

### Tests
- **`test_workspace_scope_enforcement.py`** extended to 15 cases (was 12): new `TestAggregateScopeGate` class — `test_default_deny_initial_state_blocks_aggregates` (source-level invariant pinning the default-deny pre-init), `test_aggregate_call_sites_gated_on_scope_denied` (counts ≥4 `not _scope_denied` guards across the handler), and `test_apply_workspace_scope_filters_returns_denied_for_unmatched_role` (upstream signal the gates depend on). Pure source / boolean checks — fast and don't depend on the full handler stub stack.

### Agent Guidance
- **Aggregate paths must gate on `_scope_denied`, not just merge `_scope_only_filters`.** Pre-fix, the contract was "if scope produces a filter, merge it; else run unfiltered" — that conflates "no scope rule needed" (legitimate admin) with "scope rule didn't match" (default-deny). The fix makes denial a separate boolean. When adding new chart / metric / aggregate code paths, the contract is: **no aggregate fires unless `_scope_denied is False`**.
- **Default-deny is the safe init.** The pre-init for `_scope_denied` is `True` so any failure path before scope evaluation defaults to "no aggregates ran" rather than NameError-or-silent-bypass. New helper functions that compute aggregates from `ctx` should mirror this init pattern.
- **Static-source invariant tests are cheap and effective for security gates.** When a fix is "guard X must be present at call sites Y", a regex/substring check on the source catches future edits that strip the guard. Faster than building a stub stack and avoids the testing-the-mock anti-pattern.

## [0.61.48] - 2026-04-26

Patch bump. **Phase C Patch 4** — unified site + app-shell theme manifest. An app theme can now declare a `[site]` section in its TOML to set the legacy `ThemeSpec` preset and per-token overrides for site/marketing-page rendering. One theme file → both layers configured.

### Added
- **`AppThemeManifest.site_preset: str | None`** — legacy `ThemeSpec` preset name (one of saas-default, minimal, corporate, startup, docs) used for site-page rendering when this theme is active.
- **`AppThemeManifest.site_overrides: dict[str, Any]`** — token overrides applied on top of `site_preset`. Mirrors the structure of legacy `[theme.colors]` etc. blocks. Supported categories: `colors`, `shadows`, `spacing`, `radii`, `custom`.
- **`[site]` table parsing** in `app_theme_registry._parse_manifest` — reads optional `preset` plus per-category overrides, validates types and rejects unknown keys. Themes that omit `[site]` get `(None, {})` and the runtime falls back to `[theme]` from `dazzle.toml` as before.
- **`resolve_site_config(name, project_root)`** — walks the inheritance chain (Phase C Patch 1) so a child theme inherits its parent's `[site]` config without restating it. Cascade: parent values fill in first, child shallow-merges on top (child preset wins; per-category dicts merge by key).
- **Runtime wiring** in `serve.py` — when an app theme is active (env / DSL / `[ui] app_theme`), `resolve_site_config` overlays its preset + token categories on the `theme_overrides` baseline derived from `dazzle.toml`'s `[theme]` block.

### Tests
- **`test_app_theme_registry.py`** extended to 47 cases (was 35): 6 new `TestSiteSection` cases covering parsing (no section / preset only / per-category overrides) and validation (`[site]` must be table, `preset` must be string, unknown category rejected); 6 new `TestResolveSiteConfig` cases covering resolution (None name, unknown theme, no section, single theme, parent inheritance, child override).

### Agent Guidance
- **One theme file, two layers.** Authors of new themes can configure both the app shell (`<name>.css` shadcn-shape tokens) and the site/marketing pages (`[site]` block in `<name>.toml`) in one place. Existing legacy `[theme]` blocks in `dazzle.toml` keep working — they're the baseline that any active app theme's `[site]` overlays.
- **Site overrides are shallow-merge per category.** When parent and child both declare `[site.colors]`, the result is the parent's colors with child's keys overlaid — not a wholesale replacement. Same for `spacing`, `radii`, `shadows`, `custom`. The preset is replaced (not blended); a child can switch the parent's `corporate` to `minimal` cleanly.
- **Backwards compat**: every existing project + theme keeps working. The 3 shipped themes (linear-dark / paper / stripe) ship without `[site]` so they don't disturb anyone's existing site config. `[theme]` in `dazzle.toml` is still the canonical site config when no app theme is active or when the active theme has no `[site]` section.
- **Phase D leftovers**: per-theme Tailwind plugin support remains deferred. Phase C is now complete (Patches 1–4 shipped: extends, template overrides, live switching, unified manifest).

## [0.61.47] - 2026-04-26

Patch bump. **Phase C Patch 3** — live theme switching via the `dzThemeSwitcher` Alpine component. Users can switch between any installed theme at runtime without a page reload; the choice persists across sessions via `dzPrefs` (server-backed) with `localStorage` fallback.

### Added
- **`_app_theme_map` Jinja global** — built at startup in `system_routes.py` from `discover_themes()`, mapping every available theme name to its full cascade-order URL chain (resolves each theme's `extends` chain individually). Emitted as `<script type="application/json" id="dz-app-themes">` in `base.html`.
- **`<html data-theme-name="...">` attribute + `<link data-theme-link="...">` markers** — give the switcher a stable target for swapping out the active chain's `<link>` elements.
- **`dzThemeSwitcher` Alpine component** in `dz-alpine.js` — exposes `setTheme(name)` which removes the existing `data-theme-link` elements, injects the new chain in cascade order, updates `<html data-theme-name>`, persists, and dispatches a `dz:theme-changed` window event for downstream observers. `init()` restores the persisted choice on load.
- **Persistence layer** — prefers `window.dzPrefs.set("ui.theme", name)` (already wired for other prefs); falls back to `localStorage["dz:theme"]`. Symmetric read order in `_readPersisted()`.

### Tests
- **`test_app_theme_loading.py`** extended to 39 cases (was 33): 6 new `TestThemeSwitcherWiring` cases — `<html>` carries `data-theme-name`; attribute omitted when no theme; theme `<link>` carries `data-theme-link` marker; theme map emitted as JSON script with full registry; map omitted when empty; chain links share the marker so the switcher swaps the entire chain.

### Agent Guidance
- **Theme switching is live — no reload, no rebuild.** The full per-theme URL chain is precomputed server-side at startup and shipped inline as JSON. The switcher just rewrites `<head>` `<link>` elements; browser handles the cascade. Cost is one HTTP round-trip per chain entry on switch (cached after first switch); zero cost when the user doesn't switch.
- **Persistence priority is `dzPrefs` first, then `localStorage`.** This matches existing pref handling in dz-alpine.js (e.g. tone, motion). When `dzPrefs` isn't on the page (anonymous routes, error pages), `localStorage` keeps the choice for the current browser. Reading goes the same direction so a logged-in user's server pref always wins over a stale anon localStorage value.
- **`dz:theme-changed` event is the integration point for theme-aware components.** Any component that needs to recompute layout or recolor (e.g. canvas-based widgets, dynamically-styled SVGs) should subscribe to `window.addEventListener("dz:theme-changed", ...)`. The event detail carries `{name, chain}` so subscribers don't have to re-query.
- **Switcher only swaps app theme, not site theme.** Two separate concerns: `<link data-theme-link>` is the app-shell theme (Phase B/C); `<link data-site-theme>` (if any) is the legacy site preset. The switcher targets only `data-theme-link`.

## [0.61.46] - 2026-04-26

Patch bump. **Phase C Patch 2** — component-level template overrides. Themes can now ship `<theme-name>/templates/<path>.html` overrides alongside their CSS to change template SHAPE (not just tokens). E.g. paper-theme can ship a `card_wrapper.html` with double border for paper-stack effect that no token shift can produce.

### Added
- **`AppThemeManifest.templates_dir: Path | None`** — resolved at registry-load time. Convention: a sibling directory matching the CSS filename stem with a `templates/` subdir. CSS-only themes leave it `None` and cost zero (the loader chain stays unchanged).
- **`add_theme_template_dirs(dirs)`** in `template_renderer.py` — prepends theme template dirs to the Jinja loader chain so theme templates win over project + framework. Idempotent; skips non-existent dirs; orders dirs leaf-wins (matches the cascade-order intent of the chain resolver).
- **Runtime wiring** — when the inheritance chain resolves, `system_routes.py` collects each theme's `templates_dir` and calls `add_theme_template_dirs` once at startup.

### Tests
- **`test_app_theme_registry.py`** extended to 35 cases (was 28): 7 new cases across `TestThemeTemplatesDir` (3 — None when absent for shipped themes; resolved when present in the conventional layout; bare `<theme>/` dir without `templates/` resolves to None) and `TestAddThemeTemplateDirs` (4 — theme template overrides framework; empty list is no-op; non-existent dirs skipped; chain order leaf-wins).

### Agent Guidance
- **Theme template directory convention** — `<themes_dir>/<name>/templates/<framework_path>.html`. Sibling to the CSS file, directory named for the theme. The framework template at `workspace/regions/card_wrapper.html` is overridden by `<themes_dir>/paper/templates/workspace/regions/card_wrapper.html`. The `templates/` subdir is required (not just `<themes_dir>/<name>/`) so the registry can distinguish theme-template themes from theme-asset themes (Phase D may add `assets/` for fonts, images, etc.).
- **Theme template overrides participate in the same precedence as project templates.** Cascade order: theme (leaf) → theme (root) → ... → project → framework. Within a theme chain, the leaf wins for same-name templates (the CSS cascade analogue).
- **Adding a `templates/` dir to an existing theme is safe** — registry picks it up at next startup; no migration. The 3 shipped themes (linear-dark/paper/stripe) ship CSS-only; future patches could add template overrides where tokens aren't enough (e.g. paper-stack card edge).
- **Loader cache** — `add_theme_template_dirs` mutates the singleton env. Tests that assert specific loader behaviour need to reset `tr._env = create_jinja_env()` before AND after to keep the suite hermetic — the `TestAddThemeTemplateDirs` cases follow this pattern.

## [0.61.45] - 2026-04-26

Patch bump. **Phase C Patch 1** — theme inheritance via `extends = "<parent>"` in the manifest TOML. A project variant can now ship just its delta on top of a baseline theme without copy-pasting the full token set.

### Added
- **`AppThemeManifest.extends: str | None`** — manifest field naming the parent theme.
  ```toml
  # themes/cyan-tweak.toml
  name = "cyan-tweak"
  extends = "linear-dark"
  default_color_scheme = "dark"
  ```
- **`resolve_inheritance_chain(name, project_root)`** — walks the chain root→leaf so the runtime can emit CSS links in cascade order. Validates: depth cap at 4 (deeper indicates design smell); cycle detection (`a→b→a` raises); missing parent raises; self-reference raises.
- **`_app_theme_url_chain` Jinja global** — list of stylesheet URLs in cascade order. `base.html` iterates and emits one `<link>` per chain entry. Parent loads first; child's `@layer overrides` wins via standard CSS cascade.
- **Font preconnect dedup** — when a chain inherits `font_preconnect`, the runtime collapses to unique entries preserving parent-first order.

### Changed
- **`base.html`** — prefers `_app_theme_url_chain` (Phase C) over the legacy single-URL `_app_theme_url` (Phase B). Single-parent themes have a length-1 chain so they render identically. The legacy `_app_theme_url` global still gets set to the leaf URL for older consumers.

### Tests
- **`test_app_theme_registry.py`** extended to 28 cases (was 17): 11 new cases across `TestThemeInheritance` (4 — extends parses; default None; must be string; cannot extend self) and `TestResolveInheritanceChain` (7 — no extends returns self; 2-level chain; 3-level chain; unknown theme raises; missing parent raises; cycle raises; depth cap of 4 enforced).
- **`test_app_theme_loading.py`** extended to 33 cases (was 30): 3 new TestThemeChainRendering cases — chain with 2 themes emits 2 links in cascade order; single chain renders one link; chain takes precedence over legacy URL.

### Agent Guidance
- **Inheritance is RUNTIME ONLY, not bundled at build time.** Each chain entry ships its own `<link>` tag. Browser handles the cascade — no concatenation logic, no extra build step. Cost: one HTTP round-trip per chain entry. For depth ≤ 4 (the cap) that's ≤ 5 stylesheet fetches total — tiny vs the ~100kb bundled framework CSS already there.
- **Inherited fields don't fall through automatically.** The child manifest's `default_color_scheme`, `font_preconnect`, `tags` are independent of the parent's. To inherit values, the child either omits them (gets defaults — `auto` / `[]` / `[]`) or copies the parent's verbatim. A future patch could add explicit fall-through (`default_color_scheme = "inherit"`); deferred until a real consumer asks.
- **Depth cap of 4 is intentional.** Deeper than 4 indicates a design smell — likely the child should extend a closer ancestor. Raise the cap only when a real consumer hits it AND the use case is legitimate.

## [0.61.44] - 2026-04-26

Patch bump. **Phase B complete** — Patch 4 ships `dazzle theme preview` and the corresponding `DAZZLE_OVERRIDE_THEME` env var override. All six Phase B patches now landed.

### Added
- **`dazzle theme preview <name>`** — boots the project with a theme override, no commit needed. Validates the theme name against the registry then `execvpe`s `dazzle serve --local` with `DAZZLE_OVERRIDE_THEME=<name>` set in the environment. Operators can A/B between themes by exiting and re-running with a different name; no toml or DSL mutation involved.
- **`DAZZLE_OVERRIDE_THEME` env var** — checked by the runtime BEFORE the DSL `theme:` field and `[ui] theme` toml setting. Three-level precedence: env > DSL > toml. Lets the preview command override both sources without mutating either.

### Tests
- **`test_dazzle_theme_cli.py`** extended to 22 cases (was 19): 3 new TestThemePreview cases — unknown theme exits 2; unknown name with project-local theme also exits 2 (full registry lookup); `--help` text describes the override mechanism.
- **`test_dsl_app_theme_field.py`** extended to 20 cases (was 14): 6 new TestEnvOverrideTakesPrecedence cases — env wins over DSL; env wins over toml; env wins over both; DSL used when env unset; toml used when env+DSL unset; all unset → None.

### Phase B summary

| # | Patch | Version | Status |
|---|---|---|---|
| 1 | Theme manifest TOML + registry | v0.61.39 | ✅ |
| 2 | DSL `theme:` field on `app` | v0.61.43 | ✅ |
| 3 | `dazzle theme list` | v0.61.40 | ✅ |
| 4 | `dazzle theme preview` | v0.61.44 | ✅ |
| 5 | `dazzle theme init` + project-local rendering | v0.61.41 | ✅ |
| 6 | `font_preconnect` consumption | v0.61.42 | ✅ |

End-to-end author flow now works:
1. `dazzle theme list` — see what's available
2. `dazzle theme init my-brand --inspired-by stripe` — scaffold from a baseline
3. Edit `<project>/themes/my-brand.css` and `my-brand.toml` to taste
4. `dazzle theme preview my-brand` — boot with the override, no commit
5. When happy: `app foo "Title": theme: my-brand` in the DSL OR `[ui] theme = "my-brand"` in toml

### Agent Guidance
- **Three-level precedence is `env or dsl or toml`.** If you add a fourth level (e.g. per-tenant theme), pick its place in the chain explicitly — operators rely on knowing what wins. Document it in `dev_docs/2026-04-26-design-system-phase-b.md` (the Phase B doc has an "Open questions" section for exactly this).
- **`dazzle theme preview` uses `os.execvpe`** — the CLI process is REPLACED by the dev server, not forked. No subprocess to track, no signal proxying needed. Ctrl-C goes straight to uvicorn. Works because `dazzle serve --local` is itself a long-running foreground process.
- **The env var override is a pure read** — the runtime never sets it itself. If you write a different "override theme" mechanism (e.g. a query string `?_theme=stripe`), don't tunnel it through `DAZZLE_OVERRIDE_THEME` — that env var has a specific contract (preview-only, ops-set). Add a separate parameter.

## [0.61.43] - 2026-04-26

Patch bump. Phase B Patch 2 — DSL `theme:` field on the `app` declaration. Themes can now live in the spec alongside `description:` / `multi_tenant:` / `security_profile:`. DSL value wins over `[ui] theme` in `dazzle.toml` (spec is source of truth, toml is deployment override). Closes the Phase B doc's open precedence question.

### Added
- **DSL `theme:` field** on the `app` declaration:
  ```dsl
  app contact_manager "Contact Manager":
    theme: paper
    security_profile: basic
  ```
  Quoted form (`theme: "linear-dark"`) and unquoted hyphenated form (`theme: linear-dark`) both work — the parser rejoins lexer-split `IDENT-MINUS-IDENT` tokens.
- **`AppConfigSpec.theme: str | None = None`** — IR field on the existing app-config dataclass.
- **`AppSpec.app_config`** — new field mirroring the root module's `app_config` so runtime consumers can read DSL values without re-loading source. Linker populates it.
- **`TokenType.THEME`** lexer keyword + parser branch in `parse_module_header`. Added to `KEYWORD_AS_IDENTIFIER_TYPES` so `theme` remains usable as a field/enum name elsewhere (e.g. `Setting.theme: enum[light,dark,auto]`).

### Changed
- **`subsystems/system_routes.py`** — runtime resolution now reads `appspec.app_config.theme` first, falls back to `mf.app_theme` from `dazzle.toml`. The selector is `dsl_theme or mf.app_theme` — pinned in tests.
- **`examples/ops_dashboard/dsl/app.dsl`** — moved theme declaration from `dazzle.toml [ui] theme` to DSL `theme: linear-dark` as the v0.61.43 proof. The toml setting still works (and still tested by `test_app_theme_loading.py`) but the DSL form now drives the example.

### Tests
- **`test_dsl_app_theme_field.py`** — 14 cases across 4 layers:
  - parser (6): theme parses; quoted form; unquoted hyphenated rejoin; multi-hyphen rejoin; optional default None; coexists with other app fields
  - identifier reuse (2): theme as entity field name; theme as enum value
  - IR (3): field on dataclass; default None; frozen
  - precedence (3): DSL wins; toml fallback; neither → None

### Agent Guidance
- **Spec wins over toml is the precedence rule.** When both `app foo: theme:` (DSL) and `[ui] theme = "..."` (toml) are set, the DSL value is used. Rationale: the spec is the source of truth for the application's design intent; the toml is a deployment override slot (e.g. for staging environments). Inverting this would let a deploy-time toml accidentally override the author's stated design choice.
- **Hyphenated theme names need rejoining at the parser level.** The lexer treats `linear-dark` as `IDENT(linear) MINUS IDENT(dark)`. The parser's `theme:` branch loops on `MINUS` to rejoin. Same trick is used in `_parse_model_id_value` for LLM model IDs — there's no shared helper because the surrounding context is too different. If a third such case appears, extract a shared `parse_hyphenated_identifier()`.
- **`AppSpec.app_config` is a mirror, not the source of truth.** The IR's authoritative `app_config` lives on the root `ModuleIR`. We mirror it onto AppSpec for runtime ergonomics. If you mutate `appspec.app_config`, you're modifying a frozen Pydantic clone — the original module's value is unchanged. (This isn't a real risk because the IR is frozen end-to-end, but worth knowing.)

## [0.61.42] - 2026-04-26

Patch bump. Phase B Patch 6 — `font_preconnect` consumption in `base.html`. Themes can now declare additional Google Fonts to preconnect; the `<link>` elements ship in the `<head>` so first-paint can fetch the theme's fonts in parallel with the bundle.

### Added
- **`_app_theme_font_preconnect` Jinja global** — set at startup from the theme manifest's `font_preconnect` list. `base.html` iterates and emits one `<link href="..." rel="stylesheet">` per URL, after the always-present Inter link.
- **`paper.toml.font_preconnect`** populated with Source Serif 4 (the open-source serif option for paper-vocabulary themes; existing CSS still uses Inter as body sans, so this is forward-looking).
- **`stripe.toml.font_preconnect`** populated with Inter Tight (the sans referenced in `stripe.css`'s `--font-sans`) and Geist Mono (the mono in `--font-mono`). Without these preconnects the theme's actual fonts only fetch after the CSS parses — adds ~150ms to first paint of any heading.

### Tests
- **`test_app_theme_loading.py`** extended to 30 cases (was 24): 6 new tests across `TestFontPreconnect` (3 — each URL renders as `<link>`; Inter always present; empty list adds no extras) and `TestShippedThemeFontPreconnect` (3 — linear-dark uses Inter only; paper preconnects Source Serif 4; stripe preconnects Inter Tight + Geist Mono).

### Agent Guidance
- **Inter is always preconnected by `base.html`** as the universal fallback. Themes only declare *additional* fonts in `font_preconnect`. linear-dark's font_preconnect is `[]` because it uses Inter for everything.
- **Jinja autoescapes `&` → `&amp;`** in attribute values. Tests for `font_preconnect` URLs assert the escaped form. The browser decodes it correctly so the URL is functionally identical, but the assertion needs to match the rendered HTML.
- **`font_preconnect` is a list of stylesheet URLs**, NOT plain preconnect URLs. The `<link>` is `rel="stylesheet"` (loads the CSS), not `rel="preconnect"` (just opens the connection). Naming is slightly off — could be `font_stylesheets` for clarity in a future patch. Functional behaviour is correct: the browser fetches the stylesheet, which references the font files via @font-face, and they download in parallel with the bundle.

## [0.61.41] - 2026-04-26

Patch bump. Phase B Patch 5 — closes the project-local rendering loop and adds `dazzle theme init` for scaffolding new themes from an existing one. Project-local themes now actually render (not just discoverable in `dazzle theme list`).

### Added
- **`dazzle theme init <name> [--inspired-by <theme>]`** — scaffolds `<project>/themes/<name>.css` (copied from the source theme; `linear-dark` by default) plus a `<name>.toml` boilerplate with the source's metadata. Validates: name must be lowercase + hyphens/underscores/digits; source theme must exist; target name must not already exist (refuses to overwrite). Prints next-step instructions.
- **`/static/themes/<name>.css` mount** — when `<project>/themes/` exists, the server mounts it at `/static/themes/` so project-local theme CSS is HTTP-reachable. Distinct from `/static/css/themes/` (framework themes) so the URL space stays clean.
- **`_app_theme_url` Jinja global** — resolved at startup via the registry. `base.html` prefers it over the legacy inline `('css/themes/' + name + '.css') | static_url` construction. Framework themes get `/static/css/themes/<name>.css`; project themes get `/static/themes/<name>.css`. Backwards-compat: when only `_app_theme` is set (no URL), the legacy inline path still works for framework themes.

### Tests
- **`test_dazzle_theme_cli.py`** extended to 19 cases (was 11): 8 new TestThemeInit cases — creates CSS + TOML; default source is linear-dark; `--inspired-by` honoured; unknown source / invalid name / uppercase name → exit 2; existing target refuses to overwrite; init-then-list end-to-end loop.
- **`test_app_theme_loading.py`** extended to 24 cases (was 21): 3 new TestThemeURLResolution cases — `_app_theme_url` wins over legacy path; legacy path still works when URL unset; neither set renders no link.

### Agent Guidance
- **Two URL spaces by design.** Framework themes at `/static/css/themes/<name>.css` (under the existing static mount); project themes at `/static/themes/<name>.css` (under a separate mount). The CombinedStaticFiles class doesn't support per-dir URL prefix remapping; rather than extend it, this patch just adds a second mount. The registry returns the right URL via `theme.source`, so callers don't need to know about the split.
- **`init` doesn't validate the resulting CSS** — it copies the source verbatim. If a user edits the CSS into something that breaks the cascade, the framework won't catch it. Future patch could add a `dazzle theme validate <name>` that asserts the override structure (e.g. `@layer overrides` block present).
- **Patch 4 (`preview`) and Patch 6 (`font_preconnect`) still pending.** Preview wraps `dazzle serve` with an env-var theme override so operators can A/B without committing. Font preconnect threads each theme's `font_preconnect` list into base.html as additional `<link rel="preconnect">` elements.

## [0.61.40] - 2026-04-26

Patch bump. Phase B Patch 3 — adds the `dazzle theme list` CLI subcommand. Wraps the v0.61.39 registry to give operators a fast way to discover shipped + project-local themes without reading source.

### Added
- **`dazzle theme list`** — prints a table of every discovered theme (framework + project-local) with columns: Name / Scheme / Src / Tags / Inspired by. Filters: `--tag <name>` (tag must appear in the theme's `tags` list), `--scheme <light|dark|auto>` (matches the theme's `default_color_scheme`), `--project-root <path>` (where to look for `<project>/themes/`; defaults to cwd). An empty result set is treated as a friendly empty-state, not an error (exit 0 with "No themes match the filter."). Invalid `--scheme` exits 2.
- **`src/dazzle/cli/theme.py`** — new `theme_app` typer group registered under `dazzle theme`. Skipped Patches 4 (`preview`) and 5 (`init`) for now — they're scaffolded as separate commits.

### Tests
- **`test_dazzle_theme_cli.py`** — 11 cases across 4 layers:
  - default behaviour (2): lists all three shipped themes; table header columns present
  - filtering (5): by tag; by light/dark scheme; invalid scheme → exit 2; zero-result filter exits 0 with friendly message
  - project-local discovery (2): project theme appears alongside framework; project paper overrides framework paper in listing
  - help / no-args (2): no-args lists themes (single-command typer collapse — will route to help when Patches 4/5 add siblings); `--help` mentions filter flags

### Agent Guidance
- **Single-command typer apps collapse to the command itself.** `theme_app` ships only `list` in v0.61.40 — typer treats it as the root command, so `dazzle theme` (no args) lists themes and `dazzle theme list` errors with "Got unexpected extra argument (list)". When Patches 4/5 add `preview` and `init`, this collapses back to standard subcommand routing automatically. Tests use `runner.invoke(theme_app, [...])` without the `list` prefix.
- **`--project-root` defaults to cwd** so `dazzle theme list` from any project directory shows that project's themes alongside framework ones. Tests pass `/tmp` as the project root to keep the framework-only baseline (3 themes) deterministic — passing `tmp_path` with a populated `themes/` subdir tests the project-local discovery path.

## [0.61.39] - 2026-04-26

Patch bump. Phase B Patch 1 of the design-system formalisation work — adds a theme manifest TOML format and registry loader. Each shipped theme (`linear-dark` / `paper` / `stripe`) now has a sibling `<name>.toml` declaring `description`, `inspired_by`, `default_color_scheme`, `font_preconnect`, `tags`. Foundation for Patches 2–6 (DSL field, linker validation, `dazzle theme list/preview/init` CLI, font preconnect consumption).

### Added
- **`themes/<name>.toml`** for the three shipped themes — declarative metadata sibling to the CSS file. Loader synthesises sensible defaults when a TOML is absent so legacy / quick-iteration CSS-only themes still load.
- **`dazzle_ui.themes.app_theme_registry`** module with:
  - `AppThemeManifest` (frozen dataclass): `name`, `description`, `inspired_by`, `default_color_scheme` (light/dark/auto), `font_preconnect` (tuple of Google Fonts URLs), `tags` (tuple), `css_path`, `source` (framework/project)
  - `discover_themes(project_root: Path | None = None)` — returns dict keyed by theme name; framework themes first, then project-local themes from `<project>/themes/` (which override shipped themes of the same name so projects can tweak `linear-dark` without forking)
  - `get_theme(name, project_root=None)` — single-theme lookup, returns None when not found
  - `list_theme_names(project_root=None)` — sorted name list

### Tests
- **`test_app_theme_registry.py`** — 17 cases across 4 layers:
  - shipped-theme discovery (6): each of linear-dark / paper / stripe loads with parsed manifest; list contains all three; unknown returns None; every css_path resolves to a real file
  - manifest parsing (4): invalid `default_color_scheme` raises; manifest `name` mismatch with filename raises; CSS-only theme synthesises defaults; `font_preconnect` parses as tuple
  - project-local override (4): project theme loads alongside framework; project overrides framework of same name; `project_root=None` skips project discovery; missing `themes/` directory is safe
  - registry shape (3): manifest is frozen dataclass; list is sorted; dict keys match `manifest.name`

### Agent Guidance
- **`AppThemeManifest` is the contract** — Patches 2 (DSL theme field), 3 (`dazzle theme list`), and 6 (font preconnect consumption) all consume this dataclass. Adding a field to it is a coordinated change; deferred fields (e.g. `extends` for theme inheritance, `template_overrides` for component-level overrides) are explicitly listed in the Phase B doc as Phase C scope.
- **Project-local themes live at `<project>/themes/<name>.css` (+ optional `<name>.toml`)** — same flat layout as the framework `themes/` directory. The Phase B doc proposed a directory form (`themes/<name>/<name>.css`) but the flat form is simpler today and migrates later when component-level overrides land. **Decision**: ship the flat form; reconsider when Phase C component-overrides need a sibling `templates/` dir.
- **CSS-only themes still work** — drop a `<name>.css` in `themes/` without a TOML and the registry synthesises defaults (`color_scheme=auto`, empty tags / preconnect / description). Lets contributors prototype themes quickly without manifest authoring.
- **TOML name mismatch is a hard error**, not a warning — silent renames are exactly the bug class that bit #885 / #886. The loader fails loudly when a manifest's `name` field doesn't match the CSS file stem.

## [0.61.38] - 2026-04-26

Patch bump. Closes #886 — three runtime call sites passed the cwd Path as the second arg to `build_appspec` instead of the module name. Symptom: every `dazzle db revision`, `dazzle db upgrade`, and process-worker startup raised `LinkError: Root module '/abs/path/to/project' not found. Available modules: ['myapp.core', 'stories']`. Knock-on from #885 — once that fixed the import, this surfaced.

### Fixed
- **`src/dazzle_back/alembic/env.py`** — `_load_target_metadata()` now passes `manifest.project_root` (the module name string) instead of `str(project_root)` (the cwd Path). Restores `dazzle db revision -m`, `dazzle db upgrade`, autogenerate.
- **`src/dazzle/cli/migrate.py`** — `deploy_command()` DSL validation step. Same fix.
- **`src/dazzle/process/worker.py`** — Temporal worker startup. Same fix.

### Tests
- **`test_parse_modules_imports.py`** extended with `test_build_appspec_passes_module_name_not_filesystem_path` — AST-walks each runtime caller, finds every `build_appspec(modules, <expr>)` call, asserts the second arg isn't `str(project_root)` / `str(Path.cwd())` / `str(cwd)`. Catches the cwd-Path regression at unit-test time. 7 cases now pin the import + call shape.

### Agent Guidance
- **`ProjectManifest.project_root` is a misleading field name** — despite the name, it holds the module string from `[project] root` in `dazzle.toml` (e.g. `"myapp.core"`), NOT the filesystem path. The cwd Path is also called `project_root` in many call sites. When passing to anything that expects a module name, use `manifest.project_root`. The field could be renamed `root_module_name` for clarity in a future patch — out of scope here.
- **The two-fix sequence (#885 → #886) is a class of bug**: an upstream module rename (`dsl_parser` → `parser`) silently masked a downstream API contract violation (passing wrong arg type) because the import error fired first. When fixing import errors, also audit the call sites for shape correctness — they may have been broken longer than the import.

## [0.61.37] - 2026-04-26

Patch bump. Phase A continued — adds the second and third app-shell themes (`paper` and `stripe`) and applies them to `contact_manager` and `support_tickets` respectively. Three example apps now demonstrate distinct visual identities while sharing the same DSL + templates.

### Added
- **`themes/paper.css`** — Notion-warm vocabulary. Warm cream surface (38° hue), muted clay accent (22°), generous spacing (~14–18px gaps), rounder radii (6–14px), soft warm-tinted shadows, slower motion (180–350ms with gentle ease). Light-first; dark variant is a low-warmth night-mode rather than a full dark theme.
- **`themes/stripe.css`** — Stripe-formal vocabulary. Cool slate surface (220° hue, near-white), indigo accent (245°), generous spacing, mid-size radii (4–10px), restrained cool-tinted shadows, mid-pace motion (130–280ms). Light-first; dark variant lifts the indigo for AA contrast on dark slate.

### Changed
- **`examples/contact_manager/dazzle.toml`** — `[ui] theme = "paper"`. Suits the small-firm-owner persona (CRM data benefits from readability over density).
- **`examples/support_tickets/dazzle.toml`** — `[ui] theme = "stripe"`. Suits the agent + manager personas (B2B support tools benefit from the "serious software" feel).

### Tests
- **`test_app_theme_loading.py`** — extended to 21 cases (was 11):
  - `TestLinearDarkCSS` refactored to a parametrised `TestShippedThemeCSS` class running the same 3 structural invariants (overrides layer, every load-bearing token re-defined, both dark + light variants) against all three shipped themes — `linear-dark`, `paper`, `stripe`. Adding a fourth theme means listing it in `SHIPPED_THEMES` and dropping the CSS file.
  - Two new manifest pinning tests that fail loudly if `contact_manager` or `support_tickets` rename their themes.

### Agent Guidance
- **Three themes is the minimum for confidence the mechanism scales.** With one theme, you can't tell if the architecture is right. With three differing in light/dark default + accent + spacing density + motion pace, the swap pathway is exercised across the meaningful axes. A future fourth theme should bring a different *vocabulary*, not just a colour shift — e.g. high-contrast / mono / brutalist would test corners the current three don't.
- **Theme files cap at ~150 lines.** All three shipped themes are tight: only the tokens that actually change vs. the default belong in the override block. If a theme file approaches 300 lines, the design is wandering — refactor before merging.
- **Per-theme custom fonts cost a Google-Fonts preconnect.** `paper` references iA Writer Mono; `stripe` references Inter Tight + Geist Mono. Neither is currently preconnected (only Inter is, in `base.html`'s `<head>`). The fonts fall back gracefully to system, so this is a polish item not a blocker. Phase B's theme-manifest TOML can declare which fonts to preconnect.

## [0.61.36] - 2026-04-26

Patch bump. Phase A of the design-system formalisation work — adds an app-shell theme mechanism so projects can override the default shadcn-zinc tokens with an alternate `:root` block by setting `[ui] theme = "<name>"` in `dazzle.toml`. Ships **`linear-dark`** as the first preset (Linear-vocabulary cool slate ramp + cyan accent + dense type) applied to `examples/ops_dashboard` as the proof.

### Added
- **`[ui] theme = "<name>"`** field in `dazzle.toml` — resolves to `src/dazzle_ui/runtime/static/css/themes/<name>.css`. Loaded after `dazzle-bundle.css` so the theme's `@layer overrides` block wins over the default tokens. The alias `[ui] app_theme = "..."` also works (avoids the keyword overlap with the existing `[theme]` section that controls site/marketing-page tokens). `None` (the default) keeps the shipped shadcn-zinc tokens.
- **`themes/linear-dark.css`** — first shipped preset. Borrows Linear's vocabulary (228° cool slate ramp, 205° cyan accent, dense 4px-base spacing, 100–150ms ease-out motion, minimal shadows + 1px borders, dark-first with a cooler-than-default light variant). Templates stay theme-agnostic — every `hsl(var(--*))` site picks up the new values automatically.
- **`ProjectManifest.app_theme`** field on the dataclass.

### Changed
- **`base.html`** — conditionally emits `<link rel="stylesheet" href="themes/<name>.css">` after the bundle when `_app_theme` is set on the Jinja env. Asset-fingerprinted via the existing `static_url` filter.
- **`subsystems/system_routes.py`** — sets `_app_theme` on the Jinja env globals at startup (same code path that already wires `_use_cdn` and `_favicon` from the manifest).
- **`examples/ops_dashboard/dazzle.toml`** — opts into `theme = "linear-dark"` as the proof. Doesn't affect any other example app.

### Tests
- **`test_app_theme_loading.py`** — 11 cases across 3 layers:
  - manifest (4): default is None; `[ui] theme` parses; `[ui] app_theme` alias parses; ops_dashboard pinned to `linear-dark` so a future rename fails CI rather than 404'ing the stylesheet.
  - theme CSS (4): file exists; uses `@layer overrides`; overrides every load-bearing token (`--background` / `--foreground` / `--primary` / `--card` / `--muted` / `--border` / `--ring` / `--destructive`); ships both dark + light variants.
  - base.html wiring (3): theme link present when `_app_theme` set; absent when not; renders AFTER the bundle (cascade order matters).

### Agent Guidance
- **Adding a new theme**: drop `<name>.css` in `src/dazzle_ui/runtime/static/css/themes/`, structured as a single `@layer overrides { :root, [data-theme="dark"] { ... } [data-theme="light"] { ... } }` block. Override the same shadcn-shape token names (`--background` / `--foreground` / `--primary` / etc.) that `design-system.css` defines. **Don't** introduce new token names — templates only know about the canonical set, so a new token wouldn't be consumed.
- **Theme vs ThemeSpec**: the legacy `[theme]` section + `ThemeConfig` dataclass + `ThemeSpec` presets cover **site/marketing-page** tokens (`--dz-hero-*`, `--dz-section-*`, `--dz-footer-*`). The new `[ui] theme` field covers **app-shell** tokens (the shadcn-shape `--primary` / `--card` / etc.). They're orthogonal — a project can set both. Phase B will probably consolidate them once we've felt the shape with more themes.
- **Cascade order is load-bearing**. The theme `<link>` MUST come after the bundle so `@layer overrides` resolves higher. If you add a new global stylesheet between them, audit the layer declarations.
- **One-line rollback** — comment out `theme = "linear-dark"` in `examples/ops_dashboard/dazzle.toml` and the app reverts to default tokens. No template changes needed.

## [0.61.35] - 2026-04-25

Patch bump. Two more CI-restoring fixes that surfaced once v0.61.34 unblocked the e2e jobs from running. Both are latent bugs from v0.61.25 (#884) that never got exercised because lint failures upstream had been masking them.

### Fixed
- **`delta` keyword now usable as identifier**. The v0.61.25 (#884) `TokenType.DELTA` made `enum[alpha, beta, gamma, delta]` fail to parse anywhere it appeared (`fixtures/component_showcase/dsl/app.dsl:20:35` was the first to surface). Added `TokenType.DELTA` to `KEYWORD_AS_IDENTIFIER_TYPES` in `dsl_parser_impl/base.py` so it remains usable as a field/enum value while still functioning as the region-block keyword. Same pattern as `update`, `delete`, `count` etc.
- **`RegionContext.delta` field added**. v0.61.25 (#884) wired `_compute_aggregate_metrics(delta=ctx.ctx_region.delta, …)` into `workspace_rendering.py:736` but never extended the template-facing `RegionContext` Pydantic model to carry the field. Result: any workspace region with `aggregates:` 500'd at runtime with `AttributeError: 'RegionContext' object has no attribute 'delta'`. Surfaced in CI when the `INTERACTION_WALK` + `UX Contracts (support_tickets)` jobs hit `/api/workspaces/ticket_queue/regions/queue_metrics` and returned 500. Added `delta: Any | None = None` to `RegionContext` and threaded `delta=getattr(region, "delta", None)` through `build_workspace_context`.

### Agent Guidance
- **When adding a new region-block field that the runtime reads via `ctx.ctx_region.<name>`, extend `RegionContext` AND `build_workspace_context`**. The IR `WorkspaceRegion` model is parser-facing; `RegionContext` is template/runtime-facing. They aren't the same object — the latter is built from the former in `dazzle_ui/runtime/workspace_renderer.py`. Unit tests typically exercise the IR path, so a missing thread-through silently passes pytest and only blows up at e2e time.
- **Adding a new lexer keyword**: always check whether it could appear as an identifier elsewhere (enum values, field names). If so, add to `KEYWORD_AS_IDENTIFIER_TYPES` in `src/dazzle/core/dsl_parser_impl/base.py`. Today's reserved-as-strict list is `{from, to, into}` and a handful of operators — most other keywords double as identifiers.

## [0.61.34] - 2026-04-25

Patch bump. Restores the green CI badge after the v0.61.27 → v0.61.33 chart-feature run. Two distinct fixes:
1. **Coverage gate**: the four new `DisplayMode` values (`histogram`, `radar`, `box_plot`, `bullet`) had no example-app consumer, tripping the `dazzle coverage --fail-on-uncovered` invariant.
2. **Pre-existing nav-links test**: assertion pinned an `hx-swap` string that v0.61.18 (#876) widened — broken on `main` since that release.

### Fixed
- **`examples/ops_dashboard/dsl/app.dsl`** — added four chart regions exercising the new display modes against the existing `System` entity:
  - `response_time_distribution` — `histogram` over `response_time_ms` with an "SLA target" reference line at 500ms
  - `service_type_profile` — `radar` with one spoke per `service_type`, value = system count
  - `response_time_spread` — `box_plot` with quartile spread per `service_type`, plus the SLA reference line
  - `system_response_bullet` — `bullet` with per-system response time vs three reference bands (`positive` < 250ms, `warning` 250–500ms, `destructive` > 500ms)
  Coverage rises from 63/67 (94%) to 67/67 (100%) so the gate passes.
- **`tests/unit/test_template_rendering.py::test_nav_links_use_fragment_targeting`** — assertion now uses substring `'hx-swap="morph:innerHTML transition:true'` instead of pinning the full string. v0.61.18 (#876) appended ` scroll:#main-content:top` to the swap and the test wasn't updated then; the substring form survives future suffix tweaks.

### Agent Guidance
- **The framework artefact coverage gate (`dazzle coverage --fail-on-uncovered`) runs in CI's `lint` job.** Any new `DisplayMode` enum entry needs at least one region in an example app exercising it, otherwise the gate breaks the build. Run the command locally before shipping a new chart mode.
- **Avoid pinning exact `hx-swap=` strings in template tests.** They evolve with idiomorph + scroll + transition tweaks; substring or attribute-presence checks are more durable.

## [0.61.33] - 2026-04-25

Patch bump. Closes #883 (overlay_series scope) — line/area chart regions now support an `overlay_series:` block of additional named data series with their own `source` / `filter` / `aggregate`. Pulls e.g. a cohort-average comparison line on top of a per-pupil trajectory in one chart frame. Builds on the v0.61.32 multi-measure aggregate pipeline.

### Added
- **DSL**: new `overlay_series:` block on workspace regions with `display: line_chart` (or `area_chart`). Each entry uses the YAML-style indented dash form (the lexer's existing INDENT-after-dash behaviour carries the sub-keys):
  ```dsl
  ao3_trajectory:
    source: MarkingResult
    aggregate:
      avg: avg(scaled_mark)
    display: line_chart
    group_by: bucket(assessed_at, week)
    filter: student = current_context.student and ao = ao3
    overlay_series:
      - label: "Cohort average"
        source: MarkingResult            # optional; defaults to parent
        filter: ao = ao3 and tg = current_context.teaching_group
        aggregate: avg(scaled_mark)
      - label: "Target band ceiling"
        aggregate: max(scaled_mark)
  ```
- **IR**: `dazzle.core.ir.workspaces.OverlaySeriesSpec` (frozen Pydantic model) — `label: str`, `source: str | None`, `filter: ConditionExpr | None`, `aggregate_expr: str`. Exported from `dazzle.core.ir`.
- **Lexer**: new `TokenType.OVERLAY_SERIES = "overlay_series"` keyword.
- **Runtime**: when a region has `display: line_chart` or `display: area_chart` and a non-empty `overlay_series:`, the handler fires one extra `_compute_bucketed_aggregates` call per overlay using the parent's `group_by` (and `kanban_columns` if any) but the overlay's own `source`/`aggregate`. Each overlay's filter merges into the same scope_filters the primary aggregate uses (security gate per #574). Overlays that fail their query are logged and skipped — the primary chart still renders.
- **Template**: `line_chart.html` renders one dashed `<polyline>` per overlay (`stroke-dasharray="3,2"`) BEFORE the primary line so the primary stays visually dominant. Y-axis ceiling auto-expands to include the largest overlay value so out-of-range overlays stay inside the plot. Multi-series legend (primary + each overlay) shows below the chart with token-driven colour swatches; footer reports `<N> series` when multiple lines are present.

### Tests
- **`test_workspace_overlay_series.py`** — 13 cases across 3 layers:
  - parser (6): minimal overlay; full source+filter+aggregate; multiple overlays; aggregate required; unknown key raises; overlay absent by default.
  - IR (2): defaults (source/filter both None); frozen model.
  - template (5): overlay polyline uses dashed stroke + label in legend; overlay above data peak widens the y-axis (htmls differ); legend appears for multi-series; legend omitted when no overlays; multiple overlays get distinct colours from the palette + footer reports correct series count.

### Agent Guidance
- **Per-overlay scope**. Overlays inherit the same `scope_filters` (security gates) as the primary aggregate. The overlay's `filter:` merges in on top — it cannot circumvent scope. If a teacher's scope rule restricts to `teaching_group = current_user.teaching_group`, a "national average" overlay would still be filtered to the teaching group; cross-cohort comparisons need a separate scope-bypass mechanism (out of scope today).
- **Bucket alignment is by index**. Each overlay computes its own bucket list via the same `group_by`. The template iterates overlay buckets up to `count` (the primary length). For BucketRef time-bucket group_by, both queries see the same time range so order matches; for enum/state-machine `group_by`, both pull the same bucket list. Mismatched ordering would mis-align the polyline — verify with `dazzle db explain-aggregate` if a chart looks off.
- **Single aggregate per overlay**. Each overlay carries ONE aggregate expression (no name needed — the overlay's `label:` doubles as the metric name). To draw N comparison series, list N overlays. The multi-measure pipeline that landed in v0.61.32 supports multi-series WITHIN ONE aggregate (radar's `actual` + `target`); overlays are for series that need DIFFERENT scope/filter (cohort vs individual).
- **Failure mode = skip**. An overlay that raises during query is logged and dropped; the primary chart continues. Avoid noisy chart builds where a missing FK or bad scope condition silently disappears — check the worker log for `Overlay series 'X' failed`.

## [0.61.32] - 2026-04-25

Patch bump. Closes #879 (multi-series radar) — extends the workspace aggregate pipeline so multiple named measures over the same source fire as ONE multi-measure GROUP BY query, then teaches the radar template to render one polygon per series. Also extends the aggregate-expression language so `avg(<column>)` / `sum(<column>)` / `min(<column>)` / `max(<column>)` resolve cleanly (gap surfaced by #880's investigation).

### Added
- **DSL**: aggregate expressions now accept `avg(<column>)`, `sum(<column>)`, `min(<column>)`, `max(<column>)` against a column on the region's `source:` entity (in addition to the existing `count(<Entity> [where ...])` form).
  ```dsl
  ao_profile:
    source: MarkingResult
    display: radar
    group_by: assessment_objective
    aggregate:
      actual: avg(scaled_mark)        # ← was rejected pre-0.61.32
      target: avg(target_mark)        # second series → second polygon
  ```

### Changed
- **`_aggregate_via_groupby`** signature: `metric_name: str` → `measures: dict[str, str]`. Callers pass `{"<name>": "count"}` or `{"<name>": "<op>:<col>"}` — the aggregate primitive already supported multi-measure dicts, so the SQL change is zero. Each result bucket now carries `value` (legacy alias for the FIRST measure, preserves single-series template compat) plus `metrics: {<name>: <value>, ...}` for templates that want all of them. **Breaking**: callers using `metric_name=` kwarg need to migrate (only the unit tests called this directly; the in-tree `_compute_bucketed_aggregates` is the only production caller).
- **`_compute_bucketed_aggregates`** parses ALL aggregate expressions from the DSL block upfront and fires them as one multi-measure GROUP BY when they all qualify for the fast path (same source entity, no `current_bucket` sentinel, same `where:` clause). The slow per-bucket path stays single-measure for now (only the FIRST aggregate is evaluated) — a future patch can extend it if needed. Each returned bucket carries the new `metrics` sub-dict for shape uniformity.
- **`radar.html`** renders one polygon + vertex-marker set per series, cycling through a 5-colour palette. Shared y-axis radius scales to the global max across ALL series. Single-series mode still works (legacy `b.value` consumers) — the template falls back to `[b.value]` as a one-element series list when `b.metrics` is absent. Multi-series adds a colour-swatch legend below the chart and an `<svg:title>` per vertex carrying `<spoke> <series>: <value>`.

### Tests
- **`test_multi_measure_aggregates.py`** — 7 cases: two-measures-in-one-query; first-measure drives legacy `value`; empty measures → empty result; `avg(<column>)` resolves through fast path; two aggregates same source → one query; mixed `count` + `avg`; `sum/min/max(<column>)` measure spec mapping.
- **`test_workspace_radar.py`** — extended with 5 multi-series cases: two-series renders 2× polygons; per-series tooltip carries the series name; legend appears for multi-series; legend omitted for single-series; y-axis max spans all series.
- **`test_bar_chart_bucketed_aggregate.py`** — 6 result-shape assertions updated to include the new `metrics` sub-dict (no behaviour change, legacy `value` field preserved).

### Agent Guidance
- **The fast path requires homogeneity across aggregates.** All measures in a single `aggregate:` block must (a) target the same source entity, (b) share the same `where:` clause (or all have none), and (c) avoid the `current_bucket` sentinel. If any one diverges, the runtime falls back to the slow per-bucket path which evaluates only the first aggregate. To force per-bucket-per-aggregate evaluation we'd need to fan out to N×M queries — deferred until a real consumer needs it.
- **`_compute_bucketed_aggregates` return shape now includes `metrics`** — single-measure callers can still read `b.value` (FIRST aggregate's value); multi-series callers should iterate `b.metrics.items()`. Templates that destructure each bucket via `{label, value}` only continue working unchanged.
- **Aggregate-expression language remains conservative.** `avg(at_or_above_target * 100)` (arithmetic inside the aggregate) is still NOT supported — the regex captures bare column names. Materialise computed columns at insert time when this matters. The full SQL-expression case isn't worth the parser complexity until a real DSL consumer asks for it.

## [0.61.31] - 2026-04-25

Patch bump. Closes #880 (pre-computed MVP) — new `display: bullet` mode renders Stephen Few bullet rows: one row per item, each with an actual-value bar, an optional target tick, and `reference_bands` (#883) drawn behind as comparative qualitative zones (red/amber/green or any colour token). Compact actual-vs-target read for AO-style dashboards.

### Added
- **DSL**: new `display: bullet` mode + `bullet_label:` / `bullet_actual:` / `bullet_target:` column refs on workspace regions. Each names a column on the source entity that the bullet template reads off every row.
  ```dsl
  ao_bullets:
    source: AOSummary
    display: bullet
    bullet_label: name
    bullet_actual: actual
    bullet_target: target
    reference_bands:
      - label: "On target", from: 60, to: 100, color: positive
      - label: "Below", from: 0, to: 40, color: destructive
  ```
- **IR**: `DisplayMode.BULLET` enum entry + `WorkspaceRegion.bullet_label / bullet_actual / bullet_target: str | None`.
- **Lexer**: new `TokenType.BULLET_LABEL` / `BULLET_ACTUAL` / `BULLET_TARGET` keywords.
- **Renderer**: `RegionContext` carries the three column refs through to the template-facing context.
- **Runtime**: when `display=BULLET`, builds `bullet_rows` from items by reading the three named columns, computes `bullet_max_value` as the max across actual + target + `reference_bands` extents so out-of-range values still fit on the shared scale.
- **Template**: new `bullet.html` — one flex row per item with the label (left), a 100%-wide track (middle) carrying absolutely-positioned reference-band zones + the actual bar + the target tick, and the formatted `actual / target` value (right). Token-driven band colours; primary tint for the actual bar; foreground stroke for the target tick.

### Tests
- **`test_workspace_bullet.py`** — 10 cases across 3 layers:
  - parser (3): minimal bullet; bullet + reference_bands; `bullet_target` optional.
  - template (7): one row per item; target tick suppressed when `target=None`; reference bands render zones (4 rows × 2 bands = 8 zones); actual bar width is proportional to `bullet_max_value`; empty rows show empty_message; zero max falls back to empty state cleanly; `DISPLAY_TEMPLATE_MAP['BULLET']` routes correctly.

### Agent Guidance
- **Pre-computed MVP — no per-group_by aggregation.** The original issue (#880) sketched DSL with `group_by: ao` + `aggregate: { actual: avg(...), target: avg(...) }`. This patch ships the visual primitive (the actual user value — Stephen Few rendering with bands) by reading three columns off each item directly. Per-group aggregation requires extending `_compute_bucketed_aggregates` to handle multiple metrics (currently does `next(iter(aggregates.items()))` and drops the rest); also requires the aggregate-expression language to support `avg(<column>)` as well as `count(<Entity>)` (currently only the latter resolves through `_compute_aggregate_metrics`'s entity-name lookup). Tracked as separate follow-up scope.
- **Use a pre-aggregated source entity** (e.g. `AOSummary`) when authoring bullet regions today. Materialise per-AO averages via a view, or compute them at insert time. AegisMark-style cohorts produce ~4–6 rows so a pre-aggregated entity is cheap.
- **Reference bands map to the same shared scale** as the actual bar and target tick. The runtime widens `bullet_max_value` to include the largest band's `to:` value so an "On target: 60-100" zone fits even if no row has actual=100.

## [0.61.30] - 2026-04-25

Patch bump. Closes #881 — new `display: box_plot` mode renders per-group quartile spread (Q1, median, Q3, IQR) with Tukey 1.5×IQR whiskers and outlier dots. Pure SVG, server-rendered, in-process stats over the already-fetched `items` — no extra DB query, no NumPy. Same in-process pattern as the histogram (#882) and the same `heatmap_value` legacy field for the value column.

### Added
- **DSL**: new `display: box_plot` mode + `show_outliers: true|false` toggle on workspace regions.
  ```dsl
  ao_spread:
    source: MarkingResult
    display: box_plot
    group_by: assessment_objective
    value: scaled_mark
    show_outliers: true            # default
    scope: teaching_group = current_context
  ```
  Reuses the legacy `heatmap_value` IR field as the value column (same overload as histogram). `group_by` enumerates one box per bucket.
- **IR**: `DisplayMode.BOX_PLOT` enum entry + `WorkspaceRegion.show_outliers: bool = True`.
- **Lexer**: new `TokenType.SHOW_OUTLIERS = "show_outliers"` keyword.
- **Runtime**: `_compute_box_plot_stats(items, value_field, group_by, show_outliers)` in `dazzle_back.runtime.workspace_rendering`. Quartiles via NumPy-default linear interpolation (R "type 7": Q at position `(n-1)*p`, fractional positions interpolate linearly between adjacent order statistics). Whiskers terminate at the furthest data point inside `[Q1 − 1.5·IQR, Q3 + 1.5·IQR]`; everything outside that fence is an outlier (Tukey). Skips items where the value is None or non-numeric. Returns `{label, n, min, q1, median, q3, max, iqr, whisker_low, whisker_high, outliers}` per group.
- **Template**: new `box_plot.html` — SVG with shared y-axis across boxes for direct comparability, primary-tint Q1–Q3 box, bold median line, whisker stem + caps, outlier dots, group labels below the axis. Reuses `reference_lines` from #883 as horizontal markers (target/grade-boundary lines map naturally to the y-axis here).

### Tests
- **`test_workspace_box_plot.py`** — 16 cases across 3 layers:
  - parser (3): minimal box_plot; `show_outliers: false`; invalid value raises.
  - runtime / `_compute_box_plot_stats` (8): standard Q1/median/Q3 math for 1..10 (3.25 / 5.5 / 7.75); outlier detection via Tukey fences (value 100 lands in outliers, not whisker_high); `show_outliers: false` returns empty list; groups preserve first-seen order; single-value group → degenerate flat box (no divide-by-zero); `group_by: None` returns one global bucket; non-numeric items skipped; empty input → `[]`.
  - template (5): one box rect per group; outlier renders as `<circle>` with tooltip; horizontal reference line renders dashed; empty stats shows empty_message; `DISPLAY_TEMPLATE_MAP['BOX_PLOT']` routes correctly.

### Agent Guidance
- **In-process stats (no NumPy, no SQL `PERCENTILE_CONT`).** Box-plot quartiles are computed from the already-fetched `items` (same approach as histogram #882). For massive cohorts the page-size limit on `items` (default ~50–200 for chart modes) under-samples; future work could push percentile calc to PostgreSQL `percentile_cont`. Pure stdlib is fine for school-scale + investor-demo dashboards and avoids a hard NumPy dependency.
- **Linear-interpolation quartiles match NumPy `np.percentile` defaults** (R "type 7" / inclusive method). If you wire a different chart that needs the same quartiles, reuse `_compute_box_plot_stats` rather than rolling another calculator — the test vectors pin the convention.
- **Single-value groups render a degenerate flat box** (Q1 = median = Q3 = the value, IQR = 0, no whiskers). This is preferable to skipping the group silently — the user sees that "AO4 has only one mark" rather than wondering where AO4 went.
- **`reference_lines` works on box plots too** — the existing #883 primitive maps cleanly to the y-axis. Vertical reference lines on a box plot would need a new key (and aren't a common pattern); skip unless explicitly requested.

## [0.61.29] - 2026-04-25

Patch bump. Closes #879 (single-series MVP) — new `display: radar` mode renders an SVG polar/radar chart from the same `group_by` + `aggregates` shape `bar_chart` already uses. Each `group_by` bucket becomes one spoke; the aggregate value sets the spoke length. Pure SVG, server-rendered, no JS — uses rotated `<g>` wrappers and `<line>`/`<circle>` primitives so Jinja never has to compute trig.

### Added
- **DSL**: new `display: radar` mode on workspace regions.
  ```dsl
  ao_profile:
    source: MarkingResult
    display: radar
    group_by: assessment_objective    # spokes
    aggregate:
      pct_at_target: count(MarkingResult where ao = current_bucket)
    scope: teaching_group = current_context
    empty: "No marked work yet for this class."
  ```
  Spokes start at 12 o'clock and go clockwise so the natural reading order matches the `group_by` enum order. Each vertex carries an `<svg:title>` for hover/screen-reader text.
- **IR**: `DisplayMode.RADAR` enum entry. Reuses `WorkspaceRegion.group_by` + `aggregates` — zero new IR fields.
- **Runtime**: extended `_single_dim_chart_modes` in `workspace_rendering.py` to include `RADAR` so the existing `_compute_bucketed_aggregates` pipeline feeds it (same per-bucket aggregate eval that bar_chart and line_chart use; #847's GROUP BY fast path applies).
- **Template**: new `radar.html` — concentric polar grid (4 rings at 25/50/75/100%, rendered as N-segment polygons matching the spoke count for clean geometry), spoke axes, vertex markers, and an outline polygon assembled from `N` rotated `<line>` segments. Spoke labels counter-rotate to stay upright. Degenerate fallback for < 3 spokes shows a compact value list ("Radar needs ≥ 3 spokes — showing values list instead.") rather than a meaningless point/line.

### Tests
- **`test_workspace_radar.py`** — 8 cases:
  - parser (1): `display: radar` + `group_by` + `aggregate` parses into `DisplayMode.RADAR`.
  - template (7): one `<circle>` marker per spoke; spoke labels emitted; 3-spoke minimum renders SVG (not fallback); 2-spoke degenerate fallback shows value list; empty bucketed_metrics shows empty_message; all-zero values doesn't divide-by-zero; `DISPLAY_TEMPLATE_MAP['RADAR']` routes correctly.

### Agent Guidance
- **Single-series MVP only.** The original issue (#879) also asked for a target-band overlay and a cohort-comparison series. Multi-series support requires extending `_compute_bucketed_aggregates` to return ALL aggregates not just the first — currently the helper does `next(iter(aggregates.items()))` and drops the rest. Bar_chart consumers only read the first metric so this is a backward-compatible refactor when added; tracked as follow-up scope.
- **Aggregate-expression caveat.** The current aggregate language only fully resolves `count(<Entity>)` expressions through the GROUP BY fast path. `avg(<column>)` / `sum(<column>)` will tokenise but `_compute_aggregate_metrics` rejects them at the entity-name lookup. Use `count(... where <field> = current_bucket)` for radar values until the multi-measure aggregate work lands.
- **Pure-SVG trig workaround.** Jinja can't call `cos`/`sin`, so the radar template uses chained `<g transform="rotate(deg)">` wrappers + axis-aligned `<line>`/`<circle>` primitives instead of computing explicit `(x, y)` coordinates per vertex. The outline polygon is therefore `N` rotated line segments rather than a single `<polygon>` (no fill in v1). A filled polygon can be added later by pre-computing vertex coords in the runtime and passing them as a `points` string.

## [0.61.28] - 2026-04-25

Patch bump. Closes #882 — new `display: histogram` mode renders a continuous-variable distribution (raw marks, response times, scores) with vertical reference lines for grade boundaries, targets, and threshold markers. Pure SVG, server-rendered, no extra DB query (re-uses the rows already fetched for the region).

### Added
- **DSL**: new `display: histogram` mode + `value:` (column to bin) + `bins:` (positive int or `auto`) keys on workspace regions.
  ```dsl
  mark_distribution:
    source: MarkingResult
    display: histogram
    value: scaled_mark
    bins: auto                       # or e.g. 20
    reference_lines:
      - label: "Grade 4", value: 32
      - label: "Grade 6 (target)", value: 56, style: dashed
    scope: teaching_group = current_context
    empty: "No marks yet."
  ```
  `bins: auto` selects bin count via Sturges' rule (`⌈log2(N) + 1⌉`, clamped to [1, 50]); explicit `bins: 20` forces 20 equal-width bins. The `value:` key reuses the legacy `heatmap_value` IR field as a generic "value column" — rename deferred to keep this patch focused.
- **IR**: `WorkspaceRegion.bin_count: int | None = None` (None = Sturges) + new `DisplayMode.HISTOGRAM`. Exported from `dazzle.core.ir`.
- **Lexer**: new `TokenType.BINS = "bins"` keyword.
- **Runtime**: `_compute_histogram_bins(items, value_field, bin_count)` in `dazzle_back.runtime.workspace_rendering` bins raw values into equal-width buckets. Final bin is closed on the right so the global max isn't dropped. Skips items where the value is None or non-numeric. Returns `[{label, count, low, high}, ...]` to the template. Triggered when `display=HISTOGRAM` and `value:` is set.
- **Template**: new `histogram.html` renders SVG bars with primary fill, vertical reference lines (`stroke-dasharray` per `style:`) clipped to the data range so out-of-range markers don't spill off the canvas. Each bin + ref line carries an `<svg:title>` for hover/screen-reader text. Sparse x-axis tick labels (first/last + every Nth) so dense binnings stay readable.

### Tests
- **`test_workspace_histogram.py`** — 18 cases across 3 layers:
  - parser (6): minimal histogram; explicit `bins: 20`; `bins: auto`; `bins: 0` raises; `bins: many` raises; histogram + reference_lines coexist.
  - runtime / `_compute_histogram_bins` (8): equal-width binning; global max lands in final bin; Sturges bin count for N=100; empty input → `[]`; no numeric values → `[]`; single distinct value → one degenerate bin; non-numeric items skipped; label uses `:g` format.
  - template (4): one `<rect>` per bin; vertical reference line in range renders dashed; reference line outside range is skipped (not clipped + drawn off-canvas); empty `histogram_bins` shows `empty_message` and no SVG.

### Agent Guidance
- **Histograms re-use the already-fetched `items`**, not a separate aggregate query. That means the bin count reflects the page-size limit (default ~50–200 for chart modes — see `_single_dim_chart_modes` in `workspace_rendering.py`). For massive cohorts this under-samples; future work could push binning to PostgreSQL `width_bucket` to scale, but the in-process MVP is sufficient for school-scale + investor-demo dashboards.
- **`heatmap_value` is overloaded.** It's the IR field for both heatmap cell-coloring (the original use) and histogram binning (this commit). The DSL keyword `value:` writes to it. The legacy name is kept to avoid scope creep — a future patch could rename to `value_field` (clean break — no shims).
- **Reference lines on histograms are vertical** (x-axis = the binned value). Same `ReferenceLine` IR shape as line/area charts (#883), but the chart type drives the rendering axis. If you add another distribution chart (box plot, violin), reuse the same `reference_lines` IR field and pick the axis in the template.

## [0.61.27] - 2026-04-25

Patch bump. Closes #883 (lines + bands portion) — `line_chart` and `area_chart` regions can now overlay reference lines (horizontal markers at a fixed y-value) and shaded reference bands (target zones, RAG ranges) on top of the data series. Pure SVG, server-rendered, no extra DB queries — turns a "raw values" trajectory into an "are we on target?" chart in one frame.

### Added
- **DSL**: new `reference_lines:` and `reference_bands:` blocks on `line_chart` / `area_chart` regions.
  ```dsl
  ao3_trajectory:
    source: MarkingResult
    aggregate:
      avg: avg(scaled_mark)
    display: line_chart
    group_by: bucket(assessed_at, week)
    reference_lines:
      - label: "Target (6)", value: 56, style: dashed
      - label: "Boundary 5/6", value: 50, style: dotted
    reference_bands:
      - label: "Target band", from: 50, to: 56, color: target
  ```
  Entries are comma-separated single lines (same shape as `demo` records) so they parse cleanly under the INDENT/DEDENT lexer. `style:` ∈ {`solid` (default), `dashed`, `dotted`}; `color:` ∈ {`target` (default), `positive`, `warning`, `destructive`, `muted`} maps to design tokens at render time.
- **IR**: `dazzle.core.ir.workspaces.ReferenceLine` (label, value, style) and `ReferenceBand` (label, from_value, to_value, color) — both frozen Pydantic models. `ReferenceBand` aliases `from`/`to` ↔ `from_value`/`to_value` since `from` is a Python keyword. Exported from `dazzle.core.ir`.
- **Lexer**: new `TokenType.REFERENCE_LINES` / `TokenType.REFERENCE_BANDS` keywords.
- **Renderer**: `RegionContext` carries overlays as plain dicts (DSL-facing keys, including `from`/`to`) so Jinja reads them with `band['from']` / `band.to` directly.
- **Templates**: `line_chart.html` and `area_chart.html` render `<rect>` (bands, fill-opacity 0.12, token-driven colour) and `<line>` (reference lines, stroke-dasharray per `style:`) before the data series so the polyline/stack sits on top. Y-axis scale auto-expands when an overlay sits above the data peak so target lines stay inside the plot area. Each overlay carries an SVG `<title>` for hover/screen-reader text.

### Tests
- **`test_workspace_reference_overlays.py`** — 24 cases across 4 layers:
  - parser / lines (6): minimal; multiple with mixed styles; decimal value; invalid `style` raises; unknown key raises; missing `value` raises.
  - parser / bands (5): minimal; multiple colours; invalid `color` raises; missing `to` raises; unknown key raises.
  - parser / coexistence (2): both blocks on one region; both empty by default.
  - IR (5): defaults + frozen for both models; round-trip `from`/`to` aliases via `model_dump(by_alias=True)`.
  - renderer wiring (2): `RegionContext.reference_lines` flattens to dicts; `RegionContext.reference_bands` keys use DSL-facing `from`/`to` (not Python `from_value`/`to_value`).
  - template (4): dashed-style maps to `stroke-dasharray="4,3"`; band rect carries the token primary fill + tooltip; reference line above data peak expands the y-axis; absent overlays leave only the baseline grid line.

### Agent Guidance
- **`overlay_series:` deferred to a follow-up.** The original issue (#883) also asked for additional data series on the same axes (e.g. cohort-average line on top of a per-pupil trajectory). That requires a second `Repository.aggregate` call per series and a richer template loop — out of scope for this patch. The reference-line/band primitive lands first because it's the highest-value piece (target comparison) and ships without runtime changes. #883 stays open scoped to overlay_series only.
- **`from` and `to` are accepted as keys here** even though they're reserved DSL keywords. The parser bypasses the strict identifier guard for `_parse_reference_entry` because `allowed_keys` already constrains what's legal — adding them to `KEYWORD_AS_IDENTIFIER_TYPES` globally would have wider parser implications.
- **Y-axis auto-expansion is overlay-aware.** When a reference line/band sits above the data peak the line_chart `max_val` is widened to include it. If you add a third overlay primitive, it must also feed `_max_candidates` so the data series stays inside the plot area.

## [0.61.26] - 2026-04-25

Patch bump. Closes #885 — three runtime call sites still imported `parse_modules` from the removed `dazzle.core.dsl_parser` module (split into `dazzle.core.parser` + `dazzle.core.dsl_parser_impl/` package). Failures only surfaced when downstream users actually ran `dazzle db migrate`, the migrate CLI, or the Temporal worker — silently skipping the test suite. Restores schema-migration capability for v0.61.20+ users.

### Fixed
- **`src/dazzle_back/alembic/env.py`** — `_load_target_metadata()` now imports `parse_modules` from `dazzle.core.parser`. Restores `dazzle db migrate`, `dazzle db migrate --check`, and `dazzle db migrate --sql` for downstream projects.
- **`src/dazzle/cli/migrate.py`** — `deploy_command()` now imports from `dazzle.core.parser`. Restores `dazzle migrate deploy`.
- **`src/dazzle/process/worker.py`** — `main()` now imports from `dazzle.core.parser`. Restores `python -m dazzle.process.worker` (Temporal worker entry point).

### Tests
- **`test_parse_modules_imports.py`** — AST-based regression test: parametrised over the three runtime callers, asserts that none import from the removed `dazzle.core.dsl_parser` module. Catches future stale imports at unit-test time rather than in a downstream user's terminal.

### Agent Guidance
- **When renaming/splitting a `dazzle.core.*` module, grep for stale imports across `src/`** — the test suite mocks heavy dependencies in many places, so import errors in CLI/worker/alembic entry points won't surface in `pytest` unless explicitly pinned. The `test_parse_modules_imports.py` pattern (AST scan of known caller paths) is reusable for any other re-exported function.

## [0.61.25] - 2026-04-25

Patch bump. Closes #884 — summary/metrics tiles can now declare a `delta:` block to render the period-over-period reading ("47 marked overnight ↑ +12 (34%) vs yesterday") without having to compute deltas in Python and pass them as separate fields. Surfaced from AegisMark's investor-demo dashboard requirement; companion to the chart-mode issues (#879-883).

### Added
- **DSL**: new `delta:` block on workspace regions with `display: summary` (or `metrics`).
  ```dsl
  manuscripts_marked:
    aggregate:
      count: count(Manuscript where status = marked)
    display: summary
    delta:
      period: 1 day              # required; supports second/minute/hour/day/week/month/quarter/year (singular or plural)
      sentiment: positive_up     # optional; positive_up (default) | positive_down | neutral
      field: created_at          # optional; defaults to "created_at" on the source entity
  ```
- **IR**: `dazzle.core.ir.workspaces.DeltaSpec` (frozen Pydantic model) — `period_seconds: int`, `sentiment: str`, `date_field: str | None`, `period_label: str`. Exported from `dazzle.core.ir`.
- **Lexer**: new `TokenType.DELTA = "delta"` keyword.
- **Runtime**: `_compute_aggregate_metrics` (in `dazzle_back.runtime.workspace_rendering`) now accepts an optional `delta: DeltaSpec` parameter. When set, it fires a second aggregate query per metric over the prior window (`[now() - 2*period, now() - period]`) and decorates each metric dict with `delta`, `delta_pct`, `delta_direction` (up|down|flat), `delta_sentiment`, `delta_period_label`. Wired through the workspace handler at the main UI rendering path.
- **Template**: `workspace/regions/metrics.html` renders an arrow + signed delta + percent + comparison-period label below the value when `delta_direction` is present. Sentiment maps `up + positive_up` (or `down + positive_down`) → green, the inverse → destructive red, flat → muted.

### Tests
- **`test_workspace_delta_metric.py`** — 16 cases across 3 layers:
  - parser (7): minimal block; all keys; week unit; invalid unit raises; invalid sentiment raises; missing period raises; absent block remains None;
  - IR (3): defaults, frozen, period_seconds > 0;
  - runtime (6): positive delta up; negative delta down; flat; prior=0 → pct=0 (no div-by-zero); spec absent → no delta keys; sentiment flows through.

### Agent Guidance
- **Period-label heuristic is conservative.** Only canonical singular spellings (`1 day` / `1 week` / `1 month` / `1 quarter` / `1 year`) auto-collapse to friendly labels (`yesterday` / `last week` / etc.). `7 days` falls back to `"prior 7 days"`. If you need a custom label, follow-up work could surface a `label:` sub-key on the delta block; not in v1.
- **Calendar-aligned periods deferred.** `period: current_week` / `current_month` (per the original issue body) NOT supported in v1 — only relative durations. Deferred because daylight-saving-aware boundaries pull in `dateutil` or platform-tz logic; want to land the rolling-window MVP first.
- **`field:` defaults to `created_at`.** The runtime trusts the entity to have a `created_at` column (most do via `auto_add`). If your entity uses a different timestamp (e.g. `occurred_at`, `marked_at`), set `field:` explicitly. No auto-detect probes the entity's fields in v1.
- **Delta runs an extra query per metric.** For dashboards with many summary tiles, the delta queries add latency. The implementation batches them via `asyncio.gather`, but each tile + delta = 2 queries. Watch the dashboard render latency if you light up >8 tiles with delta.

## [0.61.24] - 2026-04-25

Patch bump. Closes #877 (Option A) — `dazzle dsl operation=fidelity` no longer attributes state-transition stories (those with `trigger: status_changed`) to `mode: create` surfaces. The Option B fix in v0.61.21+ partially closed this by skipping default-aware preconditions and transition-verb outcomes; Option A is the more principled cut: a story whose trigger IS a state transition cannot fire from a creation surface (the entity is being created, not transitioned), so the surface should never be matched in the first place.

### Fixed
- **`src/dazzle/core/fidelity_scorer.py`** — `_match_stories_to_surfaces` filters stories whose `trigger.value ∈ _TRANSITION_STORY_TRIGGERS = {"status_changed"}` from `mode: create` surfaces. Other surface modes (edit, list, view) continue to match — edit fires the transition, list/view show the lifecycle, but create can't.

### Tests
- **`test_fidelity_scorer.py::TestStatusChangedTriggerExclusion`** — five cases: status_changed excluded from create; user_click still matches create; form_submitted still matches create (THE creation trigger); status_changed still matches edit; status_changed still matches list + view (lifecycle visibility).
- **`test_fidelity_scorer.py::TestCreateModeStoryGapSuppression`** — switched fixture default trigger from `STATUS_CHANGED` to `USER_CLICK` so the Option B (default-aware / transition-verb) tests still exercise their logic without being pre-filtered by Option A.

### Cross-app verification
Total fidelity gaps across all 5 example apps: 17 → 7 (Option A closes 10 false positives on top of cycle 105+106's 31). simple_task is now fully clean (was 7). Remaining 7 gaps: contact_manager 1 (ST-007 `is_favorite` toggle, `trigger: user_click` — Option B handles defaults but the precondition value differs), support_tickets 1, ops_dashboard 4, fieldtest_hub 1 — all genuinely lifecycle-related on edit / detail surfaces or non-default-value preconditions.

### Agent Guidance
- **Add new `StoryTrigger` enum values to `_TRANSITION_STORY_TRIGGERS`** if they describe state changes that can't fire at creation time. Current set is conservative: only `STATUS_CHANGED`. Candidates worth review when added: any future `STATE_CHANGED`, `PHASE_CHANGED`, `LIFECYCLE_TRANSITION`. Don't add `USER_CLICK`, `FORM_SUBMITTED`, `EXTERNAL_EVENT`, `TIMER_ELAPSED`, `CRON_*` — those legitimately can fire from a creation surface (form submit, click "Save", external trigger creating an entity).
- **Three independent fidelity-scorer suppressions now exist for `mode: create`** — (a) Option A trigger filter (this release), (b) Option B default-aware preconditions (v0.61.22), (c) Option B transition-verb outcomes (v0.61.22). Each closes a different false-positive class. Maintain all three; they don't subsume each other.

## [0.61.23] - 2026-04-25

Patch bump. Closes #878 — `dazzle dsl operation=fidelity` flagged every search_select-rendered field as `incorrect_input_type` (severity major) because the wrapper template lacked a widget marker AND the scorer had no equivalence entry for the widget. The hidden value carrier is intentional (it pairs with a visible search input), but the structural check only saw `<input type="hidden">` against a `str` field and reported it as a mismatch. Practical impact: every `field X "..." source=...` declaration in any DSL produced 2 false-positive gaps per surface (×2 across create + edit). fieldtest_hub's `manufacturer` field (declared via `source=companies_house_lookup.search_companies`) was the canonical repro.

### Fixed
- **`src/dazzle_ui/templates/fragments/search_select.html`** — added `data-dz-widget="search_select"` to the wrapper div so `_iter_inputs_with_widget_context` (in `dazzle.core.fidelity_scorer`) can attribute the widget kind to the inner hidden input. Mirrors the existing convention used by `combobox`, `datepicker`, `daterange`, etc. in `macros/form_field.html`.
- **`src/dazzle/core/fidelity_scorer.py`** — added `"search_select": {"hidden": {"text"}}` to `_WIDGET_TYPE_EQUIVALENCES`. Mirrors the existing `richtext: {"hidden": {"text", "textarea", "select"}}` entry — both widgets render as a hidden form-submission carrier alongside a separate visible editor.

### Tests
- **`test_fidelity_scorer.py::TestWidgetRenderedInputTypes::test_search_select_widget_satisfies_str_field`** — full happy path: wrapper carries `data-dz-widget="search_select"`, scorer accepts the hidden input as satisfying the str field.
- **`test_fidelity_scorer.py::TestWidgetRenderedInputTypes::test_search_select_without_widget_marker_still_flags`** — counter-test: equivalence is gated on the marker. If the decorator goes missing during a refactor, the false-positive returns and surfaces the regression.
- **`test_inline_js_quote_safety.py::TestInlineJsQuoteSafety::test_search_select_wrapper_carries_widget_decorator`** — source-grep guard: the `data-dz-widget="search_select"` marker is load-bearing and must not be deleted by template refactors.

### Cross-app verification
fieldtest_hub fidelity gaps drop 7 → 5 (the 2 `incorrect_input_type` false positives on `device_create` + `device_edit` are gone). Total across all 5 example apps drops 19 → 17. The remaining gaps are legitimate: 13 `story_precondition_missing` (preconditions on non-default state values — Option A territory for #877) + 4 `story_outcome_missing` (edit surfaces with genuine missing fields).

### Agent Guidance
- **New widget templates must self-tag with `data-dz-widget="<kind>"` on their outer wrapper.** The fidelity scorer's `_iter_inputs_with_widget_context` walks ancestors to attribute widget kind to inner inputs — without the marker, every input falls through to the literal type check and produces false-positive gaps. Convention is set by `macros/form_field.html` (combobox, datepicker, daterange, etc.). Fragments included via `{% include %}` from `form_field.html` (like `search_select.html`) need to self-tag because the include site doesn't see the inner inputs.
- **Add a corresponding entry to `_WIDGET_TYPE_EQUIVALENCES`** in `dazzle/core/fidelity_scorer.py` whenever a new widget renders an input type different from the underlying field's expected type (e.g. hidden carrier for ref/source widgets, text carrier for date pickers).

## [0.61.22] - 2026-04-25

Patch bump. Closes the JavaScript-warning class Aegismark's QA tester observed on teacher routes — recommendation rows containing names like `O'Brien` broke inline editing. Four templates were interpolating per-record values into single-quoted JS string literals via `'{{ value | e }}'`. The Jinja `| e` filter HTML-escapes apostrophes to `&#39;`, but the browser HTML-decodes the entity back to `'` before Alpine sees the attribute value — terminating the surrounding JS string mid-word and turning `:value="editing ? editing.originalValue : 'O'Brien'"` into a JS syntax error. Alpine bailed on the binding for those records; double-quote / backslash / newline values were already silently broken in the same way.

### Fixed
- **`src/dazzle_ui/templates/fragments/inline_edit.html`** — text-input branch (line 11) and date-input branch (line 75) — replaced `'{{ edit_value | e }}'` with `{{ edit_value | tojson }}` and switched the outer `:value` attribute to single-quoted so it doesn't clash with `tojson`'s `"` delimiters. Inline-cell editing now works for any value containing `'`, `"`, `\`, or control characters.
- **`src/dazzle_ui/templates/macros/form_field.html`** — combobox `x-data` (line 74) `current:` initial value and file-upload `x-init` (line 471) `filename =` assignment — same fix applied. Combobox initialisation and file-upload preview no longer break for stored values containing apostrophes.

### Tests
- **`test_inline_js_quote_safety.py::TestInlineJsQuoteSafety`** — five source-grep cases: (1) parametrised over both fixed templates asserting the broken `'{{ X | e }}'` regex never reappears, (2) inline_edit's two `:value` lines both contain `tojson`, (3) combobox `x-data` `current` uses `tojson`, (4) file-upload filename `x-init` uses `tojson`. Source-level assertions (no rendering) so the test doesn't depend on a Jinja runtime in the test process.

### Agent Guidance
- **Never write `'{{ X | e }}'` inside a JS-evaluated HTML attribute.** Browser HTML-decodes the `&#39;` for apostrophes BEFORE Alpine evaluates the attribute as JS — the apostrophe terminates the surrounding string literal. Use `{{ X | tojson }}` (no surrounding quotes — `tojson` produces a properly JS-escaped quoted literal) and switch the outer attribute to single-quoted to avoid clashing with `tojson`'s `"` delimiters. Affects every Alpine-bound attribute (`:value`, `:class`, `@click`, `x-init`, `x-data`, etc.).
- **`| e` is for HTML text/attribute safety, not JS-string safety.** They are different escape contexts. The browser un-escapes HTML entities before Alpine's expression evaluator runs, so HTML-escaped apostrophes flow through to JS unescaped.
- **Other inline JS patterns to audit** (current call sites use schema-controlled values so the bug is latent, but the pattern is the same): `fragments/related_table_group.html` (`activeTab`), `fragments/toggle_group.html` (`toggle()`), `components/filterable_table.html` (`toggleSort()`). Switch to `| tojson` if any of those start receiving user-provided values.

## [0.61.21] - 2026-04-25

Patch bump. Closes the production-startup gap introduced by `97ac3f65` ("gate startup schema creation on environment"). That commit correctly stopped `metadata.create_all()` and `CREATE TABLE IF NOT EXISTS _dazzle_params` from running when `DAZZLE_ENV=production`, but shipped the `verify_dazzle_params_table()` check without the corresponding Alembic baseline migration that creates the table — meaning every production startup raised `MigrationError("_dazzle_params table is missing. Run 'dazzle db upgrade' before startup.")` even AFTER running `dazzle db upgrade` (no-op against an empty `versions/` directory). The hint was misleading; following it didn't unblock the failure. ADR-0017 (Alembic owns schema in production) is now actually shippable.

### Added
- **`src/dazzle_back/alembic/versions/0001_framework_baseline.py`** — root Alembic revision that creates `_dazzle_params` (key TEXT, scope TEXT, scope_id TEXT default '', value_json JSONB, updated_by TEXT, updated_at TIMESTAMPTZ default now(), PK on key+scope+scope_id). DDL matches `ensure_dazzle_params_table()` in `runtime/migrations.py:127-141` exactly so dev (which still calls `CREATE TABLE IF NOT EXISTS`) and production (which runs this migration) land on the same schema.

### Tests
- **`test_runtime_schema_startup.py::TestFrameworkBaselineMigration`** — two cases: (1) migration module loads with the expected revision id + callable upgrade/downgrade; (2) `upgrade()` against a sqlite sandbox produces the expected table with the expected columns + PK constraint. JSONB is patched to JSON for the sandbox; PostgreSQL-specific behaviour is exercised in any real environment.

### Agent Guidance
- **Production startups now require migrations.** Downstream apps setting `DAZZLE_ENV=production` must run `dazzle db upgrade` to apply the framework baseline before first boot. Without it, startup raises `MigrationError` from `verify_dazzle_params_table()`.
- **Don't rename or delete `_dazzle_params_pkey` / the `0001_framework_baseline` revision.** The hint string in `verify_dazzle_params_table` (`migrations.py:161`) points at this migration; renaming the revision id orphans existing production schemas.
- **Entity-table baseline is still on the user.** This release does not auto-bootstrap migrations for app entity tables — those continue to be created via `metadata.create_all()` in dev, and downstream apps using `DAZZLE_ENV=production` are responsible for generating their own per-app baseline (e.g. `dazzle db revision --autogenerate -m "initial schema"`) before going live. A `dazzle db baseline` command that auto-generates this is tracked separately.

## [0.61.20] - 2026-04-25

Patch bump. Closes #875 — clicking the active workspace nav link triggered an HTMX morph that landed `dzDashboardBuilder` in degraded state: empty card grid, "No widgets available" picker, and all five `saveState` labels rendered simultaneously. `alpine:init` only fires once per component instance, but idiomorph keeps the existing `x-data` element across same-route nav re-clicks — so `init()` doesn't re-run, and `cards` / `catalog` / `workspaceName` / `foldCount` stay stale while the data island below them has been replaced with fresh JSON. Compounded #866's cold-load fix by exposing the re-entry path.

### Fixed
- **`src/dazzle_ui/runtime/static/js/dashboard-builder.js` — `init` + `_hydrateFromLayout` + `destroy`** — extracted the JSON-island read into `_hydrateFromLayout()` and called it from both `init()` and a new `htmx:afterSwap` listener that fires when the swap target contains the `#dz-workspace-layout` data island. The listener filter avoids re-hydration on every region-card swap. Reset `saveState = "clean"`, clear `undoStack`, cancel any pending `_savedTimer` on re-hydrate so the multi-state labels don't stack visibly. The listener is torn down in `destroy()` to match the `#797`/`#795` pattern (no leaks across navigations).

### Tests
- **`test_dashboard_builder_triggers.py::TestRehydrateOnHtmxAfterSwap`** — six source-grep cases pinning: helper extracted, init calls helper, htmx:afterSwap listener installed, swap filter targets the data island, listener torn down in destroy, saveState reset to clean inside the helper.

### Agent Guidance
- **Alpine `init()` does NOT re-run on idiomorph re-attach.** When a same-route nav click triggers an HTMX morph, the existing `x-data` element is preserved — Alpine never tears down or re-creates the component. Any state derived from a `<script>` data island elsewhere in the swap target needs an `htmx:afterSwap` listener to re-hydrate.
- **Filter the listener narrowly.** `htmx:afterSwap` fires for every region card swap inside the workspace; check the swap target contains your specific data island (e.g. `#dz-workspace-layout`) before re-hydrating, or you'll thrash on every region load.
- **Reset transient UI state on re-hydration.** `saveState`, `undoStack`, pending timers all assume continuity. When the server has just delivered a fresh layout, treat it as a clean slate and explicitly reset — don't carry forward.

## [0.61.19] - 2026-04-25

Patch bump. Closes #874 — entity-list pages rendered duplicate sidebar items: every entity that appeared in a workspace's `nav_group` ALSO appeared as a flat auto-discovered item, producing the "Recommendations / Recommendations" stutter Tom Davies saw on /app/teachingrecommendation. Workspace pages already filtered via `_build_visible_nav` (#661); the entity-list path through `_inject_auth_context` had no equivalent dedup.

### Fixed
- **`src/dazzle_ui/runtime/page_routes.py` — `_inject_auth_context`** — after persona-filtering `nav_items` and `nav_groups`, drop any flat nav item whose route also appears as a child route in a `nav_group`. Extracted as `_dedupe_nav_items_against_groups` for testability — mirrors the same shape that `_build_visible_nav` already uses on the workspace-page path.

### Tests
- **`test_entity_page_nav_groups.py::TestDedupeNavItemsAgainstGroups`** — three cases: dedup drops overlapping routes; non-overlapping items pass through; empty groups pass through.

### Agent Guidance
- **Two nav rendering paths exist** — workspace-page (`_workspace_handler`) and entity-list (`_inject_auth_context`). Any future nav-shape change must touch both, or nav structure will diverge between the two page types. The `_dedupe_nav_items_against_groups` helper is the canonical entity-list dedup; use it (don't reimplement) when adjusting `_inject_auth_context`.

## [0.61.18] - 2026-04-25

Patch bump. Closes #876 — clicking a sidebar nav entry triggered an HTMX morph that preserved the previous page's scroll offset, landing the new page's heading above the viewport. Users had to scroll back up after every cross-page nav. Idiomorph's `morph:innerHTML` strategy preserves DOM state including scroll position, but doesn't reset the document/main-content scroll for cross-route navigation.

### Fixed
- **`src/dazzle_ui/templates/layouts/app_shell.html`** — added `scroll:#main-content:top` to the `hx-swap` directive on both the ungrouped sidebar nav anchors and the grouped child anchors. HTMX scrolls `#main-content` to the top after the morph completes, so the new page's heading lands at the top of the viewport.

### Tests
- **`test_template_html.py::test_sidebar_nav_scrolls_to_top_on_morph`** — pins the modifier on both nav anchor variants in app_shell.html.

### Agent Guidance
- **Idiomorph preserves scroll position by default.** When using `hx-swap="morph:innerHTML"` for cross-route navigation, add `scroll:<target>:top` so users land at the top of the new page. Same applies to any new nav surface (mobile menu, command palette routes, breadcrumb anchors) — match the pattern in app_shell.html.

## [0.61.17] - 2026-04-25

Patch bump. Closes #873 — workspaces auto-discovered ungrouped region sources into the sidebar nav even when the author explicitly declared a `nav_group`. Junction/admin entities used purely as data sources (e.g. `ClassEnrolment`, `QuestionTopic`, `BehaviourStudent`) leaked in as flat nav items, exposing schema-shaped vocabulary to personas (e.g. teachers) who shouldn't see those standalone list pages. Authors had no clean opt-out — drop the entity's list surface entirely (loses /app/<entity> for everyone) or accept the noisy nav.

### Fixed
- **`src/dazzle_ui/runtime/page_routes.py` — `ws_entity_nav` builder** — when a workspace declares any `nav_group`, skip auto-discovery of its region sources entirely. The author has explicitly curated the entity nav by hand; ungrouped sources stay out.
- **`src/dazzle_ui/converters/template_compiler.py` — `_entity_nav_items` builder** — mirror the same guard so entity-list pages (`/app/<entity>`) inherit the same nav shape as workspace pages. Workspaces with no `nav_groups` keep the legacy zero-config auto-discovery path.

### Tests
- **`test_entity_page_nav_groups.py::TestNavGroupsSuppressAutoDiscovery`** — two cases: ungrouped region source NOT in entity nav when `nav_group` declared; zero-config workspace still auto-discovers (regression guard).

### Agent Guidance
- **`nav_group` is now an explicit "I curated this" signal.** When migrating an existing workspace to `nav_group`, you must list every entity that should appear in the nav — pre-existing flat auto-discovery items disappear. This is the intended ergonomics: it lets authors scope a teacher workspace to the 2-3 entities the persona actually navigates to, instead of fighting the framework's auto-add behaviour.
- **Zero-config workspaces (no `nav_groups`) keep auto-discovery as before.** No migration needed for apps that haven't adopted `nav_group` yet.

## [0.61.16] - 2026-04-25

Patch bump. Closes #871 — workspace region filters threw `psycopg.errors.AmbiguousColumn` on Postgres when the source entity had a scope rule that traversed FKs (so the compiled SQL JOINed in tables with same-named columns) AND the region's `filter:` named one of those columns. Affected combos included `is_current` (boolean on multiple joined tables), `teaching_group` (FK that shares its name with the joined target table), `status`, `school`, `department` etc. AegisMark's teacher_workspace lost all six `current_context`-filtered regions to this — fully empty landing page.

### Fixed
- **`src/dazzle_back/runtime/query_builder.py` — `build_where_clause`** — when `self.joins` is non-empty, qualify every user-authored filter and search column reference with the source table alias (`"ClassEnrolment"."is_current" = $1` instead of bare `"is_current" = $1`). The scope-predicate SQL was already qualified by the predicate compiler; the gap was specifically in the user-authored filter and search paths.

### Tests
- **`test_fk_display_join.py::TestFilterTableQualification`** — three cases: filter qualified when joins present; filter NOT qualified when no joins (no noise); search qualified when joins present.

### Agent Guidance
- **Bare column references in WHERE clauses are unsafe with JOINs.** When you add a code path that injects user-authored or DSL-authored column names into a query that may later acquire JOINs (FK display, scope-predicate FK traversals, future analytics enrichments), qualify with the source table alias from the start. The `quote_identifier(builder.table_name)` is the canonical alias.

## [0.61.15] - 2026-04-25

Patch bump. Closes #870 — workspaces with a `context_selector` rendered fully empty on first load for users with no saved preference. The selector defaulted to the hard-coded "All" entry, and any region filtering on `current_context` rendered its empty state. AegisMark's teacher_workspace landed on six stacked empty states for fresh users — the selector wasn't communicated as the gate.

### Fixed
- **`src/dazzle_ui/templates/workspace/_content.html`** — when no saved `workspace.<name>.context` preference exists, fall through to `sel.options[1]` (the first real option after the hard-coded "All" entry) instead of staying on "All". The change → dispatch logic is unchanged; only the default selection differs.

### Tests
- **`test_template_html.py::TestDashboardRegionCompositeShapes::test_context_selector_defaults_to_first_option`** — pins the `sel.options[1]` fallback in the template body.

### Agent Guidance
- **Behaviour change is backwards-compatible by design.** Apps that intentionally landed on "All" will see the change but every region-filter pattern degrades gracefully — the regions either render filtered (intended) or unfiltered for the rare workspace where `current_context` isn't used. If a future app needs the "All" default explicitly, add a `default: all` knob to `context_selector` (not implemented in this commit; current default is now `first`).

## [0.61.14] - 2026-04-25

Patch bump. Closes #872 — workspace list region columns ignored field-level `visible:` predicates, so every persona saw the full column set regardless of role-gated visibility on the source surface. Detail surfaces honour `visible:` correctly via `ColumnContext.visible_condition` + per-request evaluation in `page_routes.py`; workspace regions never carried the predicate through `_build_surface_columns` (column dicts), so the per-request filter had nothing to evaluate. Result: admin-scoped fields (e.g. `academic_year`, `is_current`) leaked into teacher-persona workspace cards as columns with empty cells.

### Fixed
- **`src/dazzle_back/runtime/workspace_rendering.py` — `_build_surface_columns`** — capture each surface element's `visible:` predicate (falling back to the section-level predicate, matching `template_compiler.py`) and store it as `visible_condition` on the column dict.
- **`src/dazzle_back/runtime/workspace_rendering.py` — `_workspace_region_handler`** — when any precomputed column carries a `visible_condition`, evaluate it per-request against the current persona's roles via `dazzle_ui.utils.condition_eval.evaluate_condition` and produce a fresh filtered list (never mutate the shared startup list).

### Tests
- **`test_workspace_rendering.py::TestSurfaceColumnsVisibleCondition`** — three cases pinning the contract: element-level `visible:` attaches; section-level `visible:` falls through to columns; element overrides section.

### Agent Guidance
- **Workspace columns are dicts, detail columns are `ColumnContext` objects.** Both paths now carry `visible_condition`, but in different shapes — workspace regions filter by removing the entry; detail surfaces flip `_col.hidden = True`. The condition payload is the same `ConditionExpr.model_dump()` shape in both, so `evaluate_condition` is shared.
- **Pre-computed column metadata is shared across requests.** When you need per-persona shaping at request time, copy the list — never mutate the entry in `ctx.precomputed_columns` or you'll see cross-request leakage between personas.

## [0.61.13] - 2026-04-24

Patch bump. Closes #869 — the feedback widget's "Your feedback has been resolved" toast re-fired on every page load for any non-admin user with a resolved `FeedbackReport`. Root cause was upstream of the widget's `_markNotified` PUT: the `GET /feedbackreports?notification_sent=false` poll was silently ignoring that predicate, because `notification_sent` wasn't in the admin list surface's `ux.filter` (and bare query-param filters are gated on that list). The server returned acknowledged rows anyway; the widget toasted every one; the PUT *did* persist but had no observable effect.

### Fixed
- **`src/dazzle/core/linker.py` — `_build_feedback_list_view`** — `notification_sent` and `reported_by` added to `ux.filter`. The route generator's bare query-param pathway (`route_generator.py:1558`) accepts `?field=value` only when `field ∈ filter_fields`, and that list is built from `ux.filter` via `build_entity_filter_fields`. Without the update, both predicates were dropped by `_reserved_params` filtering and never reached the repository's WHERE clause. `reported_by` is also newly respected: admins (entity scope: `all`) previously saw toasts for *every* resolved report, not just their own.

### Tests
- **`test_feedback_widget.py::test_admin_surface_filter_includes_notification_sent`** — pins the contract: both fields must appear in `feedback_admin.ux.filter`.

### Agent Guidance
- **Widget-driven API filters must be in `ux.filter`**. The route generator rejects bare `?field=value` query params unless `field` is declared in the list surface's `ux.filter`. This is a security feature (you can't filter on arbitrary columns), but it means *every* client-side filter the widget needs must have a matching DSL declaration. Filter chips are a side-effect — admins will see `notification_sent` and `reported_by` as filter options in the admin UI, which is harmless and arguably useful.
- **When adding a new client-driven filter**: update `ux.filter` on the relevant list surface and add a test that pins both the DSL declaration and the route-generator behaviour. Don't try to work around the gate by routing through a headless endpoint — that just loses the filter audit trail.

## [0.61.12] - 2026-04-24

Patch bump. Closes #868 — the consent banner served correctly after #867, but every button click (Accept all / Reject all / Save choices) 403'd on `POST /dz/consent` with `{"detail":"CSRF token missing or invalid"}`. Anonymous marketing-page visitors don't carry a `dazzle_csrf` cookie (the cookie is issued on first app-page visit, not on the site template), and `site_base.html` doesn't render a `<meta name="csrf-token">` tag, so there's no client-side token to forward. The banner rendered, looked interactive, and did nothing.

### Fixed
- **`src/dazzle_back/runtime/csrf.py`** — added `/dz/consent`, `/dz/consent/banner`, `/dz/consent/state` to `CSRFConfig.exempt_paths`. The endpoints are idempotent cookie-setters with no authority-escalating side effects; same-origin is still enforced by the `credentials: "same-origin"` policy in `dz-consent.js`. This matches the existing exemption pattern for `/feedbackreports` (also issued from anon pages).

### Tests
- **`test_consent_csrf_exempt.py`** — 5 tests pin the contract: default `CSRFConfig` lists all three paths as exempt, `POST /dz/consent` without any CSRF token returns 204 (not 403), `GET /dz/consent/state` returns 200, `GET /dz/consent/banner` returns 200/204, and a control test confirms a *non-exempt* POST still 403s (sanity: middleware not globally disabled).

### Agent Guidance
- **CSRF exemption is the right pattern for consent-style endpoints**. They're called before a user has any authenticated session, can't rely on the `dazzle_csrf` cookie being issued, and have no CSRF-sensitive side effects (the consent cookie itself is set by the request, not consulted for authority). Don't try to force CSRF on this path — add the new endpoint to `CSRFConfig.exempt_paths` following the pattern on lines 36–55.
- **When building a new anon-safe API endpoint**: either (1) mount it under one of the `exempt_path_prefixes` (e.g. `/auth/`, `/webhooks/`) or (2) add its exact path to `exempt_paths`. Don't try to thread a CSRF token through marketing-page JS — there's no infrastructure for it and the token wouldn't be meaningful without a session.

## [0.61.11] - 2026-04-24

Patch bump. Closes #867 — the v0.61.0 consent banner + analytics JS files were packaged under `src/dazzle_ui/static/js/`, but `site_base.html` references them via the `static_url` filter which resolves to `/static/*` served from `src/dazzle_ui/runtime/static/`. Every app declaring an `analytics:` block 404'd on `dz-consent.js` and `dz-analytics.js`, leaving the consent banner rendered but its buttons inert (no JS attached ⇒ clicks did nothing ⇒ GTM never initialised). Worse than no banner at all for visitors outside EEA who'd otherwise auto-grant.

### Fixed
- **Moved `src/dazzle_ui/static/js/dz-consent.js` and `dz-analytics.js` to `src/dazzle_ui/runtime/static/js/`** — same directory as every other framework JS file (`dz-alpine.js`, `dz-a11y.js`, `feedback-widget.js`, …). Site template references via `static_url` now resolve and the scripts serve correctly. No code changes; pure file relocation.

### Tests
- **`test_analytics_js_location.py`** — 4 regression tests pin the shape: `dz-consent.js` and `dz-analytics.js` live under the runtime static root, the legacy `dazzle_ui/static/js/` only carries `site.js` (which has a bespoke `/site.js` route handler), and `site_base.html` still references both scripts via `static_url`.

### Agent Guidance
- **Framework JS goes in `src/dazzle_ui/runtime/static/js/`** — that's the directory the runtime mounts at `/static/*`. The `src/dazzle_ui/static/` directory only exists for `site.js`, which is read by a custom route handler (`site_renderer.get_site_js`) and served at `/site.js` directly.
- **When adding a new JS file referenced via `static_url`**: put it in `runtime/static/js/`. The source-grep test above now catches regressions.

## [0.61.10] - 2026-04-24

Patch bump. Closes #858 — the `via EntityName(...)` scope-rule form required flat single-segment junction fields, so two-hop traversals like `teaching_group.teacher.user = current_user` errored at the first `.` with "Expected '=' or '!=' in via binding". AegisMark needed this shape for teacher-to-pupil visibility routed through `ClassEnrolment → TeachingGroup → StaffMember → User` and was working around it with denormalised FKs.

### Fixed
- **`src/dazzle/core/dsl_parser_impl/entity.py`** — `_parse_via_condition` now accumulates dotted segments on the junction-field side via a `while self.match(TokenType.DOT)` loop that mirrors the existing pattern in `_parse_comparison`. The full dotted path is stored verbatim on `ViaBinding.junction_field`.
- **`src/dazzle_back/runtime/predicate_compiler.py`** — new `_compile_dotted_junction_predicate` helper expands a dotted path into a nested `IN (SELECT id FROM ...)` chain that walks the junction's FK graph segment-by-segment. The innermost subquery holds the `<final_col> <op> <value>` comparison; each wrap selects `id` from the entity that *owns* the next FK (not its target — the initial implementation had this reversed). `_compile_exists_check` grew a `fk_graph` parameter and routes dotted bindings through the new helper while flat bindings keep the single-column shape.
- **`src/dazzle/core/validator.py`** — `_validate_predicate_node` validates dotted junction fields against the FK graph: each intermediate segment must resolve as an FK hop and the terminal segment must exist as a column on the final entity. Unknown segments produce a clear `dazzle validate` error naming the bad hop.

### Tests
- **`test_via_dotted_paths.py`** — 6 tests pin the full path: parser accepts dotted paths and preserves them on `ViaBinding`, linker produces an `ExistsCheck` with the dotted path intact, compiler emits a correctly-nested `IN (SELECT ...)` chain walking `TeachingGroup → StaffMember → User`, flat bindings keep their single-column shape, valid dotted via produces no lint error, unknown segment surfaces via `lint_appspec`.

### Agent Guidance
- **Dotted `via` paths walk the junction's FK graph** — `via ClassEnrolment(student_profile = id, teaching_group.teacher.user = current_user)` means "exists a ClassEnrolment whose `teaching_group.teacher.user` equals the current user". All intermediate segments must be FK fields on successive entities; the terminal segment is a plain column (often itself a FK, compared against `current_user` / literal / parent id).
- **Zero-hop `via` bindings still work** — `via M(field = id, user = current_user)` has no dotted paths; the compiler's fast path for flat bindings is unchanged.
- **`dazzle validate` now catches bad paths** — if a hop doesn't exist on the FK graph the error names it ("Entity 'TeachingGroup' has no FK for segment 'nonexistent_fk' ..."), so misconfigured scope rules fail at validate time rather than runtime.

## [0.61.9] - 2026-04-24

Patch bump. Closes #865 — workspace list regions issued one follow-up `SELECT *` per FK relation via the batched `_load_to_one` path. For AegisMark's teacher workspace (14 regions × 3-5 FKs) that's ~50+ round-trips per page load. The FK-display fast path now collapses each region's FK display resolution into a single LEFT JOIN'd query, matching the single-SQL-statement approach the issue proposed.

### Fixed
- **`src/dazzle_back/runtime/relation_loader.py`** — new `build_display_join_plan(entity_name, include)` returns `(joins, extra_cols, fallback_relations)`: LEFT JOINs for each to-one relation whose target entity has a registered `display_field`, aliased select columns pulling `{target}.{display_field} AS "{rel}__display"`, and a fallback list for relations that didn't qualify. Paired with `apply_display_joins_to_rows` which folds the projected display columns into the same `{id: ..., __display__: ...}` FK-dict shape the batched path produces — downstream consumers (`_inject_display_names`) work unchanged.
- **`src/dazzle_back/runtime/query_builder.py`** — `QueryBuilder` gains `extra_select_cols: list[str]` alongside the existing `joins: list[str]` field (which was declared but never emitted). `build_select` now appends joins between the FROM and WHERE clauses and merges `extra_select_cols` into the SELECT list. The base columns switch from `*` to `{table}.*` when JOINs are present so the aliased display columns don't collide with the base table's fields.
- **`src/dazzle_back/runtime/repository.py`** — `Repository.list` gains an opt-in `fk_display_only: bool = False` parameter. When enabled with `include`, it invokes the new display-join plan and reshapes rows via `apply_display_joins_to_rows`; relations that didn't qualify (no display_field, to-many) fall through to the existing batched `_load_to_one` path. Other callers (nested entity endpoints that want full related rows) are unaffected.
- **`src/dazzle_back/runtime/workspace_rendering.py`** — both workspace-region call sites (`render_page` fetch + `fetch_region_data` batch path) pass `fk_display_only=True` so workspace lists consume the fast path.

### Tests
- **`test_fk_display_join.py`** — 9 tests pin the contract: JOIN plan emits correctly-quoted identifiers, no-display-field falls back, to-many falls back, mixed includes split correctly, row folding produces FK-dicts, null FKs become `None`, missing display columns pass through unchanged, QueryBuilder emits joins + extra cols, bare SELECT still uses `*`.

### Performance
- Typical list region: 1 main + N FK follow-ups ⇒ 1 JOIN query. For a region with 3 FKs this is a 4× reduction in database round-trips. AegisMark teacher workspace (profiled baseline: ~1.5s on ClassEnrolment × 40 rows) should see the FK-resolution component collapse from ~400-600ms to ~50-100ms.

### Agent Guidance
- **`repo.list(fk_display_only=True)` is the workspace list-region contract** — use it for any list view that only needs FK display strings, not full nested entities. Nested-entity endpoints that need relation bodies should leave it `False` (the default).
- **To unlock the fast path for a new entity**: declare `display_field:` on the FK target entity. Without it, the relation silently falls back to the batched path — still correct, just no longer a single-query win. The existing `_lint_fk_targets_missing_display_field` check (#652) already nudges DSL authors toward this declaration.

## [0.61.8] - 2026-04-24

Patch bump. Closes #857 — a workspace region declaring `filter: <fk> = current_context` silently misfired because `_extract_condition_filters` had no handling for the `current_context` sentinel. The selected-entity id was already wired from the URL query param into `_filter_context["current_context"]` in `workspace_rendering.py`, but never threaded into the SQL-filter extractor — so the literal string `"current_context"` fell through to the "plain literal" branch and was applied as the filter value verbatim, resulting in zero matches. Region queries ignored the selector entirely.

### Fixed
- **`src/dazzle_back/runtime/route_generator.py`** — `_extract_condition_filters` gains an optional `context_id: str | None = None` kwarg. Both the AccessConditionSpec path (line ~508) and the IR ConditionExpr path (line ~586) now recognise the `current_context` sentinel and resolve it to `context_id` when a selection is active. When the selector is cleared (`context_id is None`), the filter is skipped so the existing persona scope applies unfiltered — matching the intent from #857. The literal-string fallback now also excludes `"current_context"` so it can't collide with the new sentinel.
- **`src/dazzle_back/runtime/workspace_rendering.py`** — both `_extract_condition_filters` call sites (top-level region fetch + `fetch_region_data` batch path) now pass `context_id=_context_id` (or `filter_context.get("current_context")`), threading the query-param value through to the filter evaluator.

### Tests
- **`test_current_context_filter.py`** — 7 tests covering the new behaviour: AccessConditionSpec + IR ConditionExpr paths, context-present vs context-cleared, literal-string non-regression, combined `current_user` AND `current_context`, and backwards compatibility for callers that don't pass the new kwarg.

### Agent Guidance
- **`current_context` is a new filter sentinel** — same pattern as `current_user`. Use it in region `filter:` clauses on workspaces that declare a `context_selector`, e.g. `filter: teaching_group = current_context`. When the user picks a value in the selector, the FK filter activates; when they clear it, the persona scope runs unfiltered.
- **Direct-FK only**: the sentinel resolves against whichever column you compare it to, so the source entity must have a direct FK to the selector entity. For indirect routes use a dotted path with a scope rule, not a region filter.

## [0.61.7] - 2026-04-24

Patch bump. Closes #861 — a workspace region sourced from entity A declaring `action: <surface>` where that surface is bound to a different entity B silently misfired at runtime when the action URL expected the FK on A referencing B. Three symptoms in one: (1) row endpoints expanded FK dicts into `{id: ..., display: ...}` and `action_id_field` wasn't forwarded to the template, so `item[id]|string` produced `{'id': '...'}`; (2) template fragments hard-coded `item.id` instead of honouring the region's `action_id_field`; (3) `dazzle validate` produced no signal when the FK probe would return zero or multiple matches.

### Fixed
- **`src/dazzle_ui/runtime/template_renderer.py`** — new `resolve_fk_id` Jinja filter robustly extracts the id from a FK value regardless of whether it's been expanded into a dict by the FK joiner or left as a scalar UUID/string. Registered globally so every region template can use it.
- **`src/dazzle_back/runtime/workspace_rendering.py`** — `render_fragment(...)` now forwards `action_id_field` from the `RegionContext` into the per-item template render context; previously the field never crossed the render boundary.
- **Region templates** (`list`, `grid`, `kanban`, `queue`, `activity_feed`, `timeline`, `metrics`, `tab_data`, `tree`) — switched from `item[action_id_field|default('id')]|string` (which breaks on dict-valued FKs) to `item[action_id_field|default('id')]|resolve_fk_id`. Tree template applies the same fix to `node[...]`.
- **`src/dazzle/core/validator.py`** — new `validate_workspace_region_actions` check errors at validate time when a cross-entity `action:` has zero FK candidates ("no FK field referencing 'Target'") or multiple candidates ("ambiguous FK — runtime cannot pick one automatically"). Wired into the main `lint_appspec` flow so `dazzle validate` catches the misconfiguration before the app ships.

### Tests
- **`test_region_action_fk_validation.py`** — 5 tests pin the validator contract: same-entity action is allowed, single FK resolves cleanly, zero FK errors, ambiguous (2+) FKs error with both field names listed, check surfaces via the non-extended `lint_appspec` path.

### Agent Guidance
- **Cross-entity region actions require an unambiguous FK**. If you declare `source: A` + `action: <surface on B>`, entity A must have exactly one `ref B` field. Zero or multiple is now a `dazzle validate` error — fix by adding the FK, renaming one of the refs, or changing the action to a surface on A.
- **Template fragment rendering**: when writing a new region template, use `|resolve_fk_id` (not `|string`) on any field that could be an FK. The filter handles both raw scalars and expanded FK dicts. Hard-coding `item.id` bypasses the region's `action_id_field` contract.

## [0.61.6] - 2026-04-24

Patch bump. Closes #859 — feedback widget polled `GET /feedbackreports?reported_by=...&status=resolved&notification_sent=false` on every page load and got 403 for non-admin personas, so the "your feedback has been resolved" toast never fired for the users who actually submitted the feedback. Root cause: `allow_personas=["admin", "super_admin"]` on the auto-generated `feedback_admin` + `feedback_edit` surfaces leaked onto the shared entity endpoints (`GET /feedbackreports`, `PUT /feedbackreports/{id}`), gating them to admin-only before Cedar's entity-level check could consult the `scope: all for: *` rule.

### Fixed
- **`src/dazzle/core/linker.py`** — `_build_feedback_report_entity` replaces the blanket `scope: all for: *` with two rules per operation: `scope: reported_by = current_user.email for: *` (any authenticated user → own rows) and `scope: all for: admin, super_admin` (admins → every row). Non-admin feedback-widget polls now succeed and return only their own reports.
- **`_build_feedback_admin_surface`** + **`_build_feedback_edit_surface`** — `allow_personas` dropped. Persona-level restriction is now enforced at the entity-level scope (own rows only), which is also the correct policy surface for row-level filtering. The UI pages still filter correctly: admins see all reports, non-admins see their own.

### Tests
- **`test_feedback_widget.py::TestFeedbackReportScopeRules`** — 3 new tests pin the scope rule shape: `reported_by = current_user.email` condition for every op with `personas=["*"]`; unconditional admin rule; exact field + value on the self-scope comparison.
- Two existing tests updated: `test_admin_surface_auth_required_no_persona_gate` and `test_edit_surface_auth_required_no_persona_gate` now assert the persona gate is intentionally empty.

### Agent Guidance
- **Surface `allow_personas` is UI-level only**: it gates who can navigate to the rendered page. Don't rely on it to secure the underlying API endpoint — the surface → endpoint converter propagates it onto the shared entity endpoints, which share across every surface targeting the same entity.
- **Row-level restriction lives in entity `scope:` rules**. Express "user sees their own rows" as `scope: <owner_field> = current_user.<user_attr> for: *`; express "admins see everything" as `scope: all for: admin, super_admin`. The runtime intersects the right rule with the request's persona.
- **Feedback widget lifecycle** — with this fix, `_checkResolved` + `_markNotified` JS paths both succeed for non-admin users; the resolved-report toast fires exactly once per report (until `notification_sent=true` is persisted), closing the notification loop as originally intended.

## [0.61.5] - 2026-04-24

Patch bump. Closes #863 — entity-list pages (`/app/<entity>`) showed a reduced sidebar compared to workspace pages because the entity-list code path (`template_compiler.py`) never populated `PageContext.nav_groups`. `app_shell.html` was already rendering `nav_groups | default([])` — the field simply wasn't set, collapsing the sidebar's group structure whenever the user navigated between an entity and its workspace.

### Fixed
- **`src/dazzle_ui/runtime/template_context.py`** — `PageContext` gains `nav_groups` + `nav_groups_by_persona` fields (default empty list / dict).
- **`src/dazzle_ui/converters/template_compiler.py`** — builds workspace `nav_group` declarations into the same dict shape `page_routes.py` already produces for workspace pages. Assigns them to every entity-surface context + the `/` fallback. Dedupes by label so two workspaces declaring the same group name don't produce sidebar duplicates.
- **`src/dazzle_ui/runtime/page_routes.py`** — mirrors the per-persona resolution path: when a user's role matches a persona in `nav_groups_by_persona`, the request-scoped `nav_groups` is replaced with the persona's subset. Matches the existing `nav_items` / `nav_by_persona` pattern.

### Tests
- **`test_entity_page_nav_groups.py`** — 5 tests pin the contract: entity-list ctx inherits nav_groups, children have correct routes, workspace + entity pages share the same group structure, duplicates collapse, field always exists.

### Agent Guidance
- **Templates read `nav_groups` directly** — no conditional needed. Field is now always present on `PageContext`.
- **New workspace code paths must populate `nav_groups`** alongside `nav_items` so the sidebar stays continuous. `page_routes.py:1676-1700` shows the canonical build pattern.
- **Per-persona filtering is opt-in**: resolution only fires when `nav_groups_by_persona` has an entry for a role. Workspaces without persona restrictions publish to the global `nav_groups` so non-persona-tagged users still see the groups.

## [0.61.4] - 2026-04-24

Patch bump. Closes #860 — vendored minified libraries (tom-select, quill, pickr) shipped with trailing `//# sourceMappingURL=...` comments pointing at `.map` files that aren't part of the vendor directory. Any developer opening DevTools saw five 404s per page: `tom-select.complete.min.js.map`, `tom-select.min.css.map`, `quill.js.map`, `quill.snow.css.map`, `pickr.min.js.map`. Noisy in logs, distracting during debugging.

### Fixed
- Stripped the trailing `sourceMappingURL` comment from the five affected vendor files in `src/dazzle_ui/runtime/static/vendor/`. Files stay valid minified JS/CSS — the sourcemap reference was the only removed content. Node's `--check` parser confirms all three JS bundles still parse cleanly.

### Tests
- **`test_vendor_sourcemap_refs.py`** — regression guard: every file in `src/dazzle_ui/runtime/static/vendor/` is scanned for `sourceMappingURL` references, and any reference pointing at a `.map` file not shipped in the vendor dir fails the test. Catches regressions when a vendor library is re-fetched from upstream without running the strip step.

### Agent Guidance
- **Vendoring a new minified library**: strip `sourceMappingURL` comments from the bundled file, or commit the matching `.map` alongside it. The test catches both failure modes — don't work around it.

## [0.61.3] - 2026-04-24

Patch bump. Closes #862 — Safari renders the CSV export inline instead of triggering a download. Root cause: `<a href="...?format=csv" download>` + `Content-Disposition: attachment` isn't enough on Safari for same-origin `text/csv` responses — Safari honours its own inline-render heuristic over the header. User loses their workspace context to a full tab navigation.

### Fixed
- **`src/dazzle_ui/runtime/static/js/dz-alpine.js`** — new `window.dz.downloadCsv(endpoint, filename)` helper. Fetches via `credentials: "same-origin"`, converts response to a Blob, creates a transient object-URL + synthetic `<a download>`, programmatically clicks to force the download, then revokes the URL. Failures surface via `window.dz.toast` + console.error.
- **`src/dazzle_ui/templates/workspace/regions/list.html`** — the CSV export anchor is now a button that calls `window.dz.downloadCsv` with the endpoint and filename from `data-dz-csv-*` attributes. Works on Safari + every other browser; the workspace context is preserved (no tab navigation).

### Tests
- **`test_dz_alpine_csv_download.py`** — new source-regression tests pin the helper's contract (fetch + Blob, download attribute, revoke URL, toast-on-error).
- **`test_workspace_routes.py`** — `test_csv_export_link_always_present` renamed to `test_csv_export_button_always_present` and asserts the new `window.dz.downloadCsv` JS call.

### Agent Guidance
- **`<a download>` is not reliable on Safari** for server-generated file responses. Use `window.dz.downloadCsv` (or the same fetch-Blob-click pattern) for any file-download UX across the framework. The same helper will be extended to other content types if/when they need the same fix.

## [0.61.2] - 2026-04-24

Patch bump. Closes #864 — every above-fold workspace region fetched twice on first paint because the template emitted `hx-trigger="load, intersect once"` for every card. `load` fires when HTMX processes the element; `intersect once` fires once the IntersectionObserver reports the element visible (which, for above-fold cards, happens in the same paint cycle). Result: ~20% wasted backend work per login on production workspaces.

### Fixed
- **`src/dazzle_ui/runtime/page_routes.py`** — `fold_count` now threaded into the workspace layout data island (previously only on the server-side WorkspaceContext).
- **`src/dazzle_ui/runtime/static/js/dashboard-builder.js`** — new `foldCount` state + `isEagerCard(card)` + `cardHxTrigger(card, sseEnabled)` helpers. Above-fold cards get `hx-trigger="load"`; below-fold cards get `"intersect once"`. SSE triggers are appended when `sseEnabled=true`.
- **`src/dazzle_ui/templates/workspace/_content.html`** — static `hx-trigger="load, intersect once..."` replaced with Alpine-bound `:hx-trigger="cardHxTrigger(card, ...)"`.

### Changed
- **Workspace region double-fetch eliminated**. Each region fetches exactly once on first paint.
- **Tests**: `test_dashboard_builder_triggers.py` adds source-regression tests for the new helpers; `test_workspace_routes.py` updated to verify the dynamic `:hx-trigger` binding + signalling of `sseEnabled`.

### Agent Guidance
- **Trigger selection is JS-side now**. If you add a new region type or change fold behaviour, update `cardHxTrigger` in `dashboard-builder.js` — don't revert to static `hx-trigger` in templates or the double-fetch returns.
- **Legacy workspaces without `fold_count` in the data island default to `isEagerCard → true`** (all cards use `load`). This preserves the pre-fix behaviour for any stored layout JSON that predates #864.

## [0.61.1] - 2026-04-24

Patch bump. Closes #866 — dashboard builder rendered in degraded state when Alpine's `alpine:init` didn't fire (HTMX morph race, layout-JSON parse error, etc.). Pure template fix: `x-cloak` added to five status-label spans inside the save button in `_content.html` and the "No widgets available" div in `_card_picker.html`. The existing `[x-cloak] { display: none }` rule in `dazzle-layer.css` hides these elements until Alpine takes control; failed init now produces a blank control panel rather than five stacked status labels + ghost catalog.

### Fixed
- **`src/dazzle_ui/templates/workspace/_content.html`** — 5 `x-show="saveState === '...'"` spans gain `x-cloak`.
- **`src/dazzle_ui/templates/workspace/_card_picker.html`** — `x-show="catalog.length === 0"` gains `x-cloak`.

## [0.61.0] - 2026-04-24

**Analytics, Consent & Privacy — stable release.** Completes the 6-phase design started in `docs/superpowers/specs/2026-04-24-analytics-privacy-design.md`. This release rolls up rc1-rc5 and adds Phase 6 (per-tenant analytics resolution).

### Added (Phase 6)

- **`TenantAnalyticsConfig`** — resolved per-tenant / per-request analytics config: `tenant_slug`, `providers` list, `data_residency`, `consent_override`, `privacy_page_url`, `cookie_policy_url`, `ga4_api_secret_env`, `extra`. Frozen dataclass.

- **`TenantAnalyticsResolver`** protocol: `(request) → TenantAnalyticsConfig`. Apps plug in their own resolver via `set_tenant_analytics_resolver()` during startup. Single-tenant apps rely on the default `make_app_wide_resolver()` which returns the DSL-declared config for every request.

- **Process-wide resolver registry** — `set/get/clear_tenant_analytics_resolvers`. App factory registers the default app-wide resolver at boot unless a custom one has already been installed.

- **`resolve_for_request()`** — fail-closed single call-site that every consumer (site routes, consent routes, security middleware) uses. Resolver exceptions or wrong return types → strict empty config, not a crash.

- **Per-request CSP resolution** — `_resolve_request_providers(request, fallback)` helper in `security_middleware`. CSP header now unions provider origins per-request from the resolver. Cross-tenant isolation enforced: tenant A's response never carries tenant B's script-src origins.

- **`tenant_slug` in page context** — `SitePageContext.tenant_slug`. Populates `data-dz-tenant` on `<body>` so client-side analytics bus tags events with the correct tenant. Already referenced by Phase 4's `dz-analytics.js`.

- **`_resolve_consent()` returns 6-tuple** (internal): consent dict, JSON, active providers, tenant_slug, privacy_url, cookie_url — all per-request, all from the resolver.

- **20 new tests** (`tests/unit/test_tenant_analytics_resolver.py`) covering the config shape, app-wide resolver derivation from DSL, registry set/get/clear, fail-closed behaviour, and cross-tenant isolation (two tenants → two distinct CSP headers).

### Changed

- **`create_site_page_routes`** accepts new consent / analytics parameters but app_factory now derives them from the resolver rather than passing them through. Backward-compat — existing callers still work.

- **`app_factory.assemble_post_build_routes`** registers the default tenant resolver alongside the consent router. Custom resolvers (set via startup hook) are respected; no auto-registration clobbers them.

### Rolled-up from rc1-rc5

- **rc1 (Phase 1)**: `pii()` field modifier + `subprocessor` construct + framework subprocessor registry (8 defaults) + `strip_pii()` + `dazzle analytics audit` CLI.
- **rc2 (Phase 2)**: Consent state + `dz_consent_v2` cookie + banner + `/dz/consent` routes + privacy-page / cookie-policy / ROPA generators + `dazzle compliance privacy` CLI.
- **rc3 (Phase 3)**: `ProviderDefinition` + GTM + Plausible providers + `analytics:` DSL block + CSP origin injection.
- **rc4 (Phase 4)**: Event vocabulary `dz/v1` (6 events) + `dz-analytics.js` client bus + template `data-dz-*` injection + dev/trial/qa disable semantics.
- **rc5 (Phase 5)**: Server-side sinks + GA4 Measurement Protocol + `analytics.server_side:` DSL subsection + event bus bridge.

### Agent Guidance

- **Apps with real tenants**: install a resolver at startup via `set_tenant_analytics_resolver(my_resolver)`. The resolver receives the Starlette Request and returns a `TenantAnalyticsConfig`. Look up your tenant from `request.url.hostname` / `request.state.tenant` / whatever your multi-tenancy convention is.
- **Resolvers should cache**: the framework calls the resolver on every analytics-touching request. If your tenant lookup hits a database, add in-process / Redis caching with your own invalidation rules.
- **Fail-closed is the contract**: the framework intentionally never raises from the resolver up to the publisher. Return a config with `providers=[]` to disable analytics for a tenant (freemium tier, trial account, etc.); don't rely on exceptions as signalling.
- **Cross-tenant isolation**: the test suite pins that two tenants on the same process produce two distinct CSP headers. If you introduce caching, make sure it's keyed on the tenant, not the process.
- **Phase 6 completes the design spec**. Further analytics work is user-initiated — adding providers (PostHog / Segment / Fathom), richer event schemas, or deeper tenant features.

## [0.61.0rc5] - 2026-04-24

Phase 5 of the **Analytics, Consent & Privacy** design: server-side analytics sinks via the existing event bus. Business events (audit, state transitions, completed orders) can now forward to Google Analytics 4's Measurement Protocol from server code — ad-blocker-proof, PII-safe, and independent of client JS / consent state for business-critical signals.

### Added

- **`AnalyticsSink` protocol** + shared types (`AnalyticsEvent`, `TenantContext`, `SinkMetrics`, `SinkResult`) in `dazzle.compliance.analytics.sinks.base`. Sinks implement `async emit(event, tenant) -> SinkResult` and track success/failure/drop counters.

- **`GA4MeasurementProtocolSink`** — posts to `https://www.google-analytics.com/mp/collect`. API secret from `DAZZLE_GA4_API_SECRET` env (never from DSL or TOML). Retries with exponential backoff on 5xx/network; drops on 4xx (bad event shape won't be fixed by retry). Missing secret or measurement_id → logs + returns `ok=False`, no HTTP call.

- **`analytics.server_side:` DSL subsection** — declare the sink + default measurement ID + bus topic globs:
  ```dsl
  analytics:
    server_side:
      sink: ga4_measurement_protocol
      measurement_id: "G-XXXXXX"
      bus_topics: [audit.*, transition.**, order.completed]
  ```
  Parser validates required `sink:`; link-time validation deferred to bridge construction.

- **`AnalyticsServerSideSpec`** IR type. Extends `AnalyticsSpec` with optional `server_side` field.

- **`AnalyticsBridge`** — routes bus events to sinks. Matches `event_type` against topic globs (single `*` = one segment, `**` = any remainder), applies PII stripping via `strip_pii()` when entity schema is known, invokes sink emission. Honors `analytics_globally_disabled()` (dev/trial/qa suppression from Phase 4). Errors never propagate — they surface via metrics + logs only.

- **Sink registry** — `FRAMEWORK_SINKS` maps sink name → factory. GA4 MP ships as first entry. Adding a sink is one factory + one registry entry.

- **`match_topic_glob()`** public helper — usable by downstream consumers who need routing logic without the full bridge.

- **27 new tests** (`tests/unit/test_analytics_sinks.py`) covering sink retry/drop behaviour, bridge topic matching, PII-safe payload coercion, disable-gate integration, and spec → bridge resolution.

### Agent Guidance

- **GA4 API secret must come from env.** `DAZZLE_GA4_API_SECRET` is a runtime secret. The DSL / TOML intentionally cannot declare it — committing secrets is the bug this avoids.
- **Server-side sinks run ALONGSIDE client-side providers.** They capture what GTM can't (ad-blocked requests, non-JS clients, state transitions that happen outside a browser). They don't replace the client layer — they complement it.
- **Bridge is best-effort.** Sink errors never fail the publisher. Use `sink.metrics.failure_total` to monitor delivery; missing events = reliability issue, not correctness issue.
- **Topic globs aren't auto-expanded to bus subscriptions.** `start_bridge_consumer()` skips wildcard topics — expand them in caller code against your known topic catalog. Glob expansion against the full event catalog is a future extension.
- **Tenant resolver is pluggable.** Pass a callable that maps envelope → TenantContext if you need per-tenant measurement IDs. Phase 6 will wire this via the tenant entity automatically.
- **entity_specs_by_name enables PII stripping.** Pass the entity spec map from AppSpec to get automatic `pii()`-field redaction on bridge payloads. Without it, payloads pass through untouched (safer for audit/compliance topics that are already PII-aware).

## [0.61.0rc4] - 2026-04-24

Phase 4 of the **Analytics, Consent & Privacy** design: client-side event vocabulary, htmx integration, template-layer `data-dz-*` attribute injection, and dev/trial/qa disable semantics. The framework now auto-emits structured events onto `window.dataLayer` — consumed identically by GTM, Plausible, PostHog, or any bus-aware provider.

### Added

- **Event vocabulary v1** (`dz/v1`) pinned in `dazzle.compliance.analytics.event_vocabulary`. Six events: `dz_page_view`, `dz_action`, `dz_transition`, `dz_form_submit`, `dz_search`, `dz_api_error`. Every event carries `dz_schema_version="1"` plus optional `dz_tenant`. Parameter names are snake_case, value types are primitive, string values clamp to 100 chars (URLs 255). Drift test `tests/unit/test_event_vocabulary_v1.py` pins the schema so changes are explicit; additive-only rule documented.

- **`dz-analytics.js`** — framework-owned client bus. Hooks `htmx:afterSwap` for page views, click delegation for `[data-dz-action]`, `htmx:afterRequest` for form submits + API errors, debounced input for `[data-dz-search]`. PII-safe: reads from `data-dz-*` attributes only, never from input values. Loaded automatically when `active_analytics_providers` is non-empty.

- **Template `data-dz-*` attribute injection** — `app_shell.html` main element emits `data-dz-surface` + `data-dz-workspace`; body tag emits `data-dz-tenant` + `data-dz-persona-class`; `detail_view.html` action/edit/delete/transition buttons emit `data-dz-action` + `data-dz-entity`. Authors never write these by hand — they fall out of the DSL compilation.

- **Disable semantics** — `analytics_globally_disabled()` respects `DAZZLE_ENV={dev,development,test}` and `DAZZLE_MODE={trial,qa}` to suppress emission. `resolve_active_providers()` returns `[]` under these conditions regardless of DSL declaration. Override via `DAZZLE_ANALYTICS_FORCE=1` for framework devs exercising the stack in dev.

### Changed

- **`SitePageContext`** doesn't change further — the banner + provider injection from Phase 2/3 already drives the JS bus load.
- **`site_base.html`** loads `js/dz-analytics.js` alongside `js/dz-consent.js` when providers are active. Both gated on the same condition so users who opt out entirely incur no JS weight.

### Agent Guidance

- **The event vocabulary is a public contract.** If you need a new event, add an `EventSchema` to `event_vocabulary.py`, update the drift test's EXPECTED_* constants, and add a CHANGELOG entry. Never rename an existing event or remove a parameter without cutting a new vocabulary version.
- **PII stays server-side.** The JS bus reads from `data-dz-*` attributes only. If a surface needs to emit entity IDs, the DSL author adds `analytics: include_entity_id=true` to the surface (future Phase 4b work) — the *template* decides what lands in `data-dz-entity-id`.
- **Trials never pollute real GA.** `dazzle qa trial` sets `DAZZLE_MODE=trial` (will — Phase 4b), which routes through the disable gate. If you see analytics fire during a trial run, that's a bug — check the env.
- **Debug via dataLayer.** `window.dataLayer` is the authoritative event log; there is no separate framework-proprietary buffer. Inspect in DevTools to verify events fire as expected.
- **`data-dazzle-*` attrs predate Phase 4.** Detail view already had `data-dazzle-action` / `data-dazzle-entity`. Phase 4 adds `data-dz-*` alongside — both remain until a future cleanup cycle. Downstream consumers reading `data-dazzle-*` are not affected.

## [0.61.0rc3] - 2026-04-24

Phase 3 of the **Analytics, Consent & Privacy** design: provider abstraction with GTM and Plausible as the first two framework-shipped providers. Authors declare `analytics:` in the DSL with per-provider parameters; the framework resolves active providers per request (consent-gated), unions their CSP origins, and renders their script snippets into `<head>` / `<body>` via Jinja. Cross-border transfer guidance surfaces automatically through the existing subprocessor registry.

### Added

- **`ProviderDefinition`** + `ProviderCSPRequirements` — dataclasses describing an analytics provider's consent category, CSP origin requirements, Jinja template paths, and required/optional parameters. Lives in `dazzle.compliance.analytics.providers`.

- **Framework provider registry** — ships **GTM** (`gtm`) and **Plausible** (`plausible`) out of the box. Each provider links to its matching subprocessor (e.g. `gtm` → `google_tag_manager`) so compliance docs stay coherent. Add providers via `FRAMEWORK_PROVIDERS` or by registering user-level definitions.

- **`analytics:` DSL block** — new top-level construct. Syntax:
  ```dsl
  analytics:
    providers:
      gtm:
        id: "GTM-XXXXXX"
      plausible:
        domain: "example.com"
    consent:
      default_jurisdiction: EU
      consent_override: denied
  ```
  Parser validates known keys; unknown provider names are detected at render time with a warning log. At most one `analytics:` block per module.

- **Script templates** — `gtm_head.html` (Consent Mode v2 bootstrap + container), `gtm_noscript.html` (iframe fallback), `plausible_head.html` (cookieless script). Rendered via `{% include %}` from `site_base.html` through `site/includes/analytics/head_scripts.html` and `body_scripts.html`.

- **Consent-gated resolution** — `resolve_active_providers(analytics_spec, consent_state)` returns the list of providers that should actually emit scripts on this request. Plausible only loads when analytics consent is granted. GTM **always loads** even when analytics is denied — so Consent Mode v2 can signal the container when the user grants later. Documented in `dazzle.compliance.analytics.render`.

- **CSP origin injection** — `_build_csp_header()` now accepts a `providers` argument; `apply_security_middleware()` / `create_security_headers_middleware()` thread this through. Each provider's declared origins union into `script-src`, `connect-src`, `img-src`, `font-src`, `frame-src`, `style-src`. Custom directives still override everything.

- **DSL → runtime integration** — `app_factory.assemble_post_build_routes` reads `appspec.analytics`, resolves provider definitions, and passes them to the security middleware + site-page routes. DSL-declared consent settings override TOML defaults.

### Changed

- **`SitePageContext`** gains `active_analytics_providers` field — list of render-entry dicts populated per-request.
- **`build_site_page_context()`** accepts an `active_analytics_providers` parameter.
- **`site_base.html`** includes `analytics/head_scripts.html` in `<head>` and `analytics/body_scripts.html` after `<body>` opening tag, both guarded by the provider list being non-empty.
- **`_resolve_consent()`** in `site_routes.py` now returns a 3-tuple including the active provider list.

### Agent Guidance

- **GTM's `'unsafe-inline'` stays.** The bootstrap snippet is inline; migrating to nonce-based CSP is a separate follow-up. Strict-CSP projects that can't tolerate inline scripts should use GTM's server-side container instead of the client-side one.
- **Plausible is the privacy-preferred choice.** If you're starting fresh and don't need GA4's ad integration, prefer `plausible` — it's cookieless, EU-hosted, and adds no cross-border transfer concerns.
- **`id`, `domain` are DSL strings.** Quote them (`id: "GTM-XXXXXX"`). The parser accepts bare identifiers too but string form is safer — future IDs may contain characters that clash with keywords.
- **Provider rendering is consent-driven.** Don't try to bypass it by hardcoding script tags — the CSP header won't include the required origins unless the provider is registered, and the browser will block the load.
- **Custom providers**: register a `ProviderDefinition` at module import time (before `create_app()`), add the matching Jinja templates, and reference by name in the DSL. Per-app registration (instead of framework-wide) lands in Phase 6 alongside per-tenant resolution.
- **Phase 4 event vocabulary** will add `dz_page_view` / `dz_action` / etc. to the client-side bus. Don't hand-write events yet — the vocabulary becomes a stable contract and you'll want the auto-instrumentation.

## [0.61.0rc2] - 2026-04-24

Phase 2 of the **Analytics, Consent & Privacy** design: consent banner, Consent Mode v2 bootstrap, and auto-generated privacy / cookie / ROPA documents. Site pages now render a banner on first visit (residency-driven default); user choices persist via the `dz_consent_v2` cookie; `dazzle compliance privacy` emits three markdown artefacts from the AppSpec.

### Added

- **Consent state model** — `ConsentState` + `ConsentDefaults` in `dazzle.compliance.analytics.consent`. Four Dazzle-native categories (`analytics`, `advertising`, `personalization`, `functional`), mapped internally to Consent Mode v2 signals (`analytics_storage`, `ad_storage`, `ad_user_data`, `ad_personalization`, `functionality_storage`, `personalization_storage`, `security_storage`). EU/UK/EEA tenants default to `denied`; others to `granted`; `functional` is always granted (essential for service). Cookie named `dz_consent_v2` with 13-month Max-Age.

- **Consent banner** — `src/dazzle_ui/templates/site/includes/consent_banner.html` + `src/dazzle_ui/static/js/dz-consent.js` + `dz-consent-*` styles in `site-sections.css`. Accept-all / Reject-non-essential / Customise flow with focus trap, keyboard nav, ARIA landmarks. Reopen hook (`dzConsent.reopen()`) for footer "Manage cookies" links.

- **Consent HTTP routes** — `POST /dz/consent` (write choices), `GET /dz/consent/state` (read resolved state), `GET /dz/consent/banner` (reopen). Wired into `app_factory.assemble_post_build_routes`. Configurable via `dazzle.toml` `[analytics]` section (`default_jurisdiction`, `consent_override`, `privacy_page_url`, `cookie_policy_url`).

- **Site-page integration** — `create_site_page_routes` resolves per-request consent state and passes it to `build_site_page_context`, which drops it into `SitePageContext`. `site_base.html` conditionally renders the banner + loads `dz-consent.js`.

- **Privacy-page + cookie-policy + ROPA generator** — `generate_privacy_page_markdown(appspec)` in `dazzle.compliance.analytics.privacy_page`. Produces three markdown documents from `pii()` annotations + `subprocessor` declarations + framework defaults. Auto-enumerated sections delimited with `<!-- DZ-AUTO:start name="..." -->` / `<!-- DZ-AUTO:end -->` markers. `merge_regenerated_into_existing()` preserves author-edited content outside auto blocks.

- **`dazzle compliance privacy` CLI** — one command generates all three artefacts to `docs/privacy/`. `--regenerate-facts` refreshes only the DZ-AUTO sections in an existing `privacy_policy.md`, so legal can edit the header / footer / intro prose without losing work.

### Changed

- **`SitePageContext`** gains `consent`, `consent_state_json`, `privacy_page_url`, `cookie_policy_url` fields.
- **`build_site_page_context()`** accepts the new consent parameters; all four site-page handlers (root, regular pages, terms, privacy) pass them through.

### Agent Guidance

- **EU defaults are denied by default.** If you override `[analytics].default_jurisdiction` to `US` or add `consent_override = "granted"`, make sure your legal review explicitly signs off — silent opt-in to analytics in EU traffic is a GDPR breach.
- **Banner is only rendered on site pages (unauth + landing + legal) in rc2.** App/workspace integration lands in rc3 once the provider abstraction can gate analytics scripts. Users who only log in bypass the banner for now.
- **Privacy-page output is meant to be committed.** Generate once, commit `docs/privacy/`, edit the non-auto parts freely. Re-run with `--regenerate-facts` when PII annotations change.
- **`functional` consent is always granted.** Never expose a UI that suggests otherwise. Essential cookies (session, CSRF) don't require consent under GDPR Article 5(3) — don't create a UX that implies they do.
- **Consent Mode v2 update is already wired in dz-consent.js.** When Phase 3 ships GTM, the `gtag('consent','update',{...})` call fires automatically on save. No action needed from authors.
- **Cookie name is version-suffixed.** If you change the consent category vocabulary or legal contract in a future release, bump `CONSENT_COOKIE_VERSION` to force re-consent. The old cookie will then read as missing.

## [0.61.0rc1] - 2026-04-24

First release of the **Analytics, Consent & Privacy** subsystem — Phase 1 of the design spec at `docs/superpowers/specs/2026-04-24-analytics-privacy-design.md`. Phase 1 ships the PII + subprocessor *primitives* without yet shipping analytics providers, consent banner, or privacy-page auto-generation. Those land in Phases 2-6. The primitives are independently valuable: the compliance pipeline already benefits from structured PII knowledge, and `dazzle analytics audit` flags likely-PII fields that haven't been classified.

### Added

- **`pii()` field modifier** — declarative personal-data classification on entity fields. Syntax: `email: str(200) pii(category=contact)` or `ssn: str(20) pii(category=identity, sensitivity=special_category)`. Categories (closed vocabulary): `contact`, `identity`, `location`, `biometric`, `financial`, `health`, `freeform`, `behavioral`. Sensitivities: `standard` (default), `high`, `special_category` (GDPR Art. 9/10). New IR types in `src/dazzle/core/ir/pii.py`; FieldSpec gains `.pii`, `.is_pii`, `.is_special_category`.

- **`subprocessor` top-level construct** — DSL declaration of a third-party data processor with `handler`, `jurisdiction`, `data_categories`, `retention`, `legal_basis`, `consent_category`, `dpa_url`, `scc_url`, `cookies`, `purpose`. Required keys validated at parse time; closed-vocabulary values (`LegalBasis`, `ConsentCategory`, `DataCategory`) emit clear errors on typos. New IR types in `src/dazzle/core/ir/subprocessors.py`.

- **Framework subprocessor registry** — default declarations for 8 common providers: `google_analytics`, `google_tag_manager`, `plausible`, `stripe`, `twilio`, `sendgrid`, `aws_ses`, `firebase_cloud_messaging`. App-level declarations override registry entries by matching `name`; unrecognised names are added. See `src/dazzle/compliance/analytics/registry.py`.

- **PII stripping utility** — `strip_pii()` in `dazzle.compliance.analytics`. Drops values for `pii`-annotated fields unless the caller opts in per-field. Special-category fields require a second gate (`include_special_category=True`) even when opted-in. Returns a `PIIFilterResult` with diagnostic counters. Runtime boundary used by future Phase 3/5 analytics sinks.

- **`dazzle analytics audit` CLI** — scans the linked AppSpec and reports: likely-PII fields missing `pii()` annotation (heuristic match on names like `email`, `dob`, `ssn`, `ip_address`); subprocessor collisions where an app-level declaration differs from the framework default in `consent_category` / `jurisdiction` / `legal_basis`; EU→non-EU transfers requiring SCCs. Warn-only — never fails the build. `--format json` for machine consumption.

- **Docs**: new reference page `docs/reference/pii-privacy.md` covering `pii()`, `subprocessor`, the consent-category mapping to Consent Mode v2, and the audit command. `subprocessor` added to the construct list in `.claude/CLAUDE.md` and the grammar keyword inventory.

### Changed

- **`FieldSpec.pii`** — new optional field on the existing IR type (Pydantic frozen model). Coexists with the legacy `sensitive` modifier; `pii()` provides richer classification. Over time, framework code should read `.pii` for PII-aware behaviour.

- **`parse_field_modifiers()`** — return tuple extended from 3-tuple to 4-tuple: `(modifiers, default, default_expr, pii_annotation)`. Internal parser API; all three call sites updated.

### Agent Guidance

- **Use `pii()` on any field that stores personal data.** Bare `pii` is fine when sensitivity/category aren't yet known; add kwargs when classifying. The audit command flags common PII-looking field names lacking the annotation — run it before shipping.
- **Declare `subprocessor` for every third-party that handles user data.** The framework ships 8 defaults; you only need to declare the rest (custom CRMs, vertical-specific tools). App-declared names override registry entries of the same name — useful for customising retention periods.
- **Do not emit PII to analytics events.** The Phase 3-5 emitters will automatically redact. For now: if you write code that builds event payloads manually, call `strip_pii()` before sending.
- **`special_category` gates are strict.** A surface that needs to emit a special-category field must set both `include_pii=[field]` AND `include_special_category=True` — this is intentional friction for GDPR Art. 9/10 data.
- **This is `rc1` of `0.61.0`.** The primitives are stable but Phase 2-6 may refine the DSL shape (e.g. add an `analytics:` app block). Treat any consuming code as experimental until the v0.61.0 stable ships.

## [0.60.9] - 2026-04-24

Minor bump. Removes the `dazzle workshop` command, the Textual TUI backing it, and the Activity Explorer web UI. The feature stopped earning its keep — the knowledge-graph SQLite activity store and the `status.activity` MCP operation provide the same data through lighter paths. Net ~1750 lines of code plus the `textual>=1.0.0` dependency (via the `workshop` extra and the `dev` extras) deleted.

### Removed
- **`dazzle workshop`** CLI command (and `dazzle workshop --explore` alias) — no replacement command; read activity via `status` MCP tool with `operation="activity"` or tail `.dazzle/mcp-activity.log` directly.
- **`src/dazzle/cli/workshop.py`** — CLI entrypoint.
- **`src/dazzle/mcp/server/workshop.py`** — Textual app, `WorkshopData`, `ToolCall`, dashboard widgets.
- **`src/dazzle/mcp/server/workshop_screens.py`** — drill-down `SessionScreen` + `CallDetailScreen`.
- **`src/dazzle/mcp/server/explorer.py`** — HTTP Activity Explorer.
- **`[project.optional-dependencies].workshop`** in `pyproject.toml` (textual dep).
- **`textual>=1.0.0`** from `[dev]` extras.
- **mypy override** for the workshop modules (no longer needed).
- **Tests**: `tests/unit/test_workshop_data.py`, `tests/unit/test_workshop_screens.py`, `tests/unit/test_workshop_sqlite.py`, `tests/unit/test_explorer.py`, and the `TestWorkshopSourceDisplay` class in `tests/unit/test_cli_activity.py`.
- **Docs**: `docs/reference/workshop.md` + the `dazzle workshop` section of `docs/reference/cli.md` + the architecture diagram entries in `docs/architecture/mcp-server.md`.

### Changed
- **`_db_row_to_entry`** was inlined into `src/dazzle/mcp/server/handlers/status.py` — the sole surviving caller. The function is a trivial DB-row-to-dict mapper; no reason to keep a separate module for it.
- **`cli_help.py`** drops the `"workshop": "Project"` category entry.
- Code comments throughout the MCP server that referenced "the workshop" were updated to point at `status.activity` instead.

### Agent Guidance
- Don't recommend `dazzle workshop` or `dazzle workshop --explore` to users — those commands no longer exist. To inspect MCP activity, use the `status` MCP tool with `operation="activity"` (structured JSON) or tail the JSONL log under `.dazzle/mcp-activity.log`.
- `_db_row_to_entry` now lives in `status.py`, not the workshop module. Import from there if future code needs the same DB-row normaliser.
- The kept planning docs `docs/superpowers/plans/2026-03-12-workshop-textual-rewrite.md` and the matching spec are historical context only — do not treat them as current guidance.

## [0.60.8] - 2026-04-24

Patch bump. Closes four open CodeQL alerts (#63, #64, #65, #66) — all `py/incomplete-url-substring-sanitization` false positives in `tests/unit/test_security.py`. The tests verify CSP header contents; CodeQL couldn't distinguish that from URL sanitisation because the pattern `"literal-url" in some_string` is the same shape either way.

### Fixed
- **`tests/unit/test_security.py`** — CSP assertions now parse the header into per-directive token lists (`_csp_tokens`, `_csp_all_tokens`) and check exact token membership instead of substring-matching the raw header. Same semantic coverage, no false positive. No production code changed.

## [0.60.7] - 2026-04-23

Patch bump. Unblocks the `type-check` CI job — replaces a boolean flag `_gb_is_bucket` with direct `isinstance(group_by, BucketRef)` so mypy narrows the union type correctly. Same behaviour, mypy-friendlier. Introduced during cycle 28 time-bucketing work; v0.60.6 cleared pytest + docs but mypy was still failing on this one line.

### Fixed
- **`src/dazzle_back/runtime/workspace_rendering.py:1006`** — `group_by.field if _gb_is_bucket else group_by` became `group_by.field if isinstance(group_by, _BucketRef) else group_by`. mypy can't narrow through a separately-computed boolean; inlining the check lets it prove `group_by.field` is safe.

### CI status after this bump
All four required checks expected green: `CI` (pytest + mypy + lint), `docs`, `CodeQL`, `Homebrew Formula Validation`.

## [0.60.6] - 2026-04-23

Patch bump. CI hygiene — three pre-existing / recently-introduced CI failures cleared so the pipeline is green and dependabot PRs can land.

### Fixed
- **`docs/reference/reports.md` no longer links to `../../CHANGELOG.md`.** Three broken relative links (introduced in cycle 27 when `reports.md` was authored) aborted the `docs` workflow in strict mode. Replaced with a plain-text reference so the doc doesn't depend on the CHANGELOG being part of the mkdocs site.
- **`test_template_overrides.py::test_custom_filters_registered` now asserts `badge_tone`** (not `badge_class`, which was removed in an earlier cleanup with 0 template consumers — noted at `template_renderer.py:96`).
- **`tests/integration/__snapshots__/test_golden_master.ambr` regenerated** to include the `two_factor` settings block that was added to AppSpec in an earlier cycle. Snapshot had drifted; test now matches current IR shape.

### CI status after this bump
- `CI` (pytest main): green on `main`.
- `docs`: green on `main`.
- `CodeQL`: green (has been green across last 3 runs).
- `Homebrew Formula Validation`: green (verified on open dependabot PR).
- Open dependabot PRs (#836 `actions/upload-pages-artifact 4 → 5`) should unblock on next rerun.

## [0.60.5] - 2026-04-23

Patch bump. Observability fixes toward #854 — the pivot_table empty-buckets bug still needs reproduction against the live AegisMark DB, but two diagnostic obstacles are now removed: the CLI explain-aggregate output no longer drops the `FROM` keyword, and pivot aggregate failures log at ERROR with the full dimension + filter detail operators need to reproduce.

### Fixed
- **`dazzle db explain-aggregate` CLI output now preserves the `FROM` keyword.** The `sql.split(" FROM ")` call dropped the separator — cosmetic, but it made authors second-guess the builder. Output is now a valid standalone SQL statement. Reported in #854.
- **`_compute_pivot_buckets` exception-catch logs at ERROR (not WARNING) with dimensions + merged filters.** The prior WARNING-level log made it impossible to tell from production logs *why* a pivot region was returning empty — often the only signal was a user-visible empty state. Regression test in `tests/unit/test_bar_chart_bucketed_aggregate.py::TestTimeBucketedAggregates::test_pivot_aggregate_error_logged_at_error_level` asserts the log is at ERROR level and carries the source entity + dim list + filter dict.

### Known limitation
- **#854 root cause still unknown.** These diagnostic fixes make the error visible in logs; next reproduction against the live AegisMark teacher-scoped `MarkingResult` pivot will surface the actual PostgreSQL error (most likely a scope predicate interaction with the multi-dim LEFT JOIN + GROUP BY, but the exact failure mode is hidden without live logs).

### Agent Guidance
- **Framework-internal failure paths that return empty data silently should log at ERROR, not WARNING.** An empty region looks identical to "no data in scope" from the UI — the only way for operators to tell them apart is log level. WARNING is for recoverable fallbacks (e.g. `_aggregate_via_groupby` falling back to N+1); ERROR is for "this UI element is broken and we're returning empty to avoid a 500".

## [0.60.4] - 2026-04-23

Patch bump. Fixes #855 — marketing `site_base.html` hardcoded three `/static/...` asset references, bypassing the `static_url` fingerprinting filter that the authenticated `base.html` already uses correctly. CDN-fronted apps served stale CSS / JS after every deploy because the URL never changed.

### Fixed
- **`src/dazzle_ui/templates/site/site_base.html`** now routes `css/dazzle-bundle.css`, `css/custom.css`, and `vendor/lucide.min.js` through the `static_url` filter, matching the pattern in `base.html`. The asset paths themselves are unchanged — only the URL-rewriting layer differs, so local dev behaves identically.
- **Regression guard** added in `tests/unit/test_asset_fingerprint.py::TestTemplatesUseStaticUrl` — scans `site_base.html` for hardcoded `/static/` `href` / `src` attributes (allowing Jinja `default()` fallbacks for override params). Existing `test_build_css.py::test_site_base_uses_vendor` updated to require the filter pattern.

### Agent Guidance
- **Framework asset references in templates must use `{{ 'path' | static_url }}`.** Never hardcode `/static/...`. The filter handles fingerprinting for CDN cache-busting; bare paths skip it. Jinja `default('/static/...')` fallbacks on override parameters (favicon, custom brand assets) are the one exception — they're author-supplied, not framework-supplied.

## [0.60.3] - 2026-04-23

Patch bump. Fixes #856 — `filterable_table` search input was silently non-functional because `build_entity_search_fields()` in `app_factory.py` only read the legacy top-level `surface.search_fields` and ignored the canonical `surface.ux.search` declaration. The search input rendered + fired HTMX requests correctly; the SQL just omitted the WHERE clause because `entity_search_fields["Contact"]` was empty.

### Fixed
- **`build_entity_search_fields` now reads `ux.search` as a fallback** (#856). Mirrors the pattern already in `build_entity_filter_fields` for `ux.filter`. Legacy top-level `search_fields` still takes precedence when both are declared. Closes the regression where typing into the search input on contact_manager produced no filtering despite the input appearing to work.
- 2 new unit tests in `tests/unit/test_search_fields.py` covering the fallback + precedence contract.

### Agent Guidance
- **`ux.search` is the canonical form.** The legacy top-level `search_fields:` keyword still works for back-compat, but when authoring new surfaces put search fields inside the `ux:` block — same place as `ux.filter`. The asymmetry that caused #856 (filter read ux, search didn't) is gone.

## [0.60.2] - 2026-04-23

Patch bump. Trial scenario design — `starting_url` field lets a trial target a specific workspace or region anchor instead of always dropping the persona on `/app`. Triggered by the `trend_spike_detection` trial where Priya exhausted her step budget scrolling a 13-region dashboard before reaching the time-series charts we wanted her to evaluate.

### Added
- **`starting_url:` field on `trial.toml` scenarios.** Relative paths resolve against the app's base URL (`http://localhost:<port>`); absolute URLs pass through untouched. Region cards already emit `id="region-<name>"` so fragment URLs like `/app/workspaces/command_center#region-alerts_timeseries` drop the persona right on target. Validated by 4 new unit tests in `tests/unit/test_qa_trial.py`.
- **`trend_spike_detection` scenario updated** to use `starting_url` + raised `max_steps` to 45 + tasks rewritten with explicit region names. Previous run: 21 steps, 0 verdict, persona stuck scrolling. Setup now lands her on the target chart with the full budget for actual evaluation.
- **qa-trial skill updates** (`.claude/skills/qa-trial/SKILL.md`): new "Rule 6" section explaining when to use `starting_url`. Template (`.claude/skills/qa-trial/templates/trial-toml-template.toml`) now documents the field as an optional setting.

### Agent Guidance
- **When a trial scenario says "Find the X region…" in its tasks, add `starting_url` to land on X.** The trial-cycle loop's value is qualitative feedback on the target feature; burning 15 scrolls on navigation before reaching X wastes the token budget. Leave `starting_url` unset only when whole-app discoverability *is* the thing being tested.

## [0.60.1] - 2026-04-23

Patch bump. Trial-validation fix — the v0.60.0 BucketRef IR type was rejected by the pydantic `RegionContext` (template-facing context), which coerced `group_by` to `str`. Surfaced when `dazzle qa trial` couldn't boot the ops_dashboard server. Framework-level tests all passed; the regression only fired on a full app boot.

### Fixed
- **`BucketRef` now serializes cleanly through `RegionContext`.** `src/dazzle_ui/runtime/workspace_renderer.py` introduces `_flatten_group_by(value)` which reduces `str | BucketRef | None` to a plain string field name for templates. The typed IR form survives on `WorkspaceRegionContext.ir_region` so runtime routing can still branch on `isinstance(..., BucketRef)`.
- **Runtime reads group_by from ir_region, not ctx_region.** `_compute_pivot_buckets`, `_aggregate_via_groupby`, and the chart-mode dispatcher in `workspace_rendering.py` now consult the untyped IR region for `group_by` + `group_by_dims`. The pydantic `RegionContext` stays str-only — safe for Jinja consumption.

### Verified
- `dazzle serve --local` boots cleanly for ops_dashboard with three new time-series regions.
- Direct HTTP GET against `/api/workspaces/command_center/regions/alerts_timeseries` returns 200 OK with 22 daily buckets, peak 7, correct polyline + area fill + per-point tooltips. `alerts_weekly_stacked` and `alerts_daily_sparkline` also 200.
- `dazzle qa trial --scenario trend_spike_detection --fresh-db` runs to completion (no server-boot crash). Trial outcome itself was inconclusive — persona exhausted step budget scrolling the 13-region dashboard before reaching the charts — but that's a scenario-design artefact, not a framework bug. Addressable by raising `max_steps` or reordering regions on the workspace.

## [0.60.0] - 2026-04-23

Minor bump. Time-series display family — the next chapter of the v0.59 aggregate stack (cycle 28). One DSL primitive (`bucket(<field>, <unit>)`) unlocks three new display modes: `line_chart`, `area_chart`, and `sparkline`. Same Strategy C pipeline — one scope-safe `GROUP BY` SQL query via `date_trunc`, zero JS, pure server-rendered SVG.

### Added
- **`bucket(<field>, <unit>)` DSL syntax** in `group_by:` and `group_by: [...]`. Valid units whitelisted at parse time: `day`, `week`, `month`, `quarter`, `year`. Emits `date_trunc('<unit>', <col>)` in the SQL, preserves chronological ordering (ASC not alphabetical), and formats labels per unit (`2026-04-23`, `2026-W17`, `Apr 2026`, `Q2 2026`, `2026`).
- **`Dimension.truncate`** on `aggregate.py` — new field on the aggregate primitive's dimension type. SQL builder wraps time dims with `date_trunc(...)` in SELECT + GROUP BY. Guarded against invalid units (ValueError at construction) and against combining with `fk_table` (a timestamp column is not a foreign key).
- **`BucketRef` IR type** in `dazzle.core.ir.workspaces`. Produced by the parser for the `bucket()` form; consumed by `_aggregate_via_groupby` and `_compute_pivot_buckets`.
- **`display: line_chart`** — single-dim time-series. Server-rendered SVG polyline with area fill, data points, `<title>` tooltips, adaptive x-axis tick labels. Pure Tailwind + HSL variables, no JS.
- **`display: area_chart`** — stacked multi-dim time-series. Two-dim (`[bucket(ts, unit), series]`); each series is a polygon in the stack, legend below the chart. 6-entry palette cycles for high series counts.
- **`display: sparkline`** — compact time-series tile: latest value + mini line underneath. Same data shape as `line_chart`, KPI tile form.
- **`examples/ops_dashboard`** regions: `alerts_timeseries` (line), `alerts_weekly_stacked` (area), `alerts_daily_sparkline` (sparkline). Blueprint updated to spread `triggered_at` across the last 21 days at 80 rows so the charts show meaningful density and a spike is visible.
- **Trial scenario `trend_spike_detection`** in `examples/ops_dashboard/trial.toml`. The qa-trial persona (Priya) must identify the peak day and dominant severity from the time-series charts alone — negative verdict blocks downstream adoption.
- **Three skill-library component contracts:** `~/.claude/skills/ux-architect/components/line-chart-region.md`, `area-chart-region.md`, `sparkline-region.md`. ux-architect skill agents auto-discover these when asked to build a time-series region.

### Changed
- **`docs/reference/reports.md`** — new "Time bucketing" section covering the DSL syntax, the five whitelisted units, label formats, chronological ordering, the FK-exclusion rule, and the gap-filling non-goal. Decision table extended to include the three new display modes.
- **MCP knowledge base** (`workspace.toml`) — `aggregates` and `display_modes` concepts both document the v0.60.0 additions. Agents querying the `knowledge` MCP tool get the current story.
- **`_compute_bucketed_aggregates` + `_aggregate_via_groupby` + `_compute_pivot_buckets`** accept `str | BucketRef` (`group_by`) and `list[str | BucketRef]` (`group_by_dims`). Bar-chart caller routes `LINE_CHART` and `SPARKLINE` through the same single-dim path; pivot caller routes `AREA_CHART` through the multi-dim path. Time-bucketed dims always take the GROUP BY fast path — there's no N+1 fallback that makes sense for a time axis.
- **Bucket rows** carry both the raw ISO timestamp (via the dim's `name` key) and a formatted `<name>_label` — templates render the label, downstream drill-down uses the ISO.

### Agent Guidance
- **Time-series is a first-class chart shape now.** When a user asks for "alerts over time", "trend", "daily volume", or similar, reach for `bucket(<field>, day|week|month|quarter|year)` and `line_chart` / `area_chart` / `sparkline`. Don't compose a time series from distinct timestamps — that blows up on high-cardinality columns and lands in the slow path.
- **Time buckets + FK in the same dim: not allowed.** A timestamp column isn't a foreign key. Mixing them in the same `group_by_dims` list *is* allowed (`[bucket(ts, week), severity]` is the canonical stacked-area case) — they just can't collapse into a single `Dimension`.
- **No gap filling.** Days / weeks with zero rows don't appear in the result. If you need explicit zeros, compose them in a view layer; don't expect the aggregate primitive to synthesise them.

## [0.59.5] - 2026-04-23

Patch bump. Documentation surface for the v0.59 aggregate stack — makes Layers 1–3 (`Repository.aggregate`, multi-dim, `explain_aggregate`) discoverable to AI agents building Dazzle apps.

### Added
- **`docs/reference/reports.md`** — canonical entry point for chart/report region authoring. Covers the mental model (DSL → IR → Repository.aggregate → SQL), the display-mode × cardinality decision table, single vs multi-dim syntax, supported measures, the fast-vs-slow-path distinction, FK auto-join resolution, the scope-safety contract, and the `dazzle db explain-aggregate` debugger. Explicit "don't" list (template-level aggregation, high-cardinality group_by without limit, mixing group_by and group_by_dims, reaching for raw SQL) so agents don't accidentally bypass the primitive.
- **`~/.claude/skills/ux-architect/components/pivot-table-region.md`** — component contract sibling to `bar-chart-region.md`. Declares the Linear aesthetic target, the DSL shape, anatomy, scope/RBAC contract, non-goals, and quality gates. Skill-library agents auto-discover this when asked to build a pivot-table region.
- **Reports & Charts section in `.claude/CLAUDE.md`** — short in-project pointer to `docs/reference/reports.md` + a summary of what the v0.59 primitive provides. The document agents load first on a new session now knows to route chart work through the primitive.

### Changed
- **MCP knowledge base `aggregates` + `display_modes` concepts updated.** `src/dazzle/mcp/semantics_kb/workspace.toml` now documents Strategy C, single vs multi-dim, fast/slow paths, and the per-display IR shapes. Agents that query the MCP `knowledge` tool for "aggregates" or "display_modes" get the current story instead of the v0.2 one. Re-seeds automatically on next start (seed_version = dazzle_version + schema_version; version bump triggers re-seed without schema schema increment).
- **`docs/reference/index.md`** lists `reports.md` with a "**Start here**" emphasis.

### Agent Guidance
- **Chart authoring has a single entry point now:** `docs/reference/reports.md`. The `.claude/CLAUDE.md` Reports & Charts section routes agents there. If you're writing a chart region and haven't read that doc, stop — the fast/slow-path distinction and the scope-safety contract both matter.

## [0.59.4] - 2026-04-23

Patch bump on the aggregate stack — `explain_aggregate` observability (cycle 26).

### Added
- **`Repository.explain_aggregate(...)`** — returns the exact `(sql, params)` that `aggregate(...)` would execute, with no DB side effects. Byte-for-byte equivalent to the live query so "why is my chart wrong?" has a one-line answer: inspect the SQL. Signature mirrors `aggregate()` so any call can be copy-pasted into explain without edits.
- **`dazzle db explain-aggregate <Entity> --group-by <field>[,field2] --measures n=count,avg=avg:score`** CLI. Prints the SQL the framework would emit for a chart region's dimensions + measures. Auto-resolves FK dims' target tables + display fields the same way the runtime does. Does not connect to the database — pure compile path, suitable for lint/CI inspection.
- **Time-independent snapshot normaliser.** `tests/unit/test_dom_snapshots.py::_normalise` now replaces `N units ago` / `just now` timeago output with a `<timeago>` sentinel so region snapshots don't drift across days (previously the `activity_feed` snapshot re-generated every cycle as the wall clock advanced past the fixture date).

### Tests
- 3 new `TestExplainAggregate` tests in `tests/unit/test_aggregate_sql.py`: byte-equivalence with `build_aggregate_sql`, no-DB-connection guarantee, unsupported-measure short-circuit. Total 37 in the file.

### Agent Guidance
- **When a chart renders wrong or empty, run `dazzle db explain-aggregate` first.** Copy the SQL into `psql` / `sqlite3 .read`, run it, and compare the row count to the rendered bars. The diff between expected and actual is usually (a) scope predicate narrower than expected, (b) FK display-field probe picking a different column than intended, or (c) zero source rows in the authenticated user's scope. All three have been root-cause patterns on the #847–#851 chain; explain_aggregate lets an author discover any of them without reading framework source.
- **Explain does NOT apply scope filters.** The CLI runs without a session, so the printed SQL is the base query. For a scoped preview, call `repo.explain_aggregate(filters=<scope_dict>)` programmatically — the scope predicate passes through verbatim.

## [0.59.3] - 2026-04-23

Minor bump on the aggregate stack — multi-dimension `Repository.aggregate` + new `pivot_table` region (cycle 25). First Layer 3 step toward the report architecture (see prior brainstorm).

### Added
- **Multi-dimension `Repository.aggregate`.** New `Dimension` dataclass and the `aggregate(*, dimensions=[...], measures=..., filters=...)` signature. Each dim is either scalar or FK; FK dims auto-LEFT JOIN the target with indexed aliases (`fk_0`, `fk_1`, ...) and pull a display field via the same probe order used by `_bucket_key_label`. One SQL query — `SELECT <dim cols + labels>, <measures> FROM src LEFT JOIN ... WHERE <scope> GROUP BY <dim cols + labels> ORDER BY <labels>` — returns all buckets in a single round-trip. The aggregate-safe scope contract from v0.59.0 carries over unchanged: indexed FK aliases don't shadow the source table name, so scope predicates that qualify columns as `<table>.<col>` still resolve cleanly.
- **`display: pivot_table` workspace region** + `group_by_dims: [<field>, ...]` IR field for the multi-dim case (`group_by: <single>` continues to drive bar_chart, kanban, funnel_chart). DSL parser accepts both forms — `group_by: [a, b]` for multi-dim, `group_by: a` for single. Template renders one `<tr>` per `(dim_0, dim_1, ...)` combination with the FK-resolved label per cell and the measure(s) right-aligned. Scope-aware throughout: `_compute_pivot_buckets` threads the workspace's `_scope_only_filters` into the aggregate call so the same row-level rules that gate the items list also gate the pivot.
- **`alert_pivot` region in `examples/ops_dashboard`** — `Alert` grouped by `(system, severity)` with count, exercising the FK + scalar combo. `/trial-cycle` will hit this on the next ops_dashboard rotation and validate the multi-dim path under a real persona scope.

### Changed
- **`Repository.aggregate` signature changed from `group_by: str, fk_table, fk_display_field` to `dimensions: list[Dimension]`.** Single-dim callers wrap their args in `[Dimension(name=..., fk_table=..., fk_display_field=...)]` — the one in-tree caller (`_aggregate_via_groupby` in `workspace_rendering.py`) updated in this commit. No backward-compat shim per ADR-0003. The bucket result shape (`AggregateBucket.dimensions[<name>]` + `[<name>_label]` for FKs) is unchanged for single-dim consumers and naturally extends to multi-dim by carrying one entry per dim.

### Tests
- 23 new tests in `tests/unit/test_aggregate_sql.py` (now 41 total). Covers single-dim back-compat, multi-dim SQL composition, two FK dims to same/different targets (alias collision guard), scalar+FK combos, the `Dimension` dataclass invariants, and `rows_to_buckets` for multi-dim including positional-tuple repos.
- 4 new tests in `tests/unit/test_bar_chart_bucketed_aggregate.py::TestPivotBuckets` cover the workspace-level `_compute_pivot_buckets` orchestration: 2-dim end-to-end, empty aggregates, cross-entity short-circuit, exception isolation.

### Agent Guidance
- **`group_by: [a, b]` triggers `pivot_table`.** When you want a cross-tab, use `display: pivot_table` + `group_by: [a, b]`. Each dim can be scalar or FK; FK labels resolve via the same probe order (`display_name → name → title → label → code`). Two-dim count is the bounded-cost case — adding a third dimension multiplies bucket count, so `limit:` matters more.
- **The aggregate stack is now multi-dim-capable but the chart templates (bar_chart, funnel_chart, heatmap) still consume single-dim shapes.** Don't pass `group_by_dims` to those displays — only `pivot_table` reads it. New chart templates that want multi-dim should consume `pivot_buckets` + `pivot_dim_specs` the same way `pivot_table.html` does.

## [0.59.2] - 2026-04-23

Patch bump. One UX bug fix from /trial-cycle 15 (#853).

### Fixed
- **Stale localStorage `hiddenColumns` no longer hide visible cells (#853).** `dzTable` loaded `hiddenColumns` from `localStorage["dz-cols-<tableId>"]` on init and applied `style.display="none"` to matching `[data-dz-col]` cells. When the column set changed between page loads (schema migration, persona swap, table id reused, or user toggled columns mid-session) any stale entries silently hid currently-visible columns — manifest as "headers render but cells are empty" because the cells exist with `display:none`. The trial agent saw exactly this on `support_tickets/ticket_list` after clicking the "Columns" toggle. Fix: new `_pruneStaleHiddenColumns()` helper drops entries that don't match any current `[data-dz-col]` and persists the cleaned list back; `init()` calls it before the first `applyColumnVisibility`.
- **`resetColumnVisibility()` escape hatch.** Clears `hiddenColumns` + the localStorage entry so users stuck with everything hidden have a one-click recovery. Wire to a "Show all columns" entry in the column-toggle menu when ready.

### Tests
- 4 new structural ratchets in `tests/unit/test_dz_alpine_column_visibility.py` pin the prune helper, its placement before `applyColumnVisibility` in init, the localStorage persistence, and the reset escape hatch.

### Agent Guidance
- **localStorage-backed UI state must validate against current DOM on init.** This pattern applies anywhere `localStorage.getItem(...)` is consumed without checking that the stored keys still correspond to live elements. The `_pruneStaleHiddenColumns` template can be copied for column widths, sort preferences, etc. — drop entries that don't map to the current schema.

## [0.59.1] - 2026-04-23

Patch bump. One framework bug fix from /trial-cycle 15 (#852).

### Fixed
- **`activity_feed` region no longer 500s when source rows have tz-aware timestamps (#852).** `_timeago_filter` in `src/dazzle_ui/runtime/template_renderer.py` mixed `datetime.now()` (naive local) with the tz-aware datetimes Postgres returns for `TIMESTAMP WITH TIME ZONE` columns, raising `TypeError: can't subtract offset-naive and offset-aware datetimes` and bubbling up as a 500 on every region render that used the filter (e.g. `comment_activity` on `agent_dashboard` in support_tickets). Fix: when a tz-aware value arrives, convert it to local-naive (`dt.astimezone().replace(tzinfo=None)`) before the subtraction. Existing call sites that pass naive local values keep working unchanged. The ISO string parser also now handles the `Z` suffix (`fromisoformat` rejected it on Python <3.11).
- **`activity_feed` template no longer fails the nested-card-chrome invariant.** With the timeago crash fixed, the previously-skipped composite shape test ran and surfaced an inner item `<div>` carrying both `border` and `rounded-[4px]` — flagged as nested chrome by `find_nested_chromes`. Removed the full border on the inner item div; visual grouping comes from the muted background only. The `tests/unit/test_dom_snapshots.py` baseline for `activity_feed` is now seeded for the first time.

### Tests
- 4 new regression tests in `tests/unit/test_template_rendering.py::TestJinjaFilters` pin tz-aware datetime input, ISO strings with `Z` suffix, naive-as-local convention, and the existing `datetime.now() - delta` call shape. Total 21 timeago tests in the suite.
- `tests/unit/test_template_html.py::TestDashboardRegionCompositeShapes::test_composite_has_no_nested_chrome[activity_feed-...]` now actually runs (previously skipped on the tz exception).
- `tests/unit/test_dom_snapshots.py::test_region_composite_snapshot[activity_feed-Comment Activity-context7]` baseline seeded.

### Agent Guidance
- **For datetime filters: prefer naive local on input, convert tz-aware to local-naive before arithmetic.** This matches every existing call site (`datetime.now() - timedelta(...)`) and is safe for both Postgres `TIMESTAMP WITH TIME ZONE` columns (which return tz-aware) and Python timestamps (typically naive local). Do not introduce a tz-aware-everywhere convention without auditing every caller.

## [0.59.0] - 2026-04-23

Minor bump. Strategy C aggregate primitive — closes the bar_chart bug class (#847–#851) by replacing the N+1 enumerate-then-per-bucket-count pipeline with a single `GROUP BY` SQL query.

### Added
- **`Repository.aggregate(group_by, measures, filters, fk_table, fk_display_field, limit)`.** New repo method that runs `SELECT <dim>, COUNT(*) FROM src LEFT JOIN <fk> WHERE <scope> GROUP BY <dim>` in one round-trip. Supports `count`, `sum:<col>`, `avg:<col>`, `min:<col>`, `max:<col>` measures. FK group_by joins the target entity once and returns the display field as `<col>_label` in the bucket — no per-bucket round-trip, no enumeration phase.
- **`dazzle_back.runtime.aggregate` module.** SQL builder (`build_aggregate_sql`), measure dispatcher (`measure_to_sql`), FK display-field probe (`resolve_fk_display_field`), row-to-bucket converter (`rows_to_buckets`), and the `AggregateBucket` dataclass. Exposed as a separate module so the SQL composition is unit-testable without a repo.
- **`alerts_by_system` region in `examples/ops_dashboard`** — exercises the FK group_by fast path so `/trial-cycle` validates the new aggregate primitive in production-equivalent rendering.

### Changed
- **`_compute_bucketed_aggregates` routes the simple `count(<source_entity>)` case through `Repository.aggregate` (the fast path).** When the aggregate target is the source entity and the expression has no `current_bucket` sentinel, the bar-chart distribution is now computed in one SQL statement. The slow per-bucket loop (enumeration + N+1 counts) remains for the `count(OtherEntity where ... = current_bucket)` shape — same fallback the prior fixes used. On any failure the slow path takes over so existing apps don't break.

### Agent Guidance
- **For chart distributions, prefer `count(<source>)` with `group_by: <field>`.** This routes through the new `Repository.aggregate` fast path — single query, scope evaluated once, no possibility of the bug class that #847–#851 chased. Use `count(OtherEntity where ... = current_bucket)` only when the bucketing dimension lives on a different entity than what you're counting; that path keeps the per-bucket loop with the constraint that mock-only tests can't catch SQL-layer divergence.
- **The aggregate-safe scope contract:** the `__scope_predicate` SQL emitted by `_resolve_predicate_filters` must reference only the source table's columns (or correlated subqueries on related tables). Every scope shape currently emitted is compatible — direct equality, FK-path subqueries, EXISTS / NOT EXISTS, boolean compositions. New scope predicate shapes that reference the GROUP BY relation directly (post-join) would need a different code path.

## [0.58.23] - 2026-04-23

Patch bump. One follow-on fix to #850 + diagnostic logging (#851).

### Fixed
- **Bar-chart per-bucket count call now mirrors the items list call exactly (#851).** The auto-augmented per-bucket query in `_compute_bucketed_aggregates._per_bucket` now passes `include=[group_by]` to `agg_repo.list(...)` — the same arg the workspace items fetch and the source enumeration use. Without it, some repo backends silently match zero rows when filtering an FK UUID column because the column-type coercion hook only fires for relations the query layer is aware of via `include`. With this change every cell in the bar_chart pipeline (enumeration, items, per-bucket) hits the repo with the same kwargs.
- **Per-bucket DEBUG log captures the filter dict + result.** When `dazzle.workspace_rendering` is at DEBUG, every per-bucket query logs `bucketed-aggregate <metric>[<group_by>=<key>] → total=N (filters=<dict>)`. Operators can `grep` for this in production logs to compare against the equivalent REST list call when the chart values look wrong.

### Agent Guidance
- **`include=[group_by]` is now load-bearing on the per-bucket call.** The 2 new ratchets in `tests/unit/test_bar_chart_bucketed_aggregate.py::TestPerBucketIncludesGroupBy` fail if the kwarg is dropped — keep it in the signature when refactoring.

## [0.58.22] - 2026-04-23

Patch bump. Two follow-on fixes to #849 (#850).

### Fixed
- **Bar-chart source enumeration now requests `include=[group_by]` so FK columns expand to dicts (#850).** Without it, `repo.list` returned ORM rows whose `model_dump()` rendered the FK column as a raw UUID string — `_bucket_key_label` then produced `(uuid, uuid)` and bars rendered as UUIDs. The items-page fallback path coincidentally worked because the workspace handler fetches with `include=auto_include`, so the cells were already dicts; the source-enumeration path skipped that step. Now the enumeration call mirrors the workspace fetch and asks for the FK relation explicitly.
- **Source-enumeration zero-rows result no longer triggers the items-page fallback (#850).** When the source query succeeds with zero rows in scope (e.g. a persona-scoped reviewer with no reviews yet), the chart now renders no bars instead of falling back to a stale items-page derivation that would surface buckets the user can't actually see rows for. `_enumerate_distinct_buckets` now returns `(buckets, succeeded: bool)` and the call site only falls back when `succeeded=False` (i.e. the source query raised). 4 new regression tests in `tests/unit/test_bar_chart_bucketed_aggregate.py` (2 for the success-flag behaviour, 2 for the `include`/scope-filter pass-through), bringing the file total to 27.

### Agent Guidance
- **Source-enumeration always passes `include=[group_by]`.** This matches the workspace items fetch — the FK relation must be present in the dump for `_bucket_key_label` to derive a sensible label. If you add a new path that calls `_enumerate_distinct_buckets`, route it through a repo that supports the `include` kwarg, or supply pre-computed `bucket_values` instead.

## [0.58.21] - 2026-04-22

Patch bump. Two follow-on bug fixes (#849).

### Fixed
- **Bar-chart FK `group_by` enumerates buckets from the full source entity, not the region's first items page (#849 Bug B).** New `_enumerate_distinct_buckets` in `src/dazzle_back/runtime/workspace_rendering.py` pages through the source repo (cap 1000 rows, 200/page), dedupes by bucket key via the same `_bucket_key_label` used elsewhere, and applies scope filters so users can't see buckets they wouldn't be allowed to see rows for. The items-page derivation remains as the fallback when the source repo isn't available or the enumeration fails.
- **Per-bucket aggregate filter is now built as a dict, bypassing `_parse_simple_where` for the auto-augmented case (#849 Bug A).** Pre-fix the auto-augment built a SQL fragment string (`"<group_by> = <bucket_key>"`) and round-tripped it through `_parse_simple_where`, which made the per-bucket query brittle to any oddity in the bucket key (UUIDs with dashes, whitespace, etc.) and harder to keep in sync with the REST list endpoint. The `current_bucket` sentinel path still parses the where clause for backward compat with author-written expressions. Per-bucket exceptions now log + return zero instead of breaking the whole region. 8 new regression tests in `tests/unit/test_bar_chart_bucketed_aggregate.py` (3 covering the dict-shape + scope merge + failure isolation, 5 covering source-entity enumeration with pagination + fallback paths).

### Agent Guidance
- **`_compute_bucketed_aggregates` now takes `source_entity`.** Callers should pass `ctx.source` so the bucket enumeration can hit the source repo. Without it, the function silently falls back to deriving buckets from the items page (which is what was wrong in v0.58.20).

## [0.58.20] - 2026-04-22

Patch bump. One follow-on bug fix to #847 (#848).

### Fixed
- **`bar_chart` with `group_by: <FK>` now uses the FK id for filtering and the display field for the label (#848).** Follow-on to #847 — when `group_by` pointed at a ref field, the list endpoint serialised that cell as a `{id, <display_field>, ...}` dict and the bucket derivation called `str(dict)` on it, producing a Python-repr string for both the bar label and the per-bucket filter value. Labels rendered as junk; filters never matched. New `_bucket_key_label(value)` returns a `(filter_key, render_label)` tuple — for FK dicts it pulls `id` for the key and probes `display_name → name → title → label → code` for the label. `_compute_bucketed_aggregates` now threads the tuple through `_per_bucket` so the `current_bucket` substitution and the auto-augmented `<group_by> = <bucket>` filter both use the FK id, and the bar renders the human-readable label. Dedup is by id, so multiple items pointing at the same FK row collapse into one bucket. 8 new regression tests in `tests/unit/test_bar_chart_bucketed_aggregate.py` (5 for `_bucket_key_label`, 3 for the FK end-to-end paths).

### Agent Guidance
- **`group_by:` on bar_chart accepts FK fields again.** The runtime auto-resolves FK dicts to their id+display_field. Authors need no DSL changes — `group_by: assessment_objective` (a ref) and `group_by: status` (a scalar enum) both work. The display-field probe order is `display_name`, `name`, `title`, `label`, `code` — falls through to `id` when none are present, so bare reference rows still get a deterministic (if ugly) bar.

## [0.58.19] - 2026-04-22

Patch bump. One feature/fix (#847).

### Added
- **Bar-chart regions now honour `aggregate:` per bucket (#847).** Authors can express true distributions like "students per grade band" by combining `display: bar_chart`, `group_by: <field>`, and an `aggregate:` block. The runtime evaluates the first aggregate expression once per bucket — substituting the new `current_bucket` sentinel into the where clause when present, or otherwise auto-augmenting the where clause with `<group_by> = <bucket>`. Bucket values come from the field's enum / state-machine first (so empty-but-defined buckets render as zero bars), falling back to distinct values from the source items.

### Fixed
- **Bar-chart no longer silently drops `aggregate:` (#847).** Pre-fix, the template ignored the metrics list when `items + group_by` were both set and rendered raw row counts per bucket — so `count(Manuscript where ...)` came back as a single bar with the count of source rows, not the per-bucket totals authors meant to express. New `_compute_bucketed_aggregates` in `src/dazzle_back/runtime/workspace_rendering.py` runs the per-bucket queries concurrently (one `asyncio.gather` per region) and merges scope filters into each query so row-level security still applies. The template `src/dazzle_ui/templates/workspace/regions/bar_chart.html` prefers `bucketed_metrics` when present and falls through to the existing count/metrics paths otherwise. 7 regression tests in `tests/unit/test_bar_chart_bucketed_aggregate.py`.

### Agent Guidance
- **Use `current_bucket` to write per-bucket aggregate expressions.** Example: `aggregate: students: count(Manuscript where computed_grade = current_bucket)`. The runtime substitutes the sentinel with each enum value or state-machine state from the `group_by` field. If the sentinel is omitted, the runtime auto-augments the where clause with `<group_by> = <bucket>` — works when the source entity and the count entity share the same field name. Only the *first* aggregate is rendered as the bar value; secondary aggregates are still computed via the metrics path.

## [0.58.18] - 2026-04-22

Patch bump. One UI fix (#845).

### Fixed
- **Heatmap row labels are now clickable (#845).** `src/dazzle_ui/templates/workspace/regions/heatmap.html` attached `hx-get` / `cursor-pointer` / `hover:opacity-80` only to the value `<td>` cells, so the leftmost row-label `<td>` was a dead zone — clicking it did nothing. Moved the HTMX attributes + pointer affordance up to the `<tr>` (gated on `action_url`), so the whole row is now the click target. Removed the per-cell `hx-get` to avoid double-fire when the `<tr>` swap would otherwise compete with the per-cell one. Threshold-colour classes still live on each `<td>` as before. Regression coverage in `tests/unit/test_heatmap_row_click.py` (3 tests).

## [0.58.17] - 2026-04-22

Patch bump. One UI fix (#846).

### Fixed
- **Sidebar Lucide icons upgrade on initial load and after HTMX swaps (#846).** `lucide.min.js` is loaded with `defer` in `base.html`, but the old upgrade call sat as a synchronous `<script>if(window.lucide)lucide.createIcons();</script>` at the bottom of `templates/layouts/app_shell.html:186`. The deferred script hadn't executed yet, so `window.lucide` was always `undefined` — every `<i data-lucide>` stayed blank on initial render. HTMX nav swaps had no re-invocation either, so a refresh wouldn't fix it. Moved the hook to `base.html` where it fires on `DOMContentLoaded` (initial load after defer resolves) and `htmx:afterSettle` (every nav swap), so new icon markup rendered into swapped fragments upgrades automatically. Removed the stale one-shot from `app_shell.html`. Regression coverage in `tests/unit/test_lucide_icon_upgrade.py` (4 tests).

## [0.58.16] - 2026-04-22

Patch bump. One UI fix (#844).

### Fixed
- **Workspace card grid rows no longer stretch to the tallest card (#844).** `src/dazzle_ui/templates/workspace/_content.html` used `class="grid grid-cols-1 md:grid-cols-12 gap-4"` with no `align-items` override — CSS Grid's default is `align-items: stretch`, which sized every row to the tallest card and left shorter cards with hundreds of pixels of dead whitespace. Added `items-start` so each grid cell collapses to its intrinsic content height. `dashboard-builder.js` only manipulates `grid-column` spans, so drag/resize behaviour is unaffected. Regression coverage in `tests/unit/test_workspace_grid_align.py`.

## [0.58.15] - 2026-04-22

Patch bump. One release-packaging fix (#843).

### Fixed
- **PyPI wheels now ship a fresh `dazzle-bundle.css` built from the tagged commit's templates (#843).** `src/dazzle_ui/runtime/static/css/dazzle-bundle.css` is gitignored (it's a Tailwind build artifact) and nothing in `publish-pypi.yml` rebuilt it before `python -m build`. On a fresh CI checkout the file was absent, so the wheel shipped a bundle that was either stale (carried over from a previous run) or missing entirely — new Tailwind classes added in template refactors silently dropped from downstream installs. The incident that surfaced this was the UX-031 app-shell refactor (cycle 0.57 → 0.58): classes like `lg:pl-64`, `inset-y-0`, `translate-x-0`, `-translate-x-full` never made it into CyFuture's wheel, collapsing the left sidebar on every workspace page. Fix: `publish-pypi.yml` now installs the package editable, runs `dazzle build-css --output src/dazzle_ui/runtime/static/css/dazzle-bundle.css` against the committed templates, then proceeds to `python -m build`. A post-build guard (`python -m zipfile -l py_dist/dazzle_dsl-*.whl | grep dazzle-bundle.css`) fails the release if the artifact isn't inside the wheel. Regression coverage in `tests/unit/test_publish_workflow.py` pins the step ordering + the grep guard.

### Agent Guidance
- **Don't remove the `dazzle build-css` step from `publish-pypi.yml` without a replacement.** Wheels need the bundle; the `**/*.css` glob in `pyproject.toml` picks it up only when the file exists on disk at packaging time. The `test_runs_build_css_before_python_build` ratchet fires if someone re-orders or deletes the step.

## [0.58.14] - 2026-04-22

Patch bump. One migration-gap fix (#840).

### Added
- **`dazzle db verify --fix-money`** — detects and (optionally) repairs legacy money columns that pre-date the v0.58 split into `{name}_minor` (BIGINT) + `{name}_currency` (TEXT). New module `src/dazzle/db/money_migration.py` walks the DSL's `money(...)` fields, checks each against `information_schema.columns` on the live DB, and classifies every field as **clean** / **drift** (legacy single-column shape still present, no new columns yet) / **partial** (legacy + one of the new columns — repair skipped to avoid clobber). For drifts, the 4-statement repair pattern (`ADD COLUMN _minor` + `ADD COLUMN _currency` + data-preserving `UPDATE` + `DROP COLUMN`) is emitted to stdout by default and, with `--fix-money`, executed on the connection.

### Fixed
- **`dazzle db verify` now surfaces legacy money-column drift instead of leaving apps 500'ing (#840).** Upgrades from pre-v0.58 DBs left money columns on the old DOUBLE PRECISION shape; every `POST`/`PUT` against affected entities returned `psycopg.errors.UndefinedColumn: column "{name}_minor" of relation "..." does not exist` because Alembic autogenerate sees two ADDs with zero DROPs and never detects the type reshaping. The verify command now runs FK integrity **and** money-column drift checks in one pass, prints the repair SQL for operator review, and offers `--fix-money` to auto-apply. 12 regression tests in `tests/unit/test_money_migration.py` cover clean/drift/partial classification, the SQL builder's safety guards (identifier quoting, 3-letter currency validation), and the dry-run-vs-apply behaviour.

### Agent Guidance
- **Don't autogenerate a migration for money-field reshaping.** Alembic's autogen doesn't understand that a DOUBLE PRECISION `{name}` column maps to a `{name}_minor` + `{name}_currency` pair — it will emit two ADD COLUMNs but never DROP the legacy column. Use `dazzle db verify` (with `--fix-money` after backup) to repair; or author the migration by hand following the 4-statement pattern.

## [0.58.13] - 2026-04-22

Patch bump. One critical-path bug fix (#841).

### Fixed
- **SLA breach-check loop no longer crashes every second when `business_hours.schedule` is a `ParamRef` (#841).** `BusinessHoursSpec.schedule` and `.timezone` are declared as `str | ParamRef` (DSL authors can bind them to runtime params), but `SLAManager._elapsed()` passed `bh.schedule` / `bh.timezone` directly to `business_seconds()`, which in turn called `schedule.strip().split()` — raising `AttributeError: 'ParamRef' object has no attribute 'strip'` on every scheduler tick. On Heroku this flooded the logplex buffer until the drain dropped messages. Fix mirrors the `_tier_seconds` pattern already present in-file (`hasattr(x, "default")` guard): `bh.schedule` and `bh.timezone` are now resolved to their default string before `business_seconds` runs. Regression coverage in `tests/unit/test_sla_manager.py::TestBusinessHoursParamRefResolution` (2 tests — one with ParamRef, one with plain str).

## [0.58.12] - 2026-04-22

Patch bump. One UI fix (#842).

### Fixed
- **Auth pages no longer paint a muted strip over the gradient background (#842).** The `auth_page_card` macro wrapped its card content in a `min-h-screen flex items-center justify-center p-4 bg-[hsl(var(--muted)/0.3)]` div. As a flex child of the `.dz-auth-page` body, that wrapper shrunk to fit the `max-w-sm` card width and painted a translucent vertical strip over the gradient instead of filling the viewport. Fix: drop the outer wrapper — `.dz-auth-page` on `<body>` already provides `min-height: 100vh`, flex centering, and the gradient background. All 7 auth templates (login, signup, forgot/reset password, 2fa_setup, 2fa_settings, 2fa_challenge) inherit the fix because they use the same macro. Regression coverage in `tests/unit/test_auth_page_wrapper.py` (4 tests).

## [0.58.11] - 2026-04-22

Patch bump. One orphan-wiring fix (#838).

### Fixed
- **`TwoFactorConfig` IR type is now composed into `SecurityConfig` and read by the runtime (#838).** The type declared 5 policy fields (`enabled`, `methods`, `otp_length`, `otp_expiry_seconds`, `recovery_code_count`, `enforce_for_roles`) but nothing in `src/` referenced it — same defect shape as #834 and #839. `SecurityConfig` now carries `two_factor: TwoFactorConfig = TwoFactorConfig()`. `dazzle_back.runtime.auth.routes_2fa.create_2fa_routes` accepts a `two_factor_config` parameter and stashes it on `_TwoFaDeps`; the three `generate_recovery_codes()` call sites (TOTP enrolment, email-OTP enrolment, regenerate-codes endpoint) now read `deps.two_factor_config.recovery_code_count` instead of the previous hardcoded 8. `AuthSubsystem` in `src/dazzle_back/runtime/subsystems/auth.py` resolves `ctx.appspec.security.two_factor` at startup and threads it through, falling back to framework defaults when no `SecurityConfig` is present on the AppSpec. IR field-reader-parity baseline in `tests/unit/fixtures/ir_reader_baseline.json` shrinks by one (`recovery_code_count` is no longer orphan). 9 new regression tests in `tests/unit/test_two_factor_config_wiring.py` pin the composition, the create_2fa_routes signature, and the structural ratchet that the handlers read from the config.

### Agent Guidance
- **DSL-level 2FA configuration is the next step.** The parser currently has no `two_factor:` clause — downstream apps configure 2FA policy by constructing a `TwoFactorConfig` in Python and threading it through `AppSpec.security`. A DSL parser clause (e.g. `app my_app: security: two_factor: recovery_code_count: 12`) is a natural follow-up and would slot into `src/dazzle/core/dsl_parser_impl/` plus the linker's `_build_security_config` path.

## [0.58.10] - 2026-04-22

Patch bump. One security hardening (#833 Phase 3 of external-resource hardening, closes the phase series).

### Security
- **CSP defaults now align with the bundled templates, and the `standard` profile emits CSP (#833).** `src/dazzle_back/runtime/security_middleware.py::_build_csp_header` previously defaulted `script-src`/`style-src`/`font-src` to `'self' 'unsafe-inline'` only — which meant every deployment using `security_profile="strict"` saw broken pages because the bundled shells load from Google Fonts (+ jsdelivr for the mermaid lazy-load in `workspace/regions/diagram.html`). Defaults now whitelist exactly the origins the post-#832 templates actually reach: `fonts.googleapis.com` (style-src), `fonts.gstatic.com` (font-src), `cdn.jsdelivr.net` (script-src). `SecurityHeadersConfig` gains a `csp_report_only: bool` flag; when set, the middleware emits `Content-Security-Policy-Report-Only` instead of the enforcing header so browsers surface violations without breaking pages. The `standard` profile flips from `enable_csp=False` (historical "CSP can break many apps" comment) to `enable_csp=True, csp_report_only=True` — a stepping-stone for apps graduating to `strict` (which is now enforcing, not report-only). IR-level `SecurityConfig.from_profile` (`src/dazzle/core/ir/security.py`) updated in lockstep. 8 new tests in `tests/unit/test_security.py` pin the default directives, the Report-Only behaviour, and the profile-level flags.

### Agent Guidance
- **When adding new template loads, extend the default CSP directives in one place.** `_build_csp_header` is the single source of truth. The external-resource lint in `tests/unit/test_external_resource_lint.py` plus the CSP-default tests together ratchet both sides — a new CDN load without a matching directive (or vice versa) fails CI.

## [0.58.9] - 2026-04-22

Patch bump. One orphan-wiring fix (#839).

### Added
- **`dazzle compliance render`** — render a markdown compliance document to a branded PDF using `dazzle.compliance.renderer.render_document` + `load_brandspec`. Requires the `weasyprint`/`jinja2`/`markdown` optional dependency group; prints a clear install hint and exits 1 when missing. Brandspec auto-resolves from `.dazzle/compliance/brandspec.yaml` or falls back to the framework default.
- **`dazzle compliance validate-citations <markdown>`** — post-render check that every `DSL ref: Entity.construct` citation resolves against the compiled auditspec. Exits 1 with a listing of unresolved citations so CI pipelines can gate on it.

### Fixed
- **Three compliance modules are now wired to the runtime pipeline (#839).** `dazzle.compliance.citation`, `dazzle.compliance.renderer`, and `dazzle.compliance.slicer` had unit tests but zero `src/` importers — cycle 369 surfaced them as an orphan cluster in the same defect class as #834. `src/dazzle/cli/compliance.py` now uses `slice_auditspec` in the `gaps` subcommand (adds a `--status` flag so gap, partial, or both can be requested from one call site) and exposes the two new subcommands above. `src/dazzle/mcp/server/handlers/compliance_handler.py::compliance_gaps` routes through `slice_auditspec` with optional `status_filter`/`tier_filter` args instead of the previous inline list-comprehension filter — the filter logic now lives in exactly one place. Regression coverage in `tests/unit/test_compliance_wiring.py` (7 tests) pins the imports, the subcommand registration, and the graceful-optional-deps behaviour.

## [0.58.8] - 2026-04-22

Patch bump. One orphan-wiring fix (#834).

### Fixed
- **`HotReloadManager` is now wired into `run_unified_server()` (#834).** `src/dazzle_ui/runtime/hot_reload.py` was authored behind the `enable_watch` + `watch_source` config flags but never imported from any runtime path — the flags were marked `# noqa: F841 — reserved for future use` since the Vite→CSS refactor and nothing actually instantiated the manager. `combined_server.py` now constructs a manager when `enable_watch=True` and a single worker is configured, registers the current `(appspec, ui_spec)` pair, starts the file watcher, and tears it down in the `finally` block of the uvicorn loop. The manager is stashed on `app.state.hot_reload_manager` so later SSE endpoints can register reload clients. Multi-worker mode prints a warning and skips the watcher (fork conflict). Regression coverage in `tests/unit/test_hot_reload.py` (10 tests) pins the watcher lifecycle, SSE registration, and the structural fact that `combined_server` imports `HotReloadManager` without `F841` suppressions.

### Agent Guidance
- **`enable_watch` is now live — multi-worker deployments must keep `workers=1` for the watcher to run.** If you see `--watch is ignored when --workers > 1` at startup, that is expected: fork-based multi-worker mode can't share watcher threads.

## [0.58.7] - 2026-04-22

Patch bump. One security hardening (#830 Phase 1 of external-resource hardening).

### Security
- **SRI integrity on the remaining CDN load (#830).** `src/dazzle_ui/templates/workspace/regions/diagram.html` dynamically injects mermaid via `document.createElement('script')`. The load is now pinned to `mermaid@11.14.0` (was `mermaid@11`, a floating major-version URL) and carries `script.integrity = "sha384-1CMXl090wj8Dd6YfnzSQUOgWbE6suWCaenYG7pox5AX7apTpY3PmJMeS2oPql4Gk"` + `script.crossOrigin = "anonymous"`. Any corruption on the CDN path or intermediate MITM now fails the integrity check and the browser refuses to execute. Google Fonts CSS (still loaded in both shells) is exempted from SRI because the response is dynamically generated per-User-Agent — documented in `_SRI_EXEMPT_ORIGINS` with a citation to the gap doc. Post-#832, this was the only pinned cross-origin JS load remaining in the shipped templates. Preventive lint extended: `tests/unit/test_external_resource_lint.py` gains three new tests — `test_every_script_link_has_sri`, `test_every_js_injected_script_has_sri`, and `test_every_sri_exempt_entry_has_citation` — which fire if a new cross-origin load lands without SRI or without a documented exemption.

### Agent Guidance
- **Bumping mermaid requires regenerating the SRI hash.** Compute via `curl -sL <url> | openssl dgst -sha384 -binary | openssl base64 -A` and update both the URL and the `script.integrity` string in `src/dazzle_ui/templates/workspace/regions/diagram.html`. The `test_every_js_injected_script_has_sri` lint will fail if only one is updated.

## [0.58.6] - 2026-04-22

Patch bump. One security hardening (#832 Phase 2 of external-resource hardening).

### Security
- **Removed Tailwind CDN + jsdelivr-mirror-of-GitHub loads from page shells (#832).** Phase 2 of the cycle 300 external-resource-integrity gap doc. `src/dazzle_ui/templates/base.html` and `src/dazzle_ui/templates/site/site_base.html` previously loaded (a) the Tailwind browser JIT runtime as executable JS via `cdn.tailwindcss.com` / `cdn.jsdelivr.net/npm/@tailwindcss/browser@4`, and (b) Dazzle's own compiled dist via `cdn.jsdelivr.net/gh/manwithacat/dazzle@v<version>/dist/...` — both are now removed. `dazzle-bundle.css` (produced by `scripts/build_css.py`) is served from `/static/css/` unconditionally, and the Dazzle design-system CSS / lucide icons come from the local static routes. The `_tailwind_bundled` / `_use_cdn` Jinja globals are no longer consulted by any shipped template (kept set for compatibility with downstream apps that may read them). External-resource allowlist in `tests/unit/test_external_resource_lint.py` narrowed: `cdn.tailwindcss.com` removed entirely; `cdn.jsdelivr.net` reason updated to cite only the remaining consumer (mermaid lazy-load in `workspace/regions/diagram.html`, still Phase 1 SRI territory tracked by #830). The `test_every_allowlist_entry_has_hits` guard ratchets this — any future reintroduction fails CI.

### Agent Guidance
- **Do not re-introduce CDN loads in page shells.** Tailwind must be compiled via `build_css.py`; any new vendored JS must live under `src/dazzle_ui/runtime/static/vendor/` and be referenced by the `static_url` filter. The external-resource lint in `tests/unit/test_external_resource_lint.py` enforces this — new allowlist entries require a citation (filed issue, gap doc, or cycle number).
- **`dazzle-bundle.css` is now a hard prerequisite, not a fallback.** Running `dazzle serve` from a source checkout requires `dazzle build-css` to have emitted `src/dazzle_ui/runtime/static/css/dazzle-bundle.css` (gitignored, built on demand). PyPI installs ship the bundle via `package_data`. Missing bundle → unstyled pages, no runtime crash, no CDN fallback.

## [0.58.5] - 2026-04-22

Patch bump. One bug fix (#831).

### Fixed
- **2FA page routes now exist (#831).** `src/dazzle_ui/templates/site/auth/2fa_challenge.html`, `2fa_setup.html`, and `2fa_settings.html` shipped in an earlier cycle as styled templates but no Python page route served them — users could configure 2FA at the backend but had no URL to reach the UI. `create_auth_page_routes` in `src/dazzle_back/runtime/site_routes.py` now registers `GET /2fa/setup`, `GET /2fa/settings`, and `GET /2fa/challenge`. Setup/settings redirect unauthenticated requests to `/login?next=<path>`; the mid-login challenge is public and accepts the pre-login session token via `?session=<token>`. `SiteAuthContext` gains `session_token`, `default_method`, and `methods` fields; `build_site_auth_context` handles three new page types. `create_auth_page_routes` now accepts an optional `get_auth_context` callable, threaded through from `app_factory.py`. Orphan and page-route ratchets in `tests/unit/test_template_orphan_scan.py` and `tests/unit/test_page_route_coverage.py` no longer allowlist the three templates. Regression coverage in `tests/unit/test_2fa_page_routes.py`.

## [0.58.4] - 2026-04-22

Patch bump. One framework-correctness fix (#835).

### Changed
- **`WorkspaceContract` generator now fans out per persona (#835).** Previously the generator at `src/dazzle/testing/ux/contracts.py` emitted exactly one contract per workspace with no persona field, so persona-scoped workspaces (`access: persona(admin)`) legitimately 403-ing non-admin personas were misread as framework bugs (EX-026). `WorkspaceContract` now carries `persona` and `expected_present`, mirroring `RBACContract`. The generator iterates `(workspace, persona)` pairs using `workspace_allowed_personas()` — the same single-source-of-truth helper the runtime enforcement path uses — so the contract and the runtime agree on visibility. The driver in `src/dazzle/cli/ux.py` uses the contract's persona when authenticating and treats HTTP 403 as a PASS when `expected_present=False`. Regression tests in `tests/unit/test_ux_contracts.py` pin the fan-out shape and the admin_dashboard persona-filter example; cross-app generation verified against all 5 example apps (simple_task: 15 contracts, contact_manager: 4, support_tickets: 16, ops_dashboard: 4, fieldtest_hub: 12 — each with a sensible allowed/denied split). Internal API break (contract identity changed); no downstream shim per ADR-0003.

### Agent Guidance
- **`WorkspaceContract` identity now includes `persona` and `expected_present`.** When authoring verification tests or baselines that reference workspace contract IDs, regenerate them — old hashes are no longer stable. The `_id_key` grammar is documented in the `WorkspaceContract` docstring.

## [0.58.3] - 2026-04-21

Patch bump. One security fix (#829).

### Security
- **TOTP enrollment no longer leaks the shared secret to a third-party QR service (#829).** The 2FA setup flow previously handed the full `otpauth://` URI — including the base32 TOTP seed — to `api.qrserver.com` via a client-side `<img src=…>`, so every enrollment transmitted the secret to that service in the clear query string. Fix: `_setup_totp` in `src/dazzle_back/runtime/auth/routes_2fa.py` now renders the QR server-side with `segno` and returns it as an inline `data:image/png;base64,…` URI alongside `secret`/`uri`. Template `src/dazzle_ui/templates/site/auth/2fa_setup.html` reads `data.qr_data_uri` directly — the secret never leaves the server. `segno>=1.5` added as a required dependency (pure-Python, zero transitive deps). External-resource allowlist entry for `api.qrserver.com` removed; regression test in `test_2fa_auth.py::TestLoginFlowAsync::test_setup_totp_returns_server_rendered_qr_data_uri` pins the new shape.

## [0.58.2] - 2026-04-21

Patch bump. One UI bug fixed (#837).

### Fixed
- **filterable_table loading overlay no longer flashes on initial navigation (#837).** Added `x-cloak` attribute to the overlay container in `src/dazzle_ui/templates/components/filterable_table.html`. Previously the SSR'd HTML arrived with the overlay at its default Tailwind `flex` display; Alpine would take ~169ms to hydrate and apply `x-show="loading"` → `display: none`, producing a visible loading flash that agent-QA tools (LLM + Playwright `browser_snapshot`) consistently captured as "stuck Loading". The `[x-cloak]` CSS rule in `dazzle-layer.css` already existed for this exact pattern — the overlay just missed the sweep that added `x-cloak` to the other Alpine-gated components (`search_input`, `search_select`, `table_pagination`, `bulk_actions`). Zero CSS change required. Surfaced by an AegisMark `dazzle qa trial` run.

## [0.58.1] - 2026-04-20

Patch bump. Two framework-level issues closed with regression tests; one stale trial-backlog entry cleaned up; three UX contract pointers added; seed generator email-uniqueness fix.

### Fixed
- **Fidelity scoring no longer drops collisions when surfaces share a name (#828).** `rendered_pages` was keyed by surface name alone, so two surfaces sharing a name but targeting different entities (e.g. an app's own `feedback_create` vs. the framework's auto-synthesised `feedback_create` on FeedbackReport) silently collided — the scorer then compared the losing surface's fields against the winning surface's HTML and produced ghost structural gaps on a surface that actually rendered its inputs correctly. AegisMark saw 99.65% fidelity where 100% was correct. Fix: `rendered_pages` now keyed by `(surface_name, entity_ref)` tuple; `PageContext.entity_ref` added so compiled contexts are self-describing; `score_appspec_fidelity` signature updated (breaking change on internal function — 2 callers updated in-place per ADR-0003). Regression guard: `TestRenderedPagesCompositeKey` pins the colliding-surface-name case.
- **Workspace dashboards now render inferred primary-action buttons (#827).** When a workspace region references an entity that has a CREATE surface and the current persona can create it, the workspace header shows a "New X" button. Framework-inferred — zero DSL changes. Filter happens per-request via `_user_can_mutate`. Regression tests in `TestWorkspacePrimaryActionCandidates` pin 6 cases (single-region emission, missing CREATE surface, dedup, multi-source fan-out, label fallback, slug form).
- **Seed generator: EMAIL_FROM_NAME and USERNAME_FROM_NAME no longer collapse to duplicate "user" strings when `source_field` misses.** Robust fallback chain (`source_field → name → full_name → first+last → random`) + uniqueness suffix (`.NNNN`). Every seed row produces a distinct email/username even when faker's name pool repeats. Fixed symptom across 4 example-app blueprints where 11-row+ seeds tripped the circuit breaker. Auto-propose default switched from `"full_name"` → `"name"` to match `person_name` output.

### Changed
- **3 UX contract pointers added** to templates that had contracts but no `Contract:` header reference: `filter_bar.html` (UX-033), `search_input.html`, `workspace/regions/diagram.html` (UX-061).

### Agent Guidance
- **Heuristic 1 (raw-layer repro before framework fix)** validated again: TR-1 "--fresh-db truncation silently failing" had a class-names-vs-table-names hypothesis that turned out to be wrong — the actual root cause was `.env` loading, already fixed in #814. Marked the trial-backlog entry RESOLVED.

## [0.58.0] - 2026-04-20

Minor bump. Consolidates a day of fixes shipped since v0.57.98: four GitHub issues closed (#823, #824, #825, #826), two latent runtime bugs found via static-debt sweep, 19 blueprint errors across three example apps, and a trial-harness gate that prevents the agent from landing a devastating verdict without recording any friction observations.

### Added
- **`submit_verdict` friction gate (trial harness).** When the agent's verdict text contains negative-sentiment tokens (`broken`, `404`, `cannot`, `unusable`, `fail`, `missing`, `unresponsive`, `timeout`, etc.) AND `record_friction` was never called during the run, the tool rejects with a nudge to record each specific failure as its own friction entry first. Closes the observed shape where the agent articulated 4+ failures in its verdict paragraph but produced zero actionable friction rows. Three regression tests in `tests/unit/test_qa_trial.py::TestBuildTrialMission`.
- **`dazzle qa trial --fresh-db` pre-flight + circuit breaker (#826).** `verify_blueprint` is now a hard-gate at trial entry — trial aborts with the first 5 error details when the blueprint is drifted, instead of firing 200+ × 400 `/__test__/seed` POSTs and then timing out on `/__test__/authenticate`. Circuit breaker additionally trips after 10 consecutive seed failures with the accumulated error samples and a pointer at `dazzle demo verify`.

### Fixed
- **AppSpec→BackendSpec type mismatch in `combined_server.py` (latent runtime bug).** `mount_graphql(app, appspec, ...)` would raise `AttributeError` the moment `--graphql` was enabled because the function reads `spec.entities` and AppSpec exposes entities at `appspec.domain.entities`. Now calls `convert_appspec_to_backend(appspec)` first, matching the pattern in `dazzle.mcp.runtime_tools.handlers`.
- **`DazzleClient._ensure_csrf_token` referenced non-existent `self.base_url` (latent runtime bug).** Would raise `AttributeError` whenever the CSRF cookie was absent. Swapped to `self.api_url` (`/health` is an API endpoint). Discovered by mypy debt sweep.
- **Fidelity check no longer misfires on float fields (#825).** Added `FieldTypeKind.FLOAT: "number"` to `FIELD_TYPE_TO_INPUT` in `fidelity_scorer.py`. Float fields now render `<input type="number">` as expected; the spurious "change input type to text for float field" gap is gone.
- **Graph-edge lint no longer misfires on audit metadata (#823).** Added `_AUDIT_METADATA_FIELD_NAMES` exclusion set and tightened `_is_edge_field` to require `has_edge AND NOT has_audit`. Fields like `assigned_to` (edge token `to` + audit token `assigned`) resolve as audit and are excluded. 3 regression tests in `test_graph_semantics.py`.
- **Workspace + surface lint skips framework-synthesised names (#824).** `_lint_workspace_personas`, `_lint_workspace_access_declarations`, and `_lint_list_surface_ux` all skip names starting with `_` — `_platform_admin`, `_admin_metrics`, `_admin_sessions`, etc. Adopters can't fix these from their DSL.
- **Admin builder produces sortable/filterable defaults (#824 bonus).** `_TIMESTAMP_SUFFIXES` gained `_start`/`_end` so `bucket_start` gets a newest-first sort. New `_CATEGORICAL_FIELD_NAMES` set makes `event_type`, `component`, `topic`, `process_name` recognised as filter candidates.
- **3 example-app blueprints: 19 strategy-type errors → 0.** simple_task (3), support_tickets (4 + 1 length-cap warning), fieldtest_hub (12). Pattern: `date_relative`/`free_text_lorem`/`uuid_generate` on `ref` → `foreign_key`; `date_relative` on numeric fields → `numeric_range`; `date_relative` on `str` → `static_list`. `dazzle demo verify` on all three: "Blueprint looks healthy." `qa trial --fresh-db` can now actually run against these apps.
- **`src/dazzle_ui/` fully mypy-clean (28 → 0 errors).** Narrow correctness wraps in `page_routes.py` (`bool()` cast + preference-dict narrowing), `expression_eval.py` (6 comparison returns), `experience_routes.py` (RedirectResponse/HTMLResponse rebind `# type: ignore[assignment]`), `hot_reload.py` (tuple→list). Module-level mypy-plugin suppression on `surface_converter.py` for a Pydantic `populate_by_name=True` false positive (17 sites → 1 annotation).
- **`src/dazzle/testing/` fully mypy-clean (7 → 0 errors).**

### Changed
- **EX-048 marked MOSTLY_FIXED.** `purpose` wired (shipped in v0.57.98); `show` + `show_aggregate` classified YAGNI (zero DSL consumers across the 5 example apps); `action_primary`, `defaults`, `focus` deferred as niche follow-ups pending a dedicated renderer per field. Issue #827 filed for `action_primary`'s nearest concrete consumer: workspace dashboards missing a primary-create CTA (surfaced during 2026-04-20 trial-cycle on simple_task).

### Agent Guidance
- **`dazzle demo verify` is now the right first step before seeding.** If it reports any errors, `dazzle qa trial --fresh-db` will refuse to seed — check the output there first.
- **Framework-synthesised names use `_`-prefix convention.** Lint rules now skip `_*` workspaces + surfaces automatically. When authoring new framework-generated constructs, use the prefix.

## [0.57.98] - 2026-04-19

### Added
- **Surface `purpose` + per-persona override wiring (EX-048 partial closure).** DSL authors have been writing `ux.purpose: "..."` on surfaces (and `for <persona>: purpose:` inside persona-variant blocks) for many cycles, but the field was silently dropped at compile time — 14+ declarations across contact_manager + fieldtest_hub were invisible at render. This release closes the gap:
  - `PageContext.page_purpose: str` + `PageContext.persona_purposes: dict[str, str]` added to `src/dazzle_ui/runtime/template_context.py`.
  - New `_extract_surface_purpose()` helper in `template_compiler.py` threaded through all six `return PageContext(...)` sites (list / create / edit / view / review / custom).
  - Request-time persona override resolved in `page_routes._render_response` using the same compile-dict-then-resolve pattern proven for `empty_message` (cycle 240) and `persona_hide` (243) — walks `user_roles` in order, first match wins.
  - `app_shell.html` renders `<p class="dz-page-purpose text-[13px] text-[hsl(var(--muted-foreground))] ..." data-dazzle-purpose>{{ page_purpose }}</p>` as a muted subtitle above the content block when `page_purpose` is truthy; emits nothing when empty.
- **`tests/unit/test_page_purpose_wiring.py`** — 12 tests covering the extractor (None/empty/surface-only/persona-variants), compile-branch threading for all 5 non-custom modes, and three render gates (non-empty, empty, persona override via `model_copy(update=...)`).

### Changed
- **EX-048 status updated to MOSTLY_FIXED.** `purpose` now wired. `show` + `show_aggregate` classified YAGNI (zero DSL consumers across all 5 example apps — Heuristic 1 verified via grep before work). `action_primary`, `defaults`, `focus` remain deferred — each has real fieldtest_hub DSL consumers but needs a dedicated renderer (surface-header CTA, form pre-fill, workspace emphasis respectively); each is a standalone mini-feature not worth shipping speculatively.

### Agent Guidance
- **New layout invariant: `page_purpose`.** Any new layout template OR any new surface-compile branch MUST thread `page_purpose` + `persona_purposes` from `surface.ux` via `_extract_surface_purpose(surface.ux)` into the `PageContext(...)` constructor. Otherwise DSL authors' `ux.purpose` declarations will silently drop. Pattern:
  ```python
  page_purpose, persona_purposes = _extract_surface_purpose(surface.ux)
  return PageContext(
      page_title=...,
      page_purpose=page_purpose,
      persona_purposes=persona_purposes,
      ...
  )
  ```
- **`app_shell.html` renders the subtitle once.** Content templates (filterable_table.html, form.html, detail_view.html, etc.) MUST NOT render `page_purpose` themselves — the shell owns the slot so there's exactly one subtitle per page, immediately above the content block.

## [0.57.97] - 2026-04-19

### Fixed
- **Eliminated theme flash-of-light on first paint for returning dark-mode users (UX-056 Q1).** `<html data-theme="light">` was hardcoded in both `site/site_base.html` and `base.html`; `site.js` ran `initTheme()` before `DOMContentLoaded` but the browser had already committed at least one paint with the wrong attribute. Returning dark-mode users saw a brief white flash on every page load. Fix threads theme through the server: `ThemeVariantMiddleware` in `src/dazzle_ui/runtime/theme.py` reads a validated `dz_theme` cookie into a `ContextVar`; `template_renderer.create_jinja_env` registers the reader as the `theme_variant` Jinja global; both layout templates now emit `<html data-theme="{{ theme_variant() }}">`. Unknown/malformed cookie values fall back to `"light"` so a bad cookie can never inject arbitrary attribute strings.
- **Cross-shell theme sync (UX-048 Q1).** Marketing shell (`site.js` `localStorage.dz-theme-variant`) and in-app shell (Alpine `$persist` `localStorage.dz-dark-mode`) stored theme state in separate keys, so toggling dark on `/` and signing in reverted to light. Both shells now write the shared `dz_theme` cookie on every toggle (marketing: `storePreference()`; in-app: `app_shell.html` Alpine `applyDark()`), and both read the cookie server-side on the next request. Legacy `localStorage` keys remain for backward compatibility but no longer drive cross-shell inconsistency — the cookie is the cross-shell source of truth.

### Added
- **`src/dazzle_ui/runtime/theme.py`** — `ThemeVariantMiddleware`, `theme_variant_ctxvar`, `get_theme_variant()`, `install_theme_middleware()`. The cookie name is `dz_theme`; accepted values are `{"light", "dark"}` only; unknown values fall back to `"light"`; the ctxvar resets between requests via `reset(token)` in the middleware's `finally` block so values don't leak across nested Starlette test clients.
- **`tests/unit/test_theme_variant_middleware.py`** — 13 tests covering ContextVar defaults, middleware behaviour over HTTP (default without cookie, `dark`/`light` cookie reads, malformed-cookie rejection, unknown-variant rejection, ctxvar-reset-between-requests), Jinja global registration, site_base.html + base.html template integration, and the `_htmx_partial` branch that skips the `<html>` wrapper entirely.

### Agent Guidance
- **Add `<html data-theme="{{ theme_variant() }}">` to any new layout template.** The `theme_variant` Jinja global is registered in `template_renderer.create_jinja_env` and resolves to the per-request variant from `ThemeVariantMiddleware`. Never hardcode `data-theme="light"` — it produces a flash-of-light regression for returning dark-mode users.
- **JS toggles MUST write the `dz_theme` cookie** alongside any `localStorage` writes. Pattern: `document.cookie = 'dz_theme=<variant>; path=/; max-age=31536000; SameSite=Lax'`. See `src/dazzle_ui/static/js/site.js::storePreference` (marketing) and `src/dazzle_ui/templates/layouts/app_shell.html` Alpine `applyDark()` (in-app) for the canonical shapes.

## [0.57.96] - 2026-04-19

### Fixed
- **Eliminated all DaisyUI class residuals from user-facing templates.** The v0.51 design-system regime replaced DaisyUI utility tokens with `.dz-*` canonical markers + HSL-variable Tailwind, but 8 leaks survived in uncontracted or loosely-governed templates (synthesised in `dev_docs/framework-gaps/2026-04-19-daisyui-residuals-in-uncontracted-templates.md`). This release closes all 8:
  - `workspace/regions/tab_data.html` — 3 leaks fixed in cycle 268 (duplicate border class, dangling `hover`, `link link-hover link-primary`).
  - `site/sections/testimonials.html:7` — `card` → `rounded-[6px]` (cycle 269).
  - `components/island.html:9` — `skeleton` → `dz-skeleton` + HSL bg + animate-pulse (cycle 270).
  - `experience/_content.html:138` — `card` → `rounded-[6px]`.
  - `fragments/detail_fields.html:4` — `card ... shadow-sm` → canonical detail-view chrome.
  - `components/alpine/dropdown.html:13` — `menu p-1` → `p-1 space-y-0.5`.
  - `layouts/single_column.html:6` — `navbar` → explicit flex+padding chrome.
  - `site/sections/features.html:8` — `card ... shadow-sm` → canonical card chrome.

### Added
- **`tests/unit/test_no_daisyui_residuals.py`** — durable CI lint rule scanning every non-exempt `.html` under `src/dazzle_ui/templates/` for banned DaisyUI tokens inside `class="..."` attributes. Bans the canonical DaisyUI vocabulary (`card`, `menu`, `btn`, `hero`, `skeleton`, `alert`, `badge`, `collapse`, `input`, `link`, `navbar`, `rounded-box`, `bg-base-*`, `text-base-content`) plus their variant prefixes. Explicit exemption for `templates/reports/` (internal dev artefact). 6 tests — 1 scanner + 5 sanity checks (dir exists, ban list self-consistent, `dz-*` always allowed, detector fires on known inputs, exempt paths exist). Runs in ~0.25s. Any future DaisyUI reintroduction fails CI at PR time.

### Agent Guidance
- **No new DaisyUI classes in `src/dazzle_ui/templates/*.html`.** The new lint rule at `tests/unit/test_no_daisyui_residuals.py` enforces this. Use `.dz-*` canonical markers + HSL-variable Tailwind arbitrary values (e.g. `bg-[hsl(var(--card))]`) instead. The ban list is the source of truth in that file — update it (with tests) when adding new tokens to the regime.

## [0.57.95] - 2026-04-19

### Fixed
- **`ux verify --contracts --managed` auth failure on CI (EX-050).** When `DAZZLE_TEST_SECRET` is not pre-exported, `dazzle serve --local` generates a random secret in the subprocess and writes it to `.dazzle/runtime.json`, but the parent process driving the contracts check never picked it up — `HtmxClient.authenticate()` reads `DAZZLE_TEST_SECRET` from env only, so every `POST /__test__/authenticate` went out with no `X-Test-Secret` header and was 401-rejected. Symptom on CI: `auth failed for <persona>` across every persona → 56/64 contract failures on support_tickets, blocking the `contracts-gate` badge since commit `454a7ffd` (2026-04-18). Masked on local dev by the shell having `DAZZLE_TEST_SECRET` pre-exported. Fix in `src/dazzle/testing/ux/interactions/server_fixture.py`: after waiting for `runtime.json`, the fixture reads the generated secret via `read_runtime_test_secret()` and propagates it into the parent's `os.environ`; restores the prior value on teardown. Verified with `env -u DAZZLE_TEST_SECRET python -m dazzle ux verify --contracts --managed` on support_tickets — `Contracts: 34 passed, 0 failed, 30 pending` (matches baseline).

### Agent Guidance
- **`launch_interaction_server` now exports the subprocess's `DAZZLE_TEST_SECRET` into the parent env.** Any code running in the same process as the fixture (HtmxClient, SessionManager, direct httpx calls to `/__test__/*`) can now use the env var without any fallback to reading `runtime.json`. Teardown restores the prior value so fixtures don't leak secrets between tests.

## [0.57.94] - 2026-04-19

### Added
- **`dazzle demo verify` command.** Static analysis of a project's demo blueprint against its AppSpec. Flags strategy/type mismatches (e.g. `date_relative` on a `ref` field, `free_text_lorem` on a `decimal` field), unknown entity/field references, invalid enum values, string-length violations, and required fields without patterns. Exit code 0 clean, 1 on errors, 2 on load failure. `--strict` escalates warnings to exit 1; `--json` emits a structured report. Sits alongside `dazzle validate` and `dazzle lint` in the static-analysis family — NOT a looping cycle (blueprints don't drift continuously).
- **`STRATEGY_COMPATIBILITY` table** in `dazzle.demo_data.verify` maps each `FieldStrategy` to the `FieldTypeKind` values it can legitimately fill. Single source of truth; stays in sync with `FieldStrategy` when new strategies are added. 13 unit tests pin every rule.
- **Integrated into `dazzle qa trial --fresh-db`** as a soft-gate pre-flight: logs violations but continues seeding (some imperfect data is usually better than none for a trial). The narrow runtime heuristic guard from v0.57.93 stays in place as a safety net.
- Real-world validation: `dazzle demo verify` against the five example-app blueprints correctly catches every drift pattern that was biting `/trial-cycle` runs (dates on ref fields, lorem on ref fields, etc.) — static analysis now surfaces them BEFORE data is generated rather than as mysterious 400s during seed.

### Agent Guidance
- **Run `dazzle demo verify` after editing a blueprint.** Same rhythm as `dazzle validate` after editing DSL: author → verify → fix → commit. Catches the common authoring-drift classes before they hit generation or seed-time failures.
- **`STRATEGY_COMPATIBILITY` is the source of truth** for which strategies work on which field types. Update the table (and tests) when adding new field strategies.

## [0.57.93] - 2026-04-19

### Fixed
- **Blueprint generator rescues seed from common authoring drift (#821).** `BlueprintDataGenerator._generate_users_from_blueprint` hardcoded `"full_name"` as the key in generated User rows even when the entity's blueprint declared `name` — support_tickets and simple_task User entities failed every seed row on `name: Field required`. Fix emits BOTH `"name"` and `"full_name"` so either schema works; the `/__test__/seed` endpoint filters by known fields so the unused alias drops out harmlessly.
- **New heuristic guard in `_generate_row`** catches two common blueprint authoring mismatches and drops the offending field from the row (NULL'd instead of crashing the POST):
  1. `date_relative` strategy on a field whose name doesn't contain date-like tokens (e.g. `created_by`, `error_rate`, `avatar_url`).
  2. Any strategy emitting a non-UUID string on a field whose name looks like a ref (`assigned_to`, `created_by`, `*_id`, etc.).
- Narrow by design — NOT a full IR-aware validator. The aim is to rescue seed runs from the common case without over-constraining blueprint authoring. 11 new unit tests.
- **Per-app blueprint corrections** for 9 enum fields that used `date_relative` instead of `enum_weighted` (support_tickets/Ticket.status, simple_task/Task.status, ops_dashboard/System.status, and 6 more in fieldtest_hub). Plus contact_manager Contact.phone flipped from 2-5-word lorem (which exceeded the `str(20)` cap) to a static list of realistic phone numbers.
- Net result across a full sweep: simple_task now seeds **23/23** fixtures (100%) — trial runs there will now evaluate against real data. contact_manager 1/30, ops_dashboard 0/40, support_tickets 3/43 — remaining failures are per-blueprint ref-field tuning (fields needing `foreign_key` strategy that currently use `free_text_lorem`), tracked as follow-up authoring work.

### Agent Guidance
- **Blueprint strategies must match field intent.** `date_relative` belongs on `*_at` / `*_date` / `deadline` / `expires` fields. Enum fields need `enum_weighted` with `enum_values` in params. Ref fields need `foreign_key` pointing at the parent entity. The heuristic guard from this release rescues runs from the most common drift, but accurate blueprints are still the way to get full seed coverage.
- **Emit both `name` and `full_name` for User entities.** Keep this dual-emit in `_generate_users_from_blueprint` when modifying it — projects that clone User schemas split between the two field names and the alias is the cheapest way to support both.

## [0.57.92] - 2026-04-19

### Fixed
- **qa trial seed bypasses Cedar via `/__test__/seed` (#820).** #817 made `--fresh-db` seed data via the regular entity API, but that API enforces Cedar `permit.create` — and most example apps scope business-entity creation to business personas (customer/agent/manager), not admin. Result: 3 of 5 example apps had 100% seed-row failure rate with empty `permitted_personas` 403s. Fix: replaced the HTTP-POST + CSRF-juggling path with direct POSTs to the existing `/__test__/seed` endpoint, which calls the repository layer directly and bypasses Cedar entirely. Gated by `X-Test-Secret` like the rest of `/__test__/*`. POSTs fixtures one-at-a-time (the endpoint is atomic per batch) so blueprint data-quality failures on some rows don't roll back the good ones. Verified end-to-end on support_tickets — no more auth errors, all remaining failures are legitimate DB integrity violations (tracked as #821).
- **`submit_verdict` now terminates the trial loop (#822).** `_trial_completion` used `getattr(action, "tool_name", "")` but `AgentAction` has no `tool_name` field — tool names live on `action.target`. Result: every trial reported `outcome=max_steps` even after the agent had written a verdict, wasting 20-40% of step budget. Fixed to `action.target == "submit_verdict"`; 5 new unit tests pin every relevant action-type case.

### Changed
- **`_seed_demo_data_for_trial` no longer uses `DemoDataLoader`.** The CSRF-sync request hook + admin auth scaffolding is gone; the helper now speaks directly to `/__test__/seed`. Cleaner and shorter (~40 LOC removed) and no longer depends on the DSL choosing a CRUD-permit list that includes admin.

## [0.57.91] - 2026-04-19

### Fixed
- **`qa trial --fresh-db` now seeds demo data after truncating (#817).** #810 introduced `--fresh-db`, #814 made truncation actually work — and those fixes then exposed the opposite problem: every trial ran against a totally empty app, so every verdict became "can't evaluate, nothing here". 7 of 9 cycles in the post-#814 sweep had this framing as the dominant signal.
- Fix: extended `dazzle.cli.demo._find_data_dir` to also look in `dsl/seeds/demo_data/` (where `dazzle init` and every example app puts their blueprint). Added `dazzle.cli.qa._seed_demo_data_for_trial` that runs post-server-launch: finds the blueprint, generates JSONL rows into a tempdir (when pre-generated files don't exist), authenticates as admin via `/__test__/authenticate`, primes the CSRF cookie with a GET, then POSTs rows via `DemoDataLoader`. An `httpx` request hook keeps `X-CSRF-Token` synced to the (rotating) `dazzle_csrf` cookie so CSRF stays valid across every POST.
- Verified: contact_manager trial seeded partial data (1/30 rows; rest failed on blueprint data-quality issues — phone-field lorem ipsum, duplicate emails — which is a separate issue) and produced 20 friction observations vs the 4-or-fewer typical of empty-app runs. Agent also called `submit_verdict` (`outcome=completed`) for the first time in 10+ cycles, confirming #818's step-N-5 nudge works end-to-end on real data.

### Agent Guidance
- **Blueprint quality matters now that seed is live.** `--fresh-db` exercising the blueprint-generated data is the fastest way to surface pattern bugs (fields that exceed their type's length, non-unique values for `unique` columns, etc.). When a trial reports bulk `seed error:` lines for a given entity, fix the blueprint's `field_patterns` before blaming the framework.

## [0.57.90] - 2026-04-19

### Fixed
- **Step-budget nudge for mission terminal tools (#818).** Across nine `/trial-cycle` runs, the trial agent never once called `submit_verdict` — 100% of cycles ended `outcome=max_steps` and relied on `trial_verdict_fallback.synthesize_verdict`. The nudge to submit lived only in the static system prompt at construction time; as the step budget drained, nothing reminded the agent. `DazzleAgent._build_messages` now takes `steps_remaining` + `mission` kwargs, and when `1 ≤ steps_remaining ≤ 5` it injects a hard-stop user message pointing at the first entry in `mission.terminal_tools` (or `done` if none). Trial mission declares `terminal_tools=["submit_verdict"]`.
- Also added a `logger.info("agent tool call: %s", tool.name)` line to `_execute_tool` so future runs can audit tool-use patterns and distinguish "agent never tried" from "agent tried but SDK rejected".
- **Dedup threshold tuned down (#819).** `_CLUSTER_SIMILARITY_THRESHOLD` in `trial_report.py` was 0.8 — too strict for LLM paraphrase variance, so cycle 3 (20 raw) and cycle 8 (17 raw) both collapsed 0 entries despite obvious near-duplicates. Lowered to 0.65. Existing dissimilar-description test pair scores 0.25 (safely below), near-duplicate "No items found" variants score 0.72–0.89 (above). 1 new test pins this behaviour.

### Changed
- **Mission.terminal_tools field.** New `list[str]` field on `dazzle.agent.core.Mission`. Missions that complete via a domain-specific tool (e.g. `submit_verdict` for qa trials) should list that tool here so the step-budget nudge targets the right tool name. Default empty list → falls back to `done`.

### Agent Guidance
- **Missions that produce a final artefact should declare `terminal_tools`.** Example: the trial mission's wrap-up tool is `submit_verdict`; the step-N-5 nudge references that name specifically so the agent stops exploring and commits a verdict. Missions without a final artefact (pure exploration) can leave `terminal_tools` empty and rely on the generic `done` action.

## [0.57.89] - 2026-04-19

### Fixed
- **Browser tab title stuck after hx-boost navigation (#816).** The `_page_handler` fall-through path only returned the partial HTML body — no `HX-Trigger-After-Swap` event for the title update. The infra to update the title via `dz:titleUpdate` already existed (fired for `wants_fragment` and `wants_drawer` paths; dz-a11y.js listener updates `document.title`), but the most common case — `hx-boost` navigation between regular pages — never emitted the trigger. Result: users landing on `/app/tester` via a click from `/app/testers` (404) saw the working tester directory with "Page Not Found - Dazzle" in the tab title.
- Fix: the fall-through now builds a `HX-Trigger-After-Swap: {"dz:titleUpdate": page_title}` header whenever the response is a partial and `page_title` is set. Symmetric with the existing `wants_drawer` path. Full-document responses (history-restore) still update the title natively via the `<title>` element.

### Agent Guidance
- **The partial-response path sets `HX-Trigger-After-Swap`.** When adding new HTMX page flows, pattern-match the existing `wants_fragment` / `wants_drawer` / fall-through branches in `src/dazzle_ui/runtime/page_routes.py:_page_handler` — all three now emit `dz:titleUpdate` so the browser tab title tracks navigation.

## [0.57.88] - 2026-04-19

### Added
- **Plural entity URLs redirect to canonical singular (#815).** Business users type `/app/tickets`, `/app/contacts`, `/app/alerts` — Dazzle's convention is singular (`/app/ticket`, `/app/contact`, `/app/alert`). Every example app trialled with `/trial-cycle` produced at least one "feature seems broken" 404 from this mismatch. `create_page_routes` now registers a 301 redirect from the plural form to the singular canonical path for each entity. Workspaces live under `/app/workspaces/<name>` so no collision; entities whose singular and plural slugs are identical are skipped; plural paths already registered by a real surface are not shadowed. Verified end-to-end: `curl /app/tasks` → 301 to `/app/task`; `curl /app/users` → 301 to `/app/user`.
- Supersedes the #811 suggestion panel for the plural-URL case — the redirect lands users on the right page directly, no click required. The suggestion panel still handles typos and fuzzy matches.

### Agent Guidance
- **Entity URLs are always singular canonical.** Internal links and nav items should use `/app/<entity>` (singular). Plural paths redirect but cost a 301 round-trip.

## [0.57.87] - 2026-04-19

### Fixed
- **`dazzle db reset` and `dazzle qa trial --fresh-db` connect to the wrong database (#814).** CLI commands outside of `dazzle serve` never loaded `<project_root>/.env`, so DB URL resolution fell back to the default `postgresql://localhost:5432/dazzle` instead of the per-project database. Every `TRUNCATE` then raised "relation does not exist" because the default DB doesn't have the app's tables — and those errors were swallowed, producing the misleading "Fresh DB: truncated N tables (0 rows removed)" banner observed across all three `/trial-cycle` runs on 2026-04-19. Second latent bug: `db_reset_impl` also tried to truncate synthetic platform entities (`SystemHealth`, `SystemMetric`, `ProcessRun`, `LogEntry`, `EventTrace`) whose data lives in Redis/in-memory, not Postgres.
- Fix (1): promoted `_load_dotenv` from `cli/runtime_impl/serve.py` into a shared `cli/dotenv.load_project_dotenv` helper, now called from `cli/db._resolve_url`. Every DB-touching CLI command now picks up `.env` the same way `serve` does. Shell exports still win.
- Fix (2): moved the virtual-entity name set into `dazzle.db.virtual.VIRTUAL_ENTITY_NAMES` (so `dazzle.db.reset` can import it without a cross-package dep) and filter it out at the top of `db_reset_impl`. `sa_schema.build_metadata` now imports the same source of truth.
- 11 new unit tests (`test_cli_dotenv.py`, `test_db_reset.py::test_skips_virtual_entities`).

### Agent Guidance
- **DB CLI commands need `.env` now** — `dazzle db status`, `dazzle db reset`, `dazzle db verify`, `dazzle qa trial --fresh-db` etc. automatically load `<cwd>/.env` before resolving DATABASE_URL. This matches `dazzle serve` behaviour and removes a whole class of "why is this connecting to the wrong DB" footguns.
- **`VIRTUAL_ENTITY_NAMES` is the source of truth** for "this entity has no Postgres table". Import from `dazzle.db.virtual` whenever you need to filter synthetic entities; don't duplicate the list.

## [0.57.86] - 2026-04-19

### Added
- **`/trial-cycle` loop command (`.claude/commands/trial-cycle.md`).** Sibling to `/ux-cycle`. Rotates through every `(example_app, trial.toml scenario)` pair, runs `dazzle qa trial --fresh-db`, and triages findings into `dev_docs/trial-backlog.md` or files GitHub issues for high-severity / cross-cycle-reinforced friction. Where `/ux-cycle` checks shape (contracts, DOM, card safety) deterministically, `/trial-cycle` checks substance (did the user achieve the task, was the RBAC sensible, did the error page help) qualitatively. ~5 min/cycle — default cadence `/loop 60m /trial-cycle`.
- **`qa-trial` skill (`.claude/skills/qa-trial/`).** User-facing skill that auto-triggers when Dazzle users author `trial.toml` or ask to set up qualitative trials. `SKILL.md` covers authoring rules (specific identity, grounded business context, goals not click-paths, stop-when protection); `templates/trial-toml-template.toml` is a blank form to fill in; `references/authoring-guide.md` has domain-specific patterns (SaaS, finserv, healthcare, logistics, edtech, multi-tenant, graph-heavy). Every user domain stress-tests a different surface of the framework — aligns with the convergence hypothesis in ROADMAP.md.

### Agent Guidance
- **When qa trial output is thin**, the scenario is almost always the root cause, not the harness. Invoke the `qa-trial` skill to audit `user_identity` / `business_context` / `tasks` specificity before blaming the framework or the LLM.
- **`/trial-cycle` is the upstream signal generator for framework issues.** It files issues that `/issues` then picks up and resolves. Don't run both concurrently — `/issues` should run on a different cadence (or on-demand after trial-cycle pauses).

## [0.57.85] - 2026-04-19

### Added
- **Friendly 404: in-app 404 page now suggests plausible alternatives (#811).** When a path inside `/app/*` 404s, `_compute_404_suggestions` proposes up to three links using: (1) plural→singular flip (`/app/tickets` → `/app/ticket` when `ticket` is a known entity slug), (2) dashboard alias (`/dashboard` or `/app/dashboard` → `/app`), and (3) Levenshtein ≤ 2 fuzzy match against entity slugs and workspace names (`/app/conatct` → `/app/contact`). Pure function so the scoring is deterministic; the rendered 404 shows a "Did you mean:" card above the existing Back/Dashboard buttons. 12 unit tests cover each heuristic plus the capping behaviour.
- Sarah's qa-trial hit `/app/tickets` (plural) and got a bare 404 that she read as "tickets feature broken". Same class of friction bit Dan on `/dashboard` vs. `/app/workspaces/command_center`. The 403 disclosure panel (#808) is the precedent: a page that was a dead-end becomes a signpost.

### Agent Guidance
- **404 handler now receives the AppSpec.** `register_site_error_handlers(app, sitespec_data, project_root, appspec=...)` — the new optional `appspec` parameter lets the handler compute suggestions from entity/workspace metadata. Callers still work without it (empty suggestion list, same behaviour as before); pass it whenever possible to surface the friendly 404.

## [0.57.84] - 2026-04-19

### Added
- **`dazzle qa trial --fresh-db` flag (#810).** Opt-in pre-trial DB reset that truncates entity tables (preserving auth) before the server boots. Closes a gap uncovered during post-#809 verification: trials run against apps whose databases persisted placeholder rows (\`Test name 1\`, \`UX Edited Value\`) from earlier runs were re-flagging the stale data as bugs. Calls \`db_reset_impl\` directly (no subprocess, no interactive confirmation), chdirs into the project for correct \`DATABASE_URL\` resolution, and restores cwd even on error. 2 unit tests pin the cwd invariant.

### Agent Guidance
- **Prefer \`dazzle qa trial --fresh-db\`** when validating a fix that touched seed or fixture code. Stale rows from prior runs will otherwise surface as "bugs" in the trial report even after the code fix is correct.

## [0.57.83] - 2026-04-19

### Changed
- **Trial reports cluster near-duplicate friction (#812).** `dazzle qa trial` agents routinely re-record the same finding 4-8 times despite the "don't flag duplicates" system prompt — 8 praise entries all about the Issue Board, 6 separate bugs for one 403, and so on. `trial_report._cluster_friction()` now groups entries with the same `(category, url)` and a `difflib.SequenceMatcher` ratio ≥ 0.8 on the description, annotating the canonical entry with `reported: ×N` and surfacing `N near-duplicates clustered` in the section heading. Non-destructive — raw JSON transcripts still include every observation.

### Agent Guidance
- **Trial report friction counts are now deduplicated.** When quoting friction counts from trial reports in issue bodies, use the rendered count; the raw JSON transcript is still available for harness-level debugging when the dedup itself is in question.

## [0.57.82] - 2026-04-19

### Fixed
- **Ref-entity filter dropdowns silently empty (#813).** `filter_bar.html` fetched `/{entity}?page_size=200` to populate ref-entity filter options (e.g. `assigned_to` on the simple_task list), but the backend caps `page_size` at 100 via `Query(..., le=100)`. Every such fetch returned 422, the Alpine `x-init` `.catch(() => { refLoading = false; })` silently swallowed the error, and the dropdown rendered with only the "All" option. To users the select looked unresponsive: clicks opened a menu with nothing to pick.
- Fix: align template with backend cap (`?page_size=100`, matching `macros/form_field.html` which already did this) and surface fetch errors via `console.warn` plus a new `refError` scope variable so future failures stop being invisible. Two surfaces affected out-of-the-box (simple_task `assigned_to`, any `ref`-typed filter in other apps).
- Found via `dazzle qa trial` (agency_lead scenario on simple_task). The contact_manager half of the same issue — "second input unresponsive" — turned out not to be a framework bug but a trial-agent selector quirk (`input:nth-of-type(2)` matched a hidden column-visibility checkbox in a collapsed menu).

## [0.57.81] - 2026-04-19

### Fixed
- **ops_dashboard example: `Alert` permit rules referenced undeclared `operator` role.** `examples/ops_dashboard/dsl/app.dsl` declared personas `admin` and `ops_engineer`, but the `Alert` entity's `permit: list/read/create/update` rules and `scope: for:` directives all referenced `operator` — a role that doesn't exist in the app. The access-control runtime correctly rejected every ops_engineer request for Alert data with 403. Dan (SRE persona) in qa trials consistently hit this as his central blocker.
- Found via the qa-trial loop itself: #808's disclosure panel (shipped v0.57.79) rendered *"Entity: Alert · Operation: list · Your roles: ops_engineer"* — which made the mismatch obvious for the first time. A clean demonstration of how improving error UX surfaces DSL misconfigurations that were previously silent.
- Scenario-level fix (three `role(operator)` → `role(ops_engineer)` + two `for: operator, admin` → `for: ops_engineer, admin` replacements). Not a framework change.

## [0.57.80] - 2026-04-19

### Added
- **Typed empty states for list surfaces (#807).** The DSL's `empty:` directive now accepts either the legacy single-string form (unchanged) or a new block form with per-case copy:

  ```dsl
  empty:
    collection: "No tickets yet. Create one to begin."
    filtered: "No tickets match the current filters."
    forbidden: "You can't see any tickets with your current role."
  ```

  The runtime picks the right case at render time by inspecting whether filters/search are active and whether the fetch errored, producing a distinct UX for:

  - **collection** (genuinely empty) — default copy + "Add one" link to the create surface
  - **filtered** (filters reduced to zero) — copy + "Clear filters" link
  - **loading** (fetch errored) — "Couldn't load X. Try reloading."
  - **forbidden** (reserved; needs follow-on API envelope change to detect reliably)

  Templates receive `table.empty_kind` as a render-time discriminator. Unknown sub-keys in the block form raise a parse error so typos don't silently drop. 8 unit tests pin the behaviour.

  Addresses the recurring "No items found" ambiguity flagged in qualitative trials against `fieldtest_hub`, `simple_task`, and `ops_dashboard` — the single-message shape couldn't distinguish "no data yet" from "filters hiding everything" from "fetch errored", leaving users unable to tell why the page was empty.

### Agent Guidance
- **Prefer the block form of `empty:`** for new list surfaces. It generates better UX for free — the framework now adds an "Add one" link on empty collections and a "Clear filters" affordance on filtered-empty states automatically, derived from surface metadata already in the DSL.

## [0.57.79] - 2026-04-19

### Fixed
- **403 responses now disclose role requirements (#808).** Previously the framework raised `HTTPException(status_code=403, detail="Forbidden")` and rendered a dead-end 403 page with no actionable information. Dan (SRE persona) in `dazzle qa trial` repeatedly reported this as his worst UX moment — *"I can't recommend a tool where the core alert management functionality simply doesn't work"*, when the real problem was an RBAC-scope mismatch he had no way to diagnose.
- New helper `_forbidden_detail()` in `dazzle_back.runtime.route_generator` builds a structured detail dict with `entity`, `operation`, `permitted_personas`, and `current_roles` — reading them from the `cedar_access_spec` that's already in scope at each raise site. Three raise sites updated: the per-entity API gate (route_generator.py:910), the list-gate (route_generator.py:1479), and the page-level entity Cedar check (page_routes.py:622 — previously bypassed the exception handler entirely by returning a plain JSONResponse).
- The exception handler unpacks the dict and passes it to `app/403.html`, which now renders a disclosure panel: *"Entity: Alert · Operation: list · Allowed for: admin, ops_engineer · Your roles: customer"*. A page that was a dead-end is now a signpost.
- HTMX-triggered 403s get `HX-Retarget: #main-content` + `HX-Reswap: innerHTML` + `HX-Push-Url`, so a 403 from an inline fragment fetch now renders the error page at the page level rather than silently being swallowed (HTMX's default non-2xx handling).
- 9 unit tests in `test_forbidden_detail.py` pin the helper's behaviour including edge cases (string vs enum operation, dedup across rules, defensive handling of malformed specs).

### Agent Guidance
- Don't raise `HTTPException(detail="Forbidden")` from new code. Use `_forbidden_detail()` to emit a structured dict the error page can render usefully. The bare string form still works but produces the dead-end experience users reported against.

## [0.57.78] - 2026-04-19

### Fixed
- **#804 actual root cause**: Alpine `x-data` attribute on list-surface tables was double-quoted while its JSON config payload (via `| tojson`) also used double quotes — the browser's HTML parser truncated the attribute value at the first `"` inside the JSON, leaving Alpine to evaluate the malformed expression `dzTable('dt-ticket_list', '/tickets', {`. The `dzTable` component never initialised, and every name it exposes (`loading`, `colMenuOpen`, `isColumnVisible`, `selected`, `bulkCount`, `columnWidths`) cascaded into *"expression error: not defined"* across the entire table surface. Users saw broken filter dropdowns, no column controls, and empty table bodies.
- Fix: single-quoted the `x-data` attribute so JSON's double quotes are valid inside. Swapped the two embedded string literals (`'dt-ticket_list'`, `'/tickets'`) to double quotes consistently. One-character change (`"` → `'`), fully resolves the error cascade.
- Verified empirically via Playwright console-capture: pre-fix, 14+ distinct Alpine expression errors per page load; post-fix, zero. The v0.57.75 fix addressed real tangential issues (`hx-include` selector mismatch, `hx-indicator` target typo, inline scope shadowing) but missed this. Left a load-bearing template comment so no one "tidies up" the quoting and reintroduces the bug.

### Agent Guidance
- **Never use `| tojson` inside a double-quoted HTML attribute.** Jinja's `tojson` escapes `<`, `>`, `&`, `'` — but NOT `"`, because those are JSON's string delimiters. Always single-quote the outer attribute when the value includes `tojson` output, OR route through a `data-*` attribute + JS parse.

## [0.57.77] - 2026-04-19

### Fixed
- **Demo seed data now reads as realistic business data (#809).** The UX seed-payload generator (`dazzle/testing/ux/fixtures.py`) and the Playwright form-filler (`dazzle/testing/ux/runner.py`) previously emitted obviously artificial strings — `"Test first_name 1"`, `"UX first_name 2f828c"`, `"UX Edited Value"` — which trials consistently flagged as *unprofessional*. Both now route through a new shared helper `realistic_str()` in `dazzle/testing/ux/seed_values.py` that uses `faker` with field-name hints: `first_name` → `"Alice"`, `email` → a real-shape email, `title` → a short sentence, `description` → a paragraph. A `realistic_email(entity_name, index)` helper gives emails with a plausible faker-generated local part but pins the domain to `<entity>.test` so per-entity rows remain visually distinct.

### Changed
- **`faker>=20.0` is now a required runtime dependency.** Previously conditionally imported in `dazzle_back/demo_data/generator.py`; the same library is now load-bearing for both demo data AND the UX-verify seed/form-fill paths. Treating it as core removes a whole class of "works on my machine" surprises.

### Agent Guidance
- Need realistic seed values elsewhere? Import from `dazzle.testing.ux.seed_values` — `realistic_str(field_name, index)` and `realistic_email(entity_name, index)`. Faker is now a hard dep so you can assume it's available.

## [0.57.76] - 2026-04-19

### Fixed
- **Workspace heading drift and browser tab title (#805).** Workspaces were rendering `workspace.purpose` (an internal developer-intent string like *"Personal dashboard for support agents"*) as the user-facing heading, which read oddly when a manager landed on an agent's workspace. Replaced the purpose paragraph with a proper `<h2>` showing `workspace.title` (falling back to a humanised `workspace.name`). Also pass `page_title=ws_title` through to `workspace/workspace.html` so the browser tab title matches the visible heading instead of just the app name.
- **Empty button labels for icon-only controls (#806).** Three icon-only buttons (remove card, expand sidebar, collapse sidebar, dark-mode toggle in top nav) had `aria-label` but no visible or `sr-only` text — making them invisible to `textContent` scrapers including agent-driven QA harnesses. Added `<span class="sr-only">` inside each, keeping the `aria-label` for redundancy. Also added `aria-hidden="true"` to the remove-card svg for consistency with the pattern used elsewhere.

## [0.57.75] - 2026-04-19

### Fixed
- **Alpine.js errors + broken filter dropdowns on every list surface (#804).** Three interrelated bugs surfaced by `dazzle qa trial` across four apps:
  - `filter_bar.html` and `search_input.html` used `hx-include="closest [data-dz-table]"`, but the outer table div is stamped `data-dazzle-table` (per the documented convention in `dazzle-layer.css` and the e2e locators). The selector never matched, so filter/search submissions missed context.
  - The same fragments used `hx-indicator="#<table_id>-loading"`, but the actual indicator element is `#<table_id>-loading-sr` (renamed when the loading overlay was refactored to Alpine control). HTMX was pointing at nothing.
  - The ref-entity filter select opened an inline `x-data="{ options: [], loading: true }"` scope whose `loading` shadowed the parent `dzTable` component's `loading` state. HTMX handlers on the `<tbody>` bound to the outer scope, and expression errors cascaded: `selected`, `colMenuOpen`, `isColumnVisible` evaluated inside the narrow inline scope failed because those names don't exist there.
- Fixed all three: fragment selectors now match the outer-div attribute; indicators point to `-loading-sr`; inline scope renames `loading` → `refLoading` to stop the shadow. ~10 lines across 3 templates, no Python changes.

## [0.57.74] - 2026-04-19

### Added
- **Trial scenarios for 4 more example apps.** `simple_task`, `contact_manager`, `fieldtest_hub`, `ops_dashboard` each now have a `trial.toml` with a business-user persona (Maya the agency lead, Tom the accountancy owner, Priya the hardware eng manager, Dan the SRE) and 3-4 tasks suited to the app's domain. Completes coverage across all shipping example apps.
- **`docs/reference/qa-trial-patterns.md`** — cross-cutting analysis of the first five-app trial sweep. Catalogues seven recurring patterns (Alpine errors universal, empty-state ambiguity, demo data quality, 403 dead-ends, role/content mismatch, praised visual design, stranded empty workspaces) and ranks them by leverage. Meta-lessons about the trial loop itself (LLM self-pacing unreliable, identity framing shapes signal density, dedup leaky but acceptable) captured for future scenario-authoring.

### Filed from the multi-app sweep
- #807 — Typed empty states (empty / filtered / forbidden / loading), surfaced independently in 3 apps.
- #808 — 403 error page should disclose role requirements, surfaced by ops_dashboard trial.
- #809 — Demo seed data undermines qualitative evaluation, surfaced by contact_manager + simple_task.

## [0.57.73] - 2026-04-18

### Fixed
- **Trials 1-3 all ended with no verdict — two root causes.**
  - **Tool-name collision.** Our mission tool was named `done`, which collides with the builtin `done` page action. The SDK routed the LLM's `done` tool call to the builtin, which doesn't take a verdict argument, so our handler never fired. The framework does warn about this collision — we now heed it. Renamed the mission tool to `submit_verdict`. All prompt references, the completion criterion, and the scenario stop_when text updated consistently.
  - **Wrap-up trigger was too late.** The previous 75%-of-budget wrap-up nudge still let the agent run out of steps because exploration + recording costs more per step than the LLM estimates. Lowered to 60%.

### Added
- **Fallback verdict synthesizer.** When a trial exits without a captured verdict but has recorded friction, `dazzle qa trial` now issues one follow-up LLM call that reads the friction observations and writes a one-paragraph verdict in the user's voice. The synthesized verdict is prefixed with a transparent disclosure (`synthesized from recorded friction — agent ran out of steps`) so triagers know it wasn't written in-situ. Guarantees 100% verdict coverage regardless of whether the agent manages its own step budget. Cost: ~2-3k tokens per fallback. Safe to fail — an empty verdict is still better than a crash at the end of a 3-minute trial.
- `src/dazzle/qa/trial_verdict_fallback.py` — `synthesize_verdict()` and `_format_friction_for_synthesis()`, plus 3 unit tests for the formatter (the LLM call itself is integration-only).

### Observed (from trial 3 — retained for the record)
- Multiple real findings beyond the `/dashboard` 404: broken filter dropdowns on `/app/ticket` (`closest [data-dz-table]` returns no matches), undefined Alpine expressions (`loading`, `colMenuOpen`, `isColumnVisible`), page title/heading mismatch on `agent_dashboard`, missing team-overview UI (the task Sarah was asked to do). These are Dazzle framework issues, not support_tickets-specific. Filing separately for triage.

## [0.57.72] - 2026-04-17

### Fixed
- **Three tweaks from the first live `dazzle qa trial` run** (v0.57.71 against support_tickets, 25 steps, 137s, 68k tokens):
  - **Trial ended at `max_steps` with no verdict** because the agent didn't know its step budget and got surprised by it. System prompt now surfaces both the total budget and a specific wrap-up step (75% of total), with an explicit instruction to call `done` before running out. A short honest verdict beats an unfinished run.
  - **Agent re-recorded the same /dashboard 404 four times** — no deduplication guidance. Added a ground-rule bullet: *"Don't record the same friction twice. A real user wouldn't file the same complaint four times."*
  - **25 steps was too tight** for a 4-task scenario with a verdict. Bumped support_tickets's `max_steps` to 35 and `time_budget_seconds` to 400. The system prompt now reads the actual configured budget, so the numbers it quotes stay accurate across scenarios.
- Two new regression tests pin the budget-awareness and deduplication prompt language.

### Observed (from trial 1 — worth keeping in mind)
- The `/dashboard` URL 404 in support_tickets IS a real piece of friction — a business-user mental model says "dashboards live at /dashboard." Either add a redirect or teach the 404 page to suggest the workspace URL. Not urgent for the harness, but a genuine finding the tool surfaced that rule-based gates wouldn't catch.

## [0.57.71] - 2026-04-17

### Added
- **`dazzle qa trial` — qualitative business-user trial harness.** A new class of test that asks "does this software actually let me do my job?" rather than "does this component match the DSL?" Puts an LLM in the shoes of a real business user (Sarah, founder of a small B2B SaaS, evaluating whether to switch from Gmail+Notion) and lets it attempt meaningful work. Records friction — bugs, confusions, missing features, aesthetic notes — into a markdown report intended for human triage, **not** a pass/fail CI gate.
- Per-app scenarios declared in `trial.toml` with persona identity, business context, tasks, stopping criteria. Shipped one for `examples/support_tickets` (Sarah / manager persona, 4 tasks).
- Mission type `build_trial_mission` in `src/dazzle/agent/missions/trial.py` reuses the existing DazzleAgent observe→decide→act→record loop. Two mission tools: `record_friction(category, description, url, evidence, severity)` and `done(verdict)`. Uses `launch_interaction_server` for managed server lifecycle (same fixture `--interactions` and `--contracts --managed` use).
- Markdown report renderer in `src/dazzle/qa/trial_report.py`. Verdict-first, then friction grouped by category (bug > missing > confusion > aesthetic > praise) and severity. Code-fenced evidence blocks. Output lands at `<app>/dev_docs/qa-trial-<scenario>-<timestamp>.md`.
- 18 unit tests pinning scenario parsing, tool handlers, report rendering, and sort ordering.

### Agent Guidance
- `dazzle qa trial` is **not** CI-safe. It is non-deterministic, LLM-driven, and costs real tokens per run. Invoke manually to surface fresh qualitative findings, triage the report, and feed the best signals into `/issues`. Different runs will surface different things — that's the point.
- When something in a trial report is "actionable" (bug, clear missing feature), file it as an issue. When it's "user perception" (aesthetic, confusion), decide whether to file, docs-note, or drop.
- Expected cost per trial: ~50-150k tokens, 5-15 minutes wall-clock depending on app complexity and agent verbosity.

## [0.57.70] - 2026-04-17

### Added
- **`contracts-gate` CI job** in `.github/workflows/ci.yml`. Runs `dazzle ux verify --contracts --managed` against `examples/support_tickets` on every push and asserts `failed == 0` (pending allowed — varies with seed data). Baseline on v0.57.70: 34 passed, 0 failed, 30 pending. Any future regression that reintroduces a false-positive workspace failure (bad persona picker, missing region, broken access rule) will break CI immediately instead of shipping to AegisMark's converge pipeline. Follows the same "proven gate becomes blocking" trajectory as INTERACTION_WALK (#800 step 7).
- **`docs/reference/implicitness-audit.md`** — working doc capturing the three implicit conventions surfaced in the v0.57.67→69 post-mortem (`personas[0]` ≡ admin, `default_workspace` only walked one way, `access:` absence inferred from runtime) and proposing four heuristics for finding more: grep for positional IR indexing, agent-readable DSL property tests, dual-layer invariant enforcement, and per-post-mortem reflection. Status line on heuristic 1: 25 `[0]` hits across 15 files today, awaiting a dedicated audit pass.

### Agent Guidance
- **Before assuming `personas[0]` is the admin-equivalent**, check `appspec.admin_persona` once that lands (proposed, not yet shipped) or fall through to `default_workspace` reverse-lookup using `_pick_workspace_check_persona()` as the reference. Positional indexing into IR lists is a code smell — see `docs/reference/implicitness-audit.md` heuristic 1.
- **Before adding a new implicit convention**, ask whether an agent reading only the DSL could derive the behavior. If not, name it. See `docs/reference/implicitness-audit.md` for the four heuristics we now use to catch these.

## [0.57.69] - 2026-04-17

### Fixed
- **Workspace contracts no longer false-positive `HTTP 403 as admin`.** When a workspace had no explicit `access: persona(...)` block, the contracts checker fell back to `appspec.personas[0].id` — conventionally `admin`, whose `default_workspace` points at the framework's `_platform_admin` UI, not the app's workspaces. The access-control runtime correctly returned 403, and the checker reported a failure that was actually a bad persona choice. Real example: support_tickets had 3 such failures (`ticket_queue`, `agent_dashboard`, `my_tickets`), owned by `agent`, `manager`, `customer` respectively — all reported as broken when they were fine.
- Fix: extracted `_pick_workspace_check_persona()` with a documented 3-step decision tree (explicit `access:` → `default_workspace` reverse-lookup → first-declared persona). The second step is new and encodes the DSL's implicit ownership signal.
- 5 unit tests in `tests/unit/test_ux_contracts_persona_picker.py` pin each branch of the decision tree, including edge cases (empty `allow_personas` list, zero personas).
- Verified on support_tickets: `dazzle ux verify --contracts --managed` now reports **34 passed, 0 failed** (was 31/3).

## [0.57.68] - 2026-04-17

### Fixed
- **Agent-driven `dazzle serve --local` could hang indefinitely on Redis connect.** `RedisBus.connect()` called `redis.ping()` with no socket/connect timeout — if REDIS_URL pointed at an unreachable host, the FastAPI `lifespan` startup blocked forever (the UI/API ports were allocated but nothing ever began accepting traffic, and the only visible log was `INFO: Waiting for application startup.`). Observed during agent harness runs where the server appeared to boot but `/__test__/authenticate` returned connection-refused indefinitely. Added `socket_connect_timeout=3.0`, `socket_timeout=5.0`, and an outer `asyncio.wait_for(..., timeout=5.0)` with a descriptive error message telling the caller to check REDIS_URL — so a missing Redis fails fast and loudly instead of hanging.

### Added
- **`dazzle ux verify --contracts --managed`.** Self-manages the local server lifecycle: spawns `dazzle serve --local` via the proven `launch_interaction_server` fixture (same one the `--interactions` flow uses), waits for readiness via TCP health-probe, runs the contract check, then tears down cleanly. Makes `--contracts` safely callable from agents and CI pipelines where no server is already running. Back-to-back invocations verified idempotent: no stray processes, clean port teardown, deterministic output.

### Agent Guidance
- When running `dazzle ux verify --contracts` from an autonomous harness, prefer `--managed` over pre-starting a server — it eliminates the port/state coordination overhead and guarantees teardown. The existing `--interactions` walk already uses this same fixture, so the two checks are now symmetric in their server-lifecycle handling.

## [0.57.67] - 2026-04-17

### Fixed
- **`dazzle ux verify --contracts` false-positive on dashboard workspaces (#803).** Workspace region wrappers with `data-dz-region-name` are emitted client-side by Alpine's `<template x-for="card in cards">` — the SSR HTML contains only a `dz-workspace-layout` JSON data island. The contracts checker only inspected the SSR DOM, so every dashboard workspace (effectively every current Dazzle example) reported `Missing region 'X'` for every declared region.
- Fix: `_check_workspace` now also consults the parsed layout JSON (`cards[].region`) via the existing `_extract_workspace_layout` helper. Regions declared in the data island satisfy the contract — matching the authoritative source for dashboard workspaces. Server-rendered workspaces with real `data-dz-region-name` attrs continue to work unchanged.
- Added two regression tests in `tests/unit/test_ux_contract_checker.py`: one that passes when regions are only in the JSON, one that still fails when the contract names a region the JSON doesn't declare.

## [0.57.66] - 2026-04-17

### Changed
- **INTERACTION_WALK CI job ratcheted to BLOCKING (step 7 of #800).** Removed `continue-on-error: true` from the `interaction-walks` job in `.github/workflows/ci.yml`. Rationale: the harness caught two real regressions during its signal-gathering window — #797 (drag `$el` scope bug causing `dx=0, dy=0`) and #798 (addCard x-for DOM-insertion race causing `body_length=13, region_fetch_count=0`). Both fixed cleanly, all three walks now green across 3 CI retries in v0.57.65. Signal-gathering served its purpose: we know the harness is stable AND catches real regressions.
- Shell retry loop (3 attempts per walk) preserved — it covers transient infra races (server boot, db provisioning). Only a genuinely-red walk after 3 tries breaks the build. If flakes appear post-ratchet, re-add `continue-on-error: true` and file a tracking issue rather than silently tolerating red.

### Agent Guidance
- **INTERACTION_WALK is now a blocking CI gate.** Changes that break the workspace dashboard drag/add/remove flows will fail CI. The diagnostic `[dz-drag]` and `[dz-addcard]` console logs in `dashboard-builder.js` surface the exact failure mode (which selector was missing, which guard returned early) — inspect `gh run view <id> --log --job <interaction-walks-job-id>` and grep for those prefixes to triage.

## [0.57.65] - 2026-04-17

### Fixed
- **#797 root cause identified and fixed — Alpine `$el` scope bug in drag/resize lifecycle.** v0.57.64's `[dz-drag]` diagnostics pinpointed the exact failure: `[dz-drag] startDrag: cardEl NOT FOUND for card-0`. When `startDrag(card.id, $event)` is called from `@pointerdown="..."` on the drag-handle div, Alpine's `$el` magic resolves to the HANDLE element (where the directive lives), not the component root. The card wrapper is an ANCESTOR of the handle, so `handle.querySelector('[data-card-id=...]')` always returns null — hence `this.drag` is never assigned, `onPointerMoveDrag` early-returns on the null guard, and `dx=0, dy=0`.
- Same bug class that killed `addCard` before the #798 fix. Replaced all five live `this.$el.querySelector(...)` sites in `dashboard-builder.js` (startDrag, onPointerMoveDrag, keyboard-move refocus, startResize, onPointerMoveResize) with `document.querySelector(...)`. The component occupies the full workspace page; there's no ambiguity about which grid/card is being queried.
- INTERACTION_WALK harness proved the diagnosis: before the fix, console showed `cardEl NOT FOUND for card-0` every drag attempt despite `pointerdown` firing correctly (`pointerType=mouse, button=0`). v0.57.65 expected to show `[dz-drag] drag state set`, `[dz-drag] phase transition pressed→dragging`, `[dz-drag] reorder X → Y`, `[dz-drag] endDrag wasDragging=true`, and the card_drag evidence dx/dy > 0.

## [0.57.64] - 2026-04-17

### Changed
- **#798 verified closed by harness; #797 reopened with harness evidence.** v0.57.63's rAF-poll fix landed cleanly: `card_add` walk now reports `body_length=51, region_fetch_count=3` across 3 retries in CI. But the same run reports `card_drag` FAIL with `dx=0, dy=0, requested_dy=200` — the defensive fixes in v0.57.46 (listener install ordering, top-level `this.drag` reassignment) did NOT resolve the drag regression. The closed #797 was based on code inspection without a live-browser gesture test; the INTERACTION_WALK harness is now the authoritative signal and it's red.
- **Targeted JS diagnostics in drag lifecycle.** Added `console.log("[dz-drag] ...")` in `startDrag`, `onPointerMoveDrag` (phase transition branch + reorder branch), and `endDrag`. Next CI run will pinpoint the exact failure mode — is pointerdown not firing at all (listener race, wrong element hit-test), firing but failing the phase transition (threshold never crossed), firing and transitioning but not reordering (midpoint hit-test wrong), or reordering but failing to re-render (Alpine proxy reactivity)? Same diagnostic-first pattern that closed #798 in v0.57.62→63.

## [0.57.63] - 2026-04-17

### Fixed
- **Fourth and definitive root-cause fix on #798 — Alpine x-for DOM insertion race.** v0.57.62's targeted console.log diagnostics proved the exact failure: `[dz-addcard] cardEl NOT FOUND for card-<id>` fires inside the `$nextTick` callback. A single `$nextTick` (or even double — see v0.57.59) is not enough to wait for Alpine's `<template x-for>` to actually append the new wrapper + its inner body to the DOM. `this.$el.querySelector(...)` returns null, so `htmx.process()` never runs and `htmx.ajax()` is never called — explaining `sample_urls=[]` across every prior cycle.
- Replaced `$nextTick` with a `requestAnimationFrame`-based polling retry that tries up to 30 frames (~500ms at 60fps) for BOTH the card wrapper (`[data-card-id=...]`) AND the body slot (`#region-<region>-<card-id>`) to appear in the DOM. Once both exist, `htmx.process` + `htmx.ajax` fire the region fetch explicitly. Queries against `document` (not `this.$el`) in case Alpine's x-for template scope boundary is the root cause instead. If both elements haven't landed after 30 frames, the harness logs how many frames were attempted and which of the two selectors was still missing — so if this fix ALSO fails, the next CI output will say so precisely rather than silently returning.

## [0.57.62] - 2026-04-18

### Changed
- **Targeted JS-level diagnostics in `addCard`.** v0.57.61's page-level capture proved HTMX fires fine for initial cards (`initial_api_calls=6`) but NEVER for the dynamically-added card (`sample_urls=[]`). So the bug is specifically in the addCard kickoff path. Restored the `htmx.ajax(url, target, swap)` call from v0.57.59 — but with `console.log("[dz-addcard] ...")` sprinkled through every early-return branch, so the next CI run pinpoints which guard is triggering. Suspect list: cardEl not found (Alpine hasn't rendered yet), workspaceName empty (layout JSON never populated), bodyEl not found (id binding not yet evaluated), or all three return false positive and htmx.ajax IS called but the URL is wrong.
- **Post-walk console dump** in the CLI: after the walks run, print any console messages whose text includes `dz-` or `error` so CI surfaces the JS-level diagnostics without drowning the log in tailwind warnings etc.
- No behavioural change to the walk runtime. Next CI run will either pinpoint the exact broken guard or show the ajax fires but the URL is malformed.

## [0.57.61] - 2026-04-18

### Changed
- **INTERACTION_WALK: page-level XHR + console capture.** v0.57.60's declarative `hx-trigger="load"` fix still showed `sample_urls=[]` during the Add-Card window. To distinguish "HTMX doesn't fire for ANY card" from "HTMX fires for initial cards but not the dynamically-added one," attach the `request` + `console` listeners to the Page at navigation time (before the first `goto`) and log a summary after `wait_for_load_state("networkidle")`. The CLI now prints `[init]` and `[console]` lines showing how many API calls and console messages the initial page produced. If `initial_api_calls=0`, HTMX isn't firing for initial cards either — which would mean the regression is broader than the Add-Card flow.
- Pure diagnostics; no behavioural change to any walk or the harness runtime.

## [0.57.60] - 2026-04-18

### Fixed
- **Third root-cause pass on #798 — declarative `hx-trigger="load"`.** v0.57.59's CI walk showed `sample_urls=[]` for `/api/` or `/regions/` URLs during the Add-Card window, meaning the imperative `htmx.ajax` kickoff from v0.57.58/59 wasn't firing at all (even with double `$nextTick` and direct URL construction — bodyEl was never found, or the call silently threw).
- Structural fix: added `load` to the card body's `hx-trigger` in `workspace/_content.html`. Now the trigger reads `hx-trigger="load, intersect once, ..."`. `load` fires the moment HTMX processes the element (works for initial page load AND dynamically-added cards via addCard); `intersect once` stays as fallback for cards scrolling in from off-screen. The responsibility moved from brittle JS kickoff code back to HTMX, where it belongs.
- Simplified `addCard` in `dashboard-builder.js` accordingly — it now just calls `htmx.process(cardEl)` in a single `$nextTick` and lets the declarative trigger do the work. Removed the double-nextTick + bodyEl lookup + direct-URL-construction code that spent three cycles failing to work correctly.

### Pending
- **#797 (card_drag) still red** — harness reports `dx=0 dy=0` under scripted gestures. Dedicated cycle needed to diagnose the Alpine proxy + pointermove dispatch path. Setting that aside as out of autonomous-cycle scope and parking it for focused investigation.

## [0.57.59] - 2026-04-18

### Fixed
- **Second root-cause pass on #798 (Add-Card region fetch).** v0.57.58's CI walk confirmed the v0.57.46 fix didn't actually land the region fetch — `body_length=13` (skeleton text) and `region_fetch_count=0` on every run. Two fixes:
  1. **Double `$nextTick`**: the first tick lets Alpine expand the `<template x-for>` to produce the new `[data-card-id]` + its inner region body. The second tick guarantees `:id` / `:hx-get` bindings have actually been evaluated and written to the DOM. Single-tick was finding `cardEl` but not necessarily completing all attribute bindings.
  2. **Direct URL construction**: don't read `bodyEl.getAttribute("hx-get")` (which races Alpine's binding evaluation). Construct the URL from `this.workspaceName + regionName` directly and target the body via its known id `region-{region}-{card_id}`. The kickoff is now independent of Alpine's render timing.
- Evidence dump in `CardAddInteraction`: on a region-fetch-miss, the walk now reports up to 10 captured URLs containing `/api/` or `/regions/` in its evidence, so CI logs distinguish "fetch to wrong path" from "no fetch at all" without needing another diagnostic cycle.

### Pending
- **#797 (card_drag) remains red.** v0.57.46's defensive fixes (listener-install ordering, top-level drag-state reassignment) didn't resolve it — the harness still reports `dx=0 dy=0` under real pointer gestures. Needs deeper investigation of the Alpine proxy + pointermove dispatch path; deferred to a dedicated cycle.

## [0.57.58] - 2026-04-18

### Fixed
- **`CardAddInteraction`: Alpine-race on picker entry + false-positive new-card detection.** First real interaction-walk run on CI (v0.57.57) revealed two bugs in the walk itself:
  1. Clicking "Add Card" flips Alpine's `showPicker` flag but the picker entries are inside `<template x-for>` that Alpine needs a tick to render. The walk was clicking the entry before it existed, so the click no-op'd. Replaced the immediate click with `page.wait_for_selector(entry_selector, state="visible", timeout=5000)` followed by the click — Alpine has time to render the picker and attach @click handlers before we hit it.
  2. The walk identified the "new" card by taking `max()` over all `[data-card-id]` attributes. If the picker click didn't actually add a card (e.g., the pre-fix Alpine race), `max()` returned an existing card's id and the walk silently reported that card's state as the "new" one — false-positive when the Add flow is actually broken. Now the walk snapshots existing card ids BEFORE the click and diffs against the post-click set. Empty diff → report "picker click didn't add a new card" with before/after card lists in evidence.
- `test_interaction_walks.py` updated: tests now provide pre-click + post-click `evaluate()` returns so the diff logic has something to work with. `_StubPage` gains a `wait_for_selector` stub.

### Known regressions surfaced by the harness
- **#797 (card_drag) still broken**: first real walk run reported `dx=0 dy=0 requested_dy=200` against the live dashboard. The defensive fixes in v0.57.46 (listener install ordering + top-level `this.drag = nextDrag` reassignment) didn't fully resolve the drag lifecycle regression. The harness is now the authoritative signal — a follow-up cycle needs deeper investigation of why the pointermove listener isn't dispatching through the Alpine proxy.
- **#798 (card_add) pending verification**: with v0.57.58's race fix in place, the next CI run should show whether the v0.57.46 addCard htmx.ajax kickoff fix actually worked, or whether the region-fetch gap is still real.

## [0.57.57] - 2026-04-18

### Fixed
- **INTERACTION_WALK: pass X-Test-Secret to /__test__/authenticate.** v0.57.56's diagnostics pinpointed the auth failure: `/__test__/authenticate returned HTTP 403 (body: '{"detail":"Invalid or missing X-Test-Secret header"}')`. The endpoint requires the per-run secret that `dazzle serve` generates in test mode (#790). `HtmxClient.authenticate` already reads `DAZZLE_TEST_SECRET` from env, but our harness was running in the same process as `launch_interaction_server` where that env var is set ONLY inside the subprocess.
- `run_interaction_walk` now reads the secret from the server's `runtime.json` via `read_runtime_test_secret(project_root)` (the helper added in #790) and passes it as `test_secret` to `_authenticate_persona_on_context`. The helper attaches the `X-Test-Secret` header on the POST to `/__test__/authenticate`. Diagnostic messages retained so any future auth-path change surfaces with a clear signal rather than a generic "no cards" error.

## [0.57.56] - 2026-04-18

### Changed
- **INTERACTION_WALK: actionable diagnostics on setup failure.** v0.57.55 fixed the auth-order bug but the harness still fails with the same generic "No interactions to run" on CI — and the log tells us nothing about which failure mode we're in. Added stderr output on both failure paths:
  - `_authenticate_persona_on_context` now logs HTTP status + body snippet when `/__test__/authenticate` returns non-200, logs the exception when the request itself fails, and logs the response-body keys when 200 is returned but no `session_token` is present.
  - The "No interactions to run" branch dumps `current URL`, `page title`, whether `#dz-workspace-layout` is present, and the actual `cards` + `catalog` lists from the layout JSON (if any). Decision tree in the message body maps each observed state to the actual root cause — /login means auth failed; no JSON means template didn't render; empty JSON means workspace has no regions or user has no default layout.
- Pure diagnostics — no behavioural change. Next CI run will reveal which of the three failure modes the harness is actually hitting so we can fix the real cause rather than guess.

## [0.57.55] - 2026-04-18

### Fixed
- **INTERACTION_WALK: authenticate on the browser context BEFORE first navigation.** Third CI pass of `interaction-walks` (v0.57.54) got past the TCP race but reported "No interactions to run — the workspace has no cards and no catalog entries." on all 3 attempts. Root cause: the harness navigated to `/app` first, got redirected to `/login` (auth gate), authenticated AFTER that, then called `page.reload()` — but the reload happened on `/login`, not on `/app`. So when the layout-JSON extractor ran, it was looking at the login page, not a workspace.
- Renamed `_authenticate_persona(page, ...)` to `_authenticate_persona_on_context(context, ...)` and moved the call to BEFORE `page.goto("/app")`. The session cookie is now installed on the `BrowserContext` before any navigation, so the first `goto` lands on the authenticated dashboard with the cards JSON already in the DOM.
- CI workflow now passes `--persona agent` — `support_tickets`'s agent persona lands on `ticket_queue`, which is the canonical cards-populated workspace for the harness.

## [0.57.54] - 2026-04-18

### Fixed
- **INTERACTION_WALK server fixture: add TCP-ready probe.** Second CI run of `interaction-walks` (v0.57.53) got past the playwright install but hit `Page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:<port>/app` on all 3 retry attempts. Root cause: `launch_interaction_server` polled for `.dazzle/runtime.json` to appear, then yielded — but the server writes that file slightly before uvicorn finishes binding to the port. Playwright's `page.goto()` raced the uvicorn bind and lost.
- Added `_wait_for_server_ready(site_url, timeout)` in `src/dazzle/testing/ux/interactions/server_fixture.py` that polls the site URL via `httpx.Client` until any response < 500 is received (2xx/3xx/4xx all count as "listening"; 5xx means a real server issue). Runs after `_wait_for_runtime_file` succeeds, before yielding the `AppConnection`. 30s timeout, 300ms poll interval. Raises `InteractionServerError` on timeout (exit code 2 in the CLI — distinguishable from test regressions).
- 3 regression tests in `tests/unit/test_interaction_server_fixture.py::TestServerReadinessProbe` pin the behaviour: returns on 200, returns on 403 (auth redirect counts), raises on timeout when every connect refuses. The existing tests (which don't bind a real TCP port) autouse-stub the probe to a no-op so they don't hang.

## [0.57.53] - 2026-04-18

### Fixed
- **INTERACTION_WALK CI job: install playwright.** The first CI run of the `interaction-walks` job in v0.57.52 failed at "Install Playwright chromium" with `No module named playwright` — the existing `.[dev,llm,mcp,mobile,postgres]` install doesn't pull playwright in. Added an explicit `pip install "playwright>=1.40"` before the chromium install. Pin at 1.40+ for the sync-API shape our harness uses. A follow-up might promote this to a proper `e2e` extra in `pyproject.toml` once the harness is blocking.

## [0.57.52] - 2026-04-18

### Added
- **Non-blocking CI job for INTERACTION_WALK (step 6 of #800).** New `interaction-walks` job in `.github/workflows/ci.yml` spins up a Postgres service, installs Playwright chromium, and runs `dazzle ux verify --interactions --headless` from `examples/support_tickets` with a shell-level retry loop (up to 3 attempts, 5s backoff) to absorb Playwright-over-HTMX flake. `continue-on-error: true` so early-signal noise doesn't red the build — this stays on for the signal-gathering window, then ratchets to blocking per step 7 of the design doc. Timeout: 8 minutes per attempt.

### Agent Guidance
- **Interaction-walk flakes in CI are expected early.** The `continue-on-error: true` guard is load-bearing during the signal-gathering window — don't remove it to chase a single red run. After 2–3 weeks of data (step 7), evaluate the flake rate and ratchet to blocking by flipping the flag.
- **Adding a new walk**: the CI job drives `dazzle ux verify --interactions` which picks the first card + first catalog region (see `_build_default_walk` in `cli/ux_interactions.py`). New walks get exercised automatically as long as they register themselves via the default-walk builder. No CI edit needed for new walk types.

## [0.57.51] - 2026-04-18

### Added
- **`dazzle ux verify --interactions` CLI flag (step 5 of #800).** New peer flag alongside `--contracts` and `--browser` that runs the INTERACTION_WALK harness against the current project. Spawns a dedicated `dazzle serve --local` via the session fixture from v0.57.49, opens a sync Playwright browser, navigates to `/app`, extracts the workspace layout from the embedded `#dz-workspace-layout` JSON, builds a default walk (`CardRemoveReachableInteraction` + `CardDragInteraction` + `CardAddInteraction` targeting the first available card/region), runs via `run_walk`, and emits a human or JSON report. Exit codes: 0 pass / 1 interaction regression / 2 setup failure (Playwright missing, server won't start, empty layout), as specified in the design doc.
- Plumbing lives in `src/dazzle/cli/ux_interactions.py` — extracted from `ux.py` so pure functions (`_build_default_walk`, `_render_human_report`, `_render_json_report`) are independently testable. 10 unit tests in `tests/unit/test_cli_ux_interactions.py` cover walk assembly under all layout permutations (cards + catalog, cards only, catalog only, empty), report rendering for pass/fail/mixed, and the exit-code constants.

### Agent Guidance
- **Running the harness**: `cd examples/support_tickets && dazzle ux verify --interactions` from a machine with Postgres + Redis running (the `--local` flag on `dazzle serve` still requires those). The CLI handles server spawn + teardown; don't pre-start the server.
- **Interaction exit codes are gate-stable**: CI workflows should branch on `rc == 2` (setup failure → retry) vs `rc == 1` (real regression → fail the build) separately. The constants live in `dazzle.cli.ux_interactions` (`EXIT_PASS`, `EXIT_REGRESSION`, `EXIT_SETUP_FAILURE`).

## [0.57.50] - 2026-04-18

### Added
- **Three v1 INTERACTION_WALK walks (step 4 of #800).** Each closes a specific regression class at the interaction level, targeting the bugs AegisMark reported in #797/#798/#799:
  - **`CardRemoveReachableInteraction`** (`card_remove_reachable.py`) — focuses a card, Tabs forward up to 15 times looking for `[data-test-id="dz-card-remove"]`, asserts the focused button's computed opacity is ≥ 0.2. Complements the static INV-9 gate (`find_hidden_primary_actions`) by verifying the invariant survives to runtime.
  - **`CardDragInteraction`** (`card_drag.py`) — pointerdown on `[data-test-id="dz-card-drag-handle"]`, move `dy` pixels in configurable steps, pointerup. Asserts the card's bounding-box delta is ≥ 5px. Catches #797's silent "drag gesture completes but card doesn't move" regression.
  - **`CardAddInteraction`** (`card_add.py`) — click `[data-test-id="dz-add-card-trigger"]`, click the picker entry `[data-test-region="<region>"]`, watch network requests, assert the new card's body has substantive text (≥40 chars) AND a GET against `/regions/<region>` fired. Catches #798's "skeleton but no fetch" regression which wouldn't show up in any static gate.
- 11 unit tests in `tests/unit/test_interaction_walks.py` verify each walk's logic against a minimal `_StubPage` without booting Playwright: opacity thresholds, never-reachable edge case, bbox-delta pass/fail, missing card, body-populated + fetch-observed pass, skeleton-only fail, no-fetch fail, unclickable trigger, missing picker entry. Real-browser integration comes next via the e2e mark + the server fixture from v0.57.49.

### Agent Guidance
- **Writing a new walk**: drop a new file in `src/dazzle/testing/ux/interactions/` with a dataclass that implements the `Interaction` protocol. Return `InteractionResult(passed=False, reason=...)` on assertion failure; raise only on catastrophic setup problems (page closed, timeouts). Prefer `[data-test-id="dz-<thing>"]` selectors — they're the test ABI.
- **Evidence dict in `InteractionResult`** is where you pin the observed state so a failing run is diagnosable without reproducing locally. The three v1 walks pin `opacity`, `tab_steps`, `dx`/`dy`, `new_card_id`, `body_length`, `region_fetch_count`. Keep evidence focused — don't dump the whole DOM.

## [0.57.49] - 2026-04-18

### Added
- **INTERACTION_WALK server fixture (step 3 of #800).** New `launch_interaction_server(project_root)` context manager in `src/dazzle/testing/ux/interactions/server_fixture.py` spawns `python -m dazzle serve --local` as a subprocess, polls for `.dazzle/runtime.json`, and yields a live `AppConnection`. Clears stale runtime.json before launch, terminates the subprocess on context exit, raises a distinct `InteractionServerError` on startup timeout so the CLI can distinguish setup failures (exit 2) from regressions (exit 1).
- 7 unit tests in `tests/unit/test_interaction_server_fixture.py` pin the lifecycle without booting a real server: project validation, runtime-file polling + timeout, stale-file cleanup, exception-safe teardown, runtime-file cleanup on exit, already-dead-process handling.

### Agent Guidance
- **Interaction tests run against a live server** — spawn it via `launch_interaction_server(project_root)`. Don't call `subprocess.Popen` directly; the fixture handles stale-file cleanup, process-group termination, and the `.dazzle/runtime.json` protocol that `dazzle serve` writes.
- **Don't confuse this with `ModeRunner`.** `dazzle.e2e.runner.ModeRunner` is the async, lock-file-guarded, DB-policy-aware launcher used by the fitness runs. `launch_interaction_server` is the sync, minimal variant for the browser harness. Both target the same `AppConnection` type so changes to how `dazzle serve` exposes URLs propagate to both.

## [0.57.48] - 2026-04-18

### Added
- **INTERACTION_WALK foundations (steps 1–2 of the design doc, #800).** Two commits of scaffolding ahead of the live-browser walks:
  - **Stable test selectors on the workspace template.** Added `data-test-id="dz-card-drag-handle"`, `data-test-id="dz-card-remove"`, `data-test-id="dz-add-card-trigger"` to `workspace/_content.html`, plus `data-test-id="dz-card-picker-entry"` + a dynamic `:data-test-region="item.name"` on each picker entry in `_card_picker.html`. These are the stable ABI the interaction harness will target — user-facing copy (`"Add Card"`, `"Remove card"`, region titles) stays free to change.
  - **`Interaction` protocol + `InteractionResult` + `run_walk`.** New `src/dazzle/testing/ux/interactions/` package with `base.py` exposing the runtime-checkable `Interaction` protocol, a dataclass `InteractionResult` (name, passed, reason, evidence), and a minimal `run_walk(page, walk)` executor. A walk is just `list[Interaction]` — no registry, no magic. Later walks (card_drag, card_add, card_remove_reachable) drop in as new files in the package. 8 unit tests pin the protocol semantics, composition order, failure non-short-circuit, and genuine-error propagation; none touch Playwright.

### Agent Guidance
- **Adding a new interaction walk**: create `src/dazzle/testing/ux/interactions/<name>.py` with a dataclass implementing `Interaction`. Keep all gesture + assertion logic inside `execute(page)`. Return `InteractionResult(passed=False, reason=...)` on assertion failure — never raise. Only raise when something catastrophic prevents the interaction from running at all (page closed, selector times out, etc.).
- **Test selectors on workspace templates** (`data-test-id="dz-*"`) are the harness ABI — rename or remove only if the corresponding interaction in `src/dazzle/testing/ux/interactions/` is also updated in the same commit.

## [0.57.47] - 2026-04-18

### Added
- **INV-9: Primary actions must be reachable without pointer hover.** New `find_hidden_primary_actions(html)` scanner in `src/dazzle/testing/ux/contract_checker.py` flags buttons (or `<a role="button">`) whose `aria-label` matches `Remove|Delete|Dismiss|Close|Archive|Unarchive|Disable|Deactivate|Revoke` and which live inside an `opacity-0 group-hover:opacity-100` ancestor (or equivalent) without a non-hover reveal (`focus-within:opacity-*`, `focus:opacity-*`, etc.). Alpine-conditional ancestors (`x-show`/`x-if`/`x-cloak`) are treated as orchestrated reveals and skipped. Wired into `check_contract` for `WorkspaceContract` and `DetailViewContract` — same dispatch point as INV-1 and INV-2. Catches exactly the #799 pattern that reached production before v0.57.46's hand-fix.
- 10 regression tests in `tests/unit/test_ux_contract_checker.py::TestFindHiddenPrimaryActions` covering: opacity-0 hover-only detection, focus-within reveal, always-visible, Alpine modal skip, non-primary-action labels, link-button role, missing aria-label, button-level opacity-0, post-v0.57.46 fix shape (confirms our fix passes the gate), and multiple hidden actions.
- `docs/reference/card-safety-invariants.md` extended with INV-9 section (rule, why, enforcement, bad/good shapes, notes on Alpine skip and non-primary labels). Meta-test `test_card_safety_invariants.py` registers 3 INV-9 enforcers.

### Agent Guidance
- **When adding a destructive/state-changing button** (Remove/Delete/Dismiss/…), don't wrap it in `opacity-0 group-hover:opacity-100`. Either keep it always visible (optionally low-opacity at rest, e.g. `opacity-60`), or add a focus-within reveal alongside the hover reveal. INV-9 is now CI-enforced — the contract checker fails the build on workspace or detail-view renders with hover-only primary actions.

### Closes
- Closes proposal issue #801.

## [0.57.46] - 2026-04-18

### Fixed
- **Workspace dashboard: drag-and-drop doesn't move cards (#797).** Two likely root causes addressed:
  1. **Silent listener-install skip in `init()`.** The dashboard-builder component's `init()` used to return early if the `#dz-workspace-layout` script tag was missing or its JSON was malformed — BEFORE the keyboard and pointer listeners were registered. Any edge case in the layout payload would silently disable drag/keyboard interaction. Reordered so listeners always install; JSON parse failure now leaves listeners in place.
  2. **Nested-property mutation may miss Alpine's effect tree.** `onPointerMoveDrag` used to mutate `this.drag.currentX`, `this.drag.currentY`, `this.drag.phase` in-place. The `:style="isDragging(card.id) ? dragTransform(card.id) : _colSpanClass(card.col_span)"` binding re-evaluates via `dragTransform`, which reads `this.drag.currentX/currentY`. In some Alpine configurations deep-proxy reactivity doesn't propagate cleanly through multiple nested reads — rewrote the handler to build a new `drag` object and assign via top-level `this.drag = nextDrag`, so the effect tree always sees the change.
- **Workspace dashboard: 'Add Card' renders skeleton without firing region data fetch (#798).** The newly-appended card body uses `hx-trigger="intersect once"`, which only fires on viewport-entry events — a freshly-added card that's already in the viewport never triggers the fetch. `addCard` now imperatively fires the region fetch via `htmx.ajax('GET', url, {target, swap})` after `htmx.process()` has registered the hx-* attrs.
- **Workspace dashboard: remove-card button invisible on touch + hard to reach by keyboard (#799).** Changed the action cluster from `opacity-0 group-hover:opacity-100` to `opacity-60 group-hover:opacity-100 group-focus-within:opacity-100` — the X remains discoverable at rest (touch + keyboard users can see it), fades up on hover or focus-within.

### Agent Guidance
- **Dashboard-builder listener lifecycle**: register pointer/keyboard listeners BEFORE the layout-JSON parse in `init()`. Listener installation should be lifecycle-driven, not data-driven — decoupling them avoids silent-skip bugs.
- **Alpine reactivity**: for state objects whose nested properties drive bindings (e.g. drag/resize state driving `:style`), prefer top-level reassignment (`this.state = { ...this.state, ...patch }`) over nested mutation. It's a one-line-longer write but guarantees the effect tree sees the change.
- **HTMX dynamically-added elements**: calling `htmx.process(el)` registers the hx-* attributes but does NOT trigger `intersect once`. If the element is already in the viewport when added, imperatively fire the fetch via `htmx.ajax()` — the intersect-once trigger is one-shot and is designed for elements that enter the viewport, not for elements that arrive already inside it.

## [0.57.45] - 2026-04-18

### Added
- **DOM snapshot baselines for the dashboard-slot + region composite.** New `tests/unit/test_dom_snapshots.py` uses pytest-syrupy to capture a byte-level baseline for each of the 13 region composites (grid, list, timeline, kanban, bar_chart, funnel_chart, queue, metrics, heatmap, progress, tree, diagram, tabbed_list). Any byte change to the rendered output fails the test — complements the shape-nesting and duplicate-title gates which only catch specific known-bad patterns. Baselines in `tests/unit/__snapshots__/test_dom_snapshots.ambr`. Regenerate on intentional change with `pytest tests/unit/test_dom_snapshots.py --snapshot-update`.

### Agent Guidance
- **When editing a region template**, expect the snapshot test for that region to fail and update the baseline in the same commit. Review the diff in `tests/unit/__snapshots__/test_dom_snapshots.ambr` before committing — if you didn't intend the structural change, fix the template instead of the baseline.
- **New region?** Add it to `_REGION_CASES` in `test_template_html.py` (the matrix is shared with the shape gates) and run `pytest tests/unit/test_dom_snapshots.py --snapshot-update` once to seed the baseline.

### Note on #94
- This partially closes backlog item #94 ("deterministic pixel/DOM snapshot gate"). The full Playwright/pixel variant remains deferred — it needs headless-browser CI infra that doesn't fit an autonomous cycle. The DOM baselines here catch most visual regressions we care about (card-in-card, removed buttons, tag changes, class changes) at the cost of missing pure CSS-only regressions. Most regressions that matter go through structural changes and show up in the DOM.

## [0.57.44] - 2026-04-18

### Added
- **`dazzle sweep examples` CLI.** Unified health check across every project under `examples/*/` that has a `dazzle.toml`. Runs `dazzle validate` and `dazzle lint` per app, snapshots framework-artefact coverage for the repo as a whole, and emits a single report. Supports `--json` for machine consumption and `--strict` to treat lint warnings as failures. Exit codes: 0 clean, 1 validate/lint error (or any warning under `--strict`), 2 fatal setup problem. Intended cadence: weekly, or after a parser/runtime change that might regress example health. 8 unit tests in `tests/unit/test_cli_sweep.py` cover lint parsing, human/JSON renderers, and end-to-end runs against the real `examples/` tree.

### Agent Guidance
- **`sweep examples` is the single invocation** for "is every example app still healthy?". Prefer it over scripting `for app in examples/*/; do dazzle validate && dazzle lint; done` — the sweep command has stable output for diffing between runs, includes the coverage snapshot, and returns a single exit code you can gate CI on.

## [0.57.43] - 2026-04-18

### Added
- **Canonical card-safety invariants spec.** New `docs/reference/card-safety-invariants.md` enumerates the 8 invariants that define "a card" in Dazzle templates and the regressions each one prevents:
  - INV-1: No nested card chrome
  - INV-2: No duplicate title within a card
  - INV-3: Side borders are accents, not card edges
  - INV-4: Bg-only rounded is not chrome
  - INV-5: Inline tags are never cards
  - INV-6: Region templates emit zero chrome
  - INV-7: Region templates emit zero title
  - INV-8: Tests must run on the composite, not the layers
- **Drift-proof spec-to-test mapping.** New `tests/unit/test_card_safety_invariants.py` pins each invariant to at least one named enforcing test (e.g., INV-1 → `TestFindNestedChromes::test_detects_rounded_plus_border_nested` + `TestDashboardRegionCompositeShapes::test_composite_has_no_nested_chrome`). If a referenced test is renamed, the meta-test fails with a pointer at the stale name. File-grep based — no dynamic imports, no user-input paths.
- **CLAUDE.md UI Invariants section.** New top-level pointer under Ship Discipline so agents touching templates, regions, or scanners know the spec exists before they start.

### Fixed
- **Parser: `auth_profile` with unknown kind now raises ParseError instead of crashing.** Pre-existing bug surfaced by the `test_swap_adjacent_mutation` fuzz test (`seed=2755`): `auth_profile: header` would raise `ValueError: 'header' is not a valid AuthKind` from deep inside `AuthKind(value)`. Wrapped the conversion with `try/except ValueError` and raise a clear `ParseError` naming the invalid kind and listing the valid options.

### Agent Guidance
- **When touching region templates, the `region_card` macro, or the shape scanners**, read `docs/reference/card-safety-invariants.md` first. Each of the 8 invariants lists the test that enforces it; if you're tempted to change one of the invariants, update the spec and the test in the same commit.
- **Adding a new card-safety invariant**: name it (INV-N), add a section to the spec, register at least one enforcing test in `INVARIANT_ENFORCERS` inside `test_card_safety_invariants.py`. Ship with the spec, test, and scanner tightening together.

## [0.57.42] - 2026-04-18

### Added
- **Workspace composite fetch for `dazzle ux verify --contracts`.** New `HtmxClient.get_workspace_composite(path)` follows the HTMX boot sequence: fetches the initial workspace page, parses the embedded `#dz-workspace-layout` JSON for the card/region list, issues a per-region GET against `/api/workspaces/{ws}/regions/{region}`, and stitches the region HTML back into each card body slot. Returns the DOM a user actually sees post-hydration — the correct input for the shape-nesting + duplicate-title gates that already run inside `check_contract`. Wired in `src/dazzle/cli/ux.py` so `WorkspaceContract` instances route through the composite path; list/detail/RBAC contracts continue to use `get_full_page` (they don't have HTMX follow-ups).
- **Pure-function assembler for unit tests.** `assemble_workspace_composite(initial_html, region_htmls)` in `src/dazzle/testing/ux/htmx_client.py` is a string-substitution helper that can run without a live server. 8 tests in `tests/unit/test_htmx_workspace_composite.py` pin: layout JSON extraction, card-slot substitution, HTMX wrapper-attribute preservation, missing-region graceful skeleton retention, and end-to-end that the scanner flags a bad composite but passes a clean one.

### Changed
- `src/dazzle/testing/ux/htmx_client.py` module docstring now explicitly documents the distinction between `get_full_page` (initial HTML, skeleton-only for workspaces) and `get_workspace_composite` (post-hydration DOM). Before v0.57.42 this was undocumented, and the contract checker's use of the former was why the #794 card-in-card survived three fix attempts.

### Agent Guidance
- **Workspace-level contracts need the composite.** When writing a new `WorkspaceContract` or extending the workspace checker, always drive it from `get_workspace_composite`, not `get_full_page`. The initial page contains an empty skeleton where the region will land; without fetching the HTMX follow-up, any assertion about the card's rendered content tests nothing.
- **Non-workspace contracts stay on `get_full_page`.** List pages, detail views, and create/edit forms render fully server-side (they don't boot a dashboard or HTMX-swap the main content slot). Using the composite path for them wastes a round-trip and doesn't change the result.

## [0.57.41] - 2026-04-17

### Added
- **Docs-vs-parser drift gate.** New `tests/unit/test_docs_drift.py` asserts every DSL construct named in `.claude/CLAUDE.md`'s `**Constructs**:` line actually exists in the parser's top-level dispatch table (`src/dazzle/core/dsl_parser_impl/__init__.py`). A companion test does the same for `dazzle.cli.coverage._DSL_CONSTRUCTS`. One-way gate — the parser can dispatch on more constructs than the quick-ref mentions, but anything the docs claim must be real. Directly addresses the blind spot the coverage-list curation cycle surfaced: `CLAUDE.md` had been naming `view`, `graph_edge`, and `graph_node` as top-level constructs when they're actually sub-keywords.

### Fixed
- **CLAUDE.md DSL construct list.** Removed stale `view` (it's a sub-keyword inside `flow`, not a top-level construct). Added an explanatory parenthetical enumerating the additional parser-dispatchable keywords (`app`, `test`, `flow`, `rule`, `message`, `channel`, `asset`, `document`, `template`, `demo`, `event_model`, `subscribe`, `project`, `stream`, `hless`, `policies`, `tenancy`, `interfaces`, `data_products`, `llm_model`, `llm_config`, `llm_intent`, `notification`, `grant_schema`, `param`, `question`) so readers know the quick-ref is curated, not exhaustive.

### Agent Guidance
- **When adding to CLAUDE.md's Constructs line**, verify the name exists in the parser's dispatch table before committing. The drift test will fail CI otherwise. Parser authoritative source: `src/dazzle/core/dsl_parser_impl/__init__.py` lines 579–625.

## [0.57.40] - 2026-04-17

### Changed
- **Honest fragment coverage: 19/19 (not the misleading 31/31).** Audit of the 15 parking-lot fragments registered in `FRAGMENT_REGISTRY` in v0.57.35 revealed that 12 had zero runtime call sites — they were counted as "covered" purely because the scanner was matching their names inside `fragment_registry.py` itself. Only `detail_fields`, `select_result`, and `table_sentinel` had real Python renderers. Two fixes restored honesty:
  1. The coverage scanner now excludes `fragment_registry.py` from the search — enumeration is not rendering.
  2. A new `PARKING_LOT_FRAGMENTS` frozenset in `src/dazzle_ui/runtime/fragment_registry.py` lists the 12 opt-in primitives (accordion, alert_banner, breadcrumbs, command_palette, context_menu, popover, skeleton_patterns, slide_over, steps_indicator, toast, toggle_group, tooltip_rich). The coverage tool excludes these from the denominator so the metric reflects only fragments the framework actually renders.
- Overall coverage moves from 71/71 (partially gamed) to **59/59 (honest)**. Category breakdown: display_modes 17/17, dsl_constructs 23/23, fragment_templates 19/19. The CI gate established in v0.57.39 continues to pass because nothing falsely counted has landed between then and now.

### Added
- 3 regression tests in `tests/unit/test_cli_coverage.py`:
  - `test_parking_lot_fragments_are_excluded_from_coverage` — pins that parking-lot names never appear in the coverage map.
  - `test_every_counted_fragment_has_a_real_caller` — pins that everything counted has a real include/render site.
  - `test_registry_enumerates_parking_lot_fragments` — pins that PARKING_LOT_FRAGMENTS and FRAGMENT_REGISTRY stay in sync.

### Agent Guidance
- **Adding a new fragment**: if it has a real include site or Python `render_fragment()` call, just add it to `FRAGMENT_REGISTRY` and CI counts it. If it's a parking-lot primitive (canonical renderer for downstream consumers to opt into, no default call site), add it to `FRAGMENT_REGISTRY` AND to `PARKING_LOT_FRAGMENTS`. When a parking-lot fragment gains a real include site, remove it from `PARKING_LOT_FRAGMENTS` — the coverage gate will then enforce that it stays rendered.

## [0.57.39] - 2026-04-17

### Added
- **CI gate on framework-artefact coverage.** New step in `.github/workflows/ci.yml` (lint job) runs `python -m dazzle coverage --fail-on-uncovered` on every push and PR. Locks the 71/71 (100%) invariant established in v0.57.35 — any new DSL construct, DisplayMode value, or fragment template landing without at least one example-app consumer fails the build. Negative path already pinned by `test_fail_on_uncovered_returns_nonzero_when_gaps_exist` in `tests/unit/test_cli_coverage.py`.

### Agent Guidance
- **Adding a new DSL construct / DisplayMode / fragment template is a two-step commit.** Ship the framework change AND a consuming DSL block in an example app in the same PR. Otherwise the coverage gate blocks merge. Curated construct list lives at `src/dazzle/cli/coverage.py::_DSL_CONSTRUCTS`.

## [0.57.38] - 2026-04-17

### Added
- **Duplicate-title gate on the HTMX-loaded dashboard composite.** New `find_duplicate_titles_in_cards(html)` in `src/dazzle/testing/ux/contract_checker.py` walks the DOM and, for each card container (elements with `data-card-id` or card chrome), flags any heading text (`<h1>..<h6>`) that appears more than once. Directly addresses AegisMark's second #794 counter — `page.get_by_text("Grade Distribution").count() == 3`. Wired into `TestDashboardRegionCompositeShapes.test_composite_has_no_duplicate_titles` which parametrises across the same 14 region cases as the chrome gate. 7 scanner-level regression tests in `test_ux_contract_checker.py`.

### Fixed
- **Three more title duplications caught by the new gate.** On first run the composite + duplicate-title gate surfaced three regions still emitting `<h3>{{ title }}</h3>` themselves, creating duplicates in the dashboard slot:
  - `workspace/regions/list.html`: header row had `<h3>{{ title }}</h3>` + CSV/region-actions. Stripped the title; actions float right.
  - `workspace/regions/queue.html`: header row had `<h3>{{ title }}</h3>` + total badge. Stripped the title; total badge floats right when > 0.
  - `workspace/regions/funnel_chart.html`: also still wrapped itself in `<div class="card bg-[hsl(var(--card))] shadow-sm">` (pre-region-card pattern) AND emitted `<h3>{{ title }}</h3>`. Converted to `{% call region_card(None) %}` and dropped the title — now consistent with every other region.

### Agent Guidance
- **Regions must not render their own title.** The dashboard slot owns it. Adding a `<h3>{{ title }}</h3>` to a region template triggers the composite duplicate-title gate. If a region needs secondary structure (action row, count badge, filter bar), render those without a `<h3>` containing the region's title.

## [0.57.37] - 2026-04-17

### Added
- **Composite shape gate for the HTMX-loaded dashboard.** New `TestDashboardRegionCompositeShapes` class in `tests/unit/test_template_html.py` simulates what a user actually sees: the dashboard card slot (from `workspace/_content.html`) concatenated with each rendered region template. Runs `find_nested_chromes` on the composite across 14 region cases (grid, list, timeline, kanban, bar_chart, metrics, queue, activity_feed, heatmap, progress, tree, diagram, tabbed_list, funnel_chart). Every prior test ran on each layer alone, which is why the #794 card-in-card was invisible for three fix attempts. Companion `test_dashboard_slot_fingerprint` ensures the hardcoded slot shell in the test stays in sync with `workspace/_content.html` — if it drifts, the fingerprint test fails and signals the test needs updating. Companion `test_bare_region_card_macro_stays_bare` locks #794's macro fix so a future edit can't silently re-introduce chrome.

### Fixed
- **Five more card-in-card regressions caught by the new composite gate.** Rolling the composite test against every region template surfaced the following still-latent stacking issues, which the isolated-template scanner never saw:
  - `workspace/regions/timeline.html`: timeline events had `rounded-[4px] border bg-[hsl(var(--background))]` — each event read as a small card inside the dashboard card. Stripped to `rounded-[4px]` with hover bg only.
  - `workspace/regions/metrics.html`: metric tiles had `rounded-[4px] bg-[hsl(var(--muted)/0.4)] border` — each tile read as a card. Stripped to tile with soft bg only, no border.
  - `workspace/regions/queue.html`: queue rows had a full `border border-[hsl(var(--border))]` — each row read as a card. Stripped to padded row; attention-state left-border accent preserved.
  - `workspace/regions/kanban.html` / `bar_chart.html`: scanner false positives — progress-bar tracks (`rounded-full bg-muted`) and kanban column backdrops (`rounded-[6px] bg-muted/0.4`) were being flagged as chrome. See scanner tightening below.

### Changed
- **Scanner: card chrome now requires a full border.** `_has_card_chrome` in `src/dazzle/testing/ux/contract_checker.py` previously flagged `rounded + (border OR bg-)` as chrome, which over-matched on decorative fills (progress tracks, kanban backdrops, filled pills). A card reads as a card because of its **edge**, not its fill. Tightened to `rounded + full border` (bg alone is no longer sufficient). Side-scoped borders (`border-l-*` accent stripes) are still excluded. Regression test `test_ignores_bg_only_rounded` pins the tightening.

### Agent Guidance
- **Region templates must not emit chrome.** The dashboard slot in `workspace/_content.html` owns card chrome and title. Any region template (or individual items within it — rows, tiles, events) that adds `border + rounded + bg` will read as a nested card. This is now CI-enforced by the composite shape gate. When adding a new region type: drop into `workspace/regions/<name>.html`, wrap the content in `{% call region_card(title) %}`, and render items as bare pads (rounded + padding + hover bg is fine; add a full border and the composite test fails).
- **When the composite gate flags a new failure**, the answer is almost always to strip the inner border/bg. A narrow exception: if the design genuinely calls for a card-inside-a-card (e.g., a surfaced alert within a dashboard region), make it explicit — add a `data-nested-card-intentional` attribute and tell the scanner to skip it.

## [0.57.36] - 2026-04-17

### Fixed
- **Root-cause fix for card-within-a-card (#794 second follow-up).** AegisMark's follow-up showed that the two prior fixes (2e9ca0cc outer wrapper + b5e3ef85 grid-item nesting) both missed the original reported shape: the dashboard card slot in `workspace/_content.html` emits its own chrome (`rounded-md border bg-[hsl(var(--card))]`) AND header title, while the `region_card` macro in `macros/region_wrapper.html` was also emitting chrome (`rounded-[6px] border bg-card shadow`) AND its own `<h3>` title. Every Dazzle dashboard region rendered with two card layers stacked and the same title printed twice. Since regions are only ever rendered into the dashboard slot (verified: single render site at `workspace_rendering.py:880`), the fix strips all chrome and title from `region_card` — it now emits only a bare `<div data-dz-region …>` as an instrumentation hook and delegates content to its caller. The dashboard slot continues to own chrome + title, as it always did.

### Changed
- `region_card(title, name)` signature preserved for caller compatibility, but `title` is now deliberately unused. All 16 region templates (grid, list, timeline, kanban, bar_chart, funnel_chart, queue, tabbed_list, heatmap, progress, activity_feed, tree, diagram, metrics, detail, map) inherit the fix without individual edits.

### Added
- Regression tests in `tests/unit/test_ux_contract_checker.py`: `test_dashboard_slot_plus_region_card_is_card_in_card` pins the AegisMark-reported shape as a known bad pattern; `test_dashboard_slot_with_bare_region_card_is_clean` pins the fixed shape. The shape-nesting scanner already detected this pair correctly — the gap was that Dazzle's own QA loop wasn't rendering the dashboard-slot + region-card composite, only individual region output.

### Agent Guidance
- **Regions are always dashboard-slot content.** Never add chrome (border, bg, rounded, shadow) or a `<h3>` title to a region template or `region_card`. The enclosing dashboard slot in `workspace/_content.html` owns all card surface. If a future surface type renders regions standalone (not in a dashboard), it should introduce its own wrapper — don't re-add chrome to the shared macro.

## [0.57.35] - 2026-04-17

### Added
- **Full framework-artefact coverage (71/71, 100%).** Second-pass fill-in on top of 0.57.34 — every DisplayMode value, top-level DSL construct, and fragment template now has at least one live consumer. Closing the long tail drove several targeted changes:
  - `support_tickets`: new top-level `enum Severity`, `sla TicketResponseTime`, `approval CriticalClose`, `webhook TicketNotify`, `rhythm agent_daily`, `island ticket_composer`, and `feedback_widget: enabled`.
  - `ops_dashboard`: new `service datadog`, `integration pager_duty`, `foreign_model DatadogMonitor`, and guided `experience incident_response` wizard across `alert_list → alert_detail → alert_ack`.
  - `fieldtest_hub`: new `ledger DeviceCost`/`OperationsBudget`, `transaction RecordRepair`, plus a `device_map` region that exercises the previously-blocked `display: map`.
- **15 parking-lot fragments registered.** Every canonical renderer under `templates/fragments/` (accordion, alert_banner, breadcrumbs, command_palette, context_menu, detail_fields, popover, select_result, skeleton_patterns, slide_over, steps_indicator, table_sentinel, toast, toggle_group, tooltip_rich) now has a `FRAGMENT_REGISTRY` entry so it's discoverable via `get_fragment_info()` and counted as live.

### Changed
- **`dazzle coverage` scanner broadened.** Now walks `src/dazzle_ui/`, `src/dazzle_back/`, and `src/dazzle/` — fragments rendered by backend routes (e.g. `select_result.html` from `fragment_routes.py`) are no longer falsely flagged as orphan. Header match now accepts `keyword:` as well as `keyword ` so config-style blocks like `feedback_widget: enabled` register. The curated construct list drops `view`, `graph_edge`, and `graph_node` — those are sub-keywords nested inside other constructs, not top-level dispatchable keywords, and were inflating the denominator with un-closable gaps.

### Fixed
- **Parser: `display: map` no longer rejected.** `TokenType.MAP` is now in `KEYWORD_AS_IDENTIFIER_TYPES`, so `map` is accepted as an identifier in value position (same treatment as `list`, `grid`, `timeline`, `detail`). The `map()` aggregate continues to parse as before — aggregate detection uses a separate path. This unblocks `DisplayMode.MAP` from being exercised in example DSL.

### Agent Guidance
- **Closing coverage gaps means wiring, not just documenting.** When a fragment is orphan, register it in `FRAGMENT_REGISTRY` (`src/dazzle_ui/runtime/fragment_registry.py`) so it's discoverable; that's a real integration point, not a cosmetic fix. When a DSL construct has zero example coverage, add it to the most natural example app — not a fixture under `fixtures/` — so it rides the live QA loop.
- **`dazzle coverage --fail-on-uncovered`** is ready as a CI gate. Once wired, it locks the "every shipped artefact has a live consumer" invariant — any new framework primitive must land with an example using it, or the build fails.

## [0.57.34] - 2026-04-17

### Added
- **`dazzle coverage` command.** Auditing tool that enumerates framework-provided artefacts (DisplayMode values, top-level DSL constructs, fragment templates) and reports which ones are exercised by at least one example app in `examples/*`. An uncovered artefact is one the framework ships but no example renders — which means no QA run hits its code path, and any regression stays hidden until a downstream consumer lands on it. Supports `--json` for machine consumption and `--fail-on-uncovered` as a CI gate. Regression tests in `tests/unit/test_cli_coverage.py` (10 cases). Starting coverage: **43/74 (58%)**; prior to this cycle: 33/74 (45%).
- **Coverage fill-in across three example apps.** Addresses the class of risk identified by the #794 follow-up (grid template shipped with no example consumer, card-in-card hidden from QA):
  - `ops_dashboard`: new `alert_severity_breakdown` (bar_chart), `alert_heatmap` (heatmap), `ack_queue` (queue), and `health_summary` now `display: metrics`.
  - `support_tickets/agent_dashboard`: new `comment_activity` (activity_feed), `resolution_funnel` (funnel_chart), `backlog_progress` (progress).
  - `fieldtest_hub/engineering_dashboard`: new `device_tree` (tree), `fleet_diagram` (diagram), `issue_tabs` (tabbed_list).
  - Net: **16 of 17 DisplayMode values now have a consuming example.** Only `map` remains — blocked because `map` is a reserved keyword in the DSL parser (collides with the `map()` aggregate). Tracked for a framework-level fix.

### Changed
- `dazzle coverage` strips DSL comments before artefact matching so a commented-out `display: <mode>` doesn't falsely count as covered.

## [0.57.33] - 2026-04-17

### Fixed
- **Root-cause fix for card-within-a-card (#794 follow-up).** The prior fix removed `rounded-md` from the dashboard-grid outer wrapper but missed the deeper source: `workspace/regions/grid.html` wrapped each inner item in `bg-[hsl(var(--card))] border rounded-[4px]` while the enclosing `region_card` macro already provided `bg-[hsl(var(--card))] border rounded-[6px]`. Two nested chrome layers on every grid region on every Dazzle dashboard. Item cells are now plain pads (rounded + padding + hover muted-bg, no border/card-bg). The attention-state left-border accent is preserved.

### Changed
- **Shape-nesting contract gate now catches the real patterns.** Three refinements in `dazzle.testing.ux.contract_checker`:
  - `_is_rounded_class` recognises arbitrary-value classes (`rounded-[4px]`, `rounded-t-[8px]`) and side-scoped forms in addition to Tailwind's fixed scale. The framework templates use `rounded-[6px]` / `rounded-[4px]`; the old gate silently passed them.
  - `_is_side_border_class` treats side-only borders (`border-l-4`, `border-t-[color]`) as accent lines rather than card surface. Attention-state stripes don't trigger the gate against their enclosing region card.
  - `_NestedChromeScanner` only flags block-level container tags (`div`, `article`, `section`, `aside`, `nav`, `main`, `header`, `footer`, `li`) as card candidates. Status-badge spans, form buttons, and table cells can legitimately carry rounded + bg without being "cards."

### Added
- **`ops_dashboard/command_center` now exercises `display: grid`.** None of the five example apps previously used the grid region, which is why the nested-chrome regression escaped QA. `system_status` is now a canonical grid region — the contract-checker + QA path now has a real target.
- **Template-level regression test.** `tests/unit/test_template_html.py::test_grid_region_does_not_nest_card_chrome` renders `workspace/regions/grid.html` with `region_card` and asserts zero nested chrome. Guards the root-cause fix from being unwound by future template edits.
- **Three new contract-checker cases** in `tests/unit/test_ux_contract_checker.py`: arbitrary-value rounded acceptance, side-border-as-accent exemption, and the fixed grid region's reference shape.

## [0.57.32] - 2026-04-17

### Added
- **`dazzle version` subcommand.** Mirrors the `--version` flag, with an additional `--full` option that appends machine-readable feature flags (`python_available: true`, `lsp_available: …`, `llm_available: …`). The subcommand shape is what most CLI conventions use (`npm version`, `docker version`, `git version`) and is what the homebrew-tap `validate-formula` workflow invokes (`dazzle version` and `dazzle version --full | grep -q "python_available"`). The existing `--version` flag still works. Regression tests in `tests/unit/test_cli_version.py` (7 cases).
- Refactored the version-printing logic into a shared `print_version_info(full=)` helper in `dazzle.cli.utils`; `version_callback` now delegates to it.

### Fixed
- Tap's `validate-formula` workflow (on `manwithacat/homebrew-tap`) now has a working `dazzle version` target — both the subcommand call and the `--full` grep will succeed.

## [0.57.31] - 2026-04-17

### Fixed
- Release CLI workflow's `update-homebrew` job now writes `dazzle mcp setup` (subcommand) into the generated formula's post-install step. The previous heredoc in `.github/workflows/release-cli.yml` still referenced the old hyphenated `dazzle mcp-setup`, which is what the tap repo was actually installing — `homebrew/dazzle.rb` in this repo is shadowed by that heredoc each release. Fixing the workflow is what actually propagates the command-shape correction to `manwithacat/homebrew-tap`.

## [0.57.30] - 2026-04-17

### Fixed
- Homebrew formula post-install step now calls `dazzle mcp setup` (subcommand) instead of the non-existent `dazzle mcp-setup` (hyphenated). Every `Validate Formula` run on `manwithacat/homebrew-tap` since the CLI restructure had been failing with `No such command 'mcp-setup'`. README updated to match.

## [0.57.29] - 2026-04-17

### Added
- **Shape-nesting gate in `dazzle ux verify --contracts`.** `WorkspaceContract` and `DetailViewContract` now additionally fail if the rendered HTML has a "card within a card" — a chrome layer (rounded + border/background) whose ancestor is another chrome layer. Exposes `find_nested_chromes(html)` helper in `dazzle.testing.ux.contract_checker`. Catches regressions like issue #794 automatically. Regression tests in `tests/unit/test_ux_contract_checker.py::TestNestedCardChrome` and `TestFindNestedChromes` (6 cases).
- **Console-error gate in `InteractionRunner._run_page_load`.** Any JS console error surfaced during page load or post-navigation settling now fails the interaction. Previously the listener was registered *after* `page.goto` (missing every load-time error) and its collected errors were never asserted — which is how issue #795 (Alpine scope ReferenceError on HTMX morph navigation) escaped QA. Regression tests in `tests/unit/test_ux_runner.py` (3 cases: pass / fail-on-error / ignore warnings+info).
- **Lint rule: nav-group icon consistency.** `dazzle lint` / `_lint_nav_group_icon_consistency` warns when a `nav_group` mixes items with and without `icon:`. Asked for in issue #796 as a follow-on. Regression tests in `tests/unit/test_lint_anti_patterns.py::TestNavGroupIconConsistency` (4 cases).
- **`/smells` check 1.8.** New regression check in `.claude/commands/smells.md` for declarative Alpine `@<event>.window` bindings in templates — each hit is a latent HTMX-morph lifecycle bug waiting to surface (root cause of issue #795).

### Fixed
- **Preventive fix: workspace dashboard drag/resize listeners.** `src/dazzle_ui/templates/workspace/_content.html` + `src/dazzle_ui/runtime/static/js/dashboard-builder.js`. Same `@pointermove.window`/`@pointerup.window` pattern as issue #795 (fixed in 007f779e for dzTable). Moved to imperative `addEventListener`/`removeEventListener` pairs in the dashboard component's `init()`/`destroy()`.

## [0.57.28] - 2026-04-17

### Fixed
- `LLMAPIClient` now sets `self.run_id: str` (UUID hex) in `__init__`. The `LlmClient` Protocol consumed by `dazzle.fitness.investigator.runner.run_investigation` declared `run_id` as required, but the concrete class never set it — any `dazzle fitness investigate --cluster CL-...` invocation crashed with `AttributeError: 'LLMAPIClient' object has no attribute 'run_id'` before reaching the LLM. Now it runs. Regression test in `tests/unit/test_llm_api_client.py::TestLLMAPIClientRunId`.

## [0.57.27] - 2026-04-17

### Changed
- Raised `_COMMAND_PALETTE_SURFACE_THRESHOLD` in `component_rules.check_component_relevance` from 5 to 20. There is no DSL-level way today to register a `command_palette` fragment, so the suggestion fired indefinitely on every app with ≥5 surfaces. At 20 the suggestion only appears for genuinely large apps (fieldtest_hub, 25 surfaces) where the payoff is undeniable; smaller apps get clean lint output instead. When fragment registration is designed, this threshold can drop back.

## [0.57.26] - 2026-04-17

### Fixed
- `DazzleBackendApp` now accepts an `extra_static_dirs: list[str | Path]` parameter. Paths passed here are prepended to the `/static` CombinedStaticFiles mount so consumer-owned static assets take priority over framework defaults. Resolves issue #793 (Penny Dreadful): consumer apps that mounted their own `/static` AFTER `.build()` were silently shadowed by DAZZLE's internal `/static` mount, and had to reach into `app.routes.insert(0, ...)` as a workaround. Consumers should now pass `extra_static_dirs=[PROJECT_ROOT / "static"]` instead of mounting manually.

### Agent Guidance
- When a consumer project has its own `static/` directory and embeds DAZZLE via `DazzleBackendApp`, pass it as `extra_static_dirs=[...]` — don't mount via `app.mount("/static", ...)` after `.build()` (that silently shadows DAZZLE's framework assets and vice versa depending on insertion order).

## [0.57.25] - 2026-04-17

### Fixed
- Timeline layout suggestion in `layout_rules.check_layout_relevance` now requires the entity to have at least one *event-bearing* date/datetime field — i.e. a date field without the `auto_add` or `auto_update` modifier. Previously every entity with a `created_at: datetime auto_add` (every Dazzle entity) triggered the "has date/datetime fields but no timeline workspace region" suggestion. Now the rule only fires for entities with domain-meaningful temporal fields (`due_date`, `triggered_at`, `logged_at`, `release_date`, etc.), dropping ~9 noise suggestions across the 5 example apps.

## [0.57.24] - 2026-04-17

### Fixed
- `_build_feedback_edit_surface` (linker) now emits the auto-generated FeedbackReport EDIT surface with three logical sections (`status`, `triage`, `relations`) instead of one 6-field section. This clears the multi-section-form lint warning on every feedback-enabled Dazzle app — the last remaining framework-generated multi-section-form noise.

## [0.57.23] - 2026-04-17

### Fixed
- Capability-discovery rules (`layout_rules.check_layout_relevance`, `component_rules.check_component_relevance`, `completeness_rules.check_completeness_relevance`) now skip framework-synthetic platform entities (`domain == "platform"` — SystemHealth, SystemMetric, DeployHistory, FeedbackReport, AIJob). These entities are code-generated and their workspaces (`_platform_admin`) are framework-owned, so the previous "has date/datetime fields but no timeline workspace region" / "has permissions but no surfaces" / "consider toggle group" suggestions fired on every Dazzle app regardless of what the app author declared. Workspaces whose name starts with `_platform_` are likewise excluded from the toggle-group suggestion.

## [0.57.22] - 2026-04-17

### Fixed
- Modeling anti-pattern lints (god entity, polymorphic key, soft-delete) now skip platform-domain entities. The framework-generated `FeedbackReport` with its 24 audit / triage / screenshot fields no longer warns "consider decomposing" on every feedback-enabled app — apps can't decompose a code-generated entity anyway.
- `_lint_graph_edge_suggestions` now requires the two (or more) ref fields to the same target to use graph-edge-shaped names (`source`, `target`, `from`, `to`, `parent`, `child`, `start`, `end`, `predecessor`, `successor` — matched per-token, underscore-delimited). Creator/assignee, requester/approver, owner/watcher patterns no longer trigger false "looks like a graph edge" suggestions on every Task / Ticket / IssueReport entity.

Combined: all 5 example apps now report 0 lint warnings.

## [0.57.21] - 2026-04-17

### Fixed
- `_detect_dead_constructs` no longer flags framework-synthetic platform entities (`domain == "platform"` — SystemMetric, SystemHealth, AIJob, FeedbackReport, etc.) as dead code when they're gated off in MINIMAL security profile. These entities come back the moment security.profile flips to STANDARD, so reporting them as dead on every Dazzle app was noise. The entities stay in the reachability cascade so admin surfaces still resolve correctly — only the final dead-entity warning skips them.

## [0.57.20] - 2026-04-17

### Fixed
- `_lint_workspace_personas` now treats `workspace.access.allow_personas` as a first-class persona binding. Previously the rule only looked at `persona.default_workspace` and `ux.persona_variants`, so workspaces that declared `access: persona(admin, manager)` (but didn't have a matching `default_workspace`) would fire "Workspace 'X' has no associated persona" even though they clearly did. simple_task `task_board` is the canonical case.

## [0.57.19] - 2026-04-17

### Fixed
- UX contract checker + runner looked for `data-region-name` but framework templates emit the namespaced `data-dz-region-name`. Every workspace surface on every downstream app was reporting `WORKSPACE_REGION_MISSING` regardless of whether regions were actually rendered. Updated `contract_checker.py` + `runner.py` (and matching unit-test fixtures) to the namespaced attribute, matching the `dz` prefix convention used across all runtime `data-*` attributes. AegisMark baseline goes from 12/972 workspace contract failures to 0 (#792).

## [0.57.18] - 2026-04-17

### Fixed
- `SessionManager.create_all_sessions` now attaches `X-Test-Secret` to its shared `httpx.AsyncClient` so every batched persona request carries the secret. Previously the batch path built a plain client and `create_session()` only injected the header when it built its own client — all personas 403'd on `/__test__/authenticate` even when the secret was correctly published to `runtime.json` by v0.57.13. Breaks had been masked because the single-call path worked (#791).

## [0.57.17] - 2026-04-17

### Added
- `SurfaceSpec.headless: bool = False` — marks a surface as intentionally API-only (no rendered form, e.g. a client-side widget owns the UI). Suppresses the "no sections defined" lint warning for these surfaces.

### Fixed
- `feedback_create` (framework-generated headless CREATE surface) now carries `headless=True` so the lint no-longer warns on every feedback-enabled app.
- Ledger parser wraps `LedgerSpec(...)` construction in `try/except ValidationError` and re-raises as a structured `ParseError` with token line/column. Previously a fuzz-mutated ledger with `account_code=0` / `ledger_id=0` would crash the caller with a raw pydantic traceback (caught by `test_insert_keyword_mutation`).

## [0.57.16] - 2026-04-17

### Fixed
- Auto-generated `feedback_admin` list surface now ships with a sensible `ux` block (sort by `created_at` desc, filter by category/severity/status, search description/reported_by, empty message). The lint warning "Surface 'feedback_admin' has no ux block" no longer fires on feedback-enabled apps — improve-loop cycle.

## [0.57.15] - 2026-04-16

### Fixed
- Auto-generated `FeedbackReport` entity (created by the linker when `feedback_widget: enabled`) now ships with `scope: all for: *` rules matching its five `permit:` rules. Previously the LIST endpoint default-denied on every feedback-enabled app because permit-without-scope is a lint warning AND a runtime default-deny. Improve-loop cycle.

## [0.57.14] - 2026-04-16

### Fixed
- Framework-generated admin surfaces (`_admin_health`, `_admin_deploys`, `_admin_metrics`, etc.) now ship with a sensible default `ux` block (status filter, text-field search, timestamp sort desc, empty message). The per-app lint warning "Surface '_admin_*' has no ux block" no longer fires on every Dazzle app — improve-loop cycle.

## [0.57.13] - 2026-04-16

### Fixed
- `dazzle serve` in test mode now generates a random `DAZZLE_TEST_SECRET` (if none is set) and publishes it to `.dazzle/runtime.json` so `dazzle test create-sessions` and `dazzle test dsl-run` can authenticate against `/__test__/*` without the caller pre-setting the env var. Closes the CyFuture / Penny Dreadful blocker where generated AUTH/SM/WS tests all failed with 403 / 404 because the test runner had no way to obtain a valid session cookie (#790).
- `SessionManager._resolve_test_secret` now falls back from env to `runtime.json` when authenticating personas. Same fallback added to the inline `SimpleAdapter` inside `E2ERunner.run_tests`.

### Added
- `ports.read_runtime_test_secret(project_root)` helper for consumers that need the shared secret without importing the whole serve context.

### Agent Guidance
- `dazzle serve --test-mode` (or any serve invocation that enables test endpoints) now writes a random `test_secret` to `.dazzle/runtime.json` alongside the port allocation. Tools that talk to `/__test__/*` endpoints should prefer reading that file (via `dazzle.cli.runtime_impl.ports.read_runtime_test_secret`) and only fall back to the `DAZZLE_TEST_SECRET` env var for CI environments that inject their own secret.

## [0.57.12] - 2026-04-16

### Added
- `dazzle agent seed <command>` — runs lint/validate pipelines and seeds a command's backlog file. Replaces the manual pipeline JSON parsing that outer assistants used to do inside the `/improve` loop (#788).
- `dazzle agent signals` — emits or consumes cross-loop signals via `.dazzle/signals/`. `--emit <kind> [--payload JSON]` drops a signal for other loops; `--consume [--kind K]` lists signals since the source's last run and marks the run (#788).
- `CommandDefinition.batch_compatible` + `signals_emit` / `signals_consume` metadata fields. The Jinja template renderer materialises declared signals into explicit consume/emit steps in the rendered skill markdown, and `batch_compatible` surfaces a grouping OBSERVE step in `/improve` that bundles identical-pattern gaps into one cycle (#788).
- Live-app health probe in `build_project_context` — detects `.dazzle/runtime.json`/`.dazzle/*.lock` markers and falls back to TCP probes on localhost:3000/8000. Gates for `requires_running_app` now reflect reality instead of always defaulting to `False` (#788).

### Changed
- Rewrote `improve.md.j2` from a generic stub to the full OBSERVE→ENHANCE→BUILD→VERIFY→REPORT playbook (based on the canonical `.claude/commands/improve.md`) with signal + batch awareness baked in. Bumped `/improve` to v1.1.0.
- Rewrote `polish.md.j2` to include a mandatory **Triage** step that filters audit findings against open GitHub issues and MCP `sentinel.findings` before marking anything actionable. Closes the feedback that `/polish` produced false positives tracing to known framework issues (#788). Bumped `/polish` to v1.1.0.

### Agent Guidance
- Loops now coordinate via signals. `/improve` emits `fix-committed` after a successful cycle; `/polish` emits `polish-complete` and consumes `fix-committed` + `ux-component-shipped`. Use `dazzle agent signals --source <loop> --consume` at the start of each cycle and `--emit <kind>` at the end of a successful cycle. Marker + signal files live in `.dazzle/signals/`.
- `/improve` can now batch identical-pattern gaps (same gap_type + target_file + category) into a single cycle. The template's OBSERVE step groups rows before marking them IN_PROGRESS. Set `batch_compatible = true` in a command's TOML to opt in.
- If `/polish` finds an issue already tracked in a GitHub issue or sentinel finding, the triage step marks the row BLOCKED with `tracked: #N` — don't waste cycles re-reporting known framework-level bugs.
- New seed invocation: `dazzle agent seed improve` / `dazzle agent seed polish` writes the backlog file from live pipeline output. No more hand-parsing JSON in the outer assistant.

## [0.57.11] - 2026-04-16

### Added
- `ux: bulk_actions:` DSL block on list-mode surfaces: binds named actions to single-field transitions (e.g. `accept: status -> active`). When present, the runtime mounts `POST /api/{entity_plural}/bulk` that accepts `{action, ids}` and applies the transition to every id. Returns per-id `{id, ok, error?}` rows plus a summary (#785).
- `BulkActionSpec` IR type in `dazzle.core.ir`.

### Agent Guidance
- Add bulk actions to a list surface without hand-coding an endpoint:
  ```dsl
  surface insertion_point_review "Review":
    uses entity InsertionPoint
    mode: list
    ux:
      bulk_actions:
        accept: status -> active
        reject: status -> rejected
  ```
  The runtime exposes `POST /api/insertionpoints/bulk` — send `{"action": "accept", "ids": [...]}` to apply the transition. Target values may be identifiers, quoted strings (for multi-word states), or `true`/`false`. Each transition flows through the repository's `update` path, so scope and access rules apply per item.

## [0.57.10] - 2026-04-16

### Added
- `dazzle ux explore` CLI command: prepares per-persona explore run contexts (state dir, findings file, background ModeRunner script) that the outer Claude Code assistant dispatches subagents against. Supports `--persona X` / `--all-personas`, `--cycles N`, `--strategy S`, `--app-dir PATH`, and `--json` output (#789).
- Three new explore strategies: `persona_journey` (walk DSL goals end-to-end), `cross_persona_consistency` (check scope rules from a single persona's POV), `regression_hunt` (post-upgrade sweep), and `create_flow_audit` (stress every create surface). Alongside existing `edge_cases` and `missing_contracts` there are now six strategies (#789).
- `/explore` agent command definition (`explore.toml` + `explore.md.j2`) so `dazzle agent sync` deploys the slash command into downstream projects.
- `GraphNodeSpec.parent_field` + DSL `parent:` inside `graph_node:` blocks (shipped in 0.57.8 — moved here for context on the exploration API rename).

### Changed
- **Breaking**: renamed explore substrate API from `example_*` to `app_*`:
  - `ExploreRunContext.example_root` → `app_root`, `example_name` → `app_name`
  - `init_explore_run(example_root=...)` → `init_explore_run(app_root=...)` (and `app_root` now defaults to `Path.cwd()`)
  - `build_subagent_prompt(example_name=...)` → `app_name=...` with a new `app_descriptor` variable replacing the hardcoded "Dazzle example app" wording
  - `PersonaRun.example_name` → `app_name`
  - `run_fitness_strategy(example_root=...)` → `app_root=...`
  No shims — callers are updated in the same commit. Rename blast radius: `subagent_explore.py`, `subagent_ingest.py`, `fitness_strategy.py`, `ux_explore_subagent.py`, and all related tests.
- `init_explore_run` now discovers `project_root` by walking upward for `dazzle.toml` (via new `discover_project_root`) instead of assuming `<repo>/examples/<name>`. Downstream projects get the same `dev_docs/ux_cycle_runs/` layout without passing paths explicitly (#789).
- Explore prompt template swapped "Dazzle example app" for a variable-driven opening so downstream projects can brand the prompt (#789).

### Agent Guidance
- Downstream projects can now run the exploration substrate without a Dazzle `examples/` tree. Add an `/explore` slash command with `dazzle agent sync`, then run `/explore` (or call `dazzle ux explore --strategy edge_cases`) from your project root. Boot the app with `dazzle serve`, dispatch subagents per the `explore.md.j2` playbook, and ingest findings into your project's `agent/explore-backlog.md`.
- When picking a strategy: start with `edge_cases`, follow up with `persona_journey` on the same persona set, then `cross_persona_consistency` to catch scope-rule drift. Use `regression_hunt` after framework upgrades and `create_flow_audit` when auditing onboarding.
- `init_explore_run(app_root=None)` uses the CWD — apps calling this from a script should always pass an explicit path when they're not running from the project root.

## [0.57.9] - 2026-04-16

### Changed
- Replace in-process `_task_store: dict[str, ProcessTask]` with pluggable `TaskStoreBackend` protocol + default `InMemoryTaskStore` (`src/dazzle/core/process/task_store.py`). `TemporalAdapter` now fetches tasks via `get_task_store()` so deployments can register a durable backend with `set_task_store(backend)` at startup before creating an adapter (#787).
- Renamed activities module helpers: `get_task_from_db` → `get_task`, `list_tasks_from_db` → `list_tasks`, `complete_task_in_db` → `complete_task`, `reassign_task_in_db` → `reassign_task`. Also: `clear_task_store()` is now an async coroutine that calls `backend.clear()`. Updated all in-tree callers; there is no backward-compat shim.

### Agent Guidance
- The in-memory task store is **not durable** — tasks vanish on process exit. Production deployments running Temporal must register a database-backed `TaskStoreBackend` before creating `TemporalAdapter`:
  ```python
  from dazzle.core.process.task_store import set_task_store
  set_task_store(MyPostgresTaskStore(...))
  ```
  The protocol contract is `save / get / list / complete / reassign / escalate / clear` — all async.

## [0.57.8] - 2026-04-16

### Added
- Parent-scoped graph endpoint `GET /api/{parent_plural}/{id}/graph` auto-registered when a `graph_node:` block declares `parent: <ref_field>`. Returns every node whose parent_field equals `{id}` plus the edges connecting them, serialized via `GraphSerializer`. Supports `?format=cytoscape|d3|raw` (default: cytoscape). Complements the existing seed-based neighborhood endpoint (#781).
- `GraphNodeSpec.parent_field` (optional) + matching DSL `parent: <ref_field>` inside the `graph_node:` block. Validator enforces that the named field exists and is a ref field.

### Agent Guidance
- Declare the parent relationship on the node entity to expose a graph view keyed off the parent:
  ```dsl
  entity Node "Graph Node":
    id: uuid pk
    work_id: ref Work required
    title: str(200) required
    graph_node:
      edges: NodeEdge
      display: title
      parent: work_id
  ```
  The runtime will mount `GET /api/works/{id}/graph` returning Cytoscape.js JSON for every node belonging to that Work plus the edges between them. The seed-based neighborhood endpoint at `/api/nodes/{id}/graph` remains available for traversal from a single node.

## [0.57.7] - 2026-04-16

### Added
- Cross-entity search endpoint `GET /api/search?q=...` registered automatically when any entity declares searchable fields. Results are grouped by entity with per-entity `total`, `fields`, and `items`. Supports `?entity=<name>` to restrict scope and `?limit=N` (1–100) per entity (#782).
- Entity-level `searchable` modifier on fields now registers those fields for search without needing a matching surface `search_fields:` declaration. Surface declarations still take precedence when both are present (#782).

### Agent Guidance
- Declare searchable fields on the entity for a zero-surface cross-entity search:
  ```dsl
  entity Work "Work":
    title: str(300) required searchable
    description: text searchable
  ```
  When multiple entities declare searchable fields, the runtime exposes `GET /api/search?q=...` fanning out across them. Surface-level `search_fields:` is still supported and takes precedence for that entity.

## [0.57.6] - 2026-04-16

### Added
- Project `dazzle.toml` files accept an `[extensions]` section listing FastAPI `APIRouter` objects to mount alongside generated routes. Each entry is a `module:attr` spec imported relative to the project root, whitelisted to plain dotted identifiers. Enables apps with large custom API surfaces (e.g. Penny Dreadful's 143 custom endpoints) to use `dazzle serve` directly instead of bypassing it with their own server module — restoring `/polish`, fitness engine, and `dazzle test agent` compatibility (#786).

### Fixed
- Mypy error in `service_generator.py` where `raise result.error` didn't narrow `Optional[TransitionError]` to a non-None `BaseException` — added the explicit `is not None` guard.

### Agent Guidance
- Declare custom routers in `dazzle.toml`:
  ```toml
  [extensions]
  routers = ["app.routes.graph:router", "app.routes.search:router"]
  ```
  Each module must expose the named attribute as a `fastapi.APIRouter`. Extension routers mount after `routes/*.py` single-file overrides and before generated CRUD routes, so they win first-match against auto-generated endpoints. Invalid specs (path traversal, non-identifier characters) are silently skipped with a warning.

## [0.57.5] - 2026-04-16

### Added
- Standalone `GET /api/workspaces/{name}/stats` endpoint returns aggregate metrics as JSON (namespaced by region name) for every workspace region that declares an `aggregates:` block. Enables headless/API-first consumption of dashboard KPIs without rendering the UI (#783).

### Fixed
- `serializers.py` now passes `set(...)` to Pydantic `model_dump(include=...)`; fixes two mypy errors introduced by the v0.57.2 frozenset-conversion sweep where `frozenset[str]` is not a valid `IncEx` type.

## [0.57.4] - 2026-04-16

### Added
- `persona` DSL blocks accept `interactive: true|false` to indicate whether a persona represents a login-capable human. Non-interactive service personas (e.g. a `system` persona for background jobs) are skipped by the auth-lifecycle test generator, eliminating guaranteed-to-fail AUTH_LOGIN_VALID/AUTH_REDIRECT/AUTH_SESSION_VALID tests (#780).

## [0.57.3] - 2026-04-16

### Fixed
- Fidelity scorer now recognises widget-rendered input types: datepicker (text→date/datetime), range-tooltip and bare `type="range"` (→number), richtext (hidden→text/textarea/select). Eliminates false-positive INCORRECT_INPUT_TYPE gaps introduced by the v0.56.0 widget system (#779).

## [0.57.2] - 2026-04-16

### Changed
- Extracted 52 AppSpec query methods to `appspec_queries.py` (delegates remain for backward compat)
- Decomposed `parse_entity` from 728 → 76 lines (25 named helpers + context dataclass)
- Decomposed `ProcessParserMixin` longest methods from 132 → 32 lines (context dataclasses)
- Decomposed `serve_command` from 594 → 45 lines (10 focused helpers)
- Decomposed `_page_handler` from 514 → 59 lines (9 route helpers + context dataclass)
- Converted 48 mutable ALL_CAPS constants to `frozenset`/`tuple` (28 sets, 20 lists)

## [0.57.1] - 2026-04-16

### Fixed
- Process executors: DB-connection failures now raise instead of silently returning `{}`
- Process executors: foreach steps with 100% sub-step failures now raise instead of reporting success
- Silent email message-read error (`JSONDecodeError`/`KeyError` caught with bare pass)
- Thread-unsafe lazy-init singletons converted to `lru_cache` or `threading.Lock` (7 locations)
- Bare `# type: ignore` comments replaced with specific error codes

### Changed
- Moved `agent_commands` shared modules to `dazzle.services` (fixes MCP→CLI import cycle)
- Consolidated divergent HTTP retry implementations into `dazzle.core.http_client`
- Deleted duplicate Celery module (`process_celery_tasks.py`, ~750 lines)
- Split `get_consolidated_tools()` from 1477-line function into per-tool factories
- Replaced 30 `Any` annotations with concrete types in `route_generator.py` and `server.py`
- Moved `field_value_gen` to `dazzle.core.field_values` (fixes UI→testing layer violation)

## [0.57.0] - 2026-04-16

### Added
- Agent-first development commands: `/improve`, `/qa`, `/spec-sync`, `/ship`, `/polish`, `/issues`
- `dazzle agent sync` CLI command — installs/updates commands in user projects
- MCP `agent_commands` tool (list, get, check_updates) for runtime capability discovery
- `AGENTS.md` cross-tool convention file generation (Copilot, Cursor, Windsurf, Codex)
- Agent Tool Convention — backlog/log pattern for `agent/` directory
- Bootstrap integration nudges agents to install commands on new projects
- 39 new tests for agent command infrastructure

### Agent Guidance
- New projects: run `dazzle agent sync` after first successful `dazzle validate`
- Agent commands track state in `agent/` (git-tracked backlogs and logs)
- Session-start: call `mcp__dazzle__agent_commands operation=check_updates` for new capabilities
- Design: `docs/superpowers/specs/2026-04-16-agent-commands-design.md`

## [0.56.0] - 2026-04-16

**Minor release — UX modernisation arc complete.** Consolidates 12 patch
releases (v0.55.36 → v0.55.47) into a named minor. Headline changes:

- DaisyUI migration 99%+ complete (~210 class instances → design tokens)
- 8 new component contracts (status-badge, metrics-region, empty-state,
  tooltip, toggle-group, breadcrumbs, alert-banner, accordion + 3 more)
- Per-persona DSL overrides (`empty:`, `hide:`, `read_only:`) wired
  end-to-end on both list and form surfaces
- Persona-entity binding (`backed_by` / `link_via`) with runtime
  auto-injection on create handlers
- Aggregate regions auto-infer `display: summary`
- Ref fields auto-render as entity-backed `<select>` dropdowns
- 3 latent XSS vectors closed
- 137 new regression tests (10,723 → 10,860), zero regressions
- Backlog cleared: 0 OPEN EX rows remaining
- Frontier agent briefing at `dev_docs/frontier-agent-briefing-v0.55.47.md`

See individual patch changelogs below for per-commit detail.

## [0.55.47] - 2026-04-16

### Fixed
- **Comprehensive DaisyUI→design-token sweep (cycle 250).** Migrated
  ~99 remaining DaisyUI class instances across 30 template files to
  canonical design-token equivalents. Covers: site/marketing pages
  (hero, CTA, pricing, FAQ, features, testimonials, card_grid, etc.),
  experience wizard, layout chrome, fragment stragglers, workspace
  region stragglers. Only 3 DaisyUI instances remain across the entire
  template set, all in the stepper/wizard component (`step-primary`)
  which requires a dedicated stepper rewrite to replace.

- **Dead drawer `href="#"` on "Open full page" (EX-005/EX-032).**
  Workspace drawer's expand link was a dead affordance. Now hidden by
  default with `hidden` attribute; JS reveals it only when a real
  URL is available.

- **Detail view renders 'None' for null timestamps (EX-022).** Added
  a `{% if value is none %}` guard at the top of the detail-view
  field rendering chain. Also fixed `default()` to pass `true` as
  the second argument so Jinja2 treats Python `None` as missing.

- **Bulk action bar double-space in "Delete  items" (EX-023).** The
  text nodes were separate flex children with gap between them.
  Wrapped in a single `<span>` so the text is one flex child.

- **Workspace filter dropdowns raw enum values (EX-031).** Applied
  `| humanize` to filter option display text in workspace region
  templates (list.html, tab_data.html, queue.html). Values remain
  raw for correct filtering.

- **Raw entity name in Create CTA and search placeholder (EX-038).**
  Applied `| replace("_", " ")` to handle snake_case entity names in
  filterable_table.html and search_input.html.

- **Missing `data-dz-region-name` on workspace regions (EX-025).**
  Extended the `region_card` macro to stamp `data-dz-region-name`
  and a matching `id="region-<name>"` from the region's context.

- **Backlog cleanup.** Removed duplicate EX-046 row. Reclassified
  EX-012 (CLOSED_NO_ACTION), EX-019 (CLOSED_SUPERSEDED by cycle 228),
  EX-026 (DEFERRED — contract-gen issue). Reclassified 7 DSL/app
  quality rows (EX-010/013/015/016/027/033/036) as DEFERRED_APP_QUALITY.

## [0.55.46] - 2026-04-16

### Added
- **Runtime auto-injection for persona-backed entities (cycle 249,
  closes EX-049).** Completes the cycle 248 `backed_by` feature by
  wiring the declaration through at runtime. New async
  `resolve_backed_entity_refs` helper in `route_generator.py` runs
  in the create handler after `inject_current_user_refs`. When a
  `ref Tester` field is missing from the body AND persona `tester`
  declares `backed_by: Tester`, the helper resolves the backing
  entity: for `link_via: id` it injects `current_user` directly
  (zero-cost, same convention as the existing #774 pattern); for
  `link_via: email` it does an async `repo.get_one({email: user_email})`
  lookup. The `persona_ref_map` is built at route-registration time
  from `entity_ref_targets` + `persona_backed_entities` (populated
  from the appspec in `server.py`). Auth wrappers now pass
  `user_email` alongside `current_user` to all core handlers.

### Fixed
- **Cedar update handler missing `**_extra` kwargs.** The update
  handler with Cedar access control had an explicit signature that
  rejected unexpected keyword arguments. Adding `user_email` to the
  auth wrapper exposed this as a TypeError. Added `**_extra` to the
  signature for forward compatibility with future auth-context fields.

### Agent Guidance
- **When adding a new field to the auth-wrapper→core-handler call
  path**, ensure ALL handler `_core` signatures accept `**_extra`
  or the specific new kwarg. There are 4 distinct `_core` functions
  in `route_generator.py` (read/create/update/delete); the update
  handler's Cedar variant was the only one missing `**_extra` before
  this fix. Cycle 249 adds `user_email` — any future auth-context
  field should also be passed as a kwarg and accepted via `**_extra`.

## [0.55.45] - 2026-04-16

### Added
- **Persona-entity binding: `backed_by` / `link_via` DSL construct
  (cycle 248, closes EX-045).** DSL authors can now explicitly declare
  which domain entity backs a persona:
  ```dsl
  persona tester "Field Tester":
    backed_by: Tester
    link_via: email
  ```
  New `PersonaSpec.backed_by: str | None` and `PersonaSpec.link_via: str`
  fields on the IR. Parser extension accepts `backed_by:` and `link_via:`
  inside persona blocks. Linker validation at `dazzle validate` time
  checks: (1) the named entity exists, (2) the `link_via` field exists
  on the entity, (3) no two personas claim the same backing entity.
  This is the **DSL surface + validation layer** — runtime auto-injection
  (resolving the backing entity row from the current auth user at
  request time) is tracked as EX-049 for a follow-up cycle that threads
  through the async repository lookup in the create handler.

### Agent Guidance
- **When a DSL has both a persona and a same-named entity** (e.g.
  `persona tester` + `entity Tester`), declare the binding explicitly
  with `backed_by: Tester`. This enables future runtime features
  (auto-injection of `ref Tester` fields, scope-rule cascading, form
  pre-selection) and catches misconfigurations at validate time rather
  than silently failing at runtime. Default `link_via` is `email`;
  override to `id` if entity IDs match auth user IDs by convention.

## [0.55.44] - 2026-04-16

### Fixed
- **Parking-lot primitives modernised (cycle 247, 6 fragments).** Batch
  modernisation of six small fragments that shipped with DaisyUI classes
  and had zero consumers: `breadcrumbs.html`, `alert_banner.html`,
  `accordion.html`, `context_menu.html`, `skeleton_patterns.html`,
  `date_range_picker.html`. All six now use design-token colours, canonical
  `dz-*` class markers, ARIA semantics, and Tailwind transitions. Family
  contract at `~/.claude/skills/ux-architect/components/parking-lot-primitives.md`.
  Also fixed: accordion `{{ content | safe }}` XSS vector removed (same
  class as cycle 241 tooltip fix), context-menu adds `@keydown.escape.window`
  for keyboard dismiss, date-range-picker adds explicit `id`+`for` on
  labels for accessibility, skeleton-patterns uses explicit `animate-pulse`
  instead of DaisyUI `skeleton` class. Updated 5 existing tests in
  `test_phase2_fragments.py` and `test_phase3_fragments.py` that asserted
  DaisyUI class names. 16 new tests in `test_parking_lot_primitives.py`.

## [0.55.43] - 2026-04-16

### Added
- **Per-persona `read_only` for list surfaces (cycle 244, EX-048
  partial).** Extended `_apply_persona_overrides` to handle the
  cycle 240 PersonaVariant resolver pattern with a third field.
  When a DSL variant declares `for <persona>: read_only: true`,
  the per-request table copy has `create_url=None`,
  `bulk_actions=False`, and `inline_editable=[]` before rendering.
  Distinct from the existing `_should_suppress_mutations` helper
  (which gates on `permit:` rules) — this is an explicit
  persona-variant declaration.

- **Per-persona `hide` + `read_only` for form surfaces (cycle 245,
  closes gap doc #2 axis 4).** New `_apply_persona_form_overrides`
  helper in `page_routes.py`, parallel to cycle 243's table
  resolver. `FormContext.persona_hide: dict[str, list[str]]` and
  `FormContext.persona_read_only: set[str]` compiled from
  `ux.persona_variants` in `_compile_form_surface`. At request
  time, hidden fields are removed from `req_form.fields`, every
  section's field list, AND `req_form.initial_values` (defensive
  — prevents hidden-field injection via pre-filled POST bodies).
  Read-only forms raise `HTTPException(403)` because a form is
  inherently a mutation affordance. Added a new per-request branch
  for CREATE-mode forms which previously used `ctx.form` directly
  with no mutation. **Closes gap doc #2 axis 4**:
  persona-unaware create-form field visibility is now a
  DSL-declarable override via `for <persona>: hide: field1, field2`
  on create/edit surfaces.

### Fixed
- **Aggregate display-mode inference (cycle 246, closes EX-047).**
  When a DSL region declared `aggregate: { ... }` but omitted
  `display:`, the display mode defaulted to LIST, routing the
  region through the list template which dropped the aggregates
  and rendered as an empty list. Fixed in `workspace_renderer.py`
  with a 3-line inference: if `display_mode == "LIST"` and
  `region.aggregates` is non-empty, promote to `SUMMARY`. Closes
  4 previously-broken regions across 2 apps: simple_task
  `admin_dashboard.metrics`, `admin_dashboard.team_metrics`,
  `team_overview.metrics`, fieldtest_hub
  `engineering_dashboard.metrics`. Cross-app HTTP verified:
  simple_task admin_dashboard/metrics now renders 5 tiles (Total
  Tasks / Todo / In Progress / In Review / Done), previously zero.

### Agent Guidance
- **PersonaVariant runtime wiring pattern is now well-established.**
  Four cycles (240/243/244/245) have used the same shape: compile
  a `persona_<field>s: dict|set` into the relevant template
  context, populate from `ux.persona_variants` in the compiler,
  resolve per-request via `_apply_persona_overrides` (tables) or
  `_apply_persona_form_overrides` (forms). Both helpers use
  first-wins role matching with `role_` prefix stripping. When
  extending to a new PersonaVariant field, follow the same recipe
  in the relevant helper's docstring.
- **Aggregate regions default to SUMMARY now.** If a DSL region
  has `aggregate:` without explicit `display:`, it renders as a
  KPI tile grid (via metrics.html), not as an empty list. If you
  want a list with aggregates below it, use `display: summary`
  explicitly — the metrics template supports both.

## [0.55.42] - 2026-04-16

### Added
- **Per-persona list-column hide support (EX-048 partial fix).** The
  DSL parser has always accepted `for <persona>: hide: col1, col2`
  inside UX blocks, but before cycle 243 the values were silently
  dropped at render time. Cycle 243 extends the cycle 240
  compile-dict-then-resolve-per-request pilot to cover `hide`:
  - `TableContext.persona_hide: dict[str, list[str]]` compiled from
    `ux.persona_variants` in `_compile_list_surface`
  - Per-request resolution sets `column.hidden=True` for every matching
    column on the user's primary persona
  - Stacks cleanly on top of the existing cycle-240 condition-eval
    column hiding (both set the same `hidden=True` flag)

- **`_apply_persona_overrides` helper in `page_routes.py`.** Extracted
  the cycle 240 inline resolver block into a standalone function that
  takes a per-request table copy and a user_roles list. First-wins
  matching (primary persona takes precedence), role-prefix stripping,
  and idempotent with empty dicts / empty user_roles. Fully testable
  in isolation without a full request context. The helper's docstring
  documents the 3-step extension pattern so future cycles can add the
  remaining PersonaVariant fields (`purpose`, `show`, `show_aggregate`,
  `action_primary`, `read_only`, `defaults`, `focus`) mechanically.

### Agent Guidance
- **When extending PersonaVariant runtime wiring**, follow the cycle
  240 + 243 pattern: (1) add a `persona_<field>s` dict to the relevant
  template context, (2) populate from `ux.persona_variants` in the
  compiler, (3) apply the resolution semantics inside
  `_apply_persona_overrides`. The helper's docstring is the canonical
  recipe. Each field is ~10-15 min of work. Batching the remaining
  6 fields in one cycle is a reasonable next step (tracked as EX-048).
- **Watch for UX backlog ID collisions.** Cycles 240 and 242 both
  claimed IDs that were already in use (UX-043, UX-046). Before
  picking the next UX-NNN ID, run
  `grep -oE "^\| UX-[0-9]+" dev_docs/ux-backlog.md | sort -u | tail -5`
  to find the highest existing ID and pick the next one.

## [0.55.41] - 2026-04-16

### Added
- **`toggle-group` component contract (UX-046).** Fifth and final cycle
  of the component menagerie mini-arc (cycles 238-242). Contract at
  `~/.claude/skills/ux-architect/components/toggle-group.md` governing
  the Linear/macOS segmented-control pattern: pill-shaped track with
  tinted background, selected button "lifted" with solid background and
  subtle drop shadow, unselected buttons muted-foreground with hover
  brightening, `role="radiogroup"` (exclusive) or `role="group"`
  (multi), `aria-pressed` per button, keyboard arrow-key navigation,
  and `focus-visible` keyboard ring. 6 quality gates and 7 v2 open
  questions (future `display: [list, kanban]` DSL extension, icon-only
  buttons, touch affordances, overflow, disabled options, value
  validation, dark-mode).

- **Keyboard arrow-key navigation for toggle groups.** Pre-cycle-242
  the fragment had no keyboard navigation between buttons. Added
  `@keydown.left.prevent` and `@keydown.right.prevent` handlers that
  move focus to the previous/next sibling button. Combined with the
  `focus-visible:ring-1 focus-visible:ring-[hsl(var(--ring))]` styling,
  this makes the control fully WCAG-keyboard-accessible.

### Fixed
- **Toggle group DaisyUI drift.** Modernised
  `fragments/toggle_group.html` — replaced
  `class="join"` + `btn join-item btn-sm` + `btn-primary`/`btn-ghost`
  dynamic classes with design tokens (`bg-[hsl(var(--muted)/0.3)]`
  track, `bg-[hsl(var(--background))]` selected, canonical
  `dz-toggle-group` + `data-dz-toggle-item` + `data-dz-value`
  automation markers). Closes more of EX-001 (DaisyUI drift).

### Agent Guidance
- **Component menagerie mini-arc is complete.** Five `contract_audit`
  cycles (238-242) shipped five component contracts: status-badge,
  metrics-region, empty-state (+ EX-046 DSL grammar extension for
  per-persona empty copy), tooltip (+ latent XSS fix), toggle-group.
  Net: 5 new contracts, ~40+ call sites migrated, +67 tests, zero
  regressions. Two latent security issues fixed along the way.
- **Cross-cutting drift clusters.** Every single cycle surfaced
  broader drift beyond the originally-targeted component. When running
  a future `contract_audit`, budget 2-3x the scope of the contract
  itself for adjacent drift discovered during the grep walk.
- **PersonaVariant runtime wiring is half-built.** Cycle 240 wired
  `empty_message` as a pilot; `purpose`, `hide`, `show`,
  `action_primary`, `read_only`, `defaults`, `focus` are all parsed
  but silently dropped at render time. Generalising the pilot pattern
  is a ~30-60 minute cycle worth doing before the next frontier-user
  release.

## [0.55.40] - 2026-04-16

### Added
- **`tooltip` component contract (UX-045).** Fourth cycle of the component
  menagerie mini-arc. Contract at
  `~/.claude/skills/ux-architect/components/tooltip.md` governing two
  canonical shapes: the native `title="..."` attribute (default, zero-JS,
  screen-reader-accessible — used for short plain-text labels on icon
  buttons and truncated cells) and the rich Alpine fragment at
  `fragments/tooltip_rich.html` (HTML-content-capable, positioning-aware,
  with configurable show/hide delays). 6 quality gates and 7 v2 open
  questions.

- **`[x-cloak] { display: none !important; }` CSS rule** in
  `dazzle-layer.css`. Without this rule, every Alpine component using
  `x-cloak` (tooltip_rich, search_input, search_select, table_pagination,
  bulk_actions) flashed briefly on first paint before Alpine removed the
  attribute. Single one-line addition fixes all 5 existing consumers.

- **`contract_audit` promoted to a named cycle strategy.** Added to
  `.claude/commands/ux-cycle.md` as strategy #5 alongside
  `missing_contracts`/`edge_cases`/`framework_gap_analysis`/
  `finding_investigation`. Track record: cycles 238 (status-badge), 239
  (metrics-region), 240 (empty-state + EX-046 grammar extension), 241
  (tooltip + latent XSS fix) — four successful iterations of the same
  shape. Distinct from `missing_contracts` in that it executes the fix
  for a specific already-chosen target rather than proposing which
  components to contract.

### Fixed
- **Latent XSS vector in `fragments/tooltip_rich.html`.** The fragment
  piped user-supplied `content` through `| safe`, bypassing Jinja
  autoescape. No known consumer was affected (the fragment has zero
  template call sites), but the pattern was a pre-positioned landmine
  for any future DSL author who wired a user-authored description into
  a tooltip. Removed `| safe` from `{{ content }}`; the trigger block
  retains `| safe` because triggers are intentionally markup. Regression
  test `test_content_is_autoescaped` pins the safe posture in place —
  it passes `<script>alert('xss')</script>` and asserts the raw tag
  does not appear in rendered output.

- **Tooltip fragment DaisyUI drift.** Modernised
  `fragments/tooltip_rich.html` — replaced
  `bg-neutral text-neutral-content rounded-box shadow-lg` with inverted
  design tokens (`bg-[hsl(var(--foreground))] text-[hsl(var(--background))]`
  for the Linear/macOS tooltip convention) and explicit two-layer shadow.
  Added canonical `dz-tooltip` class marker, `data-dz-position` attribute,
  `data-dz-tooltip-panel` panel marker for automation.

### Agent Guidance
- **Prefer native `title="..."` for tooltips unless you need HTML
  content or positioning.** Native title attributes are zero-JS,
  universally accessible, and contract-compliant as written. Only reach
  for the rich Alpine fragment when you need structured markup,
  configurable positioning, or delay tuning. On icon-only triggers,
  always pair `title=` with a matching `aria-label` for screen readers.
- **Never pipe tooltip content through `| safe`.** Jinja autoescape is
  the security posture. Callers needing HTML content should extend the
  trigger block (which IS `| safe`) rather than the content slot.
- **`contract_audit` is now a fully-supported cycle strategy.** When
  the user asks for component-quality work or references the cycle 237
  roadmap, `contract_audit` is the right shape: pick a known-templated-
  but-ungoverned component, reproduce drift, grep call sites, build
  contract + fix + tests in one commit.

## [0.55.39] - 2026-04-16

### Added
- **`empty-state` component contract (UX-043).** Third cycle of the component
  menagerie mini-arc. Two canonical shapes now formally governed: the full
  fragment at `fragments/empty_state.html` (SVG + copy + optional CTA button
  for list/grid/kanban/tree) and the dense inline `<p class="dz-empty-dense">`
  pattern (for inline-card regions like metrics/bar_chart/timeline/queue).
  Canonical class markers: `dz-empty-state` + `data-dz-empty-kind` +
  `data-dz-empty-cta`, `dz-empty-dense`, with `role="status"` ARIA
  everywhere. Contract at
  `~/.claude/skills/ux-architect/components/empty-state.md` with 5
  quality gates and 7 v2 open questions.

- **Per-persona `empty:` override (EX-046 closed).** DSL authors can now
  declare persona-specific empty-state copy inside `for <persona>:` blocks:
  ```dsl
  ux:
    empty: "No tasks yet"
    for member:
      empty: "You have no assigned tasks"
  ```
  New `ir.PersonaVariant.empty_message: str | None` field, parser support
  in `UXParserMixin.parse_persona_variant`, compile-time collection into
  `TableContext.persona_empty_messages: dict[str, str]` at
  `_compile_list_surface`, and a per-request resolver in `page_routes.py`
  that looks up the current user's role and swaps `req_table.empty_message`
  before rendering. **This is the pilot implementation for PersonaVariant
  runtime wiring** — the same compile-dict-then-resolve-per-request
  pattern can generalise to `purpose`, `hide`, `show`, `action_primary`,
  `read_only`, which are currently parsed but silently dropped at render
  time.

### Fixed
- **Legacy DaisyUI classes in `fragments/empty_state.html`.** Modernised
  the canonical full empty-state fragment to use design tokens instead
  of `btn btn-primary btn-sm` + `text-base-content/50`. The CTA button
  now uses `bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]`
  matching the canonical button anatomy used elsewhere. Closes more
  of EX-001 (DaisyUI drift).

- **Dense empty-state drift across 9 region templates.** `bar_chart`,
  `detail`, `funnel_chart`, `heatmap`, `metrics`, `progress`, `queue`,
  `tab_data`, `timeline` all had inline empty-state `<p>` tags with
  inconsistent classes. Added canonical `dz-empty-dense` class marker +
  `role="status"` everywhere. Fixed `tab_data` and `funnel_chart` legacy
  `text-sm opacity-50` (non-token fallback) to use the canonical
  `text-[13px] text-[hsl(var(--muted-foreground))]` design token.

### Agent Guidance
- **Use the canonical empty-state patterns.** For primary entity list
  surfaces, `{% include "fragments/empty_state.html" %}`. For inline
  dense regions (charts/metrics/timelines/queues), use
  `<p class="dz-empty-dense text-[13px] text-[hsl(var(--muted-foreground))]" role="status">`.
  Never inline an ad-hoc empty-state `<p>` or `<div>`.
- **When extending PersonaVariant wiring, follow the cycle 240 pilot
  pattern.** Compile a `persona_<field>s: dict[str, T]` into the
  relevant template context at compile time; resolve per-request in
  `page_routes.py` by walking `ctx.user_roles` (stripping the `role_`
  prefix) and swapping the request-copy field before rendering. This
  mirrors the cycle 228 bulk-action-bar suppression pattern and the
  cycle 240 `empty_message` resolver.

## [0.55.38] - 2026-04-16

### Added
- **`metrics-region` component contract (UX-042).** Second cycle of the
  component menagerie mini-arc. Contract at
  `~/.claude/skills/ux-architect/components/metrics-region.md` with 6
  quality gates governing the KPI tile grid + optional drill-down table
  rendered by `workspace/regions/metrics.html`. Rewrote the template to
  add canonical `dz-metrics-grid` + `dz-metric-tile` class markers,
  `data-dz-tile-count` + `data-dz-metric-key` automation attributes, and
  `tabular-nums` digit alignment.

- **`metric_number` Jinja filter.** Canonical formatter for every
  aggregate tile value across the framework. Integers render with
  thousands separator (`1234` → `1,234`), floats ≥ 1 with one decimal
  place, sub-unit floats verbatim, `True`/`False` → `Yes`/`No`,
  `None` → `0`, strings pass through. DSL authors no longer need to
  pre-format aggregate values.

### Fixed
- **Hardcoded HSL warning literals across 9 region templates (cross-cutting
  drift fix).** `grid.html`, `heatmap.html`, `kanban.html`, `list.html`,
  `metrics.html`, `progress.html`, `queue.html`, `tab_data.html`,
  `timeline.html` all had `hsl(38_92%_50%)` / `hsl(38_92%_35%)` inlined for
  attention-level warning tints instead of routing through the `--warning`
  design token. 14 call sites migrated to `hsl(var(--warning))`-based
  arbitraries. Makes these templates dark-mode-adaptive for free.
  `tab_data.html` additionally had broken Tailwind-arbitrary classes
  (`bg-error/10`, `bg-warning/10`, `bg-info/10`) that don't resolve to
  design tokens; migrated to canonical design-token arbitraries.

- **Dead `metric.description` branch removed from `metrics.html`.** The
  backend's `_compute_aggregate_metrics` only emits `{"label", "value"}`
  dicts — it never populates `description`. The `{% if metric.description %}`
  branch had been silently dead code. Removed, with a regression test
  locking the removal in place.

### Agent Guidance
- **Never inline attention-level background colours.** Use design-system
  tokens (`hsl(var(--destructive)/0.08)`, `hsl(var(--warning)/0.08)`,
  `hsl(var(--primary)/0.06)`). The pre-cycle-239 pattern of hardcoding
  `hsl(38_92%_50%/0.08)` for warning is now regressed out of every region
  template and the metrics-region contract gates against its reintroduction.
- **`contract_audit` as a cycle strategy is proving itself.** Cycles 238
  and 239 both ran the same pattern (pick ungoverned template → reproduce
  drift → grep call sites → build macro/filter + contract in one commit →
  migrate every call site → cross-app verify → regression tests). Expect
  the next several cycles (240-242) to follow the same shape. Promote to
  the skill after cycle 240.
- **When auditing a component, grep for its neighbours.** Cycle 238 found
  status-badge drift; cycle 239 found warning-HSL drift in the same class
  of templates. Cross-cutting drift tends to cluster — one audit often
  surfaces siblings worth fixing in the same commit for consistency.

## [0.55.37] - 2026-04-16

### Added
- **`status-badge` component contract (UX-041).** First cycle of the component
  menagerie mini-arc (cycles 238-242 per the roadmap at
  `dev_docs/framework-gaps/2026-04-15-component-menagerie-roadmap.md`). New
  canonical `render_status_badge` Jinja macro at
  `src/dazzle_ui/templates/macros/status_badge.html` is now the single source
  of truth for every enum/state/status rendering across the framework: 5
  semantic tones (`neutral | success | warning | info | destructive`), 2
  sizes (`md` default, `sm` for dense regions), optional bordered variant
  for detail regions. Contract at
  `~/.claude/skills/ux-architect/components/status-badge.md` with 5 quality
  gates and 7 v2 open questions.

- **`badge_tone` Jinja filter.** Maps any status/priority/severity enum value
  to one of 5 semantic tones via a canonical `_STATUS_TONE_MAP` covering
  ~30 values (active/done/open/pending/review/critical/urgent/high/medium/
  low/etc.). Case-insensitive, space-to-underscore normalised.

### Fixed
- **Status-badge drift across 16+ template call sites.** Before cycle 238,
  status rendering used 7 distinct inline class combinations plus a legacy
  DaisyUI-shaped `fragments/status_badge.html` plus a broken `.badge-error`
  CSS rule referencing an undefined `--er` variable. All call sites migrated
  to the canonical macro: `table_rows.html`, `related_status_cards.html`,
  `related_table_group.html`, `detail_fields.html`, and workspace regions
  `list`, `grid`, `timeline`, `queue`, `bar_chart`, `kanban` (2×), `detail`,
  `tab_data`, `metrics`. `grep -rn badge_class src/dazzle_ui/templates/`
  returns zero call sites. Cross-app verified on all 5 example apps: zero
  legacy `badge-{ghost,success,warning,info,error}` classes remain in
  rendered output. Closes part of EX-001.

- **Broken `.badge-error` CSS rule** at `design-system.css:702` — referenced
  undefined `--er` variable instead of the canonical `--destructive`. Every
  previously-rendered `destructive` badge was silently mis-coloured.

### Agent Guidance
- **Never inline status badge rendering.** Always use
  `{% from 'macros/status_badge.html' import render_status_badge %}` and
  call the macro. The `badge_class` filter is deprecated and exists only as
  a back-compat shim for legacy call sites — new code MUST use `badge_tone`
  + the macro, which renders to `hsl(var(--token))`-based Tailwind classes
  from the design system instead of the legacy DaisyUI class names.
- **`contract_audit` is the cycle shape for the component menagerie mini-arc**
  (cycles 238-242). Pattern: pick a known-templated-but-ungoverned component,
  HTTP-layer reproduce the drift, grep every call site, build macro + filter
  + contract in one commit, migrate every call site, cross-app verify,
  regression tests matching the quality gates. See cycle 238 for the
  template to follow for cycles 239-242.

## [0.55.36] - 2026-04-15

### Fixed
- **Widget-selection gap for `ref` fields in form generation (closes EX-044).** Plain
  `ref Entity` fields in create/update surfaces have been silently rendering as
  `<input type="text">` on every app, because the form-field template had no branch
  for `field.type == "ref"`. Fix: added `ref_entity` + `ref_api` to `FieldContext`,
  auto-populated them in `_build_form_fields` and `_build_form_sections` at
  `src/dazzle_ui/converters/template_compiler.py` for REF/BELONGS_TO fields with no
  explicit `source:` override, and added a new `{% elif field.ref_entity %}` branch
  in `src/dazzle_ui/templates/macros/form_field.html` that renders an Alpine-hydrated
  `<select>` fetching options from the entity's list endpoint (mirrors the existing
  `filter_bar.html` pattern, no new backend route needed). Cross-app verified on all
  5 example apps: simple_task/User, support_tickets/User (agent + customer),
  ops_dashboard/System, fieldtest_hub/Tester + Device+Tester. Closes EX-006,
  EX-009 (ref-half), the widget half of EX-029 + EX-041. Gap doc #5
  (widget-selection-gap.md) is now fully closed — date half in v0.55.34 cycle 232,
  ref half here in cycle 236. Also folds the v0.55.34 cycle 232 date-picker default
  into the wizard path (`_build_form_sections`) which was missing it. 3 new
  regression tests in `test_template_compiler.py::TestRefFieldAutoWiring`; full unit
  sweep 10723 pass / 101 skip / 0 fail.

### Agent Guidance
- When adding a new form-field type rendering, check BOTH `_build_form_fields` and
  `_build_form_sections` in `template_compiler.py` — the wizard path is a separate
  code path that easily gets left behind. The cycle 236 fix caught the missing
  cycle 232 date-default in the wizard path as a side effect.

## [0.55.35] - 2026-04-15

### Fixed
- **manwithacat/dazzle#777: list routes leaked bare ``*_id`` columns instead of
  eagerly loading ref relations.** Two bugs combined to break eager
  loading whenever a DSL ref field was named with an ``_id`` suffix
  (the common case — ``device_id: ref Device``, ``reported_by_id: ref
  Tester``, etc.):

  1. ``entity_converter.convert_entity`` synthesised a ``RelationSpec``
     whose ``name`` was the **raw field name** (``"device_id"``). That
     short-circuited the implicit-relation path in
     ``RelationRegistry.from_entities`` which would otherwise have
     registered the natural short name ``"device"``. App factory's
     ``entity_auto_includes`` strips the ``_id`` suffix and asks for
     ``"device"``, so ``get_relation("IssueReport", "device")`` missed
     and ``load_relations`` silently ``continue``d past every ref
     relation. Result: the registry held ``device_id`` but the runtime
     asked for ``device``, so no nested data was ever attached.
  2. Even after the first bug was fixed, the list-route handler applied
     ``json_projection`` to strip fields not listed by the surface —
     and the allow-list omitted any auto-include relation names. Keys
     that ``load_relations`` had successfully populated on the row dict
     were then filtered out before serialization, so the client saw
     only the scalar columns the surface declared.

  The fix deletes the redundant converter synthesis so
  ``RelationRegistry.from_entities`` becomes the sole authoritative
  builder of implicit relations (one code path, consistent naming), and
  teaches ``create_list_handler`` to union ``auto_include`` into the
  projection allow-list so eager-loaded nested data survives to the
  wire. Evidence: fieldtest_hub ``/issuereports`` list response went
  from ``{device_id: "..."}`` (no nested data) to ``{device_id: "...",
  device: {id, name, model, ...}}`` with a freshly inserted row whose
  FK actually resolved. Note: pre-existing seed rows in fieldtest_hub
  have orphan FKs (deterministic uuid5 IDs that don't match the uuid4
  Device rows) — that's a demo-data gap, not a framework bug.

### Added
- 11 new regression tests in ``tests/unit/test_ref_eager_loading_777.py``
  covering: converter no longer synthesises ``RelationSpec`` from ref
  fields, ``RelationRegistry.from_entities`` strips ``_id`` and keeps
  the raw field name as the FK column, raw-column lookups miss by
  design, json_projection unions ``auto_include``, and four
  parametrised cases covering the common naming patterns
  (``device_id``, ``reported_by_id``, ``assigned_to_id``, ``owner``).

### Agent Guidance
- When adding a DSL ref field, there is now a **single** source of
  truth for the relation name surfaced at runtime:
  ``RelationRegistry.from_entities`` in
  ``src/dazzle_back/runtime/relation_loader.py``. It strips a single
  trailing ``_id`` from the field name to produce the relation key and
  keeps the raw field name as ``foreign_key_field``. The entity
  converter no longer emits ``RelationSpec`` entries from ref fields —
  do not re-add that shortcut, it reintroduces the naming collision
  with ``entity_auto_includes``.

## [0.55.34] - 2026-04-15

### Fixed
- **manwithacat/dazzle#775: sidebar nav showed inaccessible workspace links.** The
  enforcement path (``_workspace_handler``) and the sidebar nav
  generator (``template_compiler``) were using **two different rules**
  to decide who could see each workspace:

  | Path | Rule when no explicit ``access:`` declaration |
  |---|---|
  | Enforcement | only personas whose ``default_workspace == ws.name`` |
  | Sidebar nav | all personas |

  So in apps like ``support_tickets`` that declare no explicit
  ``access:`` on their workspaces (it relies on ``persona
  default_workspace`` instead), the sidebar showed every persona every
  workspace link, but clicking any non-default workspace returned 403.
  4-app cross-cycle evidence from cycles 199/201/216/217 of the
  ``/ux-cycle`` autonomous loop.

  The fix introduces ``workspace_allowed_personas`` in
  ``src/dazzle_ui/converters/workspace_converter.py`` as the **single
  source of truth** for "who can see this workspace". Both the
  enforcement path in ``page_routes.py`` and the sidebar nav generator
  in ``template_compiler.py`` now call it, so they agree byte-for-byte.

  Resolution order inside the helper:
  1. Explicit ``access.allow_personas`` — returned verbatim
  2. Explicit ``access.deny_personas`` — inverted against the full persona list
  3. Implicit ``persona.default_workspace`` — personas claiming this workspace
  4. Fallback: return ``None`` meaning "no filter, visible to everyone"

  The fallback preserves backward compatibility for workspaces that
  predate the ``default_workspace`` attribute.

### Added
- 12 new unit tests in ``tests/unit/test_workspace_allowed_personas.py``
  covering all four rules, edge cases (empty access object, access=None,
  deny-all, no personas), and an end-to-end fixture matching the actual
  ``support_tickets`` shape that originally surfaced #775.
- End-to-end verification against live ``support_tickets`` with a fresh
  ``ModeRunner`` subprocess:
  - agent sees only ``ticket_queue``
  - customer sees only ``my_tickets``
  - manager sees only ``agent_dashboard``
  - zero ghost links

### Agent Guidance
- **Use ``workspace_allowed_personas`` whenever you need to decide who
  can see a workspace.** This is now the single source of truth. Don't
  reintroduce inline rules in new code paths. If a new scenario needs
  a different rule, extend the helper.



### Fixed
- **manwithacat/dazzle#774: silent create-form failure.** Create handlers now auto-inject
  `current_user` into any required `ref User` field that the DSL create
  surface omits. Before this fix, an entity declaring `created_by:
  ref User required` whose `surface ... mode: create` section didn't
  include `created_by` would produce a pydantic "Field required"
  validation error on a field the user was never shown. The fix adds
  `inject_current_user_refs` helper in
  `src/dazzle_back/runtime/route_generator.py` and a new
  `user_ref_fields` parameter on `create_create_handler`. The call site
  in `RouteGenerator.generate_route` computes `user_ref_fields` from
  the existing `entity_ref_targets` map (filtering to targets named
  `User`) so no new wiring is required at the config level.

  Injection rules (all must hold):
  1. `current_user` is non-empty (we know who to inject)
  2. The field is listed in `user_ref_fields` (entity has a `ref User`)
  3. The field exists on the pydantic input schema
  4. The field is declared required on the schema
  5. The body does NOT already supply an explicit value

  The helper never overrides an explicit body value and never injects
  for optional fields.

### Added
- 9 new unit tests in `tests/unit/test_create_user_ref_injection.py`
  covering all five injection rules, multi-field injection, unknown
  field-name tolerance, and explicit-null-triggers-injection semantics.
- End-to-end verification against `support_tickets` with a fresh
  `ModeRunner` subprocess: submitting the Ticket create form with only
  Title + Description now returns 200 OK + HX-Redirect to the new
  ticket's detail page. The core #774 defect is closed.

### Filed
- **manwithacat/dazzle#778 — auth-user ↔ User entity bridge gap.** Surfaced while
  verifying the #774 fix end-to-end. The QA magic-link flow provisions
  dev personas into the `users` auth store but not into the `User`
  domain entity, so any `ref User` FK fails validation even after
  `current_user` is injected correctly. Distinct from #774 — the
  injection is correct, but the injected UUID has no matching User
  entity row. Manual workaround: `INSERT INTO "User" ...` with the
  auth user's UUID. Framework fix direction sketched in the issue.



### Added
- **Cycle 219 — framework maturity assessment.** Synthesised the
  autonomous /ux-cycle loop's 20 cycles (198-218) + targeted
  investigations into a qualitative assessment of where the Dazzle
  framework stands. Written at a natural pause point where the loop
  has surfaced enough signal to evaluate from. Lives at
  `dev_docs/framework-maturity-2026-04-15.md`.
- **Cycle 219 — direct investigation of cycle-217 EX-017 (data-table
  formatter bug).** Code-level + API-level reproduction confirmed:
  - Real bug: list routes don't eagerly load ref relations. Template
    compiler strips `_id` from col_key expecting joined dict
    (`item['device']`) that never arrives; server dict has
    `device_id` (UUID).
  - Second real bug: `datetime auto_add` not honored in seed data —
    `reported_at: None` on every IssueReport row via `/issuereports`
    JSON API.
  - Cycle-218 EX-021 (contact_manager blank cells) is a
    **false positive** — `/app/contact` renders 11 rows with correct
    content; subagent's `visible_text` extraction likely caught
    `<template x-if>` inert content or filter-bar selects.
- **Filed manwithacat/dazzle#777** with the ref-eager-load investigation + fix
  direction sketch. Fourth framework-level issue surfaced by the loop
  this session (manwithacat/dazzle#774 silent-submit, #775 sidebar-nav, #776
  404-chrome-eject CLOSED, #777 ref-eager-load).

### Changed
- `dev_docs/ux-backlog.md` EX-017 flagged as FILED→#777 with
  root-cause summary.
- `dev_docs/ux-backlog.md` EX-021 flagged as VERIFIED_FALSE_POSITIVE
  with substrate-level explanation for future subagent cycles to
  reference.

### Framework maturity verdict (from the assessment doc)

**Composite rating: 3 / 5** — usable for prototyping and internal apps
today, but 3 open framework-level defects (#774, #775, #777) would
each block a real customer-facing deployment until fixed. Component
design system and discovery substrate are rated 4/5; write-path
correctness is rated 2/5 because of the silent-submit gap. See the
full assessment doc for the per-axis breakdown and the recommended
focus order for the next framework work.



### Fixed
- **manwithacat/dazzle#776: 404/403 pages under `/app/*` now render inside the
  authenticated app shell.** Previously `site/404.html` and
  `site/403.html` (which extend the marketing site layout) were
  rendered unconditionally for every error, so a logged-in user
  hitting a bad record URL (`/app/contact/bad-id`) or a forbidden
  workspace (`/app/workspaces/forbidden`) was dropped into the public
  marketing chrome with `Sign In` / `Get Started` nav links. Every
  Dazzle example app exhibited this (5-app cross-cycle evidence from
  cycles 201/213/216/217/218 of the /ux-cycle autonomous loop).

  The fix adds two new templates — `templates/app/404.html` and
  `templates/app/403.html` — which extend `layouts/app_shell.html`
  and render the error markup inside the authenticated sidebar +
  navbar chrome. The exception handler in
  `src/dazzle_back/runtime/exception_handlers.py` now inspects
  `request.url.path`: if it starts with `/app/` (or is exactly
  `/app`), the in-app variant is rendered; otherwise the existing
  marketing-site variant is rendered. API requests still return JSON
  regardless of path.

  The in-app error page also includes a **"Back to List" /
  "Back to Dashboard" affordance** computed from the request path.
  `/app/contact/bad-id` → `Back to List` (to `/app/contact`);
  `/app/workspaces/forbidden` → `Back to Dashboard` (to `/app`).
  This was a secondary complaint in the cycle-201 EX-004 and
  cycle-217 EX-014 observations: the only recovery affordance was
  "Go Home" which dropped the user on the public landing page.

### Added
- 14 new unit tests in `tests/unit/test_exception_handlers.py` covering
  `_is_app_path` (5 cases), `_compute_back_affordance` (5 cases), and
  the end-to-end dispatch via the registered handler (4 cases: 404
  in-app, 404 marketing, 403 in-app, API request JSON fallback).

### Agent Guidance
- **Error pages under `/app/*` must render inside the authenticated
  shell.** When adding a new error type or status code that browsers
  might hit inside the app, route through
  `_render_app_shell_error(...)` in `exception_handlers.py` rather
  than calling `render_site_page(...)` directly. The in-app variant
  preserves sidebar, persona badge, and logout context; the marketing
  variant does not.



### Added
- **Cycle 218 — explore: contact_manager / user / edge_cases.** Final
  app to receive an edge_cases run; completes the 5-app coverage matrix
  on the new substrate. 15 helper calls, ~64k subsidised tokens, 238s
  wall-clock. **0 proposals + 5 observations** (2 concerning, 1 notable,
  2 minor) ingested as EX-020..024.
- **5th-app cross-confirmation of the 404/403 marketing-chrome eject.**
  `/app/contact/{nonexistent-id}` drops the authenticated user into the
  public marketing chrome with 'Sign In' nav. Now confirmed in
  support_tickets, simple_task, ops_dashboard, fieldtest_hub, AND
  contact_manager — every example app exhibits the bug.
- **2nd-app confirmation of the data-table formatter bug, worse here.**
  `/app/contact` renders 20 row-action link groups with **zero cell
  content**. Embedded version in `/app/workspaces/contacts` renders
  the same entity correctly. Cycle 217 found "-" / blank cells in
  fieldtest_hub; here the entire row body is blank. Same root cause,
  more severe symptom.
- **Important non-finding: UX-046 bulk-action-bar is NOT regressed.**
  The cycle 217 EX-019 finding was specifically about an unfilled
  count slot in the label, not the visibility binding. The bar IS
  properly CSS-hidden without selection. Cycle 217's contract walker
  PASS stands.

### Filed upstream issues
- **manwithacat/dazzle#776 — framework: 404/403 error pages drop authenticated
  users into public marketing chrome.** Filed with 5-app cross-cycle
  evidence: cycles 201/213/216/217/218. Conclusively a framework-level
  layout dispatch bug. Suggested fix sketch included: dispatch error
  templates by URL prefix (`/app/*` → authenticated shell). Sits
  alongside #774 (silent create-form failure) and #775 (sidebar nav
  shows inaccessible links) as the three confirmed framework-level
  defects this session has surfaced.

### Agent Guidance
- **Cross-cycle convergence at N≥5 is conclusive.** When the same
  defect appears in 5 different apps with 5 different personas across
  5 different cycles, it's not a coincidence. File it. Cycle 218 made
  the 404-eject pattern N=5 and triggered the issue filing.
- **The substrate is in a steady state.** Six cycles of explore
  produce real signal but at decreasing per-cycle marginal yield. The
  high-value action now is converting accumulated cross-app signal
  into upstream issues, not running more explore cycles. The session
  has produced enough evidence to act on.



### Added
- **Cycle 217 — explore: fieldtest_hub / engineer / edge_cases.**
  Highest-yield edge_cases run yet. ~18 helper calls, ~61k subsidised
  tokens, 369s wall-clock. **0 proposals + 7 observations** (4
  concerning, 2 notable, 1 minor) — all ingested as EX-013..019:
  - **Two more cross-app convergences** strengthen existing
    framework-level signals:
    - **404/403 → marketing chrome dropout** now confirmed in **four**
      apps (support_tickets EX-003, simple_task EX-008, ops_dashboard
      adjacent EX-010, fieldtest_hub EX-014). This is conclusively a
      framework-level layout dispatch bug, not a per-app issue.
    - **Silent form submit failure** now confirmed in two apps
      (support_tickets manwithacat/dazzle#774, fieldtest_hub EX-018). Same shape as
      the cycle-201 finding.
  - **Genuinely new framework-level findings**:
    - EX-016: data-table FK lookup + datetime formatter both silently
      failing (rendering "-" and blank). The walker observed
      IssueReport rows where Device should be a ref display name and
      Reported At should be a timestamp — both empty. Two formatters,
      not one.
    - EX-019: bulk-action-bar visible without selection AND showing
      "Delete  items" with missing count. **Possible regression of
      UX-046 quality gate 1** (the visibility binding should be
      `bulkCount > 0`). Worth investigating before the next cycle
      adopts the contract for fieldtest_hub.
    - EX-013: sidebar "Issue Board" link unresolvable; fourth
      independent confirmation of the sidebar-403 / nav-mismatch
      pattern.
    - EX-017: empty-state copy "No issues reported yet - great work!"
      contradicts an adjacent region showing 5 issues. Cross-region
      inconsistency in the same workspace.

### Agent Guidance
- **Edge_cases against rich-content apps is qualitatively different
  from edge_cases against empty apps.** Cycle 217 produced 7 findings
  in fieldtest_hub vs cycle 216's 3 in ops_dashboard. The presence of
  seed data + rich region templates makes the difference. Future
  edge_cases cycles should prefer apps where the persona has reachable
  content.
- **EX-019 may be a UX-046 regression.** The bulk-action-bar contract's
  Quality Gate 1 says "When `bulkCount === 0`, the bar is hidden". The
  fieldtest_hub finding says the bar is visible at zero count. Either
  fieldtest_hub uses a stale fragment, or the contract walker on the
  cycle 212 PASS happened to hit a path where the bar was hidden but
  the gate didn't actually verify the negative. Worth a re-verification
  cycle against fieldtest_hub specifically.



### Added
- **Cycle 216 — explore: ops_dashboard / ops_engineer / missing_contracts.**
  11 helper calls, ~70k subsidised tokens, 264s wall-clock. Useful
  **negative result**: 0 proposals + 3 observations. The substrate is
  operating correctly; ops_dashboard simply doesn't expose new
  uncontracted patterns to this persona because (a) the seed is empty,
  (b) ops_dashboard's DSL only uses `list` mode regions and not the
  richer region templates (heatmap, funnel, timeline, tree, metrics,
  progress, diagram, bar_chart) that `src/dazzle_ui/templates/workspace/regions/`
  ships with.
- **Cross-app convergence #3 on the sidebar-403 pattern.** EX-010 in
  ops_dashboard joins EX-002 (support_tickets) and a similar finding
  in cycle 199's manager run. Same shape: nav links visible, persona
  can't actually access. **Three independent confirmations across
  three distinct example apps now make this a framework-level pattern
  worth filing as an issue separately from the cycle-201 issue #775.**
  Possibly the same root cause manifesting at the framework level
  (sidebar generator doesn't filter by `access:` rules).
- 3 new EX rows (EX-010..012): sidebar-403, ops-engineer empty-state
  CTAs invite admin-gated actions, and a minor "no uncontracted
  components visible on the reachable surface" observation.

### Agent Guidance
- **Empty-state runs have low component yield.** Cycle 216 confirms
  what intuition suggested: subagent explore against an app with no
  seed data reaches very few interactive surfaces. Future explore
  cycles should prefer (a) apps with rich seed data, (b) the
  `component_showcase` fixture which exercises every region template
  type, or (c) personas with admin reach. Picking ops_engineer was
  technically correct (it's the persona that owns the workspace) but
  empirically unproductive.
- **Negative results are first-class findings.** Cycle 216 produced
  zero proposals but a strong cross-app convergence signal on the
  sidebar-403 framework-level pattern. Don't treat 0-proposal cycles
  as wasted — the substrate evidence and the cross-cycle confirmation
  are real value.



### Added
- **Cycle 215 — UX-048 theme-toggle contract drafted + Phase B PASS.**
  Contract documents reality vs the cycle-213 proposal: it's a
  **two-state user-explicit toggle** (light ↔ dark), NOT a tri-state
  switcher as PROP-048 originally claimed. The system preference
  (`prefers-color-scheme`) is consulted only as a default seed when
  localStorage has no stored value. Phase B against simple_task:
  `fitness run [admin:40698edc, member:138ebeb6]: 73 findings (36/37),
  degraded=False`.
- **Headline finding: cross-shell sync is broken.** The marketing shell
  uses `localStorage.dz-theme-variant` (vanilla JS in
  `runtime/static/js/site.js`), the in-app shell uses
  `localStorage.dz-dark-mode` (Alpine `$persist` in `app_shell.html`).
  Both write `<html data-theme>` but neither reads the other's key. A
  user toggles dark on the marketing site, logs in, and the app shell
  silently defaults to light. The cycle-213 proposal claimed "single
  source of truth" — that was aspirational, not reality. v2 must
  consolidate to a single key + controller.
- 5 quality gates (toggle attribute swap, persistence within a shell,
  system seed for marketing only, stored pref overrides system, two
  distinct localStorage keys documented as current-broken-state),
  9 v2 open questions led by the cross-shell sync gap and missing
  `aria-pressed`.

### Agent Guidance
- **Contracts must document reality, not the proposal.** Cycle 213's
  PROP-048 claimed tri-state with a single source of truth. The actual
  code is two-state with two stores. The contract describes what
  exists today and flags the divergence as the v2 priority. Future
  cycles should follow this pattern: read the implementation first,
  write the contract against it, list the gaps in Open Questions.



### Added
- **Cycle 214 — triage + UX-047 feedback-widget contract + Phase B PASS.**
  Combined housekeeping + work cycle. Triaged PROP-047 and PROP-048 (the
  cycle 213 explore findings) into UX-047 and UX-048 PENDING rows, then
  immediately drafted the contract for UX-047 feedback-widget and ran
  Phase B against simple_task. The contract documents the **vanilla-JS
  module** at `runtime/static/js/feedback-widget.js` — no Alpine, no
  HTMX, all DOM construction via `document.createElement` for security,
  dedicated CSS file at `runtime/static/css/feedback-widget.css`.
  Auto-captures page snapshot + nav history + JS errors at submit time.
  Rate-limited 10/hour via localStorage with a 24h retry queue for
  failed submits. Phase B against simple_task:
  `fitness run [admin:6fdba764, member:4f8f6262]: 71 findings (36/35),
  degraded=False`. 5 quality gates, 10 v2 open questions including
  ARIA modal semantics, radiogroup chip ARIA, focus trap, live region
  on toast, toast unification with UX-013, DSL-configurable categories,
  screenshot upload, role-based visibility, page-snapshot privacy
  redaction.
- **First explore→triage→specify→QA chain on the new substrate.**
  Cycle 213 found PROP-047, cycle 214 promoted + drafted + verified it
  in a single iteration. UX-048 theme-toggle is now PENDING for the
  next cycle.

### Agent Guidance
- **The /ux-cycle skill's Step 1 doesn't pick up PROP-NNN rows.** When
  cycle N runs Step 6 EXPLORE and produces PROPs, cycle N+1 needs an
  explicit triage step before Step 1 has anything to work on.
  Otherwise the loop runs Step 6 indefinitely and the backlog
  accumulates untriaged PROPs (the failure mode cycle 200 was created
  to prevent). Until /ux-cycle gains a built-in triage step, the
  pattern is: explore N → manual triage (PROP→UX) → /ux-cycle picks
  the new UX-NNN.



### Added
- **Cycle 213 — first explore cycle past the UX-037..046 milestone.**
  Subagent walked `simple_task` as the `member` persona using the
  `missing_contracts` strategy. 11 helper calls, ~74k subsidised tokens,
  207s wall-clock. Surfaced **2 proposals + 2 observations** ingested
  via `ingest_findings`:
  - `PROP-047 feedback-widget` — `dz-feedback-*` floating FAB + popover
    with chip-group category/severity inputs and submit lifecycle.
    Rendered on every authed layout.
  - `PROP-048 theme-toggle` — `#dz-theme-toggle` tri-state persistent
    theme switcher shared across marketing and authed shells.
  - `EX-008 (notable)` — `/app/task/1` 404 renders the public marketing
    chrome ("Sign In", "Go Home") even when the session is still valid.
    Cross-app convergence with cycle-201 EX-003 (same defect in
    support_tickets) — now confirmed at the **framework level**, not a
    per-app issue.
  - `EX-009 (notable)` — Task create form renders `due_date` and
    `assigned_to` as plain `<input>` elements rather than the
    `widget-datepicker` / `widget-search-select` widgets. DSL author
    expectation vs framework form-generation gap. Same shape as the
    cycle-199 manager observation against support_tickets.

### Agent Guidance
- **Cross-app cross-cycle convergence is the highest-quality signal.**
  Two separate subagents, two different apps, same defect: the 404/403
  marketing-chrome behaviour is now confirmed as a framework-level bug,
  not a support_tickets quirk. Same for the form-widget-selection gap.
  Both are stronger candidates for filing as upstream issues than any
  single-cycle finding.



### Added
- **Cycle 212 — UX-046 bulk-action-bar contract drafted + Phase B PASS.**
  Final cycle-198+ subagent-discovered row to reach DONE. `bulkCount`-driven
  visibility with enter/leave transitions, count-pluralised
  "Delete N item(s)" + "Clear selection" escape, parent-controller-owned
  state, muted destructive treatment (8% bg-tint hover, not filled).
  Phase B against support_tickets:
  `fitness run [admin:424f981a, agent:acb76a1d]: 91 findings (43/48),
  degraded=False`. 5 quality gates, 9 v2 open questions including
  Escape-to-clear, live region, in-flight loading state, built-in
  confirmation, multi-action support, selection persistence across
  pagination, select-all-matching, position variant (inline vs
  fixed-bottom), and undo affordance.

### **MILESTONE — UX-037..046 set complete**

All ten cycle-198+ subagent-discovered UX rows are now `DONE / qa:PASS`.
The full `/ux-cycle` substrate has been proven end-to-end on real
content: explore → ingest → triage → SPECIFY → QA, repeated for ten
distinct components across `support_tickets` and `contact_manager`.

| Row | Component | Cycle DONE | Canonical |
|---|---|---|---|
| UX-037 | workspace-detail-drawer | 205 | contact_manager |
| UX-038 | workspace-card-picker | 206 | support_tickets |
| UX-039 | workspace-tabbed-region | 207 | support_tickets |
| UX-040 | kanban-board | 204 | support_tickets |
| UX-041 | column-visibility-picker | 208 | support_tickets |
| UX-042 | activity-feed | 209 | support_tickets |
| UX-043 | inline-edit | 203 | support_tickets |
| UX-044 | dashboard-region-toolbar | 210 | support_tickets |
| UX-045 | dashboard-edit-chrome | 211 | support_tickets |
| UX-046 | bulk-action-bar | 212 | support_tickets |

The next `/ux-cycle` invocation will fall through Step 1's PENDING
priority and enter Step 6 EXPLORE (or hit the explore budget short-circuit
if the session counter is exhausted).

## [0.55.23] - 2026-04-15

### Added
- **Cycle 211 — UX-045 dashboard-edit-chrome contract drafted + Phase B PASS.**
  Five-state save lifecycle (clean / dirty / saving / saved / error) with
  state-driven `:class` binding on the Save button, Reset button, and
  Add Card affordance opening the UX-038 picker. Treats the top-of-grid
  Reset+Save toolbar and the bottom-of-grid Add Card button as one
  composite component because they share the same `saveState` flag.
  Phase B against support_tickets:
  `fitness run [admin:af51414a, agent:e95819ab]: 88 findings (44/44),
  degraded=False`. 5 quality gates, 9 v2 open questions including the
  cycle-199 cross-persona "Saved" label ambiguity (flagged by both the
  agent and manager personas), missing live region for save-state
  announcements, missing `aria-expanded` on Add Card trigger, Reset
  confirmation dialog, auto-save, save shortcut key, multi-step undo,
  and a confirm-on-leave navigation guard. Ninth cycle-198+
  subagent-discovered row to DONE. **One row remaining (UX-046
  bulk-action-bar).**



### Added
- **Cycle 210 — UX-044 dashboard-region-toolbar contract drafted + Phase B PASS.**
  Per-region toolbar (title + region-actions + CSV export + multi-filter
  `<select>` bar) that recurs above each workspace region body. HTMX
  `hx-include="closest .filter-bar"` ties multi-filter coordination
  together. No Alpine. Phase B against support_tickets:
  `fitness run [admin:42c1d3cf, agent:1c6f1a9d]: 99 findings (50/49),
  degraded=False`. 5 quality gates, 8 v2 open questions. **Notable
  discrepancy with cycle 199 proposal:** the manager-persona observation
  mentioned a collapse/expand eye button but the current code has no
  such affordance — flagged for v2 to decide. Eighth cycle-198+
  subagent-discovered row to DONE.



### Added
- **Cycle 209 — UX-042 activity-feed contract drafted + Phase B PASS.**
  Vertical left-border timeline `<ul>` with primary-coloured bullet
  markers and a relative-time column. Server-rendered, no Alpine,
  optional HTMX click-to-drawer when `action_url` is configured.
  Three-step display-field fallback chain (`description` → `action`
  → `title`). Phase B against support_tickets:
  `fitness run [admin:35d368e4, agent:cdc0c4ae]: 97 findings (48/49),
  degraded=False`. 5 quality gates, 8 v2 open questions including
  severity-tinted bullets, keyboard accessibility (entries are
  `<div>` not `<button>`), drawer auto-open, time-format
  pluggability. Seventh cycle-198+ subagent-discovered row to DONE.



### Added
- **Cycle 208 — UX-041 column-visibility-picker contract drafted + Phase B PASS.**
  ARIA `role="menu"` + `role="menuitemcheckbox"` popover dropdown
  triggered by a "Columns" button in the data-table header. Conditional
  render guarded by `>3 columns`, parent-controller-owned state, no
  server endpoints. Phase B against support_tickets:
  `fitness run [admin:c79c3a35, agent:cea9824b]: 93 findings (45/48),
  degraded=False`. 5 quality gates, 8 v2 open questions including the
  cycle-199-flagged hardcoded threshold (EX-006), missing persistence,
  Escape close, and arrow-key navigation. Sixth cycle-198+
  subagent-discovered row to DONE.



### Added
- **Cycle 207 — UX-039 workspace-tabbed-region contract drafted + Phase B PASS.**
  ARIA `role="tablist"` strip with eager-load on the first tab and
  `intersect once` lazy load on the rest, DOM-classList state (no
  Alpine), inline onclick handler. Phase B against support_tickets:
  `fitness run [admin:2d196ba9, agent:f718e131]: 95 findings (47/48),
  degraded=False`. 5 quality gates, 7 v2 open questions including a
  significant accessibility cluster (anchors not keyboard-focusable,
  missing `aria-selected`, missing `role="tabpanel"`, missing live
  region). Fifth cycle-198+ subagent-discovered row to DONE.



### Added
- **Cycle 206 — UX-038 workspace-card-picker contract drafted + Phase B PASS.**
  Pure-presentation Alpine popover catalog over a server-supplied
  `catalog` array, parent-owned state model (`showPicker`, `catalog`,
  `addCard` on the dashboard editor controller). 5 quality gates,
  7 v2 open questions (ARIA `role="menu"`, focus management, Escape,
  auto-close after add, search filter, keyboard nav, position
  fallback). Phase B against support_tickets:
  `fitness run [admin:569bad2e, agent:e3af653e]: 93 findings (44/49),
  degraded=False`. Fourth cycle-198+ subagent-discovered row to DONE.



### Added
- **Cycle 205 — UX-037 workspace-detail-drawer contract drafted + Phase B PASS.**
  Contract at `~/.claude/skills/ux-architect/components/workspace-detail-drawer.md`:
  permanently-mounted right-anchored drawer with a plain-JS `window.dzDrawer`
  imperative API (no Alpine), three-way interaction model (close /
  expand-to-full / internal-navigate), HTMX content slot at
  `#dz-detail-drawer-content`. 5 quality gates (open via API, Esc close,
  backdrop close, internal-link interception, expand-href update),
  7 v2 open questions including the `href="#"` accessibility gap that
  cycle 198 originally flagged. Phase B against contact_manager:
  `fitness run [admin:562dddac, user:1dc5de59]: 20 findings (10/10),
  degraded=False`. Both personas reached the workspace anchor.



### Added
- **Cycle 204 — UX-040 kanban-board contract drafted + Phase B PASS.**
  Contract at `~/.claude/skills/ux-architect/components/kanban-board.md`:
  read-only horizontally-scrolling column board grouped by enum field,
  HTMX-into-`workspace-detail-drawer` on card click (no drag-and-drop
  in v1), Load-all overflow handling, server-owned state. Inherits
  card chrome from `region-wrapper` (UX-035). 5 quality gates
  (multi-column rendering, card→drawer routing, ref-link
  stopPropagation, Load-all reload, empty-state passthrough), 6 v2
  open questions deferred (card semantics for accessibility,
  horizontal keyboard scroll, drag-and-drop, non-enum grouping, WIP
  limits, scroll-position memory).
- **UX-040 advanced to `DONE / qa:PASS`** via the same Phase B
  fitness contract walk pattern cycle 203 used for UX-043:
  `fitness run [admin:06eae945, agent:ff320c65]: 102 findings total
  (admin=51, agent=51), degraded=False`. Both personas reached
  `/app/workspaces/ticket_queue` and the walker completed cleanly.
  Second cycle-198+ subagent-discovered row to reach DONE.

### Agent Guidance
- **Drafting a contract from existing code is a tight loop.** Cycle
  204 took ~10 minutes wall-clock from "find the template" to "Phase
  B PASS shipped" because the implementation already matched the
  contract semantics — only the documentation was missing. When
  drafting future contracts for cycle 200's promoted rows, look for
  this pattern: read the template, describe what it does, run Phase
  B, ship.

## [0.55.15] - 2026-04-15

### Changed
- **Cycle 203 — UX-043 inline-edit Phase B PASS, advanced to DONE.**
  Multi-persona fitness-engine contract walk against `support_tickets`
  with `personas=["admin", "agent"]`:
  `fitness run [admin:f9c7e3c1, agent:0e8a0f37]: 88 findings total
  (admin=41, agent=47), degraded=False`. PASS under the cycle-156
  `degraded`-based rule — the 88 findings are Pass 2a story_drift /
  spec_stale observations from `support_tickets`'s overall app
  health, orthogonal to the contract walk. The walker (`walk_contract`)
  itself emits zero findings; it only records ledger steps. Both
  personas reached the inline-edit anchor (`/app/ticket`) and the
  walker completed cleanly.
- **First cycle-198+ subagent-discovered UX row to reach `DONE`.**
  Full chain executed in this session: cycle 199 explore (proposal)
  → cycle 200 triage (PROP-043 → UX-043) → cycle 202 contract draft
  → cycle 203 Phase B PASS. The `/ux-cycle` substrate is now end-to-end
  proven for at least one component.

### Agent Guidance
- **Phase B is `degraded`-based, not `findings_count`-based.** The
  cycle 156 fix established this rule; cycle 203 is the first time
  it's been applied to a brand-new contract walked for the first
  time. 88 fitness findings sound alarming but the walker emitting
  zero of them is what matters. Don't fail a row on `findings_count`.

## [0.55.14] - 2026-04-15

### Added
- **Cycle 202 — first contract drafted for a cycle-199/200 promoted row.**
  `UX-043 inline-edit` has a contract at
  `~/.claude/skills/ux-architect/components/inline-edit.md` (in the
  ux-architect skill, not the Dazzle repo). Scope: 4 field types
  (text / bool / badge / date), mutually-exclusive `editing` state on
  the `dzTable` Alpine controller, phase-based lifecycle
  (display → editing → saving → success/error). Includes 5 testable
  quality gates (activation, mutual exclusion, commit round-trip,
  error retry, keyboard-only completion) and a documented server
  contract (`PATCH /api/{entity}/{id}/field/{col}`).
- `UX-043` status in `dev_docs/ux-backlog.md` advanced:
  `PENDING / contract:MISSING / impl:PENDING / qa:PENDING` →
  `READY_FOR_QA / contract:DONE / impl:DONE / qa:PENDING`. `impl:DONE`
  because existing code in `fragments/inline_edit.html`,
  `fragments/table_rows.html`, and `dz-alpine.js` already matches
  the drafted contract — the contract was written to reflect current
  behaviour, not to drive a refactor. First UX-037..046 row to advance
  past PENDING.

### Agent Guidance
- **Draft contracts against the existing implementation when possible.**
  When a component already exists in code (as `inline-edit` did), the
  contract should describe current behaviour rather than propose a
  rewrite — that way `impl:DONE` can be set in the same cycle and the
  row advances straight to READY_FOR_QA. Only mark `impl:PENDING` if
  the current code genuinely needs a refactor to match the contract.
- **Open questions belong in the contract.** Things that are
  deliberately deferred (refocus-after-reload, confirm-mode for
  selects/checkboxes, optimistic updates, bulk-edit, hint tooltips
  for inline-edit) live in the contract's "Open Questions for vNext"
  section. They are not implementation TODOs — they are design
  decisions the v1 contract explicitly declines to make.

## [0.55.13] - 2026-04-15

### Changed
- **Cycle 201 defects filed as GitHub issues.** The two concerning-severity
  observations from cycle 201's edge_cases run against `support_tickets`
  have been filed outside the UX backlog:
  - [#774](https://github.com/manwithacat/dazzle/issues/774) — silent create-form failure on `/app/ticket/create`. Root cause identified: the `ticket_create` surface omits `created_by: ref User required` (from the `Ticket` entity on line 64 of `examples/support_tickets/dsl/app.dsl`), so the backend rejects submissions, and the UI doesn't surface the error. Matches historical cycle 110/126/137 observations about the same underlying bug.
  - [#775](https://github.com/manwithacat/dazzle/issues/775) — sidebar nav shows workspace links that the current persona cannot actually access (403). Cross-persona confirmed: cycle 199 manager run and cycle 201 agent run independently flagged this.
- Updated `EX-002` and `EX-007` rows in `dev_docs/ux-backlog.md` with
  `FILED→#NNN` status and issue cross-links so future diagnosticians can
  trace the backlog row to the upstream issue.

### Agent Guidance
- **Edge-case findings that are real defects belong in GitHub issues,
  not the UX backlog.** The UX backlog is for components to bring under
  ux-architect governance; edge-case findings that turn out to be
  genuine app-level bugs should be promoted to issues with a
  `FILED→#NNN` breadcrumb in the backlog row.

## [0.55.12] - 2026-04-15

### Added
- **`select` action for `playwright_helper`.** The stateless Playwright
  driver used by subagent-driven explore runs can now drive `<select>`
  elements. Signature:
  `python -m dazzle.agent.playwright_helper --state-dir DIR select '<selector>' '<value>'`.
  Attempts to match `value` as an option `value` attribute first; on
  failure, falls back to matching as a visible label. Returns
  `matched_by: "value" | "label"` so callers know how the option was
  resolved.
- Driven by the cycle 201 edge_cases run against `support_tickets` —
  the subagent explicitly flagged that it couldn't drive `<select>`
  elements, which blocked root-causing the silent create-form failure
  (finding EX-007). With this action in place, the next edge_cases
  run can fully exercise forms that use `<select>` for Priority,
  Category, or any DSL enum field.
- 3 new unit tests in `tests/unit/agent/test_playwright_helper.py`
  covering the value-first happy path, the label fallback, and the
  double-failure error shape (17 tests total).

### Agent Guidance
- **Use `select` instead of `click` for `<select>` elements.** Clicking
  a `<select>` opens the native picker but doesn't let the caller
  choose an option. `select '<selector>' '<value>'` resolves the
  option deterministically.

## [0.55.11] - 2026-04-15

### Changed
- **Cycle 201 — first production `edge_cases` explore run.** Ran
  the strategy shipped in v0.55.8 against `support_tickets/agent`
  using the `ingest_findings` writer shipped in v0.55.9. End-to-end
  dogfooding of the full explore-ingest pipeline. The subagent
  surfaced 6 observations (2 concerning, 3 notable, 1 minor) and
  `ingest_findings` wrote them as `EX-002..007` in one call without
  hand-editing.
- The concerning-severity findings include a **suspected silent
  create-form failure** on `/app/ticket/create` (EX-007) — filling
  Title + Description and clicking Create produces no toast, no URL
  change, no state-change signal, and the ticket list still reads
  "No items found" afterwards. Potential data-loss dead-end on the
  support agent's core workflow.
- Three findings cross-confirmed earlier persona-runs (sidebar RBAC
  mismatch, dead `Open full page` affordance, free-text Assigned-To
  field), strengthening the signal on those issues independently of
  any single LLM's interpretation.

### Agent Guidance
- **The `ingest_findings` writer is proven in production.** Future
  `/ux-cycle` Step 6 runs should call it directly instead of
  hand-writing PROP/EX rows. First-try success: schema matched the
  hand-written cycle 199 rows byte-for-byte in the relevant columns.
- **`edge_cases` strategy produces observations, not proposals.**
  Cycle 201 wrote 0 proposals and 6 observations — exactly the shape
  the strategy section promises. Don't run `edge_cases` if you're
  trying to grow the contract backlog; run it if you're trying to
  surface friction on existing surfaces.
- **Follow-up: `playwright_helper` lacks a `select` action.** The
  subagent explicitly called this out as a mission-limiting gap —
  it couldn't drive `<select>` elements, which blocked isolation of
  the EX-007 silent-submit root cause. Worth adding in a later
  cycle.

## [0.55.10] - 2026-04-15

### Changed
- **Cycle 200 triage: 10 PROP rows promoted to UX-037..046.** All ten
  proposals produced by cycles 198+199 (`workspace-detail-drawer`,
  `workspace-card-picker`, `workspace-tabbed-region`, `kanban-board`,
  `column-visibility-picker`, `activity-feed`, `inline-edit`,
  `dashboard-region-toolbar`, `dashboard-edit-chrome`,
  `bulk-action-bar`) passed the three overlap tests — no existing
  contract subsumes them, no two proposals collapse into one, and the
  two that are popover consumers (`column-visibility-picker`,
  `workspace-card-picker`) warrant their own contracts for drift
  prevention. Each `PROP-NNN` row in
  `dev_docs/ux-backlog.md` is now marked `PROMOTED→UX-NNN`, and the
  ten new `PENDING / contract:MISSING` rows sit at the top of the
  `/ux-cycle` Step 1 priority queue for the next cycle.

### Agent Guidance
- **The explore/triage ratio matters.** Cycles 198+199 produced 10
  proposals in 4 persona-runs; cycle 200 triaged them in one pass.
  Don't run another fan-out until the triage queue has been worked
  down at least to first-draft contracts — otherwise the backlog
  just accumulates untriaged noise.

## [0.55.9] - 2026-04-15

### Added
- **`subagent_ingest` helper — automates `/ux-cycle` Step 9 backlog
  writes.** New module
  `src/dazzle/cli/runtime_impl/ux_cycle_impl/subagent_ingest.py`
  exposes `PersonaRun`, `IngestionResult`, and `ingest_findings(...)`.
  Takes a list of per-persona `SubagentExploreFindings`, parses the
  existing `dev_docs/ux-backlog.md` to find the highest existing
  `PROP-NNN` and `EX-NNN` IDs, dedupes proposals by `component_name`
  against the existing table, formats new rows (escaping pipes,
  flattening multi-line descriptions), and appends them after the
  last existing data row in each table. Callers get back an
  `IngestionResult` with added row counts, dedup skips, and
  warnings.
- **13 unit tests** in `tests/unit/test_subagent_ingest.py` covering
  ID allocation, in-call dedup, cross-cycle dedup, row formatting,
  pipe escaping, multi-line flattening, empty-input no-ops,
  single-persona proposals-only runs, and insertion-order
  preservation against unrelated sections.

### Changed
- **`.claude/commands/ux-cycle.md` Step 9 rewritten** to call
  `ingest_findings(...)` from a one-shot `python -c` block instead of
  narrating the manual "find the next ID, write a row, dedup by name"
  dance. The log entry (`ux-log.md`) is still written by hand —
  interpretive prose doesn't benefit from automation.

### Agent Guidance
- **When walking the `/ux-cycle` Step 6 playbook, use
  `ingest_findings` instead of hand-writing backlog rows.** It's
  faster, dedups correctly, and produces consistently-formatted rows
  that the next cycle's ingestion will parse without surprises.

## [0.55.8] - 2026-04-15

### Added
- **`edge_cases` strategy for `build_subagent_prompt`.** Second
  strategy for the cycle-198 subagent-driven explore path. Where
  `missing_contracts` hunts for uncontracted component patterns, the
  `edge_cases` strategy directs the subagent to probe friction and
  defects: empty/error/boundary states, dead-end navigation,
  affordance mismatches (clickable-looking elements that do nothing,
  spinners that never resolve), copy/persona mismatches, and stale
  post-navigation state. Output skews toward observations rather than
  proposals, with explicit severity guidance (concerning / notable /
  minor).
- Strategy dispatch is now validated: unknown strategy literals raise
  `ValueError` with a clear message. Previously the module raised
  `NotImplementedError` unconditionally for anything other than
  `missing_contracts`.
- Test coverage expanded: 6 new tests in
  `tests/unit/agent/test_ux_explore_subagent.py` covering edge-case
  section content, observation-skewing guidance, strategy
  non-bleed-through, and the ValueError path (16 tests total, all
  passing).

### Changed
- `.claude/commands/ux-cycle.md` Strategy Rotation section — removed
  the "not yet implemented, falls back to missing_contracts"
  disclaimer for even-numbered explore cycles. Even cycles now
  actually run the edge_cases strategy.

### Agent Guidance
- **Even-numbered explore cycles now run the `edge_cases` strategy**
  for real. If you're orchestrating `/ux-cycle` from the runbook,
  pass `strategy="edge_cases"` to `build_subagent_prompt` on even
  counts and expect the subagent's findings to be mostly
  observations, not proposals.

## [0.55.7] - 2026-04-15

### Removed
- **Cycle 197 explore path retired.** Deleted ~2100 lines of dead code
  that supported the pre-cycle-198 DazzleAgent-on-SDK explore path.
  Specifically:
  - `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py`
    (480 lines) — the `run_explore_strategy` entry point and the
    `ExploreOutcome` dataclass.
  - `src/dazzle/agent/missions/ux_explore.py` (222 lines) — the
    `build_ux_explore_mission`, `make_propose_component_tool`, and
    `make_record_edge_case_tool` helpers. Not to be confused with
    `ux_explore_subagent.py`, which is the live subagent path added
    in 0.55.5.
  - `src/dazzle/mcp/server/handlers/discovery/explore_spike.py` (192
    lines) — the cycle-198 Path-γ MCP-sampling spike handler. The
    spike proved Claude Code doesn't implement `sampling/createMessage`,
    so the handler is no longer useful.
  - The `discovery.explore` MCP operation, its enum entry, and its
    parameter schema in `tools_consolidated.py` / `handlers_consolidated.py`.
  - Four test files: `tests/unit/test_explore_strategy.py`,
    `tests/unit/test_ux_explore_mission.py`,
    `tests/unit/mcp/test_discovery_explore_spike.py`, and
    `tests/e2e/test_explore_strategy_e2e.py`.
- The live explore path is now the subagent-driven playbook documented
  in `.claude/commands/ux-cycle.md` Step 6, which uses
  `src/dazzle/agent/missions/ux_explore_subagent.py` and
  `src/dazzle/cli/runtime_impl/ux_cycle_impl/subagent_explore.py`.
  The fitness strategy (`fitness_strategy.run_fitness_strategy`) is
  unaffected and still uses `_playwright_helpers.py`.

### Agent Guidance
- **The `discovery` MCP tool now exposes only the `coherence`
  operation.** If you need explore, use the subagent-driven playbook
  via `/ux-cycle` Step 6 — not an MCP operation.

## [0.55.6] - 2026-04-15

### Added
- **Cycle 199 — multi-persona fan-out validated.** Walked the cycle 198
  subagent-driven explore playbook three times against
  `examples/support_tickets`, once per business persona (agent, customer,
  manager). Result: **9 non-overlapping proposal candidates**
  (`PROP-038..046`) plus 7 observations, including two cross-persona
  convergences (workspace save-state label ambiguity; RBAC nav/scope
  inconsistency). Total subsidised cost: ~223k tokens across 40 helper
  calls in 801s wall-clock — roughly 3× a single-persona run with zero
  hidden multipliers. The `existing_components` filter was fed each
  persona the running set of contracts already proposed in the cycle so
  later personas didn't duplicate earlier ones; zero duplicates across
  9 proposals.
- **9 new `PROP-NNN` rows** in `dev_docs/ux-backlog.md`:
  `workspace-card-picker`, `workspace-tabbed-region`, `kanban-board`,
  `column-visibility-picker`, `activity-feed`, `inline-edit`,
  `dashboard-region-toolbar`, `dashboard-edit-chrome`, `bulk-action-bar`.
  Each includes a specific selector hint, the persona that found it,
  and a rationale for why existing contracts don't cover it.

### Agent Guidance
- **Multi-persona fan-out is a playbook concern, not a code concern.**
  `init_explore_run(persona_id=...)` + `playwright_helper login <persona>`
  is the entire per-persona setup. No shared-state races, no state-dir
  clobbering. Each run gets its own `dev_docs/ux_cycle_runs/<example>_<persona>_<run_id>/`.
- **Pass the running set of proposed components into
  `build_subagent_prompt(existing_components=...)`** on each subsequent
  persona-run in a cycle, so later personas don't re-propose what
  earlier personas already found.

## [0.55.5] - 2026-04-15

### Added
- **Cycle 198 — substrate pivot for `/ux-cycle` Step 6 EXPLORE.** Replaces the
  DazzleAgent-on-direct-SDK explore path with a Claude Code Task-tool subagent
  driving a stateless Playwright helper via Bash. Cognitive work runs inside
  the Claude Code host subscription (Max Pro 20) — the metered Anthropic SDK
  is eliminated from the explore path.
- **`src/dazzle/agent/playwright_helper.py`** — stateless one-shot Playwright
  driver. Actions: `login`, `observe`, `navigate`, `click`, `type`, `wait`.
  Each call is a subprocess that loads state (storage_state + base_url +
  last_url) from `--state-dir`, performs one action, and saves state back.
  Session cookies persist across calls. Subagent consumers drive it via Bash.
- **`src/dazzle/agent/missions/ux_explore_subagent.py`** —
  `build_subagent_prompt(...)` parameterised mission template. Cycle 198
  ships `missing_contracts` only; `edge_cases` raises `NotImplementedError`
  pending a later cycle.
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/subagent_explore.py`** —
  `init_explore_run`, `ExploreRunContext`, `read_findings`,
  `write_runner_script`. Small composable helpers the outer assistant uses
  to stage state, boot ModeRunner, and read findings. No async orchestrator
  function — Claude Code's Task tool is only reachable from the assistant's
  cognitive loop, so the playbook is assistant-driven.
- **First real `PROP-037` backlog row** — `workspace-detail-drawer`, found by
  the production subagent run against `contact_manager` with persona `user`.
  92k subsidised tokens, 18 helper calls, 416s wall-clock.

### Changed
- **`.claude/commands/ux-cycle.md` Step 6 rewritten** as a 10-step
  subagent-driven playbook. Removed all references to `run_explore_strategy`,
  `DazzleAgent`, and `ANTHROPIC_API_KEY` from the explore path. Claude Code
  host is now a hard dependency for Step 6 (not for walk_contract or fitness,
  which still use DazzleAgent).

### Agent Guidance
- **`/ux-cycle` Step 6 EXPLORE requires a Claude Code host session.** The
  substrate pivot replaces DazzleAgent's `observe → decide → execute` loop
  with Claude Code's built-in Task-tool agent framework. Running Step 6 from
  a non-Claude-Code environment (raw pytest, CI runner without an MCP host)
  is not supported in cycle 198 and won't be until a later cycle decides
  whether to generalise.
- **Stateless Playwright helper pattern for browser-driving subagents.** When
  a mission prompt needs a subagent to interact with a running app, reach
  for `python -m dazzle.agent.playwright_helper --state-dir DIR <action>`
  rather than building a new observer/executor stack. The one-shot
  subprocess pattern (storage_state file + last_url file) is the
  load-bearing trick that lets a stateless Bash-driven subagent maintain
  session continuity.
- **`run_explore_strategy` (the cycle 197 DazzleAgent-based explore driver)
  still exists but is deprecated for explore.** It's kept to avoid breaking
  `tests/e2e/test_explore_strategy_e2e.py` during the migration. Cycle 199
  decides whether to delete it entirely.
- **44 new unit tests cover the substrate.** None use Playwright or launch
  real browsers — the walk-the-playbook production test is the acceptance
  check.

## [0.55.4] - 2026-04-15

### Fixed
- **Cycle 197 — Layer 4 (agent click-loop) structurally resolved.** DazzleAgent
  now sees an explicit state-change signal on every action via the new
  `ActionResult.from_url` / `to_url` / `state_changed` fields, plus action-linked
  console errors via `console_errors_during_action`. `_build_messages` renders
  these in the compressed history block so the LLM sees "NO state change (still
  at /app)" instead of the ambiguous "Clicked X" message. A bail-nudge block is
  appended when 3 consecutive no-ops are detected, explicitly telling the LLM to
  try a different action or call `done`. Verified across 5 example apps with 11
  persona-runs: every run stagnates legitimately (no click-loops) with
  `degraded=False`.

### Added
- **`src/dazzle/agent/executor.py`**: `PlaywrightExecutor` captures before/after
  page state (URL + DOM hash) around every action, attaches a `page.on("console")`
  listener that buffers error-level messages, and diff-slices the buffer into
  each `ActionResult.console_errors_during_action` for action→error attribution.
- **`src/dazzle/agent/core.py`**: module-level pure helpers `_format_history_line`
  and `_is_stuck` (with 12 unit tests), wired into `_build_messages` alongside
  the bail-nudge.
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py`**:
  `pick_explore_personas(app_spec, override=None)` auto-picks business personas
  by filtering out those whose `default_workspace` starts with `_` (framework-
  scoped). `pick_start_path` delegates to `compute_persona_default_routes` for
  per-persona start URLs. `_dedup_proposals` merges proposals by
  `(example_app, component_name)` with a `contributing_personas` list.
  `ExploreOutcome` gains `raw_proposals_by_persona: dict[str, int]` for
  pre-dedup stats.
- **`tests/e2e/test_explore_strategy_e2e.py`**: parametrised D2 verification
  sweep across 5 examples, marked `@pytest.mark.e2e` (excluded from default
  pytest, run manually with `pytest -m e2e`). Writes outcome JSON artefacts to
  `dev_docs/cycle_197_verification/` (gitignored).

### Changed
- **`run_explore_strategy` semantics** (breaking): `personas=None` now
  auto-picks business personas from the DSL (was: anonymous). `personas=[]` is
  the new explicit anonymous escape hatch. `personas=["admin"]` is unchanged.
  `start_path` is now `str | None = None` — if None, each persona gets its
  DSL-computed default route; if provided, that value is used for all personas.
  Aggregated proposals are routed through `_dedup_proposals` at the end.

### Agent Guidance
- **Mission tools must not name-collide with builtin page actions.** As of
  v0.55.2 `DazzleAgent` exposes 8 builtin page actions (navigate/click/type/
  select/scroll/wait/assert/done) as native SDK tools. A mission registering
  `click` (or any builtin name) will have its tool silently dropped with a
  warning — pick a domain-specific name like `click_record_row`.
- **Callers who want anonymous explore must explicitly pass `personas=[]`.**
  Passing `personas=None` now auto-picks business personas from the DSL.
  Existing callers that relied on the old `None → anonymous` semantics need
  updating.
- **Layer 5 known gap (cycle 197 verification).** The Layer 4 fix shipped in
  this release resolved the click-loop pathology, but verification exposed a
  deeper blocker: LLM agents under-invoke `propose_component` even when
  infrastructure permits it. 11 persona-runs across 5 examples produced 0
  proposals despite reaching target pages, taking real actions, and receiving
  state-change feedback. Tracked for cycle 198 follow-up — candidate fixes
  include rewriting the bail-nudge to push toward recording (rather than
  exploration), lowering the stagnation threshold, and A/B testing the
  `ux_explore` mission prompt.

## [0.55.3] - 2026-04-14

### Fixed
- **Integration test assertion stale after v0.55.2 builtin-action merge.**
  `tests/integration/test_agent_investigator_tool_use.py::test_nested_changes_array_arrives_intact`
  asserted `len(call_kwargs["tools"]) == 1` against the `_decide_via_anthropic_tools`
  tools list, which v0.55.2 expanded from "1 mission tool" to "8 builtin page
  actions + 1 mission tool". Two unit tests were updated in the same commit,
  but the integration test was missed by the pre-push local verification
  (`-k "agent or tool_use or explore_strategy or fitness_strategy"` was
  scoped to `tests/unit/`). Fixed by looking up the `propose_fix` entry by
  name and asserting `len == 9`. 10784/10784 Python tests pass. No runtime
  behaviour change from v0.55.2 — the shipped agent code was always correct;
  only the test's expectation was stale.

## [0.55.2] - 2026-04-14

### Fixed
- **DazzleAgent `use_tool_calls=True` page actions were text-protocol only.**
  Before this release, `DazzleAgent(use_tool_calls=True)` exposed mission
  tools as native SDK tools but left page actions (navigate/click/type/
  select/scroll/wait/assert/done) as text-protocol JSON instructions in
  `_build_system_prompt`. The LLM obediently emitted a `navigate` action
  as text JSON, `_decide_via_anthropic_tools` found no `tool_use` block,
  returned a DONE sentinel, and the agent loop exited after 1 step with
  0 actions taken. `walk_contract` dodged this because its anchor
  navigation happens outside the agent loop, but in-loop explore missions
  (`ux_explore` MISSING_CONTRACTS / EDGE_CASES) were completely blocked.

  Fixed by declaring page actions as native SDK tools alongside mission
  tools. New module-level `_BUILTIN_ACTION_NAMES` + `_builtin_action_tools()`
  factory; new `_tool_use_to_action` router that maps builtin-named
  `tool_use` blocks to their matching `ActionType` with target/value/
  reasoning extracted from `block.input`, and mission-tool names to
  `ActionType.TOOL` with `json.dumps(input)` as `value` (matching the
  text-protocol shape so `_execute_tool` consumes it unchanged).
  `_decide_via_anthropic_tools` merges builtin+mission tools into the
  SDK `tools=[...]` parameter; mission tools colliding with builtin
  names are dropped with a warning. `_build_system_prompt` branches on
  `self._use_tool_calls` and suppresses the text-protocol "Available
  Page Actions" block under tool-use mode; legacy text-protocol path
  is untouched. Empirically verified against contact_manager:
  pre-fix = 1 step DONE, post-fix = 8 real click actions via native
  tool use + legitimate stagnation.

### Added
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` —
  production driver for `/ux-cycle` Step 6 EXPLORE.** Before this release,
  `build_ux_explore_mission` existed in `src/dazzle/agent/missions/ux_explore.py`
  but had no production caller — Step 6 was pointing at a function the
  harness could not actually invoke, and cycle 147's "empirical 0 findings"
  data point was produced via a throwaway `/tmp` script. `run_explore_strategy`
  mirrors `run_fitness_strategy`'s structure: caller owns ModeRunner, strategy
  owns Playwright + per-persona login + agent mission + aggregation. Returns
  an `ExploreOutcome` with flat `proposals` / `findings` lists tagged by
  `persona_id`, plus `blocked_personas` for per-persona failures; all-blocked
  raises `RuntimeError`.
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/_playwright_helpers.py` —
  shared Playwright bundle + persona-login helpers** extracted from
  `fitness_strategy.py` so `explore_strategy` can reuse `PlaywrightBundle`,
  `setup_playwright`, and `login_as_persona` without duplication.
  `fitness_strategy` re-imports them under the old private names
  (`_PlaywrightBundle` etc.) to preserve existing test patch targets — 23/23
  `test_fitness_strategy_integration` tests pass unchanged.

### Changed
- **`.claude/commands/ux-cycle.md` Step 6 is now actionable.** Replaced the
  vague "Dispatch the `build_ux_explore_mission`" prose with a concrete
  runnable code snippet using `run_explore_strategy` + `ModeRunner`.
  Documented the semantic gate on the 5-cycle-0-findings rule (housekeeping
  cycles that never reached Step 6 must not count toward the streak;
  track via `explored_at` in `.dazzle/ux-cycle-state.json`).

### Agent Guidance
- **`DazzleAgent(use_tool_calls=True)` now exposes 8 builtin page actions
  as native SDK tools.** If you write new agent missions and use the tool-use
  path, you no longer need to instruct the LLM to emit navigate/click/type/
  etc. as text JSON — the SDK tools list carries that contract. The system
  prompt under tool-use mode omits the legacy "Available Page Actions" text
  block entirely; the legacy text-protocol path for `use_tool_calls=False`
  is unchanged.
- **Mission tool names must not collide with builtin page action names.**
  A mission that registers a tool named `click`, `navigate`, `type`, `select`,
  `scroll`, `wait`, `assert`, or `done` will have its mission tool silently
  dropped with a warning — the builtin wins. Pick a domain-specific name
  (e.g. `click_record_row` instead of `click`).
- **Prefer `run_explore_strategy` over inline ModeRunner + DazzleAgent glue
  for `/ux-cycle` Step 6.** The driver handles per-persona login, blocked-
  persona absorption, aggregation, and persona-tagged proposals out of the
  box. See `.claude/commands/ux-cycle.md` Step 6 for the invocation shape.

## [0.55.1] - 2026-04-14

### Security
- **Magic link redirect validator hardened (CodeQL `py/url-redirection`).**
  `consume_magic_link`'s `?next=` query parameter validation was
  upgraded from `startswith("/") and not startswith("//")` string-prefix
  checks to a `urllib.parse.urlparse`-based validator that catches
  backslash-bypass attacks (`/\@evil.com` — browsers normalize `\` to
  `/` per the WHATWG URL spec, potentially turning the path into a
  protocol-relative URL pointing at an attacker-controlled host), as
  well as scheme injection (`http://`, `javascript:`, `data:`) and
  authority smuggling. 29 new parametrised tests in
  `tests/unit/test_magic_link_routes.py` cover the accepted paths,
  protocol-relative rejection, scheme rejection, backslash-bypass
  rejection, and non-absolute-path rejection. CodeQL alert #58 resolved.

### Changed
- **CI: bump `actions/github-script` v8 → v9 and
  `softprops/action-gh-release` v2 → v3.** Applies Dependabot PRs #772
  and #773. Both are major-version bumps but neither breaking change
  affects this project — our workflows use the injected `github` and
  `context` parameters of `github-script` (no `require('@actions/github')`
  or `const getOctokit` patterns) and our runners (`ubuntu-latest`,
  `macos-14`) support Node 24 natively.

## [0.55.0] - 2026-04-14

### Fixed
- **DazzleAgent bug 5a (prose-before-JSON parse failure).** Claude 4.6
  frequently emits reasoning prose before JSON action blocks. The strict
  `json.loads` parser returned DONE/failure on any prose prefix, killing
  missions at step 1 (cycle 147's EXPLORE stagnation was caused by this).
  `_parse_action` is refactored as a three-tier fallback: (1) try
  `json.loads` on the whole response, (2) extract the first balanced
  JSON object via a new `_extract_first_json_object` bracket counter
  and preserve the surrounding prose in the action's `reasoning` field,
  (3) return a DONE sentinel with diagnostic if no balanced JSON found.
  Fixes bug 5a on all text-protocol paths (direct SDK and MCP sampling).

### Added
- **DazzleAgent `use_tool_calls` kwarg.** Opt-in flag that routes agent
  decisions through Anthropic's native tool use API when running on the
  direct SDK path. Fixes bug 5b (nested-JSON-in-tool-values encoding)
  for tools with nested input shapes. When combined with an
  `mcp_session`, logs a one-shot warning and falls back to the text
  protocol (MCP sampling is text-only). Currently enabled only for the
  investigator's `propose_fix` terminal action; all other missions
  keep the default `use_tool_calls=False` and use the now-robust text
  parser.
- **Investigator `propose_fix` native tool use.** The investigator
  runner now constructs `DazzleAgent(use_tool_calls=True)`, and the
  `propose_fix` schema is extracted into a module-level
  `PROPOSE_FIX_SCHEMA` constant with full item constraints on the
  `fixes` array (required `file_path`, `diff`, `rationale`,
  `confidence` on each fix). Anthropic's API enforces the shape at the
  tool_use boundary, eliminating the stringified-JSON-in-string
  reliability problem.

### Agent Guidance
- **Authoring new agent tools:** every `AgentTool` already has a
  required `schema` field. For tools used on the text protocol, the
  schema is informational (appears in the system prompt). For tools
  used with `use_tool_calls=True`, the schema becomes Anthropic's
  `input_schema` and is enforced at the API boundary. When a tool has
  a nested input structure (arrays of objects, etc.), tighten the
  schema's item constraints and flip `use_tool_calls=True` on the
  agent — the text protocol's nested-JSON encoding is unreliable
  under Claude 4.6 (bug 5b).
- **Reasoning preservation principle:** the raw LLM output (prose
  preambles, scratch notes, the JSON's `reasoning` field, text blocks
  on the tool-use path) all land in `AgentAction.reasoning` with a
  `[PROSE]` marker where appropriate. Downstream analysis tasks can
  extract human-readable justifications from this corpus later. Do
  not strip prose from the reasoning field — it is signal, not noise.

## [0.54.5] - 2026-04-14

### Added
- **Fitness investigator subsystem** — agent-led investigation of ranked
  fitness clusters. `dazzle fitness investigate` reads a cluster from
  `fitness-queue.md`, gathers context via six read-only tools (file reads,
  DSL queries, spec search, cluster expansion, related-cluster lookup),
  and writes a structured `Proposal` to `.dazzle/fitness-proposals/`.
  Read-only at the codebase level — applying proposals is a separate
  (future) actor subsystem. See `docs/reference/fitness-investigator.md`.

### Agent Guidance
- The investigator is the Option-3 ship on the path to full autonomous
  fix loops. Proposals are accumulated on disk but not applied until the
  actor subsystem lands. Run `dazzle fitness investigate --dry-run` to
  inspect a case file without burning tokens.
- Known v1 limitation: DazzleAgent's text-action protocol can't reliably
  produce the complex JSON payload for `propose_fix`; stagnation is a
  common outcome in real runs. Tracked for v2.

## [0.54.4] - 2026-04-13

## [0.54.3] - 2026-04-13

### Added
- **Fitness v1.0.3 — contract anchor navigation.** New optional `## Anchor` section in ux-architect component contracts is parsed into `ComponentContract.anchor: str | None`. The fitness strategy navigates the Playwright page to `site_url + anchor` (with leading-slash normalization) before the contract walker observes the component, closing the v1.0.2 "walker observes about:blank" gap. Existing contracts without the section continue to parse cleanly with `anchor=None`.
- **Fitness v1.0.3 — multi-persona fan-out.** New optional `personas: list[str] | None = None` kwarg on `run_fitness_strategy`. When set, the strategy runs one fitness cycle per persona inside a single subprocess lifetime: shared Playwright browser, fresh `browser.new_context()` per persona for cookie isolation, `_login_as_persona` via the QA mode magic-link flow (#768), per-persona `FitnessEngine`, per-persona outcome. When `personas=None` (default), runs a single anonymous cycle (v1.0.2 backwards compatibility preserved by construction).
- **`_login_as_persona` helper** at `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` — two-step Playwright-driven login reusing the QA mode endpoints from #768. Distinguishes three failure modes with targeted error messages: 404 (QA mode disabled OR persona not provisioned), other non-2xx (generation failed), post-consume URL contains `/login` or `/auth/login` (token rejected).
- **`_aggregate_outcomes` helper** reduces per-persona results into a single `StrategyOutcome`. Single-persona format matches v1.0.2 exactly; multi-persona format uses a bracketed `[admin:r1, editor:r2]` prefix with per-persona finding counts and max-of independence scores. Per-persona failures produce `_BlockedRunResult` outcomes via continue-on-failure semantics — one persona's failure does not abort the loop.

### Changed
- **`_build_engine` refactored** to accept a pre-built Playwright `bundle` parameter instead of creating its own internally. The strategy (`run_fitness_strategy`) now owns bundle lifecycle via outer `try/finally`, allowing the shared browser to be reused across personas. `_EngineProxy.run()` no longer closes the bundle — it simply forwards to `engine.run()`.
- **`/ux-cycle` Phase B runbook** updated to show the `personas=` kwarg with example lists (`["admin", "agent", "customer"]`) and a commented-out anonymous variant. Updated qa field mapping to note that per-persona failures inside a multi-persona run are absorbed into `outcome.degraded=True` rather than raising the whole strategy.

### Agent Guidance
- **Authoring contracts:** new ux-architect component contracts should include a `## Anchor` section with the URL the component lives at (e.g. `/login` for `auth-page`). Contracts without an anchor continue to work — the walker observes whatever page is loaded — but anchor-driven contracts produce more meaningful gate observations. The 35+ existing contracts will be backfilled with anchors as a separate one-shot data migration (not in v1.0.3 source).
- **Multi-persona execution:** when `/ux-cycle` Phase B runs against an in-app component that needs persona-scoped verification, pass `personas=["admin", ...]` matching the example app's DSL persona declarations. For public/anonymous components (auth pages, landing pages), pass `personas=None` (the default) to run a single anonymous cycle. v1.0.4+ may add AppSpec-derived auto-derivation; for v1.0.3, the caller is the source of truth.
- **Per-persona failure semantics:** per-persona failures (login rejected, engine crashed, anchor navigation failed) record `_BlockedRunResult` outcomes that absorb into the aggregated `StrategyOutcome.degraded=True` flag. The strategy only raises when there is nothing useful to return (subprocess failed to start, Playwright bundle couldn't spin up). Phase B `qa` field mapping treats raised strategy errors as `BLOCKED` and per-persona absorbed failures as part of the `FAIL`/`PASS` aggregate.

## [0.54.2] - 2026-04-13

### Added
- **Fitness v1.0.2 — contract-driven Pass 1 walker.** New `walk_contract` mission at `src/dazzle/fitness/missions/contract_walk.py` mirrors the shape of `walker.walk_story` but drives the ledger from a parsed ux-architect `ComponentContract`. Each quality gate becomes one ledger step: expect = gate description, action_desc = `"observe contract gate"`, observed_ui = `await observer.snapshot()`. Deterministic — no LLM calls. Observer is injected via a `Protocol` so unit tests use an in-memory stub and the strategy wraps a Playwright page. Symmetric intent/observation counts per step even on observer errors.
- **`FitnessEngine.contract_paths` + `contract_observer` kwargs.** The engine's Pass 1 loop now iterates contract paths (defaulting to `[]`) after story walks, parsing each via `parse_component_contract` and calling `walk_contract` with the injected observer. Both kwargs default to `None` so existing callers are unaffected. If `contract_paths` is non-empty but `contract_observer` is None, Pass 1 raises `ValueError` loudly rather than silently skipping the walk.
- **Strategy plumbing + `_ContractObserver` adapter.** `run_fitness_strategy` and `_build_engine` gain an optional `component_contract_path: Path | None = None` kwarg. When set, `_build_engine` wraps the Playwright bundle's page in a new `_ContractObserver` adapter whose `snapshot()` delegates to `await page.content()`, then passes both `contract_paths=[path]` and `contract_observer=observer` through to `FitnessEngine`.

### Changed
- **`/ux-cycle` Phase B rewritten to route through `run_fitness_strategy`.** Closes the "irony gap": Phase B previously hand-rolled its own `DazzleAgent` + `PlaywrightObserver` + `PlaywrightExecutor` dispatch, completely bypassing the fitness engine's ledger + Pass 1 machinery. The new three-line snippet calls `run_fitness_strategy(component_contract_path=path)` and the fitness engine owns the contract walk. Findings flow through the normal engine pipeline and land in `dev_docs/fitness-backlog.md`.

### Agent Guidance
- **v1.0.2 does not navigate.** The contract walker observes whatever page is loaded when Pass 1 fires — `about:blank` for fresh Playwright bundles. URL inference from contract anchors is deferred to v1.0.3 along with multi-persona fan-out and the optional `walk_story` → `walk_plan` unification. If you are writing Phase B runbooks that need real component observation, navigate to the right URL before calling `run_fitness_strategy`, or wait for v1.0.3.

## [0.54.1] - 2026-04-13

### Added
- **QA Mode (#768):** `dazzle serve --local` now auto-provisions a dev user for each DSL persona and renders a QA Personas section on the landing page. Testers click "Log in as X" to explore the app as any persona via magic links. Dev-gated generator endpoint `POST /qa/magic-link` is mounted only when `DAZZLE_ENV=development` + `DAZZLE_QA_MODE=1`. A general-purpose `GET /auth/magic/{token}` consumer endpoint is mounted unconditionally for production email-based passwordless login.
- **Magic link consumer endpoint:** `GET /auth/magic/{token}` — production-safe, general-purpose. Validates via existing `validate_magic_link` primitive (one-time use, expiry-gated), creates a session, and redirects to `?next=` (same-origin only) or `/`. Suitable for email-based passwordless login, account recovery, and dev QA mode.
- **`/ux-cycle` slash command:** iterative UX improvement loop that brings Dazzle's UX layer under ux-architect governance one component at a time. OBSERVE → SPECIFY → REFACTOR → QA → REPORT → EXPLORE cycle with persistent backlog (`dev_docs/ux-backlog.md`). Uses the new `ux_quality` DazzleAgent mission to drive Playwright through component contract quality gates as each persona (via QA mode magic link login from #768).
- **`ux_quality` and `ux_explore` agent missions:** two new DazzleAgent missions. `ux_quality` takes a ux-architect component contract and verifies its quality gates. `ux_explore` runs bottom-up gap discovery with two strategies (missing contracts, edge cases).
- **Flat-file signal bus:** `dazzle.cli.runtime_impl.ux_cycle_signals` — cross-loop coordination between `/ux-cycle`, `/improve`, `/ux-converge`. Signals at `.dazzle/signals/*.json` (gitignored).
- **Component contract parser:** `parse_component_contract()` in `dazzle.agent.missions._shared` — extracts quality gates, anatomy, and primitives from ux-architect contract markdown files.
- **DSL:** new `lifecycle:` entity block declaring ordered states and per-transition evidence predicates for the Agent-Led Fitness Methodology's progress evaluator. Orthogonal to the auto-derived `state_machine` (runtime mechanics). See ADR-0020 and `docs/reference/grammar.md`.
- **Agent-Led Fitness Methodology (v1)** — new subsystem at `src/dazzle/fitness/`.
  Continuous V&V loop triangulating `spec.md`, DSL stories, and the running
  app. Ships Pass 1 (story walker), Pass 2a (spec cross-check with structural
  independence), Pass 2b (behavioural proxy with EXPECT/ACTION/OBSERVE hard
  interlock), snapshot-based FitnessLedger, regression comparator, and
  two-gate corrector with alternative-generation disambiguation. See
  `docs/reference/fitness-methodology.md`.
- **DSL:** new `fitness.repr_fields` block on entities — required for entities
  that participate in fitness evaluation. v1 emits a non-fatal lint warning
  when missing; v1.1 will make this fatal.
- **/ux-cycle:** new `Strategy.FITNESS` — rotates alongside MISSING_CONTRACTS
  and EDGE_CASES.
- **Fitness v1.0.1 — real `_build_engine` wiring.** Replaces the
  `NotImplementedError` stub in
  `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` with the
  full async composition root: loads `AppSpec` + `FitnessConfig` from the
  example project, constructs `PostgresBackend` from `DATABASE_URL`
  (wrapped in the new `PgSnapshotSource` adapter), instantiates
  `LLMAPIClient`, spins up a headless Chromium `_PlaywrightBundle` via a
  separate `_setup_playwright` helper, builds a `DazzleAgent` with
  `PlaywrightObserver` + `PlaywrightExecutor`, and returns an
  `_EngineProxy` whose `run()` tears down Playwright even if the engine
  raises. Example-app subprocess lifecycle owned by `run_fitness_strategy`
  via `try/finally` delegating to `dazzle.qa.server.connect_app` +
  `wait_for_ready`.
- **`PgSnapshotSource` adapter** at
  `src/dazzle/fitness/pg_snapshot_source.py` — sync `SnapshotSource`
  protocol implementation over `PostgresBackend.connection()` using
  `psycopg.sql.Identifier` for safe SQL composition.
- **Unblocked e2e smoke test:**
  `tests/e2e/fitness/test_support_tickets_fitness.py::test_support_tickets_fitness_cycle_completes`
  now exercises `run_fitness_strategy` end-to-end when `DATABASE_URL` is
  set, asserting `StrategyOutcome` shape and that `fitness-log.md` +
  `fitness-backlog.md` are written.

### Changed
- **`auth_store` on `app.state`:** The auth subsystem now stashes `auth_store` on `app.state.auth_store` during startup. Route handlers can access the auth store without dependency injection gymnastics. Existing routes that receive auth_store via constructor are unchanged.
- **UX-036 auth-page series complete — all 7 `site/auth/` templates under macro governance.** Every template in `src/dazzle_ui/templates/site/auth/` now consumes the `auth_page_card` macro from `macros/auth_page_wrapper.html`. Dropped DaisyUI tokens across the series: `card`/`card-body`/`card-title`, `form-control`/`label-text`/`input-bordered`, `btn-primary`/`btn-outline`/`btn-ghost`/`btn-error`/`btn-sm`, `alert-error`/`alert-success`/`alert-warning`, `bg-base-*`, `divider`, `link-primary`/`link-secondary`, `badge badge-lg badge-outline`. Pure Tailwind replacements use HSL CSS variables from `design-system.css`. Inline JS in `2fa_settings.html` and `2fa_setup.html` extracts button class strings into named constants (`BTN_PRIMARY` / `BTN_DESTRUCTIVE` / `BTN_OUTLINE`, `RECOVERY_CODE_CLASSES`) so future tweaks touch one place. Submission handlers now all use CSRF-header-based JS fetches; `method="POST"` removed from form tags.

### Agent Guidance
- **QA Mode workflow**: When building or modifying example apps for human QA testing, the landing page renders a dev-only Personas panel with "Log in as X" buttons. The flow uses real magic links (no auth backdoor). Persona emails follow `{persona_id}@example.test`. Passwords are not set — magic-link login only. See `docs/superpowers/specs/2026-04-12-qa-mode-design.md` for the full security model.
- **`dazzle serve --local` env flags**: When `--local` is active, the CLI sets `DAZZLE_QA_MODE=1` and `DAZZLE_ENV=development` before uvicorn starts. Dev-only routes should double-check both flags at request time (defense in depth).
- **Lifecycle vs state_machine:** the new `lifecycle:` block is NOT a replacement for the existing auto-derived `state_machine`. Lifecycles encode progress semantics (ordered states, evidence predicates) and are consumed by `src/dazzle/fitness/progress_evaluator.py` once fitness v1 ships. State machines encode runtime mechanics (triggers, guards, effects). Entities may declare both; a validator warning fires if their state lists disagree.
- **Fitness prerequisite:** entities participating in fitness must declare
  both `fitness.repr_fields` (this release) and a `lifecycle:` block
  (ADR-0020). Check the lint output — missing declarations will silently
  skip the entity from fitness evaluation in v1 and error in v1.1.
- **Fitness findings routing:** never auto-correct findings with
  `low_confidence=true`. They go to soft mode (PR queue) regardless of
  maturity level. See `src/dazzle/fitness/corrector.py:route_finding`.

## [0.54.0] - 2026-04-12

### Added
- **ux-architect skill**: New Claude Code skill at `~/.claude/skills/ux-architect/` for constraint-based UI generation. 4-layer model: frozen token sheets, component contracts, interaction primitives, stack adapters. Linear aesthetic, 13 artefact files.
- **Data table inline edit**: `PATCH /api/{entity}/{id}/field/{field_name}` endpoint for single-field updates. Compiler auto-populates `inline_editable` from field types (text, bool, enum, date). Phase-based editing: double-click to enter, Enter/Tab to commit, Esc to cancel, Tab advances to next editable cell.
- **Data table bulk delete**: `POST /api/{entity}/bulk-delete` endpoint with scope-filtered ID list. Delete-only for v1; UI shows confirmation before executing.
- **Data table column resize**: Client-only column width adjustment via pointer events and `<colgroup>`. Snaps to 8px increments, persisted to localStorage per table ID.
- **Quality gate tests**: Playwright integration tests for dashboard (6 tests) and data table (9 tests). Static test harnesses serve mock data without backend. Catches DOM event wiring bugs that unit tests miss.

### Changed
- **Breaking**: Dashboard rewritten — SortableJS replaced with native pointer events + Alpine.js. 5-state save lifecycle (clean/dirty/saving/saved/error), undo stack (Cmd+Z), keyboard move/resize mode. `sortable.min.js` removed from vendor.
- **Breaking**: All table templates rewritten to pure Tailwind — DaisyUI component classes (`btn`, `table`, `badge`, `dropdown`, `checkbox`, `rounded-box`, `bg-base-*`) removed from `filterable_table.html`, `table_rows.html`, `table_pagination.html`, `bulk_actions.html`, `search_input.html`, `filter_bar.html`, `inline_edit.html`. Colours use `design-system.css` HSL variables.
- **Breaking**: `dzTable` Alpine component signature changed from `(tableId, endpoint, sortField, sortDir)` to `(tableId, endpoint, config)` where config is `{sortField, sortDir, inlineEditable, bulkActions, entityName}`.
- `examples/` reorganised: internal tools and test fixtures moved to `fixtures/`. `_archive/` deleted. `examples/` now contains only working Dazzle apps (simple_task, contact_manager, support_tickets, ops_dashboard, fieldtest_hub).

### Fixed
- CI badge (red since 2026-03-30): `test_regions_still_load_without_sse` expected `hx-trigger="load"` but template uses `intersect once`. CI validation loops updated to include `fixtures/*/`.

### Agent Guidance
- **ux-architect skill**: When building or modifying dashboard, data table, or other spec-governed UI, invoke the `ux-architect` skill. Read token sheets and component contracts before writing code. Do not invent values outside the token sheet.
- **DaisyUI phase-out**: New spec-governed components use pure Tailwind utilities. Existing non-governed templates may still use DaisyUI. Migrate incrementally as components get contracts.
- **Inline edit field types**: Compiler determines editability from column type: text, bool, badge (enum), date are editable; pk, ref, computed, sensitive, money are not.
- **examples/ vs fixtures/**: Real example apps in `examples/`, internal tools in `fixtures/`. CI validates both directories.

## [0.53.1] - 2026-03-30

### Fixed
- **SA schema**: `_field_to_column` accessed `field.required` which doesn't exist on IR `FieldSpec` (it has `is_required`). Now uses `getattr` fallback to support both FieldSpec types. Fixes NOT NULL columns for optional fields like `FeedbackReport.reported_by` (#762).
- **QA capture**: `build_capture_plan()` only checked `appspec.archetypes` (always empty for projects using `personas` keyword). Now falls back to `appspec.personas`. Unblocks `dazzle qa visual` and `dazzle qa capture` for all example apps (#763).

## [0.53.0] - 2026-03-30

### Added
- **Dashboard builder**: Replaces the workspace editor with a full card-based dashboard builder. SortableJS drag-to-reorder, snap-grid drag-to-resize (3/4/6/8/12 columns), add/remove cards from DSL-defined catalog, auto-save with 500ms debounce, always-on interactions (no edit mode toggle).
- **Layout schema v2**: Card-instance model where each card is an independent instance referencing a DSL region. Supports duplicate cards of the same type. Automatic v1→v2 migration preserves existing user layouts.
- **Catalog endpoint**: `build_catalog()` returns available widgets per workspace for the "Add Card" picker. Layout JSON data island now includes catalog metadata.
- **Card picker popover**: `_card_picker.html` template lists available regions grouped by display type and entity.

### Changed
- **Breaking**: Alpine Sort plugin removed, replaced by SortableJS (vendored). `workspace-editor.js` replaced by `dashboard-builder.js`.
- **Breaking**: Layout preference format changed from v1 `{order, hidden, widths}` to v2 `{version: 2, cards: [{id, region, col_span, row_order}]}`. Hidden cards are dropped (not flagged) in v2. Auto-migration is seamless.

### Agent Guidance
- AegisMark agents building customizable dashboards should use DSL `workspace` blocks to define the card catalog. End users compose their own layouts via the dashboard builder UI. No code changes needed — the framework handles drag-drop, resize, and persistence automatically.
- Valid `col_span` snap points: 3, 4, 6, 8, 12. The old 6/12-only restriction is gone.

## [0.52.0] - 2026-03-30

### Added
- **QA toolkit**: New `src/dazzle/qa/` package — visual quality evaluation via Claude Vision, Playwright screenshot capture, process lifecycle management, and findings aggregation. Generalized from AegisMark's autonomous quality assessment approach.
- **CLI**: `dazzle qa visual` evaluates running apps against 8 quality categories (text_wrapping, truncation, title_formatting, column_layout, empty_state, alignment, readability, data_quality). Returns structured findings with severity and fix suggestions.
- **CLI**: `dazzle qa capture` captures screenshots per persona per workspace without LLM evaluation — useful for debugging and baselines.
- **Evaluator**: Pluggable `QAEvaluator` protocol with `ClaudeEvaluator` default (via `[llm]` extra). Prompt adapted from AegisMark's battle-tested visual quality assessment.
- **Server lifecycle**: `serve_app()` context manager starts Dazzle apps as subprocesses with health polling. Accepts `--url` for already-running instances.
- **`/improve` integration**: New `visual_quality` gap type with tiered discovery — DSL gaps first (free), visual QA when exhausted (LLM cost). Findings feed into the existing OBSERVE → ENHANCE → VERIFY loop.

### Agent Guidance
- When `/improve` exhausts all DSL-level gaps (lint, validate, conformance, fidelity), it now automatically runs `dazzle qa visual` to discover display bugs (raw UUIDs, broken layouts, missing empty states). Visual findings become backlog items with fix routing by category.
- `dazzle qa visual --app <name>` works against any example app. Use `--url` for deployed instances.

## [0.51.16] - 2026-03-29

### Fixed
- **Display**: FK fields in detail views no longer render as raw Python dicts (#761). `_get_field_spec` now falls back to relation name + `_id` lookup; template else-branch applies `ref_display` filter for mapping values.
- **Display**: Datetime fields (`created_at`, `updated_at`) now format as "27 Mar 2026" instead of raw ISO strings (#760). `_field_type_to_column_type` detects `_at` suffix for framework-injected timestamp columns.
- **Workspace**: Customize button drag-and-drop now gated to edit mode via `x-sort:disabled` (#758). Added visual lift feedback CSS on drag handles.
- **Filter bar**: Ref/FK fields now render as select dropdowns instead of free-text inputs (#759). Alpine.js-driven `<select>` fetches options from the referenced entity's API on page load.

## [0.51.15] - 2026-03-29

### Fixed
- **PyPI**: Fixed `ModuleNotFoundError: No module named 'httpx'` on `dazzle --help` in PyPI installs. The sentinel CLI eagerly imported `dazzle.testing.fuzzer` at module level, which pulled in `httpx` via the e2e_runner import chain. Now lazy-imported inside the `fuzz` command.

## [0.51.14] - 2026-03-29

### Added
- **JS quality checks**: ESLint structural linting for 8 source JS files (no-undef, no-unreachable, no-dupe-keys, valid-typeof). Flat config with browser + framework globals (Alpine, htmx, Quill, etc.).
- **Dist syntax validation**: `node --check` validates composed `dist/*.js` bundles are parseable — catches concatenation errors.
- **Test suite**: `tests/unit/test_js_quality.py` with ESLint + dist syntax checks, skips gracefully if node/npx unavailable.

### Fixed
- **vitest.config.js**: Fixed typo `dazzle_dnr_ui` → `dazzle_ui` in include path.

## [0.51.13] - 2026-03-29

### Added
- **HTML template linting**: Added djLint static analysis for all 102 Jinja2 templates — catches unclosed/mismatched tags deterministically without rendering. Configured in `pyproject.toml` with structural rules only.
- **Rendered HTML validation**: New `HTMLBalanceChecker` validates balanced open/close tags on rendered template output for 18 key templates (fragments, workspace regions, components).
- **Test suite**: `tests/unit/test_template_html.py` with 24 tests covering both static and rendered HTML quality checks.

### Fixed
- **Workspace**: Fixed unclosed `<div>` in list region template causing titles to render inline with content instead of above it (#757).

## [0.51.12] - 2026-03-29

### Fixed
- **Display**: Enum/state fields now show human-readable Title Case instead of raw snake_case values in tables and detail views (#755). Added centralized `humanize` Jinja2 filter.
- **Display**: Grid and list workspace regions no longer show raw UUIDs for ref fields when FK expansion is missing (#756). Unexpanded refs now show "-" instead of the UUID string.

## [0.51.11] - 2026-03-28

### Fixed
- **Parser**: `widget=` can now appear after `visible:` on surface field declarations (#754). Previously, `field x "X" visible: role(admin) widget=picker` failed with "Unexpected 'widget'" — the parser now accepts key=value options, `visible:`, and `when:` in any order.

## [0.51.10] - 2026-03-28

### Added
- **Capability discovery**: New `src/dazzle/core/discovery/` package surfaces relevant Dazzle capabilities (widgets, layouts, components, completeness gaps) to agents at lint time using contextual references to working example apps
- **Widget rules**: Detects text fields without `widget=rich_text`, ref fields without `widget=combobox`, date fields without `widget=picker`, and name-pattern matches for tags, color, slider
- **Layout rules**: Identifies entities with transitions but no kanban workspace, date fields but no timeline, view surfaces with 3+ related entities but no groups, and large single-section forms
- **Component rules**: Suggests `dzCommandPalette` for apps with 5+ surfaces, toggle groups for enum status + grid displays
- **Completeness rules**: Flags entities with permissions but missing CRUD surfaces (edit, list, create) or no surfaces at all
- **Example index**: Scans example apps to build capability key → `ExampleRef` mappings with file paths and line numbers
- **KG seeding**: New `capabilities.toml` with 18 capability concepts seeded into knowledge graph (seed schema v8)
- **Lint integration**: `dazzle lint` and `dsl operation=lint` now include a "Relevant capabilities" section after errors/warnings
- **Bootstrap integration**: Added step 12a in bootstrap agent instructions to review capability relevance after DSL generation
- **Quiet mode**: `suppress_relevance=true` on MCP calls or `suppress=True` in API suppresses relevance output

### Agent Guidance
- After generating DSL, run `dsl operation=lint` and review the "Relevant capabilities" section. Each item references a working example app with file and line number — use these as concrete patterns, not prescriptions.
- Query `knowledge(operation='concept', term='widget_rich_text')` (or any capability key) for deeper exploration of what's available.

## [0.51.9] - 2026-03-28

### Fixed
- **CI green badge**: Resolved all 12 mypy errors across 4 files — triples.py (getattr for object attrs), service.py (mixin method type ignores), ux.py (function annotations + HtmxResponse typing), db.py (union type guard for Alembic revision)

## [0.51.8] - 2026-03-28

### Fixed
- **component_showcase**: `widget=range` on `end_date` (date field) changed to `widget=picker` — range picker returns unparseable string for date columns
- **All examples**: Removed no-op `widget=` annotations from `mode: view` and `mode: list` surfaces — detail_view.html and filterable_table.html do not check `field.widget`
- **project_tracker**: Added missing `project_edit`, `milestone_list`, `milestone_edit` surfaces — previously had broken Edit button (404)
- **design_studio**: Added missing `brand_edit`, `campaign_list`, `campaign_edit` surfaces — previously couldn't update brands or browse campaigns

### Agent Guidance
- `widget=` annotations are only effective on `mode: create` and `mode: edit` surfaces. Do not add them to `mode: view` or `mode: list` surfaces — the templates ignore them.
- `widget=range` (date range picker) should only be used on `str` fields, not `date` fields. A date range returns a compound string ("YYYY-MM-DD to YYYY-MM-DD") that cannot be stored in a scalar date column.

## [0.51.7] - 2026-03-28

### Fixed
- **Duplicated widget map**: `_field_type_to_form_type()` in template_compiler.py now delegates to canonical `resolve_widget()` from triples.py — single source of truth, 9 previously missing field type kinds covered
- **Flattened action provenance**: `VerifiableTriple.actions` now carries `ActionTriple` with `action` + `permission` fields instead of bare strings — reconciler can trace permission grants for ACTION_UNEXPECTED diagnoses
- **TEMPLATE_BUG catch-all**: New `TRIPLE_SUSPECT` diagnosis kind — reconciler cross-checks triple widget against re-derived widget from raw entity field before falling through to TEMPLATE_BUG
- **O(n) triple lookups**: `AppSpec.get_triple()`, `get_triples_for_entity()`, `get_triples_for_persona()` now use `@cached_property` dict indexes for O(1) lookups

### Added
- Scope predicate invariant documented on `derive_triples()` — triples depend only on entities, surfaces, and personas, never FK graph or scope predicates
- 5 synthetic failure tests for reconciler diagnosis paths (ACTION_MISSING, ACTION_UNEXPECTED, FIELD_MISSING, PERMISSION_GAP, TRIPLE_SUSPECT)

### Agent Guidance
- `VerifiableTriple.actions` is now `list[ActionTriple]`, not `list[str]`. Use `triple.action_names` for backward-compatible string list access.
- The template compiler no longer has its own widget map — it imports `resolve_widget()` from `dazzle.core.ir.triples`. When adding new `FieldTypeKind` values, only update `_WIDGET_MAP` in triples.py.

## [0.51.6] - 2026-03-28

### Added
- **`widget=` DSL syntax**: Surface field declarations now support `widget=value` annotations (e.g., `field description "Description" widget=rich_text`). The parser already supported `key=value` options via the `source=` pattern — this commit wires `widget` through the template compiler to `FieldContext.widget`, completing the DSL-to-template pipeline.
- All three Phase 5 example apps updated with `widget=` annotations on appropriate fields

### Agent Guidance
- Use `widget=value` on surface field lines to override the default field rendering. Supported values: `rich_text`, `combobox`, `tags`, `picker`, `range`, `color`, `slider`. The value flows through `SurfaceElement.options["widget"]` → template compiler → `FieldContext.widget` → `form_field.html` macro.
- The `widget=` option is parsed as a generic key-value pair — no parser changes were needed.

## [0.51.5] - 2026-03-28

### Added
- **UX Component Expansion — Phase 5 (Example Apps)**: Three new example apps exercising the expanded component inventory
  - `examples/project_tracker` — Project management app: 6 entities (User, Project, Milestone, Task, Comment, Attachment), kanban board, timeline, status cards, related groups, multi-section forms
  - `examples/design_studio` — Brand/design asset management: 5 entities (User, Brand, Asset, Campaign, Feedback), asset gallery grid, review queue, brand color fields, campaign scheduling
  - `examples/component_showcase` — Kitchen-sink gallery: single "Showcase" entity with every field type, all widget-capable fields exercised from one create/edit form

### Agent Guidance
- The `widget:` syntax is NOT yet implemented in the DSL parser — it exists at the template/rendering layer only. Example apps use standard DSL field types. Widget rendering will be activated when the parser supports `widget=` annotations on surface fields (planned for a future minor version).
- Each example validates cleanly (`dazzle validate`). Framework-generated `FeedbackReport` warnings are expected when `feedback_widget: enabled`.

## [0.51.4] - 2026-03-28

### Added
- **UX Component Expansion — Phase 4 (Vendored Widget Libraries)**: Complex input components via battle-tested JS libraries
  - **Tom Select** (v2.5.2, Apache 2.0): Combobox, multi-select, and tag input — `data-dz-widget="combobox|multiselect|tags"`
  - **Flatpickr** (v4.6.13, MIT): Date picker and date range picker — `data-dz-widget="datepicker|daterange"`
  - **Pickr** (v1.9.1, MIT): Color picker with nano theme — `data-dz-widget="colorpicker"`
  - **Quill** (v2.0.3, BSD-3): Rich text editor with snow theme — `data-dz-widget="richtext"`
  - Range slider with live value tooltip — `data-dz-widget="range-tooltip"`
  - `dz-widget-registry.js`: Bridge handler registrations for all 8 widget types (mount/unmount lifecycle)
  - `dz-widgets.css`: DaisyUI v4 theme overrides for all vendored libraries (oklch color tokens, radius, fonts)
  - `form_field.html` macro: 8 new `widget:` cases — combobox, multi_select, tags, picker, range, color, rich_text, slider
  - Conditional loading via `asset_manifest.py` — vendored JS/CSS only loads on pages that use the widgets

### Agent Guidance
- Set `widget:` on surface fields to use vendored widgets. The `form_field.html` macro checks `field.widget` before `field.type`.
- Widget elements use `data-dz-widget` attributes. The component bridge (`dz-component-bridge.js`) handles HTMX swap lifecycle. `dz-widget-registry.js` registers all mount/unmount handlers.
- Tom Select covers three use cases: `combobox` (single select with search), `multiselect` (multi with remove buttons), `tags` (free-form tag creation).

## [0.51.3] - 2026-03-28

### Added
- **UX Component Expansion — Phase 3 (Alpine Interactive Components)**: 6 new Alpine.js components with Jinja2 fragments
  - `dzPopover` + `popover.html`: Anchored floating content panel with click-outside dismiss
  - `dzTooltip` + `tooltip_rich.html`: Rich HTML tooltip with configurable show/hide delays
  - `dzContextMenu` + `context_menu.html`: Right-click positioned menu with divider support
  - `dzCommandPalette` + `command_palette.html`: Cmd+K spotlight search with fuzzy filter, keyboard navigation, grouped actions
  - `dzSlideOver` + `slide_over.html`: Side sheet overlay with 5 width presets, focus trapping, HTMX content loading
  - `dzToggleGroup` + `toggle_group.html`: Exclusive or multi-select button group with hidden input sync

### Agent Guidance
- All Phase 3 components are registered in `dz-alpine.js` and have matching fragments in `templates/fragments/`.
- `dzCommandPalette` accepts actions as a JSON array via `data-dz-actions` attribute or Jinja2 `actions` variable. Actions have `label`, `url`, optional `group` and `icon`.
- `dzSlideOver` listens for `dz:slideover-open` window event — dispatch from HTMX `hx-on::after-settle`.
- `dzToggleGroup` syncs to a hidden input for form submission. Use `multi=True` for multi-select mode.

## [0.51.2] - 2026-03-28

### Added
- **UX Component Expansion — Phase 2 (Server-Driven Components)**: Template fragments and HTMX patterns
  - `toast.html` fragment: auto-dismissing notifications via `remove-me` extension
  - `alert_banner.html` fragment: full-width dismissible banners with Alpine.js
  - `breadcrumbs.html` fragment + `breadcrumbs.py` module: server-side route-to-breadcrumb derivation with DaisyUI styling and HTMX navigation
  - `steps_indicator.html` fragment: DaisyUI steps component for multi-step wizard flows
  - `accordion.html` fragment: collapsible sections with optional HTMX lazy-load on first open
  - `skeleton_patterns.html` macros: reusable skeleton presets (table rows, cards, detail views)
  - `modal.html` component: general-purpose server-loaded modal using native `<dialog>` element

### Agent Guidance
- Use `build_breadcrumb_trail(path, overrides)` from `dazzle_back.runtime.breadcrumbs` to derive breadcrumb trails. Pass the result as `crumbs` to the breadcrumbs fragment.
- For accordion lazy-loading, set `endpoint` on a section to trigger HTMX fetch on first open; leave it `None` for static content.
- Skeleton macros are importable: `{% from "fragments/skeleton_patterns.html" import skeleton_table_rows, skeleton_card, skeleton_detail %}`.

## [0.51.1] - 2026-03-28

### Added
- **UX Component Expansion — Phase 1 (Foundation)**: Infrastructure for expanding Dazzle's native UX component inventory
  - Vendor HTMX extensions: `remove-me` (auto-dismiss), `class-tools` (timed CSS), `multi-swap` (multi-target), `path-deps` (auto-refresh)
  - Vendor Alpine.js plugins: `@alpinejs/anchor` (Floating UI positioning), `@alpinejs/collapse` (smooth accordion), `@alpinejs/focus` (focus trapping)
  - `dz-component-bridge.js`: Lifecycle bridge for vendored widgets across HTMX DOM swaps — mount/unmount/registerWidget API on `window.dz.bridge`
  - `response_helpers.py`: Server-side `with_toast()` and `with_oob()` helpers for HTMX OOB swaps
  - `asset_manifest.py`: Derives required vendor JS assets from surface field `widget:` hints for conditional loading
  - `base.html`: `#dz-toast-container`, `#dz-modal-slot`, `#dz-dynamic-assets` container elements; conditional vendor asset loading block

### Agent Guidance
- Use `with_toast(response, message, level)` from `dazzle_back.runtime.response_helpers` to append auto-dismissing toast notifications to any HTMX response. Use `with_oob()` for generic OOB swaps.
- Vendor widget libraries register via `window.dz.bridge.registerWidget(type, { mount, unmount })`. The bridge handles HTMX swap lifecycle automatically.
- `collect_required_assets(surface)` from `asset_manifest.py` returns the set of vendor asset keys a page needs. Pass as `required_assets` in template context.

## [0.51.0] - 2026-03-28

### Added
- **Related Display Intent**: `related` DSL block on `mode: view` surfaces for grouped, mode-specific related entity presentation
  - `RelatedDisplayMode` enum: `table`, `status_cards`, `file_list` (closed, extensible per minor version)
  - `RelatedGroup` IR type: name, title, display mode, entity list — validated at link time
  - Parser: `related name "Title": display: mode; show: Entity1, Entity2` syntax
  - Linker validation: entity existence, FK path to parent, no duplicates across groups, view-mode only
  - `RelatedGroupContext` replaces flat `related_tabs` on `DetailContext`
  - Template compiler groups tabs by declared groups; ungrouped entities auto-collect into "Other" with `display: table`
  - Three fragment templates: `related_table_group.html`, `related_status_cards.html`, `related_file_list.html`
  - `VerifiableTriple.related_groups` for contract verification of detail page layout

### Agent Guidance
- Use `related` blocks on `mode: view` surfaces to control how related entities appear on detail pages. Without them, behavior is unchanged (all reverse-FK entities as table tabs). With them, named entities render with declared display modes; unlisted entities auto-group into "Other".

## [0.50.0] - 2026-03-28

### Added
- **IR Triple Enrichment** (Layer A): Cache (Entity, Surface, Persona) triples in AppSpec at link time
  - `WidgetKind` enum: deterministic widget resolution from field types (mirrors template compiler)
  - `SurfaceFieldTriple`: per-field rendering metadata (widget, required, FK status)
  - `SurfaceActionTriple`: per-surface action with permission-based visibility
  - `VerifiableTriple`: atomic unit of verifiable behavior — fields + actions per persona
  - `derive_triples()`: pure function in linker step 10b, no UI imports
  - AppSpec getters: `get_triple()`, `get_triples_for_entity()`, `get_triples_for_persona()`
- **Reconciliation Engine** (Layer C): Back-propagate contract failures to DSL levers
  - `DiagnosisKind`: 7 failure categories (widget_mismatch, action_missing, permission_gap, template_bug, etc.)
  - `DSLLever`: points to specific DSL construct with current/suggested values
  - `Diagnosis`: structured failure report with levers for agent-driven convergence
  - `reconcile()`: deterministic diagnosis from contract + triple + HTML

### Changed
- Contract generation (`contracts.py`) rewritten as thin mapper over `appspec.triples` — ~130 lines of derivation logic removed
- `/ux-converge` command updated to use reconciler for automated failure classification

### Agent Guidance
- **IR Triples**: `appspec.triples` contains pre-computed (Entity, Surface, Persona) triples. Use `appspec.get_triple(entity, surface, persona)` instead of re-deriving from raw IR.
- **Reconciler**: When a contract fails, call `reconcile(contract, triple, html, entities, surfaces)` to get a `Diagnosis` with `levers` pointing to the DSL change that would fix it. No more manual backward reasoning.
- **Convergence loop**: `/ux-converge` now uses the reconciler. Each failure produces a structured diagnosis → apply lever → re-verify → converge.

## [0.49.14] - 2026-03-28

### Added
- **UX Contract Verification** (Layer B): `dazzle ux verify --contracts` — fast, httpx-based DOM assertion system derived from AppSpec
  - Contract generation: mechanically derives ListPage, CreateForm, EditForm, DetailView, Workspace, and RBAC contracts from the DSL
  - Contract checker: parses rendered HTML and asserts DOM structure (hx-* attributes, form fields, action buttons, region presence)
  - HTMX client: simulates browser HTMX requests with correct headers (HX-Request, HX-Target, CSRF)
  - Baseline ratchet: tracks pass/fail per contract across runs, detects regressions and fixes
  - RBAC contracts: verifies UI enforcement of every permit/forbid rule per persona (compliance evidence)
  - Performance: ~25 seconds for full verification vs 5+ minutes for Playwright
- Context selector label: human-readable names from DSL title or PascalCase splitting (#747)
- Feedback widget: validation toast when category not selected (#746)

### Fixed
- Workspace routes registered once instead of N× per workspace (#750)
- Workspace drawer reopens after backdrop close — removed vestigial `history.replaceState` (#748)
- DELETE handler returns 409 on FK constraint instead of 500 (#749)
- `/__test__/reset` clears each entity table in separate connection to avoid FK-aborted transactions (#751)
- `/__test__/seed` rolls back created entities on failure to prevent partial state (#753)
- UX inventory: deduplicated CRUD interactions to one per entity×persona (#752)
- Contract checker: calibrated against real HTML patterns (data-dazzle-table on div, hx-put for edit forms, surface-mode-gated contracts)

### Agent Guidance
- **Contract verification**: Run `dazzle ux verify --contracts` for fast DOM assertion (no browser). Use `--update-baseline` to save results, `--strict` to fail on any violation. 41/48 contracts pass on simple_task; 7 RBAC mismatches are genuine permission model issues.
- **Ratchet model**: Baseline stored in `.dazzle/ux-verify/baseline.json`. Regressions (passed→failed) are flagged prominently. Target: converge to zero failures.

## [0.49.13] - 2026-03-27

### Added
- UX verify CRUD interactions: create_submit, edit_submit, delete_confirm runners with form filling, checkbox handling, unique email generation
- UX verify runtime URL resolution from `.dazzle/runtime.json` — auto-discovers server port
- Per-entity seed batching: fixture seeding continues past individual entity failures

### Fixed
- UX verify workspace URLs: `/app/workspaces/{name}` (was `/workspace/{name}`)
- UX verify fixture generator: correct FK ref detection, skip auto-timestamp fields, exclude framework admin entities
- UX verify detail view: wait for HTMX data load, click table rows (not hidden menu links)
- UX verify drawer: use `dzDrawer` JS API for CSS-transform-based drawers, handle non-drawer regions gracefully
- UX verify auth: send `X-Test-Secret` header, extract cookie domain from URL, handle 403 as skip
- UX verify create forms: target `form[hx-post]`, handle datetime-local/checkbox/radio fields, unique values per interaction

### Agent Guidance
- **UX verify results**: simple_task 97/280 passed (0 failures), contact_manager 45/68 passed (0 failures). Skipped items are state_transition (not yet implemented) and permission/drawer-unsupported regions.
- **Delete CSRF**: `hx-delete` interactions fail with 500 due to missing CSRF token in HTMX DELETE requests — tracked as framework issue.

## [0.49.12] - 2026-03-27

### Added
- UX Verification system (Layer A): `dazzle ux verify` for deterministic interaction testing derived from the DSL
  - Interaction inventory: AppSpec → enumerable list of every testable interaction (280 for simple_task)
  - Structural HTML assertions: fast no-browser checks for back buttons, submit buttons, ARIA, duplicate IDs
  - Playwright runner: real browser interaction verification with per-persona sessions and screenshot capture
  - Postgres test harness: create/drop test database lifecycle management
  - Fixture generator: deterministic seed data from DSL entities
  - Report generator: coverage percentage, markdown/JSON output, failure gallery
- `dazzle db baseline` command for fresh database deployment — generates CREATE TABLE migration from DSL (#742)

### Fixed
- Test routes: replaced `functools.partial` with closures — fixes 422 on `/__test__/seed` and `/__test__/authenticate` (#743)
- Detail page Back button: context-aware — closes drawer when inside one, `history.back()` on full pages (#744, #745)

### Agent Guidance
- **UX verification**: Run `dazzle ux verify --structural` for fast HTML checks, `dazzle ux verify` for full browser verification. Coverage metric = interactions_tested / interactions_enumerated.
- **Fresh DB deployment**: Use `dazzle db baseline --apply` instead of `stamp` + empty revision.

## [0.49.11] - 2026-03-27

### Fixed
- Depth-N FK path scoping: subqueries now `SELECT "id"` instead of FK field values, fixing 0-row results on multi-hop scope rules (#738)
- Kanban regions default to `col_span=12` (full width) regardless of stage defaults (#739)
- Workspace layout: replaced CSS `columns-2` with CSS Grid (`grid-cols-12`) to eliminate heading/content misalignment from multi-column fragmentation (#741)
- Workspace drag-and-drop: added visual feedback — ghost opacity + dashed border, drag elevation + scale, grab cursor, save toast (#740)

## [0.49.10] - 2026-03-27

### Added
- Centralized URL configuration: `[urls]` section in `dazzle.toml` with `site_url` and `api_url` fields (#736)
- `resolve_site_url()` and `resolve_api_url()` helpers with env var → toml → localhost default cascade
- Env vars `DAZZLE_SITE_URL` and `DAZZLE_API_URL` override toml values

### Changed
- ~19 files across runtime, testing, CLI, and MCP handlers now use URL resolvers instead of hardcoded localhost URLs (#736)

### Agent Guidance
- **URL configuration**: Set `DAZZLE_SITE_URL` / `DAZZLE_API_URL` env vars or add `[urls]` to `dazzle.toml` to change default URLs. All tools, magic links, OpenAPI specs, and test infrastructure respect the cascade.

## [0.49.9] - 2026-03-27

### Fixed
- Parser hang in experience block on unexpected tokens — missing `else` branch caused infinite loop when non-`step` token appeared (#733)
- `_grants.principal_id` TEXT→UUID migration for tables created before v0.49.8 + route type coercion to prevent psycopg binary protocol mismatch (#734)
- `AuthService` now delegates `create_session()` and `_execute_modify()` to underlying `AuthStore` — fixes `dazzle auth impersonate` crash (#735)

## [0.49.8] - 2026-03-27

### Added
- DSL parser fuzzer — three-layer hybrid fuzzer (LLM generation, grammar-aware mutation, token-level mutation) with classification oracle detecting hangs, crashes, and poor error messages (#732)
- `dazzle sentinel fuzz` CLI command — run fuzz campaigns against the parser with configurable layers, sample counts, and timeout
- MCP `sentinel` tool: new `fuzz_summary` operation for on-demand parser fuzz reports
- Hypothesis-powered parser fuzz test suite — 7 property-based tests covering arbitrary input, DSL-like text, and 5 mutation strategies

### Fixed
- `parse_duration()` in process parser now raises `ParseError` instead of `ValueError` on invalid duration strings — found by the fuzzer (#732)

### Agent Guidance
- **Parser fuzzing**: Run `dazzle sentinel fuzz --layer mutate --samples 100` to check parser robustness. The fuzzer found a `ValueError` bug and a parser hang (#733) during initial development — use it after parser changes.

## [0.49.7] - 2026-03-27

### Fixed
- DSL parser: infinite loop on unsupported syntax in surface section blocks — now raises a clear `ParseError` (#731)
- DSL parser: bare `owner` in `permit:` now gives actionable guidance pointing to the correct `scope:` block pattern (#729)
- Added `ownership_pattern` concept to semantics KB for MCP knowledge tool discoverability (#729)

### Agent Guidance
- **Ownership pattern**: Row-level ownership uses `scope:` blocks, not `permit:`. Write `scope: read: user_id = current_user for: reader` — there is no standalone `owner` keyword. See KB concept `ownership_pattern`.

## [0.49.6] - 2026-03-27

### Added
- `dazzle db stamp` CLI command — marks a revision as applied without running migrations, wraps `alembic.command.stamp()` (#728)

### Fixed
- `grammar_gen.write_grammar()`, `docs_gen.write_reference_docs()`, and `docs_gen.inject_readme_feature_table()` now write to project directory (CWD) instead of package directory (ADR-0018, #725)
- `tenant/provisioner.py` locates alembic dir via `import dazzle_back` for pip install compatibility (#725)

## [0.49.5] - 2026-03-27

### Fixed
- Alembic `env.py` now normalizes Heroku's `postgres://` scheme to `postgresql://` before adding the psycopg driver — fixes `Can't load plugin: sqlalchemy.dialects:postgres` on Heroku (#727)
- `_get_url()` now prefers `sqlalchemy.url` (already normalized by `db.py`) over raw `DATABASE_URL` env var

## [0.49.4] - 2026-03-27

### Added
- PythonAuditAgent (PA) sentinel agent — detects obsolete Python patterns in user project code (#726)
- Three detection layers: ruff profile (UP/PTH/ASYNC/C4/SIM), semgrep ruleset (8 rules for deprecated stdlib), and 6 `@heuristic` AST-based methods for LLM training-bias patterns
- Semgrep ruleset at `src/dazzle/sentinel/rules/python_audit.yml` covering distutils, pkg_resources, cgi, imp, asyncio.get_event_loop, nose, toml PyPI package, and datetime.timezone.utc
- LLM-bias heuristics: requests-in-async (PA-LLM-01), manual dunders (PA-LLM-03), unittest-in-pytest (PA-LLM-04), setup.py alongside pyproject.toml (PA-LLM-05), pip-when-uv-available (PA-LLM-06)
- Python version filtering — findings with min_version above project target are excluded
- Orchestrator now passes `project_path` through to agents that need it

### Agent Guidance
- **PA agent**: Results appear via existing `sentinel findings`/`status`/`history` MCP tools — no new MCP operations. PA scans user project code (app/, scripts/, root .py files), never framework code.

## [0.49.3] - 2026-03-27

### Fixed
- `dazzle db revision` now writes migration files to project directory (`.dazzle/migrations/versions/`) instead of the framework's package directory (#724)
- Alembic config uses `version_locations` to chain framework + project migrations — upgrade/downgrade discovers both
- Framework alembic directory located via `dazzle_back` package path (works with pip installs, not just editable dev mode)

### Agent Guidance
- **Migration output path**: `dazzle db revision` writes to `.dazzle/migrations/versions/` in the project directory. Framework migrations and project migrations are chained via Alembic's `version_locations`. Never write to the Python package directory.

## [0.49.2] - 2026-03-26

### Added
- Environment profiles: `[environments.<name>]` sections in `dazzle.toml` for per-environment database configuration (#718)
- Global `--env` CLI flag and `DAZZLE_ENV` environment variable to select active profile (#718)
- `EnvironmentProfile` dataclass with `database_url`, `database_url_env`, and `heroku_app` fields (#718)
- `environment_profiles` concept in semantics KB with resolution priority documentation (#718)
- Commented-out `[environments.*]` example in blank project template (#718)

### Changed
- `resolve_database_url()` now accepts `env_name` parameter — inserted at priority #2 between explicit URL and DATABASE_URL env var (#718)
- All database-touching CLI commands (db, dbshell, tenant, serve --local, backup) thread `env_name` through to URL resolution (#718)

### Agent Guidance
- **Environment profiles**: Use `[environments.<name>]` in `dazzle.toml` to declare per-environment database connections. Select via `--env <name>` or `DAZZLE_ENV`. Profile names are freeform (development, staging, production, blue, green, demo, etc.).
- **Resolution priority**: `--database-url` > `--env` profile > `DATABASE_URL` env var > `[database].url` > default. Document this in comments when using profiles.
- **CI/CD**: Set `DAZZLE_ENV=production` in deployment config instead of passing `--env` to every command.

## [0.49.1] - 2026-03-26

### Changed
- All tutorial examples now declare `security_profile: basic` and an `admin` persona — aligns with auth-universal philosophy (#704)
- `llm_ticket_classifier` example: added `[auth]` section to `dazzle.toml` (#704)
- `contact_manager` stories: fixed actor references to match declared persona IDs (#704)

### Agent Guidance
- **Examples are auth-universal**: All tutorial examples now have auth enabled, an `admin` persona, and `security_profile: basic`. When scaffolding new apps from examples, this is the expected baseline.

## [0.49.0] - 2026-03-26

### Added
- MCP `knowledge` tool: `changelog` operation — returns `### Agent Guidance` entries from recent releases, with optional `since` version filter (#716)
- MCP `knowledge` tool: `version_info` block in concept lookup responses — includes `since` version and `changes` history when annotated in TOML (#716)
- Semantics KB: `since_version` and `changed_in` fields on TOML concepts — 5 concepts annotated (feedback_widget, scope, static_assets, predicate_compilation, surface_access) (#716)
- KG seeder: changelog guidance entries stored as `changelog:vX.Y.Z` entities during startup (#716)

### Agent Guidance
- **Version-aware concepts**: Some concept lookups now include a `version_info` block with `since` (introduction version) and `changes` (version history). Use this to understand when features appeared and what changed.
- **Changelog operation**: Use `knowledge(operation='changelog')` to get agent guidance from recent releases. Use `since` parameter to filter (e.g., `knowledge(operation='changelog', since='0.48.0')`). Default: last 5 releases with guidance.

## [0.48.16] - 2026-03-26

### Added
- Admin workspace: `DIAGRAM` display mode — entity relationship diagrams rendered via Mermaid JS (#700)
- Admin workspace: app map region showing entity FK graph in Operations nav group (#700)
- Admin workspace: deploy trigger actions — "Trigger Deploy" header button and per-row "Rollback" on deploys region (#701)
- Admin workspace: `_REGION_ACTIONS` / `_ROW_ACTIONS` action button system for admin regions (#701)
- Admin API: `POST /_admin/api/deploys/trigger` and `POST /_admin/api/deploys/{id}/rollback` endpoints (super_admin only) (#701)

## [0.48.15] - 2026-03-26

### Added
- Admin workspace: `LogEntry` virtual entity and `_admin_logs` region — log viewer backed by `get_recent_logs()` with level filtering (#699)
- Admin workspace: `EventTrace` virtual entity and `_admin_events` region — event explorer backed by event bus replay API (#702)
- Feedback widget: resolved-report notification — toast on page load when reports are resolved, `notification_sent` tracking field (#721)

## [0.48.14] - 2026-03-26

### Removed
- Removed unnecessary `from __future__ import annotations` from 547 files — ban-by-default policy, retained with `# required:` justification in ~145 files with genuine forward references (#717)

### Fixed
- Feedback widget PUT endpoint: added test coverage verifying surface converter generates PUT endpoint and UPDATE service for FeedbackReport (#720)

## [0.48.13] - 2026-03-26

### Fixed
- Feedback widget: all buttons now have `type="button"` — prevents Safari scroll glitch on first click inside `hx-boost` bodies (#722)
- Feedback widget: removed `textarea.focus()` on panel open — eliminates iPad Safari white bar from virtual keyboard reservation (#723)
- Feedback widget: panel height changed from `100vh` to `100dvh` — tracks dynamic viewport excluding virtual keyboard on mobile Safari (#723)

## [0.48.12] - 2026-03-26

### Added
- Universal admin workspace: linker auto-generates `_platform_admin` (and `_tenant_admin` for multi-tenant apps) with profile-gated regions for health, metrics, deploys, processes, sessions, users, and feedback (#686)
- Five synthetic platform entities: `SystemHealth`, `SystemMetric`, `DeployHistory`, `ProcessRun`, `SessionInfo` — backed by existing observability stores (#686)
- `SystemEntityStore` adapter: routes reads for virtual entities to health aggregator, metrics store, and process monitor instead of PostgreSQL (#686)
- Collision detection: `LinkError` raised if user-declared entities/workspaces conflict with synthetic admin names (#686)
- Admin LIST surfaces for all synthetic entities with admin-persona access control (#686)
- Content-hash cache busting: `static_url` Jinja2 filter rewrites asset paths with SHA-256 fingerprints — no build step (#711)
- Project layout convention: recommended `app/` directory structure for custom Python code; `dazzle init --with-app` scaffold (#715)
- Security profile reference: `docs/reference/security-profiles.md` with profile comparison and admin region tables (#705)
- Template override docs: `dz://` prefix, declaration headers, available blocks (#710)

### Fixed
- Feedback widget retry toast no longer shown on page load — silent mode for background retries (#708)
- CSS sidebar hidden on desktop — moved `dz.css` out of `@layer(framework)` so overrides beat DaisyUI (#709)

### Changed
- All schema changes (including framework entities) now go through Alembic — removed raw ALTER TABLE startup path (ADR-0017, #713)
- Virtual entities (SystemHealth, SystemMetric, ProcessRun) excluded from SA metadata — no phantom PostgreSQL tables (#713)

### Deprecated
- Founder console routes (`/_ops/`, `/_console/`) — `X-Dazzle-Deprecated` header added, will be removed in a future release (#686)

### Agent Guidance
- **Admin workspace entities**: The linker now generates synthetic entities with `domain="platform"`. Tests and tools that count entities should filter these out (e.g., `[e for e in entities if e.domain != "platform"]`).
- **Entity naming**: Don't declare entities named `SystemHealth`, `SystemMetric`, `DeployHistory`, `ProcessRun`, or `SessionInfo` — these are reserved by the admin workspace and will cause a `LinkError`.
- **Schema migrations**: Use `dazzle db revision -m "description"` then `dazzle db upgrade` for ALL schema changes, including framework entities. No raw ALTER TABLE (ADR-0017).
- **Static assets in templates**: Use `{{ 'css/file.css' | static_url }}` instead of bare `/static/css/file.css` paths. The filter adds content-hash fingerprints for cache busting.
- **Project layout**: Custom Python code goes in `app/<category>/` (db, sync, render, qa, demo). One-shot scripts go in `scripts/`. Don't create flat `pipeline/` directories.
- **Security profiles**: All three profiles (basic/standard/strict) now include auth and an admin workspace. See `docs/reference/security-profiles.md` for which regions each profile gets.

## [0.48.11] - 2026-03-25

### Fixed
- Feedback widget POST 422: `reported_by` now populated from session email, field made optional (#687)
- Feedback widget CSS: converted `oklch()` to `hsl()` to match design system variable format (#690)
- Missing favicon `<link>` in app `base.html` — 404 console error on all app pages (#691)
- `/__test__/reset` now reads `.dazzle/test_credentials.json` for user creation instead of generic emails (#688)
- Dead-construct lint false positives: surfaces reachable via `nav_group` entity items no longer flagged (#689)

### Agent Guidance
- **FeedbackReport idempotency**: The `idempotency_key` field (str(36), unique) was added to FeedbackReport in #693. Existing deployments need `dazzle db upgrade` to add the column.

## [0.48.10] - 2026-03-25

### Changed
- `process_manager` added to `RuntimeServices`, task route handlers use `Depends(get_services)` (#673)
- Rate-limit globals replaced with `_Limits` dataclass container — eliminates `global` keyword (#673)
- `runtime_tools/state.py` globals (`_appspec_data`, `_ui_spec`) moved to `ServerState` (#673)
- `api_kb/loader.py` cache globals (`_pack_cache`, `_packs_loaded`, `_project_root`) moved to `ServerState` (#673)
- All 17 remaining `global` statements annotated with `# noqa: PLW0603` and mandatory reason (#673)

### Removed
- `src/dazzle/mcp/runtime_tools/state.py` — module deleted, state migrated to `ServerState` (#673)
- `get_process_manager()`, `set_process_manager()` global singleton functions (#673)
- `api_kb.loader.set_project_root()` — cache clearing handled by `ServerState.set_project_root()` (#673)

### Agent Guidance
- **No new singletons** (ADR-0005): Access runtime services via `Depends(get_services)` in route handlers or `request.app.state.services` in middleware. Do not create module-level mutable state.

## [0.48.9] - 2026-03-25

### Changed
- 6 HIGH-risk module-level mutable singletons in `dazzle_back` consolidated into `RuntimeServices` dataclass on `app.state.services` (#673)
- Route handlers access services via `Depends(get_services)`, middleware via `request.app.state.services` (#673)
- Tests use pytest fixtures creating fresh instances instead of global reset functions (#673)

### Removed
- `get_event_bus()`, `set_event_bus()`, `reset_event_bus()` global singleton functions (#673)
- `get_presence_tracker()`, `set_presence_tracker()`, `reset_presence_tracker()` global singleton functions (#673)
- `get_framework()`, `init_framework()`, `shutdown_framework()` global singleton functions (#673)
- `get_collector()`, `reset_collector()`, `get_system_collector()`, `reset_system_collector()` global singleton functions (#673)
- `get_emitter()`, `emit()` global singleton functions (#673)

## [0.48.8] - 2026-03-25

### Changed
- CSS delivery default flipped to local-first (`_use_cdn = False`); CDN opt-in via `[ui] cdn = true` in `dazzle.toml` (#671)
- CSS Cascade Layers (`@layer base, framework, app, overrides`) added to `base.html` and `site_base.html` for explicit cascade ordering (#671)
- New `dazzle-framework.css` entry point replaces standalone `dz.css` loading in local mode (#671)
- `css_loader.py` updated with canonical CSS order, `@layer framework` wrappers, and inline source map (#671)
- `build_dist.py` produces layer-aware `dazzle.min.css` with `@layer framework` wrappers (#671)
- CI publish workflow rebuilds `dist/` at release time for CDN freshness (#671)

### Agent Guidance
- **CSS is local-first**: Static CSS/JS are served from the app, not CDN. The CDN path is opt-in via `[ui] cdn = true` in `dazzle.toml`.
- **Cascade layers**: CSS uses `@layer base, framework, app, overrides`. Framework styles go in `layer(framework)`. Exception: `dz.css` is unlayered so its sidebar overrides beat DaisyUI's unlayered drawer styles.

## [0.48.7] - 2026-03-25

### Fixed
- Workspace regions returning 0 rows: UUID FK attrs from psycopg3 silently dropped in session preferences (#684)
- Feedback widget POST 403 on deployed sites: route now uses direct SQL insert instead of nonexistent repository
- Feedback widget CSS missing from CDN bundle — added to `build_dist.py`

### Added
- Positive auth resolution tests: verify UUID FK attrs resolve through full auth chain, not just deny paths (#684)

### Changed
- PostgreSQL CI job runs only `pytest.mark.postgres` tests (127 tests) instead of full suite (9,143) — ~3 min saved per run

## [0.48.6] - 2026-03-25

### Changed
- `eval_comparison_op` extracted to `dazzle.core.comparison` — eliminates 60-line duplication between `_comparison.py` and `condition_eval.py` (#675)
- `appspec: Any` replaced with `appspec: AppSpec` via `TYPE_CHECKING` across 5 agent mission files (#676)
- `EventFramework.get_bus()` public method replaces all direct `framework._bus` access (#678)
- `AuthStore` public API: `count_users`, `count_active_sessions`, `list_distinct_roles`, `list_sessions`, `store_totp_secret_pending` — eliminates 7 external `_execute` calls (#672)
- `_fastapi_compat.py` TYPE_CHECKING imports — mypy sees real FastAPI types, removes type: ignore cascade (#677)
- `route_generator.py` public handler signatures typed with `BaseService`, `EntityAccessSpec`, `AuditLogger` (#680)

## [0.48.5] - 2026-03-25

### Fixed
- `has_grant()` state machine guard: properly enter `db.connection()` context for GrantStore — was passing context manager generator instead of connection (#669)
- `has_grant()` diagnostic logging: WARNING on missing store/IDs/UUID failures, DEBUG on query results (#669)
- UUID objects passed through without re-casting in `has_grant()` (#669)
- Feedback widget POST route registered at `/feedbackreports` when `feedback_widget.enabled` — was returning 403/404 (#670)

### Changed
- 7 `# type: ignore[no-any-return]` on `json.loads()` replaced with explicit variable annotations (#682)

## [0.48.4] - 2026-03-24

### Added
- SOC 2 Trust Services Criteria taxonomy — 63 controls across 5 categories with DSL evidence mappings (#657)
- Reference documentation for graph features (CTE neighborhood, NetworkX algorithms, domain-scoped graphs) (#656)
- Reference documentation for compliance framework (ISO 27001 + SOC 2 pipeline, CLI, evidence mapping) (#656)
- Grant-based RBAC section in access-control reference (grant_schema, has_grant, four-eyes approval) (#656)
- System endpoints (/health, /_diagnostics) and feedback widget in runtime-capabilities reference (#656)

## [0.48.3] - 2026-03-24

### Fixed
- Connection pool auto-rollback on failed transactions — prevents cascading 500s from poisoned connections (#664)
- `RedisBus.start_consumer_loop()` accepts `poll_interval` kwarg to match base class signature (#662)
- FK fields on detail pages now resolve to `display_field` values instead of showing raw UUIDs (#663)
- ParamRef resolved to its default value before use as field default in `_build_column` (#641)
- GrantStore supports PostgreSQL `%s` placeholders (#640)

### Changed
- Pool `open_pool()` passes a `reset` callback to rollback aborted transactions on connection return
- Detail view template checks `{relation_name}_display` key for ref fields, matching list surface behaviour
- Nav group route dedup prevents entity items appearing in both flat nav and grouped accordion (#661)
- Feedback widget CSS uses oklch fallback values for opaque backgrounds (#660)

## [0.48.2] - 2026-03-24

### Changed
- Event system is now PostgreSQL-only — removed all aiosqlite/SQLite code paths from outbox, inbox, consumer, publisher, and framework (#644)
- `OutboxPublisher`, `IdempotentConsumer`, `idempotent()`: `db_path` parameter removed — use `connect=` instead
- `EventFrameworkConfig`: `db_path` field removed — use `database_url` instead
- `EventOutbox`: `use_postgres` parameter removed — always PostgreSQL
- `EventInbox`: `placeholder`/`backend_type` parameters removed — always PostgreSQL
- Canary dependency probe changed from `aiosqlite` to `psycopg` in `null.py`

### Agent Guidance
- **PostgreSQL only** (ADR-0008): No SQLite code paths remain. All database operations use PostgreSQL via psycopg. Don't propose SQLite as a fallback or dev convenience.

### Fixed
- Feedback widget Jinja global set after `configure_project_templates()` to survive env replacement (#649)
- Workspace grid uses CSS columns for masonry-style card layout — eliminates whitespace gaps (#648)
- `/health` endpoint now reports `version`, `dsl_hash`, and `uptime_seconds` (#651)
- Queue display uses `_display` sibling key for FK ref columns instead of raw dict repr (#654)
- `_eval_func` implements `has_grant()` for state machine transition guards (#653)
- `grant_routes`: `_check_granted_by` reads from `GrantRelationSpec`, not `GrantSchemaSpec` (#650)

### Added
- `/_diagnostics` endpoint (admin-only) returning entity/surface/workspace counts and feature flags (#651)
- Lint warning for FK-target entities missing `display_field` (#652)
- `_extract_roles` helper for compound `ConditionExpr` trees in grant routes (#650)

### Removed
- `aiosqlite` dependency from `events` and `dev` extras in pyproject.toml (#644)
- SQLite DDL constants from outbox.py and inbox.py (#644)
- All `db_path` deprecation shims from event system (#644)

## [0.48.1] - 2026-03-24

### Fixed
- `grant_routes`: `_check_granted_by` now reads `granted_by` and `approval` from `GrantRelationSpec` instead of `GrantSchemaSpec` — fixes 500 error on all grant creation (#650)

### Added
- `_extract_roles` helper to walk `ConditionExpr` trees for compound role expressions (e.g. `role(admin) or role(manager)`)
- `_get_relation_spec` helper for relation-level lookups within grant schemas
- Unit tests for grant routes (`test_grant_routes.py`)

## [0.48.0] - 2026-03-24

### Agent Guidance
- **Grant-based RBAC**: GrantStore is now PostgreSQL-only with atomic state transitions. Use `has_grant()` in state machine guards. See `src/dazzle_back/runtime/grant_routes.py` for the HTTP API.
- **Template overrides**: Use `{% extends "dz://base.html" %}` to extend framework templates from project overrides. Plain `{% extends "base.html" %}` causes infinite recursion.

### Changed
- GrantStore rewritten as PostgreSQL-only — removed all SQLite code paths, `_sql()` helper, and `placeholder` parameter
- Grant tables now use native PostgreSQL types: UUID columns, TIMESTAMPTZ timestamps, JSONB metadata
- State transitions use atomic `UPDATE WHERE status + rowcount` pattern — eliminates TOCTOU race conditions
- `list_grants` uses dynamic WHERE clause construction instead of `IS NULL OR` anti-pattern
- `expire_stale_grants` uses `RETURNING id` for single-pass batch expiry
- `grant_routes.py` docstring and constructor updated for psycopg (was sqlite3)

### Added
- `cancel_grant` transition: `pending_approval → cancelled` (by the granter)
- CHECK constraints on `_grants.status` and `_grant_events.event_type` columns
- Partial index `idx_grants_expiry` for active grants with expiry dates
- FK index `idx_grant_events_grant_id` on grant events table
- Cancel endpoint: `POST /api/grants/{id}/cancel`
- UUID validation at HTTP boundary in grant routes (`_parse_uuid` helper)
- Concurrency tests proving one-winner property for competing state transitions
- PostgreSQL integration tests via `TEST_DATABASE_URL` (skip when not set)

### Removed
- SQLite support in GrantStore — PostgreSQL is the sole supported backend
- `_sql()` placeholder rewriting helper
- `placeholder` parameter on GrantStore constructor

## [0.47.2] - 2026-03-23

### Fixed
- Rebuilt `dist/dazzle.min.js` CDN bundle — stale `dzWorkspaceEditor` signature caused Alpine init failure (#638)
- Context selector `scope_field` now reads domain attributes from `auth_ctx.preferences` instead of `user_obj` (#639)
- Data island `layout_json` uses `| safe` filter to prevent Jinja2 entity-encoding inside `<script>` tags (#635 follow-up)

## [0.47.1] - 2026-03-23

### Fixed
- Workspace layout JSON now embedded as `<script type="application/json">` data island instead of inlined in `x-data` HTML attribute — eliminates JSON/HTML escaping conflict (#632, #635)
- Nav: workspace home link now renders above collapsible nav_groups (#630)
- Heatmap region click-through uses FK target entity ID instead of source item ID (#633)
- Tailwind safelist for `col-span-{4,6,8,12}` at responsive breakpoints — workspace card width customisation now takes effect (#631)
- Context selector: `scope_field` wired into options route + `htmx.ajax()` for unconditional region refresh (#634)
- Event framework startup hang with remote Postgres: added `connect_timeout=10` + lazy pool open + REDIS_URL forwarding (#636)

### Added
- Grant management API: `POST/GET/DELETE /api/grants/*` endpoints wrapping existing `GrantStore` — unblocks `has_grant()` transition guards (#629)
- `dazzle serve --local-assets/--cdn-assets` flag — serve JS/CSS from local installation instead of CDN; defaults local in dev, CDN in production (#637)

## [0.47.0] - 2026-03-23

### Added
- `feedback_widget` DSL keyword with parser mixin, IR model (`FeedbackWidgetSpec`), and auto-entity generation
- Auto-generated `FeedbackReport` entity with lifecycle state machine (new → triaged → in_progress → resolved → verified) when `feedback_widget: enabled` is declared
- Client-side feedback widget (JS/CSS) injected into authenticated pages — safe DOM construction, idempotency keys, rate limiting, offline retry
- Apps can override auto-entity by declaring their own `FeedbackReport` entity

### Changed
- Database migrations now use Alembic instead of hand-rolled `MigrationPlanner`
- `dazzle db migrate` generates and applies migrations in one step
- `dazzle db rollback` reverts migrations with optional revision target
- Type changes detected automatically via `compare_type=True`
- `dazzle serve --production` refuses to start with pending migrations
- Linker `_parse_field_type` now supports `ref <Entity>` and `float` types

### Added
- Compliance documentation compiler: maps DSL metadata to framework controls
- `dazzle compliance compile` / `evidence` / `gaps` CLI commands
- MCP `compliance` tool with 5 operations (compile, evidence, gaps, summary, review)
- ISO 27001:2022 taxonomy (93 controls, 4 themes)
- Pydantic models for Taxonomy, EvidenceMap, AuditSpec IR
- `[compliance]` optional extra in pyproject.toml
- Safe cast registry: text→uuid, text→date, text→timestamptz, text→jsonb applied automatically with USING clauses
- `dazzle db migrate --check` dry-run to preview schema changes
- `dazzle db migrate --tenant <slug>` for per-tenant schema migration

### Removed
- `MigrationPlanner`, `MigrationExecutor`, `MigrationHistory` classes (~400 lines)
- `auto_migrate()` / `plan_migrations()` functions — replaced by Alembic

## [0.46.5] - 2026-03-23

### Fixed
- 77 mypy type errors across `dazzle_back` and `dazzle.core` (Redis async unions, bare `dict` params, missing `column` arg in `make_parse_error`, missing `_build_graph_filter_sql`)
- Gitignore `.claude/projects/` local session data

## [0.46.4] - 2026-03-22

### Fixed
- Suppress misleading "permit without scope" linter warning on framework-generated entities (e.g. AIJob from `llm_intent` blocks)

## [0.46.3] - 2026-03-22

### Added
- `--production` flag on `dazzle serve` — binds 0.0.0.0, reads PORT env var, requires DATABASE_URL, structured JSON logging, disables dev features
- `dazzle deploy dockerfile` — generates production Dockerfile + requirements.txt
- `dazzle deploy heroku` — generates Procfile, runtime.txt, requirements.txt
- `dazzle deploy compose` — generates production docker-compose.yml

### Removed
- Container runtime (`dazzle_ui.runtime.container`) — replaced by `dazzle serve --production`
- `DockerRunner` and Docker template generation — replaced by `dazzle deploy`
- `dazzle rebuild` command — prints migration message directing to `dazzle deploy dockerfile`

### Fixed
- `float` type missing from frontend spec export `FIELD_TYPE_MAP`
- `target:` keyword not recognized in integration transform block parser
- Stale test snapshots for graph semantics and streamspec error types
- Content negotiation test mocks returning truthy MagicMock for `query_params.get()`

## [0.46.2] - 2026-03-22

### Fixed
- Legacy scope condition path (via clauses) now catches exceptions instead of 500 (#617)
- Graph materialization SQL uses `quote_identifier` for defense-in-depth

## [0.46.1] - 2026-03-22

### Added
- `float` field type — IEEE 754 double precision for sensors, weights, and scores (#620)

### Fixed
- Float type included in tagged release (v0.46.0 tag predated the float commit)

## [0.46.0] - 2026-03-22

### Added
- **Graph Semantics** — full directed property multigraph support in the DSL (#619)
  - Phase 1: `graph_edge:` and `graph_node:` blocks on entities with validation and lint hints
  - Phase 2: `?format=cytoscape|d3` on edge entity list endpoints via `GraphSerializer`
  - Phase 3: `GET /{entity}/{id}/graph?depth=N` neighborhood traversal via PostgreSQL recursive CTE
  - Phase 4: Shortest path and connected components via optional NetworkX integration
- Domain-scoped graph algorithms (per-work graph partitioning via filter params)
- `networkx>=3.0` as optional `[graph]` extra

## [0.45.5] - 2026-03-22

### Added
- Graph algorithms: shortest path + connected components endpoints (#619 Phase 4)
- `GraphMaterializer` — on-demand DB → NetworkX graph materialization
- Domain-scoped algorithms via filter params (`?work_id=uuid`) for partitioned graphs
- NetworkX as optional dependency (`pip install dazzle-dsl[graph]`)

## [0.45.4] - 2026-03-22

### Added
- Neighborhood endpoint: `GET /{entity}/{id}/graph?depth=N&format=cytoscape|d3` (#619 Phase 3)
- `NeighborhoodQueryBuilder` — PostgreSQL recursive CTE for graph traversal
- Directed and undirected traversal with automatic cycle prevention via UNION
- Scope predicate injection into CTE WHERE clauses
- Configurable depth bound (1–3 hops)

## [0.45.3] - 2026-03-22

### Added
- Graph serializer: `?format=cytoscape|d3` on edge entity list endpoints (#619 Phase 2)
- `GraphSerializer` class for Cytoscape.js and D3 force-graph JSON output
- Heterogeneous graph support (bipartite graphs with different node entity types)
- Node batch-fetch with scope/permit enforcement

## [0.45.2] - 2026-03-22

### Added
- `graph_edge:` and `graph_node:` blocks on entities — formal graph semantics declarations (#619)
- Graph validation: field references, type checks, cross-entity consistency
- Lint hints: suggest `graph_edge:` for entities with 2+ refs to same entity, suggest `graph_node:` for targeted entities
- Grammar reference updated with graph semantics BNF

## [0.45.1] - 2026-03-22

### Fixed
- CDN bundle at v0.45.0 tag missing Alpine + workspace editor — rebuilt with all components (#615, #618)
- CSRF middleware rewritten as pure ASGI to fix body consumption (#606)
- Scope predicate resolution: most-permissive-wins for dual-role users (#604), pass-through for no-scope entities (#607), Tautology detection (#604)
- Graceful handling of null FK in EXISTS scope bindings (#617)
- MCP db handlers converted to async (#609), topology/triggers import path fixed
- `/create` guard routes registered before `/{id}` routes (#598)
- Circular FK references demoted to warning (#608), decimal parse error improved (#610)
- EntitySpec.relations and FieldSpec.unique API mismatches in migrate (#616)
- Workspace action URL interpolation with cross-entity FK fields (#614)
- Lucide sourcemap 404 in Safari stripped
- Security test updated for CSRF middleware class rename
- `/check` and `/ship` mypy targets aligned with CI (src/dazzle_back/)

### Added
- 15 runtime contract KB entries (display_field, scope, CSRF, request lifecycle, etc.)
- Purpose-annotated `implemented_by` on KB concepts
- `graph topology` operation — derive project structure from DSL
- Knowledge effectiveness metrics in telemetry
- `/improve` autonomous improvement loop (BDD pattern)
- Alpine.js `$persist` plugin for localStorage state
- Example app DSL quality improvements across 6 apps (scope blocks, workspace wiring, ux blocks)

### Changed
- dz.js fully retired — all UI state managed by Alpine.js components in dz-alpine.js

## [0.45.0] - 2026-03-21

### Added
- **Conformance Role 2**: HTTP execution engine — boots FastAPI in-process, seeds fixtures via `/__test__/seed`, runs all derived cases as HTTP assertions (#601)
- **Stage invariant verification**: three-stage verifier for predicate compilation chain (ConditionExpr → ScopePredicate → SQL → resolved params) (#603)
- **Runtime contract monitoring**: `ConformanceMonitor` captures access decisions during scenario execution and compares against expected conformance cases (#602)
- `dazzle conformance execute` CLI command for running HTTP conformance against PostgreSQL
- `monitor_status` MCP operation on conformance tool
- `?q=` alias for `?search=` on all API list endpoints (#596)
- Bare `?field=value` query params accepted when field is in DSL `ux: filter:` list (#596)
- `build_entity_filter_fields()` extracts filter allowlist from surface UX declarations
- Alpine.js `$persist` plugin (835B) for localStorage state management
- `dz-alpine.js` — Alpine.data() components replacing dz.js: dzToast, dzConfirm, dzTable, dzMoney, dzFileUpload, dzWizard (#600)
- `param` DSL construct for runtime-configurable parameters with tenant-scoped cascade (#572)
- `param("key")` reference syntax in workspace region constructs (heatmap thresholds)
- `_dazzle_params` table for storing per-scope parameter overrides
- `param list/get/validate` MCP operations and CLI commands
- Startup validation of stored param overrides against DSL declarations
- `dazzle e2e journey` — persona-driven E2E testing against live deployments (#557)
- Two-phase execution: deterministic workspace exploration + LLM story verification
- Cross-persona pattern analysis with structured HTML reports
- `test_intelligence journey` MCP operation (read-only)
- `.dazzle/test_personas.toml` credential file for journey testing
- `dazzle demo propose` now generates test persona credentials
- `not via` syntax for NOT EXISTS scope rules
- `not (...)` parenthesised negation in scope rules
- depth-N FK path traversal in scope rules (previously depth-1 only)
- Static validation of scope rule FK paths at `dazzle validate` time
- Runtime startup assertion verifies all scope predicates compile

### Changed
- Scope rules compile to formal ScopePredicate algebra with FK graph validation
- OR conditions in scope rules now compile to SQL OR (previously post-fetch filtered)
- Template strings replaced with contextual variables (`app_name`, `entity_name`) across 10 templates (#593)
- Console routes derive `app_name` from AppSpec instead of hardcoding "Dazzle Console"
- All UI state management migrated from dz.js to Alpine.js (#600)

### Removed
- `dz.js` micro-runtime (1102 lines) — replaced by Alpine.js components in `dz-alpine.js`
- Post-fetch OR filtering for scope rules (replaced by SQL OR)

### Fixed
- CSRF middleware now exempts `/__test__/` and `/dazzle/dev/` paths (internal-only endpoints)

## [0.44.0] - 2026-03-19

### Added
- **Schema-per-tenant isolation** — `TenantMiddleware` with subdomain/header/session resolvers, registry cache, `pg_backend` context-var routing, `--tenant` flag on `dazzle db` commands (#531)
- **Domain user attribute resolution** — auth session validation merges DSL User entity fields into `auth_context.preferences` so scope rules like `current_user.school` resolve correctly (#532)
- **Via clause entity ID resolution** — bare `current_user` in via clauses now resolves to DSL User entity PK via `preferences["entity_id"]` (#534)
- **DSL anti-pattern guidance** — 5 modeling anti-patterns (polymorphic keys, god entities, soft-delete booleans, stringly-typed refs, duplicated fields) surfaced via inference KB, lint warnings, and `_guidance` string
- **External action links** — new `OutcomeKind.EXTERNAL` and `external` keyword for URL-based action links on surfaces (#542)
- **Docker dev infrastructure** — `dazzle serve` (Docker mode) now starts Postgres+Redis via Docker Compose while running the app locally (#540, #541)

### Fixed
- Scope rules using `current_user.school` resolve to null — auth users lacked domain attributes (#532)
- Via clause `current_user` resolved to auth user ID instead of DSL entity ID (#534)
- Test generator didn't populate nullable FKs required by 3-way OR invariants (#533)
- 4 pre-existing CI failures (type-check, security tests, PostgreSQL tests, E2E smoke) all resolved
- 6 bare `except Exception: pass` sites given proper logging
- `_pack_cache` thread-safety gap fixed via atomic snapshot replacement
- HTTP retry coverage gap — 4 unretried outbound call sites retrofitted
- Docker container runtime SQLite → PostgreSQL default (#541)

### Changed
- **`server.py` subsystem migration** — reduced from 2,214 to 936 lines; `IntegrationManager` and `WorkspaceRouteBuilder` moved to standalone modules; circular import with `app_factory.py` eliminated (#535)
- **Route factory extraction** — all 13 route factory mega-functions (300-784L each) refactored: handlers extracted to module level with `_XxxDeps` dataclasses, factories shrunk to route registration (#536)
- **Parser nesting depth** — top 4 offenders flattened: `execute_step` (depth 24→dispatch), `_parse_single_step` (22→field parsers), `parse_type_spec` (20→sub-parsers), `handle_runtime_tool` (18→dispatch table) (#537)
- **`dazzle_back` public API** — `__init__.py` exports 11 symbols via lazy loaders; CLI/MCP no longer reach into `dazzle_back.runtime.*` internals (#539)
- Duplicated `error_response`/`unknown_op_response` in `handlers_consolidated.py` removed
- 8 `Any` annotations replaced with concrete `TYPE_CHECKING` types
- `ViaBinding` and `ViaCondition` added to `ir.__init__.__all__`
- Shapes validation DSL fixed: `or` syntax in permit blocks, missing PKs and persona

## [0.43.0] - 2026-03-18

### Added
- **RBAC Verification Framework** — three-layer provable access control: static access matrix (Layer 1), dynamic verification (Layer 2), decision audit trail (Layer 3)
- `dazzle rbac matrix` CLI command — generate (role, entity, operation) → permit/deny matrix from DSL
- `dazzle rbac verify` CLI command (stub) — dynamic verification pipeline
- `dazzle rbac report` CLI command — compliance report from verification results
- `policy access_matrix` and `policy verify_status` MCP operations
- `src/dazzle/rbac/` package: `matrix.py`, `audit.py`, `verifier.py`, `report.py`
- `AccessDecisionRecord` audit trail with pluggable sinks (Null, InMemory, JsonFile)
- `evaluate_permission()` instrumented to emit audit records on every decision
- `examples/shapes_validation/` — abstract RBAC validation domain (7 personas, 4 entities) exercising RBAC0/RBAC2/ABAC/multi-tenancy patterns
- CI security gate: Shapes RBAC matrix validated on every push (fails if any entity is PERMIT_UNPROTECTED)
- Two-tier access control evaluation model documented in `docs/reference/access-control.md`
- RBAC verification deep-dive with academic references in `docs/reference/rbac-verification.md`
- README "Provable RBAC" section

### Fixed
- **Critical: LIST gate silently disabled for all role-based access rules** (#520) — `_is_field_condition()` now correctly classifies role_check conditions as gate-evaluable
- Sidebar navigation not filtered by role — restricted workspaces now hidden from unauthorized users (#521)
- Workspace region filters fall back to unfiltered when result is empty (#522)
- HTMX workspace region loading no longer causes unintended page navigation (#523)
- URL scheme validation in `_sync_fetch` prevents file:// SSRF (#519)
- SQL table name validation in control_plane `_delete_all_rows()` (#519)

### Changed
- 14 code smells fixed from systematic analysis (#504–#518): `_sessions` race condition locked, `__self_service__` monkey-patch removed, comparison logic deduplicated across 3 evaluators, 6 `_generate_field_value` implementations consolidated, FastAPI import guards centralized, HTTP error responses standardized, mutable globals protected with locks, core→backend layer boundary restored, dazzle_ui→dazzle_back dependency made one-directional, subsystem plugin infrastructure created, deep nesting reduced in parser/tokenizer/test runner
- `DazzleBackendApp` partially decomposed into subsystem plugins (9 modules, 6 dead `_init_*` methods removed)

### Removed
- `__self_service__` dynamic attribute pattern in route_generator.py
- 17 duplicate FastAPI import guard blocks (replaced by `_fastapi_compat.py`)
- `hx-push-url="true"` from workspace region templates (redundant with drawer JS)

## [0.42.0] - 2026-03-14

### Added
- **Surface field visibility by role** (`visible:` condition on sections and fields) — role-based RBAC for hiding sensitive fields/sections without duplicating surfaces (#487)
- `visible:` supports `role()`, `has_grant()`, compound `and`/`or` via existing ConditionExpr system
- `visible:` and `when:` can coexist on the same field (role-based vs data-driven visibility)
- **Grant schema infrastructure** — `grant_schema` DSL construct with `relation` sub-blocks, `has_grant()` condition function, `GrantStore` runtime with SQLite-backed CRUD and audit events
- Grant pre-fetching in workspace rendering for synchronous condition evaluation

### Fixed
- Pulse compliance scoring now reads DSL `classify` directives (confidence=1.0) before pattern matching (#488)
- Pulse security scoring counts default-deny as deliberate secure posture instead of penalising it (#488)
- `when_expr` silently dropped in multi-section (wizard) surface forms — now correctly propagated
- Auto-generate READ endpoints for entities with LIST surfaces (#482)
- Resolve `current_user` in workspace filters in test mode (#483)
- Cross-entity navigation resolved by shared workspace nav_groups (#477)
- Infer experience reachability from access spec (#476)

## [0.41.1] - 2026-03-12

### Changed
- `dazzle workshop` rewritten from Rich to Textual TUI with keyboard-driven drill-down
  - DashboardScreen: live active tools + recent completed history
  - SessionScreen: all calls grouped by tool, collapsible groups
  - CallDetailScreen: full progress timeline for a single call
  - Navigation: Enter to drill in, Esc to go back, j/k for movement
- Workshop now requires `textual>=1.0.0` via optional `workshop` extra

### Added
- Handler progress instrumentation: 15 handlers now emit structured progress events
  - pipeline, story.coverage, dsl_test, sentinel, composition, e2e_test,
    dsl.validate, dsl.fidelity, discovery, process.coverage, nightly
- `context_json` on tool completion events for structured summaries in workshop

## [0.41.0] - 2026-03-12

### Added
- **Convergent BDD:** `rule` DSL construct — domain-level business invariants with `kind` (constraint/precondition/authorization/derivation), `origin` (top_down/bottom_up), and `invariant` fields
- **Convergent BDD:** `question` DSL construct — typed specification gaps that block artifacts until resolved, with `blocks`, `raised_by`, and `status` fields
- `exercises:` field on stories — links stories to rules they exercise for convergence tracking
- Rule and question parser mixins (`RuleParserMixin`, `QuestionParserMixin`)
- Rule and question emitters (`emit_rule_dsl`, `emit_question_dsl`, `append_rules_to_dsl`, `append_questions_to_dsl`)
- Linker validation: rule scope, story exercises, question blocks, open-question-blocks-accepted-artifact error
- MCP operations: `rule_propose`, `rule_get`, `rule_coverage`, `question_get`, `question_resolve` (story tool); `converge`, `question_raise` (discovery tool)
- `rule(coverage)` and `rule(converge)` pipeline quality steps
- Convergence handler: structural analysis of rule-story alignment, gap detection, coverage scoring
- Semantics KB: `rule`, `question`, `convergence` concepts with aliases and relations

### Changed
- **Breaking:** Stories now use DSL-only persistence (`dsl/stories.dsl`) — removed JSON persistence layer (`stories.json`, `StoriesContainer`, `_inject_json_stories`)
- **Breaking:** `unless` keyword on stories raises parse error — use `rule` construct with boundary stories instead
- Story IR uses Gherkin fields (`given`, `when`, `then`) — removed legacy fields (`preconditions`, `happy_path_outcome`, `side_effects`, `constraints`, `variants`, `created_at`, `accepted_at`)
- `rbac_validation` example migrated from `unless` to rule + boundary story pattern

### Removed
- `StoryException` class and `unless` field from `StorySpec`
- `unless` handling from fidelity scorer, process proposals, process coverage, serializers
- `unless_block` from grammar
- `src/dazzle/core/stories_persistence.py` — JSON read/write layer
- `StoriesContainer` class and `with_status()` / `effective_given` / `effective_then` helpers
- `_inject_json_stories()` from appspec loader

## [0.40.0] - 2026-03-11

### Added
- Rhythm fidelity metric: `fidelity` operation measures how well surfaces serve scene intent by comparing `expects:` keywords against surface field names (#450)
- Surface reuse detection: `evaluate` handler flags surfaces used in multiple scenes with divergent `expects:` values as specialization signals (#448)
- Standardized action vocabulary: 7 action verbs mapped to 3 archetypes (observe, act, decide) with `classify_action()` API and advisory warnings for non-standard verbs (#449)
- Phase-level `depends_on:` field for declaring phase ordering constraints with circular dependency detection (#451)
- Phase kind `gate` for mandatory completion phases (#451)
- Phase-level `cadence:` field for temporal frequency hints (#447)
- Persona-scoped coverage metric respecting surface ACL `allow_personas`/`deny_personas` (#446)
- Scenes can target workspaces via `on:` field, tracked separately in coverage (#445)

### Fixed
- Rhythm `story:` field now accepts quoted strings for hyphenated IDs like `"ST-020"` (#452)

## [0.39.0] - 2026-03-11

### Added
- Rhythm DSL construct: `rhythm`, `phase`, `scene` keywords for longitudinal persona journey evaluation (#444)
- Rhythm MCP tool with 5 operations: `propose`, `evaluate`, `coverage`, `get`, `list`
- Static rhythm evaluation: surface existence, entity coverage, navigation coherence checks
- Rhythm conceptual guide (`docs/guides/rhythms.md`) and reference page (`docs/reference/rhythms.md`)

## [0.38.1] - 2026-03-10

### Added
- Declarative transition side effects: `on_transition:` blocks fire `create`/`update` actions on entity state changes (#435)
- Configurable per-field max upload size: `file(200MB)` DSL syntax overrides global security profile limit (#436)
- Post-upload event hook: `FILE_UPLOADED` event emitted to event bus after file upload with entity context; `entity.post_upload` hook point for Python hooks (#437)

## [0.38.0] - 2026-03-09

### Fixed
- Nav group `items` key collision with Python `dict.items()` in Jinja2 — renamed to `children` to fix TypeError/500 on workspace pages with nav_groups (#421)

### Added
- Documentation infrastructure: `dazzle docs generate` renders TOML knowledge base into human-readable reference docs; `dazzle docs check` validates coverage
- 17 auto-generated reference doc pages covering all DSL constructs (entities, access control, surfaces, workspaces, LLM, processes, ledgers, governance, etc.)
- 13 new knowledge base concepts for previously undocumented features (nav_group, approval, SLA, webhook, LLM triggers, visibility rules, etc.)
- README.md overhauled — slimmed from 1247 to 509 lines with auto-generated feature table linking to reference docs
- Deterministic demo data loading: `dazzle demo load` loads seed CSV/JSONL files into a running instance via REST API with FK-aware topological ordering (#420)
- `dazzle demo validate` validates seed files against DSL (FK integrity, enum values, field coverage)
- `dazzle demo reset` clears and reloads demo data (deletes in reverse dependency order, then reloads)
- MCP `demo_data` tool: new `load` and `validate_seeds` operations complete the propose → save → generate → load lifecycle
- LLM intent execution: `/_dazzle/llm/execute/{intent_name}` triggers intents at runtime, records AIJob for cost tracking
- MCP `llm` tool: `list_intents`, `list_models`, `inspect_intent`, `get_config` operations
- Collapsible navigation groups with Lucide icon support in workspace DSL (`nav_group` keyword) and app shell sidebar (#418)
- LLM async event queue: background job queue with token-bucket rate limiting and per-model semaphore concurrency (#417)
- LLM entity triggers: `trigger:` clause on `llm_intent` fires intents on entity created/updated/deleted events with input mapping, write-back, and conditional execution
- `llm_config` gains `concurrency:` block for per-model max concurrent request limits
- Process `llm_intent` step kind: processes can now execute LLM intents as steps with `input_map` context resolution
- Linear checkpointed process executor: sequential step execution with checkpoint-based resume on restart
- Async job execution: `POST /_dazzle/llm/execute/{intent_name}?async_mode=true` queues jobs and returns `job_id`; poll with `GET /_dazzle/llm/jobs/{job_id}`
- MCP `graph` tool: new `triggers` operation shows cross-references (what fires when entity X event Y occurs)
- Workspace context selector: multi-scope users get a dropdown to filter all workspace regions by a scope entity (e.g., School) with preference persistence (#425)
- DSL-driven reference data seeding: entities with `seed:` blocks auto-generate rolling-window rows (academic years, fiscal years) at server startup with idempotent upsert (#428)
- FK traversal support in workspace region filter validation (#419)

## [0.37.0] - 2026-03-07

### Added
- AST-level test verifying all server startup paths pass `app_prefix` to `create_page_routes` — prevents #408-style regressions
- AST-level test ensuring auth routes returning `Response` use `include_in_schema=False` — prevents #411-style regressions

### Changed
- Unified server startup paths: `run_unified_server()` and `create_app_factory()` now share `build_server_config()` and `assemble_post_build_routes()`
- `dazzle serve --local` gains experience routes, entity list projections, search fields, auto-includes, schedule sync
- `create_app_factory()` gains route validation
- `run_backend_only()` gains entity projections and search fields

### Fixed
- `dsl-run --cleanup` now cascade-deletes child records before parents, preventing orphaned rows from FK references (#407)
- Sidebar nav links missing `/app` prefix in `dazzle serve` mode — `combined_server.py` now passes `app_prefix="/app"` to `create_page_routes` (#408)
- `ref_display` chain now recognises `forename`/`surname` fields — FK columns for UK naming conventions show names instead of UUIDs (#409)
- `dsl-run --cleanup` no longer queries API for child records — uses topological sort of tracked entities, avoiding RBAC 403 errors (#410)
- `/openapi.json` no longer crashes with `PydanticUserError` — auth and email tracking routes returning `Response` excluded from schema (#411)

## [0.36.0] - 2026-03-07

### Added
- `events` extras group (`pip install dazzle-dsl[events]`) for optional event system dependency (aiosqlite)
- `NullBus` and `NullEventFramework` no-op implementations in `dazzle_back.events.null` — always importable regardless of extras
- `dazzle_back.events.api` public API boundary module for alternative event bus implementations
- Wire `EventEmittingMixin.set_event_framework()` at server startup (fixes dead code bug)
- Event system imports gated behind `EVENTS_AVAILABLE` flag — apps without event extras stay lean

### Fixed
- Workspace redirect missing `/app` prefix — `_workspace_root_route()` now returns `/app/workspaces/{name}` (#406)
- Login form ignoring persona-specific redirect URL — now uses `redirect_url` from server response (#406)
- Role prefix mismatch preventing persona-based routing — `role_` prefix now stripped when matching user roles against persona IDs in auth redirect, RBAC checks, nav filtering, and workspace access (#406)

## [0.35.0] - 2026-03-06

### Added
- **Team section type** (`type: team`) — dedicated cards for team/people pages with circular avatar (image or auto-generated initials), name, role, bio, and social links (linkedin, email, twitter, github) (#394)
- **Section backgrounds** — `background: alt | primary | dark` on any section for visual rhythm; `layout.section_backgrounds: auto-alternate` for automatic alternating backgrounds (#395)
- **Media rendering** in `card_grid` and `features` sections — `section_media()` macro in `_helpers.html` for reusable section-level images (#396)
- **Validation warning** when `media` is set on section types that don't render it (#396)
- **`sitespec advise` MCP operation** — proactive layout suggestions: missing hero sections, background variation, team section recommendations, long markdown splitting (#397)
- **Media.src path validation** — `sitespec validate` warns on non-`/static/` paths and missing files; imagery prompts include `save_to` and `sitespec_src` fields (#391)
- jsDelivr CDN distribution — framework CSS/JS served from `cdn.jsdelivr.net` for faster loading and cache sharing across Dazzle-powered sites
- `dist/dazzle.min.css` (43 KB) — micro-runtime + design system + site sections CSS bundle
- `dist/dazzle.min.js` (131 KB) — HTMX + extensions + micro-runtime JS bundle
- `dist/dazzle-icons.min.js` (350 KB) — Lucide icons bundle (site pages only)
- `scripts/build_dist.py` — concatenates and minifies framework assets into `dist/`
- `scripts/update_vendors.py` — checks/downloads latest vendor JS versions (htmx, idiomorph, lucide)
- `.github/workflows/update-vendors.yml` — weekly automated vendor update PR
- `[ui] cdn = false` in `dazzle.toml` — disables CDN for air-gapped deployments
- `_dazzle_version` and `_use_cdn` Jinja2 globals in template renderer

### Changed
- `base.html` and `site_base.html` now load framework assets from jsDelivr CDN by default, with local vendored fallback when CDN is disabled

### Fixed
- **Legal page CSS** — constrained width (45rem) and left-aligned headings for terms/privacy pages (#393)
- **Markdown `<hr>` styling** — horizontal rules render as subtle centered gradient lines instead of crude browser default (#398)
- **Infrastructure banner** no longer shows stale `.dazzle/data.db` or "Lite (in-process)" when PostgreSQL is configured (#390)
- **Circular FK migration** — `Department ↔ User` foreign keys no longer fail migration (#389)
- **Heroku deployment** — `[serve]` extra installs runtime dependencies (`uvicorn`, `gunicorn`, etc.) (#388)

### Removed
- `LiteProcessAdapter` and `DevBrokerSQLite` — deprecated SQLite-based process/event backends fully removed; PostgreSQL is now required for event bus
- `SQLITE` tier from `EventBusTier` enum

## [0.34.0] - 2026-02-23

### Added
- `ApiResponseCache` — async Redis cache for external API responses with scoped keys, dedup locking, and lazy connection (`dazzle_back.runtime.api_cache`)
- `cache:` keyword in integration mapping blocks — per-mapping TTL (e.g. `cache: "24h"`) parsed via `parse_duration()`
- Fragment route caching — search (5 min TTL) and select (1 hour TTL) endpoints use shared `ApiResponseCache`
- `cache_ttl` values for all API pack foreign models — data-volatility-appropriate defaults across all 10 packs
- `format_duration()` helper — converts seconds to compact duration strings (86400 → "1d", 300 → "5m")
- `ApiPack.generate_integration_template()` — generates DSL integration blocks with `cache:` directives from pack metadata
- `generate_service_dsl` MCP handler now returns `integration_template` field with recommended cache settings
- Pack TTL fallback in `MappingExecutor` — when no `mapping.cache_ttl` is set, looks up the pack's foreign model `cache_ttl` before falling back to the default
- Built-in entity CRUD operations for process service steps — `Entity.create`, `Entity.read`, `Entity.update`, `Entity.delete`, `Entity.transition` now execute directly against PostgreSQL without requiring custom Python service modules (#345)
- Entity metadata (fields, status_field) stored in Redis at startup by `ProcessManager` for Celery worker access
- `query` step kind — queries entities matching Django-style filters (e.g. `{"due_date__lt": "today", "status__not_in": ["completed"]}`) with date literal resolution (#346)
- `foreach` step kind — iterates over query results and executes sub-steps for each item, enabling batch operations like escalation workflows (#346)
- AI cost tracking gateway — `budget_alert_usd`, `default_provider` on `llm_config`; `vision`, `description` on `llm_intent`; auto-generated `AIJob` entity for cost/token audit trail (#376)
- Integration data transformation — `transform:` block on integration mappings with `jmespath`, `template`, and `rename` expressions (#383)
- Workflow Field Specification (WFS) — `wfs_fields:` block on process steps for field-level read/write/required declarations with runtime enforcement (#375)

### Changed
- `MappingExecutor` now accepts `cache: ApiResponseCache | None` instead of auto-creating sync Redis. All cache operations are async
- Cache keys scoped to `api_cache:{scope}:{url_hash}` preventing collisions across integrations
- Cache TTL priority chain: DSL `cache:` directive > pack TOML `cache_ttl` > default 86400
- Replaced `getattr()` string literals with typed attribute access across agent missions, persona journey, workspace/UI files (#367)
- Eliminated `BackendSpec` from main code path — runtime uses `AppSpec` directly (#369)
- Wired `EventBusProcessAdapter` into app startup, simplified Procfile (#368)
- Eliminated Celery dependency for event bus — native async process adapter (#368)
- Fixed silent exception handlers in event delivery path (#365)

### Improved
- Eliminated 8 swallowed exceptions (`except Exception: pass`) — all now log at appropriate levels (debug/info/warning)
- Extracted Cedar/audit helpers in `route_generator.py` — `_build_access_context()`, `_record_to_dict()`, `_log_audit_decision()` replace ~140 lines of duplicated code across 7 handler closures
- Canonicalized AppSpec loading in `tool_handlers.py` — 7 inline manifest→discover→parse→build patterns replaced with single `load_project_appspec()` calls

### Fixed
- `ProcessStateStore` UUID serialization error — `json.dumps()` now uses a custom encoder that handles `uuid.UUID`, `datetime`, `date`, and `Decimal` objects from psycopg v3 / SQLAlchemy (#344)
- `create_app_factory()` now loads persisted processes from `.dazzle/processes/processes.json` — previously only DSL-parsed processes were used, leaving ProcessManager empty when processes were composed via MCP (#343)
- Sync Redis in async context — replaced `import redis` with `redis.asyncio` in cache layer
- `cache=False/None` still created cache — disabled state now respected via `enabled` flag
- Dedup lock never released — `release_lock()` called in `finally` block after HTTP response
- Lock key collisions across integrations — keys now include `{integration}:{mapping}` scope
- `force_refresh=True` blocked by dedup lock — lock check skipped when force-refreshing
- Blocking `redis.ping()` in constructor — connection is now lazy (first `get()`/`put()`)
- Hardcoded `ssl.CERT_NONE` — removed, uses redis-py defaults (validates certs)
- CI test `test_crud_service_with_repository` — fixture missing surface, service name convention mismatch

### Removed
- `IntegrationCache` class from `mapping_executor.py` — replaced by `ApiResponseCache`

## [0.33.0] - 2026-02-19

### Added
- Canonical AppSpec loader (`dazzle.core.appspec_loader`) — single implementation of manifest → discover → parse → build pipeline, replacing 6 duplicate copies (#329)
- `error_response()` and `unknown_op_response()` factory functions in MCP handler common module, replacing ~100 inline `json.dumps({"error": ...})` calls (#329)
- Experience flow entity orchestration — `context:`, `prefill:`, `saves_to:`, `when:` blocks for multi-entity experience steps (#326)
- Process step side-effect actions for cross-entity automation (#323)
- Multi-source workspace regions with tabbed display (#322)
- Guided review surface mode with queue navigation and approve/return actions (#325)
- Experience flow resume with durable file-based progress persistence (#324)
- Polymorphic FK detection for related entity tabs (#321)

### Changed
- HTMX utilities (`HtmxDetails`, `htmx_error_response`) moved from `dazzle_back` to `dazzle_ui.runtime.htmx` — correct layer ownership (#329)
- Backward compatibility policy: clean breaks preferred over shims; breaking changes communicated via CHANGELOG (#329)

### Removed
- Backward-compat shims: `get_project_path()` alias, pipeline/nightly aliases, archetype→stage aliases, `paths.py` re-export module, `handlers/utils.py` re-export module, `site_renderer.py` shim functions, `DNRDevServer`/`DNRDevHandler` aliases, `docker_runner.py` re-export module (#329)
- Deprecated `db_path` parameters from 6 constructor signatures (`TokenStore`, `AuthStore`, `FileMetadataStore`, `OpsDatabase`, `DeviceRegistry`, `create_local_file_service`, `create_s3_file_service`) (#329)
- CLI utils backward-compat aliases (`_print_human_diagnostics`, etc.) (#329)

### Fixed
- Last 2 swallowed exceptions in `workspace_rendering.py` now log at WARNING level (#329)
- Expression evaluator duplication eliminated — shared `dazzle_ui.utils.expression_eval` module (#327)
- Reduced MCP handler inner catches from 71 to 38 (#327)

## [0.32.0] - 2026-02-17

### Added
- Dead construct detection lint pass — warns on unreachable surfaces, entities with no surfaces, orphaned views, and undefined service references (#279)
- Source locations on IR nodes — parser attaches file/line/column to all major constructs for source-mapped diagnostics (#280)
- Query pre-planning at startup — projection pushdown from surface section fields, not just view-backed surfaces (#281)
- Template constant folding — pre-compute workspace column metadata at startup instead of per-request (#282)
- Workspace query batching — concurrent aggregate metric queries via asyncio.gather (#283)
- `dazzle build --target` codegen pipeline — SQL DDL, OpenAPI, and AsyncAPI code generation targets with `--check` validation-only mode (#284)

## [0.31.0] - 2026-02-17

## [0.30.0] - 2026-02-17

### Added
- Typed expression language: tokenizer, recursive descent parser, tree-walking evaluator, and type checker for pure-function expressions over entity fields (`src/dazzle/core/expression_lang/`) ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Expression AST types: `Literal`, `FieldRef`, `DurationLiteral`, `BinaryExpr`, `UnaryExpr`, `FuncCall`, `InExpr`, `IfExpr` with full operator precedence ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Field expression defaults: `total: int = subtotal + tax` — computed default values using typed expressions on entity fields ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Cross-entity predicate guards on state transitions with FK arrow path syntax: `guard: self->signatory->aml_status == "completed"` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Guard message support: `message: "Signatory must pass AML checks"` sub-clause on transition guards ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Block-mode transition parsing: transitions now support indented sub-blocks alongside existing inline syntax ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Process-aware task inbox with step context enrichment showing position in workflows ([#274](https://github.com/manwithacat/dazzle/issues/274))
- Built-in expression functions: `today()`, `now()`, `days_until()`, `days_since()`, `concat()`, `coalesce()`, `abs()`, `min()`, `max()`, `round()`, `len()` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Invariant expressions consolidated to unified Expr type with `InvariantSpec.invariant_expr` field ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Computed fields consolidated to unified Expr type with `ComputedFieldSpec.computed_expr` field ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Surface field `when:` clause for conditional visibility: `field notes "Notes" when: status == "pending"` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Duration word-form mapping in expression parser: `14 days` → `14d`, `2 hours` → `2h` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Declarative integration mappings: `base_url`, `auth`, `mapping` blocks with HTTP requests, lifecycle triggers, response field mapping, and error strategies ([#275](https://github.com/manwithacat/dazzle/issues/275))

## [0.29.0] - 2026-02-17

### Added
- `sensitive` field modifier for PII masking — auto-masks values in list views, excludes from filters, adds `x-sensitive: true` to OpenAPI schemas ([#263](https://github.com/manwithacat/dazzle/issues/263))
- UI Islands (`island` DSL construct) — self-contained client-side interactive components with typed props, events, entity data binding, and auto-generated API endpoints
- `nightly` MCP tool — parallel quality pipeline with dependency-aware fan-out for faster CI runs
- `sentinel` MCP tool — static failure-mode detection across dependency integrity, accessibility, mapping track, and boundary layer
- `story(scope_fidelity)` operation — verifies implementing processes exercise all entities in story scope, integrated into quality pipeline ([#266](https://github.com/manwithacat/dazzle/issues/266))
- htmx SPA-like UX enhancements: View Transitions API, preload extension, response-targets, loading-states, SSE real-time updates, infinite scroll pagination, optimistic UI feedback, skeleton loading placeholders
- htmx fragment targeting for app navigation — `hx-target="#main-content"` replaces full-body swap for smoother transitions ([#265](https://github.com/manwithacat/dazzle/issues/265))

### Fixed
- Test runner cross-run unique collisions — replaced timestamp-based suffixes with UUID4, regenerate unique fields after design-time overrides ([#262](https://github.com/manwithacat/dazzle/issues/262))
- Persona discovery agent stuck in click loop — extract href from CSS selectors, include element attributes in prompt, start at `/app` not public homepage ([#261](https://github.com/manwithacat/dazzle/issues/261))
- `/_site/nav` authenticated routes returning 404 — fixed double-prefixed page routes and singular slug mismatch ([#260](https://github.com/manwithacat/dazzle/issues/260))
- Entity surface links added to workspace sidebar navigation ([#259](https://github.com/manwithacat/dazzle/issues/259))
- Sitespec review false positives for card_grid, pricing, value_highlight sections ([#258](https://github.com/manwithacat/dazzle/issues/258))
- Visual evaluator false positives from preprocessed images and budget exhaustion ([#257](https://github.com/manwithacat/dazzle/issues/257))
- Sentinel suppress writing invalid status that crashes next scan ([#256](https://github.com/manwithacat/dazzle/issues/256))

## [0.28.2] - 2026-02-16

### Changed
- Split god classes: DazzleBackendApp, KnowledgeGraphHandlers, LiteProcessAdapter into focused sub-classes
- Split large modules: discovery.py and KG handlers.py into packages with focused sub-modules
- Extract BaseEventBus from postgres/redis/sqlite event bus implementations
- Handler factory pattern for consolidated MCP handlers reducing boilerplate
- Centralized path constants in paths.py replacing hardcoded strings
- LSP completion refactored into per-context dispatch for maintainability

### Removed
- Dead tools.py (1623 lines) replaced by tools_consolidated.py

### Fixed
- Error handling in queue/stream adapters for JSON decode and subprocess timeouts
- Type safety: concrete DB return types, TypedDict for structured returns
- ARIA accessibility improvements for generated app interfaces

## [0.28.1] - 2026-02-15

### Fixed
- Composition `analyze` returning false 100/100 when LLM evaluation fails — now returns `visual_score: null` with actual error messages ([#239](https://github.com/manwithacat/dazzle/issues/239))
- Sentinel PR-05 false positives on list surfaces with view-based projections — now counts view fields instead of entity fields ([#238](https://github.com/manwithacat/dazzle/issues/238))
- Sentinel PR-01 false positives for N+1 risk on entities with ref fields — ref fields excluded since runtime auto-eager-loads them ([#238](https://github.com/manwithacat/dazzle/issues/238))

## [0.28.0] - 2026-02-15

### Added
- Agent swarm infrastructure with parallel execution and background tasks ([#224](https://github.com/manwithacat/dazzle/issues/224))
- `--base-url` flag for `dsl-run` to test against remote servers ([#226](https://github.com/manwithacat/dazzle/issues/226))
- File-based MCP activity log for Claude Code progress visibility ([#206](https://github.com/manwithacat/dazzle/issues/206))
- Infrastructure manifest for auto-provisioning services from DSL declarations ([#200](https://github.com/manwithacat/dazzle/issues/200))
- Authenticated UX coherence check for post-login experience validation ([#197](https://github.com/manwithacat/dazzle/issues/197))
- Business priority and revenue-criticality signals on DSL constructs ([#196](https://github.com/manwithacat/dazzle/issues/196))
- Persona-scoped navigation audit to detect admin content shown to all users ([#195](https://github.com/manwithacat/dazzle/issues/195))
- Project-level custom CSS override via `static/css/custom.css` ([#187](https://github.com/manwithacat/dazzle/issues/187))
- CSS computed style inspection for agent-driven layout diagnosis ([#186](https://github.com/manwithacat/dazzle/issues/186))
- Layout geometry extraction via Playwright bounding boxes in composition ([#183](https://github.com/manwithacat/dazzle/issues/183))
- Composition analysis MCP tool with dual-layer DOM audit and visual evaluation ([#180](https://github.com/manwithacat/dazzle/issues/180))
- Pulse tool with story wall, readiness radar, and decision queue for founders ([#178](https://github.com/manwithacat/dazzle/issues/178))
- Summary mode for pipeline and fidelity output for LLM-friendly compact results ([#173](https://github.com/manwithacat/dazzle/issues/173))
- Declarative `themespec.yaml` for deterministic design generation ([#167](https://github.com/manwithacat/dazzle/issues/167))
- Batch MCP operations to reduce round-trips for agent loops ([#165](https://github.com/manwithacat/dazzle/issues/165))
- Responsive testing strategy with structural, viewport, and visual tiers ([#153](https://github.com/manwithacat/dazzle/issues/153))
- MCP entrypoint for agent-driven smoke test authoring and execution ([#148](https://github.com/manwithacat/dazzle/issues/148))
- HX-Trigger response headers for server→client event coordination ([#142](https://github.com/manwithacat/dazzle/issues/142))
- Auto-generated curl smoke test suite from DSL specification ([#138](https://github.com/manwithacat/dazzle/issues/138))
- Per-persona authenticated sessions for testing and ACL verification ([#137](https://github.com/manwithacat/dazzle/issues/137))

### Changed
- Expanded LSP hover and go-to-definition to all DSL construct types ([#235](https://github.com/manwithacat/dazzle/issues/235))
- Context-aware completion suggestions in LSP ([#234](https://github.com/manwithacat/dazzle/issues/234))
- Missing construct keywords added to TextMate grammar for syntax highlighting ([#236](https://github.com/manwithacat/dazzle/issues/236))
- Parser diagnostics published to editor for real-time error feedback ([#232](https://github.com/manwithacat/dazzle/issues/232))
- Auto-eager-load ref fields on list surfaces to prevent N+1 queries ([#231](https://github.com/manwithacat/dazzle/issues/231))
- View projections on list surfaces to reduce column fetch ([#230](https://github.com/manwithacat/dazzle/issues/230))
- Per-test progress and result annotations in Workshop for `dsl_test.run_all` ([#227](https://github.com/manwithacat/dazzle/issues/227))
- CLI command activity written to shared store for Workshop visibility ([#225](https://github.com/manwithacat/dazzle/issues/225))
- UK government identifier detection (NINO, UTR) added to compliance scanner ([#221](https://github.com/manwithacat/dazzle/issues/221))
- Discovery agent now uses MCP sampling instead of direct Anthropic API calls ([#220](https://github.com/manwithacat/dazzle/issues/220))
- Progress feedback, token visibility, and streaming added to MCP tools ([#201](https://github.com/manwithacat/dazzle/issues/201))
- Explicit password option in `create-user` and `reset-password` CLI commands ([#199](https://github.com/manwithacat/dazzle/issues/199))
- Production-grade Docker setup with Postgres, Redis, and Celery ([#198](https://github.com/manwithacat/dazzle/issues/198))
- Orphan experience detection for experiences with no workspace entry point ([#194](https://github.com/manwithacat/dazzle/issues/194))
- Composition audit step added to pipeline for visual hierarchy validation ([#192](https://github.com/manwithacat/dazzle/issues/192))
- Pipeline semantics step returns counts and summaries instead of full schemas ([#190](https://github.com/manwithacat/dazzle/issues/190))
- Perfect-score surfaces omitted from fidelity output to reduce pipeline size ([#189](https://github.com/manwithacat/dazzle/issues/189))
- Hero-balance severity escalated when media is declared but not side-by-side ([#188](https://github.com/manwithacat/dazzle/issues/188))
- Sitespec media declarations cross-checked against rendered layout in audit ([#185](https://github.com/manwithacat/dazzle/issues/185))
- Money field widget with major/minor unit conversion in forms ([#172](https://github.com/manwithacat/dazzle/issues/172))
- Runtime standardised on PostgreSQL-only backend; SQLite removed ([#158](https://github.com/manwithacat/dazzle/issues/158))
- Migrated from psycopg2 + asyncpg to unified psycopg v3 driver ([#155](https://github.com/manwithacat/dazzle/issues/155))
- PostgreSQL-first runtime with SQLite-isms eliminated ([#154](https://github.com/manwithacat/dazzle/issues/154))
- Postgres constraint violations return 422 with helpful messages ([#146](https://github.com/manwithacat/dazzle/issues/146))
- htmx upgraded from 2.0.3 to 2.0.8 ([#144](https://github.com/manwithacat/dazzle/issues/144))
- Idiomorph swap for table performance to preserve DOM state ([#143](https://github.com/manwithacat/dazzle/issues/143))
- Alpine.js replaced with lightweight `dz.js` micro-runtime (~3 KB) ([#141](https://github.com/manwithacat/dazzle/issues/141))

### Deprecated
- Dazzle Bar dev toolbar feature removed ([#164](https://github.com/manwithacat/dazzle/issues/164))

### Fixed
- Recursive FK dependency chains in DSL test generator ([#237](https://github.com/manwithacat/dazzle/issues/237))
- Document symbol positions so outline navigation works correctly ([#233](https://github.com/manwithacat/dazzle/issues/233))
- Auth propagation to TestRunner and test generator quality issues ([#229](https://github.com/manwithacat/dazzle/issues/229))
- Authentication before CRUD tests when using `--base-url` ([#228](https://github.com/manwithacat/dazzle/issues/228))
- JSONL file writer connected to SQLite activity store for Workshop visibility ([#223](https://github.com/manwithacat/dazzle/issues/223))
- v0.25.0 constructs silently dropped by pre-v0.25.0 dispatchers ([#222](https://github.com/manwithacat/dazzle/issues/222))
- DSL with reserved keyword conflicts now rejected during MCP validation ([#219](https://github.com/manwithacat/dazzle/issues/219))
- Remaining ForwardRef modules causing `/openapi.json` 500 ([#218](https://github.com/manwithacat/dazzle/issues/218))
- Pydantic ForwardRef errors causing `/openapi.json` 500 ([#217](https://github.com/manwithacat/dazzle/issues/217))
- `asyncio.run()` conflict in `create_sessions` under MCP event loop ([#216](https://github.com/manwithacat/dazzle/issues/216))
- `InFailedSqlTransaction` recovery in publisher loop instead of cascading ([#215](https://github.com/manwithacat/dazzle/issues/215))
- Pluralization in surface converter to match test infrastructure ([#214](https://github.com/manwithacat/dazzle/issues/214))
- `from __future__ import annotations` removed from remaining route modules ([#213](https://github.com/manwithacat/dazzle/issues/213))
- `/openapi.json` returning 500 Internal Server Error ([#211](https://github.com/manwithacat/dazzle/issues/211))
- `asyncio.run()` conflict in `dsl_test` `create_sessions` ([#210](https://github.com/manwithacat/dazzle/issues/210))
- Workspace routes returning 404 despite nav links pointing to them ([#209](https://github.com/manwithacat/dazzle/issues/209))
- Entity route names using proper English pluralization ([#208](https://github.com/manwithacat/dazzle/issues/208))
- `dsl_test` route pattern matching actual runtime API routes ([#207](https://github.com/manwithacat/dazzle/issues/207))
- Partial stories always appear in pipeline coverage regardless of pagination ([#193](https://github.com/manwithacat/dazzle/issues/193))
- False positives in compliance signal detection for non-PII fields ([#191](https://github.com/manwithacat/dazzle/issues/191))
- LLM vision path not executing in `composition(analyze)` ([#184](https://github.com/manwithacat/dazzle/issues/184))
- Sitespec rendering for `split_content` source.path and pricing layout ([#182](https://github.com/manwithacat/dazzle/issues/182))
- Playwright async API in composition capture to fix asyncio conflict ([#181](https://github.com/manwithacat/dazzle/issues/181))
- Hero section media image not rendering despite correct sitespec ([#179](https://github.com/manwithacat/dazzle/issues/179))
- Sitespec rendering for `card_grid`, `split_content`, `trust_bar`, and more ([#177](https://github.com/manwithacat/dazzle/issues/177))
- `role()` conditions evaluated in policy simulate instead of always allowing ([#176](https://github.com/manwithacat/dazzle/issues/176))
- False HIGH severity gaps suppressed for system entities lacking create/edit ([#175](https://github.com/manwithacat/dazzle/issues/175))
- Standalone entity routes recognised in sitespec validator ([#174](https://github.com/manwithacat/dazzle/issues/174))
- Money field expansion accounted for in fidelity checker to prevent false positives ([#171](https://github.com/manwithacat/dazzle/issues/171))
- CSS/HTML class name mismatches breaking site styling ([#166](https://github.com/manwithacat/dazzle/issues/166))
- SQLAlchemy included as base dependency to prevent fresh deploy crashes ([#163](https://github.com/manwithacat/dazzle/issues/163))
- Tables topologically sorted by FK dependencies during PostgreSQL migration ([#162](https://github.com/manwithacat/dazzle/issues/162))
- `DATABASE_URL` honoured in `dazzle migrate` CLI command ([#161](https://github.com/manwithacat/dazzle/issues/161))
- Extra `dazzle` argument removed from subprocess command in `dazzle check` ([#160](https://github.com/manwithacat/dazzle/issues/160))
- Entity list routes 500 from psycopg v3 `dict_row` incompatibility ([#157](https://github.com/manwithacat/dazzle/issues/157))
- PostgresBus table creation crash from `.format()` vs JSONB DEFAULT conflict ([#156](https://github.com/manwithacat/dazzle/issues/156))
- SQL placeholder for FK pre-validation on PostgreSQL ([#152](https://github.com/manwithacat/dazzle/issues/152))
- psycopg2 `IntegrityError` subclasses handled in repository exception check ([#151](https://github.com/manwithacat/dazzle/issues/151))
- DaisyUI drawer hamburger toggle not appearing on tablet viewports ([#150](https://github.com/manwithacat/dazzle/issues/150))
- Project-level static images served after unified server change ([#149](https://github.com/manwithacat/dazzle/issues/149))
- `dz.js` and `dz.css` returning 404 after Alpine.js migration ([#147](https://github.com/manwithacat/dazzle/issues/147))
- Authentication enforced on workspace dashboard routes ([#145](https://github.com/manwithacat/dazzle/issues/145))
- Enum validation error handler crash from non-serializable `ValueError` ([#140](https://github.com/manwithacat/dazzle/issues/140))
- Orphaned column removed after money field expansion to fix NOT NULL violation ([#139](https://github.com/manwithacat/dazzle/issues/139))
- Entity route names using proper English pluralization ([#136](https://github.com/manwithacat/dazzle/issues/136))
- HTML sanitized in string/text fields to prevent stored XSS ([#135](https://github.com/manwithacat/dazzle/issues/135))
- Unique constraint violations return 422 instead of 500 ([#134](https://github.com/manwithacat/dazzle/issues/134))
- Foreign key constraint violations return 422 instead of 500 ([#133](https://github.com/manwithacat/dazzle/issues/133))
- `auto_add` and `auto_update` timestamp fields populated on insert and update ([#132](https://github.com/manwithacat/dazzle/issues/132))
- `money(GBP)` type expanded to `_minor`/`_currency` column pair instead of string ([#131](https://github.com/manwithacat/dazzle/issues/131))
- Enum field values validated against DSL-defined options on CRUD endpoints ([#130](https://github.com/manwithacat/dazzle/issues/130))

## [0.16.0] - 2025-12-16

### Added
- **MkDocs Material Documentation Site** ([manwithacat.github.io/dazzle](https://manwithacat.github.io/dazzle))
  - Complete DSL reference with 10 sections (modules, entities, surfaces, workspaces, services, integrations, messaging, ux, scenarios, experiences)
  - Architecture guides (overview, event semantics, DSL to AppSpec, MCP server)
  - 5 example walkthroughs (simple_task, contact_manager, support_tickets, ops_dashboard, fieldtest_hub)
  - Getting started guides (installation, quickstart, first app)
  - Contributing guides (dev setup, testing, adding features)
  - Auto-generated API reference from source code analysis (315 files)
  - GitHub Pages deployment via GitHub Actions

- **Event-First Architecture** (Issue #25) - Events as invisible substrate
  - EventBus interface (Kafka-shaped) with DevBrokerSQLite (zero-Docker development)
  - Transactional outbox for at-least-once delivery (no dual writes)
  - Idempotent inbox for consumer deduplication
  - DSL extensions: `event_model`, `topic`, `event`, `publish when`, `subscribe`, `project`
  - Replay capability for projection rebuild
  - Developer Observability Pack:
    - CLI commands: `dazzle events status|tail|replay`, `dazzle dlq list|replay|clear`, `dazzle outbox status|drain`
    - Event Explorer API at `/_dnr/events/`
    - AsyncAPI 3.0 generation from AppSpec
  - Email as events: raw stream, normalized stream, outbound events
  - Data products module: field classification, curated topics, policy transforms
  - 12 Stability Rules (Constitution) for event-first systems
  - KafkaBus adapter for production
  - Multi-tenancy strategies and topology drift detection

- **SiteSpec: Public Site Shell** (Issue #24)
  - YAML-based `sitespec.yaml` for public pages (home, about, pricing, terms, privacy)
  - 10 section types: hero, features, feature_grid, cta, faq, testimonials, stats, steps, logo_cloud, pricing
  - Template variable substitution (`{{product_name}}`, `{{year}}`, etc.)
  - Legal page templates (terms.md, privacy.md with full boilerplate)
  - Generated auth pages (login, signup) with working forms
  - Theme presets (`saas-default`, `minimal`)
  - MCP tools: `get_sitespec`, `validate_sitespec`, `scaffold_site`

- **Performance & Reliability Analysis (PRA)**
  - Load generator with configurable event profiles
  - Throughput and latency metrics collection
  - CI integration with stress test scenarios
  - Pre-commit hook for PRA unit tests

- **HLESS (High-Level Event Semantics Specification)**
  - RecordKind enum: INTENT, FACT, OBSERVATION, DERIVATION
  - StreamSpec model with IDL fields
  - HLESSValidator enforcing semantic rules
  - Cross-stream reference validation

- **Playwright E2E Tests**
  - Smoke tests for P0 examples (simple_task, contact_manager)
  - Screenshot tests for fieldtest_hub (16 screenshots)
  - Semantic DOM contract validation

- **Messaging Channels** (Issue #20) - Complete email workflow
  - DSL parser for `message`, `channel`, `asset`, `document`, `template`
  - IR types: MessageSpec, ChannelSpec, SendOperationSpec, ThrottleSpec
  - Outbox pattern: transactional persistence, status tracking, retry logic, dead letter handling
  - Background dispatcher: `ChannelManager.start_processor()` processes outbox every 5s
  - Email adapters: MailpitAdapter (SMTP), FileEmailAdapter (disk fallback)
  - Provider detection framework for email, queue, stream providers
  - Template engine with variable substitution and conditionals
  - Server integration: API routes at `/_dnr/channels/*`
  - MCP tools: `list_channels`, `get_channel_status`, `list_messages`, `get_outbox_status`
  - 95 unit tests

### Changed
- Examples reorganized: removed obsolete examples, added support_tickets and fieldtest_hub
- Consolidated `tools/` into `scripts/` directory
- API reference generator now excludes `__init__.py` files and detects events/invariants

---

## [0.15.0] - 2025-12-15

### Added
- **Interactive CLI Commands**: New user-friendly interactive modes
  - `dazzle init`: Interactive project wizard with guided setup
  - `dazzle doctor`: Environment diagnostics with automatic fixes
  - `dazzle explore`: Interactive DSL explorer with syntax examples
  - `dazzle kb`: Knowledgebase browser for DSL concepts and patterns

### Changed
- CLI version bumped to 0.15.0

---

## [0.14.0] - 2025-12-14

### Added
- **MCP Commands Restored**: Full MCP server functionality in Bun CLI
  - `dazzle mcp`: Run MCP server for Claude Code integration
  - `dazzle mcp-setup`: Register MCP server with Claude Code
  - `dazzle mcp-check`: Check MCP server status
- **Deterministic Port Allocation**: DNR serve now uses deterministic ports based on project path
- **Semantic E2E Attributes**: Added `data-dazzle-*` attributes for E2E testability

---

## [0.9.3] - 2025-12-11

### Added
- **Documentation Overhaul**
  - Complete DSL reference guide in `docs/reference/` (11 files)
  - Comprehensive README with DSL constructs overview
  - Renamed docs/v0.7 to docs/v0.9

---

## [0.8.0] - 2025-12-09

### Added
- **Bun CLI Framework**: Complete CLI rewrite for 50x faster startup
  - Bun-compiled binary (57MB, single file)
  - 20ms startup vs 1000ms+ Python CLI
  - JSON-first output for LLM integration
  - `__agent_hint` fields in errors for AI remediation

### Changed
- **Command Mappings**:
  | Old Command | New Command |
  |-------------|-------------|
  | `dazzle init` | `dazzle new` |
  | `dazzle dnr serve` | `dazzle dev` |
  | `dazzle validate` | `dazzle check` |
  | `dazzle inspect` | `dazzle show` |
  | `dazzle dnr test` | `dazzle test` |
  | `dazzle eject run` | `dazzle eject` |
  | `dazzle dnr migrate` | `dazzle db` |

### Distribution
- GitHub Releases with 4 platform binaries (darwin-arm64, darwin-x64, linux-arm64, linux-x64)
- Homebrew tap updated (`brew install manwithacat/tap/dazzle`)
- VS Code extension v0.8.0 with new command mappings

---

## [0.7.2] - 2025-12-10

### Added
- **Ejection Toolchain**: Generate standalone code from DNR applications
  - Ejection config parser for `dazzle.toml` `[ejection]` section
  - Adapter registry with pluggable generators
  - FastAPI backend adapter (models, schemas, routes, guards, validators, access)
  - React frontend adapter (TypeScript types, Zod schemas, TanStack Query hooks)
  - Testing adapters (Schemathesis contract tests, Pytest unit tests)
  - CI adapters (GitHub Actions, GitLab CI)
  - OpenAPI 3.1 generation from AppSpec
  - Post-ejection verification (no Dazzle imports, no template markers)
  - `.ejection.json` metadata file for audit trail
  - CLI: `eject run`, `eject status`, `eject adapters`, `eject openapi`, `eject verify`
  - 35 unit tests

---

## [0.7.1] - 2025-12-10

### Added
- **LLM Cognition & DSL Generation Enhancement**
  - Intent declarations on entities (`intent: "..."`)
  - Domain and patterns semantic tags (`domain: billing`, `patterns: lifecycle, audit`)
  - Archetypes with extends inheritance (`archetype Timestamped`, `extends: Timestamped`)
  - Example data blocks (`examples: [{...}]`)
  - Invariant messages and codes (`message: "...", code: ERROR_CODE`)
  - Relationship semantics (`has_many`, `has_one`, `embeds`, `belongs_to`)
  - Delete behaviors (`cascade`, `restrict`, `nullify`, `readonly`)
  - Updated MCP semantic index with all v0.7.1 concepts
  - 5 example projects updated

---

## [0.7.0] - 2025-12-10

### Added
- **Business Logic Extraction**: DSL as compression boundary for semantic reasoning
  - State machines for entity lifecycle (`transitions:` block)
  - Computed fields for derived values (`computed` keyword)
  - Invariants for data integrity (`invariant:` rules)
  - Access rules for visibility/permissions
  - All 5 example projects upgraded with v0.7 features
  - 756 tests passing

---

## [0.6.0] - 2025-12-09

### Added
- **GraphQL BFF Layer**: API aggregation and external service facade
  - GraphQLContext: Multi-tenant context with role-based access control
  - SchemaGenerator: Generate Strawberry types from BackendSpec
  - ResolverGenerator: Generate CRUD resolvers with tenant isolation
  - FastAPI Integration: `mount_graphql()`, `create_graphql_app()`
  - CLI: `--graphql` flag for `dazzle dnr serve`
  - `dazzle dnr inspect --schema` command
  - External API Adapters with retry logic and rate limiting
  - Error normalization with unified error model
  - 53 unit tests for adapter interface
  - 7 GraphQL integration tests

---

## [0.5.0] - 2025-12-02

### Added
- **Anti-Turing Extensibility Model**
  - Domain Service DSL: `service` with `kind`, `input`, `output`, `guarantees`, `stub`
  - Service Kinds: domain_logic, validation, integration, workflow
  - ServiceLoader: Runtime discovery of Python stubs
  - Stub Generation: `dazzle stubs generate` command
  - EBNF Grammar: Restricted to aggregate functions only
  - Documentation: `docs/EXTENSIBILITY.md`
  - 31 new tests (14 domain service + 17 service loader)

- **Inline Access Rules**
  - New `access:` block syntax in entity definitions
  - `read:` rule for visibility/view access control
  - `write:` rule for create/update/delete permissions
  - 8 unit tests

- **Component Roles** (UISpec)
  - `ComponentRole` enum: PRESENTATIONAL, CONTAINER
  - Auto-inference based on state and actions
  - 13 unit tests

- **Action Purity** (UISpec)
  - `ActionPurity` enum: PURE, IMPURE
  - Auto-inference based on effects
  - 14 unit tests

### Status
- 601 tests passing

---

## [0.4.0] - 2025-12-02

### Added
- **DNR Production Ready**
  - `dazzle dnr test` command for API contract testing
  - `--benchmark` option for performance testing
  - `--a11y` option for WCAG accessibility testing
  - `dazzle dnr build` for production bundles
  - Multi-stage Dockerfile generation
  - docker-compose.yml for local deployment
  - `dazzle dnr migrate` for database migrations
  - Kubernetes health probes (`/_dnr/live`, `/_dnr/ready`)

---

## [0.3.3] - 2025-12

### Added
- **DNR Developer Experience**
  - DSL file watching with instant reload (`dazzle dnr serve --watch`)
  - Browser dev tools panel with state/action inspection
  - State inspector with real-time updates
  - Action log with state diff visualization
  - `dazzle dnr inspect` command for spec inspection
  - `dazzle dnr inspect --live` for running server inspection
  - `/_dnr/*` debug endpoints (health, stats, entity details)

---

## [0.3.2] - 2025-12

### Added
- **Semantic E2E Testing Framework** (8 phases complete)
  - DOM Contract: `data-dazzle-*` attributes for semantic locators
  - TestSpec IR: FlowSpec, FlowStep, FlowAssertion, FixtureSpec, E2ETestSpec
  - Auto-Generate E2ETestSpec from AppSpec (CRUD, validation, navigation flows)
  - Playwright Harness: semantic locators, flow execution, domain assertions
  - Test Endpoints: `/__test__/seed`, `/__test__/reset`, `/__test__/snapshot`
  - DSL Extensions: `flow` block syntax with parser support
  - CLI: `dazzle test generate`, `dazzle test run`, `dazzle test list`
  - Usability & Accessibility: axe-core integration, WCAG mapping
  - 61 new tests

---

## [0.3.1] - 2025-12

### Fixed
- **Critical Bug Fixes**
  - ES module export block conversion failure in `js_loader.py`
  - HTML script tag malformation in `js_generator.py`

### Added
- **E2E Testing**
  - E2E tests for DNR serve in `tests/e2e/test_dnr_serve.py`
  - Matrix-based E2E testing for example projects in CI
  - P0 examples (simple_task, contact_manager) block PRs on failure

- **MCP Server Improvements**
  - Getting-started workflow guidance
  - Common DSL patterns documentation
  - Semantic index v0.5.0 with extensibility concepts

---

## [0.3.0] - 2025-11

### Added
- **Dazzle Native Runtime (DNR)**: Major pivot to runtime-first approach

  **DNR Backend**:
  - SQLite persistence with auto-migration
  - FastAPI server with auto-generated CRUD endpoints
  - Session-based auth, PBKDF2 password hashing
  - Row-level security, owner/tenant-based access control
  - File uploads: Local and S3 storage, image processing, thumbnails
  - Rich text: Markdown rendering, HTML sanitization
  - Relationships: Foreign keys, nested data fetching
  - Full-text search: SQLite FTS5 integration
  - Real-time: WebSocket support, presence indicators, optimistic updates

  **DNR Frontend**:
  - Signals-based UI: Reactive JavaScript without virtual DOM
  - Combined server: Backend + Frontend with API proxy
  - Hot reload: SSE-based live updates
  - Vite integration: Production builds

  **UI Semantic Layout Engine**:
  - 5 Archetypes: FOCUS_METRIC, SCANNER_TABLE, DUAL_PANE_FLOW, MONITOR_WALL, COMMAND_CENTER
  - Attention signals with priority weights
  - Engine variants: Classic, Dense, Comfortable
  - `dazzle layout-plan` command
  - Persona-aware layout adjustments

### Changed
- Legacy code generation stacks deprecated in favor of DNR

---

## [0.2.0] - 2025-11

### Added
- **UX Semantic Layer**: Fundamental DSL language enhancement
  - Personas: Role-based surface/workspace variants with scope filtering
  - Workspaces: Composed dashboards with multiple data regions
  - Attention Signals: Data-driven alerts (critical, warning, notice, info)
  - Information Needs: `show`, `sort`, `filter`, `search`, `empty` directives
  - Purpose Statements: Semantic intent documentation
  - MCP Enhancements: Semantic concept lookup, example search

---

## [0.1.1] - 2025-11-23

### Fixed
- **express_micro stack**:
  - Graceful fallback for AdminJS on incompatible Node.js versions (v25+)
  - Node.js version constraints to package.json (`>=18.0.0 <25.0.0`)
  - Missing `title` variable in route handlers
  - Admin interface mounting in server.js
  - Error handling with contextual logging

### Added
- Environment variable support with dotenv
- Generated `.env.example` file

---

## [0.1.0] - 2025-11-22

### Added
- **Initial Release**
  - Complete DSL parser (800+ lines)
  - Full Internal Representation (900+ lines, Pydantic models)
  - Module system with dependency resolution
  - 6 code generation stacks (Django, Express, OpenAPI, Docker, Terraform)
  - LLM integration (spec analysis, DSL generation)
  - LSP server with VS Code extension
  - Homebrew distribution
  - MCP server integration

---

## Deprecated Features

The following are deprecated as of v0.3.0 in favor of DNR:

| Stack | Status | Recommendation |
|-------|--------|----------------|
| `django_micro` | Deprecated | Use DNR |
| `django_micro_modular` | Deprecated | Use DNR |
| `django_api` | Deprecated | Use DNR |
| `express_micro` | Deprecated | Use DNR |
| `nextjs_onebox` | Deprecated | Use DNR |
| `nextjs_semantic` | Deprecated | Use DNR |
| `openapi` | Available | For API spec export only |
| `terraform` | Available | For infrastructure |
| `docker` | Available | For DNR deployment |
