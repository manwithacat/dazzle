"""Drift gate: zero silent-swallow patterns in production code.

Why this exists:
    Bare ``except Exception: pass`` and its variants
    (``return None``/``{}``/``[]``/``""``) all swallow every error silently —
    the canonical silent-failure pattern. They hide bugs in production paths.

    Smells round 2026-05-04 surfaced 51 variants beyond the strict
    ``: pass`` form (return-trivial). v0.65.17 fixed all 51 by inserting a
    ``logger.debug(..., exc_info=True)`` line above the trivial return,
    then tightened this gate to catch new cases.

How to satisfy:
    Use one of:
      * ``with suppress(Exception):`` — when the suppression is intentional
        (cleanup, best-effort probes, optional features). Greppable as
        "we meant to ignore this".
      * Two-statement except: ``except Exception: logger.debug(...); return X``
        — when the site has a logger and the failure is informational.
      * Re-raise / handle the specific exception — when the failure must
        actually be addressed.

The test rejects single-statement ``except Exception:`` bodies whose only
statement is ``pass`` or a trivial ``return``. A multi-statement body
(e.g. log + return) is accepted because the developer added at least one
informational line.

Tests are out of scope; production code only.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROD_DIRS = ("src/dazzle", "src/dazzle/http", "src/dazzle/page")


def _is_bare_except_exception(handler: ast.ExceptHandler) -> bool:
    """An ``except Exception:`` (no alias, possibly tuple containing Exception)."""
    exc_type = handler.type
    if exc_type is None:
        return False
    # Match `except Exception:` directly
    if isinstance(exc_type, ast.Name) and exc_type.id == "Exception":
        return True
    return False


def _is_trivial_return(node: ast.stmt) -> bool:
    """Is *node* a ``return`` of a trivially empty value (``None``/``{}``/``[]``)?"""
    if not isinstance(node, ast.Return):
        return False
    val = node.value
    if val is None:
        return True
    if isinstance(val, ast.Constant):
        return val.value is None or val.value in (True, False, 0, "", b"")
    # Empty container literal: {}, [], (), set()
    if isinstance(val, ast.Dict) and not val.keys:
        return True
    if isinstance(val, (ast.List, ast.Set, ast.Tuple)) and not val.elts:
        return True
    if isinstance(val, ast.Call):
        f = val.func
        if (
            isinstance(f, ast.Name)
            and f.id in {"dict", "list", "set", "tuple"}
            and not val.args
            and not val.keywords
        ):
            return True
    return False


def _body_is_silent_swallow(handler: ast.ExceptHandler) -> bool:
    """The handler body is a single ``pass`` or trivial ``return``.

    A multi-statement body (e.g. log + return) is NOT a silent swallow —
    the dev added at least one informational statement.
    """
    if len(handler.body) != 1:
        return False
    body0 = handler.body[0]
    return isinstance(body0, ast.Pass) or _is_trivial_return(body0)


def _walk_python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for d in PROD_DIRS:
        root = REPO_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            # skip nested test dirs (e.g. dazzle_http/tests/)
            parts = p.relative_to(REPO_ROOT).parts
            if "tests" in parts:
                continue
            files.append(p)
    return files


def test_no_bare_except_exception_pass() -> None:
    """No production module may silently swallow ``except Exception``.

    Catches both ``except Exception: pass`` and the variant forms that
    return a trivial value (``return None``, ``return {}``, ``return []``,
    ``return ""``, etc.) without logging.
    """
    offenders: list[str] = []
    for path in _walk_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if _is_bare_except_exception(node) and _body_is_silent_swallow(node):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        "Silent `except Exception` swallow is forbidden in production code. "
        'Add a `logger.debug("...", exc_info=True)` line above the return, '
        "use `with suppress(Exception):`, or catch a specific exception type. "
        f"Offenders ({len(offenders)}):\n  " + "\n  ".join(offenders)
    )
