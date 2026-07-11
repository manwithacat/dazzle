# Project Layout

Every Dazzle project starts with a DSL directory and a `dazzle.toml`
manifest. As the project grows, custom Python code needs a home. This
reference describes the recommended layout.

### Epistemic stems (`stems/`)

Apps should keep a short **`stems/`** directory: compressed domain judgement
(INDEX + small stem files). Framework stems live in the monorepo root
`stems/`; HaTchi-MaXchi has `packages/hatchi-maxchi/stems/`. See monorepo
`stems/README.md` and `AGENTS.md` › Epistemic layout. SPEC/DSL are
*expressions* of stems, not replacements for them.

## Minimal Project

```
my-app/
  dazzle.toml              # Project manifest
  stems/                   # Domain stems (even for small apps)
    README.md
    INDEX.md
  dsl/
    app.dsl                # DSL entry point
    entities.dsl           # Entity definitions
    surfaces.dsl           # UI surfaces
```

This is sufficient for apps that are fully DSL-driven with no custom code.
Add stem files under `stems/` as domain judgement solidifies.

## Full Project Layout

When a project has custom Python code beyond the DSL:

```
my-app/
  dazzle.toml              # Project manifest
  stems/                   # Domain epistemic stems (INDEX + short files)
    README.md
    INDEX.md
  dsl/                     # DSL source files
    app.dsl
    entities.dsl
    surfaces.dsl
    stories.dsl
  routes/                  # Custom FastAPI route overrides
  static/                  # Project static assets (shadows framework assets)
  app/                     # Custom application code
    __init__.py
    db/                    # Database operations
      __init__.py
      snapshots.py         # DB snapshot/restore
    sync/                  # External data integration
      __init__.py
      wonde.py             # Example: Wonde API sync
    render/                # Document generation (PDF, reports)
      __init__.py
    qa/                    # Quality assurance tooling
      __init__.py
    demo/                  # Demo data generation
      __init__.py
      constants.py         # Shared demo constants
      generate.py          # Main demo data generator
  scripts/                 # One-shot scripts (fixups, experiments)
    fix_dept_linkage.py    # Date-prefixed or descriptive names
  tests/                   # Mirrors app/ structure
    test_sync_wonde.py
    test_render.py
```

## Directory Purposes

| Directory | Purpose | Examples |
|-----------|---------|----------|
| `dsl/` | DSL source files | Entity definitions, surfaces, stories |
| `routes/` | Custom FastAPI route handlers | Override or extend generated API |
| `static/` | Project static assets | Images, custom CSS/JS |
| `app/` | Production application code | Services, integrations, generators |
| `app/db/` | Database operations | Snapshots, data fixups, seed scripts |
| `app/sync/` | External data integration | API clients, sync jobs, importers |
| `app/render/` | Document generation | PDF rendering, report builders |
| `app/qa/` | Quality assurance tooling | Visual regression, data validators |
| `app/demo/` | Demo data generation | Faker-based generators, seed data |
| `scripts/` | One-shot scripts | Migration fixups, experiments |
| `tests/` | Test files | Mirrors `app/` structure |

## Guidelines

### Where does new code go?

- **Will it run in production?** → `app/<category>/`
- **Is it a one-time fixup?** → `scripts/` (or delete after running — it's in git history)
- **Does it override framework behavior?** → `routes/` or `templates/`
- **Is it a test?** → `tests/`

### Avoid flat dumping grounds

Don't put everything in a single `pipeline/` or `scripts/` directory.
Group by purpose — code that changes together lives together.

### Archive superseded code

One-shot fixups and superseded scripts accumulate. Prefer deleting them
(they're in git history). If you must keep them, move to `scripts/archive/`.

### Sub-packages for related code

When a category grows beyond 3-4 files, extract a sub-package:

```
app/sync/
  __init__.py
  wonde/
    __init__.py
    client.py
    models.py
    sync.py
```

## Scaffold

Generate the `app/` structure for an existing project:

```bash
dazzle init --with-app    # Add app/ structure to existing project
```

## Project Post-Build Hook (#1290)

To inject ASGI middleware or run other setup against the fully-built
FastAPI app, place a module at `pipeline/serve/app_init.py` that exposes
a `register_middleware(app)` callable:

```python
# pipeline/serve/app_init.py
from pipeline.tenant.middleware import TenantResolutionMiddleware

def register_middleware(app) -> None:
    app.add_middleware(TenantResolutionMiddleware, ...)
```

The framework imports and invokes this module after `builder.build()`
and `assemble_post_build_routes` in both deployment paths
(`create_app_factory()` for `--factory` deployments and
`run_unified_server()` for the combined dev/local server). A missing
module is a silent no-op (most projects don't need this); any exception
raised by the hook itself is logged and re-raised so a broken hook
can't ship a half-configured app.

### Page-render auth bridge (#1401)

If your app resolves UI auth through its **own** ASGI entrypoint rather than
the framework auth middleware, the same module may expose a
`page_auth_context(request) -> AuthContext | None` callable. When present, it
**overrides** the framework default for page rendering, so `dazzle serve` (and
the `ux verify --guides` oracle that boots through it) resolves the same auth
context your own server would:

```python
# pipeline/serve/app_init.py
def page_auth_context(request):
    # Return your app's AuthContext (or None for anonymous).
    return request.scope.get("dazzle_auth_ctx")
```

Without it, an app whose page-auth is wired outside the framework middleware
leaves the server-rendered auth gate seeing `None` — so persona-gated overlays
(e.g. onboarding guides) never render and `ux verify --guides` false-negatives.
A missing callable is a no-op; a non-callable attribute is ignored with a warning.

## See Also

- [Customising rendered output](htmx-templates.md#customising-rendered-output) — custom renderers + per-entity detail viewers (replaces the removed Jinja template-override mechanism)
- [CLI Reference](cli.md) — `dazzle init` command options
