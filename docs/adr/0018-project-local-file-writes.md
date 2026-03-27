# ADR-0018: Project-Local File Writes

**Status**: Accepted
**Date**: 2026-03-27
**Relates to**: #724, ADR-0017 (Alembic migrations)

## Context

Dazzle is distributed as a pip package (`pip install dazzle-dsl`). When installed,
framework code lives in `site-packages/` which may be read-only (sandboxed installs,
Docker, system-managed Python). Several code paths used `Path(__file__).parents[N]`
to locate framework directories, then wrote project artifacts (migrations, caches,
reports) into those same directories. This is wrong for three reasons:

1. **Wrong location**: project artifacts mixed with framework distribution files
2. **Permission failures**: `site-packages/` is read-only on many deployment targets
3. **Cross-contamination**: multiple projects sharing a single Dazzle install would
   write into the same framework directory

Issue #724 exposed this: `dazzle db revision` wrote Alembic migrations into
`site-packages/dazzle_back/alembic/versions/` instead of the user's project.

## Decision

**All file writes go to the project directory. Never write to the package directory.**

Two rules:

1. **Read framework assets** (templates, env.py, TOML data, static files) via package
   import paths:
   ```python
   import dazzle_back
   framework_dir = Path(dazzle_back.__file__).parent / "alembic"
   ```
   Or use `importlib.resources` for assets that need to survive wheel packaging.

2. **Write project artifacts** (migrations, caches, reports, generated code) to the
   project directory:
   ```python
   project_root = Path.cwd()  # or manifest-resolved path
   output_dir = project_root / ".dazzle" / "migrations" / "versions"
   ```

**Banned pattern**: `Path(__file__).resolve().parents[N]` for write targets. This
resolves to `site-packages/` in pip installs and is not the user's project.

## Consequences

- All CLI commands that write files must resolve the project root from `Path.cwd()`
  or from the manifest, never from `__file__`
- The `.dazzle/` directory is the standard location for framework-generated project
  artifacts (already used for sentinel data, runtime state, logs)
- Framework assets remain read-only after installation — no post-install writes
- Editable installs (`pip install -e .`) still work because the package path points
  to the source tree, but the principle holds: writes go to the project being worked
  on, not the framework source
