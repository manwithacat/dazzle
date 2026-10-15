"""Regression tests for #935 — workspace region query errors are loud
in logs.

Pre-fix the workspace-region handler caught every `repo.list` exception
at WARN level and rendered an empty result. That meant a Postgres type
mismatch (e.g. `varchar uploaded_by = uuid User.id`) zeroed the region
silently while the entity-list path (which used a different code path
for current_user resolution) succeeded — costing real engineer time to
debug.

The fail-closed semantics are preserved (#546) — the region still
renders empty rather than leaking unscoped data — but the log line is
now ERROR-level + structured so production log filters surface the
underlying cause on the first occurrence.

Source-grep tests; the IIFE and try/except blocks are exercised
end-to-end by Playwright gates elsewhere.
"""

from pathlib import Path

import pytest

_RUNTIME = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime"


@pytest.mark.parametrize(
    ("module", "log_format"),
    [
        ("workspace_region_fetch.py", "workspace_region_query_failed entity=%s region=%s exc=%s"),
        (
            "workspace_handlers.py",
            "workspace_region_query_failed entity=%s region=%s exc=%s context=batch",
        ),
    ],
    ids=["single-region", "batch"],
)
def test_region_query_failure_logs_error_with_exception_class(module: str, log_format: str) -> None:
    """Each fail-closed handler logs at ERROR with the structured key and the
    exception class name, so log filters group failures without the traceback."""
    src = (_RUNTIME / module).read_text(encoding="utf-8")
    call = src.index(f'"{log_format}"')
    assert src.rfind("logger.error(", 0, call) > src.rfind("except Exception as exc:", 0, call) > 0
    assert "type(exc).__name__" in src[call : call + 200]
