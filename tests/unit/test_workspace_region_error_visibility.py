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


def test_failing_region_filter_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1847: a region `filter:` that cannot be compiled must raise into
    `fetch_region_items`' fail-closed handler (pinned above), never return
    no filter — which fetched the region unfiltered."""
    from types import SimpleNamespace

    from dazzle.http.runtime import scope_filters
    from dazzle.http.runtime.workspace_region_fetch import _region_condition_filters

    def _broken(*args: object, **kwargs: object) -> None:
        raise TypeError("stale host wrapper signature")

    monkeypatch.setattr(scope_filters, "_extract_condition_filters", _broken)
    ctx = SimpleNamespace(
        source="Ticket", ir_region=SimpleNamespace(filter=object()), entity_ref_targets={}
    )
    user_ctx = SimpleNamespace(user_id="u1", auth_ctx_for_filters=None, filter_context={})
    with pytest.raises(TypeError):
        _region_condition_filters(ctx, user_ctx)
