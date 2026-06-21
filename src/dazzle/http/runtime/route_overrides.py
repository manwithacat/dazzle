"""Route override discovery for project-level custom handlers (v0.29.0).

Scans project ``routes/`` for Python files with declaration headers
and loads custom FastAPI route handlers that replace generated routes.

Route override files use declaration headers::

    # dazzle:route-override GET /app/tasks/create
    from fastapi import Request
    from fastapi.responses import HTMLResponse

    async def handler(request: Request):
        return HTMLResponse("<h1>Custom Task Wizard</h1>")

When project routes are registered before generated routes,
FastAPI's first-match behavior ensures the project handler wins.
"""

import importlib.util
import inspect
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from dazzle.core import ir

logger = logging.getLogger(__name__)

# Declaration header pattern: # dazzle:route-override METHOD /path
_ROUTE_OVERRIDE_RE = re.compile(
    r"#\s*dazzle:route-override\s+(GET|POST|PUT|PATCH|DELETE)\s+(\S+)", re.IGNORECASE
)

# v0.71.24 (#1126) — declarative policy gate. Project overrides opt
# back into DSL permit/scope enforcement by naming the entity + op the
# handler logically implements, plus the path parameter that holds the
# target row's PK. The framework wraps the handler so permit/scope
# evaluation runs BEFORE dispatch. See `policy.check_entity_op` for
# the imperative form (body-shaped ops).
_IMPLEMENTS_RE = re.compile(
    r"#\s*dazzle:implements\s+([A-Za-z_][A-Za-z0-9_]*)\.([a-z]+)\s+via\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# #1392 item 3 — declared link/fetch targets a handler emits (one path per line).
# `verify_emits_paths` resolves each against the mounted route set; a dead target
# fails the build (the custom-mode analogue of `primary_action -> surface`).
_EMITS_RE = re.compile(r"#\s*dazzle:emits\s+(\S+)", re.IGNORECASE)

# #1392 item 2 — declared response shape. The kind ENCODES chrome: only `fragment` is
# shell-wrapped; `page` is a full document (novel/full-bleed UX, never refused);
# `partial` is raw HTML for a targeted HTMX swap; `json` is data. Drives
# `_wrap_with_response_contract`. None = undeclared (today's behaviour + advisory nudge).
_RETURNS_RE = re.compile(r"#\s*dazzle:returns\s+(\w+)", re.IGNORECASE)
_VALID_RETURN_KINDS = frozenset({"page", "fragment", "partial", "json"})

# Valid Python module path: dotted identifier segments only.
# Enforces that extension router specs from dazzle.toml resolve to
# real package paths and prevents injection via the config value.
_MODULE_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_ATTR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class RouteOverrideDescriptor:
    """Metadata about a discovered route override."""

    method: str  # HTTP method (GET, POST, PUT, PATCH, DELETE)
    path: str  # Route path (e.g. /app/tasks/create)
    source_path: Path
    handler: Callable[..., Any]
    # v0.71.24 (#1126) — declarative policy-gate annotation. When set,
    # the framework wraps `handler` so permit + scope evaluation runs
    # against the row at `kwargs[implements_via]` before dispatch.
    # All three are populated together or all None.
    implements_entity: str | None = None
    implements_op: str | None = None  # one of: list, read, create, update, delete
    implements_via: str | None = None  # path-param name holding the row's PK
    # #1392 item 3 — declared `# dazzle:emits <path>` link targets. Each must resolve
    # to a mounted route (verify_emits_paths). () = undeclared (opt-in).
    emits_paths: tuple[str, ...] = ()
    # #1392 item 2 — declared response shape (page|fragment|partial|json). Drives
    # `_wrap_with_response_contract` (kind encodes chrome). None = undeclared.
    returns_kind: str | None = None


def find_unbound_shadowing_overrides(
    overrides: list[RouteOverrideDescriptor],
    generated_paths: set[tuple[str, str]],
) -> list[str]:
    """#1420 Slice 3 / ADR-0040 D2 — conformance violations.

    A route-override that *shadows* a generated entity route (same ``(METHOD,
    path)``) but declares no ``# dazzle:implements`` binding silently replaces a
    permit/scope-bound generated route with an un-gated custom one. Return one
    human-readable violation string per such override; empty list = conformant.

    ``generated_paths`` is the set of ``(METHOD, path)`` the generated CRUD layer
    would mount (a domain route shape). An override that shadows one of these is
    by definition domain-touching, so it must carry the binding.
    """
    violations: list[str] = []
    for o in overrides:
        if o.implements_entity is not None:
            continue  # bound → conformant
        if (o.method.upper(), o.path) in generated_paths:
            violations.append(
                f"Route override {o.method.upper()} {o.path} ({o.source_path.name}) shadows a "
                "generated entity route but declares no `# dazzle:implements <Entity>.<op> via "
                "<param>` binding — it bypasses the entity's permit/scope model. Add the binding, "
                "or call dazzle.http.runtime.policy.check_entity_op(...) in the handler."
            )
    return violations


_VALID_CRUD_OPS = frozenset({"list", "read", "create", "update", "delete"})


def verify_emits_paths(
    overrides: list[RouteOverrideDescriptor], route_paths: set[str]
) -> list[str]:
    """#1392 item 3 — every ``# dazzle:emits <path>`` must match a mounted route.

    The route-override analogue of the surface ``emits:`` gate (and of
    ``primary_action -> surface``): a route-override declares the link/fetch targets
    its handler emits; an emitted path that matches no mounted route is a dead target.
    ``route_paths`` is the mounted-route set in template form (generated CRUD routes +
    route-override paths + page routes, e.g. ``/app/tasks/{id}``). Returns one
    ``E_DEAD_EMIT_TARGET`` violation string per unresolved path; empty = clean.
    """
    violations: list[str] = []
    for o in overrides:
        for path in o.emits_paths:
            if path not in route_paths:
                violations.append(
                    f"E_DEAD_EMIT_TARGET: route-override {o.path!r} emits {path!r}, which "
                    f"matches no mounted route."
                )
    return violations


def verify_route_matrix_completeness(
    appspec: ir.AppSpec,
    overrides: list[RouteOverrideDescriptor],
    generated_paths: set[tuple[str, str]],
) -> list[str]:
    """#1420 Slice 3 / ADR-0040 D3 — every domain route must be matrix-represented.

    The hard-gate form of the conformance check. Two ways a custom route escapes
    the RBAC matrix:

    1. **Unbound shadow** — an override that shadows a generated entity route but
       carries no ``# dazzle:implements`` binding (no ``(entity, op)`` → no matrix
       row). Reuses :func:`find_unbound_shadowing_overrides`.
    2. **Dangling binding** — an override whose ``# dazzle:implements`` names an
       entity that doesn't exist in the AppSpec, or an op outside the CRUD set.
       Its row points at nothing.

    Returns one violation string per offending override; ``[]`` means the route
    set is matrix-complete. A CLI gate (`dazzle rbac routes --strict`) exits
    non-zero when this is non-empty.
    """
    violations = list(find_unbound_shadowing_overrides(overrides, generated_paths))
    entity_names = {e.name for e in appspec.domain.entities}
    for o in overrides:
        if o.implements_entity is None:
            continue
        if o.implements_entity not in entity_names:
            violations.append(
                f"Route override {o.method.upper()} {o.path} ({o.source_path.name}) binds to "
                f"`# dazzle:implements {o.implements_entity}.{o.implements_op}` but entity "
                f"{o.implements_entity!r} does not exist in the AppSpec — dangling binding, no "
                "matrix row."
            )
        elif o.implements_op not in _VALID_CRUD_OPS:
            violations.append(
                f"Route override {o.method.upper()} {o.path} ({o.source_path.name}) binds to op "
                f"{o.implements_op!r}, which is not a CRUD op (list/read/create/update/delete) — "
                "no matrix row."
            )
    return violations


_RAW_DB_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\.execute\s*\(\s*['\"]?\s*(SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE),
        "raw SQL via .execute(...)",
    ),
    (re.compile(r"\bRepository\s*\("), "direct Repository(...) construction"),
    (re.compile(r"(?m)^\s*(import\s+psycopg|from\s+psycopg(\.\w+)?\s+import)\b"), "psycopg import"),
]


def scan_handler_for_raw_db(source: str) -> list[str]:
    """#1420 Slice 3 / ADR-0040 D4 — flag raw DB access in a custom route handler.

    A domain-touching custom handler must bind via the ``# dazzle:implements``
    header or call ``dazzle.http.runtime.policy.check_entity_op`` — not reach the
    database directly (raw SQL / a hand-built Repository), which escapes the
    declared binding and bypasses permit/scope. Returns one label per detected
    pattern; ``[]`` means the handler does not touch the DB directly. Backs the
    ``raw_db_in_custom_route`` counter-prior.
    """
    return [label for pat, label in _RAW_DB_PATTERNS if pat.search(source)]


def discover_route_overrides(routes_dir: Path) -> list[RouteOverrideDescriptor]:
    """Scan a project routes directory for override declarations.

    Args:
        routes_dir: Path to the project's ``routes/`` directory.

    Returns:
        List of route override descriptors.
    """
    overrides: list[RouteOverrideDescriptor] = []

    if not routes_dir.is_dir():
        return overrides

    for py_file in sorted(routes_dir.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except OSError:
            continue

        match = _ROUTE_OVERRIDE_RE.search(content)
        if not match:
            continue

        method = match.group(1).upper()
        path = match.group(2).strip()

        handler = _load_handler(py_file)
        if handler is None:
            logger.warning("No callable 'handler' function found in %s", py_file)
            continue

        # v0.71.24 (#1126) — optional `# dazzle:implements <Entity>.<op>
        # via <param>` annotation. When present, the route is wrapped
        # at registration time with the framework's permit + scope
        # policy gate. Absent → handler runs unguarded (legacy
        # behaviour preserved for overrides that intentionally take
        # their own authorisation).
        impl_match = _IMPLEMENTS_RE.search(content)
        implements_entity: str | None = None
        implements_op: str | None = None
        implements_via: str | None = None
        if impl_match:
            implements_entity = impl_match.group(1)
            implements_op = impl_match.group(2).lower()
            implements_via = impl_match.group(3)
            if implements_op not in {"list", "read", "create", "update", "delete"}:
                logger.warning(
                    "Route override %s: `# dazzle:implements` op must be one of "
                    "list/read/create/update/delete, got %r — annotation ignored",
                    py_file.name,
                    implements_op,
                )
                implements_entity = implements_op = implements_via = None

        # #1392 item 3 — declared link/fetch targets (one `# dazzle:emits <path>` per line).
        emits_paths = tuple(m.group(1) for m in _EMITS_RE.finditer(content))

        # #1392 item 2 — declared response shape. Unknown kind = a discovery error.
        returns_kind: str | None = None
        returns_match = _RETURNS_RE.search(content)
        if returns_match:
            returns_kind = returns_match.group(1).lower()
            if returns_kind not in _VALID_RETURN_KINDS:
                raise ValueError(
                    f"Route override {py_file.name}: `# dazzle:returns {returns_kind}` is not a "
                    f"valid kind. Expected one of: {', '.join(sorted(_VALID_RETURN_KINDS))}."
                )

        overrides.append(
            RouteOverrideDescriptor(
                method=method,
                path=path,
                source_path=py_file,
                handler=handler,
                implements_entity=implements_entity,
                implements_op=implements_op,
                implements_via=implements_via,
                emits_paths=emits_paths,
                returns_kind=returns_kind,
            )
        )
        if implements_entity:
            logger.info(
                "Discovered route override: %s %s from %s — implements "
                "%s.%s via %s (framework policy gate active)",
                method,
                path,
                py_file,
                implements_entity,
                implements_op,
                implements_via,
            )
        else:
            logger.info("Discovered route override: %s %s from %s", method, path, py_file)

    return overrides


def _load_handler(py_file: Path) -> Callable[..., Any] | None:
    """Load a Python file and extract the ``handler`` function.

    Issue #1020: when the override file re-exports its ``handler`` from
    another module via ``from X import handler``, the returned callable's
    ``__module__`` points at the *source* module, not the override file.
    Multiple alias files all sharing one underlying handler then collapse
    onto a single dispatch identity — every alias path serves whichever
    underlying body imported first.

    To preserve the natural re-export idiom while keeping per-file
    identity, when we detect a re-export we wrap the underlying callable
    in a thin async forwarder owned by the alias module. The forwarder's
    ``__module__`` is the alias module name (keyed by file path stem),
    so each alias has a distinct dispatch entry while still delegating
    to the shared underlying behaviour.
    """
    # Issue #1020: handlers must be keyed by file path, not by
    # handler.__module__, because `from X import handler` re-exports
    # preserve the original __module__ and would collapse multiple
    # alias files onto a single dispatch entry.
    module_name = f"dazzle_routes.{py_file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        logger.warning("Failed to load route override %s", py_file, exc_info=True)
        del sys.modules[module_name]
        return None

    func: Callable[..., Any] | None = getattr(module, "handler", None)
    if func is None or not callable(func):
        del sys.modules[module_name]
        return None

    # Detect re-export: the resolved handler was defined elsewhere.
    # Wrap it in a thin forwarder owned by the alias module so each
    # alias file has its own dispatch identity.
    func_module = getattr(func, "__module__", None)
    if func_module and func_module != module_name:
        func = _make_alias_forwarder(func, module_name)

    return func


def _make_alias_forwarder(underlying: Callable[..., Any], owner_module: str) -> Callable[..., Any]:
    """Wrap ``underlying`` in a thin async forwarder owned by ``owner_module``.

    The forwarder preserves the underlying signature (so FastAPI can
    introspect type hints and dependencies) while giving each alias file
    its own callable identity for per-handler keying.
    """
    import functools

    @functools.wraps(underlying)
    async def _alias_handler(*args: Any, **kwargs: Any) -> Any:
        result = underlying(*args, **kwargs)
        # Support both async and sync underlying handlers — re-exports
        # in the wild are typically async, but stay tolerant.
        if hasattr(result, "__await__"):
            return await result
        return result

    _alias_handler.__module__ = owner_module
    # functools.wraps copies __wrapped__ already; FastAPI's signature
    # introspection follows that to find the real parameters.
    return _alias_handler


def load_extension_routers(
    project_root: Path,
    router_specs: list[str],
) -> list[APIRouter]:
    """Import FastAPI ``APIRouter`` objects declared in ``dazzle.toml`` (#786).

    Each entry in ``router_specs`` is a ``module:attr`` string — e.g.
    ``app.routes.graph:router``. The module is imported with
    ``project_root`` on ``sys.path`` so apps can place routers under
    their own package without a wheel install.

    Returns the list of successfully resolved routers. Malformed specs
    and import failures are logged and skipped so a single broken
    router never takes the whole app down.
    """
    routers: list[APIRouter] = []
    if not router_specs:
        return routers

    import importlib

    root_str = str(project_root)
    added_to_path = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        added_to_path = True

    try:
        for spec in router_specs:
            if ":" not in spec:
                logger.warning("Invalid extension router spec %r — expected 'module:attr'", spec)
                continue
            module_path, attr_name = spec.split(":", 1)
            module_path = module_path.strip()
            attr_name = attr_name.strip()
            if not _MODULE_PATH_RE.match(module_path) or not _ATTR_NAME_RE.match(attr_name):
                # Reject anything that isn't a plain dotted identifier —
                # no path traversal, no shell chars, no dynamic expressions.
                logger.warning("Invalid extension router spec %r", spec)
                continue

            try:
                # Module path is whitelisted to plain dotted identifiers by
                # _MODULE_PATH_RE above and sourced from the project's own
                # dazzle.toml — not external request input.
                module = importlib.import_module(  # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
                    module_path
                )
            except Exception:
                logger.warning(
                    "Failed to import extension router module %r", module_path, exc_info=True
                )
                continue

            router = getattr(module, attr_name, None)
            if router is None:
                logger.warning("Extension router %r not found in module %r", attr_name, module_path)
                continue
            if not isinstance(router, APIRouter):
                logger.warning(
                    "Extension %s.%s is not a FastAPI APIRouter (got %s)",
                    module_path,
                    attr_name,
                    type(router).__name__,
                )
                continue

            routers.append(router)
            logger.info("Loaded extension router %s:%s", module_path, attr_name)
    finally:
        if added_to_path:
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass

    return routers


# #1392 item 2 — one-time advisory dedup (keyed by route path), like #1413's signpost.
_RESPONSE_CONTRACT_NUDGED: set[str] = set()


def _is_full_document(body: str) -> bool:
    """True if the body sniffs as a full HTML document (vs an inner fragment)."""
    head = body.lstrip()[:200].lower()
    return head.startswith("<!doctype") or head.startswith("<html")


def _normalise_html_result(result: Any) -> tuple[str | None, int, dict[str, str], str]:
    """Normalise a handler return to ``(html_body|None, status, headers, media_type)``.

    ``html_body`` is None for a non-HTML response (JSON/redirect/file/stream) — those pass
    through the contract wrapper untouched. A bare ``str`` is treated as HTML.
    """
    from starlette.responses import Response

    if isinstance(result, str):
        return result, 200, {}, "text/html"
    if isinstance(result, Response):
        media = (result.media_type or "").lower()
        if "html" in media or media == "":
            raw = result.body
            body = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
            return body, result.status_code, dict(result.headers), result.media_type or "text/html"
        return None, result.status_code, dict(result.headers), result.media_type or ""
    return None, 200, {}, ""


def _wrap_with_response_contract(
    handler: Callable[..., Any],
    *,
    returns_kind: str | None,
    path: str,
    page_ctx_builder: Callable[..., Any] | None,
) -> Callable[..., Any]:
    """Apply the #1392 item-2 response contract to a route-override handler.

    By ``returns_kind``: ``fragment`` → HTMX-aware shell-wrap (inner HTML for an
    ``HX-Request``; a full chromed document otherwise, via ``page_ctx_builder`` +
    ``dispatch_render_page``); ``partial`` → raw inner HTML; ``page`` → full document
    served as-is (never refused — novel/full-bleed UX); ``json`` → pass through;
    ``None`` (undeclared) → pass through + a one-time advisory for ``/app`` HTML.
    Consistency: a ``fragment``/``partial`` handler returning a full ``<!doctype>`` is a
    typed 500. Composes OUTSIDE ``_wrap_with_policy_gate`` (RBAC already ran).
    """
    import functools

    from fastapi import HTTPException, Request
    from starlette.responses import HTMLResponse

    def _find_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        req = kwargs.get("request")
        if req is None:
            req = next((a for a in args if isinstance(a, Request)), None)
        return req

    @functools.wraps(handler)
    async def contract_handler(*args: Any, **kwargs: Any) -> Any:
        result = handler(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result

        body, status, headers, media = _normalise_html_result(result)
        if body is None:
            return result  # non-HTML → untouched

        request = _find_request(args, kwargs)
        is_htmx = bool(request is not None and request.headers.get("HX-Request"))

        if returns_kind in ("fragment", "partial") and _is_full_document(body):
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "response_contract_violation",
                    "reason": (
                        f"Route override {path} declared `# dazzle:returns {returns_kind}` but "
                        f"returned a full HTML document. Return inner HTML — the app shell is the "
                        f"framework's. Use `# dazzle:returns page` for a deliberate full document."
                    ),
                },
            )

        if returns_kind == "fragment" and not is_htmx and page_ctx_builder is not None:
            from dazzle.render.dispatch import dispatch_render_page

            page_ctx, assets = await page_ctx_builder(request, path)
            html = dispatch_render_page(
                page_ctx,
                body,
                css_links=assets.css_links,
                js_scripts=assets.js_scripts,
                theme=assets.theme,
                font_preconnect=assets.font_preconnect,
                favicon=assets.favicon,
            )
            return HTMLResponse(content=html, status_code=status)

        if returns_kind is None:
            # Undeclared: pass through + a one-time nudge for HTML under /app on a full nav.
            if (
                path.startswith("/app")
                and not is_htmx
                and "html" in media.lower()
                and path not in _RESPONSE_CONTRACT_NUDGED
            ):
                _RESPONSE_CONTRACT_NUDGED.add(path)
                logger.warning(
                    "Route override %s returns HTML but declares no `# dazzle:returns` — declare "
                    "`page` (full-bleed), `fragment` (live in the app shell), or `partial` (raw "
                    "HTMX swap) so the framework knows whether to chrome it (#1392).",
                    path,
                )
            return result

        # fragment+HTMX, partial, page, json → serve the handler's HTML/response as-is.
        if isinstance(result, str):
            return HTMLResponse(content=body, status_code=status, headers=headers or None)
        return result

    return contract_handler


def build_override_router(
    routes_dir: Path, *, page_ctx_builder: Callable[..., Any] | None = None
) -> APIRouter | None:
    """Build a FastAPI router from discovered route overrides.

    Args:
        routes_dir: Path to the project's ``routes/`` directory.
        page_ctx_builder: async ``(request, current_route) -> (PageContext, _ChromeAssets)``
            for the #1392 item-2 ``fragment`` chrome-wrap (None ⇒ fragments are served
            un-chromed, with the contract still enforcing the no-full-document rule).

    Returns:
        APIRouter with project routes, or None if no overrides found.
    """
    overrides = discover_route_overrides(routes_dir)
    if not overrides:
        return None

    router = APIRouter(tags=["Project Overrides"])
    method_map = {
        "GET": router.get,
        "POST": router.post,
        "PUT": router.put,
        "PATCH": router.patch,
        "DELETE": router.delete,
    }

    for override in overrides:
        decorator = method_map.get(override.method)
        if decorator:
            # v0.71.24 (#1126): when the override declared
            # `# dazzle:implements`, wrap the handler so permit + scope
            # evaluation runs against the row at `kwargs[via]` before
            # the user's code sees the request. Otherwise register the
            # bare handler — legacy override behaviour preserved.
            handler = override.handler
            if override.implements_entity:
                handler = _wrap_with_policy_gate(
                    handler,
                    entity=override.implements_entity,
                    op=override.implements_op or "",
                    via=override.implements_via or "",
                )
            # #1392 item 2 — apply the response contract OUTSIDE the policy gate (RBAC
            # runs first, then chrome/shape the result). Applied when a kind is declared,
            # or for an undeclared GET under /app (the advisory nudge needs that case).
            if override.returns_kind is not None or (
                override.method == "GET" and override.path.startswith("/app")
            ):
                handler = _wrap_with_response_contract(
                    handler,
                    returns_kind=override.returns_kind,
                    path=override.path,
                    page_ctx_builder=page_ctx_builder,
                )
            decorator(override.path)(handler)
            logger.info(
                "Registered route override: %s %s -> %s",
                override.method,
                override.path,
                override.source_path.name,
            )

    return router


def _wrap_with_policy_gate(
    handler: Callable[..., Any],
    *,
    entity: str,
    op: str,
    via: str,
) -> Callable[..., Any]:
    """Wrap an override handler so permit + scope evaluation runs first.

    Closes #1126. The wrapper calls
    ``dazzle.http.runtime.policy.check_entity_op`` against the row at
    ``kwargs[via]`` BEFORE invoking the underlying handler. On reject
    the wrapped call raises ``HTTPException(403 or 404)`` and the
    handler body never runs — matching the framework's own CRUD-route
    semantics.

    Limitations of v1:

    - The path param named ``via`` must hold the row's PK directly. If
      the override extracts the row identity from the body or composes
      it from multiple path params, use the imperative form
      ``check_entity_op(request, ..., row_id=...)`` from the handler
      body instead.
    - ``op == "create"`` is supported but ``via`` is unused (the payload
      lives on the request body, which the handler should parse and
      pass to the imperative form). v1 wraps create-mode declarations
      with a permit-gate only; for full create-time scope enforcement
      use the imperative form.

    Async-only: the wrapper is async, and the underlying handler must
    be too (or be a sync function that returns an awaitable). FastAPI
    rejects sync route handlers in the override path — this is the
    same constraint the unwrapped path enforced.
    """
    import functools

    from fastapi import HTTPException, Request

    @functools.wraps(handler)
    async def gated_handler(*args: Any, **kwargs: Any) -> Any:
        # Locate the Request positional/keyword. FastAPI passes it by
        # name when the handler's signature annotates it; some hand-
        # rolled overrides take it positionally.
        request: Request | None = kwargs.get("request")
        if request is None:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        if request is None:
            # Defensive: if the override doesn't take a Request, we
            # can't reach app.state.policy_registry. Surface a clear
            # 500 rather than silently dropping the policy check.
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "policy_gate_missing_request",
                    "reason": (
                        "Route override declared `# dazzle:implements` but "
                        "the handler signature has no `request: Request` "
                        "parameter — the framework can't reach the policy "
                        "registry without it."
                    ),
                },
            )

        # Resolve the row identifier from the path-param kwargs.
        row_id = kwargs.get(via) if op != "create" else None
        if op != "create" and row_id is None:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "policy_gate_missing_path_param",
                    "reason": (
                        f"Route override declared `# dazzle:implements ... "
                        f"via {via}` but no path parameter named {via!r} was "
                        "found on the request — check the route path."
                    ),
                },
            )

        from dazzle.http.runtime.policy import check_entity_op

        # `check_entity_op` raises HTTPException on denial; the
        # underlying handler runs only when the gate passes.
        await check_entity_op(request, entity, op, row_id=row_id)

        result = handler(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    return gated_handler
