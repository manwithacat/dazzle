"""RBAC verifier — Layer 2 of the RBAC verification framework.

Provides types for representing verification results, the core `compare_cell()`
comparison function, and `VerificationReport` with JSON serialisation.

The full `verify()` async function (which starts a live server and probes
endpoints) is stubbed here. The types and comparison logic are the critical
pieces for unit testing.
"""

from __future__ import annotations  # required: forward reference

import json
import logging
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

_logger = logging.getLogger(__name__)


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
    error: str | None = None
    """Boot/provisioning failure message, or None on a successful run.

    A zeroed report (total=0) with `error` set means verification could
    not run — distinct from a clean run of an app with no cells.
    """

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
            "error": self.error,
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
            error=raw.get("error"),
        )


def compare_cell(
    expected: PolicyDecision,
    observed_status: int,
    observed_count: int | None,
    *,
    total: int | None = None,
    operation: str | None = None,
) -> CellResult:
    """Compare an observed HTTP response against an expected policy decision.

    Comparison table
    ----------------
    DENY               + 403                           → PASS
    DENY               + 200                           → VIOLATION
    PERMIT             + 200                            → PASS
    PERMIT             + 403                            → VIOLATION
    PERMIT_SCOPED      + 200                            → PASS
    PERMIT_SCOPED      + 403                            → VIOLATION
    PERMIT_SCOPED      + 404 on a single-id op          → PASS  (scoped out)
    PERMIT_NO_SCOPE    + 403                            → VIOLATION
    PERMIT_NO_SCOPE    + 200/404                        → WARNING (config gap)
    PERMIT_FILTERED    + 200 + 0 < count < total        → PASS
    PERMIT_FILTERED    + 200 + count == total           → VIOLATION  (unfiltered)
    PERMIT_FILTERED    + 200 + count == 0               → WARNING
    PERMIT_UNPROTECTED + 200                            → PASS
    PERMIT_UNPROTECTED + 403                            → VIOLATION

    Any (expected, observed) combination not explicitly listed above
    is treated as WARNING.

    ``operation`` is the matrix operation name (``read``/``update``/``delete``/
    ``list``/``create``).  It only matters for ``PERMIT_SCOPED``: a 404 on a
    single-id op means the scope filter legitimately hid the baseline row from
    a role that does not own it — that is *correct* RBAC behaviour, so it
    counts as PASS rather than an inconclusive WARNING.
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

    if expected == PolicyDecision.PERMIT_SCOPED:
        # Access is granted by `permit:` and rows are scoped by a `scope:`
        # rule. A 403 contradicts the grant. A 200 confirms it. A 404 on a
        # single-id op (read/update/delete) is the scope filter correctly
        # hiding a row the role does not own — definitively correct, PASS.
        if observed_status == 200:
            return CellResult.PASS
        if observed_status == 403:
            return CellResult.VIOLATION
        if observed_status == 404 and operation in ("read", "update", "delete"):
            return CellResult.PASS
        return CellResult.WARNING

    if expected == PolicyDecision.PERMIT_NO_SCOPE:
        # `permit:` grants access but no matching `scope:` rule exists — the
        # role sees 0 rows. The matrix already flags this as a config gap; the
        # only definitive verdict the verifier can add is that a 403 still
        # contradicts the permit grant.
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
#
# `update` is PUT, not PATCH: the generated entity CRUD router
# (`route_generator.py`) mounts the full-row update at ``PUT /<plural>/<id>``.
# The only PATCH route is ``/<plural>/<id>/field/<name>`` (inline single-field
# edit), so probing ``PATCH /<plural>/<id>`` would always 405 and reduce every
# update cell to an inconclusive WARNING.
_PROBE_VERBS: dict[str, tuple[str, bool, bool]] = {
    "list": ("GET", False, False),
    "read": ("GET", True, False),
    "create": ("POST", False, True),
    "update": ("PUT", True, True),
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

    The generated entity CRUD routes are mounted at ``/<plural>`` and
    ``/<plural>/<id>`` (no ``/api`` prefix — see `RouteGenerator` /
    `route_generator.py`). The mutating verbs (POST/PATCH/DELETE) pass
    through the double-submit CSRF middleware, so this echoes the client's
    `dazzle_csrf` cookie back as the X-CSRF-Token header for those verbs.
    """
    method, needs_id, has_body = _PROBE_VERBS[operation]
    plural = to_api_plural(entity)
    url = f"/{plural}/{baseline_id}" if needs_id else f"/{plural}"

    kwargs: dict[str, Any] = {}
    if has_body:
        kwargs["json"] = body or {}
    # Every state-changing verb (POST/PUT/PATCH/DELETE) passes through the
    # double-submit CSRF middleware; only GET/HEAD are exempt. `update` is
    # PUT, so it MUST carry the token — omitting it 403s before the RBAC
    # gate runs, masking the verdict as a false VIOLATION.
    if method not in ("GET", "HEAD"):
        kwargs["headers"] = _csrf_headers(client)

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


def _minimal_body_for_entity(
    entity_name: str,
    appspec: Any,
    *,
    baseline: dict[str, str] | None = None,
    unique_suffix: str = "",
) -> dict[str, Any] | None:
    """Build the smallest valid JSON body for creating an entity row.

    Iterates the entity's required non-PK fields and emits a representative
    value for each field type.  A required ``ref`` field is resolved against
    ``baseline`` (the already-seeded row id for the target entity).  If a
    required ref has no seeded target, the entity cannot be created — this
    function returns ``None`` and the caller omits the entity.

    ``unique_suffix`` is appended to every ``unique`` string/email field so a
    create *probe* does not collide with the baseline row's value (a unique
    constraint hit returns 422, which would mask the real RBAC verdict).
    Pass an empty suffix for the one-off baseline seed.
    """
    from dazzle.core.ir.fields import FieldTypeKind

    baseline = baseline or {}
    entity = next(
        (e for e in (appspec.domain.entities or []) if e.name == entity_name),
        None,
    )
    if entity is None:
        return None

    body: dict[str, Any] = {}
    for field in entity.fields:
        if not field.is_required:
            continue
        if field.is_primary_key:
            continue
        kind = field.type.kind
        if kind in (
            FieldTypeKind.HAS_MANY,
            FieldTypeKind.HAS_ONE,
            FieldTypeKind.EMBEDS,
            FieldTypeKind.BELONGS_TO,
        ):
            # Relationship fields are not required in DSL practice — they
            # are populated via FK columns, not the create body. Skip.
            continue
        if kind == FieldTypeKind.REF:
            ref_entity = field.type.ref_entity
            ref_id = baseline.get(ref_entity) if ref_entity else None
            if ref_id is None:
                # Required FK with no seeded target — entity is unseedable.
                return None
            body[field.name] = ref_id
        elif kind in (FieldTypeKind.STR, FieldTypeKind.TEXT, FieldTypeKind.EMAIL):
            # Unique fields get the suffix so a probe never collides with the
            # baseline row on a unique constraint (a 422 that hides the verdict).
            suffix = unique_suffix if field.is_unique else ""
            body[field.name] = f"seed-{field.name}{suffix}"
        elif kind == FieldTypeKind.INT:
            body[field.name] = 1
        elif kind == FieldTypeKind.DECIMAL:
            body[field.name] = "1.00"
        elif kind == FieldTypeKind.FLOAT:
            body[field.name] = 1.0
        elif kind == FieldTypeKind.MONEY:
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
        elif kind in (FieldTypeKind.URL, FieldTypeKind.FILE):
            body[field.name] = "https://example.com/seed"
        elif kind == FieldTypeKind.TIMEZONE:
            body[field.name] = "UTC"
        elif kind == FieldTypeKind.JSON:
            body[field.name] = {}
        else:
            body[field.name] = ""
    return body


# CSRF cookie name set by the framework's double-submit middleware
# (`dazzle.back.runtime.csrf.CSRFConfig`).  State-changing requests must
# echo this cookie value back in the X-CSRF-Token header.
_CSRF_COOKIE = "dazzle_csrf"
_CSRF_HEADER = "X-CSRF-Token"


def _csrf_headers(client: Any) -> dict[str, str]:
    """Return the X-CSRF-Token header for `client` if it carries the cookie.

    The framework's CSRF middleware issues the `dazzle_csrf` cookie on the
    first non-Bearer response; once the verifier client has made any GET
    (e.g. the bootstrap `/auth/login` round-trip) the cookie is in its jar.
    """
    token = client.cookies.get(_CSRF_COOKIE)
    return {_CSRF_HEADER: token} if token else {}


def _probe_transport(ctx_transport: Any) -> Any:
    """Return an ``ASGITransport`` for the booted app that surfaces server
    errors as HTTP responses instead of re-raising them.

    `httpx.ASGITransport` defaults to ``raise_app_exceptions=True``, so an
    unhandled 500 inside a route propagates as a Python exception and aborts
    the whole probe.  A delete blocked by a foreign-key constraint, for
    example, is a *data-integrity* outcome — not an RBAC verdict — and must
    not crash verification.  This rebuilds the transport pointed at the same
    in-process app with ``raise_app_exceptions=False`` so the probe observes a
    500 status and records a WARNING for that one cell.
    """
    import httpx

    return httpx.ASGITransport(app=ctx_transport.app, raise_app_exceptions=False)


def _create_capable_role(matrix: AccessMatrix, entity: str) -> str | None:
    """Return a role that holds a `create` PERMIT for *entity*, or None.

    The bootstrap superuser is created with ``roles=[]`` so every project
    whose entities carry a `permit: create:` role gate (or a `scope: create:`
    rule) rejects it with 403.  Baseline rows are test scaffolding, not a
    probe — they must be inserted by a client that genuinely satisfies the
    create gate.  This picks the first role from the static matrix whose
    decision for ``(role, entity, "create")`` is any PERMIT* variant, so the
    baseline POST goes through the same gate a real authorised user would.

    Returns None when no role can create the entity (e.g. framework/admin
    entities exposed read-only) — such entities are legitimately un-seedable
    and their read/update/delete cells stay WARNING.
    """
    for role in matrix.roles:
        if matrix.get(role, entity, "create").value.startswith("PERMIT"):
            return role
    return None


async def _seed_baseline_rows(
    *,
    transport: Any,
    base_url: str,
    matrix: AccessMatrix,
    creds: dict[str, tuple[str, str]],
    entities: list[str],
    appspec: Any,
) -> dict[str, str]:
    """Create one baseline row per entity via a create-capable role-user.

    Returns {entity: row_id}. The generated CRUD routes are mounted at
    ``/<plural>`` (no ``/api`` prefix) and POST is CSRF-protected, so this
    echoes each role client's `dazzle_csrf` cookie back as the X-CSRF-Token
    header.

    Each entity is seeded by a role-user whose role holds a `create` PERMIT
    in the static matrix — *not* the bootstrap superuser, which carries
    ``roles=[]`` and is rejected by every `permit: create:` role gate and
    every `scope: create:` rule (403).  Role clients are opened lazily and
    cached for the duration of the call; all ride the same in-process
    ``ASGITransport`` as the verifier context so the seeded rows land in the
    booted scratch database.

    Entities are seeded in the given order; a required ``ref`` field is
    resolved against rows already seeded earlier in the list, so callers
    should pass referenced entities before their dependents.  Any entity
    whose create fails (no create-capable role, no POST route, missing FK,
    validation error) is omitted so callers can continue with the entities
    that did seed.
    """
    import httpx

    from dazzle.cli.rbac import _login

    baseline: dict[str, str] = {}
    role_clients: dict[str, httpx.AsyncClient] = {}
    try:
        for entity in entities:
            role = _create_capable_role(matrix, entity)
            if role is None or role not in creds:
                # No role can create this entity — legitimately un-seedable.
                continue
            body = _minimal_body_for_entity(entity, appspec, baseline=baseline)
            if body is None:
                # Required FK with no seeded target — skip this entity.
                continue

            client = role_clients.get(role)
            if client is None:
                client = httpx.AsyncClient(
                    transport=transport,
                    base_url=base_url,
                    follow_redirects=True,
                )
                try:
                    await _login(client, base_url, *creds[role])
                except Exception:
                    # Role user cannot authenticate — skip; _probe_all_cells
                    # records the per-cell WARNING for this role separately.
                    await client.aclose()
                    continue
                role_clients[role] = client

            plural = to_api_plural(entity)
            resp = await client.request(
                "POST",
                f"/{plural}",
                json=body,
                headers=_csrf_headers(client),
            )
            if resp.status_code in (200, 201):
                try:
                    row_id = resp.json().get("id")
                except Exception:
                    row_id = None
                if row_id:
                    baseline[entity] = str(row_id)
    finally:
        for client in role_clients.values():
            await client.aclose()
    return baseline


async def _probe_all_cells(
    ctx: _VerifierContext,
    matrix: AccessMatrix,
    creds: dict[str, tuple[str, str]],
    baseline: dict[str, str],
    *,
    transport: Any,
) -> list[VerifiedCell]:
    """Open one authenticated client per role; probe every matrix cell.

    Reuses the app already booted by `_verifier_app_context` — the seeded
    role users and baseline rows live in *that* boot's scratch database, so
    every role client must ride a transport over the same in-process app.
    Re-booting the app would point at a fresh, empty database and lose the
    fixtures.  `transport` is the lenient (`raise_app_exceptions=False`)
    transport built by `_probe_transport`, so a server-side 500 surfaces as a
    status code rather than aborting the run.

    Per-cell probe failures are caught here and recorded as WARNING — only
    an app-boot failure (which happens before this is called) yields an
    empty report.
    """
    import httpx

    from dazzle.cli.rbac import _login
    from dazzle.rbac.audit import InMemoryAuditSink, NullAuditSink, set_audit_sink

    cells: list[VerifiedCell] = []
    base_url = "http://verifier.local"

    for role in matrix.roles:
        if role not in creds:
            continue
        email, password = creds[role]
        async with httpx.AsyncClient(
            transport=transport,
            base_url=base_url,
            follow_redirects=True,
        ) as client:
            try:
                await _login(client, base_url, email, password)
            except Exception as exc:
                # The role user cannot authenticate — every cell for this
                # role is unverifiable. Record one WARNING per cell.
                for entity in matrix.entities:
                    for operation in matrix.operations:
                        expected = matrix.get(role, entity, operation)
                        cells.append(
                            VerifiedCell(
                                role=role,
                                entity=entity,
                                operation=operation,
                                expected=expected,
                                observed_status=0,
                                observed_count=None,
                                result=CellResult.WARNING,
                                audit_records=[],
                                detail=f"role login failed: {exc}",
                            )
                        )
                continue

            for entity in matrix.entities:
                for operation in matrix.operations:
                    expected = matrix.get(role, entity, operation)
                    # Each cell installs its own sink and resets it in the
                    # finally so a probe failure can't leak the sink into the
                    # next cell. verify()'s outer finally is the backstop.
                    sink = InMemoryAuditSink()
                    set_audit_sink(sink)
                    try:
                        # create/update are body-bearing verbs — without a
                        # valid body the request 422s on required-field
                        # validation before the RBAC gate is even reached,
                        # masking the verdict. create uses a per-cell unique
                        # suffix so a `unique` field never collides with the
                        # baseline row.
                        body: dict[str, Any] | None = None
                        if operation in ("create", "update"):
                            suffix = f"-{role}-{operation}" if operation == "create" else ""
                            body = _minimal_body_for_entity(
                                entity,
                                ctx.appspec,
                                baseline=baseline,
                                unique_suffix=suffix,
                            )
                        probe = await _probe_cell(
                            client,
                            entity=entity,
                            operation=operation,
                            baseline_id=baseline.get(entity),
                            body=body,
                        )
                        result = compare_cell(
                            expected, probe.status, probe.count, operation=operation
                        )
                        detail = ""
                    except Exception as exc:
                        probe = _ProbeResult(status=0, count=None)
                        result = CellResult.WARNING
                        detail = f"probe error: {exc}"
                    finally:
                        set_audit_sink(NullAuditSink())
                    cells.append(
                        VerifiedCell(
                            role=role,
                            entity=entity,
                            operation=operation,
                            expected=expected,
                            observed_status=probe.status,
                            observed_count=probe.count,
                            result=result,
                            audit_records=list(sink.records),
                            detail=detail,
                        )
                    )
    return cells


async def verify(
    project_root: Path,
    *,
    server_database_url: str | None = None,
) -> VerificationReport:
    """Run Layer-2 dynamic RBAC verification.

    Provisions a disposable database, boots the app in-process, probes
    every (role, entity, operation) matrix cell as the relevant role, and
    compares observed behaviour against the static matrix.
    """
    import importlib.metadata
    import os
    from datetime import UTC, datetime

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.rbac.audit import NullAuditSink, set_audit_sink
    from dazzle.rbac.matrix import generate_access_matrix

    try:
        version = importlib.metadata.version("dazzle-dsl")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    now = datetime.now(UTC).isoformat()

    server_url = server_database_url or os.environ.get("DATABASE_URL")
    if not server_url:
        raise RuntimeError(
            "dynamic RBAC verification requires a PostgreSQL server — set "
            "DATABASE_URL (the verifier creates and drops its own scratch DB)."
        )

    appspec = load_project_appspec(project_root)
    matrix = generate_access_matrix(appspec)

    cells: list[VerifiedCell] = []
    try:
        async with _DisposableDatabase(server_url) as db_url:
            async with _verifier_app_context(project_root, db_url) as ctx:
                creds = await _seed_role_users(ctx.auth_store, roles=list(matrix.roles))
                # All probe/seed clients ride a transport over the same booted
                # app, but with raise_app_exceptions=False so a server-side 500
                # surfaces as a status code instead of crashing the run.
                transport = _probe_transport(ctx.client._transport)
                # Baseline rows are seeded by a create-capable role-user, not
                # the roles-less bootstrap superuser (which every create gate
                # rejects with 403).
                baseline = await _seed_baseline_rows(
                    transport=transport,
                    base_url="http://verifier.local",
                    matrix=matrix,
                    creds=creds,
                    entities=list(matrix.entities),
                    appspec=ctx.appspec,
                )
                cells = await _probe_all_cells(ctx, matrix, creds, baseline, transport=transport)
    except Exception as exc:
        # App-boot / database-provisioning failure — return an empty report
        # rather than raising, so callers can render a consistent result.
        # The `error` field disambiguates this from a clean run of an app
        # with zero cells: a zeroed report with `error` set means the
        # verifier could not run, not that everything passed.
        _logger.error("verify() boot failed: %s", exc, exc_info=True)
        return VerificationReport(
            app_name=str(project_root),
            timestamp=now,
            dazzle_version=version,
            matrix=matrix,
            cells=[],
            total=0,
            passed=0,
            violated=0,
            warnings=0,
            error=repr(exc),
        )
    finally:
        set_audit_sink(NullAuditSink())

    passed = sum(1 for c in cells if c.result == CellResult.PASS)
    violated = sum(1 for c in cells if c.result == CellResult.VIOLATION)
    warnings = sum(1 for c in cells if c.result == CellResult.WARNING)
    return VerificationReport(
        app_name=str(project_root),
        timestamp=now,
        dazzle_version=version,
        matrix=matrix,
        cells=cells,
        total=len(cells),
        passed=passed,
        violated=violated,
        warnings=warnings,
    )
