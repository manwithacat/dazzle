"""`dazzle db resanitize-rich-text` planner (flense ship W, ADR-0057).

Ship T sanitises rich text on write; rows stored before it are not. The
planner runs ``clean_rich_text`` over every stored rich-text value through a
``RichTextStore``; here a fake store stands in for Postgres. The real-database
proof is ``tests/integration/test_db_resanitize_rich_text_pg.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import DEFAULT, MagicMock, patch

import pytest
from typer.testing import CliRunner

from dazzle.db.resanitize_rich_text import (
    RichTextTarget,
    resanitize_rich_text,
    rich_text_targets,
)

_HOSTILE = '<p>Hi</p><script>alert(1)</script><img src=x onerror="alert(2)">'
_CLEAN = "<p>Hi <strong>ok</strong></p>"


class _FakeStore:
    def __init__(self, rows: dict[tuple[str, str], dict[Any, Any]]) -> None:
        self.rows = rows
        self.writes: list[tuple[str, str, Any, str | None]] = []

    async def iter_values(self, entity: str, field: str) -> AsyncIterator[tuple[Any, Any]]:
        for row_id, value in self.rows.get((entity, field), {}).items():
            if value is not None:
                yield row_id, value

    async def write_value(self, entity: str, field: str, row_id: Any, value: str | None) -> None:
        self.writes.append((entity, field, row_id, value))
        self.rows[(entity, field)][row_id] = value


def _store() -> _FakeStore:
    return _FakeStore(
        {
            ("Note", "body"): {
                1: _HOSTILE,
                2: _CLEAN,
                3: "<p>" + "x" * 50 + "</p>",  # over the 40-char cap
                4: "<p><br></p>",  # visually empty
                5: None,
            },
            ("Note", "summary"): {1: "<img src=x onerror=alert(1)>"},
        }
    )


_TARGETS = [
    RichTextTarget(entity="Note", field="body", cap=40),
    RichTextTarget(entity="Note", field="summary", cap=1000, required=True),
]


@pytest.mark.asyncio
async def test_dry_run_counts_changes_and_writes_nothing() -> None:
    store = _store()
    report = await resanitize_rich_text(_TARGETS, store)
    assert store.writes == []
    assert not report.applied
    body, summary = report.fields
    assert (body.scanned, body.changed, body.over_cap) == (4, 2, 1)
    assert (summary.scanned, summary.changed, summary.over_cap) == (1, 1, 0)
    assert (report.total_changed, report.total_over_cap) == (3, 1)
    # Counts only: no stored value is carried by the report.
    dumped = repr(report.model_dump())
    assert "script" not in dumped and "onerror" not in dumped and "xxxx" not in dumped


@pytest.mark.asyncio
async def test_apply_writes_sanitised_values_and_skips_over_cap() -> None:
    store = _store()
    report = await resanitize_rich_text(_TARGETS, store, apply=True)
    assert report.applied and report.total_changed == 3
    assert sorted(store.writes, key=repr) == sorted(
        [
            ("Note", "body", 1, "<p>Hi</p>alert(1)"),
            ("Note", "body", 4, None),  # empty shell → NULL, as on the write path
            ("Note", "summary", 1, ""),  # required field: "" rather than NULL
        ],
        key=repr,
    )
    assert store.rows[("Note", "body")][3].startswith("<p>xxx")  # over cap: untouched
    # Idempotent: a second pass finds nothing to change.
    again = await resanitize_rich_text(_TARGETS, store, apply=True)
    assert again.total_changed == 0


def test_targets_come_from_surfaces_and_skip_unknown_fields(tmp_path: Path) -> None:
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    dsl = tmp_path / "app.dsl"
    dsl.write_text(
        """module rt
app rt "RT"

entity Note "Note":
  id: uuid pk
  title: str(200) required
  body: text required
  plain: text

surface note_create "New":
  uses entity Note
  mode: create
  section main:
    field title "Title"
    field body "Body" widget=rich_text rich_text_max_length="300"
    field plain "Plain"
"""
    )
    appspec = build_appspec(parse_modules([dsl]), "rt")
    assert rich_text_targets(appspec) == [
        RichTextTarget(entity="Note", field="body", cap=300, required=True)
    ]


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _close_coro(coro: Any) -> Any:
    coro.close()
    return DEFAULT


def test_cli_rejects_dry_run_with_apply() -> None:
    from dazzle.cli.db import db_app

    result = CliRunner().invoke(db_app, ["resanitize-rich-text", "--dry-run", "--apply"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


@patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
@patch("dazzle.cli.db.load_project_appspec")
def test_cli_reports_counts_per_field(mock_load: MagicMock, mock_run: MagicMock) -> None:
    from dazzle.cli.db import db_app
    from dazzle.db.resanitize_rich_text import FieldResult, ResanitizeReport

    mock_load.return_value = MagicMock()
    mock_run.return_value = ResanitizeReport(
        applied=False,
        fields=[FieldResult(entity="Note", field="body", scanned=4, changed=2, over_cap=1)],
    )
    from dazzle.db.connection import SOURCE_FLAG, DbTarget

    with (
        patch(
            "dazzle.db.resanitize_rich_text.rich_text_targets",
            return_value=[RichTextTarget(entity="Note", field="body", cap=40)],
        ),
        patch(
            "dazzle.cli.db._resolve_target",
            return_value=DbTarget("postgresql://u@h/db", SOURCE_FLAG),
        ),
    ):
        result = CliRunner().invoke(db_app, ["resanitize-rich-text"])
    assert result.exit_code == 0, result.output
    assert "Note.body: 2 of 4 rows" in result.output
    assert "1 over cap, left untouched" in result.output
    assert "Would update 2 rich-text values" in result.output
    assert "--apply" in result.output
