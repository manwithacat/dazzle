"""#1436: runtime error reporting must use the logger, not print().

A ``print()`` inside an ``except`` block in the HTTP/page runtime writes the
failure to stdout, bypassing log levels, structured handlers, and aggregation —
so the error is invisible to operators and the stack trace is lost. Real
request-path failures must go through the module logger (``logger.exception`` /
``logger.warning``).

Allow-listed: the interactive dev-console modules whose ``print()`` IS the
intended UX (the ``dazzle serve`` banner / dependency-missing hints / the
``--reload`` file-watcher), exactly as the issue's enforcement note carves out.
"""

from __future__ import annotations

import ast
import pathlib

_ROOTS = [pathlib.Path("src/dazzle/http"), pathlib.Path("src/dazzle/page")]

# Console-UX modules: print() is the deliberate interactive output here, not
# silent error swallowing. Keep this list tight — a new entry needs a reason.
_ALLOW = {
    "combined_server.py",  # `dazzle serve` console banner + dependency hints
    "dev_server.py",  # dev server console output
    "hot_reload.py",  # the --reload file-watcher's terminal UX
}


def _except_prints(path: pathlib.Path) -> list[int]:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "print"
            ):
                lines.append(sub.lineno)
    return lines


def test_no_print_in_except_blocks_in_runtime() -> None:
    offenders: list[str] = []
    for root in _ROOTS:
        for p in root.rglob("*.py"):
            if "/tests/" in str(p) or p.name in _ALLOW:
                continue
            for ln in _except_prints(p):
                offenders.append(f"{p}:{ln}")
    assert not offenders, (
        "Runtime error reporting must use the module logger, not print() — found "
        "print() inside an except block in:\n  " + "\n  ".join(offenders) + "\n"
        "Use logger.exception(...)/logger.warning(...). If this is genuine "
        "interactive console UX, add the module to the _ALLOW list with a reason."
    )
