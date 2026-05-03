"""Tests for #954 cycle 4 — highlight + search_box region.

Cycle 3 shipped the lexical search endpoint backed by `ts_rank`. This
cycle adds:

- `ts_headline` snippet columns when `SearchSpec.highlight=True`.
  Each searchable text field gets a `<field>__snippet` column with
  matched terms wrapped in `<mark>` tags.
- Default ranking switched to `ts_rank_cd` (cover-density) — usually
  produces better top results than plain `ts_rank` for short queries.
- `display: search_box` workspace region — registered in
  `DISPLAY_TEMPLATE_MAP`, backed by an htmx-driven template that
  hits `/api/fts/<entity>?q=…`.
- HTML fragment response on the FTS endpoint when `?html=1`.

These tests verify the SQL shape (highlight on/off branch),
the field-name allow-list (defence in depth), the fragment template
renders the `<mark>` tags, and DisplayMode.SEARCH_BOX dispatches
correctly.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core.ir.search import SearchField, SearchSpec
from dazzle_back.runtime.repository import Repository, _safe_text_field_names

# ---------------------------------------------------------------------------
# Stub connection (mirrors test_fts_search_method.py)
# ---------------------------------------------------------------------------


class _StubCursor:
    def __init__(self, count: int, rows: list[dict[str, Any]]) -> None:
        self._count = count
        self._rows = rows
        self.queries: list[tuple[str, list[Any]]] = []
        self._last_was_count = False

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...]) -> None:
        self.queries.append((sql, list(params)))
        self._last_was_count = "COUNT(*)" in sql

    def fetchone(self) -> Any:
        if self._last_was_count:
            return (self._count,)
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _StubDb:
    placeholder = "%s"

    def __init__(self, count: int = 0, rows: list[dict[str, Any]] | None = None) -> None:
        self.cursor_obj = _StubCursor(count, rows or [])

    @contextmanager
    def connection(self):
        yield SimpleNamespace(cursor=lambda: self.cursor_obj)


def _entity_with_fields(name: str, field_specs: list[tuple[str, str]]) -> Any:
    """Stub entity carrying just (name, field-kind) tuples."""
    fields = [
        SimpleNamespace(name=fname, type=SimpleNamespace(kind=fkind))
        for fname, fkind in field_specs
    ]
    return SimpleNamespace(name=name, fields=fields, computed_fields=[])


def _build_repo(
    entity_name: str = "Manuscript",
    fields: list[tuple[str, str]] | None = None,
    count: int = 3,
    rows: list[dict[str, Any]] | None = None,
) -> Repository:
    if fields is None:
        fields = [("id", "uuid"), ("title", "str"), ("body", "text")]
    if rows is None:
        rows = [
            {
                "id": "uid-1",
                "rank": 0.95,
                "title": "Hello world",
                "title__snippet": "<mark>Hello</mark> world",
                "body__snippet": "An intro to the <mark>hello</mark> phrase.",
            }
        ]
    entity = _entity_with_fields(entity_name, fields)

    class _M:
        pass

    return Repository(
        db_manager=_StubDb(count=count, rows=rows), entity_spec=entity, model_class=_M
    )


def _spec_with_highlight(highlight: bool = True) -> SearchSpec:
    return SearchSpec(
        entity="Manuscript",
        fields=[SearchField(path="title", weight=4), SearchField(path="body", weight=1)],
        tokenizer="english",
        highlight=highlight,
    )


# ---------------------------------------------------------------------------
# _safe_text_field_names — defence-in-depth filter
# ---------------------------------------------------------------------------


class TestSafeTextFieldNames:
    def test_returns_only_text_shaped_fields(self):
        entity = _entity_with_fields(
            "Doc",
            [("title", "str"), ("body", "text"), ("page_count", "int"), ("created_at", "datetime")],
        )
        spec = SearchSpec(
            entity="Doc",
            fields=[
                SearchField(path="title", weight=4),
                SearchField(path="body", weight=1),
                SearchField(path="page_count", weight=2),  # int → dropped
            ],
        )
        names = _safe_text_field_names(entity, spec)
        assert names == ["title", "body"]
        assert "page_count" not in names

    def test_skips_dotted_fk_paths(self):
        entity = _entity_with_fields("Doc", [("title", "str")])
        spec = SearchSpec(
            entity="Doc",
            fields=[SearchField(path="title", weight=4), SearchField(path="author.name", weight=2)],
        )
        names = _safe_text_field_names(entity, spec)
        assert names == ["title"]

    def test_skips_unknown_fields(self):
        entity = _entity_with_fields("Doc", [("title", "str")])
        spec = SearchSpec(
            entity="Doc",
            fields=[SearchField(path="title", weight=4), SearchField(path="ghost", weight=2)],
        )
        names = _safe_text_field_names(entity, spec)
        assert names == ["title"]

    def test_dedupes_within_spec(self):
        entity = _entity_with_fields("Doc", [("title", "str")])
        # SearchSpec validation might allow duplicates; helper must
        # collapse them so we don't emit two `title__snippet` columns.
        spec = SimpleNamespace(
            fields=[
                SimpleNamespace(path="title"),
                SimpleNamespace(path="title"),
            ]
        )
        names = _safe_text_field_names(entity, spec)
        assert names == ["title"]


# ---------------------------------------------------------------------------
# fts_search SQL with highlight=True
# ---------------------------------------------------------------------------


class TestHighlightSql:
    def test_highlight_off_omits_ts_headline(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec_with_highlight(False), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "ts_headline" not in items_sql

    def test_highlight_on_adds_one_ts_headline_per_text_field(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec_with_highlight(True), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        # Two text fields → two ts_headline calls.
        assert items_sql.count("ts_headline(") == 2

    def test_highlight_uses_mark_tags(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec_with_highlight(True), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "StartSel=<mark>" in items_sql
        assert "StopSel=</mark>" in items_sql

    def test_highlight_aliases_columns_with_double_underscore_snippet(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec_with_highlight(True), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert '"title__snippet"' in items_sql
        assert '"body__snippet"' in items_sql

    def test_highlight_query_is_parameterised(self):
        # ts_headline takes its own bind for the tsquery — verify the
        # query string never gets inlined.
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec_with_highlight(True), "'; DROP TABLE Manuscript; --"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "DROP TABLE" not in items_sql

    def test_highlight_uses_ts_rank_cd(self):
        # Cover-density gives better short-query results than plain ts_rank.
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec_with_highlight(True), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "ts_rank_cd(" in items_sql

    def test_result_carries_snippet_fields_metadata(self):
        repo = _build_repo()
        result = asyncio.run(repo.fts_search(_spec_with_highlight(True), "hello"))
        # Templates can introspect snippet_fields without scanning rows.
        assert result["snippet_fields"] == ["title", "body"]


# ---------------------------------------------------------------------------
# DisplayMode + workspace_renderer wiring
# ---------------------------------------------------------------------------


class TestDisplayModeRegistration:
    def test_search_box_in_display_mode_enum(self):
        from dazzle.core.ir.workspaces import DisplayMode

        assert DisplayMode.SEARCH_BOX == "search_box"

    def test_search_box_template_mapped(self):
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "SEARCH_BOX" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["SEARCH_BOX"].endswith("search_box.html")

    def test_search_box_template_loads_from_framework_env(self):
        # Same loader the runtime uses — verifies the template path is
        # actually resolvable.
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        tpl = env.get_template("dz://workspace/regions/search_box.html")  # nosemgrep
        assert "dz-search-box-region" in tpl.render(  # nosemgrep
            source="Manuscript",
            title="Search",
            placeholder="Search…",
            display_field="title",
            name="ms",
            _=lambda s: s,
        )


# ---------------------------------------------------------------------------
# Result fragment rendering
# ---------------------------------------------------------------------------


class TestResultsFragment:
    def test_fragment_renders_no_results_message(self):
        from dazzle_ui.runtime.template_renderer import render_fragment

        out = render_fragment(
            "fragments/search_box_results.html",
            entity="Manuscript",
            q="missing-thing",
            items=[],
            snippet_fields=[],
            total=0,
        )
        assert "No results" in out
        assert "missing-thing" in out

    def test_fragment_preserves_mark_tags_in_snippet(self):
        # ts_headline output has `<mark>` tags; the fragment must pass
        # them through with `| safe` so the highlight survives.
        from dazzle_ui.runtime.template_renderer import render_fragment

        out = render_fragment(
            "fragments/search_box_results.html",
            entity="Manuscript",
            q="hello",
            items=[
                {
                    "id": "uid-1",
                    "title": "Hello world",
                    "title__snippet": "<mark>Hello</mark> world",
                }
            ],
            snippet_fields=["title"],
            total=1,
        )
        # `<mark>` survives autoescape via `| safe` filter.
        assert "<mark>Hello</mark>" in out

    def test_fragment_links_to_entity_detail_route(self):
        from dazzle_ui.runtime.template_renderer import render_fragment

        out = render_fragment(
            "fragments/search_box_results.html",
            entity="Manuscript",
            q="hello",
            items=[{"id": "uid-1", "title": "Hello world"}],
            snippet_fields=[],
            total=1,
        )
        assert 'href="/app/manuscript/uid-1"' in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
