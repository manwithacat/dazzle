"""Tests for documentation generator."""

import dazzle.mcp.server.docs_inventory  # noqa: F401 — registers the mcp_tools auto-source
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
    def test_loads_21_generated_pages(self) -> None:
        # 17 concept-assembled + 3 prose pages (rhythms, graphs, compliance)
        # + 1 auto-source page (mcp-tools). Hand-written pages registered for
        # index-linking only (#1372) carry `handwritten = true` and are
        # excluded from this count.
        pages = load_page_metadata()
        generated = {s: p for s, p in pages.items() if not p.get("handwritten")}
        assert len(generated) == 21

    def test_handwritten_pages_are_registered(self) -> None:
        # #1372: hand-written reference pages are registered in doc_pages.toml
        # with `handwritten = true` so the generated index links them.
        pages = load_page_metadata()
        handwritten = {s for s, p in pages.items() if p.get("handwritten")}
        assert handwritten, "no handwritten pages registered — #1372 regression"

    def test_pages_have_required_fields(self) -> None:
        pages = load_page_metadata()
        for _slug, page in pages.items():
            assert "title" in page
            assert "order" in page
            assert "intro" in page

    def test_prose_pages_carry_body(self) -> None:
        """Prose pages (no concept entries) must declare their content via `body`."""
        pages = load_page_metadata()
        for slug in ("rhythms", "graphs", "compliance"):
            assert slug in pages, f"prose page {slug!r} missing from doc_pages.toml"
            assert (pages[slug].get("body") or "").strip(), (
                f"prose page {slug!r} must declare a non-empty `body` field"
            )

    def test_mcp_tools_page_is_auto_source(self) -> None:
        """The MCP tool inventory must be auto-generated from the live registry."""
        pages = load_page_metadata()
        assert "mcp-tools" in pages, "mcp-tools page missing from doc_pages.toml"
        assert pages["mcp-tools"].get("auto_source") == "mcp_tools", (
            "mcp-tools page must declare `auto_source = 'mcp_tools'`"
        )


class TestMcpToolsInventory:
    """Tests for the live MCP tool inventory page."""

    def test_inventory_renders_at_least_one_tool(self) -> None:
        from dazzle.mcp.server.docs_inventory import generate_mcp_tools_inventory

        out = generate_mcp_tools_inventory()
        assert "## Tool index" in out
        assert "## Per-tool detail" in out
        # Spot-check a known stable tool.
        assert "### `dsl`" in out, "dsl tool must appear in the inventory"
        assert "### `knowledge`" in out
        assert "### `bootstrap`" in out

    def test_inventory_counts_match_registry(self) -> None:
        """The header tally must match what the registry actually exposes."""
        from dazzle.core.docs_gen import _extract_operations
        from dazzle.mcp.server.docs_inventory import generate_mcp_tools_inventory
        from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

        out = generate_mcp_tools_inventory()
        tools = get_all_consolidated_tools()
        total_ops = sum(len(_extract_operations(t.inputSchema)) for t in tools)
        assert f"**Live count:** {len(tools)} tools, {total_ops} operations." in out


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
