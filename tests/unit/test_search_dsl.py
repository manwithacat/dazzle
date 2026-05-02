"""Tests for the `search` DSL block (#954 cycle 1).

Cycle 1 ships parser + IR + linker propagation only. Cycle 2 adds the
Alembic migration for the GIN index; cycle 3 the search endpoint;
cycle 4 the search-box region. These tests pin the surface so later
cycles can extend without DSL re-authoring.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest


@pytest.fixture()
def parse_dsl():
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    def _parse(source: str, tmp_path: pathlib.Path):
        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(textwrap.dedent(source).lstrip())
        modules = parse_modules([dsl_path])
        return build_appspec(modules, "test")

    return _parse


class TestBasicSearch:
    def test_minimal_search(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              title: str(200)
              content: text

            search on Manuscript:
              fields: title, content
            """,
            tmp_path,
        )
        s = appspec.searches[0]
        assert s.entity == "Manuscript"
        assert [f.path for f in s.fields] == ["title", "content"]
        assert all(f.weight == 1 for f in s.fields)
        assert s.highlight is False
        assert s.tokenizer == "english"

    def test_dotted_field_path(self, parse_dsl, tmp_path):
        """Cross-FK paths like ``author.name`` are captured as dotted strings."""
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Author "A":
              id: uuid pk
              name: str(200)

            entity Manuscript "M":
              id: uuid pk
              title: str(200)
              author: ref Author

            search on Manuscript:
              fields: title, author.name
            """,
            tmp_path,
        )
        s = appspec.searches[0]
        assert [f.path for f in s.fields] == ["title", "author.name"]


class TestRanking:
    def test_ranking_block(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              title: str(200)
              content: text

            search on Doc:
              fields: title, content
              ranking:
                title: 4
                content: 1
            """,
            tmp_path,
        )
        weights = {f.path: f.weight for f in appspec.searches[0].fields}
        assert weights == {"title": 4, "content": 1}

    def test_invalid_weight_rejected(self, parse_dsl, tmp_path):
        """Weights must be 1..4 to map to Postgres tsvector D..A."""
        from dazzle.core.errors import ParseError

        with pytest.raises(ParseError, match="weight"):
            parse_dsl(
                """
                module test
                app a "A"

                entity Doc "D":
                  id: uuid pk
                  title: str(200)

                search on Doc:
                  fields: title
                  ranking:
                    title: 7
                """,
                tmp_path,
            )

    def test_unranked_fields_default_to_one(self, parse_dsl, tmp_path):
        """Fields listed in `fields:` but absent from `ranking:` get
        weight 1 (Postgres tsvector D)."""
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              title: str(200)
              content: text
              tags: str(500)

            search on Doc:
              fields: title, content, tags
              ranking:
                title: 4
            """,
            tmp_path,
        )
        weights = {f.path: f.weight for f in appspec.searches[0].fields}
        assert weights == {"title": 4, "content": 1, "tags": 1}


class TestHighlightAndTokenizer:
    def test_highlight_true(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              content: text

            search on Doc:
              fields: content
              highlight: true
            """,
            tmp_path,
        )
        assert appspec.searches[0].highlight is True

    def test_tokenizer_french(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              content: text

            search on Doc:
              fields: content
              tokenizer: french
            """,
            tmp_path,
        )
        assert appspec.searches[0].tokenizer == "french"


class TestErrors:
    def test_missing_fields_raises(self, parse_dsl, tmp_path):
        from dazzle.core.errors import ParseError

        with pytest.raises(ParseError, match="at least one field"):
            parse_dsl(
                """
                module test
                app a "A"

                entity Doc "D":
                  id: uuid pk

                search on Doc:
                  highlight: true
                """,
                tmp_path,
            )


class TestLinkerPropagation:
    def test_search_lands_in_appspec(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              title: str(200)

            search on Doc:
              fields: title
            """,
            tmp_path,
        )
        assert len(appspec.searches) == 1

    def test_duplicate_search_per_entity_rejected(self, parse_dsl, tmp_path):
        from dazzle.core.errors import LinkError

        with pytest.raises(LinkError, match="Duplicate search"):
            parse_dsl(
                """
                module test
                app a "A"

                entity Doc "D":
                  id: uuid pk
                  title: str(200)

                search on Doc:
                  fields: title

                search on Doc:
                  fields: title
                """,
                tmp_path,
            )


class TestImmutability:
    def test_search_spec_is_frozen(self):
        from pydantic import ValidationError

        from dazzle.core.ir import SearchField, SearchSpec

        s = SearchSpec(entity="Doc", fields=[SearchField(path="title")])
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            s.entity = "Other"  # type: ignore[misc]


def test_ir_exports_search_types() -> None:
    from dazzle.core.ir import SearchField, SearchSpec

    assert SearchSpec.__name__ == "SearchSpec"
    assert SearchField.__name__ == "SearchField"
