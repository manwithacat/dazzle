"""Tests for #954 cycle 2 — SearchSpec → tsvector + GIN index DDL.

Cycle 1 shipped the SearchSpec IR + parser; this cycle bridges it to
the DDL Postgres needs to make full-text search actually work. The
runtime applies the DDL after `metadata.create_all` in dev mode;
production migrations include the same statements via Alembic.

Tests cover:
- The generated SQL is shape-correct (ALTER TABLE … ADD COLUMN …
  GENERATED ALWAYS AS … STORED, then CREATE INDEX … USING GIN)
- Weights map int → letter correctly (4 → A, 3 → B, 2 → C, 1 → D)
- The tokenizer is validated against the Postgres allow-list
- Dotted FK paths skip with a warning (cycle 4+ work)
- Non-text fields skip with a warning
- Idempotent: repeated boots don't error (IF NOT EXISTS clauses)
- Empty searches list returns []
- Misnamed entity in spec returns [] + logs warning
- Special / mixed-case identifiers are quoted
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.search import SearchField, SearchSpec
from dazzle_back.runtime.search_schema import (
    SEARCH_VECTOR_COLUMN,
    build_search_index_ddl,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _entity(name: str, fields: list[tuple[str, FieldTypeKind]]) -> Any:
    """Minimal entity stub: just enough for the schema generator's
    .name + .fields[*].name + .fields[*].type.kind reads."""
    field_specs = [FieldSpec(name=fname, type=FieldType(kind=fkind)) for fname, fkind in fields]
    # The generator only touches `.name` and `.fields`; using a SimpleNamespace
    # keeps the test independent of the full EntitySpec validation.
    from types import SimpleNamespace

    return SimpleNamespace(name=name, fields=field_specs)


def _spec(entity: str, fields: list[tuple[str, int]], **kwargs: Any) -> SearchSpec:
    return SearchSpec(
        entity=entity,
        fields=[SearchField(path=p, weight=w) for p, w in fields],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Happy-path shape
# ---------------------------------------------------------------------------


class TestGeneratedDdlShape:
    def test_emits_alter_then_index_pair(self):
        manuscript = _entity(
            "Manuscript",
            [("title", FieldTypeKind.STR), ("body", FieldTypeKind.TEXT)],
        )
        spec = _spec("Manuscript", [("title", 4), ("body", 1)])
        ddl = build_search_index_ddl([manuscript], [spec])
        assert len(ddl) == 2
        assert ddl[0].startswith("ALTER TABLE")
        assert "ADD COLUMN IF NOT EXISTS" in ddl[0]
        assert f'"{SEARCH_VECTOR_COLUMN}" tsvector' in ddl[0]
        assert "GENERATED ALWAYS AS" in ddl[0]
        assert "STORED" in ddl[0]
        assert ddl[1].startswith("CREATE INDEX IF NOT EXISTS")
        assert "USING GIN" in ddl[1]

    def test_index_name_includes_table_lowercased(self):
        e = _entity("Manuscript", [("title", FieldTypeKind.STR)])
        spec = _spec("Manuscript", [("title", 4)])
        ddl = build_search_index_ddl([e], [spec])
        # ix_manuscript_search_vector — predictable so adopters can
        # reference it in performance dashboards.
        assert '"ix_manuscript_search_vector"' in ddl[1]

    def test_table_and_column_identifiers_are_quoted(self):
        # Mixed-case entity names must round-trip safely. Postgres
        # folds unquoted identifiers to lowercase; double-quoting
        # preserves them.
        e = _entity("Manuscript", [("title", FieldTypeKind.STR)])
        spec = _spec("Manuscript", [("title", 4)])
        ddl = build_search_index_ddl([e], [spec])
        assert '"Manuscript"' in ddl[0]
        assert '"title"' in ddl[0]


# ---------------------------------------------------------------------------
# Weight + tokenizer mapping
# ---------------------------------------------------------------------------


class TestWeightMapping:
    @pytest.mark.parametrize(
        "weight,expected_letter",
        [(4, "A"), (3, "B"), (2, "C"), (1, "D")],
    )
    def test_int_maps_to_letter(self, weight: int, expected_letter: str):
        e = _entity("Doc", [("body", FieldTypeKind.TEXT)])
        spec = _spec("Doc", [("body", weight)])
        ddl = build_search_index_ddl([e], [spec])
        assert (
            f"setweight(to_tsvector('english', coalesce(\"body\", '')), '{expected_letter}')"
            in ddl[0]
        )

    def test_concat_preserves_field_order(self):
        e = _entity(
            "Doc",
            [("title", FieldTypeKind.STR), ("body", FieldTypeKind.TEXT)],
        )
        spec = _spec("Doc", [("title", 4), ("body", 1)])
        ddl = build_search_index_ddl([e], [spec])
        # title appears before body in the concatenation
        title_idx = ddl[0].find('"title"')
        body_idx = ddl[0].find('"body"')
        assert title_idx < body_idx
        assert " || " in ddl[0]


class TestTokenizer:
    def test_default_tokenizer_is_english(self):
        e = _entity("Doc", [("body", FieldTypeKind.TEXT)])
        spec = _spec("Doc", [("body", 1)])
        ddl = build_search_index_ddl([e], [spec])
        assert "to_tsvector('english'," in ddl[0]

    def test_explicit_french_tokenizer(self):
        e = _entity("Doc", [("body", FieldTypeKind.TEXT)])
        spec = _spec("Doc", [("body", 1)], tokenizer="french")
        ddl = build_search_index_ddl([e], [spec])
        assert "to_tsvector('french'," in ddl[0]

    def test_unknown_tokenizer_falls_back_to_english(self, caplog):
        e = _entity("Doc", [("body", FieldTypeKind.TEXT)])
        spec = _spec("Doc", [("body", 1)], tokenizer="klingon")
        with caplog.at_level("WARNING"):
            ddl = build_search_index_ddl([e], [spec])
        assert "to_tsvector('english'," in ddl[0]
        assert "klingon" in caplog.text

    def test_tokenizer_normalised_lowercase(self):
        e = _entity("Doc", [("body", FieldTypeKind.TEXT)])
        spec = _spec("Doc", [("body", 1)], tokenizer="ENGLISH")
        ddl = build_search_index_ddl([e], [spec])
        assert "to_tsvector('english'," in ddl[0]


# ---------------------------------------------------------------------------
# Field-skip behaviour
# ---------------------------------------------------------------------------


class TestFieldSkip:
    def test_dotted_path_skipped_with_warning(self, caplog):
        # Cycle 2 doesn't traverse FKs — `author.name` would need a
        # trigger or join expansion. Skip + log so the spec is
        # honoured incrementally.
        e = _entity(
            "Manuscript",
            [("title", FieldTypeKind.STR)],
        )
        spec = _spec("Manuscript", [("title", 4), ("author.name", 2)])
        with caplog.at_level("WARNING"):
            ddl = build_search_index_ddl([e], [spec])
        # Title still indexed; author.name dropped.
        assert '"title"' in ddl[0]
        assert "author" not in ddl[0]
        assert "author.name" in caplog.text

    def test_non_text_field_skipped_with_warning(self, caplog):
        # Integers / dates / bools can't go into tsvector cleanly.
        e = _entity(
            "Doc",
            [("title", FieldTypeKind.STR), ("page_count", FieldTypeKind.INT)],
        )
        spec = _spec("Doc", [("title", 4), ("page_count", 2)])
        with caplog.at_level("WARNING"):
            ddl = build_search_index_ddl([e], [spec])
        assert '"title"' in ddl[0]
        assert "page_count" not in ddl[0]
        assert "page_count" in caplog.text

    def test_unknown_field_skipped_with_warning(self, caplog):
        # `subtitle` doesn't exist on Doc.
        e = _entity("Doc", [("title", FieldTypeKind.STR)])
        spec = _spec("Doc", [("title", 4), ("subtitle", 2)])
        with caplog.at_level("WARNING"):
            ddl = build_search_index_ddl([e], [spec])
        assert '"title"' in ddl[0]
        assert "subtitle" in caplog.text

    def test_all_fields_skipped_returns_empty(self, caplog):
        # Spec references only non-resolvable fields → no DDL emitted.
        e = _entity("Doc", [("page_count", FieldTypeKind.INT)])
        spec = _spec("Doc", [("page_count", 4)])
        with caplog.at_level("INFO"):
            ddl = build_search_index_ddl([e], [spec])
        assert ddl == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_searches_returns_empty(self):
        e = _entity("Doc", [("title", FieldTypeKind.STR)])
        assert build_search_index_ddl([e], []) == []

    def test_unknown_entity_in_spec_warns_and_skips(self, caplog):
        e = _entity("Doc", [("title", FieldTypeKind.STR)])
        spec = _spec("DoesNotExist", [("title", 4)])
        with caplog.at_level("WARNING"):
            ddl = build_search_index_ddl([e], [spec])
        assert ddl == []
        assert "DoesNotExist" in caplog.text

    def test_multiple_search_specs_emit_independent_ddl_pairs(self):
        manuscript = _entity("Manuscript", [("title", FieldTypeKind.STR)])
        comment = _entity("Comment", [("body", FieldTypeKind.TEXT)])
        ddl = build_search_index_ddl(
            [manuscript, comment],
            [
                _spec("Manuscript", [("title", 4)]),
                _spec("Comment", [("body", 1)]),
            ],
        )
        assert len(ddl) == 4  # 2 specs × (ALTER + INDEX)
        assert any('"Manuscript"' in s and "ALTER" in s for s in ddl)
        assert any('"Comment"' in s and "ALTER" in s for s in ddl)

    def test_idempotent_clauses_present(self):
        # Both DDL statements use IF NOT EXISTS so dev-mode reboot
        # (which re-runs create_all + the index DDL) doesn't error.
        e = _entity("Doc", [("title", FieldTypeKind.STR)])
        spec = _spec("Doc", [("title", 4)])
        ddl = build_search_index_ddl([e], [spec])
        assert all("IF NOT EXISTS" in s for s in ddl)

    def test_email_and_url_fields_searchable(self):
        # Email + URL are text-shaped and should index naturally.
        e = _entity(
            "User",
            [("email", FieldTypeKind.EMAIL), ("homepage", FieldTypeKind.URL)],
        )
        spec = _spec("User", [("email", 4), ("homepage", 2)])
        ddl = build_search_index_ddl([e], [spec])
        assert '"email"' in ddl[0]
        assert '"homepage"' in ddl[0]
