# Project Layout

Every Dazzle project starts with a DSL directory and a `dazzle.toml`
manifest. As the project grows, custom Python code needs a home. This
reference describes the recommended layout.

## Minimal Project

```
my-app/
  dazzle.toml              # Project manifest
  dsl/
    app.dsl                # DSL entry point
    entities.dsl           # Entity definitions
    surfaces.dsl           # UI surfaces
```

This is sufficient for apps that are fully DSL-driven with no custom code.

## Full Project Layout

When a project has custom Python code beyond the DSL:

```
my-app/
  dazzle.toml              # Project manifest
  dsl/                     # DSL source files
    app.dsl
    entities.dsl
    surfaces.dsl
    stories.dsl
  routes/                  # Custom FastAPI route overrides
  templates/               # Custom Jinja2 template overrides (see dz:// docs)
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
| `templates/` | Jinja2 template overrides | Custom `base.html` via `dz://` |
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

## See Also

- [Template Overrides](htmx-templates.md#template-overrides) — `dz://` prefix for template customization
- [CLI Reference](cli.md) — `dazzle init` command options
