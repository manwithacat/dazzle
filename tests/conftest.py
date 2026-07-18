"""Shared pytest fixtures for DAZZLE tests."""

import os
from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from tests import _pg_worker_db


def _load_dotenv_for_tests() -> None:
    """Load `.env` from the repo root so test fixtures see the same
    environment a developer's shell sees. Critical for TEST_DATABASE_URL
    (Postgres-backed tests) and similar opt-in integration tests that
    skip when the var is missing. Only loads variables not already
    present in the environment so explicit `TEST_DATABASE_URL=... pytest`
    invocations win over the file."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        # Skip host DATABASE_URL — a developer's support_tickets / app DB
        # must not hijack unit HTTP e2e fixtures that expect sqlite or a
        # clean schema. Prefer TEST_DATABASE_URL for opt-in Postgres tests.
        if key == "DATABASE_URL":
            continue
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_for_tests()

# Rich/Typer highlight numbers and JSON when TERM looks interactive. Local
# agent shells often set TERM=xterm-256color while CI is dumb — that made
# CLI tests pass on Actions and fail on laptops (or vice versa). Force dumb
# for the whole suite so CliRunner output matches bare text assertions.
os.environ["TERM"] = "dumb"
os.environ.setdefault("NO_COLOR", "1")

# Local shells often export DATABASE_URL for an app under development
# (support_tickets schema ≠ simple_task HTTP e2e fixtures). GitHub Actions
# sets CI=true and its own DATABASE_URL for Postgres jobs — leave that alone.
# Opt-in local Postgres: set TEST_DATABASE_URL (preferred) or CI=true.
if not os.environ.get("CI") and not os.environ.get("DAZZLE_KEEP_DATABASE_URL"):
    os.environ.pop("DATABASE_URL", None)


@pytest.fixture(autouse=True, scope="session")
def _skip_infra_check() -> None:
    """Disable startup infrastructure validation in unit tests."""
    os.environ.setdefault("DAZZLE_SKIP_INFRA_CHECK", "1")


# Per-xdist-worker PostgreSQL databases (see tests/_pg_worker_db.py).
#
# The controller decides ONCE whether workers get their own databases and
# pushes the verdict to every worker via xdist's workerinput channel. A
# per-worker probe would risk split-brain: one worker's transient probe
# failure while the controller probed True would silently run postgres tests
# against the shared base DB concurrently with other workers' — the exact
# corruption this mechanism prevents. With the verdict centralized, a worker
# either provisions (and crashes the run loudly if it can't) or knows the
# fallback pin is in force.
_PG_WORKER_DB_KEY = "dazzle_pg_worker_db"


def _pg_worker_db_enabled() -> bool:
    """Controller-side verdict: can/should workers provision own databases?

    ``DAZZLE_PG_WORKER_DB=0`` (or off/false) forces the fallback pin — the
    escape hatch, and the lever the fallback path is tested with.
    """
    base_url = _pg_worker_db.base_pg_url()
    if not base_url:
        return False
    if os.environ.get("DAZZLE_PG_WORKER_DB", "").lower() in {"0", "off", "false"}:
        return False
    return _pg_worker_db.can_create_databases(base_url)


def pytest_configure_node(node) -> None:  # type: ignore[no-untyped-def]  # xdist controller hook
    """Runs on the controller once per worker node, before the worker starts."""
    node.workerinput[_PG_WORKER_DB_KEY] = "1" if _pg_worker_db_enabled() else "0"


# Suppress deprecation warnings from deprecated adapters used in tests
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "filterwarnings",
        "ignore:OutboxPublisher.*db_path.*is deprecated:DeprecationWarning",
    )
    _provision_pg_worker_db(config)


def _provision_pg_worker_db(config: pytest.Config) -> None:
    """In an xdist worker the controller cleared: provision this worker's DB.

    Runs before collection, so the env rewrite is visible to the module-
    import-time ``os.environ.get("TEST_DATABASE_URL")`` reads most postgres
    test files do. Only env vars already set get rewritten — setting an
    unset DATABASE_URL would activate tests that today skip. A provisioning
    failure raises, which crashes the worker and fails the run loudly —
    never a silent fall-through to the shared base database.
    """
    workerinput = getattr(config, "workerinput", None)
    if not workerinput or workerinput.get(_PG_WORKER_DB_KEY) != "1":
        return
    base_url = _pg_worker_db.base_pg_url()
    assert base_url, "controller set the worker-db flag without a DB URL"
    new_url = _pg_worker_db.provision_worker_database(base_url, workerinput["workerid"])
    for var in _pg_worker_db.PG_ENV_VARS:
        if os.environ.get(var):
            os.environ[var] = new_url


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Fallback serialization for postgres-marked tests.

    Applies only in xdist workers the controller did NOT clear for per-worker
    databases while a live DB URL is configured: all postgres-marked tests
    then share one worker under ``--dist loadgroup`` (they'd corrupt each
    other's state on a shared database otherwise).

    ``tryfirst`` is load-bearing: xdist's WorkerInteractor registers AFTER
    conftests, so under plain (LIFO) ordering its collection_modifyitems —
    which bakes each item's xdist_group into the ``@group`` nodeid suffix the
    controller's loadgroup scheduler splits on — would run BEFORE this hook
    and never see the marker (empirically: 26 cross-worker failures with the
    plain hook, green with tryfirst). Serial runs never reach this: without
    xdist there is no workerinput.
    """
    workerinput = getattr(config, "workerinput", None)
    if not workerinput or workerinput.get(_PG_WORKER_DB_KEY) == "1":
        return
    if not _pg_worker_db.base_pg_url():
        return
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(pytest.mark.xdist_group("postgres"))


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def dsl_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return path to DSL fixtures directory."""
    return fixtures_dir / "dsl"


@pytest.fixture
def simple_entity() -> ir.EntitySpec:
    """Return a simple entity for testing."""
    return ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
            ir.FieldSpec(
                name="status",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.ENUM, enum_values=["todo", "in_progress", "done"]
                ),
                modifiers=[],
            ),
        ],
    )


@pytest.fixture
def simple_appspec(simple_entity: ir.EntitySpec) -> ir.AppSpec:
    """Return a simple AppSpec for testing."""
    return ir.AppSpec(
        name="test_app",
        title="Test App",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[simple_entity]),
    )


@pytest.fixture
def simple_test_dsl(dsl_fixtures_dir: Path) -> Path:
    """Return path to simple_test.dsl fixture."""
    return dsl_fixtures_dir / "simple_test.dsl"


def parse_dsl_fixture(dsl_path: Path) -> ir.AppSpec:
    """Helper to parse a DSL fixture and return AppSpec."""
    modules = parse_modules([dsl_path])
    # Infer root module name from first module
    root_module = modules[0].name if modules else "test.app"
    return build_appspec(modules, root_module)
