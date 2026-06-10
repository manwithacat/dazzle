"""Drift gate: ADR-0014 — no ``from __future__ import annotations`` in
FastAPI files that touch runtime introspection.

Why this exists:
    FastAPI uses runtime introspection (Pydantic ``TypeAdapter``) to build
    OpenAPI schemas and resolve ``Depends(...)`` callables. When a module
    declares ``from __future__ import annotations``, every annotation in
    that module becomes a string at runtime. FastAPI's ``Depends(...)``
    then sees ``ForwardRef('Request')`` instead of the real ``Request``
    class, and ``GET /openapi.json`` 500s with::

        TypeAdapter has no _type_adapter for ForwardRef('Request')

    Closed #1102 (and originally #1034) by removing the future imports
    from the affected files. This gate keeps them from creeping back.

What this enforces:
    Modules under ``src/dazzle/back/runtime/`` that contain a
    ``Depends(`` call site OR a route-handler decorator (``@router.get``,
    ``@router.post``, ``@app.get``, etc.) MUST NOT use
    ``from __future__ import annotations``. These are the file shapes
    FastAPI runtime-introspects.

    Files that only import FastAPI for type hints (e.g. ``app: FastAPI``
    parameter on a builder function) but never define a Depends or
    route handler are unaffected — they can still use the future
    import freely. The gate scoping is intentional: ADR-0014 only
    targets the specific failure mode (#1102).

How to satisfy a violation:
    Remove the ``from __future__ import annotations`` line. Python 3.12+
    supports ``X | Y`` unions and ``list[X]`` generics natively without
    the future import. If you genuinely need deferred evaluation for a
    circular import, scope the affected imports under
    ``if TYPE_CHECKING:`` and use string-literal annotations explicitly
    (``foo: "EntitySpec"``) only where the type would otherwise force
    a runtime circular import.
"""

from __future__ import annotations  # SAFE: this is a test module, not a route file

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / "src" / "dazzle" / "back" / "runtime"

# Patterns that mark a file as runtime-introspected by FastAPI. A file
# triggers ADR-0014 if it has any of:
#  - a ``Depends(`` call site (FastAPI dependency injection — TypeAdapter
#    resolves the annotated parameter types), OR
#  - a route-handler decorator on a router or app, OR
#  - an imperative ``.add_api_route(`` registration (#1365 — the metrics
#    route slipped past the decorator-only gate; a functools.partial
#    endpoint has no __globals__, so a stringified annotation stays a
#    ForwardRef and 500s /openapi.json app-wide).
_DEPENDS_PATTERN = re.compile(r"\bDepends\s*\(")
_ROUTE_DECORATOR_PATTERN = re.compile(
    r"^\s*@(?:[a-z_][a-z_0-9]*\.)+"
    r"(?:get|post|put|patch|delete|head|options|websocket|api_route|middleware)\s*\(",
    re.MULTILINE,
)
_ADD_API_ROUTE_PATTERN = re.compile(r"\.add_api_route\s*\(")


def _is_runtime_introspected(path: Path) -> bool:
    """Does the module define a Depends-using callable or a route handler?"""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return False
    if _DEPENDS_PATTERN.search(text):
        return True
    if _ROUTE_DECORATOR_PATTERN.search(text):
        return True
    if _ADD_API_ROUTE_PATTERN.search(text):
        return True
    return False


def _has_future_annotations(path: Path) -> bool:
    """Return True iff the file has ``from __future__ import annotations``."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


def test_no_future_annotations_in_introspected_routes() -> None:
    """Route files that FastAPI runtime-introspects must not defer annotations (ADR-0014)."""
    violations: list[str] = []
    for path in sorted(RUNTIME_DIR.rglob("*.py")):
        if not _is_runtime_introspected(path):
            continue
        if _has_future_annotations(path):
            violations.append(str(path.relative_to(REPO_ROOT)))

    if violations:
        msg = (
            "ADR-0014 violation — these files define a Depends-injected callable "
            "or a route handler, AND have `from __future__ import annotations`. "
            "The combination breaks Pydantic TypeAdapter on /openapi.json (#1102):\n  "
            + "\n  ".join(violations)
            + "\n\nRemove the future import. Python 3.12+ supports `X | Y` and "
            "`list[X]` natively. If a TYPE_CHECKING-only import gives you a "
            "circular-import problem after removing the future import, use "
            'string-literal annotations (`foo: "EntitySpec"`) only on the '
            "specific parameters that would otherwise force runtime resolution."
        )
        pytest.fail(msg)
