# Environment Profiles in dazzle.toml

**Issue**: #718
**Status**: Approved
**Date**: 2026-03-26

## Summary

Add `[environments.<name>]` sections to `dazzle.toml` so projects can declare per-environment database connections and Heroku app names. A global `--env` CLI flag (with `DAZZLE_ENV` fallback) selects the active profile.

## Design

### 1. TOML Schema

New `[environments.<name>]` sections in `dazzle.toml`:

```toml
# Environment profiles — selected via --env or DAZZLE_ENV
# Priority: --database-url > --env profile > DATABASE_URL env var > [database].url > default
#
# Only database connection varies per environment. Other config (auth, theme, etc.)
# is environment-independent at this stage.

[environments.development]
database_url = "postgresql://localhost:5432/myapp_dev"

[environments.staging]
database_url_env = "HEROKU_POSTGRESQL_COPPER_URL"
heroku_app = "myapp-staging"

[environments.production]
database_url_env = "HEROKU_POSTGRESQL_COPPER_URL"
heroku_app = "myapp-prod"
```

- **`database_url`**: literal connection string (development use — never commit production credentials).
- **`database_url_env`**: env var name to read at runtime (production use — safe to commit).
- **`heroku_app`**: Heroku app name for `dazzle db` commands that shell out to `heroku pg:`.
- Profile names are freeform strings — no fixed set. Common convention: `development`, `staging`, `production`. Blue/green, demo, per-developer profiles all work.
- If both `database_url` and `database_url_env` are set on the same profile, `database_url` wins (explicit > indirect).

### 2. Manifest Dataclass

New dataclass in `src/dazzle/core/manifest.py`:

```python
@dataclass
class EnvironmentProfile:
    """Per-environment configuration (database connection, Heroku app)."""
    database_url: str = ""
    database_url_env: str = ""
    heroku_app: str = ""
```

New field on `ProjectManifest`:

```python
environments: dict[str, EnvironmentProfile] = field(default_factory=dict)
```

`load_manifest()` parses `[environments.*]` TOML sections into this dict.

### 3. Database URL Resolution

Updated priority chain for `resolve_database_url()` — new `env_name` parameter:

```
1. --database-url (explicit CLI flag — always wins)
2. --env profile (database_url or database_url_env from the named profile)
3. DATABASE_URL env var
4. dazzle.toml [database].url (with env: indirection support)
5. Default: postgresql://localhost:5432/dazzle
```

Step 2 resolution: if the profile has `database_url`, use it directly. If it has `database_url_env`, read that env var at runtime. If neither resolves (env var not set), fall through to step 3.

**Error handling**: if `env_name` is provided but `[environments.<env_name>]` doesn't exist in the manifest, raise a `SystemExit` with a clear error listing available profiles. Do not silently fall through.

### 4. CLI Integration

**Global `--env` flag** on the Typer app callback in `cli/__init__.py`:

```python
@app.callback()
def main_callback(
    env: str = typer.Option("", "--env", help="Environment profile from dazzle.toml"),
):
    ...
```

**Resolution order** for the active environment name:
1. `--env` CLI flag (highest priority)
2. `DAZZLE_ENV` environment variable (fallback for CI/CD)
3. No environment (default — existing behaviour, no profile applied)

**Storage**: new module `src/dazzle/cli/env.py` with:
- `_active_env: str = ""` module-level state
- `set_active_env(name: str) -> None` — called by the app callback
- `get_active_env() -> str` — called by commands that need the environment name

**Commands that consume it**: all database-touching commands pass `env_name=get_active_env()` to `resolve_database_url()`:
- `dazzle db status|verify|reset|cleanup|revision|upgrade`
- `dazzle dbshell`
- `dazzle serve --local`
- `dazzle tenant *`

**Commands unaffected**: `validate`, `lint`, `lsp`, `mcp`, `specs`, `discovery`, etc.

### 5. Knowledge Base

New concept `environment_profiles` in `src/dazzle/mcp/semantics_kb/misc.toml`:
- `since_version = "0.49.2"`
- Documents the TOML schema, priority chain, `DAZZLE_ENV` convention, and examples
- Aliases: `env_profiles`, `environments`, `dazzle_env`

### 6. Template Update

Add commented-out `[environments.*]` block to `src/dazzle/templates/blank/dazzle.toml` so new projects see the pattern.

### 7. Testing

- Unit tests for `EnvironmentProfile` dataclass and `load_manifest()` parsing of `[environments.*]` sections
- Unit tests for `resolve_database_url()` with `env_name` — all 5 priority levels
- Unit test for unknown environment name → `SystemExit` error with available profiles
- Unit test for `database_url_env` indirection (reads from `os.environ`)
- Unit test for `get_active_env()` reading from `DAZZLE_ENV` fallback
- Unit test for `database_url` winning over `database_url_env` on same profile

### 8. What Does Not Change

- `dazzle serve` with Docker (Docker Compose manages its own env vars)
- MCP server (stateless reads, no database connection)
- DSL parsing or validation
- Auth, theme, shell, or other manifest config (environment-independent at this stage)

## Files to Modify

| File | Change |
|------|--------|
| `src/dazzle/core/manifest.py` | Add `EnvironmentProfile` dataclass, `environments` field on `ProjectManifest`, parse in `load_manifest()`, update `resolve_database_url()` |
| `src/dazzle/cli/env.py` | New module: `get_active_env()`, `set_active_env()` |
| `src/dazzle/cli/__init__.py` | Add `--env` to app callback, resolve `DAZZLE_ENV` fallback, call `set_active_env()` |
| `src/dazzle/cli/db.py` | Pass `env_name=get_active_env()` to `resolve_database_url()` |
| `src/dazzle/cli/dbshell.py` | Pass `env_name=get_active_env()` to DB URL resolution |
| `src/dazzle/cli/auth.py` | Pass `env_name=get_active_env()` if auth touches DB |
| `src/dazzle/mcp/semantics_kb/misc.toml` | Add `environment_profiles` concept |
| `src/dazzle/templates/blank/dazzle.toml` | Add commented-out `[environments.*]` example |
| `tests/unit/test_manifest.py` | Tests for profile parsing and resolve_database_url with env_name |
| `tests/unit/test_cli_env.py` | Tests for get_active_env / DAZZLE_ENV |
