"""#1445 (ADR-0005): no NEW module-level mutable global without review.

ADR-0005 forbids new singletons / hidden globals (use RuntimeServices/ServerState or
`functools.cache` for idempotent values). `ruff PLW0603` flags `global` writes but is
suppressed per-site with `# noqa`. This gate turns the documented rule into a ratchet:
the set of `global _<name>` write sites in `src/dazzle` may only **shrink**. Any new one
fails here until it's either reworked onto ServerState/`functools.cache` or — if it's a
genuinely sanctioned process/CLI/test seam — added to `_ALLOWLIST` with justification.

The #1445 cleanup removed the lazy-cache (`_dispatch_cache`, `_sa`, `_signer_cache`,
`_fingerprint_cache`, `_WIDGET_KIND_TO_FORM_TYPE`), boot-flag (`_HAPTIC_ENABLED`,
`_DARK_MODE_TOGGLE_ENABLED`), and accumulator (`_DEFAULT_ACCUMULATOR`) globals. What
remains is the frozen baseline below — each is either sanctioned (centralised MCP state,
init-only logging, CLI per-invocation storage, the process-bounded browser gate, the
OTel tracer provider) or tracked for a later slice (`task_store._DEFAULT_BACKEND` pending
the core-injection-seam design; `tenant_isolation._rls_user_attr_names`).
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "dazzle"
_REPO = _SRC.parents[1]

# Frozen baseline — (path relative to repo root, global'd name). Only shrinks.
_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        # Sanctioned process/CLI/test seams (ADR-0005-compatible):
        ("src/dazzle/rbac/audit.py", "_current_sink"),  # thread-safe audit-sink swap (tests)
        ("src/dazzle/mcp/server/state.py", "_state"),  # centralised MCP server state
        ("src/dazzle/cli/env.py", "_active_env"),  # CLI per-invocation
        ("src/dazzle/cli/auth.py", "_database_url_override"),  # CLI callback storage
        ("src/dazzle/testing/browser_gate.py", "_gate"),  # process-bounded browser resource
        ("src/dazzle/http/runtime/logging.py", "_log_dir"),  # system-wide logging, init-only
        ("src/dazzle/http/runtime/logging.py", "_file_handler"),  # system-wide logging, init-only
        ("src/dazzle/perf/tracer.py", "_provider"),  # OTel tracer provider, set-once
        # Warn-once flags (benign one-shot latches):
        ("src/dazzle/core/sitespec_loader.py", "_PATH_KEY_DEPRECATION_WARNED"),
        ("src/dazzle/core/manifest.py", "_FRAGMENT_CHROME_WARNED"),
        # Tracked for a later #1445 slice (genuine shared state):
        ("src/dazzle/core/process/task_store.py", "_DEFAULT_BACKEND"),  # core↛http seam (design)
        ("src/dazzle/http/runtime/tenant_isolation.py", "_rls_user_attr_names"),
    }
)


def _global_sites() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for p in _SRC.rglob("*.py"):
        if "/tests/" in str(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(p.relative_to(_REPO))
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                for name in node.names:
                    if name.startswith("_"):
                        found.add((rel, name))
    return found


def test_no_new_module_level_mutable_globals() -> None:
    sites = _global_sites()
    new = sorted(sites - _ALLOWLIST)
    assert not new, (
        "New module-level mutable `global _<name>` write (ADR-0005). Rework onto "
        "RuntimeServices/ServerState (or `functools.cache` for an idempotent value), or — if "
        "it's a genuinely sanctioned process/CLI/test seam — add it to `_ALLOWLIST` with a "
        "one-line justification:\n  " + "\n  ".join(f"{f}:{n}" for f, n in new)
    )


def test_allowlist_has_no_stale_entries() -> None:
    """The allow-list only shrinks — an entry that no longer exists in the tree (because
    its global was reworked away) must be deleted from `_ALLOWLIST`, keeping it honest."""
    sites = _global_sites()
    stale = sorted(_ALLOWLIST - sites)
    assert not stale, (
        "`_ALLOWLIST` entry no longer present in src/dazzle — the global was removed; delete the "
        "allow-list entry too (the ratchet only shrinks):\n  "
        + "\n  ".join(f"{f}:{n}" for f, n in stale)
    )
