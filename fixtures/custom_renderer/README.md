# Custom renderer worked example

Minimal end-to-end example of registering a project-side renderer.
Worth reading start-to-end if you're an agent or human about to write
your first custom renderer — the example covers both halves of the
extension contract (link-time allowlist + runtime registration).

Closes the discoverability gap surfaced in
[#1117](https://github.com/manwithacat/dazzle/issues/1117), and
demonstrates the manifest-aware validation path added in
[#1116](https://github.com/manwithacat/dazzle/issues/1116).

## What's here

- `dazzle.toml` — declares `[renderers] extra = ["word_cloud",
  "feedback_detail"]` so the link-time validator accepts both names on
  surface DSL.
- `dsl/app.dsl` — one entity (`Feedback`), three surfaces. The
  `tag_cloud` surface uses `mode: custom` + `render: word_cloud`; the
  `feedback_detail` surface uses `mode: view` + `render: feedback_detail`
  (a per-entity detail viewer, #1297); the `feedback_list` surface uses
  the default fragment renderer.
- `app/render/word_cloud.py` — ~120 lines: a `WordCloudRenderer` class
  implementing the protocol (`render(surface, ctx) -> str`) plus a
  `register_with_app(services)` helper for the runtime registration
  step.
- `app/render/feedback_detail.py` — a `FeedbackDetailRenderer` that
  **delegates** to the framework's generic detail rendering and wraps it
  with bespoke chrome (the #1297 per-entity detail-viewer pattern).
- `app/render/__init__.py` — `register_all(services)`, registering both
  renderers in one call.

## The two halves of the extension contract

Registering a custom renderer takes **two** steps. The framework
validates them independently, at different times, so missing either
fails differently.

### 1. Declare the name (link-time)

In `dazzle.toml` — list every project-side renderer name (this example
ships two):

```toml
[renderers]
extra = ["word_cloud", "feedback_detail"]
```

This adds the names to the allowlist consulted by
`dazzle.core.renderer_registry.known_renderer_names(manifest)`. Every
code path that calls `build_appspec(known_renderers=…)` reads this:
`dazzle validate`, `dazzle serve`, `dazzle db upgrade` (via alembic),
the LSP, hot-reload, deploy. Without this declaration, every CLI that
runs the linker rejects the DSL with a `RenderValidationError` that
quotes both halves of the recipe (see `linker._unknown_renderer_message`).

### 2. Register the handler (runtime)

In application code (here: `register_all` in `app/render/__init__.py`,
which composes the per-renderer `register_with_app` helpers):

```python
def register_all(services: RuntimeServices) -> None:
    services.renderer_registry.register(name="word_cloud", handler=WordCloudRenderer())
    services.renderer_registry.register(name="feedback_detail", handler=FeedbackDetailRenderer())
```

`services.renderer_registry` is the same registry inspected by
`dispatch_render` at request time. If step 1 passes but step 2 is
missing, `dispatch.dispatch_render` raises `FragmentError` with the
runtime-side half of the recipe — except for non-custom modes
(`mode: view` / `mode: list`), which **fall back to the generic
built-in rendering** instead of erroring, so a half-wired detail viewer
degrades gracefully rather than 500ing.

The two error messages are coordinated — an agent encountering either
sees the same shape ("here's the manifest key", "here's the
registration call", "here's the worked example").

## Wiring `register_with_app`

`dazzle serve` builds `RuntimeServices` inside the app factory; the
factory calls `register_default_renderers(services)` early in boot.
Project-side registrations attach **after** that — pick whichever
attachment point matches your deploy shape:

- **FastAPI startup event** (most common):

  ```python
  from app.render import register_all

  @app.on_event("startup")
  async def _wire_custom_renderers() -> None:
      register_all(app.state.services)
  ```

- **Custom app factory** (if you build the app yourself):

  ```python
  app, services = create_app(project_root)
  register_all(services)
  ```

## Per-entity detail viewers (#1297) — replacing Jinja overrides

Before ADR-0023 (which dropped Jinja2, #1042), projects routed specific
entities to bespoke detail viewers by overriding the framework template
`components/detail_view.html` and branching on `entity_name`:

```jinja
{# dazzle:override components/detail_view.html #}   {# ← removed, no longer consulted #}
{% if detail.entity_name == "Manuscript" %}
  {% include "components/manuscript_viewer.html" %}
{% else %}
  {% include "dz://components/detail_view.html" %}   {# generic fall-through #}
{% endif %}
```

That mechanism is **gone** — there is no Jinja resolver to consult the
override. The modern, supported shape is **per-surface**, not one
god-file branching on `entity_name`:

1. Declare a custom renderer on the entity's **VIEW** surface:

   ```dsl
   surface manuscript_detail "Manuscript":
     uses entity Manuscript
     mode: view
     render: manuscript_viewer       # ← per-entity detail viewer
     section main:
       field title "Title"
   ```

2. Add the name to `[renderers] extra` in `dazzle.toml` and register a
   handler (as above).

3. In the handler, **delegate** to the framework's generic detail
   rendering via `ctx["detail_context"]` — the direct analogue of the
   old `{% include "dz://components/detail_view.html" %}` fall-through:

   ```python
   from dazzle.page.runtime import render_detail_view

   class ManuscriptViewer:
       def render(self, surface, ctx) -> str:
           detail = ctx["detail_context"]          # the original DetailContext
           generic_body = render_detail_view(detail)   # standard field layout
           custom_panel = self._render_ao_grid(detail.item)
           return f'<section>{custom_panel}{generic_body}</section>'
   ```

`render_detail_view(ctx["detail_context"])` is **lazy** — the generic
HTML is only produced if you call it, so a viewer that *fully* replaces
the standard layout simply never calls it and pays nothing.

See `app/render/feedback_detail.py` for a runnable version of exactly
this pattern.

> **Scope note (#1297):** VIEW-surface detail pages reached via
> `/app/<entity>/{id}` (the workspace detail route) honour `render:`
> today. Detail bodies rendered *inside an `experience` step* still use
> the generic inline renderer regardless of `render:` — wiring that path
> through the registry is tracked as a non-blocking follow-up.

## Things this example deliberately avoids

- **Auth.** The framework auth subsystem is orthogonal to renderer
  extension. `simple_task` / `contact_manager` cover the auth path.
- **DB integration.** A production word-cloud renderer would query
  Feedback rows from the repository — this example reads from
  `ctx.get("rows", [])` so it stays focused on the protocol shape.
  See `src/dazzle/http/runtime/repository.py` for the repository
  helpers a real renderer would use.
- **Tests.** Renderer-level tests look like
  `tests/unit/test_*_renderer.py` in the framework tree —
  parametrise over fixture surfaces, assert the rendered HTML
  contains the expected structure.

## Common gotchas (and what triggers each error)

| What you forgot | Error you'll see | Where it fires |
| --- | --- | --- |
| `[renderers] extra` declaration | `RenderValidationError: surface 'tag_cloud' declares render: 'word_cloud', but that name isn't in the known-renderers set` | Link time (`dazzle validate`, app boot) |
| Runtime `register(...)` call | `FragmentError: surface 'tag_cloud': renderer 'word_cloud' is declared in the DSL but no runtime handler is registered for that name` | Request time (first hit on the surface) |
| Mistyped name (`wordcloud` vs `word_cloud`) | Same as above — names must match across DSL, manifest, and registration | Link time (loudest) |

Both errors include the full registration recipe in the message — so
even if you skip this README, the framework will hand-feed you the
recipe at the moment you hit the wall.

## Further reading

- `src/dazzle/core/renderer_registry.py` — the `known_renderer_names`
  function and the `_DEFAULT_RENDERERS` constant.
- `src/dazzle/render/dispatch.py` — `dispatch_render`, the registry
  lookup that picks your handler at request time.
- `src/dazzle/http/runtime/renderers/fragment.py` — the framework's
  own fragment renderer. Read this for the canonical example of how
  an adapter wraps a richer underlying renderer behind the
  `(surface, ctx) -> str` protocol.
