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

- `dazzle.toml` — declares `[renderers] extra = ["word_cloud"]` so the
  link-time validator accepts the name on surface DSL.
- `dsl/app.dsl` — one entity (`Feedback`), two surfaces. The
  `tag_cloud` surface uses `mode: custom` + `render: word_cloud` to
  dispatch through our handler; the `feedback_list` surface uses the
  default fragment renderer.
- `app/render/word_cloud.py` — ~120 lines: a `WordCloudRenderer` class
  implementing the protocol (`render(surface, ctx) -> str`) plus a
  `register_with_app(services)` helper for the runtime registration
  step.

## The two halves of the extension contract

Registering a custom renderer takes **two** steps. The framework
validates them independently, at different times, so missing either
fails differently.

### 1. Declare the name (link-time)

In `dazzle.toml`:

```toml
[renderers]
extra = ["word_cloud"]
```

This adds `"word_cloud"` to the allowlist consulted by
`dazzle.core.renderer_registry.known_renderer_names(manifest)`. Every
code path that calls `build_appspec(known_renderers=…)` reads this:
`dazzle validate`, `dazzle serve`, `dazzle db upgrade` (via alembic),
the LSP, hot-reload, deploy. Without this declaration, every CLI that
runs the linker rejects the DSL with a `RenderValidationError` that
quotes both halves of the recipe (see `linker._unknown_renderer_message`).

### 2. Register the handler (runtime)

In application code (here: `register_with_app` in
`app/render/word_cloud.py`):

```python
def register_with_app(services: RuntimeServices) -> None:
    services.renderer_registry.register(
        name="word_cloud",
        handler=WordCloudRenderer(),
    )
```

`services.renderer_registry` is the same registry inspected by
`dispatch_render` at request time. If step 1 passes but step 2 is
missing, `dispatch.dispatch_render` raises `FragmentError` with the
runtime-side half of the recipe.

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
  from app.render.word_cloud import register_with_app

  @app.on_event("startup")
  async def _wire_custom_renderers() -> None:
      register_with_app(app.state.services)
  ```

- **Custom app factory** (if you build the app yourself):

  ```python
  app, services = create_app(project_root)
  register_with_app(services)
  ```

## Things this example deliberately avoids

- **Auth.** The framework auth subsystem is orthogonal to renderer
  extension. `simple_task` / `contact_manager` cover the auth path.
- **DB integration.** A production word-cloud renderer would query
  Feedback rows from the repository — this example reads from
  `ctx.get("rows", [])` so it stays focused on the protocol shape.
  See `src/dazzle/back/runtime/repository.py` for the repository
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
- `src/dazzle/back/runtime/renderers/fragment.py` — the framework's
  own fragment renderer. Read this for the canonical example of how
  an adapter wraps a richer underlying renderer behind the
  `(surface, ctx) -> str` protocol.
