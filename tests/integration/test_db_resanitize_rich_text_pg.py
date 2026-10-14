"""Real-Postgres proof of ``dazzle db resanitize-rich-text`` (flense ship W).

Rows stored before flense ship T hold whatever HTML was posted. This boots a
two-field DSL (``body`` is rich text on its surface, ``plain`` is not) in
``tmp_path`` against a disposable database so the tables exist, inserts a
hostile row directly with SQL (bypassing the write path), runs the command
dry and then with ``--apply``, and reads the row back.

The project lives in ``tmp_path``, so no ``xdist_group`` pin is needed.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

_MANIFEST = """[project]
name = "rt_resan"
version = "0.1.0"
root = "rt_resan"

[modules]
paths = ["./dsl"]
"""

_DSL = """module rt_resan
app rt_resan "Rich Text Resanitise"

entity Note "Note":
  id: uuid pk
  title: str(200) required
  body: text
  plain: text

surface note_edit "Edit Note":
  uses entity Note
  mode: edit
  section main:
    field title "Title"
    field body "Body" widget=rich_text
    field plain "Plain"
"""

_HOSTILE = "<p>Hi <strong>there</strong></p><script>alert(1)</script><svg/onload=alert(2)>"
_CLEANED = "<p>Hi <strong>there</strong></p>alert(1)"
_PLAIN = "<script>not a rich-text field</script> one=two"


def _read(db_url: str, note_id: uuid.UUID) -> tuple[str, str]:
    import psycopg

    with psycopg.connect(db_url) as conn:
        row = conn.execute('SELECT body, plain FROM "Note" WHERE id = %s', (note_id,)).fetchone()
    assert row is not None
    return row[0], row[1]


async def test_resanitize_rich_text_cleans_a_stored_hostile_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import psycopg
    from typer.testing import CliRunner

    from dazzle.cli.db import db_app
    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase

    root = tmp_path / "rt_resan"
    (root / "dsl").mkdir(parents=True)
    (root / "dazzle.toml").write_text(_MANIFEST)
    (root / "dsl" / "app.dsl").write_text(_DSL)

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(root, db_url)  # creates the entity tables
        db_manager = getattr(built.builder, "_db_manager", None)
        if db_manager is not None:
            db_manager.close_pool()

        note_id = uuid.uuid4()
        with psycopg.connect(db_url) as conn:
            conn.execute(
                'INSERT INTO "Note" (id, title, body, plain) VALUES (%s, %s, %s, %s)',
                (note_id, "Old", _HOSTILE, _PLAIN),
            )

        monkeypatch.chdir(root)
        runner = CliRunner()
        args = ["resanitize-rich-text", "--database-url", db_url]

        dry = await asyncio.to_thread(runner.invoke, db_app, args)
        assert dry.exit_code == 0, dry.output
        assert "Note.body: 1 of 1 rows" in dry.output
        assert "script" not in dry.output  # counts only, never values
        assert _read(db_url, note_id) == (_HOSTILE, _PLAIN)  # dry run wrote nothing

        applied = await asyncio.to_thread(runner.invoke, db_app, [*args, "--apply"])
        assert applied.exit_code == 0, applied.output
        assert "Updated 1 rich-text values" in applied.output
        assert _read(db_url, note_id) == (_CLEANED, _PLAIN)

        again = await asyncio.to_thread(runner.invoke, db_app, args)
        assert "Note.body: 0 of 1 rows" in again.output
