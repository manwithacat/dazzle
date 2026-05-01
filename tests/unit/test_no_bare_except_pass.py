"""Drift gate: zero bare ``except Exception: pass`` blocks in production code.

Why this exists:
    Bare ``except Exception: pass`` swallows every error silently — the canonical
    silent-failure pattern. Smells round 2026-04-16/2026-05-01 trimmed prod sites
    from 44 → 28 → 0; this test pins the achievement.

How to satisfy:
    Use one of:
      * ``with suppress(Exception):`` — when the suppression is intentional
        (cleanup, best-effort probes, optional features). Greppable as
        "we meant to ignore this".
      * ``except Exception: logger.debug("...", exc_info=True)`` — when the
        site has a logger and the failure is informational.
      * Re-raise / handle the specific exception — when the failure must
        actually be addressed.

Tests are out of scope; production code only.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROD_DIRS = ("src/dazzle", "src/dazzle_back", "src/dazzle_ui")


def _is_bare_except_exception(handler: ast.ExceptHandler) -> bool:
    """An ``except Exception:`` (no alias, possibly tuple containing Exception)."""
    exc_type = handler.type
    if exc_type is None:
        return False
    # Match `except Exception:` directly
    if isinstance(exc_type, ast.Name) and exc_type.id == "Exception":
        return True
    return False


def _body_is_only_pass(handler: ast.ExceptHandler) -> bool:
    """The handler body is a single ``pass`` statement."""
    return len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)


def _walk_python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for d in PROD_DIRS:
        root = REPO_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            # skip nested test dirs (e.g. dazzle_back/tests/)
            parts = p.relative_to(REPO_ROOT).parts
            if "tests" in parts:
                continue
            files.append(p)
    return files


def test_no_bare_except_exception_pass() -> None:
    """No production module may contain ``except Exception: pass``."""
    offenders: list[str] = []
    for path in _walk_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if _is_bare_except_exception(node) and _body_is_only_pass(node):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        "Bare `except Exception: pass` is forbidden in production code. "
        "Use `with suppress(Exception):` or log at debug level. "
        f"Offenders ({len(offenders)}):\n  " + "\n  ".join(offenders)
    )
