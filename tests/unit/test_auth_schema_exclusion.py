"""Tests that auth routes returning Response are excluded from OpenAPI schema (#411).

`from __future__ import annotations` turns `-> Response` into a forward ref string
that Pydantic can't resolve during schema generation. Routes returning Response
(cookie/redirect responses) have no meaningful JSON schema anyway, so they must
use `include_in_schema=False`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Files that have `from __future__ import annotations` and route handlers
# returning `Response` — these MUST use `include_in_schema=False`.
AUTH_ROUTE_FILES = [
    "src/dazzle_back/runtime/auth/routes.py",
    "src/dazzle_back/runtime/auth/routes_2fa.py",
    "src/dazzle_back/runtime/email_templates.py",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _find_response_routes_missing_schema_exclusion(filepath: Path) -> list[str]:
    """Find route handlers returning Response that lack include_in_schema=False."""
    source = filepath.read_text()
    tree = ast.parse(source)
    problems: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Check if return annotation is Response or RedirectResponse
        ret = node.returns
        if ret is None:
            continue
        ret_name = None
        if isinstance(ret, ast.Name):
            ret_name = ret.id
        elif isinstance(ret, ast.Constant) and isinstance(ret.value, str):
            ret_name = ret.value
        if ret_name not in ("Response", "RedirectResponse"):
            continue

        # Check if this function is decorated with @router.xxx
        for deco in node.decorator_list:
            call = deco if isinstance(deco, ast.Call) else None
            if call is None:
                continue
            func = call.func
            if not isinstance(func, ast.Attribute):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id != "router":
                continue
            if func.attr not in ("get", "post", "put", "patch", "delete"):
                continue

            # Check for include_in_schema=False
            has_exclusion = any(
                isinstance(kw.value, ast.Constant)
                and kw.arg == "include_in_schema"
                and kw.value.value is False
                for kw in call.keywords
            )
            if not has_exclusion:
                problems.append(
                    f"{node.name} (line {node.lineno}): "
                    f"@router.{func.attr} returns {ret_name} but missing "
                    f"include_in_schema=False"
                )
    return problems


@pytest.mark.parametrize("rel_path", AUTH_ROUTE_FILES)
def test_response_routes_excluded_from_schema(rel_path: str) -> None:
    """Routes returning Response must have include_in_schema=False (#411)."""
    filepath = PROJECT_ROOT / rel_path
    if not filepath.exists():
        pytest.skip(f"{rel_path} not found")
    problems = _find_response_routes_missing_schema_exclusion(filepath)
    assert not problems, (
        f"Routes in {rel_path} returning Response without include_in_schema=False:\n"
        + "\n".join(f"  - {p}" for p in problems)
    )
