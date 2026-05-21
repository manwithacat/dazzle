"""RBAC verifier — Layer 2 of the RBAC verification framework.

Provides types for representing verification results, the core `compare_cell()`
comparison function, and `VerificationReport` with JSON serialisation.

The full `verify()` async function (which starts a live server and probes
endpoints) is stubbed here. The types and comparison logic are the critical
pieces for unit testing.
"""

from __future__ import annotations  # required: forward reference

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from dazzle.core.strings import to_api_plural
from dazzle.rbac.audit import AccessDecisionRecord
from dazzle.rbac.matrix import AccessMatrix, PolicyDecision

if TYPE_CHECKING:
    import httpx

    from dazzle.back.runtime.auth.store import AuthStore
    from dazzle.back.runtime.server import DazzleBackendApp
    from dazzle.core.ir import AppSpec


class CellResult(StrEnum):
    """The verification outcome for a single (role, entity, operation) cell."""

    PASS = "PASS"
    """Observed behaviour matches the expected policy decision."""

    VIOLATION = "VIOLATION"
    """Observed behaviour contradicts the expected policy decision."""

    WARNING = "WARNING"
    """Observed behaviour is technically consistent but warrants review."""


@dataclass
class VerifiedCell:
    """Verification result for a single (role, entity, operation) triple."""

    role: str
    entity: str
    operation: str
    expected: PolicyDecision
    observed_status: int
    observed_count: int | None
    result: CellResult
    audit_records: list[AccessDecisionRecord]
    detail: str

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "role": self.role,
            "entity": self.entity,
            "operation": self.operation,
            "expected": self.expected.value,
            "observed_status": self.observed_status,
            "observed_count": self.observed_count,
            "result": self.result.value,
            "audit_records": [r.to_dict() for r in self.audit_records],
            "detail": self.detail,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VerifiedCell:
        records = [AccessDecisionRecord(**r) for r in d.get("audit_records", [])]
        return cls(
            role=d["role"],
            entity=d["entity"],
            operation=d["operation"],
            expected=PolicyDecision(d["expected"]),
            observed_status=d["observed_status"],
            observed_count=d.get("observed_count"),
            result=CellResult(d["result"]),
            audit_records=records,
            detail=d.get("detail", ""),
        )


@dataclass
class VerificationReport:
    """Full RBAC verification report produced by `verify()`."""

    app_name: str
    timestamp: str
    dazzle_version: str
    matrix: AccessMatrix | None
    cells: list[VerifiedCell]
    total: int
    passed: int
    violated: int
    warnings: int

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serialisable representation of the report."""
        matrix_json = self.matrix.to_json() if self.matrix is not None else None
        return {
            "app_name": self.app_name,
            "timestamp": self.timestamp,
            "dazzle_version": self.dazzle_version,
            "matrix": matrix_json,
            "cells": [c.to_dict() for c in self.cells],
            "total": self.total,
            "passed": self.passed,
            "violated": self.violated,
            "warnings": self.warnings,
        }

    def save(self, path: Path) -> None:
        """Serialise the report to *path* as JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> VerificationReport:
        """Deserialise a report previously saved with `.save()`."""
        raw = json.loads(path.read_text())

        # Reconstruct AccessMatrix if present.
        matrix: AccessMatrix | None = None
        if raw.get("matrix") is not None:
            m = raw["matrix"]
            cells_dict: dict[tuple[str, str, str], PolicyDecision] = {}
            for c in m.get("cells", []):
                cells_dict[(c["role"], c["entity"], c["operation"])] = PolicyDecision(c["decision"])
            from dazzle.rbac.matrix import PolicyWarning

            warnings = [
                PolicyWarning(
                    kind=w["kind"],
                    entity=w["entity"],
                    role=w["role"],
                    operation=w["operation"],
                    message=w["message"],
                )
                for w in m.get("warnings", [])
            ]
            matrix = AccessMatrix(
                cells=cells_dict,
                warnings=warnings,
                roles=m.get("roles", []),
                entities=m.get("entities", []),
                operations=m.get("operations", []),
            )

        cells = [VerifiedCell.from_dict(c) for c in raw.get("cells", [])]

        return cls(
            app_name=raw["app_name"],
            timestamp=raw["timestamp"],
            dazzle_version=raw["dazzle_version"],
            matrix=matrix,
            cells=cells,
            total=raw["total"],
            passed=raw["passed"],
            violated=raw["violated"],
            warnings=raw["warnings"],
        )


def compare_cell(
    expected: PolicyDecision,
    observed_status: int,
    observed_count: int | None,
    *,
    total: int | None = None,
) -> CellResult:
    """Compare an observed HTTP response against an expected policy decision.

    Comparison table
    ----------------
    DENY            + 403                              → PASS
    DENY            + 200                              → VIOLATION
    PERMIT          + 200                              → PASS
    PERMIT          + 403                              → VIOLATION
    PERMIT_FILTERED + 200 + 0 < count < total          → PASS
    PERMIT_FILTERED + 200 + count == total             → VIOLATION  (unfiltered)
    PERMIT_FILTERED + 200 + count == 0                 → WARNING
    PERMIT_UNPROTECTED + 200                           → PASS
    PERMIT_UNPROTECTED + 403                           → VIOLATION

    Any (expected, observed) combination not explicitly listed above
    is treated as WARNING.
    """
    if expected == PolicyDecision.DENY:
        if observed_status == 403:
            return CellResult.PASS
        if observed_status == 200:
            return CellResult.VIOLATION
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT:
        if observed_status == 200:
            return CellResult.PASS
        if observed_status == 403:
            return CellResult.VIOLATION
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT_FILTERED:
        if observed_status == 200:
            if observed_count is None:
                # Can't determine filtering without a count — treat as warning.
                return CellResult.WARNING
            if total is not None and observed_count == total:
                return CellResult.VIOLATION  # unfiltered
            if observed_count == 0:
                return CellResult.WARNING
            return CellResult.PASS
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT_UNPROTECTED:
        if observed_status == 200:
            return CellResult.PASS
        if observed_status == 403:
            return CellResult.VIOLATION
        return CellResult.WARNING

    return CellResult.WARNING


@dataclass
class _ProbeResult:
    """Observed outcome of probing one (role, entity, operation) cell."""

    status: int
    count: int | None


# operation -> (HTTP method, needs_id, has_body)
_PROBE_VERBS: dict[str, tuple[str, bool, bool]] = {
    "list": ("GET", False, False),
    "read": ("GET", True, False),
    "create": ("POST", False, True),
    "update": ("PATCH", True, True),
    "delete": ("DELETE", True, False),
}


async def _probe_cell(
    client: Any,
    *,
    entity: str,
    operation: str,
    baseline_id: str | None,
    body: dict[str, Any] | None = None,
) -> _ProbeResult:
    """Issue the HTTP request for one matrix cell and capture status + count.

    `client` is an authenticated httpx.AsyncClient (cookies already set).
    `baseline_id` is the seeded row for read/update/delete; ignored for
    list/create. `count` is the item count of a list response, else None.
    """
    method, needs_id, has_body = _PROBE_VERBS[operation]
    plural = to_api_plural(entity)
    url = f"/api/{plural}/{baseline_id}" if needs_id else f"/api/{plural}"

    kwargs: dict[str, Any] = {}
    if has_body:
        kwargs["json"] = body or {}

    response = await client.request(method, url, **kwargs)

    count: int | None = None
    if operation == "list" and response.status_code == 200:
        try:
            payload = response.json()
            items = payload.get("items") if isinstance(payload, dict) else payload
            if isinstance(items, list):
                count = len(items)
        except Exception:
            count = None

    return _ProbeResult(status=response.status_code, count=count)


class _DisposableDatabase:
    """Async context manager: create a scratch PostgreSQL database, yield
    its URL, drop it on exit. The scratch DB never leaks — the drop runs
    in `__aexit__` even when the body raises."""

    def __init__(self, server_url: str) -> None:
        self._server_url = server_url
        self._db_name = f"dazzle_verify_{uuid.uuid4().hex}"

    def _admin_url(self) -> str:
        # Uses the standard 'postgres' maintenance DB — present on every
        # standard PostgreSQL install; may need adjusting for non-standard
        # setups (e.g. RDS with a different superuser database).
        parts = urlparse(self._server_url)
        return urlunparse(parts._replace(path="/postgres"))

    def _scratch_url(self) -> str:
        parts = urlparse(self._server_url)
        return urlunparse(parts._replace(path=f"/{self._db_name}"))

    async def __aenter__(self) -> str:
        import psycopg

        with psycopg.connect(self._admin_url(), autocommit=True) as conn:
            # _db_name is a server-generated hex identifier (uuid4().hex) — not user input.
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            conn.execute(f'CREATE DATABASE "{self._db_name}"')
        return self._scratch_url()

    async def __aexit__(self, *exc: object) -> None:
        import psycopg

        # If the DROP fails (e.g. admin DB unreachable) that error
        # propagates and may shadow a body exception — acceptable; a
        # leaked scratch DB is always worth surfacing.
        with psycopg.connect(self._admin_url(), autocommit=True) as conn:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            conn.execute(f'DROP DATABASE IF EXISTS "{self._db_name}" WITH (FORCE)')


# ---------------------------------------------------------------------------
# Bootstrap superuser credentials used by _verifier_app_context.
# These are the credentials injected into the scratch DB so the verifier
# can log in as a superuser and probe entity endpoints.
# ---------------------------------------------------------------------------

_SUPERUSER_EMAIL: str = "verifier-admin@dazzle.internal"
_SUPERUSER_PASSWORD: str = "verifier-bootstrap-secret"  # nosec B105 — scratch DB only


@dataclass
class _VerifierContext:
    """Holds the booted AppSpec, an authenticated httpx client, and the auth store."""

    appspec: AppSpec
    client: httpx.AsyncClient  # authenticated as superuser
    auth_store: AuthStore | None


@dataclass
class _BuiltApp:
    """Everything `_verifier_app_context` needs from a single app build.

    Carries the FastAPI app, the `DazzleBackendApp` builder (for the
    wired `auth_store` and `db_manager`), and the parsed `AppSpec` — so
    the caller never has to parse the project DSL a second time.
    """

    app: Any  # FastAPI
    builder: DazzleBackendApp
    appspec: AppSpec


def _build_asgi_app(root: Path, database_url: str) -> _BuiltApp:
    """Build the Dazzle ASGI app for `root` against `database_url`.

    Thin adapter over `DazzleBackendApp.build()`.  Enables test-mode so
    entity tables are created on first boot (no prior Alembic migration
    needed) and `enable_auth` follows the project manifest so `/auth/login`
    is mounted when the project uses auth.

    The caller is responsible for creating the bootstrap superuser in the
    auth store before the first authenticated request.
    """
    from dazzle.back.runtime.app_factory import build_server_config
    from dazzle.back.runtime.server import DazzleBackendApp
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.manifest import load_manifest

    manifest = load_manifest(root / "dazzle.toml")
    appspec = load_project_appspec(root)
    config = build_server_config(
        appspec,
        database_url=database_url,
        enable_auth=manifest.auth.enabled,
        auth_config=manifest.auth if manifest.auth.enabled else None,
        enable_test_mode=True,
        project_root=root,
    )
    builder = DazzleBackendApp(appspec, config=config)
    app = builder.build()
    return _BuiltApp(app=app, builder=builder, appspec=appspec)


@asynccontextmanager
async def _verifier_app_context(
    project_root: str | Path,
    database_url: str,
) -> AsyncIterator[_VerifierContext]:
    """Boot the Dazzle app in-process against `database_url`, yield an
    httpx client bound to it via ASGITransport and logged in as the
    bootstrap superuser.  Schema + auth tables are created on boot
    (empty scratch DB).

    Usage::

        async with _verifier_app_context("fixtures/rbac_validation", db_url) as ctx:
            resp = await ctx.client.get("/health")
            assert resp.status_code == 200
    """
    import httpx

    from dazzle.cli.rbac import _login

    root = Path(project_root)

    # Build the ASGI app — entity + auth tables are created synchronously
    # during DazzleBackendApp.build() because enable_test_mode=True sets
    # _should_create_schema_on_startup() → True.  `_BuiltApp` carries the
    # builder + appspec so we don't re-parse the project DSL.
    built = _build_asgi_app(root, database_url)
    app = built.app
    auth_store = built.builder.auth_store

    # Seed the bootstrap superuser when auth is enabled.  AuthStore._init_db()
    # already ran inside build(); the create call is idempotent (skip if the
    # row already exists).
    if auth_store is not None:
        existing = auth_store.get_user_by_email(_SUPERUSER_EMAIL)
        if existing is None:
            auth_store.create_user(
                email=_SUPERUSER_EMAIL,
                password=_SUPERUSER_PASSWORD,
                is_superuser=True,
                roles=[],
            )

    # httpx.ASGITransport does NOT run FastAPI lifespan events, so the
    # `_open_db_pool` startup handler never fires — repositories and the
    # AuthStore fall back to per-call connections.  We still close the
    # connection pool on exit (idempotent no-op when it was never opened)
    # so a future change that opens it eagerly can't leak connections
    # across the scratch-DB drop.
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://verifier.local",
            follow_redirects=True,
        ) as client:
            if auth_store is not None:
                await _login(client, "http://verifier.local", _SUPERUSER_EMAIL, _SUPERUSER_PASSWORD)
            yield _VerifierContext(appspec=built.appspec, client=client, auth_store=auth_store)
    finally:
        db_manager = getattr(built.builder, "_db_manager", None)
        if db_manager is not None:
            db_manager.close_pool()


_VERIFIER_PASSWORD = "verify-test-password"  # nosec B105 — scratch DB only


async def _seed_role_users(
    auth_store: Any,
    *,
    roles: list[str],
) -> dict[str, tuple[str, str]]:
    """Create one user per role via auth_store. Returns {role: (email, password)}.

    `create_user` is synchronous; this wrapper is async for uniformity with
    other async verifier helpers so call sites can `await` it.
    """
    creds: dict[str, tuple[str, str]] = {}
    for role in roles:
        email = f"verify-{role}@dazzle.test"
        existing = auth_store.get_user_by_email(email)
        if existing is None:
            auth_store.create_user(
                email,
                _VERIFIER_PASSWORD,
                roles=[role],
            )
        creds[role] = (email, _VERIFIER_PASSWORD)
    return creds


def _minimal_body_for_entity(entity_name: str, appspec: Any) -> dict[str, Any]:
    """Build the smallest valid JSON body for creating an entity row.

    Iterates the entity's required non-PK fields and emits a representative
    value for each field type.  Ref fields are omitted (FK not seeded yet);
    callers should handle the 422 by omitting that entity.
    """
    from dazzle.core.ir.fields import FieldTypeKind

    entity = next(
        (e for e in (appspec.entities or []) if e.name == entity_name),
        None,
    )
    if entity is None:
        return {}

    body: dict[str, Any] = {}
    for field in entity.fields:
        if not field.is_required:
            continue
        if field.is_primary_key:
            continue
        kind = field.type.kind
        if kind == FieldTypeKind.REF:
            # FK — dependent entity not seeded; skip and let caller handle 422.
            continue
        if kind in (FieldTypeKind.STR, FieldTypeKind.TEXT, FieldTypeKind.EMAIL):
            body[field.name] = f"seed-{field.name}"
        elif kind == FieldTypeKind.INT:
            body[field.name] = 1
        elif kind == FieldTypeKind.DECIMAL:
            body[field.name] = "1.00"
        elif kind == FieldTypeKind.BOOL:
            body[field.name] = False
        elif kind == FieldTypeKind.DATE:
            body[field.name] = "2000-01-01"
        elif kind == FieldTypeKind.DATETIME:
            body[field.name] = "2000-01-01T00:00:00Z"
        elif kind == FieldTypeKind.UUID:
            body[field.name] = "00000000-0000-0000-0000-000000000001"
        elif kind == FieldTypeKind.ENUM:
            values = field.type.enum_values
            body[field.name] = values[0] if values else ""
        else:
            body[field.name] = ""
    return body


async def _seed_baseline_rows(
    client: Any,
    *,
    entities: list[str],
    appspec: Any,
) -> dict[str, str]:
    """Create one baseline row per entity (client authenticated as superuser).

    Returns {entity: row_id}. Entities whose create fails (e.g. missing FK
    dependency) are omitted so callers can continue with the entities that
    did seed successfully.
    """
    baseline: dict[str, str] = {}
    for entity in entities:
        body = _minimal_body_for_entity(entity, appspec)
        plural = to_api_plural(entity)
        resp = await client.request("POST", f"/api/{plural}", json=body)
        if resp.status_code in (200, 201):
            try:
                row_id = resp.json().get("id")
            except Exception:
                row_id = None
            if row_id:
                baseline[entity] = str(row_id)
    return baseline


async def verify(
    project_root: Path,
    *,
    host: str = "localhost",
    port: int = 8000,
) -> VerificationReport:
    """Run Layer 2 dynamic RBAC verification against a live server.

    This is a stub — the full server lifecycle + HTTP probing implementation
    is deferred to a follow-up task.  Returns a placeholder report with zero
    cells so that callers can handle the result type consistently.
    """
    import importlib.metadata
    from datetime import UTC, datetime

    try:
        version = importlib.metadata.version("dazzle-dsl")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    return VerificationReport(
        app_name=str(project_root),
        timestamp=datetime.now(UTC).isoformat(),
        dazzle_version=version,
        matrix=None,
        cells=[],
        total=0,
        passed=0,
        violated=0,
        warnings=0,
    )
