"""Unit tests for the OnboardingStateRepository (v0.71.1).

These mock psycopg at the boundary — no real DB. Integration coverage
(against a real Postgres) lives in the v0.71.x integration suite once
the renderer ships.

Three things to pin:

1. SQL shapes — INSERT ... ON CONFLICT for upsert, SELECT for get,
   UPDATE for mark_completed. Wrong SQL = silent data loss.
2. Idempotency — repeating mark_step_completed for the same step
   doesn't duplicate the step in completed_steps. Repeating
   mark_completed leaves completed_at stable (handled by
   first-call-wins via the UPDATE).
3. JSON round-tripping — completed_steps/dismissed_steps survive
   ``json.dumps`` → row.read → ``json.loads`` via _parse_json_list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dazzle.http.runtime.onboarding.state_repository import (
    OnboardingStateRepository,
    _parse_json_dict,
    _parse_json_list,
    _row_to_progress,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_conn(fetchone_returns: Any = None, rowcount: int = 1):
    """Build a mock psycopg connection that captures the SQL + params
    of every execute() call and returns the supplied fetchone payload."""
    cur = MagicMock()
    cur.fetchone = MagicMock(return_value=fetchone_returns)
    cur.rowcount = rowcount
    # Context-manager protocol on the cursor.
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cur)
    conn.commit = MagicMock()
    conn.close = MagicMock()
    return conn, cur


# ---------------------------------------------------------------------------
# Row → dataclass conversion (pure)
# ---------------------------------------------------------------------------


def test_row_to_progress_round_trip() -> None:
    row = {
        "id": "row-1",
        "user_id": "u1",
        "guide_name": "workspace_setup",
        "guide_version": 1,
        "current_step": "create_task",
        "completed_steps": '["welcome_empty"]',
        "dismissed_steps": "[]",
        "started_at": "2026-05-16T10:00:00+00:00",
        "completed_at": None,
        "metadata": None,
    }
    p = _row_to_progress(row)
    assert p.id == "row-1"
    assert p.user_id == "u1"
    assert p.guide_name == "workspace_setup"
    assert p.guide_version == 1
    assert p.current_step == "create_task"
    assert p.completed_steps == ["welcome_empty"]
    assert p.dismissed_steps == []
    assert p.started_at == datetime(2026, 5, 16, 10, 0, 0, tzinfo=UTC)
    assert p.completed_at is None
    assert p.metadata is None
    assert p.is_complete is False


def test_row_to_progress_handles_completed_row() -> None:
    row = {
        "id": "row-1",
        "user_id": "u1",
        "guide_name": "g",
        "guide_version": 1,
        "current_step": None,
        "completed_steps": '["a", "b", "c"]',
        "dismissed_steps": "[]",
        "started_at": "2026-05-16T10:00:00+00:00",
        "completed_at": "2026-05-16T11:00:00+00:00",
        "metadata": '{"k": "v"}',
    }
    p = _row_to_progress(row)
    assert p.is_complete is True
    assert p.metadata == {"k": "v"}
    assert p.completed_steps == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# JSON parse helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, []),
        ("", []),
        ("[]", []),
        ('["x"]', ["x"]),
        ('["x", "y"]', ["x", "y"]),
        (["literal-list"], ["literal-list"]),  # already-decoded payload
        ("not-json", []),  # malformed → empty
        ('{"obj": 1}', []),  # wrong shape → empty
    ],
)
def test_parse_json_list_handles_all_shapes(value: Any, expected: list[str]) -> None:
    assert _parse_json_list(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ('{"k": 1}', {"k": 1}),
        ({"k": 1}, {"k": 1}),  # already-decoded
        ("not-json", None),
        ('["list"]', None),  # wrong shape → None
    ],
)
def test_parse_json_dict_handles_all_shapes(value: Any, expected: Any) -> None:
    assert _parse_json_dict(value) == expected


# ---------------------------------------------------------------------------
# Repository methods
# ---------------------------------------------------------------------------


def test_get_returns_none_when_no_row() -> None:
    conn, cur = _mock_conn(fetchone_returns=None)
    repo = OnboardingStateRepository("postgresql://test")
    with patch.object(repo, "_get_connection", return_value=conn):
        result = repo.get("u1", "g1", 1)
    assert result is None
    # Verify SELECT shape — no f-string interpolation. Table identifier
    # must be the double-quoted PascalCase form (#1115); unquoted
    # `onboarding_state` would be folded to lowercase by Postgres and
    # fail to resolve against the migration's `"OnboardingState"` DDL.
    assert cur.execute.call_count == 1
    sql, params = cur.execute.call_args[0]
    assert 'SELECT * FROM "OnboardingState"' in sql
    assert "onboarding_state" not in sql.lower().replace('"onboardingstate"', "")
    assert "WHERE user_id = %s AND guide_name = %s AND guide_version = %s" in sql
    assert params == ("u1", "g1", 1)


def test_get_returns_progress_when_row_exists() -> None:
    row = {
        "id": "row-1",
        "user_id": "u1",
        "guide_name": "g1",
        "guide_version": 1,
        "current_step": None,
        "completed_steps": "[]",
        "dismissed_steps": "[]",
        "started_at": "2026-05-16T10:00:00+00:00",
        "completed_at": None,
        "metadata": None,
    }
    conn, _ = _mock_conn(fetchone_returns=row)
    repo = OnboardingStateRepository("postgresql://test")
    with patch.object(repo, "_get_connection", return_value=conn):
        result = repo.get("u1", "g1", 1)
    assert result is not None
    assert result.user_id == "u1"
    assert result.guide_name == "g1"


def test_upsert_uses_on_conflict_clause() -> None:
    row = {
        "id": "row-1",
        "user_id": "u1",
        "guide_name": "g1",
        "guide_version": 1,
        "current_step": "s1",
        "completed_steps": "[]",
        "dismissed_steps": "[]",
        "started_at": "2026-05-16T10:00:00+00:00",
        "completed_at": None,
        "metadata": None,
    }
    conn, cur = _mock_conn(fetchone_returns=row)
    repo = OnboardingStateRepository("postgresql://test")
    with patch.object(repo, "_get_connection", return_value=conn):
        result = repo.upsert(
            user_id="u1",
            guide_name="g1",
            guide_version=1,
            current_step="s1",
        )
    sql = cur.execute.call_args[0][0]
    # Quoted PascalCase per #1115 — see test_get_returns_none_when_no_row.
    assert 'INSERT INTO "OnboardingState"' in sql
    assert "ON CONFLICT (user_id, guide_name, guide_version)" in sql
    assert "DO UPDATE SET" in sql
    assert result.current_step == "s1"
    conn.commit.assert_called_once()


def test_mark_step_completed_is_idempotent() -> None:
    """Calling mark_step_completed twice with the same step name leaves
    the completed_steps list with one entry, not two."""
    existing_row = {
        "id": "row-1",
        "user_id": "u1",
        "guide_name": "g1",
        "guide_version": 1,
        "current_step": "s1",
        "completed_steps": '["s1"]',  # s1 already complete
        "dismissed_steps": "[]",
        "started_at": "2026-05-16T10:00:00+00:00",
        "completed_at": None,
        "metadata": None,
    }
    upsert_row = dict(existing_row, current_step="s2")  # what upsert returns
    conn, cur = _mock_conn()
    # get() returns the existing row; upsert() returns the new row.
    cur.fetchone = MagicMock(side_effect=[existing_row, upsert_row])

    repo = OnboardingStateRepository("postgresql://test")
    with patch.object(repo, "_get_connection", return_value=conn):
        result = repo.mark_step_completed(
            user_id="u1",
            guide_name="g1",
            guide_version=1,
            step_name="s1",  # already in completed_steps
            next_current_step="s2",
        )
    # The completed_steps array passed to upsert should NOT have a
    # duplicate s1 — extract it from the second execute() call.
    upsert_params = cur.execute.call_args_list[1][0][1]
    completed_json = upsert_params[5]
    assert completed_json == '["s1"]', f"expected dedupe, got {completed_json!r}"
    assert result.current_step == "s2"


def test_mark_step_dismissed_is_idempotent() -> None:
    existing = {
        "id": "r",
        "user_id": "u1",
        "guide_name": "g",
        "guide_version": 1,
        "current_step": "s1",
        "completed_steps": "[]",
        "dismissed_steps": '["s1"]',
        "started_at": "2026-05-16T10:00:00+00:00",
        "completed_at": None,
        "metadata": None,
    }
    conn, cur = _mock_conn()
    cur.fetchone = MagicMock(side_effect=[existing, existing])

    repo = OnboardingStateRepository("postgresql://test")
    with patch.object(repo, "_get_connection", return_value=conn):
        repo.mark_step_dismissed(user_id="u1", guide_name="g", guide_version=1, step_name="s1")
    upsert_params = cur.execute.call_args_list[1][0][1]
    dismissed_json = upsert_params[6]
    assert dismissed_json == '["s1"]'


def test_mark_completed_uses_update_with_now() -> None:
    conn, cur = _mock_conn(rowcount=1)
    repo = OnboardingStateRepository("postgresql://test")
    with patch.object(repo, "_get_connection", return_value=conn):
        ok = repo.mark_completed(user_id="u1", guide_name="g1", guide_version=1)
    assert ok is True
    sql, params = cur.execute.call_args[0]
    # Quoted PascalCase per #1115.
    assert 'UPDATE "OnboardingState"' in sql
    assert "completed_at = %s" in sql
    assert "current_step = NULL" in sql
    # First param is the ISO timestamp.
    assert isinstance(params[0], str)


def test_mark_completed_returns_false_when_no_row_touched() -> None:
    conn, _ = _mock_conn(rowcount=0)
    repo = OnboardingStateRepository("postgresql://test")
    with patch.object(repo, "_get_connection", return_value=conn):
        ok = repo.mark_completed(user_id="ghost", guide_name="g1", guide_version=1)
    assert ok is False


# ---------------------------------------------------------------------------
# #1115 — table-identifier convention. Every SQL statement the
# repository issues must reference `"OnboardingState"` (double-quoted
# PascalCase). Unquoted `onboarding_state` would be folded to lowercase
# by Postgres and fail to resolve against the migration-created
# `"OnboardingState"` DDL. The bug presents as a silent guide-overlay
# failure: page renders, ImportError-class exception swallowed by
# `_inject_onboarding_step`, no overlay visible.
# ---------------------------------------------------------------------------


def _capture_all_sql_strings() -> list[str]:
    """Exercise every write+read path through the repository against
    a mock cursor and return the SQL strings that hit cur.execute()."""
    repo = OnboardingStateRepository("postgresql://test")
    captured: list[str] = []

    minimal_row = {
        "id": "r",
        "user_id": "u1",
        "guide_name": "g",
        "guide_version": 1,
        "current_step": None,
        "completed_steps": "[]",
        "dismissed_steps": "[]",
        "started_at": "2026-05-16T10:00:00+00:00",
        "completed_at": None,
        "metadata": None,
    }

    for op in ("get", "upsert", "mark_step_completed", "mark_step_dismissed", "mark_completed"):
        conn, cur = _mock_conn(fetchone_returns=minimal_row, rowcount=1)
        # Mark_step_*: get() runs first, then upsert() — both return rows.
        cur.fetchone = MagicMock(side_effect=[minimal_row, minimal_row, minimal_row])
        with patch.object(repo, "_get_connection", return_value=conn):
            if op == "get":
                repo.get("u1", "g", 1)
            elif op == "upsert":
                repo.upsert(user_id="u1", guide_name="g", guide_version=1)
            elif op == "mark_step_completed":
                repo.mark_step_completed(
                    user_id="u1", guide_name="g", guide_version=1, step_name="s1"
                )
            elif op == "mark_step_dismissed":
                repo.mark_step_dismissed(
                    user_id="u1", guide_name="g", guide_version=1, step_name="s1"
                )
            elif op == "mark_completed":
                repo.mark_completed(user_id="u1", guide_name="g", guide_version=1)
        for call in cur.execute.call_args_list:
            captured.append(call[0][0])
    return captured


def test_every_sql_statement_quotes_the_table_name_as_pascalcase() -> None:
    """Regression for #1115. Every SQL statement issued by the
    repository must reference the table as `"OnboardingState"` (quoted
    PascalCase). Any unquoted `onboarding_state` substring is a bug —
    Postgres folds unquoted identifiers to lowercase, which would miss
    the migration-created `"OnboardingState"` DDL and produce silent
    `relation "onboarding_state" does not exist` errors that the
    onboarding injector swallows."""
    sql_strings = _capture_all_sql_strings()
    assert sql_strings, "expected at least one SQL statement"

    for sql in sql_strings:
        assert '"OnboardingState"' in sql, (
            f"SQL statement does not quote the table identifier: {sql!r}"
        )
        # The unquoted form must not appear anywhere. Strip the
        # quoted form first so an incidental substring match inside
        # `"OnboardingState"` doesn't false-positive.
        without_quoted = sql.replace('"OnboardingState"', "")
        assert "onboarding_state" not in without_quoted.lower(), (
            f"SQL statement contains unquoted lowercase `onboarding_state` "
            f"(case-folded by PG → unresolved): {sql!r}"
        )
