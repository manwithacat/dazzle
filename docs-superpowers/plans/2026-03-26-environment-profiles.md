# Environment Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `[environments.<name>]` sections to `dazzle.toml` with per-environment database config, a global `--env` CLI flag, and `DAZZLE_ENV` fallback.

**Architecture:** `EnvironmentProfile` dataclass parsed from TOML into `ProjectManifest.environments` dict. `resolve_database_url()` gains an `env_name` parameter inserted at priority #2 (between explicit URL and DATABASE_URL env var). A new `cli/env.py` module stores the active environment name set by the `--env` flag or `DAZZLE_ENV`.

**Tech Stack:** Python 3.12, dataclasses, tomllib, Typer, pytest

---

### Task 1: EnvironmentProfile Dataclass + Manifest Parsing — Tests

**Files:**
- Modify: `tests/unit/test_manifest_database.py`

- [ ] **Step 1: Write tests for environment profile parsing**

Append to `tests/unit/test_manifest_database.py`:

```python
from dazzle.core.manifest import EnvironmentProfile


class TestLoadManifestEnvironments:
    def test_no_environments_section(self, tmp_path: Path) -> None:
        """Backward compat: no [environments] → empty dict."""
        toml_path = _write_toml(tmp_path)
        mf = load_manifest(toml_path)
        assert mf.environments == {}

    def test_single_environment(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.development]
                database_url = "postgresql://localhost:5432/myapp_dev"
            """),
        )
        mf = load_manifest(toml_path)
        assert "development" in mf.environments
        profile = mf.environments["development"]
        assert isinstance(profile, EnvironmentProfile)
        assert profile.database_url == "postgresql://localhost:5432/myapp_dev"
        assert profile.database_url_env == ""
        assert profile.heroku_app == ""

    def test_multiple_environments(self, tmp_path: Path) -> None:
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.staging]
                database_url_env = "STAGING_DB_URL"
                heroku_app = "myapp-staging"

                [environments.production]
                database_url_env = "PROD_DB_URL"
                heroku_app = "myapp-prod"
            """),
        )
        mf = load_manifest(toml_path)
        assert len(mf.environments) == 2
        assert mf.environments["staging"].database_url_env == "STAGING_DB_URL"
        assert mf.environments["staging"].heroku_app == "myapp-staging"
        assert mf.environments["production"].heroku_app == "myapp-prod"

    def test_freeform_environment_names(self, tmp_path: Path) -> None:
        """Environment names are freeform — blue/green, demo, etc."""
        toml_path = _write_toml(
            tmp_path,
            textwrap.dedent("""\

                [environments.blue]
                database_url_env = "BLUE_DB"

                [environments.green]
                database_url_env = "GREEN_DB"

                [environments.demo]
                database_url = "postgresql://localhost:5432/demo"
            """),
        )
        mf = load_manifest(toml_path)
        assert set(mf.environments.keys()) == {"blue", "green", "demo"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_manifest_database.py::TestLoadManifestEnvironments -v`
Expected: FAIL — `EnvironmentProfile` not importable or `environments` not on `ProjectManifest`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_manifest_database.py
git commit -m "test: add environment profile parsing tests (#718)"
```

---

### Task 2: EnvironmentProfile Dataclass + Manifest Parsing — Implementation

**Files:**
- Modify: `src/dazzle/core/manifest.py`

- [ ] **Step 1: Add EnvironmentProfile dataclass**

In `src/dazzle/core/manifest.py`, add after the `DatabaseConfig` dataclass (around line 310):

```python
@dataclass
class EnvironmentProfile:
    """Per-environment configuration (database connection, Heroku app)."""

    database_url: str = ""
    database_url_env: str = ""
    heroku_app: str = ""
```

- [ ] **Step 2: Add environments field to ProjectManifest**

Add to `ProjectManifest` (after the `cdn` field, around line 343):

```python
    environments: dict[str, EnvironmentProfile] = field(default_factory=dict)
```

- [ ] **Step 3: Parse [environments.*] in load_manifest()**

In `load_manifest()`, add environment parsing after the `[ui]` section parsing (before the `return ProjectManifest(...)` call, around line 543):

```python
    # Parse environment profiles
    env_data = data.get("environments", {})
    environments: dict[str, EnvironmentProfile] = {}
    for env_name, env_config in env_data.items():
        if isinstance(env_config, dict):
            environments[env_name] = EnvironmentProfile(
                database_url=env_config.get("database_url", ""),
                database_url_env=env_config.get("database_url_env", ""),
                heroku_app=env_config.get("heroku_app", ""),
            )
```

- [ ] **Step 4: Pass environments to ProjectManifest constructor**

In the `return ProjectManifest(...)` call, add:

```python
        environments=environments,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_manifest_database.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/manifest.py
git commit -m "feat: EnvironmentProfile dataclass and manifest parsing (#718)"
```

---

### Task 3: resolve_database_url with env_name — Tests

**Files:**
- Modify: `tests/unit/test_manifest_database.py`

- [ ] **Step 1: Write tests for resolve_database_url with env_name**

Append to `tests/unit/test_manifest_database.py`:

```python
class TestResolveDatabaseUrlWithEnv:
    """Tests for the env_name parameter in resolve_database_url()."""

    def _make_manifest_with_envs(self) -> ProjectManifest:
        return ProjectManifest(
            name="test",
            version="0.1.0",
            project_root=".",
            module_paths=["./dsl"],
            database=DatabaseConfig(url="postgresql://toml:5432/tomldb"),
            environments={
                "staging": EnvironmentProfile(
                    database_url_env="STAGING_DB_URL",
                    heroku_app="myapp-staging",
                ),
                "development": EnvironmentProfile(
                    database_url="postgresql://localhost:5432/devdb",
                ),
                "both": EnvironmentProfile(
                    database_url="postgresql://direct:5432/db",
                    database_url_env="INDIRECT_DB_URL",
                ),
            },
        )

    def test_explicit_url_beats_env_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--database-url always wins, even with --env."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        result = resolve_database_url(
            manifest, explicit_url="postgresql://cli:5432/clidb", env_name="development"
        )
        assert result == "postgresql://cli:5432/clidb"

    def test_env_profile_direct_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Profile with database_url resolves directly."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        result = resolve_database_url(manifest, env_name="development")
        assert result == "postgresql://localhost:5432/devdb"

    def test_env_profile_env_var_indirection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Profile with database_url_env resolves from environment."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("STAGING_DB_URL", "postgresql://staging:5432/stgdb")
        manifest = self._make_manifest_with_envs()
        result = resolve_database_url(manifest, env_name="staging")
        assert result == "postgresql://staging:5432/stgdb"

    def test_env_profile_env_var_unset_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Profile env var not set → fall through to DATABASE_URL."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("STAGING_DB_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        result = resolve_database_url(manifest, env_name="staging")
        # Falls through to manifest [database].url
        assert result == "postgresql://toml:5432/tomldb"

    def test_env_profile_direct_beats_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_url wins over database_url_env on same profile."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("INDIRECT_DB_URL", "postgresql://indirect:5432/db")
        manifest = self._make_manifest_with_envs()
        result = resolve_database_url(manifest, env_name="both")
        assert result == "postgresql://direct:5432/db"

    def test_env_profile_beats_database_url_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--env profile beats DATABASE_URL env var."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://ambient:5432/ambientdb")
        manifest = self._make_manifest_with_envs()
        result = resolve_database_url(manifest, env_name="development")
        assert result == "postgresql://localhost:5432/devdb"

    def test_unknown_env_name_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown environment name raises SystemExit."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        with pytest.raises(SystemExit, match="Unknown environment 'nonexistent'"):
            resolve_database_url(manifest, env_name="nonexistent")

    def test_unknown_env_lists_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Error message lists available environments."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        with pytest.raises(SystemExit, match="staging"):
            resolve_database_url(manifest, env_name="nonexistent")

    def test_no_env_name_uses_existing_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty env_name → standard resolution (backward compat)."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = self._make_manifest_with_envs()
        result = resolve_database_url(manifest, env_name="")
        assert result == "postgresql://toml:5432/tomldb"

    def test_env_profile_normalises_postgres_scheme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Heroku postgres:// in profile gets normalised."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        manifest = ProjectManifest(
            name="test",
            version="0.1.0",
            project_root=".",
            module_paths=["./dsl"],
            environments={
                "heroku": EnvironmentProfile(database_url="postgres://u:p@h:5432/d"),
            },
        )
        result = resolve_database_url(manifest, env_name="heroku")
        assert result == "postgresql://u:p@h:5432/d"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_manifest_database.py::TestResolveDatabaseUrlWithEnv -v`
Expected: FAIL — `env_name` parameter not accepted

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_manifest_database.py
git commit -m "test: resolve_database_url with env_name tests (#718)"
```

---

### Task 4: resolve_database_url with env_name — Implementation

**Files:**
- Modify: `src/dazzle/core/manifest.py`

- [ ] **Step 1: Update resolve_database_url signature and implementation**

Replace the current `resolve_database_url` function (lines 568-609) with:

```python
def resolve_database_url(
    manifest: ProjectManifest | None = None,
    *,
    explicit_url: str = "",
    env_name: str = "",
) -> str:
    """Resolve the database URL with clear priority.

    Priority:
        1. explicit_url (CLI ``--database-url`` flag)
        2. Environment profile (``--env`` / ``DAZZLE_ENV``)
        3. ``DATABASE_URL`` environment variable
        4. ``dazzle.toml`` ``[database].url`` (supports ``env:VAR_NAME`` indirection)
        5. Default: ``postgresql://localhost:5432/dazzle``

    The ``env:VAR_NAME`` syntax in the manifest lets users commit a safe pointer
    (e.g. ``url = "env:DATABASE_URL"``) that resolves at runtime.

    Heroku-style ``postgres://`` URLs are normalised to ``postgresql://``
    for SQLAlchemy compatibility.
    """
    # 1. Explicit CLI flag
    if explicit_url:
        return _normalise_postgres_scheme(explicit_url)

    # 2. Environment profile
    if env_name and manifest is not None:
        if env_name not in manifest.environments:
            available = ", ".join(sorted(manifest.environments.keys())) or "(none)"
            raise SystemExit(
                f"Unknown environment '{env_name}'. "
                f"Available: {available}. "
                f"Check [environments.*] in dazzle.toml."
            )
        profile = manifest.environments[env_name]
        # database_url wins over database_url_env on the same profile
        if profile.database_url:
            return _normalise_postgres_scheme(profile.database_url)
        if profile.database_url_env:
            resolved = os.environ.get(profile.database_url_env, "")
            if resolved:
                return _normalise_postgres_scheme(resolved)
        # Profile set but neither field resolved — fall through

    # 3. Environment variable
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        return _normalise_postgres_scheme(env_url)

    # 4. Manifest [database].url
    if manifest is not None:
        manifest_url = manifest.database.url
        if manifest_url.startswith("env:"):
            var_name = manifest_url[4:]
            resolved = os.environ.get(var_name, "")
            if resolved:
                return _normalise_postgres_scheme(resolved)
            # env var not set — fall through to default
        elif manifest_url and manifest_url != _DEFAULT_DATABASE_URL:
            return _normalise_postgres_scheme(manifest_url)

    # 5. Default
    return _DEFAULT_DATABASE_URL
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_manifest_database.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/core/manifest.py
git commit -m "feat: resolve_database_url with env_name priority (#718)"
```

---

### Task 5: CLI env Module + --env Flag — Tests

**Files:**
- Create: `tests/unit/test_cli_env.py`

- [ ] **Step 1: Write tests for the CLI env module**

```python
"""Tests for CLI environment profile resolution."""

import os

import pytest


class TestCliEnv:
    def test_get_active_env_default_empty(self) -> None:
        """Default active env is empty string."""
        from dazzle.cli.env import get_active_env, set_active_env

        set_active_env("")
        assert get_active_env() == ""

    def test_set_and_get_active_env(self) -> None:
        """set_active_env stores the value for get_active_env."""
        from dazzle.cli.env import get_active_env, set_active_env

        set_active_env("staging")
        assert get_active_env() == "staging"
        set_active_env("")  # cleanup

    def test_resolve_env_cli_flag_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """--env flag (non-empty) beats DAZZLE_ENV."""
        monkeypatch.setenv("DAZZLE_ENV", "production")
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name("staging") == "staging"

    def test_resolve_env_dazzle_env_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DAZZLE_ENV used when CLI flag is empty."""
        monkeypatch.setenv("DAZZLE_ENV", "production")
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name("") == "production"

    def test_resolve_env_nothing_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No flag, no DAZZLE_ENV → empty string."""
        monkeypatch.delenv("DAZZLE_ENV", raising=False)
        from dazzle.cli.env import resolve_env_name

        assert resolve_env_name("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_cli_env.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.cli.env'`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_cli_env.py
git commit -m "test: CLI env module tests (#718)"
```

---

### Task 6: CLI env Module + --env Flag — Implementation

**Files:**
- Create: `src/dazzle/cli/env.py`
- Modify: `src/dazzle/cli/__init__.py`

- [ ] **Step 1: Create the env module**

Create `src/dazzle/cli/env.py`:

```python
"""Active environment profile for the CLI session.

Set by the ``--env`` global flag or ``DAZZLE_ENV`` environment variable.
Read by database-touching commands to select the right connection.
"""

import os

_active_env: str = ""


def resolve_env_name(cli_flag: str) -> str:
    """Resolve the active environment name.

    Priority:
        1. ``--env`` CLI flag (non-empty value)
        2. ``DAZZLE_ENV`` environment variable
        3. Empty string (no profile — existing behaviour)
    """
    if cli_flag:
        return cli_flag
    return os.environ.get("DAZZLE_ENV", "")


def set_active_env(name: str) -> None:
    """Store the active environment name for the CLI session."""
    global _active_env  # noqa: PLW0603
    _active_env = name


def get_active_env() -> str:
    """Get the active environment name."""
    return _active_env
```

- [ ] **Step 2: Wire --env into the CLI callback**

In `src/dazzle/cli/__init__.py`, update the `main_callback`:

```python
@app.callback()
def main_callback(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and environment information",
    ),
    env: str = typer.Option(
        "",
        "--env",
        help="Environment profile from dazzle.toml (e.g. staging, production)",
    ),
) -> None:
    """DAZZLE CLI main callback for global options."""
    from dazzle.cli.env import resolve_env_name, set_active_env

    resolved = resolve_env_name(env)
    if resolved:
        set_active_env(resolved)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/unit/test_cli_env.py -v`
Expected: All 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/env.py src/dazzle/cli/__init__.py
git commit -m "feat: --env global CLI flag with DAZZLE_ENV fallback (#718)"
```

---

### Task 7: Thread env_name Through Database Commands

**Files:**
- Modify: `src/dazzle/db/connection.py`
- Modify: `src/dazzle/cli/db.py`
- Modify: `src/dazzle/cli/dbshell.py`
- Modify: `src/dazzle/cli/tenant.py`
- Modify: `src/dazzle/cli/services/auth_service.py`
- Modify: `src/dazzle/cli/services/build_service.py`
- Modify: `src/dazzle/cli/backup.py`

- [ ] **Step 1: Update resolve_db_url in connection.py**

In `src/dazzle/db/connection.py`, update `resolve_db_url` to accept and pass through `env_name`:

```python
def resolve_db_url(
    *,
    explicit_url: str = "",
    project_root: Path | None = None,
    env_name: str = "",
) -> str:
    """Resolve the database URL.

    Priority: explicit_url > env profile > DATABASE_URL env > dazzle.toml > default.
    Delegates to dazzle.core.manifest.resolve_database_url.
    """
    manifest = None
    if project_root is not None:
        toml_path = project_root / "dazzle.toml"
        if toml_path.exists():
            manifest = load_manifest(toml_path)

    return resolve_database_url(manifest, explicit_url=explicit_url, env_name=env_name)
```

- [ ] **Step 2: Update _resolve_url in cli/db.py**

In `src/dazzle/cli/db.py`, update `_resolve_url` (around line 279):

```python
def _resolve_url(database_url: str) -> str:
    """Resolve database URL from flag, env, or manifest."""
    from dazzle.cli.env import get_active_env
    from dazzle.db.connection import resolve_db_url

    return resolve_db_url(
        explicit_url=database_url,
        project_root=Path.cwd().resolve(),
        env_name=get_active_env(),
    )
```

- [ ] **Step 3: Update _resolve_db_url in cli/dbshell.py**

In `src/dazzle/cli/dbshell.py`, update `_resolve_db_url` (around line 13):

```python
def _resolve_db_url(database_url: str | None = None) -> str:
    """Resolve DB URL with env profile support."""
    from dazzle.cli.env import get_active_env
    from dazzle.core.manifest import load_manifest, resolve_database_url

    manifest = None
    toml_path = Path.cwd().resolve() / "dazzle.toml"
    if toml_path.exists():
        manifest = load_manifest(toml_path)
    return resolve_database_url(
        manifest,
        explicit_url=database_url or "",
        env_name=get_active_env(),
    )
```

- [ ] **Step 4: Update tenant.py**

In `src/dazzle/cli/tenant.py`, update the two functions that call `resolve_database_url`. Find the `create_tenant` function (around line 34) and update:

```python
    from dazzle.cli.env import get_active_env
    from dazzle.core.manifest import load_manifest, resolve_database_url

    manifest = load_manifest(Path.cwd().resolve() / "dazzle.toml")
    db_url = resolve_database_url(manifest, env_name=get_active_env())
```

Find the `list_tenants` function (around line 44) and make the same change:

```python
    from dazzle.cli.env import get_active_env
    from dazzle.core.manifest import load_manifest, resolve_database_url

    toml_path = Path.cwd().resolve() / "dazzle.toml"
    manifest = load_manifest(toml_path) if toml_path.exists() else None
    db_url = resolve_database_url(manifest, env_name=get_active_env())
```

- [ ] **Step 5: Update auth_service.py**

In `src/dazzle/cli/services/auth_service.py`, find `resolve_database_url` call (around line 38) and update:

```python
        from dazzle.cli.env import get_active_env
        from dazzle.core.manifest import load_manifest, resolve_database_url

        manifest = load_manifest(toml_path) if toml_path.exists() else None
        url = resolve_database_url(manifest, explicit_url=explicit, env_name=get_active_env())
```

- [ ] **Step 6: Update build_service.py**

In `src/dazzle/cli/services/build_service.py`, find the `resolve_database_url` method (around line 65) and update:

```python
    def resolve_database_url(self, explicit_url: str = "") -> str:
        from dazzle.cli.env import get_active_env
        from dazzle.core.manifest import load_manifest, resolve_database_url

        manifest = None
        toml_path = self.project_root / "dazzle.toml"
        if toml_path.exists():
            manifest = load_manifest(toml_path)
        return resolve_database_url(manifest, explicit_url=explicit_url, env_name=get_active_env())
```

- [ ] **Step 7: Update backup.py**

In `src/dazzle/cli/backup.py`, find `_resolve_database_url` (around line 24) and update:

```python
def _resolve_database_url(manifest_path: Path) -> str:
    from dazzle.cli.env import get_active_env
    from dazzle.core.manifest import load_manifest, resolve_database_url

    manifest = load_manifest(manifest_path) if manifest_path.exists() else None
    return resolve_database_url(manifest, env_name=get_active_env())
```

- [ ] **Step 8: Run existing tests to verify nothing broke**

Run: `pytest tests/unit/test_manifest_database.py tests/unit/test_cli_env.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/dazzle/db/connection.py src/dazzle/cli/db.py src/dazzle/cli/dbshell.py src/dazzle/cli/tenant.py src/dazzle/cli/services/auth_service.py src/dazzle/cli/services/build_service.py src/dazzle/cli/backup.py
git commit -m "feat: thread env_name through all database commands (#718)"
```

---

### Task 8: Semantics KB Concept

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/misc.toml`
- Modify: `src/dazzle/mcp/semantics_kb/__init__.py` (aliases)

- [ ] **Step 1: Add environment_profiles concept to misc.toml**

Append to `src/dazzle/mcp/semantics_kb/misc.toml`:

```toml
[concepts.environment_profiles]
category = "Project Configuration"
since_version = "0.49.2"
definition = """
Per-environment database configuration in dazzle.toml. Declare [environments.<name>] sections
with database_url (literal) or database_url_env (env var indirection) and optional heroku_app.
Select at runtime via --env flag or DAZZLE_ENV environment variable.

Resolution priority:
1. --database-url (explicit CLI flag — always wins)
2. --env profile (database_url or database_url_env from the named profile)
3. DATABASE_URL environment variable
4. dazzle.toml [database].url
5. Default: postgresql://localhost:5432/dazzle
"""
syntax = '''
[environments.development]
database_url = "postgresql://localhost:5432/myapp_dev"

[environments.staging]
database_url_env = "HEROKU_POSTGRESQL_COPPER_URL"
heroku_app = "myapp-staging"

[environments.production]
database_url_env = "HEROKU_POSTGRESQL_COPPER_URL"
heroku_app = "myapp-prod"
'''
example = '''
# Select environment via CLI flag
dazzle db status --env staging

# Or via environment variable (CI/CD)
export DAZZLE_ENV=production
dazzle db status

# --database-url always wins, regardless of --env
dazzle db status --env production --database-url postgresql://override:5432/db
'''
related = ["authentication", "schedule"]
```

- [ ] **Step 2: Add aliases in semantics_kb/__init__.py**

In `src/dazzle/mcp/semantics_kb/__init__.py`, add to the `ALIASES` dict:

```python
    "env_profiles": "environment_profiles",
    "dazzle_env": "environment_profiles",
```

- [ ] **Step 3: Run seed test to verify TOML is valid**

Run: `pytest tests/unit/test_kg_seed.py::TestSeedPipeline::test_seed_framework_knowledge_creates_concepts -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/misc.toml src/dazzle/mcp/semantics_kb/__init__.py
git commit -m "feat: environment_profiles concept in semantics KB (#718)"
```

---

### Task 9: Template Update

**Files:**
- Modify: `src/dazzle/templates/blank/dazzle.toml`

- [ ] **Step 1: Add commented-out environments block**

Append to `src/dazzle/templates/blank/dazzle.toml`:

```toml
[auth]
enabled = true
provider = "session"
allow_registration = true

# Environment profiles — select via: dazzle <command> --env <name>
# Or set DAZZLE_ENV=<name> for CI/CD.
# Priority: --database-url > --env profile > DATABASE_URL > [database].url > default
#
# [environments.development]
# database_url = "postgresql://localhost:5432/{{project_name}}_dev"
#
# [environments.staging]
# database_url_env = "HEROKU_POSTGRESQL_COPPER_URL"
# heroku_app = "{{project_name}}-staging"
#
# [environments.production]
# database_url_env = "HEROKU_POSTGRESQL_COPPER_URL"
# heroku_app = "{{project_name}}-prod"
```

- [ ] **Step 2: Commit**

```bash
git add src/dazzle/templates/blank/dazzle.toml
git commit -m "feat: environment profiles template in blank project (#718)"
```

---

### Task 10: Full Integration Test

**Files:**
- No new files

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `ruff check src/dazzle/core/manifest.py src/dazzle/cli/env.py src/dazzle/cli/__init__.py src/dazzle/cli/db.py src/dazzle/cli/dbshell.py src/dazzle/db/connection.py --fix && ruff format src/dazzle/core/manifest.py src/dazzle/cli/env.py src/dazzle/cli/__init__.py src/dazzle/cli/db.py src/dazzle/cli/dbshell.py src/dazzle/db/connection.py`
Expected: Clean

- [ ] **Step 3: Run mypy**

Run: `mypy src/dazzle/core/manifest.py src/dazzle/cli/env.py src/dazzle/cli/__init__.py src/dazzle/db/connection.py`
Expected: No errors

- [ ] **Step 4: Fix any issues and commit**

```bash
git add -u
git commit -m "fix: lint and type fixes for environment profiles (#718)"
```

(Skip this commit if no fixes needed.)
