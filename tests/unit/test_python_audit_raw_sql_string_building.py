"""PA-LLM-11 (round 5 of the agent code quality substrate) — raw-SQL
string-building in user code.

The heuristic flags `.execute(...)` calls whose first positional
argument is built via f-string interpolation, `+` concatenation,
%-format on a literal or `.format()` on a literal. It does NOT flag bare
string literals (parameter-free), identifiers (data-flow out of scope) or
parameterised calls (the right shape). Catalogue wiring and noqa are rows
in test_python_audit_agent.py.

See docs/counter-priors/raw-sql-string-building.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.helpers.python_audit import scan


@pytest.mark.parametrize(
    ("rel_path", "source"),
    [
        pytest.param(
            "app/reports.py",
            "def overdue(tenant_id):\n"
            "    cur.execute(f\"SELECT * FROM invoice WHERE tenant_id = '{tenant_id}'\")\n",
            id="f-string",
        ),
        pytest.param(
            "app/tags.py",
            "def rename(old, new):\n"
            "    cur.execute('UPDATE tag SET name = ' + new + ' WHERE name = ' + old)\n",
            id="string-concat",
        ),
        pytest.param(
            "app/legacy.py",
            "def lookup(user_id):\n"
            "    cur.execute('SELECT * FROM users WHERE id = %s' % (user_id,))\n",
            id="pct-format",
        ),
        pytest.param(
            "app/format.py",
            "def lookup(uid):\n    cur.execute('SELECT * FROM u WHERE id = {}'.format(uid))\n",
            id="format-method",
        ),
        pytest.param(
            # Matches on the `.execute` attribute, not a receiver name.
            "app/sa.py",
            "def fetch(uid):\n    session.execute(f'SELECT * FROM u WHERE id = {uid}')\n",
            id="session-receiver",
        ),
        pytest.param(
            # Unlike PA-LLM-07..10, `scripts/` is in scope: one-shot scripts
            # that bypass the ORM are the canonical pathology.
            "scripts/migrate.py",
            "def bump(table, col):\n    cur.execute(f'UPDATE {table} SET {col} = {col} + 1')\n",
            id="scripts-dir-in-scope",
        ),
    ],
)
def test_fires_on_built_sql(tmp_path: Path, rel_path: str, source: str) -> None:
    findings = scan(tmp_path, "PA-LLM-11", {rel_path: source})
    assert [f.heuristic_id for f in findings] == ["PA-LLM-11"]


@pytest.mark.parametrize(
    ("rel_path", "source"),
    [
        pytest.param(
            "app/ok.py", "def health():\n    cur.execute('SELECT 1')\n", id="bare-literal"
        ),
        pytest.param(
            "app/ok.py",
            "def lookup(uid):\n    cur.execute('SELECT * FROM u WHERE id = %s', (uid,))\n",
            id="parameterised",
        ),
        pytest.param(
            "app/ok.py", "def fetch(query):\n    cur.execute(query)\n", id="identifier-arg"
        ),
        pytest.param(
            # Only `.execute()` is the injection sink.
            "app/ok.py",
            "def log(uid):\n    logger.info(f'user {uid} logged in')\n",
            id="non-execute-call",
        ),
        pytest.param(
            # Only app/ and scripts/ are user code.
            "models.py",
            "def fetch(uid):\n    cur.execute(f'SELECT * FROM u WHERE id = {uid}')\n",
            id="outside-app-and-scripts",
        ),
    ],
)
def test_does_not_fire(tmp_path: Path, rel_path: str, source: str) -> None:
    assert scan(tmp_path, "PA-LLM-11", {rel_path: source}) == []


def test_counter_prior_frontmatter_declares_heuristic() -> None:
    """The counter-prior file lists PA-LLM-11 in its `detectors:` slot so the
    catalogue↔detector link is discoverable from both sides."""
    repo_root = Path(__file__).resolve().parents[2]
    counter_prior = repo_root / "docs" / "counter-priors" / "raw-sql-string-building.md"
    assert "PA-LLM-11" in counter_prior.read_text(encoding="utf-8")
