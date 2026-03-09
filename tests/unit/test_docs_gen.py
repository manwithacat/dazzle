"""Tests for documentation generator."""

from __future__ import annotations

from dazzle.core.docs_gen import (
    check_docs_coverage,
    generate_reference_docs,
    load_concepts,
    load_page_metadata,
)


class TestLoadConcepts:
    def test_loads_all_concepts(self) -> None:
        # Should load 88+ concepts (75 original + 13 new)
        concepts = load_concepts()
        assert len(concepts) >= 85

    def test_concepts_have_doc_page(self) -> None:
        concepts = load_concepts()
        with_page = [n for n, i in concepts.items() if i.get("doc_page")]
        assert len(with_page) >= 85

    def test_loads_patterns(self) -> None:
        concepts = load_concepts()
        patterns = [n for n, i in concepts.items() if i.get("source") == "patterns"]
        assert len(patterns) >= 20


class TestLoadPageMetadata:
    def test_loads_17_pages(self) -> None:
        pages = load_page_metadata()
        assert len(pages) == 17

    def test_pages_have_required_fields(self) -> None:
        pages = load_page_metadata()
        for _slug, page in pages.items():
            assert "title" in page
            assert "order" in page
            assert "intro" in page


class TestGenerateReferenceDocs:
    def test_returns_dict(self) -> None:
        docs = generate_reference_docs()
        assert isinstance(docs, dict)

    def test_has_all_pages(self) -> None:
        docs = generate_reference_docs()
        assert "entities" in docs
        assert "access-control" in docs
        assert "llm" in docs
        assert "index" in docs

    def test_pages_have_auto_generated_header(self) -> None:
        docs = generate_reference_docs()
        for _slug, content in docs.items():
            assert "Auto-generated" in content

    def test_pages_start_with_title(self) -> None:
        docs = generate_reference_docs()
        for _slug, content in docs.items():
            assert content.startswith("# ")

    def test_entities_page_has_entity_section(self) -> None:
        docs = generate_reference_docs()
        assert "## Entity" in docs["entities"]

    def test_no_empty_code_blocks(self) -> None:
        docs = generate_reference_docs()
        for _slug, content in docs.items():
            assert "```dsl\n\n```" not in content
            assert "```dsl\n```" not in content

    def test_index_has_table(self) -> None:
        docs = generate_reference_docs()
        assert "| Section |" in docs["index"]
        assert "entities.md" in docs["index"]


class TestCheckDocsCoverage:
    def test_no_errors(self) -> None:
        issues = check_docs_coverage()
        errors = [i for i in issues if i.startswith("ERROR")]
        assert errors == [], f"Coverage errors: {errors}"
