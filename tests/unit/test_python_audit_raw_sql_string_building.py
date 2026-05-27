"""PA-LLM-11 (round 5 of the agent code quality substrate) — raw-SQL
string-building in user code.

The heuristic flags `.execute(...)` calls whose first positional
argument is built via:
  - f-string interpolation     `cur.execute(f"SELECT ... {x}")`
  - string concatenation        `cur.execute("SELECT ... " + x)`
  - %-format on a literal       `cur.execute("SELECT ... %s" % (x,))`
  - `.format()` on a literal    `cur.execute("SELECT ... {}".format(x))`

It explicitly does NOT flag:
  - bare string literals        `cur.execute("SELECT 1")` (parameter-free, safe)
  - identifiers                 `cur.execute(query)` (data-flow OoS)
  - parameterised calls         `cur.execute("SELECT ... ?", (x,))` (the right shape)

See docs/counter-priors/raw-sql-string-building.md.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.sentinel.agents.python_audit import PythonAuditAgent

# ---------------------------------------------------------------------------
# Positive — should fire
# ---------------------------------------------------------------------------


def test_fires_on_f_string_execute(tmp_path: Path) -> None:
    """The canonical wrong shape — f-string straight into execute()."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "reports.py").write_text(
        "def overdue(tenant_id):\n"
        "    cur.execute(f\"SELECT * FROM invoice WHERE tenant_id = '{tenant_id}'\")\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1
    f = findings[0]
    assert f.heuristic_id == "PA-LLM-11"
    assert f.catalogue_entry == "raw-sql-string-building"
    assert f.remediation is not None
    assert any(
        "docs/counter-priors/raw-sql-string-building.md" in ref for ref in f.remediation.references
    )


def test_fires_on_string_concat_execute(tmp_path: Path) -> None:
    """String concatenation with `+` — the other corpus default."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "tags.py").write_text(
        "def rename(old, new):\n"
        "    cur.execute('UPDATE tag SET name = ' + new + ' WHERE name = ' + old)\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1
    assert findings[0].heuristic_id == "PA-LLM-11"


def test_fires_on_pct_format_execute(tmp_path: Path) -> None:
    """Old-style %-format against a SQL literal."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "legacy.py").write_text(
        "def lookup(user_id):\n    cur.execute('SELECT * FROM users WHERE id = %s' % (user_id,))\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1
    assert findings[0].heuristic_id == "PA-LLM-11"


def test_fires_on_format_method_execute(tmp_path: Path) -> None:
    """`"SELECT {}".format(x)` shape — equivalent to the f-string case
    in injection risk; corpus example for older code."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "format.py").write_text(
        "def lookup(uid):\n    cur.execute('SELECT * FROM u WHERE id = {}'.format(uid))\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1


def test_fires_on_scripts_subdir(tmp_path: Path) -> None:
    """`scripts/` is in scope — one-shot scripts that bypass the ORM are
    the canonical example pathology."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "migrate.py").write_text(
        "def bump(table, col):\n    cur.execute(f'UPDATE {table} SET {col} = {col} + 1')\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1


def test_fires_on_session_execute_not_just_cursor(tmp_path: Path) -> None:
    """`session.execute(...)` / `conn.execute(...)` shapes are flagged
    too — the helper matches on the `.execute` attribute, not on a
    specific receiver name."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "sa.py").write_text(
        "def fetch(uid):\n    session.execute(f'SELECT * FROM u WHERE id = {uid}')\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# Negative — should NOT fire
# ---------------------------------------------------------------------------


def test_does_not_fire_on_bare_string_literal_execute(tmp_path: Path) -> None:
    """A bare string literal is parameter-free and safe."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "ok.py").write_text("def health():\n    cur.execute('SELECT 1')\n")
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert findings == []


def test_does_not_fire_on_parameterised_execute(tmp_path: Path) -> None:
    """The right shape — driver handles substitution. SQL string is a
    bare literal with placeholders; values are a separate tuple arg."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "ok.py").write_text(
        "def lookup(uid):\n    cur.execute('SELECT * FROM u WHERE id = %s', (uid,))\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert findings == []


def test_does_not_fire_on_identifier_arg(tmp_path: Path) -> None:
    """Identifier argument — out of scope; data-flow tracking would be
    needed to know whether the identifier was built unsafely."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "ok.py").write_text("def fetch(query):\n    cur.execute(query)\n")
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert findings == []


def test_does_not_fire_on_non_execute_call(tmp_path: Path) -> None:
    """Other methods (`.write`, `.format`, etc.) are not flagged even
    with f-strings — only `.execute()` is the SQL injection sink."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "ok.py").write_text("def log(uid):\n    logger.info(f'user {uid} logged in')\n")
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert findings == []


def test_noqa_suppression_on_execute_line(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-11 — <reason>` on the call line silences the
    finding. The reason isn't enforced but is strongly expected."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "scoped.py").write_text(
        "def fetch(table):\n"
        "    # table name is whitelisted upstream, not user-derived\n"
        "    cur.execute(f'SELECT * FROM {table}')  # noqa: PA-LLM-11 — whitelisted table name\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert findings == []


def test_no_scan_dirs_returns_empty(tmp_path: Path) -> None:
    """Projects without an `app/` or `scripts/` dir produce no findings
    (the heuristic only scans user code, not random tmp_path files)."""
    (tmp_path / "models.py").write_text(
        "def fetch(uid):\n    cur.execute(f'SELECT * FROM u WHERE id = {uid}')\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_raw_sql_string_building(appspec=None)  # type: ignore[arg-type]
    assert findings == []


# ---------------------------------------------------------------------------
# Catalogue integration
# ---------------------------------------------------------------------------


def test_counter_prior_frontmatter_declares_heuristic() -> None:
    """The counter-prior file lists PA-LLM-11 in its `detectors:` slot
    so the catalogue↔detector link is discoverable from both sides."""
    repo_root = Path(__file__).resolve().parents[2]
    counter_prior = repo_root / "docs" / "counter-priors" / "raw-sql-string-building.md"
    assert counter_prior.exists()
    text = counter_prior.read_text(encoding="utf-8")
    assert "PA-LLM-11" in text, (
        "raw-sql-string-building counter-prior must declare PA-LLM-11 "
        "in its frontmatter `detectors:` list so the catalogue↔detector "
        "round-trip works in MCP `knowledge counter_prior` lookups."
    )
