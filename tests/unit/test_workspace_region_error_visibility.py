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

# v0.67.105 (#1057 cut 6): batch + stats handlers moved to workspace_handlers.py.
# v0.67.111 (#1057 cut 12): the per-region `workspace_region_query_failed`
# log line moved to workspace_region_fetch.py.
# v0.67.116 (#1057 cut 17): the workspace_rendering re-export shim was deleted;
# the 6-phase handler lives in workspace_region_handler.py.
# These source-grep tests sweep all four files so the invariants follow the
# code, not the filename.
WS_HANDLERS = Path("src/dazzle/http/runtime/workspace_handlers.py")
WS_FETCH = Path("src/dazzle/http/runtime/workspace_region_fetch.py")
WS_HANDLER = Path("src/dazzle/http/runtime/workspace_region_handler.py")


def _read() -> str:
    return "\n".join((WS_HANDLER.read_text(), WS_HANDLERS.read_text(), WS_FETCH.read_text()))


class TestWorkspaceRegionErrorVisibility:
    def test_no_remaining_warning_swallow(self) -> None:
        """The two `except Exception` blocks that previously logged at
        WARN level have been bumped to ERROR. A `logger.warning` with
        the original `Failed to list items for workspace region`
        message would mean a regression."""
        src = _read()
        assert 'logger.warning("Failed to list items for workspace region"' not in src, (
            "WARN-level swallow should have been bumped to ERROR for #935"
        )

    def test_single_handler_logs_at_error(self) -> None:
        src = _read()
        # The single-region handler's failure path uses logger.error +
        # the structured "workspace_region_query_failed" key.
        assert "workspace_region_query_failed entity=%s region=%s exc=%s" in src

    def test_batch_handler_logs_at_error(self) -> None:
        """Same structured message + a `context=batch` discriminator
        so log queries can split single vs batch failures."""
        src = _read()
        assert "context=batch" in src
        # Two distinct logger.error sites (one per handler).
        assert src.count("workspace_region_query_failed") >= 2

    def test_log_includes_exception_class_name(self) -> None:
        """The structured log captures `type(exc).__name__` so log
        filters can group by error class (e.g. UndefinedFunction,
        UndefinedColumn) without parsing the traceback."""
        src = _read()
        assert "type(exc).__name__" in src

    def test_fail_closed_semantics_preserved(self) -> None:
        """The fix must not change the security posture — failures
        still result in an empty render, never an unscoped fallback."""
        src = _read()
        # The "Do NOT fall back to unfiltered queries" comment from
        # #546 must still anchor the fail-closed intent.
        assert "Do NOT fall back to unfiltered queries" in src
