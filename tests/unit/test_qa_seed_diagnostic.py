"""Tests for the seed circuit-breaker failure-classifier (#1207).

When `dazzle qa trial --fresh-db` trips its 10-consecutive-failure circuit
breaker, the recovery hint must distinguish schema/migration drift (Alembic
recovery) from blueprint drift (`dazzle demo verify` recovery). Sending the
operator down the wrong path was the bug — these tests pin the classifier.
"""

from __future__ import annotations

from dazzle.cli.qa import _diagnose_seed_failures


def test_diagnose_column_missing_recommends_alembic() -> None:
    """A column-missing error names the column + table and recommends `dazzle db revision`."""
    sample = [
        'Alert/abc: HTTP 400 {"detail":"Failed to create Alert: '
        'column \\"status\\" of relation \\"Alert\\" does not exist..."}'
    ]
    hint = _diagnose_seed_failures(sample)
    assert hint is not None
    assert "status" in hint
    assert "Alert" in hint
    assert "dazzle db revision" in hint


def test_diagnose_table_missing_recommends_alembic() -> None:
    """A relation-missing error names the table and recommends `dazzle db revision`."""
    sample = ['Foo/xyz: HTTP 400 {"detail":"relation \\"Foo\\" does not exist"}']
    hint = _diagnose_seed_failures(sample)
    assert hint is not None
    assert "Foo" in hint
    assert "dazzle db revision" in hint


def test_diagnose_unrelated_error_returns_none() -> None:
    """A non-schema error returns None so the caller falls back to the blueprint-drift message."""
    sample = ['Bar/q: HTTP 400 {"detail":"foreign key violation"}']
    assert _diagnose_seed_failures(sample) is None
