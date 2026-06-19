"""Framework structural-fitness: broad-exception-swallow census + ratchet input.

Counts the two swallow shapes the 2026-06-19 smells round flagged as the dominant
semantic debt, so a drift-style gate can hold the line (the class only shrinks):

- **silent**: ``except (Exception | ImportError): pass|continue`` — fire-and-forget,
  zero diagnostic even at DEBUG.
- **debug_only**: ``except Exception: ... logger.debug(...)`` — effectively silent in
  production (DEBUG is off), blurring expected-and-handled with unexpected-and-hidden.

Deterministic regex census (not AST) so the baseline is stable across machines and
matches the smells report's own ``done_criteria`` greps. The fix for a flagged site is
to narrow the exception type or raise the log level — never to broaden the regex.
"""

from __future__ import annotations

import re
from pathlib import Path

# `except (Exception|ImportError) ...:` immediately followed by only pass/continue.
_SILENT = re.compile(r"except\s+(?:Exception|ImportError)\b[^\n]*:\s*\n[ \t]*(?:pass|continue)\b")
# `except Exception ...:` immediately followed by a debug-level log call (no higher,
# no re-raise on the first body line) — the "log at debug and carry on" idiom.
_DEBUG_ONLY = re.compile(
    r"except\s+Exception\b[^\n]*:\s*\n[ \t]*(?:logger|log|logging\.getLogger\([^\n)]*\))\.debug\("
)


def count_swallows(root: Path) -> dict[str, int]:
    """Census of broad-exception swallows under ``root`` → ``{"silent": n, "debug_only": m}``."""
    silent = 0
    debug_only = 0
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        silent += len(_SILENT.findall(src))
        debug_only += len(_DEBUG_ONLY.findall(src))
    return {"silent": silent, "debug_only": debug_only}
