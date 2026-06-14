"""RBAC verifier harness — private infrastructure for Layer-2 dynamic verification.

Contains the database helpers, app-boot context, role seeding, baseline seeding,
and per-cell probing logic.  This module is only imported at verify()-call time
(lazy httpx/psycopg dependencies); it is **not** imported on every ``dazzle``
CLI invocation.

Public re-exports live in ``dazzle.rbac.verifier``; callers should import from
there, not directly from this module.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from dazzle.core.strings import to_api_plural
from dazzle.rbac.matrix import AccessMatrix, PolicyDecision
from dazzle.rbac.verification_types import (
    CellResult,
    VerifiedCell,
    VerifiedFlow,
    compare_cell,
    compare_flow,
)

if TYPE_CHECKING:
    import httpx

    from dazzle.back.runtime.auth.store import AuthStore
    from dazzle.back.runtime.server import DazzleBackendApp
    from dazzle.core.ir import AppSpec

_logger = logging.getLogger(__name__)


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
    transport: Any = field(default=None)
    """The ``httpx.ASGITransport`` used by ``client``.

    Exposed as a public field so callers can pass it to ``_probe_transport``
    without reaching into the private ``client._transport`` attribute.
    """


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
            yield _VerifierContext(
                appspec=built.appspec,
                client=client,
                auth_store=auth_store,
                transport=transport,
            )
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
    for fld in entity.fields:
        if not fld.is_required:
            continue
        if fld.is_primary_key:
            continue
        kind = fld.type.kind
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
            ref_entity = fld.type.ref_entity
            ref_id = baseline.get(ref_entity) if ref_entity else None
            if ref_id is None:
                # Required FK with no seeded target — entity is unseedable.
                return None
            body[fld.name] = ref_id
        elif kind in (FieldTypeKind.STR, FieldTypeKind.TEXT, FieldTypeKind.EMAIL):
            # Unique fields get the suffix so a probe never collides with the
            # baseline row on a unique constraint (a 422 that hides the verdict).
            suffix = unique_suffix if fld.is_unique else ""
            body[fld.name] = f"seed-{fld.name}{suffix}"
        elif kind == FieldTypeKind.INT:
            body[fld.name] = 1
        elif kind == FieldTypeKind.DECIMAL:
            body[fld.name] = "1.00"
        elif kind == FieldTypeKind.FLOAT:
            body[fld.name] = 1.0
        elif kind == FieldTypeKind.MONEY:
            body[fld.name] = "1.00"
        elif kind == FieldTypeKind.BOOL:
            body[fld.name] = False
        elif kind == FieldTypeKind.DATE:
            body[fld.name] = "2000-01-01"
        elif kind == FieldTypeKind.DATETIME:
            body[fld.name] = "2000-01-01T00:00:00Z"
        elif kind == FieldTypeKind.UUID:
            body[fld.name] = "00000000-0000-0000-0000-000000000001"
        elif kind == FieldTypeKind.ENUM:
            values = fld.type.enum_values
            body[fld.name] = values[0] if values else ""
        elif kind in (FieldTypeKind.URL, FieldTypeKind.FILE):
            body[fld.name] = "https://example.com/seed"
        elif kind == FieldTypeKind.TIMEZONE:
            body[fld.name] = "UTC"
        elif kind == FieldTypeKind.JSON:
            body[fld.name] = {}
        else:
            body[fld.name] = ""
    return body


def _scope_create_overlay(
    entity_name: str,
    appspec: Any,
    *,
    role: str,
    user_email: str,
    user_id: str | None,
) -> dict[str, Any]:
    """Return create-body field values that satisfy the entity's `scope: create:` rule.

    A `scope: create:` predicate (#1124) is checked against the *inserted row*
    AFTER framework defaulting — so for a `PERMIT_SCOPED` create the request
    body must carry the values the predicate requires (e.g. FeedbackReport's
    ``reported_by = current_user.email``).  A real client supplies them: the
    feedback widget posts ``reported_by`` explicitly.  `_minimal_body_for_entity`
    only emits *required* fields, so a scope-referenced field that is optional
    (FeedbackReport's ``reported_by`` is ``str(200)`` with no ``required``
    modifier) is omitted, the predicate sees ``None``, and the create 403s —
    a false VIOLATION against a correct-by-design app.

    This walks the create-scope rule matching ``role`` and resolves the
    equality constraints it can satisfy from the probing role-user's identity:

    * ``field = current_user.email``       → the role-user's email
    * ``field = current_user.id`` (bare)   → the role-user's auth id
    * ``field = <literal>``                → the literal

    Constraints referencing a domain attribute the verifier cannot resolve
    (e.g. ``current_user.org`` — needs a seeded domain ``User`` row) are
    skipped; the cell then stays a WARNING rather than being silently passed.
    Only equality (`EQ`) constraints are overlaid — an inequality cannot be
    satisfied by a single deterministic value.
    """
    from dazzle.core.ir.predicates import (
        BoolComposite,
        BoolOp,
        ColumnCheck,
        CompOp,
        PathCheck,
        UserAttrCheck,
    )

    entity = next(
        (e for e in (appspec.domain.entities or []) if e.name == entity_name),
        None,
    )
    if entity is None:
        return {}
    access = getattr(entity, "access", None)
    scopes = getattr(access, "scopes", None) or []

    # Find the create-scope rule that matches this role (`*` or an explicit
    # persona list). The runtime ORs all matched rules; the verifier only
    # needs *one* satisfiable rule, so the first match is enough.
    rule = None
    for r in scopes:
        op = r.operation.value if hasattr(r.operation, "value") else str(r.operation)
        if op != "create":
            continue
        personas = list(getattr(r, "personas", []) or [])
        if "*" in personas or role in personas:
            rule = r
            break
    if rule is None:
        return {}

    predicate = getattr(rule, "predicate", None)
    if predicate is None:
        return {}

    overlay: dict[str, Any] = {}

    def _resolve_user_attr(attr: str) -> Any:
        if attr in ("id", ""):
            return user_id
        if attr == "email":
            return user_email
        # Any other attribute (org, school, ...) needs a seeded domain row —
        # not available for a generic probe. Leave the field unset.
        return None

    def _walk(p: Any) -> None:
        if isinstance(p, UserAttrCheck) and p.op == CompOp.EQ:
            value = _resolve_user_attr(p.user_attr)
            if value is not None:
                overlay[p.field] = value
        elif isinstance(p, ColumnCheck) and p.op == CompOp.EQ:
            value_ref = p.value
            attr_name: str | None = getattr(value_ref, "user_attr", None)
            if getattr(value_ref, "current_user", False):
                if user_id is not None:
                    overlay[p.field] = user_id
            elif getattr(value_ref, "current_tenant", False):
                # #1394: `field = current_tenant` binds the host-resolved tenant,
                # which a generic in-process probe can't simulate (it would need a
                # `<slug>.host` request so TenantResolutionMiddleware sets the host
                # tenant context). Intentionally NOT overlaid: the cell stays a
                # truthful WARNING ("unverified") rather than a misleading PASS/FAIL.
                # Full current_tenant cell verification is a follow-up.
                pass
            elif attr_name:
                value = _resolve_user_attr(attr_name)
                if value is not None:
                    overlay[p.field] = value
            elif getattr(value_ref, "literal", None) is not None:
                overlay[p.field] = value_ref.literal
        elif isinstance(p, PathCheck) and p.op == CompOp.EQ and len(p.path) == 1:
            value_ref = p.value
            attr_name = getattr(value_ref, "user_attr", None)
            if attr_name:
                value = _resolve_user_attr(attr_name)
                if value is not None:
                    overlay[p.path[0]] = value
            elif getattr(value_ref, "current_user", False):
                if user_id is not None:
                    overlay[p.path[0]] = user_id
            elif getattr(value_ref, "literal", None) is not None:
                overlay[p.path[0]] = value_ref.literal
        elif isinstance(p, BoolComposite) and p.op == BoolOp.AND:
            # AND: every child must hold — overlay each one.
            for child in p.children:
                _walk(child)
        # OR / NOT and unsupported shapes: skip — no single deterministic
        # overlay satisfies them; the cell stays a WARNING.

    _walk(predicate)
    return overlay


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
    # Lazy import is intentional: httpx is only ever needed at verify() time,
    # and this module is imported on every `dazzle` CLI invocation (e.g. for
    # the type/report classes). Keeping httpx off the module-load path mirrors
    # the lazy-import pattern used throughout the rest of this module.
    import httpx

    return httpx.ASGITransport(app=ctx_transport.app, raise_app_exceptions=False)


@asynccontextmanager
async def _open_role_client(
    transport: Any,
    base_url: str,
    email: str,
    password: str,
) -> AsyncIterator[Any]:
    """Yield an authenticated `httpx.AsyncClient` for one role user.

    Single source of truth for the verifier's per-role client setup —
    `_seed_baseline_rows` and `_probe_all_cells` both use it, so the client
    construction (transport, base_url, follow_redirects) and the `_login`
    round-trip can never drift between the two call sites.  The client is
    closed when the context exits; a failed `_login` propagates after the
    client is closed so callers can record the role as unverifiable.
    """
    import httpx

    from dazzle.cli.rbac import _login

    client = httpx.AsyncClient(
        transport=transport,
        base_url=base_url,
        follow_redirects=True,
    )
    try:
        await _login(client, base_url, email, password)
    except Exception:
        await client.aclose()
        raise
    try:
        yield client
    finally:
        await client.aclose()


def _create_capable_role(matrix: AccessMatrix, entity: str) -> str | None:
    """Return a role that holds a `create` PERMIT for *entity*, or None.

    The bootstrap superuser is created with ``roles=[]`` so every project
    whose entities carry a `permit: create:` role gate (or a `scope: create:`
    rule) rejects it with 403.  Baseline rows are test scaffolding, not a
    probe — they must be inserted by a client that genuinely satisfies the
    create gate.  This picks the first role from the static matrix whose
    decision for ``(role, entity, "create")`` is any PERMIT* variant, so the
    baseline POST goes through the same gate a real authorised user would.

    Roles are iterated in ``matrix.roles`` order, which preserves the
    persona-declaration order from the DSL.  "First capable role" is therefore
    deterministic, but declaration-order-dependent: reordering personas in the
    DSL can change which role seeds a given entity (the seeded row is
    equivalent either way, so this only matters for reproducing a specific
    run).

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
    from contextlib import AsyncExitStack

    baseline: dict[str, str] = {}
    # Role clients are opened lazily and cached for the duration of the call;
    # the AsyncExitStack closes every one when this function returns. A role
    # whose `_login` fails is recorded as `None` so it is not retried per
    # entity — _probe_all_cells records the per-cell WARNING for it separately.
    role_clients: dict[str, Any] = {}
    async with AsyncExitStack() as stack:
        for entity in entities:
            role = _create_capable_role(matrix, entity)
            if role is None or role not in creds:
                # No role can create this entity — legitimately un-seedable.
                continue
            body = _minimal_body_for_entity(entity, appspec, baseline=baseline)
            if body is None:
                # Required FK with no seeded target — skip this entity.
                continue
            # Satisfy any `scope: create:` predicate on the seeding role —
            # `_create_capable_role` may pick a role whose create is
            # `PERMIT_SCOPED` (e.g. FeedbackReport's `reported_by =
            # current_user.email`), and a body that omits the scoped field
            # would 403 and leave the entity un-seeded. Same overlay a real
            # client supplies. See `_scope_create_overlay`.
            body.update(
                _scope_create_overlay(
                    entity,
                    appspec,
                    role=role,
                    user_email=creds[role][0],
                    user_id=None,
                )
            )

            if role not in role_clients:
                try:
                    role_clients[role] = await stack.enter_async_context(
                        _open_role_client(transport, base_url, *creds[role])
                    )
                except Exception:
                    # Role user cannot authenticate — mark unverifiable so it
                    # is not retried for the next entity owned by this role.
                    role_clients[role] = None
            client = role_clients[role]
            if client is None:
                continue

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
    from contextlib import AsyncExitStack

    from dazzle.rbac.audit import InMemoryAuditSink, NullAuditSink, set_audit_sink

    cells: list[VerifiedCell] = []
    base_url = "http://verifier.local"

    # Map each role to its seeded auth-user id so `_scope_create_overlay` can
    # satisfy a `scope: create:` predicate that references bare `current_user`
    # / `current_user.id`. Resolved once up front from the auth store.
    _role_auth_ids: dict[str, str | None] = {}
    if ctx.auth_store is not None:
        for _role, (_email, _) in creds.items():
            _rec = ctx.auth_store.get_user_by_email(_email)
            _role_auth_ids[_role] = str(_rec.id) if _rec is not None else None

    for role in matrix.roles:
        if role not in creds:
            continue
        email, password = creds[role]
        # `_open_role_client` raises if `_login` fails; an AsyncExitStack lets
        # the failure be caught here (to emit per-cell WARNINGs) while still
        # closing the client deterministically on the success path.
        async with AsyncExitStack() as stack:
            try:
                client = await stack.enter_async_context(
                    _open_role_client(transport, base_url, email, password)
                )
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
                        # masking the verdict.
                        #
                        # Only `create` gets a unique suffix: it inserts a new
                        # row, so a `unique` field must not collide with the
                        # baseline row. `update` is a PUT against the baseline
                        # row itself — the value replaces itself, so there is
                        # no unique-constraint collision and no suffix needed.
                        body: dict[str, Any] | None = None
                        if operation in ("create", "update"):
                            suffix = f"-{role}-{operation}" if operation == "create" else ""
                            body = _minimal_body_for_entity(
                                entity,
                                ctx.appspec,
                                baseline=baseline,
                                unique_suffix=suffix,
                            )
                            # A `PERMIT_SCOPED` create checks the inserted row
                            # against the entity's `scope: create:` predicate
                            # (#1124). A scope-referenced field that is optional
                            # is omitted by `_minimal_body_for_entity`, so the
                            # predicate sees `None` and the create 403s — a
                            # false VIOLATION. Overlay the values the predicate
                            # requires (e.g. `reported_by = current_user.email`),
                            # exactly as a real client would supply them.
                            if operation == "create" and body is not None:
                                overlay = _scope_create_overlay(
                                    entity,
                                    ctx.appspec,
                                    role=role,
                                    user_email=email,
                                    user_id=_role_auth_ids.get(role),
                                )
                                body.update(overlay)
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


def _minimal_flow_inputs(
    flow_name: str,
    appspec: Any,
    *,
    baseline: dict[str, str],
) -> dict[str, Any]:
    """Build the smallest valid JSON body for an atomic flow's ``inputs:`` block.

    Mirrors ``build_input_model``'s ``_TYPE_MAP`` so every value passes the
    auto-generated Pydantic model (a 422 would mask the permit-gate verdict).
    A ``ref`` input resolves against the seeded ``baseline`` row id for its
    target entity; with no seeded target it falls back to a syntactically-valid
    placeholder UUID — enough to clear body validation so the role gate (which
    fires before any scope/FK check) is observable.
    """
    from dazzle.core.ir.fields import FieldTypeKind

    flow = next((f for f in (appspec.atomic_flows or []) if f.name == flow_name), None)
    if flow is None:
        return {}

    _placeholder_uuid = "00000000-0000-0000-0000-000000000001"
    body: dict[str, Any] = {}
    for inp in flow.inputs:
        kind = inp.type.kind
        if kind == FieldTypeKind.REF:
            ref_entity = inp.type.ref_entity
            body[inp.name] = (baseline.get(ref_entity) if ref_entity else None) or _placeholder_uuid
        elif kind == FieldTypeKind.UUID:
            body[inp.name] = _placeholder_uuid
        elif kind == FieldTypeKind.INT:
            body[inp.name] = 1
        elif kind == FieldTypeKind.MONEY:
            body[inp.name] = 1  # _TYPE_MAP: MONEY → int (minor units)
        elif kind in (FieldTypeKind.FLOAT, FieldTypeKind.DECIMAL):
            body[inp.name] = 1.0
        elif kind == FieldTypeKind.BOOL:
            body[inp.name] = False
        elif kind == FieldTypeKind.DATE:
            body[inp.name] = "2000-01-01"
        elif kind == FieldTypeKind.DATETIME:
            body[inp.name] = "2000-01-01T00:00:00Z"
        else:
            # STR/TEXT/EMAIL/URL/SLUG/TIMEZONE and any unmapped kind → str.
            body[inp.name] = f"seed-{inp.name}"
    return body


def _is_role_gate_403(response: Any) -> bool:
    """True when a 403 came from the atomic flow's *role* gate, not scope.

    The permit-gate rejection in ``atomic_flow_routes._make_handler`` carries a
    detail of the form ``"Atomic flow '<name>' requires one of [...]; user has
    [...]."``. A per-step ``scope:`` denial raises a 403 with a different body,
    so the marker substring distinguishes the two.

    A decode failure on ``response.text`` propagates to ``_probe_atomic_flows``'s
    probe ``try/except`` (recorded as a WARNING) rather than being swallowed here.
    """
    return "requires one of" in response.text


async def _probe_atomic_flows(
    matrix: AccessMatrix,
    creds: dict[str, tuple[str, str]],
    baseline: dict[str, str],
    *,
    transport: Any,
    appspec: Any,
) -> list[VerifiedFlow]:
    """Probe ``POST /api/atomic/<name>`` per (flow, role); verify the permit gate.

    For each projected atomic flow (``matrix.atomic_flows``) and each role, POST
    the flow with a minimal valid body and check the ``permit: execute`` gate: a
    non-permitted role must be rejected (403 from the role gate), a permitted
    role must clear it. Per-step scope correctness is integration-tested
    separately (see ``VerifiedFlow`` / ``compare_flow``).
    """
    from contextlib import AsyncExitStack

    flows_out: list[VerifiedFlow] = []
    if not matrix.atomic_flows:
        return flows_out

    base_url = "http://verifier.local"
    for role in matrix.roles:
        if role not in creds:
            continue
        email, password = creds[role]
        async with AsyncExitStack() as stack:
            try:
                client = await stack.enter_async_context(
                    _open_role_client(transport, base_url, email, password)
                )
            except Exception as exc:
                for proj in matrix.atomic_flows:
                    expected = PolicyDecision.PERMIT if role in proj.roles else PolicyDecision.DENY
                    flows_out.append(
                        VerifiedFlow(
                            flow=proj.name,
                            role=role,
                            expected=expected,
                            observed_status=0,
                            result=CellResult.WARNING,
                            detail=f"role login failed: {exc}",
                        )
                    )
                continue

            for proj in matrix.atomic_flows:
                expected = PolicyDecision.PERMIT if role in proj.roles else PolicyDecision.DENY
                body = _minimal_flow_inputs(proj.name, appspec, baseline=baseline)
                try:
                    resp = await client.request(
                        "POST",
                        f"/api/atomic/{proj.name}",
                        json=body,
                        headers=_csrf_headers(client),
                    )
                    status = resp.status_code
                    role_gate_rejected = status == 403 and _is_role_gate_403(resp)
                    result = compare_flow(expected, status, role_gate_rejected=role_gate_rejected)
                    detail = ""
                except Exception as exc:
                    status = 0
                    result = CellResult.WARNING
                    detail = f"probe error: {exc}"
                flows_out.append(
                    VerifiedFlow(
                        flow=proj.name,
                        role=role,
                        expected=expected,
                        observed_status=status,
                        result=result,
                        detail=detail,
                    )
                )
    return flows_out
